# flake8: noqa
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

"""migration helpers"""

from elasticsearch import helpers as es_helpers
from cubicweb_elasticsearch.es import get_connection

from cubicweb_francearchives.utils import table_exists
from cubicweb_francearchives.dataimport import es_bulk_index


def add_column_to_published_table(cnx, table, column, attrtype):
    cnx.system_sql(
        str("ALTER TABLE published.cw_%s ADD  IF NOT EXISTS cw_%s %s" % (table, column, attrtype)),
        rollback_on_failure=False,
    )


def drop_column_from_published_table(cnx, table, column):
    cnx.system_sql(
        str("ALTER TABLE published.cw_%s DROP COLUMN IF EXISTS cw_%s" % (table, column)),
        rollback_on_failure=False,
    )


def rename_column_in_published_table(cnx, table, old_attr, new_attr):
    cnx.system_sql(
        str(
            "ALTER TABLE published.cw_%s RENAME COLUMN cw_%s TO cw_%s" % (table, old_attr, new_attr)
        ),
        rollback_on_failure=False,
    )


def update_etypes_in_published_schema(
    sql, etypes=None, rtypes=(), user=None, sqlschema="published", dumpfiles=None, verbose=True
):
    """Add or update etype related table in schema (named "published" by default) in
    which we find filtered copied of CMS entities postgresql tables
    (and the required relations) that are in the
    wfs_cmsobject_published WF state.

    This schema can be used by the "read-only" application (using the
    "db-namespace" config option).
    """
    # create tables which does not exist in the dedicated namespace (schema) for entities that have
    # a publication workflow and their relations
    # XXX use jinja2 instead
    create_tables = []
    for etype in etypes:
        tablename = "cw_" + etype.lower()
        if table_exists(sql, tablename, sqlschema):
            continue
        create_tables.append(
            "create table if not exists {schema}.{table} as "
            "  select * from {table} where null;".format(table=tablename, schema=sqlschema)
        )
        create_tables.append(
            "alter table {schema}.{table} "
            "  add primary key (cw_eid);".format(table="cw_" + etype.lower(), schema=sqlschema)
        )

    # XXX should we introspect the cw schema to get these rtypes?
    indexes = []
    for rtype in rtypes:
        tablename = rtype + "_relation"
        if table_exists(sql, tablename, sqlschema):
            continue
        create_tables.append(
            "create table if not exists {schema}.{table} as "
            "  select * from {table} where null;".format(table=tablename, schema=sqlschema)
        )
        create_tables.append(
            "alter table {schema}.{table} "
            "  add primary key (eid_from, eid_to);".format(
                table=rtype + "_relation", schema=sqlschema
            )
        )
        # create indexes on those relation tables
        for col in ("eid_from", "eid_to"):
            indexes.append(
                "create index {rtype}_{col}_idx on "
                "{schema}.{rtype}_relation({col});".format(
                    schema=sqlschema,
                    rtype=rtype,
                    col=col,
                )
            )
    template = """
{schema_creation}

{create_tables}

{indexes}
"""
    sqlcode = template.format(
        schema_creation="",
        create_tables="\n".join(create_tables),
        indexes="\n".join(indexes),
    )
    if dumpfiles:
        with open(osp.join(dumpfiles, "setup.sql"), "w") as fobj:
            fobj.write(sqlcode)
    if not sqlcode.strip():
        print("-> no sqlcode to execute")
        return
    if sql:
        if verbose:
            print(sqlcode)
        sql(sqlcode)


def delete_from_es_by_etype(cnx, cw_etype, log=True):
    def docs_to_delete(es, index_name):
        print("-> deleting from {}".format(index_name))
        for doc in es_helpers.scan(
            es,
            index=index_name,
            docvalue_fields=(),
            query={"query": {"match": {"cw_etype": cw_etype}}},
        ):
            if log:
                print("  delete {}".format(doc["_source"]["eid"]))
            yield {
                "_op_type": "delete",
                "_index": index_name,
                "_id": doc["_id"],
            }

    cms_index_name = cnx.vreg.config["index-name"]
    public_index_name = cnx.vreg.config["published-index-name"]
    for index_name in (cms_index_name, public_index_name):
        es = get_connection(cnx.vreg.config)
        if not es or not es.ping():
            print("-> no es connection found: abort deletion")
            return
        es_docs = docs_to_delete(es, index_name + "_all")
        es_bulk_index(es, es_docs, raise_on_error=False)


def get_foreign_constraint_names(sql, tablename, schema):
    cu = sql(
        """
        SELECT
            tc.constraint_name
        FROM
            information_schema.table_constraints AS tc
        WHERE tc.constraint_type = 'FOREIGN KEY'
            AND tc.table_schema = %(s)s
            AND tc.table_name= %(t)s""",
        {"t": tablename, "s": schema},
    )
    res = cu.fetchall()
    if res:
        return [name for name, in res]
    return []


def set_foreign_constraints_defferrable(cnx, tables, schema, logger=None):
    """make foreign contraints defferable for tables"""
    sql = cnx.system_sql
    for f_table in tables:
        if logger:
            logger.info(f"\n set DEFERRABLE INITIALLY IMMEDIATE on `{f_table}` foreign_constraints")
        f_constraintes = get_foreign_constraint_names(sql, f_table, schema)
        if f_constraintes:
            for f_name_constraint in f_constraintes:
                if logger:
                    logger.info(f"update {f_name_constraint}")
                sql(
                    f"""ALTER TABLE {f_table} ALTER CONSTRAINT {f_name_constraint} DEFERRABLE INITIALLY IMMEDIATE"""
                )
            cnx.commit()


def set_foreign_constraints_no_defferrable(cnx, tables, schema, logger=None):
    """make foreign contraints defferable for tables"""
    sql = cnx.system_sql
    for f_table in tables:
        if logger:
            logger.info(f"\n set NO DEFERRABLE on `{f_table}` foreign_constraints")
        f_constraintes = get_foreign_constraint_names(sql, f_table, schema)
        if f_constraintes:
            for f_name_constraint in f_constraintes:
                if logger:
                    logger.info(f"update {f_name_constraint}")
                sql(f"""ALTER TABLE {f_table} ALTER CONSTRAINT {f_name_constraint} NO DEFERRABLE""")
            cnx.commit()
