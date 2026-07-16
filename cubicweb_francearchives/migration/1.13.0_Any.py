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
#
from cubicweb_francearchives.migration import migr_113
from cubicweb_francearchives.dataimport import sqlutil
from cubicweb_francearchives.dataimport.ead import ead_foreign_key_tables

add_relation_type("externref_image")


def alter_published_table(table, column, attrtype):
    cnx.system_sql(
        str("ALTER TABLE published.cw_%s ADD cw_%s %s" % (table, column, attrtype)),
        rollback_on_failure=False,
    )


with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
    foreign_key_tables = ead_foreign_key_tables(cnx.vreg.schema)
    sqlutil.disable_triggers(su_cnx, foreign_key_tables)
    # remove default value for FAComponent.additional_resources_format
    # to avoid excuting the "UPDATE cw_facomponent SET cw_a...='text/html' that
    # takes ages
    adr_fmt_rdef = fsschema.relation_schema_for("additional_resources_format").relation_definition(
        "FAComponent", "String"
    )
    adr_fmt_rdef.default = None
    for etype, attrs in (
        ("FindingAid", ("accessrestrict", "userestrict", "additional_resources")),
        ("FAComponent", ("additional_resources",)),
    ):
        for attr in attrs:
            print("add attr %s" % attr)
            attr_fmt = "{}_format".format(attr)
            add_attribute(etype, attr)
            add_attribute(etype, attr_fmt)
            alter_published_table(etype, attr, "text")
            alter_published_table(etype, attr_fmt, "character varying(50)")
    # reset correct default value in cw_cwattribute for FAComponent.additional_resources_format
    cnx.system_sql(
        "UPDATE cw_cwattribute as a "
        "SET cw_defaultval=a2.cw_defaultval "
        "FROM cw_cwrtype r, cw_cwetype e, "
        "     cw_cwattribute a2 JOIN cw_cwrtype r2 ON (r2.cw_eid=a2.cw_relation_type) "
        "   JOIN cw_cwetype e2 ON (a2.cw_from_entity=e2.cw_eid) "
        "WHERE a.cw_relation_type=r.cw_eid AND a.cw_from_entity=e.cw_eid "
        "   AND e.cw_name='FAComponent' AND r.cw_name='additional_resources_format'"
        "   AND r2.cw_name='additional_resources_format' AND e2.cw_name='FindingAid'"
    )
    cnx.commit()
    sqlutil.enable_triggers(su_cnx, foreign_key_tables)

print("add description on the url")

# add description on search_form_url
#  sync_schema_props_perms('search_form_url')


if __name__ == "__main__":
    if confirm("fix Service.search_form_url? [Y/n]"):
        migr_113.fix_search_form_url(cnx)
