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

import boto3
from collections import defaultdict, OrderedDict
from datetime import datetime
from itertools import chain
from jinja2 import Environment, PackageLoader
import logging
import multiprocessing as mp
from optparse import OptionParser
import os
import os.path
from psycopg2.errors import UndefinedTable
import tarfile
import time
import sys

from logilab.common.decorators import timed
from rdflib.graph import ConjunctiveGraph

from cubicweb.entity import Relation
from cubicweb.rset import ResultSet

from cubicweb_francearchives import admincnx
from cubicweb_francearchives.xy import add_statements_to_graph
from cubicweb_francearchives.storage import S3BfssStorageMixIn


AWS_S3_RDF_BUCKET_NAME = os.environ.get("AWS_S3_RDF_BUCKET_NAME")
if AWS_S3_RDF_BUCKET_NAME is None:
    AWS_S3_RDF_BUCKET_NAME = "rdf"

ETYPES_ADAPTERS = OrderedDict(
    {
        "Service": ("rdf",),
        "AuthorityRecord": ("rdf",),
        "AgentAuthority": ("rdf",),
        "LocationAuthority": ("rdf",),
        "SubjectAuthority": ("rdf",),
        "FAComponent": ("rdf",),
        "FindingAid": ("rdf",),
    }
)

AUTHORITY_ETYPES = ("LocationAuthority", "AgentAuthority", "SubjectAuthority")


def directory_from_graph_name(graph_name):
    return "UNQUALITY" if graph_name == "BASE" else graph_name


def _ecache_factory(rset, rows):
    return [rset.get_entity(rowidx, 1) for rowidx, row in rows]


def build_rset_from_sql(cnx, query, desc_info, emulated_rql):
    descr, rows = [], []
    rows = cnx.system_sql(query).fetchall()
    descr = (desc_info,) * len(rows)
    rset = ResultSet(rows, emulated_rql, description=descr)
    rset.req = cnx
    return rset


class FSRDFStorge:
    def __init__(self, output_dir, logger):
        self.output_dir = output_dir
        self.logger = logger
        self.storage = S3BfssStorageMixIn(bfss=True, log=self.logger)
        self.backuped_bucket_name = None

    def prepare_storage(self, options):
        if not os.path.exists(self.output_dir):
            self.logger.info(f"[fs_storage]: Create {self.output_dir}")
            os.makedirs(self.output_dir)
        self.logger.info(f"[fs_storage]: Rdf dumps will be stored in '{self.output_dir}'")

    def get_filepath(self, etype, offset, _format, graph_name, compressed=True):
        directory = directory_from_graph_name(graph_name)
        graph_dir_path = os.path.join(self.output_dir, directory)
        if not os.path.exists(graph_dir_path):
            self.logger.info(f"[fs_storage]: Create {graph_dir_path}")
            os.makedirs(graph_dir_path)
        if compressed:
            _format = "{}.gz".format(_format)
        filepath = "%s_%06d.%s" % (etype.lower(), offset, _format)
        filepath = os.path.join(graph_dir_path, filepath)
        self.logger.info(f"Start writing {filepath}")
        return filepath


class S3RDFStorge:
    def __init__(self, logger):
        if not AWS_S3_RDF_BUCKET_NAME:
            self.logger.error("[s3 storage]: No bucket name (AWS_S3_RDF_BUCKET_NAME) found")
            sys.exit()
        self.logger = logger
        self.s3_bucket = AWS_S3_RDF_BUCKET_NAME
        self.storage = S3BfssStorageMixIn(bucket_name=self.s3_bucket, log=self.logger)
        self._s3_resource = None
        self.backuped_bucket_name = None

    @property
    def s3_resource(self):
        if self._s3_resource is None:
            endpoint_url = os.environ.get("AWS_S3_ENDPOINT_URL")
            if endpoint_url:
                self.logger.debug(
                    "[s3_resource]: Using custom S3 endpoint url {}".format(endpoint_url)
                )
            self._s3_resource = boto3.resource("s3", endpoint_url=endpoint_url)
        return self._s3_resource

    def get_buckets_list(self):
        response = self.storage.s3.s3cnx.list_buckets()
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            if "Buckets" not in response:
                self.logger.error(
                    "[get_buckets_list]: No information about existing s3 buckets "
                    "could be retrieved"
                )
                sys.exit(1)
        return [obj["Name"] for obj in response["Buckets"]]

    def delete_bucket(self, bucket_name):
        self.logger.info(f'[delete_bucket]: Start deleting "{bucket_name}" bucket')
        bucket = self.s3_resource.Bucket(bucket_name)
        self.empty_bucket(bucket)
        bucket.delete()
        self.logger.info(f'-> [delete_bucket]: {bucket_name}" bucket is deleted')

    def empty_bucket(self, bucket):
        self.logger.info(f'[empty_bucket]: Start emptying "{bucket.name}" bucket')
        bucket.objects.delete()
        self.logger.info(f'-> [empty_bucket]: "{bucket.name}" bucket is empty')

    def rename_bucket(self, bucket_name, new_bucket_name=None):
        """Is there a simplier way to do this ?"""
        bucket = self.s3_resource.Bucket(bucket_name)
        date = bucket.creation_date.strftime("%Y%m%d%H%M")
        new_bucket_name = new_bucket_name or f"{bucket_name}-{date}"
        self.logger.info(f'[rename_bucket]: Rename "{bucket_name}" into "{new_bucket_name}"')
        if bucket_name not in self.get_buckets_list():
            self.logger.info(f'-> [rename_bucket]: "{bucket_name}" bucket doesn\'t exist.')
            return
        if new_bucket_name in self.get_buckets_list():
            self.logger.warning(
                f'-> [rename_bucket]: The new "{new_bucket_name}" bucket already exists, delete it'
            )
            self.delete_bucket(new_bucket_name)
            self.logger.info(
                f'-> [rename_bucket]: The new "{new_bucket_name}" bucket has been deleted'
            )
        self.logger.info(f'-> [rename_bucket]: Create the new "{new_bucket_name}"')
        self.storage.s3.s3cnx.create_bucket(Bucket=new_bucket_name)
        self.logger.info(
            f'-> [rename_bucket]: Copy "{bucket_name}" data in the the new "{new_bucket_name}"'
        )
        result = self.storage.s3.s3cnx.list_objects(Bucket=bucket_name)
        if "Contents" in result:
            for key in self.storage.s3.s3cnx.list_objects(Bucket=bucket_name)["Contents"]:
                key_name = key["Key"]
                self.storage.s3.s3cnx.copy_object(
                    Bucket=new_bucket_name, CopySource=f"{bucket_name}/{key_name}", Key=key_name
                )
                self.storage.s3.s3cnx.delete_object(Bucket=bucket_name, Key=key_name)
        # delete the old bucket
        self.logger.info(f'[rename_bucket]: Delete the empty old "{bucket_name}"')
        bucket.delete()
        return new_bucket_name

    def prepare_storage(self, options):
        self.storage = S3BfssStorageMixIn(bucket_name=self.s3_bucket, log=self.logger)
        if self.storage.s3_bucket in self.get_buckets_list():
            if options.get("s3db"):
                try:
                    self.delete_bucket(self.storage.s3_bucket)
                except Exception as ex:
                    self.logger.error(f"[s3 storage]: Abort: {ex}")
                    sys.exit(1)
            if options.get("s3rb"):
                self.backuped_bucket_name = self.rename_bucket(self.storage.s3_bucket)
        if self.storage.s3_bucket not in self.get_buckets_list():
            self.logger.info(f"[s3 storage]: Creating {self.storage.s3_bucket} bucket")
            self.storage.s3.s3cnx.create_bucket(Bucket=self.storage.s3_bucket)
        self.logger.info(f"[s3 storage]: Generating dumps in '{self.storage.s3_bucket}' bucket")

    def get_filepath(self, etype, offset, _format, graph_name, compressed=True):
        directory = directory_from_graph_name(graph_name)
        if compressed:
            _format = "{}.gz".format(_format)
        filepath = "%s/%s_%06d.%s" % (directory, etype.lower(), offset, _format)
        self.logger.info(f"Start writing {filepath} in '{self.storage.s3_bucket}' bucket")
        return filepath


class BaseSQLHelper:
    def __init__(self, cnx, logger, schema=None):
        self.cnx = cnx
        self.logger = logger
        self.schema = schema

    def check_table_exists(self, table_name):
        query = "SELECT * FROM {0} LIMIT 1".format(table_name)
        try:
            self.cnx.system_sql(query)
            self.logger.info(f"[sql]: SQL tables for {self.table_name} already exist")
            return True
        except UndefinedTable:
            self.logger.info(f"[sql]: SQL tables for {self.table_name} don't exist")
            return False

    def preprocess_sql_tables(self):
        pass

    def create_sql_tables(self, table_name=None, etype=None, generate_not_qualified=True):
        self.preprocess_sql_tables()
        if table_name is None:
            table_name = self.table_name
        if etype is None:
            etype = self.etype
        if not self.check_table_exists(table_name):
            self.logger.info(f"[sql]: Start generating SQL tables for {etype}")
            start = time.time()
            env = Environment(
                loader=PackageLoader("cubicweb_francearchives", "rdf/templates"),
            )
            env.filters["sqlstr"] = lambda x: "'{}'".format(x)  # noqa
            template = env.get_template("create_rdf_tables.sql")
            sqlcode = template.render(
                schema=self.schema,
                etype=etype.lower(),
                generate_not_qualified=generate_not_qualified,
            )
            self.logger.info(sqlcode)
            self.cnx.system_sql(sqlcode)
            end = time.time()
            self.logger.info(
                f"{time.ctime()}: Finished generating tables for {self.etype}: "
                f"Took {end - start} secs"
            )

    def clean_sql_tables(self):
        self.logger.info(f"[sql]: Start cleaning SQL tables for {self.etype}")
        env = Environment(
            loader=PackageLoader("cubicweb_francearchives", "rdf/templates"),
        )
        env.filters["sqlstr"] = lambda x: "'{}'".format(x)  # noqa
        template = env.get_template("drop_rdf_tables.sql")
        sqlcode = template.render(etype=self.etype.lower())
        self.cnx.system_sql(sqlcode)
        self.logger.info(f"[sql]: Finished cleaning SQL tables for {self.etype}")


class FAComponentSQLHelper(BaseSQLHelper):
    etype = "FAComponent"
    table_name = "tmp_facomponent_qualified"


class FindingAidSQLHelper(BaseSQLHelper):
    etype = "FindingAid"
    table_name = "tmp_findingaid_qualified"

    def preprocess_sql_tables(self):
        # check FaComponent table exists and create them if needed
        fa_helper = SQL_HELPERS["FAComponent"](self.cnx, self.logger, self.schema)
        fa_helper.create_sql_tables(generate_not_qualified=False)


class BaseRDFCacher:
    etype = None
    fetch_all_rql = None
    restriction_rql = None  # Use EXISTS in the restrictions to avoid multiple rows in rset

    def __init__(self, logger):
        self.logger = logger

    def __str__(self):
        return f"{self.etype}RDFCacher" if self.etype else "BaseRDFCacher"

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

    def build_rset(self, cnx, limit, offset):
        return cnx.execute(self.build_query() % (limit, offset), build_descr=True)

    def count_query(self):
        query = self.fetch_all_rql
        if query is None:
            raise NotImplementedError()
        _, restrictions = self.get_rql_selection_restriction()
        query = "Any COUNT(X) WHERE %s" % (restrictions)
        return query

    def get_entities_count(self, cnx):
        return cnx.execute(self.count_query())[0][0]

    def set_entity_cache(
        self, cnx, etype, entities, query, cachekey, cache_factory=_ecache_factory, empty_value=()
    ):
        set_entity_cache(
            cnx, etype, entities, query, cachekey, cache_factory, empty_value, self.restriction_rql
        )

    def setup_iteration_cache(self, cnx, rset):
        pass


class ArchivesRDFCacher(BaseRDFCacher):
    @property
    def count_query_sql(self):
        return "SELECT COUNT(eid) FROM %s" % self.table_name

    def get_entities_count(self, cnx):
        return cnx.system_sql(self.count_query_sql).fetchone()[0]

    def build_emulated_rql(self):
        query = self.fetch_all_rql
        if query is None:
            raise NotImplementedError()
        selection, restrictions = self.get_rql_selection_restriction()
        query = "%s ORDERBY X LIMIT %%s OFFSET %%s WHERE %s" % (
            selection,
            restrictions,
        )
        return query

    def build_query(self):
        raise NotImplementedError()

    def build_sql_query(self):
        raise NotImplementedError()

    def build_rset(self, cnx, limit, offset):
        raise NotImplementedError()

    def digitized_versions_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_illustration_url, _E.cw_url
        %s , cw_DigitizedVersion AS _E, cw_{etype} AS _X,
        digitized_versions_relation AS rel_digitized_versions0
        WHERE rel_digitized_versions0.eid_from=_X.cw_eid AND
              rel_digitized_versions0.eid_to=_E.cw_eid AND
              _X.cw_eid=_T0.C0
        """.format(
            etype=self.etype
        )
        rql_query = (
            "Any X, E, IU, U WHERE E is DigitizedVersion, E url U, "
            "E illustration_url IU, X digitized_versions E"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "DigitizedVersion", "String", "String"),
            rql_query,
            "digitized_versions",
        )

    def did_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_unittitle, _E.cw_unitid,
               _E.cw_startyear, _E.cw_stopyear, _E.cw_origination,
               _E.cw_physloc, _E.cw_physdesc
        %s, cw_Did AS _E, cw_{etype} AS _X
        WHERE _X.cw_did=_E.cw_eid AND _X.cw_eid=_T0.C0
        """.format(
            etype=self.etype
        )
        rql_query = (
            "Any X, E, T, U, S, P, O, PHL, PHD  WHERE X did E, E is Did, "
            "E unitid U, E unittitle T, E startyear S, E stopyear P, "
            "E origination O, E physloc PHL, E physdesc PHD"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "Did", "String", "String", "Int", "Int", "String", "String", "String"),
            rql_query,
            "did",
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
            "FROM (SELECT _T.eid AS C0 "
            "      FROM {table_name} AS _T "
            "      WHERE _T.eid>={min_eid} "
            "      ORDER BY 1 "
            "      LIMIT {limit}) AS _T0 "
        ).format(min_eid=min(entities), limit=len(entities), table_name=self.table_name)
        rset = build_rset_from_sql(cnx, sql_query % sql_with_being, descr_info, emulated_rql)
        related, no_relation_eids = _grouped_rset(entities, rset)
        for main_entity_eid, rows in related.items():
            entity = cnx.entity_from_eid(main_entity_eid)
            entity.__dict__[cachekey] = cache_factory(rset, rows)
        for main_entity_eid in no_relation_eids:
            entity = cnx.entity_from_eid(main_entity_eid)
            entity.__dict__[cachekey] = empty_value


class FindingAidRDFCacher(ArchivesRDFCacher):
    etype = "FindingAid"
    fetch_all_rql = (
        "Any X,B,C,D,E,F,G,H,I,J,K "
        "WHERE X is FindingAid,X name B,X eadid C, "
        "X accessrestrict D, "
        "X userestrict E, "
        "X acquisition_info F, "
        "X scopecontent G, "
        "X stable_id H, "
        "X fa_header I?, "
        "X service J?, "
        "X did K?"
    )
    table_name = "tmp_findingaid_not_qualified"

    def build_sql_query(self):
        return (
            "SELECT _F.eid, _X.cw_name, _X.cw_eadid, _X.cw_accessrestrict, "
            "_X.cw_userestrict, _X.cw_acquisition_info, _X.cw_scopecontent, "
            "_X.cw_stable_id, _X.cw_fa_header, _X.cw_service, _X.cw_did "
            "FROM {table_name} as _F, cw_FindingAid AS _X "
            "WHERE _F.eid=_X.cw_eid AND "
            "      _F.eid IN ( SELECT eid FROM {table_name} "
            "       ORDER BY eid LIMIT %s OFFSET %s) "
            "ORDER BY _F.eid".format(table_name=self.table_name)
        )

    def build_rset(self, cnx, limit, offset):
        descr_info = (
            self.etype,
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
        emulated_rql = self.build_emulated_rql() % (limit, offset)
        query = self.build_sql_query() % (limit, offset)
        return build_rset_from_sql(cnx, query, descr_info, emulated_rql)

    def service_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_code, _E.cw_name, _E.cw_name2, _E.cw_level
        %s, cw_FindingAid AS _X, cw_Service AS _E
        WHERE _X.cw_service=_E.cw_eid AND
              _X.cw_eid=_T0.C0"""
        rql_query = (
            "Any X, E, C, N, NM, L WHERE X service E, E is Service, E code C, "
            "E name N, E name2 NM, E level L"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "Service", "String", "String", "String", "String"),
            rql_query,
            "related_service",
            first_entity_factory,
        )

    def faheader_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_titleproper, _E.cw_lang_code
        %s, cw_FAHeader AS _E, cw_FindingAid AS _X
        WHERE _X.cw_fa_header=_E.cw_eid AND _X.cw_eid=_T0.C0"""
        rql_query = (
            "Any X, E, T, U WHERE X fa_header E, E is FAHeader, " "E lang_code U, E titleproper T"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "FAHeader", "String", "String"),
            rql_query,
            "fa_header",
        )

    def fa_top_components_cache(self, cnx, entities):
        sql_query = """
        SELECT _FC.cw_finding_aid, _FC.cw_eid, _FC.cw_stable_id
        %s, cw_FAComponent AS _FC
        WHERE _FC.cw_finding_aid=_T0.C0 AND _FC.cw_finding_aid IS NOT NULL AND
              NOT (EXISTS(SELECT 1 WHERE _FC.cw_parent_component IS NOT NULL))
        """
        rql_query = "Any X, FC, SI WHERE X top_components FC, FC stable_id SI"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FindingAid", "FAComponent", "String"),
            rql_query,
            "top_components",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            self.digitized_versions_cache(cnx, entities)
            self.did_cache(cnx, entities)
            self.faheader_cache(cnx, entities)
            self.service_cache(cnx, entities)
            self.fa_top_components_cache(cnx, entities)


class FindingAidQualityRDFCacher(FindingAidRDFCacher):
    restriction_rql = (
        "EXISTS(INDEX index X, INDEX authority AUTH, AUTH quality True)"
        "OR EXISTS (FC finding_aid X, FINDEX index FC, FINDEX authority FAUTH, FAUTH quality True)"
    )
    table_name = "tmp_findingaid_qualified"

    def __str__(self):
        return "FindingAidQualityRDFCacher"


class FAComponentRDFCacher(ArchivesRDFCacher):
    etype = "FAComponent"
    fetch_all_rql = (
        "Any X,A,B,C,D,E,F,G,H"
        "WHERE X is FAComponent, "
        "X accessrestrict A, "
        "X userestrict B, "
        "X acquisition_info C, "
        "X scopecontent D, "
        "X stable_id E, "
        "X did F?, "
        "X parent_component G?, "
        "X finding_aid H?"
    )
    table_name = "tmp_facomponent_not_qualified"

    def build_sql_query(self):
        return (
            "SELECT _F.eid, _X.cw_accessrestrict, _X.cw_userestrict, "
            "_X.cw_acquisition_info, _X.cw_scopecontent, _X.cw_stable_id, "
            "_X.cw_did, _X.cw_parent_component, _X.cw_finding_aid "
            "FROM {table_name} as _F, cw_FAComponent AS _X "
            "WHERE _F.eid=_X.cw_eid AND "
            "      _F.eid IN ( SELECT eid FROM {table_name} "
            "       ORDER BY eid LIMIT %s OFFSET %s) "
            "ORDER BY _F.eid".format(table_name=self.table_name)
        )

    def build_rset(self, cnx, limit, offset):
        descr_info = (
            self.etype,
            "String",
            "String",
            "String",
            "String",
            "String",
            "Did",
            "FAComponent",
            "FindingAid",
        )
        query = self.build_sql_query() % (limit, offset)
        emulated_rql = self.build_emulated_rql() % (limit, offset)
        return build_rset_from_sql(cnx, query, descr_info, emulated_rql)

    def service_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_code, _E.cw_name, _E.cw_name2, _E.cw_level
        %s, cw_FAComponent AS _X, cw_FindingAid AS _F, cw_Service AS _E
        WHERE _X.cw_finding_aid=_F.cw_eid AND _F.cw_service=_E.cw_eid AND _X.cw_eid=_T0.C0
        """
        rql_query = (
            "Any X, E, C WHERE X finding_aid F, F service E, E is Service, E code C, "
            "E name N, E name2 NM, E level L"
        )
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FAComponent", "Service", "String", "String", "String", "String"),
            rql_query,
            "related_service",
            first_entity_factory,
        )

    def findingaid_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_stable_id
        %s, cw_FAComponent AS _X, cw_FindingAid AS _E
        WHERE _X.cw_finding_aid=_E.cw_eid AND _X.cw_eid=_T0.C0
        """
        rql_query = "Any X, E, C WHERE  X finding_aid E, E stable_id C"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FAComponent", "FindingAid", "String"),
            rql_query,
            "finding_aid",
        )

    def parent_cache(self, cnx, entities):
        sql_query = """
        SELECT _X.cw_eid, _E.cw_eid, _E.cw_stable_id
        %s, cw_FAComponent AS _E, cw_FAComponent AS _X
        WHERE _X.cw_parent_component=_E.cw_eid AND _X.cw_eid=_T0.C0"""

        rql_query = "Any X, E, C WHERE X parent_component E, E stable_id C"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FAComponent", "FAComponent", "String"),
            rql_query,
            "parent_component",
        )

    def child_cache(self, cnx, entities):
        sql_query = """
        SELECT _FC.cw_parent_component, _FC.cw_eid, _FC.cw_stable_id
        %s, cw_FAComponent AS _FC
        WHERE _FC.cw_parent_component IS NOT NULL AND _FC.cw_parent_component=_T0.C0"""

        rql_query = "Any X, FC, SI WHERE FC parent_component X, FC stable_id SI"
        self.set_entity_cache_from_sql(
            cnx,
            self.etype,
            entities,
            sql_query,
            ("FAComponent", "FAComponent", "String"),
            rql_query,
            "reverse_parent_component",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            self.digitized_versions_cache(cnx, entities)
            self.did_cache(cnx, entities)
            self.service_cache(cnx, entities)
            self.findingaid_cache(cnx, entities)
            self.parent_cache(cnx, entities)
            self.child_cache(cnx, entities)


class FAComponentQualityRDFCacher(FAComponentRDFCacher):
    restriction_rql = "EXISTS(INDEX index X, INDEX authority AUTH, AUTH quality True)"
    table_name = "tmp_facomponent_qualified"

    def __str__(self):
        return "FAComponentQualityRDFCacher"


class AuthorityRecordRDFCacher(BaseRDFCacher):
    etype = "AuthorityRecord"
    fetch_all_rql = (
        "Any X,B,C,D,E,F,G WHERE X is AuthorityRecord, X record_id B, "
        "X isni C, X start_date D, X languages E, X end_date F, "
        "X agent_kind G? "
    )
    restriction_rql = "NOT EXISTS(AUTH same_as X, AUTH quality True)"

    def same_as_agent_cache(self, cnx, entities):
        self.set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, A, L, Q LIMIT 1 WHERE X is AuthorityRecord, "
            "A same_as X, A is AgentAuthority, A quality True, A quality Q, "
            "A label L",
            "qualified_authority",
        )

    def activity_cache(self, cnx, entities):
        self.set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, A, TYPE, START, END, AGENTTYPE, AGENT, DESC WHERE"
            "A is Activity, A generated X, X is AuthorityRecord, "
            "A type TYPE, A start START, A end END, A agent_type AGENTTYPE,"
            "A agent AGENT, A description DESC",
            "activities",
        )

    def sources_cache(self, cnx, entities):
        self.set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, S, T, U WHERE"
            "S is EACSource, S source_agent X, X is AuthorityRecord, "
            "S title T, S url U",
            "sources",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            self.same_as_agent_cache(cnx, entities)
            self.activity_cache(cnx, entities)
            self.sources_cache(cnx, entities)


class AuthorityRecordQualityRDFCacher(AuthorityRecordRDFCacher):
    restriction_rql = "EXISTS(AUTH same_as X, AUTH quality True)"

    def __str__(self):
        return "AuthorityRecordQualityRDFCacher"


class AuthorityRDFCacher(BaseRDFCacher):
    fetch_all_rql = None

    def same_as_external_cache(self, cnx, entities):
        self.set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, U WHERE X same_as E, E is ExternalUri, E uri U",
            "same_as",
        )

    def same_as_concept_cache(self, cnx, entities):
        self.set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, U WHERE X same_as E, E is Concept, E cwuri U",
            "same_as",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            query = """DISTINCT Any X, TYPE WHERE X is AgentAuthority,
                       I is AgentName, I authority X, I type TYPE"""
            _cache_index_types_info(cnx, "AgentAuthority", entities, query)
            self.same_as_external_cache(cnx, entities)


class AgentAuthorityRDFCacher(AuthorityRDFCacher):
    etype = "AgentAuthority"
    fetch_all_rql = "Any X,A,B WHERE X is AgentAuthority," "X quality A, X quality True, X label B "

    def same_as_agent_cache(self, cnx, entities):
        self.set_entity_cache(
            cnx,
            self.etype,
            entities,
            "Any X, E, R WHERE X same_as E, E is AuthorityRecord, E record_id R",
            "same_as",
        )

    def setup_iteration_cache(self, cnx, rset):
        entities = dict((e.eid, e) for e in rset.entities())
        if entities:
            query = """DISTINCT Any X, TYPE WHERE X is AgentAuthority,
                       I is AgentName, I authority X, I type TYPE"""
            _cache_index_types_info(cnx, "AgentAuthority", entities, query)
            self.same_as_external_cache(cnx, entities)
            self.same_as_agent_cache(cnx, entities)


class SubjectAuthorityRDFCacher(AuthorityRDFCacher):
    etype = "SubjectAuthority"
    fetch_all_rql = "Any X,A,B WHERE X is SubjectAuthority, X quality A, X quality True, X label B "


class LocationAuthorityRDFCacher(AuthorityRDFCacher):
    etype = "LocationAuthority"
    fetch_all_rql = (
        "Any X,A,B,C,D WHERE X is LocationAuthority, X quality A, "
        "X quality True, X label B, X longitude C, X latitude D"
    )


class ServiceRDFCacher(BaseRDFCacher):
    etype = "Service"
    fetch_all_rql = (
        "Any X,A,B,C,D,E,F,G,H,I,J,K,L,M,N,O WHERE "
        "X is Service, X name A, X name2 B, X short_name C, "
        "X phone_number D, X email E, X address F, "
        "X zip_code G, X city H, X website_url I, "
        "X opening_period J, X contact_name K, X level L, X code M, "
        "X longitude N, X latitude O"
    )
    restriction_rql = "NOT EXISTS(FA service X, FA is FindingAid)"


class ServiceQualityRDFCacher(ServiceRDFCacher):
    restriction_rql = "EXISTS(FA service X, FA is FindingAid)"

    def __str__(self):
        return "ServiceQualityRDFCacher"


CACHER_CLASSES = {
    "BASE": {
        "findingaid": FindingAidRDFCacher,
        "facomponent": FAComponentRDFCacher,
        "authorityrecord": AuthorityRecordRDFCacher,
        "service": ServiceRDFCacher,
    },
    "QUALITY": {
        "findingaid": FindingAidQualityRDFCacher,
        "facomponent": FAComponentQualityRDFCacher,
        "authorityrecord": AuthorityRecordQualityRDFCacher,
        "service": ServiceQualityRDFCacher,
    },
    "AUTHORITY": {
        "agentauthority": AgentAuthorityRDFCacher,
        "subjectauthority": SubjectAuthorityRDFCacher,
        "locationauthority": LocationAuthorityRDFCacher,
    },
}

SQL_HELPERS = {
    "FAComponent": FAComponentSQLHelper,
    "FindingAid": FindingAidSQLHelper,
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
    # For now, the orm relations are not rebound after the rdfdump
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
    assert len(rows) == 1, "service relations are not supposed to be multivalued"
    return rset.get_entity(rows[0][0], 1)


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


def iter_rdf_adapters(entity):
    for adapter_id in ETYPES_ADAPTERS.get(entity.__regid__):
        adapter = entity.cw_adapt_to(adapter_id)
        if adapter:
            yield adapter


def add_entity_to_graph(graph, entity, logger):
    rdf_adapters = [iter_rdf_adapters(entity)]
    for adapter in chain(*rdf_adapters):
        try:
            add_statements_to_graph(graph, adapter)
        except Exception as ex:
            logger.error("Error while generating rdf for %s: err %s" % (entity, ex))


def add_etype_to_graph(cnx, graph, etype, limit, offset, logger, cacher):
    rset = cacher.build_rset(cnx, limit, offset)
    logger.info(f"Write {rset.rowcount} {etype} (offset {offset})")
    cacher.setup_iteration_cache(cnx, rset)
    # Construct graph
    for entity in rset.entities():
        add_entity_to_graph(graph, entity, logger)
    logger.info(f"Remove cache of {rset.rowcount} {etype} (offset {offset})")
    cnx.drop_entity_cache()


def write_graph(
    appid,
    schema,
    s3,
    graph_name,
    cacher,
    output_dir,
    formats,
    etype,
    limit,
    offset,
    chunksize,
    compressed,
    logger,
):
    filenames = []
    with admincnx(appid) as cnx:
        if schema == "published":
            set_published_schema(cnx)
        if s3:
            st = S3RDFStorge(logger)
        else:
            st = FSRDFStorge(output_dir, logger)
        graph = ConjunctiveGraph()
        limit = limit if limit and limit < chunksize else chunksize
        add_etype_to_graph(cnx, graph, etype, limit, offset, logger, cacher)
        for _format in formats:
            filepath = st.get_filepath(etype, offset, _format, graph_name, compressed=compressed)
            st.storage.storage_write_file(
                filepath, graph.serialize(format=_format).encode("utf-8"), compressed=compressed
            )
            logger.info(f"Finished writing {filepath}")
            filenames.append(filepath)
            # clean as much as possible to avoid memory exhaustion
    return filenames


def set_published_schema(cnx):
    cnx.system_sql("SET search_path TO published, public;")


class RDFDumper:
    def __init__(self, schema, etype, formats, output_dir, logger, graph_name):
        self.etype = etype
        self.output_dir = output_dir
        self.formats = formats
        self.schema = schema
        self.logger = logger
        self.graph_name = graph_name

    def teardown_cache(self, cnx, rset=None):
        cnx.drop_entity_cache()

    @timed
    def dump_entities(self, appid, nb_processes, options):
        limit = options.get("limit")
        cacher = CACHER_CLASSES[self.graph_name][self.etype.lower()](self.logger)
        self.logger.info(f"[dump_entities]: Use {str(cacher)} cacher")
        with admincnx(appid) as cnx:
            if self.schema == "published":
                self.logger.info("[dump_entities]: Search in published schema")
                set_published_schema(cnx)
            if not limit:
                nb_entities = cacher.get_entities_count(cnx)
            else:
                nb_entities = int(limit)
        offset = options["offset"]
        self.logger.info(
            f"[dump_entities]: Process {nb_entities} {self.etype} from offset {offset} "
            f"with {nb_processes} processes"
        )
        pool = mp.Pool(nb_processes)
        s3storage = options.get("s3")
        chunksize = options.get("chunksize")
        filenames = []
        results = pool.starmap(
            write_graph,
            [
                (
                    appid,
                    self.schema,
                    s3storage,
                    self.graph_name,
                    cacher,
                    self.output_dir,
                    self.formats,
                    self.etype,
                    limit,
                    offset_,
                    chunksize,
                    options["c"],
                    self.logger,
                )
                for offset_ in range(offset, nb_entities, chunksize)
            ],
        )
        for res in results:
            filenames.extend(res)
        return filenames

    def dump(self, appid, nb_processes, options):
        filenames = self.dump_entities(appid, nb_processes, options)
        self.logger.info(
            f"[dump] {self.etype}: RDF generation finished. "
            f"{len(filenames)} files have been created."
        )
        if not options.get("s3"):
            # if options["c"] == True : RDF files are compressed. There is no use
            # to compress the archives
            self.fs_make_archive(filenames, compressed=not (options["c"]))

    def fs_make_archive(self, filenames, compressed=False):
        for _format in self.formats:
            directory = directory_from_graph_name(self.graph_name)
            ext = "tar.gz" if compressed else "tar"
            archive_name = f"{directory}_{self.etype.lower()}_{_format}.{ext}"
            archive_path = os.path.join(self.output_dir, archive_name)
            self.logger.info(f"[dump] {self.etype}: Write archives {archive_path}")
            _options = "w:gz" if compressed else "w"
            with tarfile.open(archive_path, _options) as tar:
                for filename in filenames:
                    # add file but specify basename as the alternative filename
                    # to avoid nested directory structure in the archive
                    tar.add(filename, arcname=os.path.basename(filename))
                    # os.remove(filename)


def create_dumps(appid, config, etype, output_dir, logger, graph_name):
    if etype not in ETYPES_ADAPTERS:
        logger.error(
            f"No RDF adapter is available for {etype}. "
            f"RDF adapters are available for: {', '.join(ETYPES_ADAPTERS)}"
        )
        return
    formats = config.get("formats")
    if not isinstance(formats, (list, tuple)):
        formats = formats.split(",")
    schema = "published" if config.get("published") else "public"
    dumper = RDFDumper(
        schema,
        etype,
        formats,
        output_dir,
        logger,
        graph_name,
    )

    if config.get("rqllog"):
        from cubicweb import server

        server.set_debug("DBG_RQL")
    if config.get("profile"):
        proffile = "/tmp/rdfdump_{}.prof".format(etype.lower())
        logger.info("[profiling] Start generating and profiling dump %s in %s", etype, proffile)
        import cProfile

        cProfile.runctx("run([dumper], appid, config, logger)", globals(), locals(), proffile)
        logger.info("\n[profiling] check profile in %s with snakeviz" % proffile)
    else:
        try:
            logger.info("Start generating %s dump for %s graph", etype, graph_name)
            run([dumper], appid, config, logger)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            logger.error("Failed to generate dump %s %s", etype, exc)
            raise Exception(exc)


def run(dumpers, appid, options, logger):
    try:
        mp.cpu_count()
    except Exception as ex:
        logger.error(ex)
    nb_processes = options.get("nbprocesses")
    if nb_processes is None:
        nb_processes = max(mp.cpu_count() - 1, 1)
    if nb_processes > 1:
        logger.info("%s CPU availables, use %s processes\n", mp.cpu_count(), nb_processes)
    else:
        logger.info("%s CPU availables, use 1 process\n", mp.cpu_count())
    for dumper in dumpers:
        dumper.dump(appid, nb_processes, options)


def init_sql_tables(appid, etype, schema, logger):
    if etype in SQL_HELPERS:
        with admincnx(appid) as cnx:
            helper = SQL_HELPERS[etype](cnx, logger, schema)
            helper.create_sql_tables()


def clean_sql_tables(appid, logger=None):
    """Remove all sql tables"""
    if not logger:
        logger = logging.getLogger("francearchives.rdfdump")
        logger.setLevel(logging.INFO)
    for helper in SQL_HELPERS.values():
        with admincnx(appid) as cnx:
            helper(cnx, logger=logger).clean_sql_tables()


def init_logger(options):
    # init logger
    logfile = options.get("logfile")
    logger = logging.getLogger("francearchives.rdfdump")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(logfile)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def rdfdumps(appid, options):
    if options.get("published"):
        os.environ["RDFDUMP_PUBLISHED"] = "1"
    logger = init_logger(options)
    if options.get("s3") or options.get("loads3"):
        if not AWS_S3_RDF_BUCKET_NAME:
            logger.error("[s3 storage]: No bucket name (AWS_S3_RDF_BUCKET_NAME) found")
            sys.exit()
    date = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join(options["output-dir"], date)
    if options.get("s3"):
        st = S3RDFStorge(logger=logger)
    else:
        st = FSRDFStorge(output_dir, logger=logger)
    st.prepare_storage(options)
    etypes = options.get("etypes")
    if not isinstance(etypes, (list, tuple)):
        etypes = etypes.split(",")
    graph = options.get("graph")
    if graph not in ("ALL", "BASE", "QUALITY"):
        logger.warning(
            f'[rdfdumps]: invalid graph option {graph} not in ("ALL", "BASE", "DEFAULT"), '
            'defaulting to "ALL"'
        )
        graph = "ALL"
    if options.get("dsql", True):
        clean_sql_tables(appid, logger)
    schema = "published" if options.get("published") else "public"
    for etype in etypes:
        if etype in SQL_HELPERS:
            init_sql_tables(appid, etype, schema, logger)

    try:
        for etype in etypes:
            if etype in AUTHORITY_ETYPES:
                create_dumps(appid, options, etype, output_dir, logger, "AUTHORITY")
            elif graph == "ALL":
                # export both
                create_dumps(appid, options, etype, output_dir, logger, "QUALITY")
                create_dumps(appid, options, etype, output_dir, logger, "BASE")
            else:
                create_dumps(appid, options, etype, output_dir, logger, graph)
    except Exception:
        if hasattr(st, "s3_bucket") and st.backuped_bucket_name:
            st.delete_bucket(st.s3_bucket)
            st.rename_bucket(st.backuped_bucket_name, st.s3_bucket)
            return
    # delete the backuped bucket
    if st.backuped_bucket_name:
        logger.info(f'[rdfdumps]: Start deleting the backuped bucket "{st.backuped_bucket_name}"')
        st.delete_bucket(st.backuped_bucket_name)
        logger.info(f'[rdfdumps]: The backuped bucket "{st.backuped_bucket_name}" is deleted')
    # load generated RDF files from FS to S3
    if options["loads3"]:
        load_data_on_s3(output_dir, options, logger)


@timed
def load_data_on_s3(output_dir, options, logger=None):
    """load generated RDF files from FS to S3"""
    if not logger:
        logger = logging.getLogger("francearchives.rdfdump")
        logger.setLevel(logging.INFO)
    if not os.path.exists(output_dir):
        logger.error(f"[rdfdumps]: No directory {output_dir} found")
        return
    if not AWS_S3_RDF_BUCKET_NAME:
        logger.error("[rdfdumps]: No bucket name (no AWS_S3_RDF_BUCKET_NAME found)")
        return
    st = S3RDFStorge(logger=logger)
    st.prepare_storage(options)
    logger.info(f"[rdfdumps]: Start uploading from {output_dir} to s3 {st.s3_bucket} bucket")
    for dirpath, dirnames, filenames in os.walk(output_dir):
        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            key = st.storage.s3.ensure_key(filepath.split(output_dir)[1])
            with open(filepath, "rb") as f:
                st.storage.s3_write_file(key, f.read())
    logger.info(f"[rdfdumps]: Finished uploading from {output_dir} to s3 {st.s3_bucket} bucket")
    # for now we do not remove FS data which will be removed une the pod is deleted
    if options["fsclean"]:
        logger.info(f'[rdfdumps]: Delete "{output_dir}" data')
        import shutil

        shutil.rmtree(output_dir)


if __name__ == "__main__":  # if used with cubicweb-ctl shell
    parser = OptionParser("usage: %prog [options] <instanceid>")
    parser.add_option(
        "--etypes",
        dest="etypes",
        default=list(ETYPES_ADAPTERS),
        help=("comma separated list of cwetypes to be exported: %s" % list(ETYPES_ADAPTERS)),
    ),
    parser.add_option(
        "--p",
        dest="published",
        action="store_true",
        default=True,
        help="execute on published schema",
    )

    parser.add_option(
        "--output-dir",
        dest="output-dir",
        type="string",
        default="/tmp/rdfdata",
        help=("directory where the rdf dumps are stored on the filesystem or " "S3 name bucket"),
    ),
    parser.add_option(
        "--formats",
        dest="formats",
        default=("nt",),
        help=(
            "comma separated list of formats you want to generate: 'nt', 'n3', 'xml' "
            "(default to nt)"
        ),
    ),
    parser.add_option(
        "--chunksize", dest="chunksize", type="int", default=2000, help="chunksize size"
    )
    parser.add_option("--limit", dest="limit", type="int", help="max number of entities generated")
    parser.add_option("--offset", dest="offset", default=0, type="int", help="Offset of entities")
    parser.add_option(
        "--s3",
        dest="s3",
        action="store_true",
        default=False,
        help="store in s3 from AWS_S3_RDF_BUCKET_NAME",
    )
    parser.add_option(
        "--s3db",
        dest="s3db",
        action="store_true",
        default=False,
        help="delete existing s3 AWS_S3_RDF_BUCKET_NAME bucket",
    )
    parser.add_option(
        "--s3rb",
        dest="s3rb",
        action="store_true",
        default=False,
        help="rename existing s3 AWS_S3_RDF_BUCKET_NAME bucket",
    )
    parser.add_option(
        "--loads3",
        dest="loads3",
        action="store_true",
        default=True,
        help="load fs-generated RDF files on s3",
    )
    parser.add_option(
        "--fsclean",
        dest="loads3",
        action="store_true",
        default=False,
        help="remove generated FS data",
    )
    parser.add_option(
        "--dsql",
        dest="dsql",
        action="store_true",
        default=True,
        help="drop existing SQL tables",
    )
    parser.add_option(
        "--c",
        dest="c",
        action="store_true",
        default=True,
        help="compress RDF files (do not compress archives)",
    )
    parser.add_option(
        "--nbprocesses",
        type="int",
        dest="nbprocesses",
        default=None,
        help="number of subprocesses to spawn to generate RDF dumps",
    )
    parser.add_option(
        "--logfile",
        dest="logfile",
        type="string",
        help="rdfdump logfile",
        default="/tmp/rdfdump.log",
    )
    parser.add_option(
        "--rqllog",
        dest="rqllog",
        action="store_true",
        default=False,
        help="dump rql queries on stdout",
    )
    parser.add_option(
        "--profile",
        dest="profile",
        action="store_true",
        default=False,
        help="use cProfile to monitor execution (dump in /tmp/rdfdump.prof)",
    )
    parser.add_option(
        "--graph",
        type="string",
        dest="graph",
        default="ALL",
        help="graph to recreate (BASE : all the data, QUALITY: "
        "qualified data for sparnatural, ALL: both graphs)",
    )
    (options, args) = parser.parse_args()
    if not args:
        parser.error("<instanceid> argument missing")
    appid = args[0]
    options = vars(options)
    rdfdumps(appid, options)
    clean_sql_tables(appid)
