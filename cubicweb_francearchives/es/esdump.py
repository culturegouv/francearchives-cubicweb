# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2019
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

# update ESDocument for all FindingAid
# python esdump.py instance --etypes=FindingAid --update-db

# update index ES <index_name> all FindingAid

# python esdump.py instance --index-name=index-name --schema=public --etypes=FindingAid  --update-es

from collections import defaultdict, OrderedDict
from jinja2 import Environment, PackageLoader
import logging
import multiprocessing as mp
from optparse import OptionParser
from psycopg2.errors import UndefinedTable
from psycopg2.extras import execute_batch
import time
import sys

from elasticsearch.helpers import parallel_bulk, bulk, BulkIndexError
from elasticsearch_dsl import Search, query as dsl_query
from elasticsearch_dsl.connections import connections

from logilab.common.decorators import timed

from cubicweb.utils import json_dumps
from cubicweb.entity import Relation

from cubicweb.rset import ResultSet

from cubicweb_francearchives import admincnx, IIIF_MANIFEST_ROLE
from cubicweb_francearchives.ccplugin import ETYPES_ES_MAP

ETYPES_ADAPTERS = OrderedDict(
    {
        "FAComponent": "IDumpFullTextIndexSerializable",
        "FindingAid": "IDumpFullTextIndexSerializable",
    }
)


def get_es_connection(locations, timeout=20):
    """
    Get connection with config object, creates a persistent connexion and
    """
    try:
        return connections.get_connection()
    except KeyError:
        if locations:
            # TODO sanitize locations
            es = connections.create_connection(
                hosts=locations.split(","),
                verify_certs=False,
                ssl_show_warn=False,
                timeout=timeout,
            )
            # test connection is alive while using the fonction
            return es


def get_last_indexed_eid(cnx, es_locations, index_name, etype):
    es = get_es_connection(es_locations)
    if not es or not es.ping():
        cnx.info("No elasticsearch connection, abort")
        sys.exit()
    search = Search(index=index_name, extra={"size": 1}).sort({"eid": {"order": "desc"}})
    must = [{"term": {"cw_etype": etype}}]
    search.query = dsl_query.Bool(must=must)
    response = search.execute()
    if response and response.hits.total.value:
        return response[0].eid


def get_last_updated_eid(cnx):
    rows = cnx.system_sql("SELECT last FROM tmp_last_esdocument").fetchall()
    return rows[0][0] if rows else None


def get_index_name(cnx, options, logger):
    index_name = options.get("index-name")
    if not index_name:
        index_name = cnx.vreg.config["index-name"]
    if not index_name and options.get("update-es"):
        logger.error("Abort: No elasticsearch index provided (--index-name option)")
        sys.exit()
    return f"{index_name}_all"


def _ecache_factory(rset, rows):
    return [rset.get_entity(rowidx, 1) for rowidx, row in rows]


def build_rset_from_sql(cnx, query, desc_info, emulated_rql):
    descr, rows = [], []
    rows = cnx.system_sql(query).fetchall()
    descr = (desc_info,) * len(rows)
    rset = ResultSet(rows, emulated_rql, description=descr)
    rset.req = cnx
    return rset


class BaseSQLHelper:
    def __init__(self, cnx, logger=None):
        self.cnx = cnx
        if not logger:
            logger = logging.getLogger("francearchives.esindex")
            logger.setLevel(logging.INFO)
        self.logger = logger

    def check_table_exists(self, table_name):
        query = "SELECT * FROM {0} LIMIT 1".format(table_name)
        try:
            self.cnx.system_sql(query)
            self.logger.info(f"[sql]: SQL tables for {table_name} already exist")
            return True
        except UndefinedTable:
            self.logger.info(f"[sql]: SQL tables for {table_name} don't exist")
            return False

    def execute_from_template(self, template):
        start = time.time()
        env = Environment(
            loader=PackageLoader("cubicweb_francearchives", "es/templates"),
        )
        env.filters["sqlstr"] = lambda x: "'{}'".format(x)  # noqa
        template = env.get_template(template)
        sqlcode = template.render()
        self.logger.info(sqlcode)
        self.cnx.system_sql(sqlcode)
        end = time.time()
        self.logger.info(f"{time.ctime()}: Finished generating tables" f"Took {end - start} secs")

    def create_sql_tables(self, update_db, update_es):
        self.logger.info("[sql]: Start generating SQL tables")
        if update_es and not self.check_table_exists("tmp_findingaid_es"):
            self.execute_from_template("create_es_tables.sql")
        if update_db and not self.check_table_exists("tmp_cw_esdocument"):
            self.execute_from_template("duplicate_esdoc.sql")

    def clean_sql_tables(self):
        env = Environment(
            loader=PackageLoader("cubicweb_francearchives", "es/templates"),
        )
        env.filters["sqlstr"] = lambda x: "'{}'".format(x)  # noqa
        template = env.get_template("drop_es_tables.sql")
        sqlcode = template.render()
        self.cnx.system_sql(sqlcode)
        self.logger.info("[sql]: Finished cleaning SQL tables")


class BaseIndexerCacher:
    etype = None
    fetch_all_rql = None
    restriction_rql = None  # Use EXISTS in the restrictions to avoid multiple rows in rset

    def __init__(self, logger):
        self.logger = logger

    def __str__(self):
        return f"{self.etype}IndexerCacher" if self.etype else "BaseIndexerCacher"

    def get_rql_selection_restriction(self):
        selection, restrictions = self.fetch_all_rql.split("WHERE")
        if self.restriction_rql:
            restrictions += f", {self.restriction_rql}"
        return selection, restrictions

    def build_query(self):
        query = self.fetch_all_rql
        if query is None:
            raise NotImplementedError()
        selection, restrictions = self.get_rql_selection_restriction()
        query = "%s ORDERBY X LIMIT %%s OFFSET %%s WHERE %s" % (
            selection,
            restrictions,
        )
        return query

    def build_rset(self, cnx, limit, offset, lasteid):
        query = self.build_query()
        if lasteid:
            query += f", X eid > {lasteid}"
        return cnx.execute(self.build_query() % (limit, offset), build_descr=True)

    def count_query(self):
        raise NotImplementedError

    def get_entities_count(self, cnx, limit, lasteid):
        return cnx.execute(self.count_query(limit, lasteid))[0][0]

    def set_entity_cache(
        self, cnx, etype, entities, query, cachekey, cache_factory=_ecache_factory, empty_value=()
    ):
        set_entity_cache(
            cnx, etype, entities, query, cachekey, cache_factory, empty_value, self.restriction_rql
        )

    def setup_iteration_cache(self, cnx, rset, schema, from_db=False, in_state=False):
        pass


class ArchivesIndexerCacher(BaseIndexerCacher):
    def count_query_sql(self, limit, lasteid):
        query = f"SELECT COUNT(cw_eid) FROM cw_{self.etype}"
        if lasteid:
            query += f" WHERE cw_eid > {lasteid}"
        return query

    def get_entities_count(self, cnx, limit, lasteid):
        nb_entities = cnx.system_sql(self.count_query_sql(limit, lasteid)).fetchone()[0]
        if limit:
            return nb_entities if nb_entities < limit else limit
        return nb_entities

    def build_emulated_rql(self, lasteid):
        query = self.fetch_all_rql
        if query is None:
            raise NotImplementedError()
        selection, restrictions = self.get_rql_selection_restriction()
        if lasteid:
            restrictions += f", X eid > {lasteid}"
        query = "%s ORDERBY X LIMIT %%s OFFSET %%s WHERE %s" % (
            selection,
            restrictions,
        )
        return query

    def build_query(self):
        raise NotImplementedError()

    def build_sql_query(self, lasteid):
        raise NotImplementedError()

    def build_rset(self, cnx, limit, offset, lasteid):
        raise NotImplementedError()

    def did_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_unittitle, _E.cw_unitid,
               _E.cw_startyear, _E.cw_stopyear, _E.cw_origination,
               _E.cw_abstract, _E.cw_note
        %s, cw_Did AS _E, cw_{etype} AS _X
        WHERE _X.cw_did=_E.cw_eid AND _X.cw_eid=_T0.C0
        """.format(
            etype=self.etype
        )
        rql_query = (
            "Any X, E, T, U, S, P, O, A, N  WHERE X did E, E is Did, "
            "E unitid U, E unittitle T, E startyear S, E stopyear P, "
            "E origination O, E abstract A, E note N"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "Did", "String", "String", "Int", "Int", "String", "String", "String"),
            rql_query,
            "esdump_did",
            first_entity_factory,
        )

    def originators_cache(self, cnx, entities):
        sql_query = f"""
        SELECT _X.cw_eid, _I.cw_authority, _A.cw_label
        %s, cw_AgentName AS _I, cw_AgentAuthority AS _A, cw_{self.etype} AS _X,
        index_relation AS rel_index0
        WHERE _X.cw_eid=_T0.C0 AND rel_index0.eid_from=_I.cw_eid
              AND rel_index0.eid_to=_X.cw_eid AND NOT (_I.cw_role='index')
              AND _I.cw_authority=_A.cw_eid
        """
        rql_query = (
            f"Any X, A, L WHERE I index X, X is {self.etype}, I authority A, "
            "I is AgentName, A label L, NOT I role 'index'"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            (self.etype, "AgentAuthority", "String"),
            rql_query,
            "esdump_originators",
        )

    def agents_cache(self, cnx, entities):
        sql_query = f"""
        SELECT _X.cw_eid, _I.cw_eid, _I.cw_authority, _I.cw_label, _I.cw_authfilenumber,
        _I.cw_type, _I.cw_role  %s, cw_AgentName AS _I, cw_{self.etype} AS _X,
        index_relation AS rel_index0
        WHERE _X.cw_eid=_T0.C0 AND rel_index0.eid_from=_I.cw_eid
              AND rel_index0.eid_to=_X.cw_eid AND _I.cw_authority IS NOT NULL
        """
        rql_query = (
            f"Any X, I, AE, L, N, T, R  WHERE I index X, X is {self.etype}, I authority A, "
            "A eid AE, I is AgentName, I label L, I authfilenumber N, I type T, I role R"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            (self.etype, "AgentName", "String", "String", "String", "String", "String"),
            rql_query,
            "esdump_agents",
            index_entity_factory,
        )

    def locations_cache(self, cnx, entities):
        sql_query = f"""
        SELECT _X.cw_eid, _I.cw_eid, _I.cw_authority, _I.cw_label, _I.cw_authfilenumber,
        _I.cw_type, _I.cw_role %s, cw_{self.etype} AS _X, cw_Geogname AS _I,
        index_relation AS rel_index0
        WHERE _X.cw_eid=_T0.C0 AND rel_index0.eid_from=_I.cw_eid
              AND rel_index0.eid_to=_X.cw_eid AND _I.cw_authority IS NOT NULL
        """
        rql_query = (
            f"Any X, I, AE, L, N, T WHERE I index X, X is {self.etype}, I authority A, "
            "A eid AE, I is Geogname, I label L, I authfilenumber N, I type T, I role R"
        )

        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            (self.etype, "Geogname", "String", "String", "String", "String", "String"),
            rql_query,
            "esdump_locations",
            index_entity_factory,
        )

    def subjects_cache(self, cnx, entities):
        sql_query = f"""
        SELECT _X.cw_eid, _I.cw_eid, _I.cw_authority, _I.cw_label, _I.cw_authfilenumber,
        _I.cw_type, _I.cw_role %s, cw_{self.etype} AS _X, cw_Subject AS _I,
        index_relation AS rel_index0
        WHERE _X.cw_eid=_T0.C0 AND rel_index0.eid_from=_I.cw_eid
              AND rel_index0.eid_to=_X.cw_eid AND _I.cw_authority IS NOT NULL
        """
        rql_query = (
            f"Any X, I, AE, L, N, T  WHERE I index X, X is {self.etype}, I authority A, "
            "A eid AE, I is Subject, I label L, I authfilenumber N, I type T, I role R"
        )

        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            (self.etype, "Subject", "String", "String", "String", "String", "String"),
            rql_query,
            "esdump_subjects",
            index_entity_factory,
        )

    def esdocument_cache(self, cnx, entities):
        sql_query = f"""
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_doc
        %s, cw_esdocument AS _E, cw_{self.etype} AS _X
        WHERE _E.cw_entity=_X.cw_eid AND _X.cw_eid=_T0.C0"""
        rql_query = "Any X, E, D WHERE E entity X, E is EsDocument, E doc D"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            (self.etype, "EsDocument", "String"),
            rql_query,
            "esdump_esdoc",
            first_entity_factory,
        )

    def set_entity_cache_from_sql(
        self,
        cnx,
        etype,
        entities,
        sql_query,
        descr_info,
        rql_query,
        cachekey,
        cache_factory=_ecache_factory,
        empty_value=(),
    ):
        if not entities:
            return
        rql_restriction = ""
        if self.restriction_rql:
            rql_restriction = f", {self.restriction_rql}"
        with_being = (
            ", X identity X2 WITH X2 BEING "
            "(Any X ORDERBY X LIMIT {0} WHERE X is {1}{2},"
            "X eid >= %(x)s)".format(len(entities), etype, rql_restriction)
        )
        emulated_rql = rql_query + with_being % {"x": min(entities)}
        etype_class = cnx.vreg["etypes"].etype_class(etype)
        _unbind_orm_relation(etype_class, cachekey)
        sql_with_being = (
            "FROM (SELECT _T.cw_eid AS C0 "
            "      FROM cw_{etype} AS _T "
            "      WHERE _T.cw_eid>={min_eid} "
            "      ORDER BY 1 "
            "      LIMIT {limit}) AS _T0 "
        ).format(min_eid=min(entities), limit=len(entities), etype=etype)
        rset = build_rset_from_sql(cnx, sql_query % sql_with_being, descr_info, emulated_rql)
        related, no_relation_eids = _grouped_rset(entities, rset)
        for main_entity_eid, rows in related.items():
            entity = cnx.entity_from_eid(main_entity_eid)
            entity.__dict__[cachekey] = cache_factory(rset, rows)
        for main_entity_eid in no_relation_eids:
            entity = cnx.entity_from_eid(main_entity_eid)
            entity.__dict__[cachekey] = empty_value


class FindingAidIndexerCacher(ArchivesIndexerCacher):
    etype = "FindingAid"
    table_name = "public.tmp_findingaid_es"
    fetch_all_rql = (
        "Any X,B,C,F,G,H,D,P,CD,MD,I,J,K"
        "WHERE X is FindingAid, X name B, X eadid C, "
        "X acquisition_info F, "
        "X scopecontent G, "
        "X stable_id H, "
        "X description D, "
        "X publisher P, "
        "X creation_date CD, "
        "X modification_date MD, "
        "X fa_header I?, "
        "X service J?, "
        "X did K?"
    )

    def build_sql_query(self, lasteid):
        restriction = ""
        if lasteid:
            restriction = f" WHERE X.cw_eid > {lasteid} "
        return (
            f"SELECT X.cw_eid, X.cw_name, X.cw_eadid, "
            f"X.cw_acquisition_info, X.cw_scopecontent, "
            f"X.cw_stable_id, X.cw_description, X.cw_publisher, "
            f"X.cw_creation_date, X.cw_modification_date, "
            f"X.cw_fa_header, X.cw_service, X.cw_did "
            f"FROM cw_FindingAid AS X {restriction} "
            f"ORDER BY cw_eid LIMIT %s OFFSET %s"
        )

    def build_rset(self, cnx, limit, offset, lasteid):
        descr_info = (
            self.etype,
            "String",
            "String",
            "String",
            "String",
            "String",
            "String",
            "String",
            "String",
            "String",
            "FAHeader",
            "Service",
            "Did",
        )
        query = self.build_sql_query(lasteid) % (limit, offset)
        emulated_rql = self.build_emulated_rql(lasteid) % (limit, offset)
        return build_rset_from_sql(cnx, query, descr_info, emulated_rql)

    def service_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_code, _E.cw_name, _E.cw_name2, _E.cw_short_name,
        _E.cw_level %s, cw_FindingAid AS _X, cw_Service AS _E
        WHERE _X.cw_service=_E.cw_eid AND
              _X.cw_eid=_T0.C0"""
        rql_query = (
            "Any X, E, C, N, NM, SN, L WHERE X service E, E is Service, E code C, "
            "E name N, E name2 NM, E short_name SN, E level L"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "Service", "String", "String", "String", "String", "String"),
            rql_query,
            "esdump_service",
            first_entity_factory,
        )

    def faheader_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_titleproper
        %s, cw_FAHeader AS _E, cw_FindingAid AS _X
        WHERE _X.cw_fa_header=_E.cw_eid AND _X.cw_eid=_T0.C0"""
        rql_query = "Any X, E, T WHERE X fa_header E, E is FAHeader, E titleproper T"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "FAHeader", "String", "String"),
            rql_query,
            "esdump_faheader",
            first_entity_factory,
        )

    def digitized_versions_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid
        %s , cw_DigitizedVersion AS _E, cw_{etype} AS _X,
        digitized_versions_relation AS rel_digitized_versions0
        WHERE rel_digitized_versions0.eid_from=_X.cw_eid AND
              rel_digitized_versions0.eid_to=_E.cw_eid AND
              _X.cw_eid=_T0.C0 LIMIT 1
        """.format(
            etype=self.etype
        )
        rql_query = "Any X, E WHERE E is DigitizedVersion"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            (self.etype, "DigitizedVersion"),
            rql_query,
            "esdump_digitized_versions",
        )

    def iiif_manifest_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid
        %s , cw_DigitizedVersion AS _E, cw_{etype} AS _X,
        digitized_versions_relation AS rel_digitized_versions0
        WHERE rel_digitized_versions0.eid_from=_X.cw_eid AND
              rel_digitized_versions0.eid_to=_E.cw_eid AND
              _E.cw_role='{role}' AND
              _X.cw_eid=_T0.C0 LIMIT 1
        """.format(
            etype=self.etype, role=IIIF_MANIFEST_ROLE
        )
        rql_query = f"Any X, E WHERE E is DigitizedVersion, E role '{IIIF_MANIFEST_ROLE}'"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            (self.etype, "DigitizedVersion", "String"),
            rql_query,
            "esdump_iiif_manifest",
        )

    def pdf_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _A.cw_eid
        %s, cw_File AS _A, cw_FindingAid AS _X
        WHERE _X.cw_findingaid_support=_A.cw_eid
              AND _A.cw_data_format='application/pdf'
              AND _X.cw_eid=_T0.C0 LIMIT 1
        """
        rql_query = """Any X, A, FSPATH(D) WHERE X findingaid_support A, A data D,
                       A data_format 'applicatio/pdf'"""
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "File"),
            rql_query,
            "esdump_pdf",
        )

    def in_state_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_name
        %s, cw_FindingAid AS _X, {table_name} as _E
        WHERE _X.cw_eid=_E.cw_eid AND _X.cw_eid=_T0.C0
        """.format(
            table_name=self.table_name
        )
        rql_query = "Any X, SN WHERE X  in_state S, S name SN"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "String"),
            rql_query,
            "esdump_in_state",
            in_state_factory,
        )

    def setup_iteration_cache(self, cnx, rset, schema, from_db=False, in_state=False):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            self.did_cache(cnx, entities)
            self.faheader_cache(cnx, entities)
            self.service_cache(cnx, entities)
            self.esdocument_cache(cnx, entities)
            self.agents_cache(cnx, entities)
            self.locations_cache(cnx, entities)
            self.subjects_cache(cnx, entities)
            if in_state:
                self.in_state_cache(cnx, entities)
            if from_db:
                self.digitized_versions_cache(cnx, entities)
                self.iiif_manifest_cache(cnx, entities)
                self.originators_cache(cnx, entities)
                self.pdf_cache(cnx, entities)

    def setup_iteration_esdoc_cache(self, cnx, rset, schema, in_state):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            self.esdocument_cache(cnx, entities)
            if in_state:
                self.in_state_cache(cnx, entities)


class FAComponentIndexerCacher(ArchivesIndexerCacher):
    etype = "FAComponent"
    table_name = "public.tmp_findingaid_es"
    fetch_all_rql = (
        "Any X,A,B,C,D,S,CD,F,G,H"
        "WHERE X is FAComponent, "
        "X accessrestrict A, "
        "X userestrict B, "
        "X acquisition_info C, "
        "X scopecontent D, "
        "X stable_id S, "
        "X creation_date CD, "
        "X did F?, "
        "X parent_component G?, "
        "X finding_aid H?"
    )

    def build_sql_query(self, lasteid):
        restriction = ""
        if lasteid:
            restriction = f" WHERE X.cw_eid > {lasteid} "
        return (
            f"SELECT X.cw_eid, X.cw_accessrestrict, X.cw_userestrict, "
            f"X.cw_acquisition_info, X.cw_scopecontent, X.cw_stable_id, "
            f"X.cw_creation_date, "
            f"X.cw_did, X.cw_parent_component, X.cw_finding_aid "
            f"FROM cw_FAComponent AS X {restriction} "
            f"ORDER BY cw_eid LIMIT %s OFFSET %s"
        )

    def build_rset(self, cnx, limit, offset, lasteid):
        descr_info = (
            self.etype,
            "String",
            "String",
            "String",
            "String",
            "String",
            "String",
            "Did",
            "FAComponent",
            "FindingAid",
        )
        query = self.build_sql_query(lasteid) % (limit, offset)
        emulated_rql = self.build_emulated_rql(lasteid) % (limit, offset)
        return build_rset_from_sql(cnx, query, descr_info, emulated_rql)

    def service_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_code, _E.cw_name, _E.cw_name2, _E.cw_short_name,
        _E.cw_level  %s, cw_FAComponent AS _X, cw_FindingAid AS _F, cw_Service AS _E
        WHERE _X.cw_finding_aid=_F.cw_eid AND _F.cw_service=_E.cw_eid AND _X.cw_eid=_T0.C0
        """
        rql_query = (
            "Any X, E, C, N, NM, SN, L WHERE X finding_aid F, F service E, E is Service, E code C, "
            "E name N, E name2 NM, E short_name SN, E level L"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FAComponent", "Service", "String", "String", "String", "String", "String"),
            rql_query,
            "esdump_service",
            first_entity_factory,
        )

    def findingaid_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_stable_id, _E.cw_creation_date
        %s, cw_FAComponent AS _X, cw_FindingAid AS _E
        WHERE _X.cw_finding_aid=_E.cw_eid AND _X.cw_eid=_T0.C0
        """
        rql_query = "Any X, E, C, CD WHERE X finding_aid E, E stable_id C, E creation_date CD"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FAComponent", "FindingAid", "String", "DateTime"),
            rql_query,
            "esdump_findingaid",
            first_entity_factory,
        )

    def setup_iteration_esdoc_cache(self, cnx, rset, schema, in_state):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            self.esdocument_cache(cnx, entities)

    def setup_iteration_cache(self, cnx, rset, schema, from_db=False, in_state=False):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            self.findingaid_cache(cnx, entities)
            self.did_cache(cnx, entities)
            self.service_cache(cnx, entities)
            self.esdocument_cache(cnx, entities)
            self.agents_cache(cnx, entities)
            self.locations_cache(cnx, entities)
            self.subjects_cache(cnx, entities)
            if from_db:
                self.digitized_versions_cache(cnx, entities)
                self.iiif_manifest_cache(cnx, entities)
                self.originators_cache(cnx, entities)


CACHER_CLASSES = {
    "findingaid": FindingAidIndexerCacher,
    "facomponent": FAComponentIndexerCacher,
}


def _grouped_rset(entities, rset):
    no_relation_eids = set(entities)
    related = defaultdict(list)
    for rowidx, row in enumerate(rset):
        related[row[0]].append((rowidx, row))
    no_relation_eids -= set(related)
    return related, no_relation_eids


def _unbind_orm_relation(eclass, rtype):
    # rtype descriptor might have been removed in a previous iteration
    # For now, the orm relations are not rebound after the esindextion
    # This is not an issue for its use in a dedicated process
    # If this function is called in a python script, the ORM entity attributes
    # will not be accessible afterwards (until the python objects are deleted
    # and recreated)
    if isinstance(eclass.__dict__.get(rtype), Relation):
        delattr(eclass, rtype)


def _cache_index_types_info(cnx, etype, entities, query):
    with_being = (
        ", X identity X2 WITH X2 BEING "
        "(Any X ORDERBY X LIMIT {0} WHERE X is {1}, "
        "X eid >= %(x)s)".format(len(entities), etype)
    )
    if not entities:
        return
    rset = cnx.execute(query + with_being, {"x": min(entities)})
    related, no_relation_eids = _grouped_rset(entities, rset)
    cachekey = "index_types"
    for main_entity_eid, rows in related.items():
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = tuple(set([row[1] for rowidx, row in rows]))
    for main_entity_eid in no_relation_eids:
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = ()


def first_entity_factory(rset, rows):
    assert len(rows) == 1, " relations are not supposed to be multivalued"
    return rset.get_entity(rows[0][0], 1)


def index_entity_factory(rset, rows):
    indexes = []
    for rowidx, row in rows:
        index = rset.get_entity(rowidx, 1)
        index.autheid = row[2]
        indexes.append(index)
    return indexes


def in_state_factory(rset, rows):
    for rowidx, row in rows:
        return row[1]


def set_entity_cache(
    cnx,
    etype,
    entities,
    query,
    cachekey,
    cache_factory=_ecache_factory,
    empty_value=(),
    restriction=None,
):
    if not entities:
        return
    rql_restriction = ""
    if restriction:
        rql_restriction = f", {restriction}"
    with_being = (
        ", X identity X2 WITH X2 BEING "
        "(Any X ORDERBY X LIMIT {0} WHERE X is {1}{2},"
        "X eid >= %(x)s)".format(len(entities), etype, rql_restriction)
    )
    etype_class = cnx.vreg["etypes"].etype_class(etype)
    _unbind_orm_relation(etype_class, cachekey)
    rset = cnx.execute(query + with_being, {"x": min(entities)})
    related, no_relation_eids = _grouped_rset(entities, rset)
    for main_entity_eid, rows in related.items():
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = cache_factory(rset, rows)
    for main_entity_eid in no_relation_eids:
        entity = cnx.entity_from_eid(main_entity_eid)
        entity.__dict__[cachekey] = empty_value


def bulk_actions(cnx, index_name, schema, etype, limit, offset, lasteid, cacher, debug, logger):
    rset = cacher.build_rset(cnx, limit, offset, lasteid)
    logger.info(
        f"[es]: Start retrieving related entities for {rset.rowcount} {schema} "
        f"{etype}: (offset {offset})"
    )
    in_state = schema == "public"
    cacher.setup_iteration_esdoc_cache(cnx, rset, schema, in_state=in_state)
    cursor = cnx.cnxset.cu
    if not rset:
        logger.warning("No entities found for %s" % rset.printable_rql())
        return
    for idx, entity in enumerate(rset.entities(), 1):
        es_id = entity.cw_adapt_to("IFullTextIndexSerializable").es_id
        json = cursor.execute(
            "SELECT cw_doc from cw_esdocument WHERE cw_entity=%(eid)s", {"eid": entity.eid}
        )
        # json = entity.esdump_esdoc.doc
        res = cursor.fetchall()
        if not res:
            logger.error(
                "Could not retrive data for cw_esdocument for entity %s %s. Adapt it from IFullTextIndexSerializable",  # noqa
                entity.cw_etype,
                entity.eid,
            )
            try:
                json = entity.cw_adapt_to("IFullTextIndexSerializable").serialize_from_db()
            except Exception as err:
                logger.error(
                    "Could not retrive data for cw_esdocument for entity %s %s: %s",  # noqa
                    entity.cw_etype,
                    entity.eid,
                    err,
                )
        else:
            json = res[0][0]
        if not json:
            logger.error("-> Failed to serialize entity {} ({})".format(entity.eid, etype))
            continue
        if schema == "public" and etype == "FindingAid":
            json["is_published"] = entity.esdump_in_state == "wfs_cmsobject_published"
        if debug:

            from pprint import pprint

            logger.info(pprint(json))
        data = {
            "_op_type": "index",
            "_index": index_name,
            "_id": es_id,
            "_source": json,
        }
        yield data

    logger.info(f"[{index_name}] Send to index {idx} {etype} entities, remove cache")
    cnx.drop_entity_cache()


def do_process(
    appid,
    es_locations,
    index_name,
    schema,
    cacher,
    etype,
    limit,
    offset,
    chunksize,
    lasteid,
    update_db,
    update_es,
    debug,
    logger,
):
    if update_db:
        update_pg(
            appid,
            cacher,
            etype,
            limit,
            offset,
            chunksize,
            lasteid,
            debug,
            logger,
        )
    if update_es:
        update_index(
            appid,
            es_locations,
            index_name,
            schema,
            cacher,
            etype,
            limit,
            offset,
            chunksize,
            lasteid,
            debug,
            logger,
        )


def update_pg(
    appid,
    cacher,
    etype,
    limit,
    offset,
    chunksize,
    lasteid,
    debug,
    logger,
):
    """Update PostgresSQL ESDocument for each entity"""
    with admincnx(appid) as cnx:
        if lasteid == "last":
            lasteid = get_last_updated_eid(cnx)
            logger.info(f"[postgres]: the last updated {etype} eid is {lasteid}")
        logger.info(f"[postgres]: User defined last eid: {lasteid}")
        limit = limit if limit and limit < chunksize else chunksize
        rset = cacher.build_rset(cnx, limit, offset, lasteid)
        if not rset:
            logger.warning("[postgres] No entities found for %s" % rset.printable_rql())
            return
        logger.info(
            f"[postgres]: Start updating related entities for {rset.rowcount} {etype}: "
            f"(offset {offset})"
        )
        cacher.setup_iteration_cache(cnx, rset, "public", from_db=False)
        logger.info(
            f"[postgres]: Done retrieving related entities for {rset.rowcount} {etype}: "
            f"(offset {offset})"
        )
        logger.info(f"[postgres] Start updating {rset.rowcount} {etype}: (offset {offset})")
        data = []
        adapter_regid = ETYPES_ADAPTERS.get(etype)
        if not rset:
            logger.warning("[postgres] No entities found for %s" % rset.printable_rql())
            return
        for idx, entity in enumerate(rset.entities(), 1):
            serializer = entity.cw_adapt_to(adapter_regid)
            if not serializer:
                logger.error(
                    "[postgres] Entity {} {} is not adaptable to {}".format(
                        entity.cw_etype, entity.eid, adapter_regid
                    )
                )
                continue
            try:
                json = serializer.serialize(complete=False)
                if not json:
                    logger.error(
                        "-> [postgres] Failed to serialize entity {} ({})".format(entity.eid, etype)
                    )
                    continue
            except Exception as err:
                logger.error(
                    "-> [postgres] Failed to serialize entity {} ({}); {}".format(
                        entity.eid, etype, err
                    )
                )
                continue
            if not entity.esdump_esdoc:
                logger.error(
                    "-> [postgres] No EsDocument found for entity {} ({})".format(entity.eid, etype)
                )
                continue
            data.append((json_dumps(json), entity.eid))
        if debug:
            from pprint import pprint

            for doc in data:
                logger.warning(pprint(doc))
        else:
            execute_batch(
                cnx.cnxset.cu,
                "UPDATE cw_esdocument SET cw_doc=%s WHERE cw_entity=%s",
                data,
            )
            logger.info(
                f"[postgres]: updated {etype} ESDocuments from {rset[0][0]} to {entity.eid}"
            )
            cnx.cnxset.cu.execute("UPDATE tmp_last_esdocument SET last=%s", (entity.eid,))
            cnx.commit()
        logger.info(f"[postgres]: {idx} {etype} entities, remove cache")


def update_index(
    appid,
    es_locations,
    index_name,
    schema,
    cacher,
    etype,
    limit,
    offset,
    chunksize,
    lasteid,
    debug,
    logger,
):
    with admincnx(appid) as cnx:
        if schema == "published":
            set_published_schema(cnx)
        if lasteid == "last":
            lasteid = get_last_indexed_eid(cnx, es_locations, index_name, etype)
            logger.info(f"[es indexer]: the last indexed {etype} eid is {lasteid}")
        logger.info(f"[es indexer]: Index {schema} {etype} from eid: {lasteid}")
        limit = limit if limit and limit < chunksize else chunksize
        es = get_es_connection(es_locations)
        if not es or not es.ping():
            cnx.info("[es indexer]: No elasticsearch connection, abord")
            sys.exit()
        if debug:
            # try to index juste one entity to get more debug info on bulk error"
            index_one_for_debug(
                cnx,
                es,
                index_name,
                schema,
                etype,
                1,
                offset,
                lasteid,
                cacher,
                debug,
                logger,
            )
        else:
            for res, data in parallel_bulk(
                es,
                bulk_actions(
                    cnx,
                    index_name,
                    schema,
                    etype,
                    limit,
                    offset,
                    lasteid,
                    cacher,
                    debug,
                    logger,
                ),
                raise_on_error=True,
                raise_on_exception=True,  # must be an option
            ):
                if not res:
                    logger.error(
                        "[es indexer]: A error occured while indexing %s with %s es_id"
                        % (etype, data["index"]["_id"])
                    )
                    sys.exit()
        time.sleep(5)  # wait for ES to finish
        search = Search(index=index_name)
        if etype in ETYPES_ES_MAP:
            must = [{"terms": {"cw_etype": ETYPES_ES_MAP[etype]["cw_etypes"]}}]
        else:
            must = [{"term": {"cw_etype": etype}}]
            search.query = dsl_query.Bool(must=must)
        logger.info(f"[es indexer]: found {search.count()} indexed {etype} in {index_name}")


def index_one_for_debug(
    cnx, es, index_name, schema, etype, limit, offset, lasteid, cacher, debug, logger
):
    """try to index juste one entity to get more debug info on bulk error"""
    try:
        bulk(
            es,
            bulk_actions(
                cnx, index_name, schema, etype, limit, offset, lasteid, cacher, debug, logger
            ),
            raise_on_error=True,
            raise_on_exception=True,
            stats_only=False,
        )
    except BulkIndexError as exception:
        from pprint import pprint

        pprint(exception.errors)


def set_published_schema(cnx):
    cnx.system_sql("SET search_path TO published, public;")


class ESProcessor:
    def __init__(self, schema, etype, logger):
        self.etype = etype
        self.schema = schema
        self.logger = logger
        self._es_locations = None
        self._es_index_name = None

    def es_locations(self, cnx=None, options=None):
        if self._es_locations is None:
            self._es_locations = (
                options.get("elasticsearch-locations") or cnx.vreg.config["elasticsearch-locations"]
            )
        self.logger.info(f"[ES host]: {self._es_locations}")
        return self._es_locations

    def index_name(self, cnx=None, options=None):
        if self._es_index_name is None:
            self._es_index_name = get_index_name(cnx, options, self.logger)
        self.logger.info(f"[ES index-name]: {self._es_index_name}")
        return self._es_index_name

    def teardown_cache(self, cnx, rset=None):
        cnx.drop_entity_cache()

    def process_entities(self, appid, options):
        limit = options.get("limit")
        cacher = CACHER_CLASSES[self.etype.lower()](self.logger)
        self.logger.info(f"[process_entities]: Use {str(cacher)} cacher")
        update_db = options.get("update-db")
        update_es = options.get("update-es")
        lasteid = options.get("fromeid")
        with admincnx(appid) as cnx:
            index_name = self.index_name(cnx, options)
            es_locations = self.es_locations(cnx, options)
            if self.schema == "published":
                set_published_schema(cnx)
                self.logger.info("[process_entities]: Set to search in published schema")
            if not lasteid and options.get("from-last-processed"):
                lasteid = "last"
                if update_es:
                    lasteid = get_last_indexed_eid(cnx, es_locations, index_name, self.etype)
                if update_db:
                    lasteid = get_last_updated_eid(cnx)
            nb_entities = cacher.get_entities_count(cnx, limit, lasteid)
            if nb_entities == 0:
                self.logger.warning(
                    "Abort: No entities has been found for %s, with lasteid %s and limit %r",
                    self.etype,
                    lasteid,
                    limit,
                )
                self.write_state(appid, options)
                sys.exit(1)
        chunksize = options.get("chunksize")
        nb_processes = options.get("nbprocesses")
        if nb_processes is None:
            nb_processes = max(mp.cpu_count() - 1, 1)
        if nb_processes > 1:
            self.logger.info("%s CPU availables, use %s processes\n", mp.cpu_count(), nb_processes)
        else:
            self.logger.info("%s CPU availables, use 1 process\n", mp.cpu_count())
        self.logger.info(
            f"[indexer]: Process {nb_entities} {self.schema} {self.etype} "
            f"with {nb_processes} processes "
        )
        debug = options.get("debug")
        if not nb_processes == 1:
            [
                do_process(
                    appid,
                    es_locations,
                    index_name,
                    self.schema,
                    cacher,
                    self.etype,
                    limit,
                    offset,
                    chunksize,
                    lasteid,
                    update_db,
                    update_es,
                    debug,
                    self.logger,
                )
                for offset in range(0, nb_entities, chunksize)
            ]
        else:
            pool = mp.Pool(nb_processes)
            pool.starmap(
                do_process,
                [
                    (
                        appid,
                        es_locations,
                        index_name,
                        self.schema,
                        cacher,
                        self.etype,
                        limit,
                        offset,
                        chunksize,
                        lasteid,
                        update_db,
                        update_es,
                        debug,
                        self.logger,
                    )
                    for offset in range(0, nb_entities, chunksize)
                ],
            )

    def write_state(self, appid, options):
        self.logger.info(f"[process] {self.etype}: Processing finished.")
        # check the last eid
        etypes = get_etypes_from_options(options)
        self.logger.info(
            f"--- Check ES indexing /Posgres updating states for {', '.join(etypes)} ---"
        )
        with admincnx(appid) as cnx:
            last_updated = get_last_updated_eid(cnx)
            self.logger.info(f"[update-db]: Last updated eid: {last_updated}")
            for etype in etypes:
                lasteid = cnx.execute(f"Any X ORDERBY X DESC LIMIT 1 WHERE X is {etype}")[0][0]
                self.logger.info(f"[postgres] Last existing eid for {etype}: {lasteid}")
            es_index_name = self.index_name(cnx, options)
            for etype in etypes:
                last_updated = get_last_indexed_eid(
                    cnx, self.es_locations(cnx, options), es_index_name, etype
                )
                self.logger.info(
                    f"[update-es]: Last indexed eid in '{es_index_name}' "
                    f"for {etype}: {last_updated}"
                )

    def process(self, appid, options):
        if options.get("check"):
            # write the state and quite
            self.write_state(appid, options)
            sys.exit(1)
        self.process_entities(appid, options)
        self.logger.info(f"[process] {self.etype}: Processing finished.")


def process_etype(appid, config, etype, logger):
    if etype not in ETYPES_ADAPTERS:
        logger.error(
            f"No ES adapter is available for {etype}. "
            f"ES adapters are available for: {', '.join(ETYPES_ADAPTERS)}"
        )
        return
    schema = config.get("schema")
    if config.get("update-es"):
        if not schema:
            logger.error("Abort: No postgreSQL schema provided (--schema option)")
            sys.exit()
        if schema not in ("published", "public"):
            logger.error('Abort: Schema name must be one of: "published", "public"')
            sys.exit()
    processor = ESProcessor(
        schema,
        etype,
        logger,
    )
    if config.get("rqllog"):
        from cubicweb import server

        server.set_debug("DBG_RQL")
    if config.get("sqllog"):
        from cubicweb import server

        server.set_debug("DBG_SQL")
    if config.get("profile"):
        proffile = "/tmp/esindex_{}.prof".format(etype.lower())
        logger.info("[profiling] Start indexing and profiling %s in %s", etype, proffile)
        import cProfile

        cProfile.runctx("run([processor], appid, config, logger)", globals(), locals(), proffile)
        logger.info("\n[profiling] check profile in %s with snakeviz" % proffile)
    else:
        logger.info("[profiling] Start indexing %s", etype)
        run([processor], appid, config, logger)


def run(processors, appid, options, logger):
    try:
        mp.cpu_count()
    except Exception as ex:
        logger.error(ex)
    for processor in processors:
        processor.process(appid, options)


def init_logger(options):
    # init logger
    logfile = options.get("logfile")
    logger = logging.getLogger("francearchives.esindex")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(logfile)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def get_etypes_from_options(options):
    etypes = options.get("etypes")
    if not isinstance(etypes, (list, tuple)):
        etypes = etypes.split(",")
    return etypes


@timed
def process_indexes(appid, options, logger):
    logger.info(f"Options -> {str(options)}")
    update_db = options.get("update-db")
    update_es = options.get("update-es")
    action = ""
    if not (update_db or update_es):
        logger.error(
            "Abort: nothing to do. Please, provide one of 'update-db' or 'update-es' options"
        )
        sys.exit()
    if update_es and update_db:
        logger.error("Abort: Please, choose only one of 'update-db' or 'update-es' options")
        sys.exit()
    if update_es:
        action = "update_es"
        schema = options.get("schema")
        if not schema:
            logger.error("Abort: No postgreSQL schema provided (--schema option)")
            sys.exit()
        if schema not in ("published", "public"):
            logger.error('Abort: Schema name must be one of: "published", "public"')
            sys.exit()
    if update_db:
        action = "update_db"
    etypes = get_etypes_from_options(options)
    if options.get("from-last-processed") and options.get("fromeid"):
        logger.error("Abort: both 'from-last-processed' and 'fromeid' options cannot be applied")
        sys.exit()
    if (options.get("from-last-processed") or options.get("fromeid")) and len(etypes) != 1:
        logger.error("Abort: 'from-last-processed' and 'fromeid' can only be applied for one etype")
        sys.exit()
    with admincnx(appid) as cnx:
        if update_db:
            logger.info(f"{action}: Build data from PostgreSQL")
        if update_es:
            es_locations = (
                options.get("elasticsearch-locations") or cnx.vreg.config["elasticsearch-locations"]
            )
            index_name = get_index_name(cnx, options, logger)
            logger.info(
                f"{action}: Index data from ESDocument into {index_name} ES index "
                f"with ES host f{es_locations}"
            )
            indexer = cnx.vreg["es"].select("indexer", cnx)
            es = get_es_connection(es_locations)
            if not es or not es.ping():
                logger.info(f"{action}: Abort: no elasticsearch configuration found")
                sys.exit()
            shards = options["shards"]
            replicas = options["replicas"]
            logger.info(
                f'{action}: Create ES index "{index_name}" if not exists with {shards} '
                f"shards and {replicas} replicas"
            )
            es_settings = {
                "settings": {
                    "number_of_shards": shards,
                    "number_of_replicas": replicas,
                },
            }
            indexer.create_index(index_name=index_name, custom_settings=es_settings)
        BaseSQLHelper(cnx, logger).create_sql_tables(update_db, update_es)
    for etype in etypes:
        process_etype(appid, options, etype, logger)


if __name__ == "__main__":
    parser = OptionParser("usage: %prog [options] <instanceid>")
    # required
    parser.add_option(
        "--schema",
        dest="schema",
        type="string",
        default="public",
        help="PostgreSQL schema value: 'public' or 'published'",
    )
    # required
    parser.add_option(
        "--index-name",
        type="string",
        dest="index-name",
        help="override index-name if you want to use a different ID"
        "[default: uses index-name from all-in-one.conf]",
    )
    parser.add_option(
        "--es-loc",
        type="string",
        dest="elasticsearch-locations",
        help="elasticsearch-locations"
        "[default: uses elasticsearch-locations from all-in-one.conf]",
    )
    parser.add_option(
        "--etypes",
        dest="etypes",
        default=list(ETYPES_ADAPTERS),
        help=("comma separated list of cwetypes to be exported: %s" % list(ETYPES_ADAPTERS)),
    ),
    parser.add_option(
        "--chunksize", dest="chunksize", type="int", default=10000, help="chunksize size"
    ),
    parser.add_option(
        "--shards",
        type="int",
        dest="shards",
        default=1,
        help="number of shard for index ES",
    ),
    parser.add_option(
        "--replicas",
        type="int",
        dest="replicas",
        default=1,
        help="number of replicas for index ES",
    ),
    parser.add_option("--fromeid", dest="fromeid", type="int", help="Eid to start indexing with")
    parser.add_option(
        "--from-last-processed",
        dest="from-last-processed",
        action="store_true",
        default=False,
        help="Start indexing from the last eid indexed in ES or Postgres",
    )
    parser.add_option(
        "--update-db",
        dest="update-db",
        action="store_true",
        default=False,
        help="Update PostgreSQL ESDocument",
    )

    parser.add_option(
        "--update-es",
        dest="update-es",
        action="store_true",
        default=False,
        help="Index data from ESDocument",
    )

    parser.add_option("--limit", dest="limit", type="int", help="max number of entities indexed")
    parser.add_option("--offset", dest="offset", default=0, type="int", help="Offset of entities")
    parser.add_option(
        "--nbprocesses",
        type="int",
        dest="nbprocesses",
        default=None,
        help="number of subprocesses to spawn to index ES",
    )
    parser.add_option(
        "--debug",
        dest="debug",
        action="store_true",
        default=False,
        help="Display logs for debug",
    )
    parser.add_option(
        "--logfile",
        dest="logfile",
        type="string",
        help="logfile",
        default="/tmp/eseindex.log",
    )
    parser.add_option(
        "--rqllog",
        dest="rqllog",
        action="store_true",
        default=False,
        help="write RQL queries on stdout",
    )
    parser.add_option(
        "--sqllog",
        dest="sqllog",
        action="store_true",
        default=False,
        help="write SQL queries on stdout",
    )
    parser.add_option(
        "--profile",
        dest="profile",
        action="store_true",
        default=False,
        help="use cProfile to monitor execution (dump in /tmp/esindex_<ETYPE>.prof)",
    )
    parser.add_option(
        "--check",
        dest="check",
        action="store_true",
        default=False,
        help="check indexing / updating state and abort",
    )

    (options, args) = parser.parse_args()
    if not args:
        parser.error("<instanceid> argument missing")
    appid = args[0]
    options = vars(options)
    logger = init_logger(options)
    process_indexes(appid, options, logger)
    # delete sql tables
    with admincnx(appid) as cnx:
        logger.info("Clean SQL tables")
        BaseSQLHelper(cnx).clean_sql_tables()
