# -*- coding: utf-8 -*-
#
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
#
"""cubicweb-ctl plugin providing additional commands

:organization: Logilab
:copyright: 2016 LOGILAB S.A. (Paris, FRANCE), all rights reserved.
:contact: http://www.logilab.fr/ -- mailto:contact@logilab.fr
"""


import os
import os.path as osp
import sys
import shutil
from glob import glob
from datetime import datetime
from itertools import chain
from functools import partial
import logging
import csv
from rql import parse as rql_parse
from time import process_time, time, sleep
import tqdm
import yaml

from urllib.parse import urlparse

from elasticsearch_dsl import Search, query as dsl_query
from elasticsearch.helpers import scan, parallel_bulk
from elasticsearch.exceptions import NotFoundError as EsNotFoundError

from logilab.database import get_connection
from logilab.common.decorators import monkeypatch

from cubicweb import ConfigurationError
from cubicweb.cwctl import CWCTL
from cubicweb.cwconfig import CubicWebConfiguration as cwcfg, CubicWebConfiguration
from cubicweb.toolsutils import Command, underline_title


from cubicweb_elasticsearch import es as cwes
from cubicweb_elasticsearch.ccplugin import IndexInES
from cubicweb_elasticsearch.es import indexable_entities

from cubicweb_francearchives import (
    S3_ACTIVE,
    NOMINA_INDEXABLE_ETYPES,
    AGENTS_REFERENCE_INDEXABLE_ETYPES,
    ColoredLogsMixIn,
)
from cubicweb_francearchives.storage import S3BfssStorageMixIn
from cubicweb_francearchives import admincnx, i18n, sitemap, init_bfss, utils, commemodump
from cubicweb_francearchives.dataimport.dc import import_filepath as dc_import_filepath
from cubicweb_francearchives.dataimport.directories import import_directory
from cubicweb_francearchives.dataimport.ead import readerconfig
from cubicweb_francearchives.dataimport.importer import import_filepaths
from cubicweb_francearchives.dataimport import oai, es_bulk_index, log_in_db, strip_html
from cubicweb_francearchives.entities.es import SUGGEST_ETYPES
from cubicweb_francearchives.entities.indexes import (
    LocationAuthority,
    SubjectAuthority,
    AgentAuthority,
)
from cubicweb_francearchives.dataimport.eac import eac_import_files
from cubicweb_francearchives.dataimport.maps import import_maps
from cubicweb_francearchives.dataimport.newsletter import import_subscribers
from cubicweb_francearchives.utils import init_repository, es_start_letter
from cubicweb_francearchives.xmlutils import enhance_accessibility
from cubicweb_francearchives import CMS_OBJECTS, CMS_I18N_OBJECTS
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import generate_ape_ead_files
from cubicweb_francearchives.dataimport.scripts.generate_ape_eac import generate_ape_eac_files
from cubicweb_francearchives.rdf import rdfdump
from cubicweb_francearchives.scripts.nginx_confs_from_faredirects import write_nginx_confs
from cubicweb_francearchives.scripts.reindex_nomina import reindex_nomina
from cubicweb_francearchives.scripts.dead_links import run_linkchecker, clean_up_linkchecker
from cubicweb_francearchives.scripts.eval_tags import EvalTagValues
from cubicweb_francearchives.scripts.check_db_integrity import DBIntegrityHelper
from cubicweb_francearchives.scripts.index_nomina import index_nomina_in_es
from cubicweb_francearchives.scripts.index_agents_reference import index_agents_reference_in_es
from cubicweb_francearchives.esutils import delete_autority_from_es

_tqdm = partial(tqdm.tqdm, disable=None)

HERE = osp.dirname(osp.abspath(__file__))


ETYPES_ES_MAP = {
    "ExternRef": {
        "cw_etypes": ["Virtual_exhibit", "Blog", "Other"],
        "rtype": "reftype",
    },
    "BaseContent": {
        "cw_etypes": [
            "Publication",
            "SearchHelp",
            "Article",
        ],
        "rtype": "content_type",
    },
}


def get_indexable_fa(cnx, etype, chunksize=100000, lasteid=0, log=None):
    rql = (
        "Any X, E, D, U, S ORDERBY X LIMIT {} WHERE "
        "X is {}, E is EsDocument, E entity X, E doc D, "
        "X cwuri U, X stable_id S, "
        "X eid > %(l)s"
    ).format(chunksize, etype)
    while True:
        if log:
            t1 = time()
        rset = cnx.execute(rql, {"l": lasteid})
        if not rset:
            break
        for e in rset.entities():
            yield e
        cnx.drop_entity_cache()
        if log:
            c1 = process_time()
            timeinfo = f"clock: {process_time() - c1:.9f} / time: {time() - t1:.9f}"

            log.info(
                f"  -> retrieved data for {rset.rowcount} {etype} from {lasteid}"
                f" to {rset[-1][0]} eid, {timeinfo}"
            )
        lasteid = rset[-1][0]


class PniaIndexInEs(IndexInES):
    """Index content in ElasticSearch.

    <instance id>
      identifier of the instance

    """

    options = IndexInES.options + [
        (
            "lasteid",
            {
                "short": "e",
                "type": "int",
                "default": None,
                "help": ("start index from the given eid (only for FAComponent and FindingAid"),
            },
        ),
        (
            "from-lastindexed",
            {
                "short": "f",
                "action": "store_true",
                "default": False,
                "help": (
                    "start index from the last indexed eid (only for FAComponent and FindingAid"
                ),
            },
        ),
    ]

    def bulk_actions(self, etypes, cnx, index_name=None, dry_run=False):
        self.log = logging.getLogger("index-in-es")
        self.log.setLevel(logging.DEBUG)
        index_name = index_name or "%s_all" % cnx.vreg.config["index-name"]
        self.log.info(f"[{index_name}]: start indexation for {etypes} \n")
        etypes = set(etypes) & set(cwes.indexable_types(cnx.vreg.schema))
        if not etypes:
            self.log.error("-> abort indexation: found no suitable etypes to index")
            return
        init_bfss(cnx.repo)
        for etype in etypes:
            start_msg = f"[{index_name}]: start indexing {etype}"
            if etype in ("FAComponent", "FindingAid"):
                lasteid = 0
                if self.config.lasteid and self.config.from_lastindexed:
                    self.log.error(
                        "only one of 'lasteid' or 'from-lastindexed' option can be used",
                        file=sys.stderr,
                    )
                    self.help()
                    sys.exit()
                if self.config.lasteid:
                    lasteid = int(self.config.lasteid)
                if self.config.from_lastindexed:
                    search = Search(index=index_name, extra={"size": 1}).sort(
                        {"eid": {"order": "desc"}}
                    )
                    must = [{"term": {"cw_etype": etype}}]
                    search.query = dsl_query.Bool(must=must)
                    response = search.execute()
                    if response and response.hits.total.value:
                        lasteid = response[0].eid
                if lasteid:
                    start_msg = f"[{index_name}]: start indexing {etype} from eid {lasteid}"
                gen = get_indexable_fa(
                    cnx, etype, chunksize=self.config.chunksize, lasteid=lasteid, log=self.log
                )
            else:
                gen = indexable_entities(cnx, etype, chunksize=self.config.chunksize)
            self.log.info(start_msg)
            idx = 0
            for idx, entity in enumerate(gen, 1):
                try:
                    serializer = entity.cw_adapt_to("IFullTextIndexSerializable")
                    json = serializer.serialize(complete=False)
                except Exception:
                    self.log.error(
                        "-> failed to serialize entity {} ({})".format(entity.eid, etype)
                    )
                    continue
                if not dry_run and json:
                    data = {
                        "_op_type": "index",
                        "_index": index_name,
                        "_id": serializer.es_id,
                        "_source": json,
                    }
                    self.customize_data(data)
                    yield data
                cnx.info(
                    "[{}] indexed {} {} entities (eid {})".format(
                        index_name, idx, etype, entity.eid
                    )
                )
            self.log.info(f"[{index_name}]: finished indexing {idx} {etype} \n")
        self.log.info(f"[{index_name}]: indexing completed for all etypes: {etypes}\n")
        sleep(5)  # wait for ES to finish
        for etype in etypes:
            search = Search(index=index_name)
            if etype in ETYPES_ES_MAP:
                must = [{"terms": {"cw_etype": ETYPES_ES_MAP[etype]["cw_etypes"]}}]
            else:
                must = [{"term": {"cw_etype": etype}}]
            search.query = dsl_query.Bool(must=must)
            self.log.info(f"[{index_name}]: found {search.count()} indexed {etype}")

    @staticmethod
    def strip_html_from_es_data(data):
        """Remove HTML tags from the data that will be sent to ElasticSearch"""
        # FIXME: get the attribute list from schema introspection
        attributes_to_strip = ["content"]

        for attr in attributes_to_strip:
            if attr in data["_source"] and data["_source"][attr]:
                data["_source"][attr] = strip_html(data["_source"][attr])

        return data


class ImportAll(Command):
    """call all import command"""

    arguments = "<instance>"
    name = "import-all"
    min_args = max_args = 1
    options = [
        (
            "config",
            {
                "short": "c",
                "type": "string",
                "default": osp.expanduser("~/.config/francearchives.yaml"),
                "help": "fichier contenant les paramètres de toutes les " "commandes",
            },
        ),
        (
            "skip",
            {
                "short": "S",
                "type": "csv",
                "default": (),
                "help": "Liste des commandes d'import à ignorer " "(séparées par des virgules)",
            },
        ),
        (
            "import-from",
            {
                "short": "F",
                "type": "string",
                "default": (),
                "help": "Commande d'import à partir de laquelle reprendre " "l'import",
            },
        ),
    ]

    def _build_cmd(self, cmd):
        cmd_line = [cmd, self.appid]
        if cmd not in self.yamlconfig:
            return cmd_line
        for k, v in list(self.yamlconfig[cmd].get("opts", {}).items()):
            opt_name = "--%s" % k
            if isinstance(v, bool) and v:
                cmd_line.append(opt_name)
            else:
                cmd_line.append(opt_name)
                cmd_line.append(v)
        for arg in self.yamlconfig[cmd].get("args", []):
            if "*" in arg:
                cmd_line += glob(arg)
            else:
                cmd_line.append(arg)
        return cmd_line

    def run(self, args):
        self.appid = args.pop(0)
        configpath = self.config.config
        if not osp.exists(configpath):
            print("path to config file does not exist", file=sys.stderr)
            self.help()
            sys.exit(1)
        with open(self.config.config) as f:
            self.yamlconfig = yaml.load(f)
        toskip = self.config.skip or ()
        fromcmd = self.config.import_from
        for cmdname in self.yamlconfig["commands"]:
            if fromcmd:
                if fromcmd != cmdname:
                    print("[import-all] skipping {}".format(cmdname))
                    continue
                fromcmd = None
            if cmdname in toskip:
                print("[import-all] skipping {}".format(cmdname))
                continue
            print("[import-all] {}".format(cmdname))
            try:
                CWCTL.run(self._build_cmd(cmdname))
            except SystemExit as exc:
                # if something went wrong, exit now
                if exc.code != 0:
                    raise


class ImportEAD(Command):
    """Import EAD files"""

    arguments = "<instance> <xmlfiles>"
    name = "import-ead"
    min_args = 1
    options = [
        (
            "esonly",
            {
                "action": "store_true",
                "default": False,
                "help": (
                    "contruit seulement les documents elasticsearch "
                    "(n'exécute aucune transaction sur la base postgres)"
                ),
            },
        ),
        (
            "fromfile",
            {
                "type": "string",
                "help": (
                    "lit la liste des fichiers depuis le fichier plutôt "
                    "que la ligne de commande. Le fichier lu doit contenir "
                    "un chemin de fichier par ligne"
                ),
            },
        ),
        (
            "noes",
            {
                "action": "store_true",
                "default": False,
                "help": "ne pousse pas les documents dans elasticsearch",
            },
        ),
        (
            "nodrop",
            {
                "action": "store_true",
                "default": False,
                "help": "ne détruit pas les index / contraintes PG durant l'import",
            },
        ),
        (
            "dedupe-authorities",
            {
                "type": "string",
                "default": "service/normalize",
                "help": "which mode of autodedupe algorithme we want to use",
            },
        ),
    ]

    def run(self, args):
        """call import_filepaths from dataimport.ead"""
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            if self.config.fromfile:
                if args:
                    print(
                        "si --fromfile est utilisé, aucun " "fichier ne doit être passé en argument"
                    )
                    sys.exit(1)
                with open(self.config.fromfile) as inputf:
                    filepaths = (line.strip() for line in inputf)
                    filepaths = [fpath for fpath in filepaths if fpath and fpath[0] != "#"]
            else:
                filepaths = args
            import_filepaths(
                cnx,
                filepaths,
                readerconfig(
                    cnx.vreg.config,
                    appid,
                    self.config.esonly,
                    self.config.nodrop,
                    autodedupe_authorities=self.config.dedupe_authorities,
                    noes=self.config.noes,
                ),
            )


class ImportDirectories(Command):
    """Import service directories.

    <instance id>
      identifier of the instance
    <services-directory>
      services-directory csv file
    <services-departements>
      services-departements csv file
    <services-logos-directory>
      directory containing services logos
    """

    arguments = "<instance> <directory> <departements> <logo-directory>"
    name = "import-directories"
    min_args = max_args = 4

    def run(self, args):
        """call import_directory from dataimport.directories"""
        appid, directory, departement, logos_directory = args
        with admincnx(appid) as cnx:
            import_directory(cnx, directory, departement, logos_directory)


class ImportEAC(Command):
    """Import EAC files"""

    arguments = "<instance> <xmlfiles>"
    name = "import-eac"
    min_args = 2

    def run(self, args):
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            eac_import_files(cnx, args)


class ImportOai(Command):
    """Harvest an OAI repository and import its content in the database."""

    arguments = "<instance> <oaiurls>"
    name = "import-oai"
    min_args = 2
    options = [
        (
            "fpath",
            {
                "short": "f",
                "type": "string",
                "help": (
                    "fichier contenant la correspondance entre les "
                    "services et les  urls moissonnées"
                ),
            },
        ),
    ]

    @staticmethod
    def url_key(url):
        parse_result = urlparse(url.strip())
        return parse_result.netloc + parse_result.path

    def load_services(self):
        services = {}
        with open(self.config.fpath) as f:
            reader = csv.reader(f)
            header = next(reader)  # noqa
            for entry in reader:
                # columns = 'Code_institution', 'URL'
                url = self.url_key(entry[1])
                if entry[0] and url:
                    services[url] = entry[0].strip()
        return services

    def run(self, args):
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            services_map = self.load_services()
            for url in args:
                url_key = self.url_key(url)
                service_infos = None
                service_code = services_map.get(url_key)
                if service_code:
                    rset = cnx.execute(
                        "Any X WHERE X is Service, X code %(s)s", {"s": service_code}
                    )
                    if len(rset) == 1:
                        service = rset.one()
                        service_infos = {
                            "code": service_code,
                            "name": service.publisher(),
                            "eid": service.eid,
                        }
                else:
                    service_code = urlparse(url).netloc
                if service_infos is None:
                    service_infos = {
                        "code": service_code,
                        "name": service_code,
                        "eid": None,
                    }
                try:
                    print("harvesting %r" % url)
                    oai.import_oai(cnx, url, service_infos)
                    cnx.commit()
                except Exception as exc:
                    print("failed to harvest %r because %s" % (url, exc))
                    cnx.rollback()


class IndexESAutocomplete(Command):
    """Index content for autocomplete search in ElasticSearch.

    <instance id>
      identifier of the instance

    """

    name = "index-es-suggest"
    min_args = max_args = 1
    arguments = "<instance id>"
    options = [
        (
            "dry-run",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to skip the insertion in ES",
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
        (
            "suggest-index-name",
            {
                "type": "string",
                "default": None,
                "help": (
                    "use a custom index name rather than the one "
                    "specified in the all-in-one.conf file. "
                    "(Note that no implicit _suggest suffix will be "
                    "appended to the index name specified by this option)"
                ),
            },
        ),
        (
            "etypes",
            {
                "type": "csv",
                "default": "",
                "help": (
                    "only index given etypes: "
                    "LocationAuthority, SubjectAuthority, AgentAuthority"
                ),
            },
        ),
    ]

    def suggest_index_name(self, cnx):
        if self.config.suggest_index_name:
            return self.config.suggest_index_name
        else:
            return "{}_suggest".format(cnx.vreg.config["index-name"])

    def run(self, args):
        """run the command with its specific arguments"""
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            self.log = logging.getLogger("index-es-suggest")
            if self.config.debug:
                self.log.setLevel(logging.DEBUG)
                self.log.debug("index: %s", self.suggest_index_name(cnx))
            indexer = cnx.vreg["es"].select("suggest-indexer", cnx)
            indexer.indexable_etypes = SUGGEST_ETYPES
            indexer.create_index(index_name=self.suggest_index_name(cnx))
            es = indexer.get_connection()
            if es:
                log_in_db(self.index_es_autosuggest)(cnx, es)
            else:
                if self.config.debug:
                    self.log.debug("no elasticsearch configuration found, skipping")

    def index_es_autosuggest(self, cnx, es):
        for _ in parallel_bulk(
            es,
            self.bulk_actions(cnx, es, dry_run=self.config.dry_run),
            raise_on_error=False,
            raise_on_exception=False,
        ):
            pass

    etype2type = {
        "LocationAuthority": "geogname",
        "SubjectAuthority": "subject",
        "AgentAuthority": "agent",
    }
    etype2urlsegment = {
        "LocationAuthority": "location",
        "SubjectAuthority": "subject",
        "AgentAuthority": "agent",
    }

    def bulk_actions(self, cnx, es, dry_run=False):
        etypes = self.config.etypes or self.etype2type.keys()
        auth_circ_map = dict(
            cnx.execute(
                """DISTINCT Any A, COUNT(X) GROUPBY A WITH X, A BEING (
                (Any X, A WHERE X is Circular, X business_field F, A same_as F)
                UNION
                (Any X, A WHERE X is Circular, X action F, A same_as F)
                UNION
                (Any X, A WHERE X is Circular, X document_type F, A same_as F)
                UNION
                (Any X, A WHERE X is Circular, X historical_context F, A same_as F)
                )"""
            )
        )
        try:
            suggest_index_name = self.suggest_index_name(cnx)
            for (
                etype,
                authtable,
                indextable,
            ) in (
                ("LocationAuthority", "cw_locationauthority", "cw_geogname"),
                ("SubjectAuthority", "cw_subjectauthority", "cw_subject"),
                ("AgentAuthority", "cw_agentauthority", "cw_agentname"),
            ):
                if etype not in etypes:
                    continue
                cnx.info(f"[{suggest_index_name}]: processing {etype}: loading data...")
                if self.config.debug:
                    print(f"[{suggest_index_name}]: processing {etype}: loading data...")
                # execute an SQL query instead of RQL like
                # Any X, L, COUNT(F), COUNT(B), COUNT(X1) GROUPBY X, L WHERE X is {etype},
                # X label L, A? authority X, B? related_authority X, A index F?,
                # X grouped_with X1?
                # as there is no simple way in RQL to count only distinct values

                query = """
                SELECT at.cw_eid, at.cw_label, at.cw_quality,
                    COUNT(DISTINCT rel_index.eid_to),
                    COUNT(DISTINCT rel_auth.eid_from),
                    COUNT(DISTINCT rel_group.eid_to)
                FROM {authtable} AS at
                    LEFT OUTER JOIN {indextable} AS it ON (it.cw_authority=at.cw_eid)
                    LEFT OUTER JOIN same_as_relation AS sa ON (sa.eid_from=at.cw_eid)
                    LEFT OUTER JOIN related_authority_relation AS rel_auth
                               ON (rel_auth.eid_to=at.cw_eid)
                    LEFT OUTER JOIN index_relation AS rel_index
                              ON (rel_index.eid_from=it.cw_eid)
                    LEFT OUTER JOIN grouped_with_relation AS rel_group
                              ON (rel_group.eid_from=at.cw_eid)
                GROUP BY at.cw_eid,at.cw_label"""
                rset = cnx.system_sql(
                    query.format(authtable=authtable, indextable=indextable)
                ).fetchall()
                cnx.info(f"start indexing {len(rset)} {etype}...")
                if self.config.debug:
                    print(f"start indexing {len(rset)} {etype}...")
                progress_bar = _tqdm(total=len(rset))
                for i, (
                    autheid,
                    label,
                    quality,
                    countfa,
                    countcomext,
                    countgrouped,
                ) in enumerate(rset):
                    if not dry_run:
                        try:
                            progress_bar.update()
                        except Exception:
                            pass
                        count_docs = countcomext + auth_circ_map.get(autheid, 0)
                        yield {
                            "_op_type": "index",
                            "_index": suggest_index_name,
                            "_id": autheid,
                            "_source": {
                                "cw_etype": etype,
                                "eid": autheid,
                                "text": label,
                                # do not use type from Geogname, Subject, AgentName
                                # because user could have group authorities so
                                # one authority could have 2 AgentName with two different
                                # type
                                "label": label,
                                "type": self.etype2type[etype],
                                "urlpath": "{}/{}".format(self.etype2urlsegment[etype], autheid),
                                "archives": countfa,
                                "siteres": count_docs,
                                "count": countfa + count_docs,
                                "grouped": bool(countgrouped),
                                "quality": quality,
                                "letter": es_start_letter(label),
                            },
                        }
                cnx.info(f"[{suggest_index_name}]: Finished indexing {etype}")
                if self.config.debug:
                    print(f"[{suggest_index_name}]: Finished indexing {etype}")

        except Exception as err:
            import traceback

            traceback.print_exc()
            print(f"Error while indexing!!! {err}")
            raise
        cnx.info(f"\n[{suggest_index_name}]: Suggest indexing terminated\n")
        if self.config.debug:
            print(f"\n[{suggest_index_name}]: Suggest indexing terminated\n")
        if self.config.debug:
            sleep(1)  # wait for ES to finish
            for etype in self.etype2type.keys():
                search = Search(index="{}".format(suggest_index_name))
                must = [{"term": {"cw_etype.keyword": etype}}]
                search.query = dsl_query.Bool(must=must)
                cnx.info(f"[{suggest_index_name}] -> found {search.count()} indexed {etype}")
                print(f"[{suggest_index_name}] -> found {search.count()} indexed {etype}")


@CWCTL.register
class IndexESNominaRecords(Command):
    """Index NominaRecords content.

    <instance id>
      identifier of the instance

    """

    name = "index-es-nomina"
    min_args = max_args = 1
    arguments = "<instance id>"
    options = [
        (
            "dry-run",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to skip the insertion in ES",
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": True,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
        (
            "stats",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you only want see indexed documents stats",
            },
        ),
        (
            "services",
            {
                "type": "csv",
                "default": (),
                "help": (
                    "List of services codes to be indexed separated by comma."
                    "If the list is empty, all services will be indexed"
                ),
            },
        ),
        (
            "act-types",
            {
                "type": "string",
                "default": "",
                "help": (
                    "List of notices act types to be indexed."
                    "If the option is empty, all notices will be indexed"
                ),
            },
        ),
        ("chunksize", {"type": "int", "default": 100000, "help": "chunksize size"}),
        (
            "index-name",
            {
                "type": "string",
                "default": None,
                "help": (
                    "use a custom index name rather than the one "
                    "specified in the all-in-one.conf file. "
                    "(Note that no implicit _suggest suffix will be "
                    "appended to the index name specified by this option)"
                ),
            },
        ),
    ]
    indexable_etypes = NOMINA_INDEXABLE_ETYPES
    failed_mark = "\033[91m" + "x" + "\033[0m"
    passed_mark = "\033[32m" + "\u2713" + "\33[0m"

    def index_name(self, cnx):
        if self.config.index_name:
            return self.config.index_name
        else:
            return cnx.vreg.config["nomina-index-name"]

    def run(self, args):
        """run the command with its specific arguments"""
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            indexer = cnx.vreg["es"].select("nomina-indexer", cnx)
            indexer.indexable_etypes = self.indexable_etypes
            index_name = self.index_name(cnx)
            indexer.create_index(index_name=index_name)
            es = indexer.get_connection()
            self.log = logging.getLogger("index-es-nomina")
            if self.config.debug:
                self.log.setLevel(logging.DEBUG)
            if self.config.stats:
                self.show_stats(cnx, es, index_name)
                return
            if es:
                log_in_db(index_nomina_in_es)(
                    cnx,
                    es,
                    index_name,
                    self.logger,
                    services=self.config.services,
                    act_types=self.config.act_types,
                    dry_run=self.config.dry_run,
                )
            else:
                if self.config.debug:
                    self.log.error("Error: no elasticsearch configuration found, abort.")

    def show_stats(self, cnx, es, index_name):
        search = Search(index=f"{index_name}")
        message = f"[{index_name}] {search.count()} NominaRecord(s) have been indexed"
        self.log.info(f" {self.passed_mark} {message}")


class ImportDC(Command):
    """Import findingaids"""

    arguments = "<instance> <csvfile1> [<csvfile2> ...]"
    name = "import-dc"
    min_args = 2
    options = [
        (
            "esonly",
            {
                "action": "store_true",
                "default": False,
                "help": (
                    "contruit seulement les documents elasticsearch "
                    "(n'exécute aucune transaction sur la base postgres)"
                ),
            },
        ),
        (
            "dedupe-authorities",
            {
                "type": "string",
                "default": "service/normalize",
                "help": "which mode of autodedupe algorithme we want to use",
            },
        ),
        (
            "noes",
            {
                "action": "store_true",
                "default": False,
                "help": "ne pousse pas les documents dans elasticsearch",
            },
        ),
    ]

    def run(self, args):
        appid = args[0]
        with admincnx(appid) as cnx:
            config = readerconfig(
                cnx.vreg.config,
                appid,
                self.config.esonly,
                autodedupe_authorities=self.config.dedupe_authorities,
                noes=self.config.noes,
                dc_no_cache=True,
            )
            for filepath in args[1:]:
                metadata_filepath = osp.join(osp.dirname(filepath), "metadata.csv")
                if not osp.exists(metadata_filepath):
                    metadata_filepath = None
                dc_import_filepath(cnx, config, filepath, metadata_filepath)


class ImportMaps(Command):
    """Import maps"""

    arguments = "<instance> <csvfile directory>"
    name = "import-maps"
    min_args = max_args = 2

    def run(self, args):
        """call import_maps from dataimport.maps"""
        appid, directory = args
        with admincnx(appid) as cnx:
            import_maps(cnx, directory)


class GenRedirect(Command):
    """generate map file for nginx to redirect previous url"""

    arguments = "<instance>"
    name = "fa-gen-redirect"
    min_args = max_args = 1
    options = [
        (
            "output",
            {
                "type": "string",
                "default": "map.conf",
                "short": "o",
                "help": "filepath to write map file",
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            baseurl_parsed = urlparse(cnx.vreg.config["base-url"])
            redirect_netloc = "redirect.%s" % baseurl_parsed.netloc
            rset = cnx.execute("Any X, U WHERE X previous_info Y, Y url U")
            redirects = []
            for idx, (eid, url) in enumerate(rset):
                entity = rset.get_entity(idx, 0)
                line = "~%s/%s/?$ %s;" % (redirect_netloc, url.strip("/"), entity.absolute_url())
                redirects.append(line)
            rset = cnx.execute(
                "Any F,FDN,FH WHERE F data_name FDN, "
                'F data_name LIKE "static_%", '
                "F data_hash FH, "
                "NOT EXISTS(X findingaid_support F)"
            )
            for f in rset.entities():
                basename = osp.splitext(f.data_name)[0]
                line = "~%s/%s/?$ %s;" % (
                    redirect_netloc,
                    "static/{}".format(basename.split("_")[-1]),
                    f.cw_adapt_to("IDownloadable").download_url(),
                )
                redirects.append(line)
            with open(self.config.output, "w") as fout:
                fout.write("\n".join(line.encode("utf-8") for line in redirects))


@CWCTL.register
class GenSitemap(Command):
    """generate sitemap files"""

    arguments = "<instance>"
    name = "fa-gen-sitemap"
    min_args = max_args = 1

    options = [
        (
            "base-url",
            {
                "type": "string",
                "default": None,
                "help": "custom base-url to use to build entity URLS",
            },
        ),
        (
            "clear-sitemap-dir",
            {
                "short": "c",
                "action": "store_true",
                "default": False,
                "help": "clear destination directory content before generating " "sitemap files",
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": True,
                "help": "set to True if you want to print out info",
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            cnx.info("[sitemap]: start generating sitemap")
            dst = cnx.vreg.config.get("sitemap-dir")
            if not dst:
                cnx.error('[sitemap]: abort: no "sitemap-dir" value found in all-in-one')
                return
            st = S3BfssStorageMixIn()
            if self.config.clear_sitemap_dir:
                if self.config.debug:
                    print(f'-> [sitemap]: remove existing files in sitemap directory "{dst}"')
                st.storage_clean_sitemap_files(dst)
            if self.config.base_url:
                cnx.vreg.config.global_set_option("base-url", self.config.base_url)
            sitemap.dump_sitemaps(cnx, st, dst)
            cnx.info("[sitemap]: finished generating sitemap files")


@CWCTL.register
class ImportNLSubscribers(Command):
    """import newsletter subscribers emails"""

    arguments = "<instance> <csvfile>"
    name = "import-subscribers"
    min_args = max_args = 2

    def run(self, args):
        appid, filepath = args
        with admincnx(appid) as cnx:
            import_subscribers(cnx, filepath)


@monkeypatch(cwcfg)
def _load_site_cubicweb(self, cube):
    """Load site_cubicweb.py from `cube` (or apphome if cube is None)."""
    mod = None
    if cube is not None:
        if not cube.startswith("cubicweb_"):
            try:
                modname = "cubicweb_%s" % cube
                __import__(modname)
            except ImportError:
                modname = "cubes.%s" % cube
                __import__(modname)
        else:
            modname = cube
        modname = modname + ".site_cubicweb"
        __import__(modname)
        mod = sys.modules[modname]
    else:
        import imp

        apphome_site = osp.join(self.apphome, "site_cubicweb.py")
        if osp.exists(apphome_site):
            with open(apphome_site, "rb") as f:
                mod = imp.load_source("site_cubicweb", apphome_site, f)
    if getattr(mod, "options", None):
        self.register_options(mod.options)
        self.load_defaults()


@CWCTL.register
class ESDumpSnapshot(Command):
    """create an ES snapshot"""

    name = "fa-es-dump"
    arguments = "<instance>"
    min_args = max_args = 1

    options = [
        (
            "snapshot-name",
            {
                "short": "s",
                "type": "string",
                "default": None,
                "help": "name of the snapshot (default to instance-name>-<timestamp>)",
            },
        ),
        (
            "setup-repository",
            {
                "action": "store_true",
                "default": False,
                "help": "setup ES repository before snapshotting",
            },
        ),
        (
            "delete-existing-snapshot",
            {
                "short": "d",
                "action": "store_true",
                "default": False,
                "help": "delete the snapshot if it alredy exists in ES before" "snapshotting",
            },
        ),
    ]

    def run(self, args):
        appid = args[0]
        cwconfig = cwcfg.config_for(appid)
        cwconfig.init_cubes(cwconfig.available_cubes())  # load all options
        print("elasticsearch-locations =", cwconfig["elasticsearch-locations"])
        if self.config.setup_repository:
            utils.es_setup_backup(cwconfig)

        snapshot_name = self.config.snapshot_name or "{}-{}".format(
            appid.lower(), datetime.now().strftime("%Y%m%d-%H:%M:%S")
        )
        utils.es_dump(cwconfig, snapshot_name, delete=self.config.delete_existing_snapshot)
        print(
            "The creation of the ES snapshot is in progress, it may "
            "take a while to complete. Please check "
            "http://%s/_cat/snapshots/francearchives-backups?v for "
            "job completion" % cwconfig.get("elasticsearch-locations")
        )


@CWCTL.register
class ESRestoreSnapshot(Command):
    """restore an ES snapshot"""

    name = "fa-es-restore"
    arguments = "<instance> <snapshot-name>"
    min_args = max_args = 2

    options = [
        (
            "index-prefix",
            {
                "short": "p",
                "type": "string",
                "default": "francearchives",
                "help": "basename of indices to restore (e.g. `xxx` in `xxx`_{all,suggest}",
            },
        ),
        (
            "delete-existing-indices",
            {
                "short": "d",
                "action": "store_true",
                "default": False,
                "help": "delete existing indices from ES before " "restore",
            },
        ),
    ]

    def run(self, args):
        appid, snapshot_name = args
        cwconfig = cwcfg.config_for(appid)
        cwconfig.init_cubes(cwconfig.available_cubes())  # load all options
        utils.es_restore(
            cwconfig,
            snapshot_name,
            self.config.index_prefix,
            delete=self.config.delete_existing_indices,
        )

        print(
            "The restore of the ES snapshot is in progress, it may "
            "take a while to complete. Please check "
            "http://%s/_cat/indices?v for "
            "job completion" % cwconfig.get("elasticsearch-locations")
        )


@CWCTL.register
class DeleteEAD(Command):
    """delete FindingAid and related entities in database and elasticsearch"""

    name = "fa-delete-ead"
    arguments = "<instance> <ead-files>"
    min_args = 2
    options = [
        (
            "esonly",
            {
                "action": "store_true",
                "default": False,
                "help": (
                    "supprime seulement les documents elasticsearch "
                    "(n'exécute aucune transaction sur la base postgres)"
                ),
            },
        ),
        (
            "interactive",
            {
                "action": "store_true",
                "default": False,
                "help": "force la demande des identifiants super-utilisateur postgresql",
            },
        ),
        (
            "stable-id",
            {
                "action": "store_true",
                "default": False,
                "help": "flag pour indiquer si les paramètres correspondent à des " "stable_id.",
            },
        ),
    ]

    def run(self, args):
        appid = args.pop(0)
        with admincnx(appid) as cnx:
            cnx.vreg.config.debugmode = True
            cnx.vreg.config.init_log(force=True)
            from cubicweb_francearchives.dataimport import sqlutil

            cnx.commit()
            sqlutil.delete_from_filenames(
                cnx,
                args,
                esonly=self.config.esonly,
                interactive=self.config.interactive,
                is_filename=not self.config.stable_id,
            )


@CWCTL.register
class DeleteInEs(Command):
    """restore an ES snapshot"""

    name = "fa-delete-in-es"
    arguments = "<instance>"
    min_args = max_args = 1

    options = [
        ("etypes", {"type": "csv", "default": "", "help": "only index given etypes"}),
    ]

    @staticmethod
    def es_documents(es, index_name, etype):
        """return all documents of type ``etype`` stored in ES"""
        for doc in scan(
            es,
            index=index_name,
            # no fields, limit result size, we only need metadata
            docvalue_fields=(),
        ):
            yield {
                "_op_type": "delete",
                "_index": index_name,
                "_id": doc["_id"],
            }

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            indexer = cnx.vreg["es"].select("indexer", cnx)
            es = indexer.get_connection()
            es_docs = []
            for etype in self.config.etypes:
                es_docs.append(self.es_documents(es, indexer.index_name, etype))
        es_bulk_index(es, chain(*es_docs), raise_on_error=False)


@CWCTL.register
class ReindexIR(Command):
    """reindex IR (PDF / XML) documents stored in the database.

    Internally runs import-ead but only with files referenced in
    the database.
    """

    name = "fa-reindex-ead"
    arguments = "<instance>"
    min_args = max_args = 1

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            rset = cnx.execute(
                "Any FSPATH(D) WHERE X is FindingAid, " "X findingaid_support F, F data D"
            )
            filepaths = [fspath.getvalue() for fspath, in rset]
            import_filepaths(cnx, filepaths, readerconfig(cnx.vreg.config, appid, True))


@CWCTL.register
class ReindexIRFromESDoc(Command):
    """reindex IR (PDF / XML) for its IFullTextIndexSerializable serialization"""

    name = "fa-reindex-ead-esdoc"
    arguments = "<instance> <stable_id>"
    min_args = max_args = 2

    options = [
        (
            "force",
            {
                "type": "yn",
                "default": False,
                "help": "delete existing data and reindex all",
            },
        ),
        (
            "index-name",
            {
                "type": "string",
                "default": None,
                "help": (
                    "use a custom index name rather than the one "
                    "specified in the all-in-one.conf file. "
                    "(Note that no implicit _suggest suffix will be "
                    "appended to the index name specified by this option)"
                ),
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": True,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
    ]

    def run(self, args):
        appid, stable_id = args
        with admincnx(appid) as cnx:
            self.log = logging.getLogger("fa-reindex-ead-esdoc")
            if self.config.debug:
                self.log.setLevel(logging.DEBUG)
            init_bfss(cnx.repo)
            rset = cnx.execute(
                """Any X WHERE X stable_id %(sti)s""",
                {"sti": stable_id},
            )
            if not rset:
                self.log.error(
                    "[fa-reindex-ead-esdoc] Error: no Findingaid "
                    "with stable_id {} found".format(stable_id)
                )
                return
            indexer = cnx.vreg["es"].select("indexer", cnx)
            index_name = self.config.index_name or indexer.index_name
            self.log.debug(f"[fa-reindex-ead-esdoc]: index in '{index_name}' index")
            es = indexer.get_connection()
            if not es:
                self.log.error(
                    "[fa-reindex-ead-esdoc] Error: no elasticsearch configuration found, skipping"
                )
                return
            entity = rset.one()
            if self.config.force:
                self.log.info("[fa-reindex-es-service] Delete indexed data")
                es.delete_by_query(
                    index=index_name,
                    body={"query": {"match": {"stable_id": stable_id}}},
                )
            try:
                serializer = entity.cw_adapt_to("IFullTextIndexSerializable")
                json = serializer.serialize(complete=False)
            except Exception:
                cnx.error(
                    "[{}] Failed to serialize entity {}".format(indexer.index_name, entity.eid)
                )
                return
            data = {
                "_op_type": "index",
                "_index": index_name,
                "_id": serializer.es_id,
                "_source": json,
            }
            self.log.debug(f"[fa-reindex-ead-esdoc]: start indexing {data}")
            es_bulk_index(es, [data], raise_on_error=True)
            self.log.debug("[fa-reindex-ead-esdoc]: finished indexing")


@CWCTL.register
class ReindexIRByStableId(Command):
    """reindex one IR (PDF / XML) documents stored in the database.

    Internally runs import-ead but only with files referenced in
    the database.
    """

    name = "fa-es-reindex"
    arguments = "<instance> <stable_id>"
    min_args = max_args = 2

    def run(sealf, args):
        appid, stable_id = args
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            rset = cnx.execute(
                """Any FSPATH(D) WHERE X is FindingAid,
                   X findingaid_support F, F data D,
                   X stable_id %(sti)s""",
                {"sti": stable_id},
            )
            if not rset:
                print("No Findingaid with stable_id {} found".format(stable_id))
                return
            filepaths = [fspath.getvalue() for fspath, in rset]
            import_filepaths(cnx, filepaths, readerconfig(cnx.vreg.config, appid, True))


SERVICE_ETPYES = ["FindingAid", "FAComponent", "BaseContent", "ExternRef"]


@CWCTL.register
class ReindexEsService(Command):
    """reindex FindingAid and FAComponent in es by service.

    This command dont delete existing data.

    arguments = '<instance> <service_code> <index_name>'
    """

    name = "fa-reindex-es-service"
    arguments = "<instance> <service_code> <index_name>"
    min_args = max_args = 3
    options = [
        (
            "index-name",
            {
                "type": "string",
                "default": None,
                "help": (
                    "use a custom index name rather than the one "
                    "specified in the all-in-one.conf file. "
                    "(Note that no implicit _suggest suffix will be "
                    "appended to the index name specified by this option)"
                ),
            },
        ),
        (
            "etypes",
            {
                "type": "csv",
                "default": SERVICE_ETPYES,
                "help": "list of cwetypes to be exported: %s" % SERVICE_ETPYES,
            },
        ),
        (
            "force",
            {
                "type": "yn",
                "default": False,
                "help": "delete existing data and reindex all",
            },
        ),
        (
            "dry-run",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to skip the insertion in ES",
            },
        ),
        ("chunksize", {"type": "int", "default": 100000, "help": "chunksize size"}),
        (
            "debug",
            {
                "type": "yn",
                "default": True,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
    ]

    def run(self, args):
        appid, service_code, index_name = args
        with admincnx(appid) as cnx:
            self.log = logging.getLogger("fa-reindex-es-service")
            if self.config.debug:
                self.log.setLevel(logging.DEBUG)
            service = cnx.execute("Any X WHERE X code %(c)s", {"c": service_code})
            if not service:
                self.log.error(
                    "[fa-reindex-es-service] Error: "
                    "no service with code {} exists".format(service_code)
                )
                return
            publisher = service.one().publisher()
            indexer = cnx.vreg["es"].select("indexer", cnx)
            index_name = self.config.index_name or indexer.index_name
            es = indexer.get_connection()
            if not es:
                self.log.error(
                    "[fa-reindex-es-service] Error: no elasticsearch configuration found, skipping"
                )
                return
            if self.config.force:
                self.log.info(
                    f"[fa-reindex-es-service] Delete {', '.join(self.config.etypes)}"
                    f" indexed data in {index_name} for '{publisher}'"
                )
                must = [{"term": {"service.code": service_code}}]
                esetypes = []
                for etype in self.config.etypes:
                    if etype in ETYPES_ES_MAP:
                        esetypes.extend(ETYPES_ES_MAP[etype]["cw_etypes"])
                    else:
                        esetypes.append(etype)
                must.append({"terms": {"cw_etype": esetypes}})
                es.delete_by_query(
                    index=index_name,
                    body={"query": {"bool": {"must": must}}},
                )
            for _ in parallel_bulk(
                es,
                self.bulk_actions(
                    cnx,
                    publisher,
                    index_name=index_name,
                    service_code=service_code,
                    chunksize=self.config.chunksize,
                    dry_run=self.config.dry_run,
                ),
                raise_on_error=False,
                raise_on_exception=False,
            ):
                pass

    def bulk_actions(self, cnx, publisher, index_name, service_code, chunksize, dry_run=True):
        for etype, gen in (
            ("FindingAid", self.get_indexable_fa(cnx, "FindingAid", publisher, chunksize)),
            ("FAComponent", self.get_indexable_fa(cnx, "FAComponent", publisher, chunksize)),
            (
                "BaseContent",
                self.get_indexable_cms(cnx, "BaseContent", "basecontent_service", service_code),
            ),
            ("ExternRef", self.get_indexable_cms(cnx, "ExternRef", "exref_service", service_code)),
        ):
            if etype not in self.config.etypes:
                continue
            for idx, entity in enumerate(gen, 1):
                try:
                    serializer = entity.cw_adapt_to("IFullTextIndexSerializable")
                    json = serializer.serialize(complete=False)
                except Exception:
                    self.log.error(
                        "[{}] Failed to serialize entity {} ({})".format(
                            index_name, entity.eid, etype
                        )
                    )
                    continue
                if not dry_run and json:
                    # Entities with
                    # fulltext_containers relations return their container
                    # IFullTextIndex serializer , therefor the "id" and
                    # "doc_type" in kwargs bellow must be container data.
                    data = {
                        "_op_type": "index",
                        "_index": index_name or cnx.vreg.config["index-name"],
                        "_id": serializer.es_id,
                        "_source": json,
                    }
                    yield data

    def get_indexable_cms(self, cnx, etype, rel, service_code):
        rql = cwes.fulltext_indexable_rql(etype, cnx)
        rqlst = rql_parse(rql).children[0]
        mainvar = next(rqlst.get_selected_variables())
        rset = cnx.execute(
            f"{rql}, {mainvar} {rel} {mainvar}SERVICE, {mainvar}SERVICE code '{service_code}'"
        )
        self.log.info(f"[fa-reindex-es-service] Reindex {rset.rowcount} {etype}")
        for e in rset.entities():
            e.complete()
            yield e

    def get_indexable_fa(self, cnx, etype, publisher, chunksize=100000):
        self.log.info(f"[fa-reindex-es-service] Reindex {etype}")
        rqlpart = (
            "X publisher %(p)s, "
            if etype == "FindingAid"
            else "X finding_aid FA, FA publisher %(p)s, "
        )
        lasteid = 0
        rql = (
            "Any X, E, D, U, S ORDERBY X LIMIT {} WHERE "
            "X is {}, E is EsDocument, E entity X, E doc D, "
            "X cwuri U, X stable_id S, "
            "{} "
            "X eid > %(l)s"
        ).format(chunksize, etype, rqlpart)
        while True:
            print("will execute", rql, {"l": lasteid, "p": publisher})
            rset = cnx.execute(rql, {"l": lasteid, "p": publisher})
            print("\tget", len(rset), "rows")
            if not rset:
                break
            for e in rset.entities():
                yield e
            cnx.drop_entity_cache()
            lasteid = rset[-1][0]


@CWCTL.register
class ReindexESNomina(Command):
    """reindex NominaRecord for its INominaIndexSerializable serialization"""

    name = "fa-reindex-es-nomina"
    arguments = "<instance> <stable_id>"
    min_args = max_args = 2

    options = [
        (
            "force",
            {
                "type": "yn",
                "default": False,
                "help": "delete existing data and reindex all",
            },
        ),
        (
            "index-name",
            {
                "type": "string",
                "default": None,
                "help": (
                    "use a custom index name rather than the one "
                    "specified in the all-in-one.conf file. "
                ),
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": True,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
    ]

    def run(self, args):
        appid, stable_id = args
        log = logging.getLogger("fa-reindex-es-nomina")
        if self.config.debug:
            log.setLevel(logging.DEBUG)
        with admincnx(appid) as cnx:
            reindex_nomina(
                cnx,
                stable_id,
                index_name=self.config.index_name,
                delete=self.config.force,
                logger=log,
            )


@CWCTL.register
class RdfDump(Command):
    """create a RDF dump of entities"""

    name = "fa-rdfdump"
    arguments = "<instance>"
    min_args = max_args = 1
    options = [
        (
            "etypes",
            {
                "type": "csv",
                "default": list(rdfdump.ETYPES_ADAPTERS),
                "help": "list of cwetypes to be exported: %s" % list(rdfdump.ETYPES_ADAPTERS),
            },
        ),
        (
            "graph",
            {
                "type": "string",
                "default": "ALL",
                "help": (
                    "graph to recreate (BASE : all the data, QUALITY: "
                    "qualified data for sparnatural, ALL: both graphs)"
                ),
            },
        ),
        (
            "published",
            {
                "type": "yn",
                "default": True,
                "help": "execute on published schema",
            },
        ),
        (
            "output-dir",
            {
                "type": "string",
                "default": "/tmp/rdfdata",
                "help": (
                    "directory where the rdf dumps are stored on the filesystem or "
                    "S3 name bucket"
                ),
            },
        ),
        (
            "formats",
            {
                "type": "csv",
                "default": ("nt",),
                "help": (
                    "comma separated list of formats you want to generate: 'nt', 'n3', 'xml' "
                    "(default to nt)"
                ),
            },
        ),
        (
            "chunksize",
            {
                "type": "int",
                "default": 2000,
                "help": "chunksize size",
            },
        ),
        (
            "limit",
            {
                "type": "int",
                "default": None,
                "help": "max number of entities generated",
            },
        ),
        (
            "offset",
            {
                "type": "int",
                "default": 0,
                "help": "offset of entities",
            },
        ),
        (
            "s3",
            {
                "action": "store_true",
                "default": False,
                "help": "store in s3 from AWS_S3_RDF_BUCKET_NAME",
            },
        ),
        (
            "s3db",
            {
                "action": "store_true",
                "default": False,
                "help": "delete existing s3 AWS_S3_BUCKET_NAME bucket",
            },
        ),
        (
            "s3rb",
            {
                "action": "store_true",
                "default": False,
                "help": "rename existing s3 AWS_S3_BUCKET_NAME bucket",
            },
        ),
        (
            "loads3",
            {
                "type": "yn",
                "default": True,
                "help": "load fs-generated RDF files on s3",
            },
        ),
        (
            "fsclean",
            {
                "type": "yn",
                "default": False,
                "help": "remove generated FS data",
            },
        ),
        (
            "dsql",
            {
                "type": "yn",
                "default": True,
                "help": "drop existing SQL tables",
            },
        ),
        (
            "c",
            {
                "type": "yn",
                "default": True,
                "help": "compress RDF files (do not compress archives)",
            },
        ),
        (
            "nbprocesses",
            {
                "type": "int",
                "help": "number of subprocesses to spawn to generate RDF dumps",
            },
        ),
        (
            "logfile",
            {
                "type": "string",
                "default": "/tmp/rdfdump.log",
                "help": "rdfdump logfil",
            },
        ),
        (
            "rqllog",
            {
                "action": "store_true",
                "default": False,
                "help": "dump rql queries on stdout",
            },
        ),
        (
            "profile",
            {
                "action": "store_true",
                "default": False,
                "help": "use cProfile to monitor execution (dump in /tmp/rdfdump.prof)",
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        try:
            rdfdump.rdfdumps(appid, self)
        except Exception as error:
            log = logging.getLogger(self.name)
            log.error(error)
        # then clean temporary tables. We can not create SQL temporary tables
        # as cnx can not be used in multiprocessing
        rdfdump.clean_sql_tables(appid)


@CWCTL.register
class RdfDumps3Loads(Command):
    """load generated RDF files from FS to S3"""

    name = "fa-rdfdump-s3load"
    arguments = "<instance>"
    min_args = max_args = 1
    options = [
        (
            "output-dir",
            {
                "type": "string",
                "default": "/tmp/rdfdata",
                "help": (
                    "directory where the rdf dumps are stored on the filesystem or "
                    "S3 name bucket"
                ),
            },
        ),
        (
            "s3db",
            {
                "action": "store_true",
                "default": False,
                "help": "delete existing s3 AWS_S3_BUCKET_NAME bucket",
            },
        ),
        (
            "s3rb",
            {
                "action": "store_true",
                "default": False,
                "help": "rename existing s3 AWS_S3_BUCKET_NAME bucket",
            },
        ),
        (
            "fsclean",
            {
                "type": "yn",
                "default": False,
                "help": "remove generated FS data",
            },
        ),
    ]

    def run(self, args):
        rdfdump.load_data_on_s3(self.config.output_dir, self)


class InitDatabase(Command):
    """Initialize the database **in the default namespace** but do NOT
    fill it with anything, and create entity tables for CMS entities
    and their relations in the namespace defined in the db-namespace config
    option

    """

    name = "db-init-tables"
    arguments = "<instance>"
    min_args = max_args = 1
    options = (
        (
            "drop",
            {
                "short": "d",
                "action": "store_true",
                "default": False,
                "help": (
                    "insert drop statements to remove previously existant "
                    "tables, indexes... (no by default)"
                ),
            },
        ),
    )

    def run(self, args):
        print("\n" + underline_title("Initializing the system database"))
        appid = args[0]
        config = CubicWebConfiguration.config_for(appid)
        try:
            system = config.system_source_config
            sqlschema = system.pop("db-namespace")
            extra_args = system.get("db-extra-arguments")
            extra = extra_args and {"extra_args": extra_args} or {}
            cnx = get_connection(
                system["db-driver"],
                database=system["db-name"],
                host=system.get("db-host"),
                port=system.get("db-port"),
                user=system.get("db-user") or "",
                password=system.get("db-password") or "",
                **extra,
            )
        except Exception as ex:
            raise ConfigurationError(
                "You seem to have provided wrong connection information in "
                "the %s file. Resolve this first (error: %s)."
                % (config.sources_file(), str(ex).strip())
            )
        init_repository(config, drop=self.config.drop)

        from cubicweb_francearchives.utils import setup_published_schema

        etypes = list(CMS_OBJECTS) + CMS_I18N_OBJECTS + ["CWProperty"]
        rtypes = ("in_state", "children", "news_image")
        with cnx.cursor() as cursor:
            setup_published_schema(cursor.execute, etypes, rtypes, sqlschema=sqlschema)
            cnx.commit()
        print("DONE")


@CWCTL.register
class EnhanceAccessibility(Command):
    """
    Apply some RGAA rules to CMS HTML content.
    For exemple:
     - add missing `alt` attribute on image
     - add `_blank` traget in extrenal links, etc
    """

    name = "rgaa"
    arguments = "<instance>"
    min_args = max_args = 1
    options = (("replace", {"short": "r", "action": "store_true", "help": "replace all content"}),)

    def run(self, args):
        appid = args.pop()
        replace_all = self.config.replace
        with admincnx(appid) as cnx:
            init_bfss(cnx.repo)
            with cnx.allow_all_hooks_but("metadata"):
                """XXX Images/CSSImage.caption and description are not processed so far"""
                count = 0
                query = (
                    'Any X, C WHERE X content C, X content_format "text/html", '
                    "X is IN (%(etypes)s), NOT X content NULL"
                )
                for eid, c in cnx.execute(query % {"etypes": ", ".join(list(CMS_OBJECTS))}):
                    content = enhance_accessibility(c, cnx, eid=eid)
                    if replace_all or content != c:
                        count += 1
                        cnx.execute(
                            "SET X content %(c)s WHERE X eid %(eid)s", {"eid": eid, "c": content}
                        )
                        cnx.commit()
                map_query = (
                    "Any X, T, B WHERE X is Map, "
                    "X top_content T, NOT X top_content NULL, "
                    'X top_content_format "text/html", '
                    "X bottom_content B, NOT X  bottom_content NULL, "
                    'X bottom_content_format "text/html"'
                )
                for eid, top, bottom in cnx.execute(map_query):
                    top = enhance_accessibility(top, cnx, eid=eid)
                    bottom = enhance_accessibility(bottom, cnx, eid=eid)
                    count += 1
                    cnx.execute(
                        "SET X top_content %(t)s, X bottom_content %(b)s WHERE X eid %(eid)s",
                        {"eid": eid, "t": top, "b": bottom},
                    )
                    cnx.commit()
                service_query = (
                    'Any X, O WHERE X other O, X other_format "text/html", '
                    "X is Service,  NOT X other NULL"
                )
                for eid, o in cnx.execute(service_query):
                    other = enhance_accessibility(o, cnx)
                    if replace_all or other != o:
                        count += 1
                        cnx.execute(
                            "SET X other %(o)s WHERE X eid %(eid)s", {"eid": eid, "o": other}
                        )
                        cnx.commit()
            print("fixed {} entities".format(count))


@CWCTL.register
class GenerateApeEadFiles(Command):
    """Generate ApeEad files for all FindingAids"""

    arguments = "<instance>"
    name = "generate-ape-ead"
    min_args = 1
    max_args = 3
    options = [
        (
            "all",
            {
                "action": "store_true",
                "default": False,
                "help": "generate ape-ead files for all ir",
            },
        ),
        (
            "service",
            {
                "short": "s",
                "type": "string",
                "help": "generate ape_ead files for all ir in service",
            },
        ),
    ]

    def run(self, args):
        """call generate_ape_ead from dataimport.ape_ead"""
        self.appid = args.pop(0)
        with admincnx(self.appid) as cnx:
            generate_ape_ead_files(cnx, self.config.all, service_code=self.config.service)


class GenerateApeEacFiles(Command):
    """Generate ApeEAC-CPF files for all AuthorityRecords"""

    arguments = "<instance>"
    name = "generate-ape-eac"
    min_args = 1
    max_args = 3
    options = [
        (
            "regenerate",
            {
                "action": "store_true",
                "default": False,
                "help": "regenerate ape-ead files for all AuthorityRecords",
            },
        ),
        (
            "service",
            {
                "short": "s",
                "type": "string",
                "help": (
                    "generate ape_ead files for all AuthorityRecords " "for a given service (code)"
                ),
            },
        ),
        (
            "eid",
            {
                "short": "e",
                "type": "string",
                "help": "generate ape_ead files for a given AuthorityRecord (eid)",
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
    ]

    def run(self, args):
        """call generate_ape_ead from dataimport.ape_ead"""
        self.appid = args.pop(0)
        with admincnx(self.appid) as cnx:
            log = logging.getLogger(self.name)
            generate_ape_eac_files(cnx, self.config, logger=log)


@CWCTL.register
class GenerateOaiRedirections(Command):
    """Create FindingAid and FAComponent nginx redirections files
    from data stored in fa_redirects sql table
    """

    name = "gen-fa-redirects"
    arguments = "<instance>"
    min_args = max_args = 1

    def run(self, args):
        appid = args.pop()
        with admincnx(appid) as cnx:
            write_nginx_confs(cnx)


@CWCTL.register
class FindDeadLinks(Command):
    """Find dead links using linkchecker tool."""

    name = "find-dead-links"
    arguments = "<instance><url>"
    min_args = max_args = 2

    options = [
        (
            "config",
            {"type": "string", "default": "", "help": "linkchecker configuration file path"},
        ),
        (
            "output-linkchecker",
            {"type": "string", "default": "/tmp", "help": "linkchecker output directory path"},
        ),
        (
            "output-dead-links",
            {"type": "string", "default": "/tmp", "help": "find-dead-links output file path"},
        ),
    ]

    def run(self, args):
        _, url = args
        try:
            print("run linkchecker")
            print("this may take some time")
            # linkchecker creates any missing directories in the user-defined path
            output_linkchecker = os.path.join(self.config.output_linkchecker, "linkchecker-out.csv")
            run_linkchecker(url, output_linkchecker, config=self.config.config)
        except RuntimeError as exception:
            print("WARNING:incomplete results:%s", str(exception))
        # create missing directories in the user-defined path
        os.makedirs(self.config.output_dead_links, exist_ok=True)
        clean_up_linkchecker(output_linkchecker, os.path.normpath(self.config.output_dead_links))


@CWCTL.register
class ProcessOrphanAuthorities(Command):
    """Find and delete orphan Authorities"""

    name = "delete-orphan-authorities"
    arguments = "<instance>"
    min_args = max_args = 1
    options = [
        (
            "dry-run",
            {
                "type": "yn",
                "default": True,
                "help": """set to False if you want to delete orphan authorities
                          (LocationAuthority, SubjectAuthority, AgentAuthority)""",
            },
        ),
        (
            "etypes",
            {
                "type": "csv",
                "default": "",
                "help": "only process/delete orphan authorities of given etypes",
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
    ]

    etype2class = {
        "LocationAuthority": LocationAuthority,
        "SubjectAuthority": SubjectAuthority,
        "AgentAuthority": AgentAuthority,
    }

    def run(self, args):
        appid = args.pop()
        etypes = ("LocationAuthority", "SubjectAuthority", "AgentAuthority")
        do_delete = not self.config.dry_run
        self.log = logging.getLogger(self.name)
        if self.config.debug:
            self.log.setLevel(logging.DEBUG)
        with admincnx(appid) as cnx:
            if self.config.etypes:
                etypes = self.config.etypes
            for etype in etypes:
                query = self.etype2class[etype].orphan_query()
                rset = cnx.execute(query)
                print("Find {count} orphan {etype}".format(count=rset.rowcount, etype=etype))
                if do_delete:
                    print("Delete {count} orphan {etype}".format(count=rset.rowcount, etype=etype))
                    progress_bar = _tqdm(total=rset.rowcount)
                    eids_to_delete = []
                    for i, eid in enumerate(rset):
                        eid = eid[0]
                        eids_to_delete.append(eid)
                        cnx.transaction_data["delete-orphans"] = True
                        # delete all trailing same_as for "LocationAuthority"
                        # and "SubjectAuthority")
                        if etype in ("LocationAuthority", "SubjectAuthority"):
                            cnx.execute("DELETE S same_as A WHERE A eid %(eid)s", {"eid": eid})
                            cnx.execute("DELETE A same_as S WHERE A eid %(eid)s", {"eid": eid})
                        cnx.execute(
                            "DELETE {etype} X WHERE X eid {eid}".format(etype=etype, eid=eid)
                        )
                        # delete from history table
                        cnx.system_sql(f"delete from authority_history where autheid={eid}")
                        if not i % 100:
                            # commit every 100 entities to limit memory consumption
                            cnx.commit()
                            # update es indexes
                            delete_autority_from_es(cnx, eids_to_delete, self.log)
                            eids_to_delete = []
                        try:
                            progress_bar.update()
                        except Exception:
                            pass
                    cnx.commit()
                    # update es indexes
                    delete_autority_from_es(cnx, eids_to_delete, self.log)


@CWCTL.register
class CommemoDump(Command):
    """
    Create posgresql and csv dumps of CommemorationItems
    """

    name = "commemo-dump"
    arguments = "<instance>"
    min_args = max_args = 1
    options = [
        (
            "output-dir",
            {
                "type": "string",
                "default": "/tmp",
                "help": "répertoire dans lequel les archives seront créées",
            },
        ),
        (
            "formats",
            {
                "type": "csv",
                "default": ("csv", "postgres"),
                "help": "liste des formats dans lequel on veut sérialiser le rdf (csv ou postgres)",
            },
        ),
    ]

    def run(self, args):
        appid = args.pop()
        if not set(self.config.formats).issubset(("csv", "postgres")):
            print("liste des formats contient format(s) non supporté(s)")
        with admincnx(appid) as cnx:
            output_dir = os.path.join(
                self.config.output_dir,
                "francearchives_commemorations_{}".format(datetime.now().strftime("%Y%m%d")),
            )
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
            os.makedirs(output_dir)
            commemodump.create_dumps(cnx, output_dir, self.config.formats)
            # remove output directory containing temporary files (pg_dump)
            shutil.rmtree(output_dir)


@CWCTL.register
class FACheckData(Command, ColoredLogsMixIn):
    """Check Fa Es data consistency"""

    arguments = "<instance>"
    name = "fa-check-data"
    min_args = max_args = 1

    options = [
        (
            "index-name",
            {"type": "string", "default": None, "help": "an existing es index "},
        ),
    ]

    def run(self, args):
        self.appid = args.pop(0)
        with admincnx(self.appid) as cnx:
            self.check_es_indexation(cnx)

    def check_es_indexation(self, cnx):
        """Compare the numbre of indexable entities in Postgres with the number of
        actually ES indexed entities

        """
        print("\n1. Check Elasticsearch/PostgreSQL data consistency\n")
        index_name = self.config.index_name or cnx.vreg.config["index-name"]

        es = cwes.get_connection(cnx.vreg.config)
        if not es:
            self.log("Error: no elasticsearch configuration found, skipping")
            return
        self.check_es_indexation_all(cnx, index_name)
        self.check_es_indexation_suggest(cnx, index_name)

    def check_es_indexation_all(self, cnx, index_name):
        all_index = f"{index_name}_all"
        search = Search(index=all_index)
        indexables_types = list(
            set(cwes.indexable_types(cnx.vreg.schema)[:]).difference(
                (
                    "File",
                    "SectionTranslation",
                    "BaseContentTranslation",
                    "SectionTranslation",
                    "CommemorationItemTranslation",
                )
            )
        )
        # we dont index File, XXXTranslation entities are indexed on their french version
        print(f"[{all_index}]\n")
        for etype in sorted(indexables_types):
            if etype in ETYPES_ES_MAP:
                must = [{"terms": {"cw_etype": ETYPES_ES_MAP[etype]["cw_etypes"]}}]
            else:
                must = [{"term": {"cw_etype": etype}}]
            if etype == "Card":
                rset = cnx.execute("Any COUNT(X) WHERE X is Card, X do_index True")
            else:
                rset = cnx.execute(f"Any COUNT(X) WHERE X is {etype}")
            search.query = dsl_query.Bool(must=must)
            es_search_count = search.count()
            self.log(
                cnx,
                f"[{all_index}] {es_search_count}/{rset[0][0]} {etype} indexed",
                status=rset[0][0] == es_search_count,
            )

            # specific cases
            if etype in ETYPES_ES_MAP:
                rtype = ETYPES_ES_MAP[etype]["rtype"]
                for es_cw_type in ETYPES_ES_MAP[etype]["cw_etypes"]:
                    search.query = dsl_query.Bool(must=[{"term": {"cw_etype": es_cw_type}}])
                    rset = cnx.execute(f'Any COUNT(X) WHERE X is {etype}, X {rtype} "{es_cw_type}"')
                    es_search_count = search.count()
                    self.log(
                        cnx,
                        f"[{all_index}]  -> {es_search_count}/{rset[0][0]} {es_cw_type} indexed",
                        status=rset[0][0] == es_search_count,
                    )

    def check_es_indexation_suggest(self, cnx, index_name):
        suggest_index = f"{index_name}_suggest"
        search = Search(index=suggest_index)
        print(f"\n[{suggest_index}]\n")
        for etype in ["AgentAuthority", "LocationAuthority", "SubjectAuthority"]:
            search.query = dsl_query.Bool(must=[{"term": {"cw_etype.keyword": etype}}])
            rset = cnx.execute(f"Any COUNT(X) WHERE X is {etype}")
            es_search_count = search.count()
            self.log(
                cnx,
                f"[{suggest_index}] {es_search_count}/{rset[0][0]} {etype} indexed",
                status=rset[0][0] == es_search_count,
            )


@CWCTL.register
class FACheckFiles(Command, ColoredLogsMixIn):
    """Check Files data consistency"""

    arguments = "<instance>"
    name = "fa-check-files"
    min_args = max_args = 1

    options = [
        (
            "output-dir",
            {
                "type": "string",
                "default": "/tmp",
                "help": "Directory to store log files",
            },
        ),
        (
            "check-content",
            {
                "action": "store_true",
                "default": "False",
                "help": "Check files exist",
            },
        ),
        (
            "check-all",
            {
                "action": "store_true",
                "default": "False",
                "help": "Check only IR files",
            },
        ),
    ]

    def run(self, args):
        self.appid = args.pop(0)
        with admincnx(self.appid) as cnx:
            init_bfss(cnx.repo)
            self.check_filepaths(cnx)

    def is_orphan_file(self, cnx, file_eid):
        """Returns true is the file is not linked to any other entity"""
        raise  # for now
        eschema = cnx.vreg.schema.entity_schema_for("File")
        objrels = [e.type for e in eschema.object_relations if not e.meta]
        rels = ["X{i} {rel} F".format(i=i, rel=rel) for i, rel in enumerate(objrels)]
        vars = ["X{i}".format(i=i) for i in range(len(objrels))]
        file_query = "Any {vars} WHERE F eid {eid}, {rels}".format(
            vars=", ".join(vars), rels=", ".join(rels), eid=file_eid
        )
        return not bool(cnx.execute(file_query).rowcount)

    def check_filepaths(self, cnx):
        print("\n1. Check S3/PostgreSQL data consistency\n")
        missings = set()
        unknown = set()
        missings_fpath = osp.join("/tmp", "missing_files.csv")
        if S3_ACTIVE:
            from botocore.exceptions import ClientError
        missings_fpath = osp.join(self.config.output_dir, "missing_files.csv")
        with open(missings_fpath, "w") as csvfile:
            csvwriter = csv.writer(csvfile, delimiter="\t")
            csvwriter.writerow(("filepath", "CWFile eid"))
        for etype, storagedict in cnx.repo.system_source._storages.items():  # noqa
            for attr in storagedict:
                storage = cnx.repo.system_source.storage(etype, attr)
                if self.config.check_all:
                    rset = cnx.execute(f"Any S, FSPATH(D) WHERE F is {etype}, F {attr} D")
                    print("Checking all files")
                else:
                    rset = cnx.execute(
                        """Any S, FSPATH(D) WHERE X is FindingAid,
                        X findingaid_support S, S data D
                        """
                    )
                    print("Checking only IR files")
                print(f"Checking {rset.rowcount} {etype} : {storagedict}")
                progress_bar = _tqdm(total=rset.rowcount)
                for idx, (eid, filepath) in enumerate(rset, 1):
                    if filepath is None:
                        missings.add(("", eid))
                        continue
                    filepath = filepath.getvalue().decode("utf8")
                    # orphan = self.is_orphan_file(cnx, eid)
                    if S3_ACTIVE:
                        try:
                            if self.config.check_content:
                                storage.s3cnx.get_object(Bucket=storage.bucket, Key=filepath)
                            else:
                                storage.s3cnx.head_object(Bucket=storage.bucket, Key=filepath)
                        except ClientError:
                            with open(missings_fpath, "a") as csvfile:
                                missings.add((filepath, filepath, eid))
                                csvwriter = csv.writer(csvfile, delimiter="\t")
                                csvwriter.writerow((filepath, eid))
                    else:
                        if not osp.isfile(filepath):
                            missings.add((filepath, "", eid))
                            continue
                    try:
                        progress_bar.update()
                    except Exception:
                        pass

        missings_dirs = osp.join("/tmp", "unknown_files.csv")
        with open(missings_dirs, "w") as csvfile:
            csvwriter = csv.writer(csvfile, delimiter="\t")
            csvwriter.writerow(("filepath",))
            for fpath in unknown:
                csvwriter.writerow((fpath,))
            # print(f" -> {fpath} \n")
        print(f"Found {len(unknown)} unknown files")
        print(f"Found {len(missings)} missing files storage")
        if missings:
            print(f"CSV file of missing paths {missings_fpath}")


@CWCTL.register
class IndexESAgentsReferenceRecords(Command):
    """Index AgentsReferenceRecords content.

    <instance id>
      identifier of the instance

    """

    name = "index-es-agents-ref"
    min_args = max_args = 1
    arguments = "<instance id>"
    options = [
        (
            "dry-run",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you want to skip the insertion in ES",
            },
        ),
        (
            "debug",
            {
                "type": "yn",
                "default": True,
                "help": "set to True if you want to print out debug info and progress",
            },
        ),
        (
            "stats",
            {
                "type": "yn",
                "default": False,
                "help": "set to True if you only want see indexed documents stats",
            },
        ),
        (
            "delete-index",
            {
                "short": "d",
                "action": "store_true",
                "default": False,
                "help": ("delete the existing index"),
            },
        ),
        ("chunksize", {"type": "int", "default": 100000, "help": "chunksize size"}),
        (
            "index-name",
            {
                "type": "string",
                "default": None,
                "help": (
                    "use a custom index name rather than the one "
                    "specified in the all-in-one.conf file. "
                    "(Note that no implicit _suggest suffix will be "
                    "appended to the index name specified by this option)"
                ),
            },
        ),
    ]
    indexable_etypes = AGENTS_REFERENCE_INDEXABLE_ETYPES
    failed_mark = "\033[91m" + "x" + "\033[0m"
    passed_mark = "\033[32m" + "\u2713" + "\33[0m"

    def delete_index(self, es, index_name):
        self.log.info(f"Delete index {index_name}")
        try:
            es.indices.delete(index=index_name)
            self.log.info(f"Index '{index_name}' deleted successfully.")
        except EsNotFoundError:
            self.log.info(f"Index '{index_name}' does not exist.")
        except Exception as e:
            self.log.error(f"Error deleting index: {e}")

    def index_name(self, cnx):
        if self.config.index_name:
            return self.config.index_name
        else:
            return cnx.vreg.config["agents-reference-index-name"]

    def run(self, args):
        """run the command with its specific arguments"""
        appid = args.pop(0)
        self.log = logging.getLogger(self.name)
        if self.config.debug:
            self.log.setLevel(logging.DEBUG)

        with admincnx(appid) as cnx:
            indexer = cnx.vreg["es"].select("agents-reference-indexer", cnx)
            indexer.indexable_etypes = self.indexable_etypes
            index_name = self.index_name(cnx)
            if not index_name:
                self.error("No index name found in config.")
                return
            es = indexer.get_connection()
            if self.config.delete_index:
                self.delete_index(es, index_name)
            indexer.create_index(index_name=index_name)
            if self.config.stats:
                self.show_stats(cnx, es, index_name)
                return
            if es:
                log_in_db(index_agents_reference_in_es)(
                    cnx,
                    es,
                    index_name,
                    self.logger,
                    dry_run=self.config.dry_run,
                )
            else:
                if self.config.debug:
                    self.log.error("Error: no elasticsearch configuration found, abort.")

    def show_stats(self, cnx, es, index_name, processed=None):
        if not processed:
            processed = cnx.execute("Any COUNT(X) WHERE X is AgentRecord")[0][0]
        search = Search(index=f"{index_name}")
        status = search.count() == processed
        message = f"[{index_name}] {search.count()}/{processed} AgentRecor(s) have been indexed"
        if status:
            self.log.info(f" {self.passed_mark} {message}")
        else:
            self.log.warning(f" {self.failed_mark} {message}")


@CWCTL.register
class DBIntegrity(Command, DBIntegrityHelper):
    """While importing data we disable all triggers which may result lein data
    unconsistency. Check DataBase consistency. For now it check onyly a few
    tables. To be continued.

    """

    arguments = "<instance>"
    name = "fa-db-check"
    min_args = max_args = 1

    options = [
        (
            "v",
            {"type": "yn", "default": True, "help": """print the queries"""},
        )
    ]

    def run(self, args):
        self.appid = args.pop(0)
        with admincnx(self.appid) as cnx:
            print("""Check database integrity after imports which will take some time.\n""")
            helper = DBIntegrityHelper(self.config)
            helper.check_indexes(cnx)
            helper.check_ir_documents(cnx)
            helper.check_authority_history(cnx)


for cmdclass in (
    ImportEAD,
    ImportEAC,
    ImportOai,
    ImportAll,
    ImportDC,
    ImportDirectories,
    IndexESAutocomplete,
    PniaIndexInEs,
    GenRedirect,
    ImportMaps,
    InitDatabase,
    EnhanceAccessibility,
    GenerateApeEadFiles,
    GenerateApeEacFiles,
    EvalTagValues,
    DBIntegrity,
):
    CWCTL.register(cmdclass)
i18n.register_cwctl_commands()
