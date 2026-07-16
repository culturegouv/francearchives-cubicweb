# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
# Contact http://www.logilab.fr -- mailto:contact@logilab.fr
#
# This software is governed by the CeCILL-C license under French law and
# abiding by the rules of distribution of free software. You can use,
# modify and/ or redistribute the software under the terms of the CeCILL-C
# license as circulated by CEA, CNRS and INRIA at the following URL
# "http://www.cecill.info".
#
# As a counterpart to the access to the source code and rights to copy,
# modify and redistribute granted by the license, users are provided only
# with a limited warranty and the software's author, the holder of the
# economic rights, and the successive licensors have only limited liability.
#
# In this respect, the user's attention is drawn to the risks associated
# with loading, using, modifying and/or developing or reproducing the
# software by the user in light of its specific status of free software,
# that may mean that it is complicated to manipulate, and that also
# therefore means that it is reserved for developers and experienced
# professionals having in-depth computer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systemsand/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.

from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime

import logging
import re
import requests
from time import process_time, time
from urllib.parse import urlparse

from cubicweb.utils import admincnx

from cubicweb_elasticsearch.es import get_connection
from elasticsearch import helpers as es_helpers

from cubicweb_francearchives import IIIF_MANIFEST_ROLE
from cubicweb_francearchives.dataimport import es_bulk_index, sqlutil
from cubicweb_francearchives.dataimport.stores import create_massive_store
from cubicweb_francearchives.entities.es import DZFacetValues

# python add_iiif_daos_4.6.0.py cms -s=FRBNF

DZ_VALUES = DZFacetValues.index_values(digitized=True, iiif=True)
SERVICES = {}


def get_json(entity, logger):
    try:
        return entity.cw_adapt_to("IFullTextIndexSerializable").serialize()
    except Exception as err:
        logger.error(f"-> Failed to serialize {entity.cw_etype} {entity.eid} : {err}")
        return {}


def es_index(cnx, entities_to_index, logger):
    """Build and index ES documents"""

    def docs_to_index(es, index_name, docs):
        for esdoc in docs:
            assert esdoc["digitized_all"] == DZ_VALUES
            yield {
                "_op_type": "index",
                "_index": index_name,
                "_id": esdoc["stable_id"],
                "_source": esdoc,
            }

    es = get_connection(cnx.vreg.config)
    if not es or not es.ping():
        logger.error(f"{action}: Abort: no elasticsearch configuration found")
        return
    if not es or not es.ping():
        print("-> no es connection found: abort deletion")
        return
    # index cms
    published_state = entities_to_index["is_published"]
    index_name = cnx.vreg.config["index-name"] + "_all"
    public_index_name = cnx.vreg.config["published-index-name"] + "_all"
    # Index FindingAid
    findingaid_eid = entities_to_index.get("fi")
    if "fi" in entities_to_index:
        findingaid = cnx.entity_from_eid(entities_to_index.get("fi")[0])
        logger.info(f"   -> ES index FindingAid {findingaid.eid} in {index_name}")
        json = get_json(findingaid, logger)
        if json:
            fi_docs = [
                {
                    "_op_type": "index",
                    "_index": index_name,
                    "_id": findingaid.stable_id,
                    "_source": json,
                }
            ]
            es_bulk_index(es, fi_docs, raise_on_error=True)
            if published_state:
                # index publisehd
                logger.info(f"   -> ES index FindingAid {findingaid.eid} in {public_index_name}")
                if "is_published" not in json:
                    logger.error(
                        f"JSON has no 'is_published' key for FindingAid {findingaid.stable_if}"
                    )
                else:
                    json.pop("is_published")
                fi_docs = [
                    {
                        "_op_type": "index",
                        "_index": public_index_name,
                        "_id": findingaid.stable_id,
                        "_source": json,
                    }
                ]
                es_bulk_index(es, fi_docs, raise_on_error=True)
        else:
            logger.error("-> Failed to serialize FindingAid {indingaid.eid}")
    # Index FAComponents
    eids = entities_to_index["fa"]
    logger.info(f"   -> ES index {len(eids)} FAComponents in {index_name} : ")
    _docs = [get_json(cnx.entity_from_eid(eid), logger) for eid in eids]
    fa_docs = docs_to_index(es, index_name, _docs)
    es_bulk_index(es, fa_docs, raise_on_error=True)
    if published_state:
        fa_docs = docs_to_index(es, public_index_name, _docs)
        logger.info(f"   -> ES index {len(eids)} FAComponents" f" in {public_index_name} : ")
        es_bulk_index(es, fa_docs, raise_on_error=True)
    cnx.drop_entity_cache()


def iiif_manifest_url(entity):
    """Compute manifest_url"""
    unprocessed_digitized_urls = entity.unprocessed_digitized_urls
    if not unprocessed_digitized_urls:
        return None
    service = entity.related_service
    if not service:
        logger.error("  No service found for %s %s", entity.cw_etype, entity.stable_id)
        return None
    if not entity.is_iiif_active:
        return None
    if service.code == "FRBNF":
        for dao, _ in unprocessed_digitized_urls:
            res = urlparse(dao)
            if res.netloc == "gallica.bnf.fr" and res.path.startswith("/ark:/"):
                # keep URL with /manifest
                if "/manifest" in res.path.lower() or res.path.endswith(".json"):
                    return dao
                return f"{res.scheme}://{res.netloc}/iiif{res.path}/manifest.json"
    elif service.code in ("FRAD053", "FRCDF"):
        for dao, _ in unprocessed_digitized_urls:
            res = urlparse(dao)
            regx = re.compile(r"(?P<visio>archives-en-ligne/)(?P<notice_id>ark:/.*/)f1")
            m = regx.search(res.path)
            if m:
                return f"{res.scheme}://{res.netloc}/{m.group('visio')}iiif/{m.group('notice_id')}manifest.json"  # noqa
    else:
        # services with iiif manifest url encoded in <extptr> (LIGEO editor)
        # or services using iiif_bnf policy with potential UUID in URL
        extptr = entity.did[0].extptr if entity.did else None
        if extptr and "ark:/" in extptr:
            res = urlparse(extptr)
            # Check if URL already contains /manifest or .json
            if "/manifest" in res.path.lower() or res.path.endswith(".json"):
                return extptr
            # Detect if URL contains a UUID at the end (standard pattern)
            uuid_pattern = re.compile(
                r"/([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})$"
            )
            match = uuid_pattern.search(res.path)
            if match:
                # URL with UUID: extract parent ARK
                ark_path = res.path[: match.start()]
                # For archives.somme.fr: use /group/0/manifest.json
                if res.netloc == "archives.somme.fr":
                    return f"{res.scheme}://{res.netloc}/iiif{ark_path}/group/0/manifest.json"
                else:
                    # Other domains: use standard /manifest.json
                    return f"{res.scheme}://{res.netloc}/iiif{ark_path}/manifest.json"
            else:
                # No UUID: use standard pattern
                return f"{extptr.rstrip('/')}/manifest"


def iiif_manifest_dao(cnx, entity, manifest_url, logger):
    """Test if iiif_manfest allready exists"""
    kwargs = {"url": manifest_url, "role": IIIF_MANIFEST_ROLE, "eid": entity.eid}
    rset = cnx.execute(
        """Any X WHERE X is DigitizedVersion, X role %(role)s, X url %(url)s,
           F digitized_versions X, F eid %(eid)s""",
        kwargs,
    )
    if rset.rowcount > 2:
        logger.error(f"{entity} has {rset.rowcount} IIIF manifest URL")
    # if rset.rowcount: # Delete existing IIIF for test purposes
    #     rset.one().cw_delete()
    #     cnx.commit()
    return bool(rset)


def add_dao(cnx, entity, manifest_url, logger):
    """Create a new dao"""
    logger.info(f"  Create {manifest_url} for {entity.cw_etype} {entity.stable_id}")
    cnx.create_entity(
        "DigitizedVersion",
        url=manifest_url,
        role=IIIF_MANIFEST_ROLE,
        reverse_digitized_versions=entity,
    )


def create_dao_extentity(store, entity, manifest_url, logger):
    """Create a DigitizedVersion dao extentity  for the entity (FindingAid of FAComponent)"""
    logger.info(f"  Create {manifest_url} for {entity.cw_etype} {entity.stable_id}")
    attrs = {"url": manifest_url, "role": IIIF_MANIFEST_ROLE}
    attrs["eid"] = store.prepare_insert_entity("DigitizedVersion", **attrs)
    store.prepare_insert_relation(entity.eid, "digitized_versions", attrs["eid"])


def massif_import_iiif_manifests(cnx, services, logger):
    """Create IIIF manifests daos with massif import"""
    all_services_codes = [
        c for c, in cnx.execute("Any C ORDERBY C WHERE X is Service, X code C, X iiif_extptr True")
    ]
    logger.info(f"All IIIF Services codes : {all_services_codes}")
    if services:
        codes = services.split(",")
        query = "Any X, C ORDERBY C WHERE X is Service, X code C, X code IN (%(s)s)" % {
            "s": ", ".join(f"'{c}'" for c in codes)
        }
        services = list(cnx.execute(query).entities())
        logger.info(f"Process Services {[s.code for s in services]} for codes {codes}")
    else:
        services = list(
            cnx.execute(
                "Any X, C ORDERBY C WHERE X is Service, X code C, X iiif_extptr True"
            ).entities()
        )
        logger.info(f"Process Services {[s.code for s in services]}")
    services_with_iiif_urls = [
        c
        for c, in cnx.execute(
            """Any C WITH C BEING (
        (DISTINCT Any C WHERE X is FindingAid, X digitized_versions D, D role 'iiif_manifest', X service S, S code C)
        UNION
        (DISTINCT Any C WHERE X is FAComponent, X finding_aid F, X digitized_versions D, D role 'iiif_manifest', F service S, S code C)
        )"""
        )
    ]
    # services_with_iiif_urls = []
    for service in services:
        if not service.code:
            logger.warning(
                f" -> Skip Service {service.dc_title()}, eid: {service.eid}:"
                " No code found for this service."
            )
            continue
        if service.code in services_with_iiif_urls:
            logger.warning(
                f" -> Skip Service {service.dc_title()}, eid : {service.eid}:"
                " this service already has IIIF URL. Reindex it."
            )
            continue
        if not service.iiif_extptr:
            logger.warning(
                f" -> Skip Service {service.dc_title()}, eid : {service.eid}:" " IIIF is no active."
            )
            continue
        with create_massive_store(cnx, nodrop=True) as store:
            es_entities = import_iiif_manifest_by_service(store, service, logger)
            logger.info(f"->  Start finishing massing import for service {service.dc_title()}")
        logger.info(f"->  Finished massing import for service {service.dc_title()}")
        if es_entities:
            es = get_connection(cnx.vreg.config)
            logger.info(
                f"->  [ES] Start indexing {len(es_entities)} entities for {service.dc_title()}"
            )
            for entities_to_index in es_entities:
                try:
                    es_index(cnx, entities_to_index, logger)
                except Exception as err:
                    logger.error(err)
                    logger.error(entities_to_index)
                    print(entities_to_index)
            logger.info(
                f"->  [ES] Done indexing {len(es_entities)} entities for {service.dc_title()}"
            )
    logger.info(
        f"Summary: created {sum([i['created'] for i in SERVICES.values()])} DigitizedVersion with IIIF manifest URL"
    )
    logger.info(f"Summary: indexed {sum([i['indexed'] for i in SERVICES.values()])} Documents")
    logger.info(f"Summary: for all services {SERVICES}")
    logger.info(f"All IIIF Services codes : {all_services_codes}")


def import_iiif_manifest_by_service(store, service, logger):
    t = time()
    c = process_time()
    created, indexed = 0, 0
    logger.info(
        f" -> Process Service {service.dc_title()}, code: {service.code}, eid: {service.eid}, url: {service.absolute_url()}"
    )
    cnx = store._cnx
    findingaids = cnx.execute(
        f"""Any F, SI WHERE X is Service, X eid {service.eid},
        F service X, F is FindingAid, F stable_id SI"""
    )
    ficount = findingaids.rowcount
    logger.info(f"Process {ficount} FindingAids")
    es_entities = []
    for fidx, findingaid in enumerate(findingaids.entities()):
        entities_to_index = defaultdict(list)
        manifest_url = iiif_manifest_url(findingaid)
        logger.info(f" -> Process FindingAid {findingaid.stable_id}: {fidx} out of {ficount} ")
        if manifest_url:
            if not iiif_manifest_dao(cnx, findingaid, manifest_url, logger):
                create_dao_extentity(store, findingaid, manifest_url, logger)
                created += 1
                entities_to_index["fi"].append(findingaid.eid)
                indexed += 1
        facomponents = cnx.execute(
            f"""Any FA, SI WHERE FA finding_aid F, F eid {findingaid.eid},
            FA is FAComponent, FA stable_id SI"""
        )
        logger.info(
            "    "
            f" ->  Process {facomponents.rowcount} FAComponents of "
            f"{findingaid.stable_id}"
        )
        for idx, facomponent in enumerate(facomponents.entities()):
            manifest_url = iiif_manifest_url(facomponent)
            if manifest_url:
                if not iiif_manifest_dao(cnx, facomponent, manifest_url, logger):
                    create_dao_extentity(store, facomponent, manifest_url, logger)
                    created += 1
                    entities_to_index["fa"].append(facomponent.eid)
                    indexed += 1
            if idx > 0 and not idx % 1000:
                logger.info("    " f" ->  Processed 1000/{idx} FAComponents")
        if entities_to_index:
            entities_to_index["is_published"] = (
                findingaid.cw_adapt_to("IWorkflowable").state == "wfs_cmsobject_published"
            )
            es_entities.append(entities_to_index)
        # commit for each findingaid and its facomponents
        # logger.info(f"->  Done rollback for FindingAid {findingaid.eid}")
    SERVICES[service.code] = {"created": created, "indexed": indexed}
    logger.info(f"[Service {service.code}] to be done: {SERVICES[service.code]}")
    logger.info(
        f"[Service {service.code}] clock: {process_time() - c:.9f} / time: {time() - t:.9f}"
    )
    return es_entities


def ead_foreign_key_tables(schema):
    etypes = {
        "FindingAid",
        "FAComponent",
        "DigitizedVersion",
    }
    return sqlutil.foreign_key_tables(schema, etypes)


def main():
    args = parse_args()
    date = datetime.now().strftime("%Y%m%d-%H%M")
    filepath = f"{args.logdir}/add_iiif_daos_{date}.log"
    handler = logging.FileHandler(filepath)
    formatter = logging.Formatter("%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger = logging.getLogger("add_iiif_daos")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info(f"Logs are stored in '{filepath}'")
    esindex = args.esindex
    if esindex:
        logger.info(f"New URL will be reindexed in ES")
    else:
        logger.info(f"New URL will not be reindexed in ES")
    with admincnx(args.CW_INSTANCE) as cnx:
        foreign_key_tables = ead_foreign_key_tables(cnx.vreg.schema)
        with sqlutil.no_trigger(cnx, foreign_key_tables, interactive=False, logger=logger):
            massif_import_iiif_manifests(cnx, args.services, logger)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("CW_INSTANCE", help="Name of the CW application instance")

    parser.add_argument(
        "-e",
        "--esindex",
        dest="esindex",
        action="store_true",
        help="index changes in ES",
    ),
    parser.add_argument(
        "-s",
        "--services",
        dest="services",
        default="",
        help="services codes",
    ),
    parser.add_argument(
        "-ld",
        "--logdir",
        dest="logdir",
        default="/tmp",
        help="logfile directiry",
    ),
    return parser.parse_args()


if __name__ == "__main__":
    main()
