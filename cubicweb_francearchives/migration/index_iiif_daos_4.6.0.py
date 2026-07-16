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

# from cubicweb_francearchives.entities.es import DZFacetValues

# python add_iiif_daos_4.6.0.py cms -s=FRBNF -c -e
from cubicweb import _


class DZFacetValues:
    dz = _("digitized")
    nondz = _("non-digitized")
    dz_noniiif = _("digitized-noniiif")
    dz_iiif = _("digitized-iiif")

    @classmethod
    def dzitems(cls):
        return {
            "digitized-iiif": cls.dz_iiif,
            "digitized-noniiif": cls.dz_noniiif,
        }

    @classmethod
    def index_values(cls, digitized, iiif):
        """
        :param Bool digitized: value is digitized or not
        :param Bool align: value is digitized in iiif or not iiif
        """
        if digitized:
            if iiif:
                return [cls.dz, cls.dz_iiif]
            return [cls.dz, cls.dz_noniiif]
        return cls.nondz


DZ_VALUES = DZFacetValues.index_values(digitized=True, iiif=True)
SERVICES = {}


def get_json(entity, logger, published=False):
    try:

        json = entity.cw_adapt_to("IFullTextIndexSerializable").serialize()
        if published:
            json.pop("is_published")
        return json
    except Exception as err:
        logger.error(f"-> Failed to serialize {entity.cw_etype} {entity.eid} : {err}")
        return {}


def docs_to_index(es, index_name, docs):
    for esdoc in docs:
        assert esdoc["digitized_all"] == DZ_VALUES
        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": esdoc["stable_id"],
            "_source": esdoc,
        }


def es_index_findingaids(cnx, entities_to_index, logger):
    """Build and index ES documents"""
    es = get_connection(cnx.vreg.config)
    if not es or not es.ping():
        logger.error(f"{action}: Abort: no elasticsearch configuration found")
        return
    if not es or not es.ping():
        print("-> no es connection found: abort deletion")
        return
    index_name = cnx.vreg.config["index-name"] + "_all"
    public_index_name = cnx.vreg.config["published-index-name"] + "_all"

    # Index drafted FindingAid in public index
    eids = entities_to_index["draft"]
    if eids:
        logger.info(f"   -> ES index draft {len(eids)} FindingAids in {index_name} : ")
        draft_docs = [get_json(cnx.entity_from_eid(eid), logger) for eid in eids]
        fi_docs = docs_to_index(es, index_name, draft_docs)
        es_bulk_index(es, fi_docs, raise_on_error=True)

    # index published FindingAids in public index
    eids = entities_to_index["published"]
    if eids:
        logger.info(f"   -> ES index published {len(eids)} FindingAids in {index_name} : ")
        p_docs = [get_json(cnx.entity_from_eid(eid), logger) for eid in eids]
        fi_docs = docs_to_index(es, index_name, p_docs)
        es_bulk_index(es, fi_docs, raise_on_error=True)

        # index published FindingAids in published index
        p_docs = [get_json(cnx.entity_from_eid(eid), logger, published=True) for eid in eids]
        fi_docs = docs_to_index(es, public_index_name, p_docs)
        logger.info(
            f"   -> ES index published {len(eids)} FindingAids" f" in {public_index_name} : "
        )
        es_bulk_index(es, fi_docs, raise_on_error=True)
        cnx.drop_entity_cache()


def es_index_facomponents(cnx, entities_to_index, logger):
    es = get_connection(cnx.vreg.config)
    if not es or not es.ping():
        logger.error(f"{action}: Abort: no elasticsearch configuration found")
        return
    if not es or not es.ping():
        print("-> no es connection found: abort deletion")
        return
    index_name = cnx.vreg.config["index-name"] + "_all"
    public_index_name = cnx.vreg.config["published-index-name"] + "_all"

    # index drafted FAComponents in public index
    eids = entities_to_index["draft"]
    if eids:
        logger.info(f"   -> ES index draft {len(eids)} FAComponents in {index_name} : ")
        draft_docs = [get_json(cnx.entity_from_eid(eid), logger) for eid in eids]
        fa_docs = docs_to_index(es, index_name, draft_docs)
        es_bulk_index(es, fa_docs, raise_on_error=True)

    # index published FAComponents in public index
    eids = entities_to_index["published"]
    if eids:
        logger.info(f"   -> ES index published {len(eids)} FAComponents in {index_name} : ")

        _docs = [get_json(cnx.entity_from_eid(eid), logger) for eid in eids]
        fa_docs = docs_to_index(es, index_name, _docs)
        es_bulk_index(es, fa_docs, raise_on_error=True)

        # index published FAComponents in published index
        fa_docs = docs_to_index(es, public_index_name, _docs)
        logger.info(
            f"   -> ES index published {len(eids)} FAComponents" f" in {public_index_name} : "
        )
        es_bulk_index(es, fa_docs, raise_on_error=True)
        cnx.drop_entity_cache()


def main():
    args = parse_args()
    date = datetime.now().strftime("%Y%m%d-%H%M")
    filepath = f"{args.logdir}/index_iiif_daos_{date}.log"
    handler = logging.FileHandler(filepath)
    formatter = logging.Formatter("%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger = logging.getLogger("add_iiif_daos")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.info(f"Logs are stored in '{filepath}'")
    with admincnx(args.CW_INSTANCE) as cnx:
        index_iiif_manifests(cnx, args.services, logger)


def index_iiif_manifests(cnx, services, logger):
    if services:
        codes = services.split(",")
        query = "Any X, C WHERE X is Service, X code C, X code IN (%(s)s)" % {
            "s": ", ".join(f"'{c}'" for c in codes)
        }
        services = list(cnx.execute(query).entities())
        logger.info(f"Process Services {[s.code for s in services]} for codes {codes}")
    else:
        fi = [
            e
            for e, in cnx.execute(
                "DISTINCT Any S WHERE X is FindingAid, EXISTS(X digitized_versions D, D role 'iiif_manifest', X service S, S code C)"
            )
        ]
        fa = [
            e
            for e, in cnx.execute(
                "DISTINCT Any S WHERE X is FAComponent, X finding_aid F, EXISTS(X digitized_versions D, D role 'iiif_manifest', F service S)"
            )
        ]
        codes = set(fa).union(fi)
        query = "Any X, C WHERE X is Service, X code C, X eid IN (%(s)s)" % {
            "s": ", ".join(f"'{c}'" for c in codes)
        }
        services = list(cnx.execute(query).entities())
        logger.info(f"Process Services {[s.code for s in services]}")
    SERVICES = {}
    for service in services:
        if not service.code:
            logger.warning(
                f" -> Skip Service {service.dc_title()}, eid: {service.eid}:"
                " No code found for this service."
            )
            continue
        if not service.iiif_extptr:
            logger.warning(
                f" -> Skip Service {service.dc_title()}, eid : {service.eid}:" " IIIF is no active."
            )
            continue
        t = time()
        c = process_time()
        indexed = 0
        logger.info(
            f" -> Process Service {service.dc_title()}, code: {service.code}, eid: {service.eid}, url: {service.absolute_url()}"
        )
        findingaids = cnx.execute(
            f"DISTINCT Any X WHERE X is FindingAid, X digitized_versions D, D role 'iiif_manifest', X service S, S code '{service.code}'"
        )
        logger.info(f"Index {findingaids.rowcount} FindingAids")
        entities_to_index = defaultdict(list)
        for fidx, findingaid in enumerate(findingaids.entities()):
            indexed += 1
            state = (
                "published"
                if findingaid.cw_adapt_to("IWorkflowable").state == "wfs_cmsobject_published"
                else "draft"
            )
            entities_to_index[state].append(findingaid.eid)
            if fidx > 0 and not fidx % 1000:
                es_index_findingaids(cnx, entities_to_index, logger)
                logger.info(f"->  Indexed 1000/{fidx} FindingAids")
                entities_to_index = defaultdict(list)
        if entities_to_index:
            es_index_findingaids(cnx, entities_to_index, logger)
            logger.info(f"->  Indexed {fidx} FindingAids")
        facomponents = cnx.execute(
            f"DISTINCT Any X, F WHERE X is FAComponent, X finding_aid F, X digitized_versions D, D role 'iiif_manifest', F service S, S code '{service.code}'"
        )
        logger.info(f"Index {facomponents.rowcount} FAComponents")
        entities_to_index = defaultdict(list)
        for idx, (facomponent, findingaid) in enumerate(facomponents.iter_rows_with_entities()):
            indexed += 1
            state = (
                "published"
                if findingaid.cw_adapt_to("IWorkflowable").state == "wfs_cmsobject_published"
                else "draft"
            )
            entities_to_index[state].append(facomponent.eid)
            if idx > 0 and not idx % 1000:
                es_index_facomponents(cnx, entities_to_index, logger)
                logger.info(f"->  Indexed 1000/{idx} FAComponents")
                entities_to_index = defaultdict(list)
        if entities_to_index:
            es_index_facomponents(cnx, entities_to_index, logger)
            logger.info(f"->  Indexed {idx} FAComponents")
        logger.info(f"->  Done ES indexing")
        SERVICES[service.code] = {"indexed": indexed}
        logger.info(f"[Service {service.code}]: {SERVICES[service.code]}")
        logger.info(
            f"[Service {service.code}] clock: {process_time() - c:.9f} / time: {time() - t:.9f}"
        )
    logger.info(f"Indexed {sum([i['indexed'] for i in SERVICES.values()])} Documents")
    logger.info(f"DigitizedVersions and ES indexed documents by service: {SERVICES}")


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("CW_INSTANCE", help="Name of the CW application instance")

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
