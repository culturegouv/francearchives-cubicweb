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
sql(
    """
CREATE OR REPLACE FUNCTION update_index_entries(index_entries json, oldauth int, newauth int)
RETURNS jsonb as $$
DECLARE
  result jsonb;
BEGIN
  SELECT
    json_agg(
      json_build_object(
        'authority', CASE tmp.authority WHEN oldauth THEN newauth ELSE tmp.authority END,
        'label', tmp.label,
        'role', tmp.role,
        'normalized', tmp.normalized,
        'type', tmp.type
      )
    )
    INTO result
  FROM
    json_to_recordset(index_entries) as tmp(authority int, label text, role text, normalized text, authfilenumber text, type text);
  RETURN result;
END;
$$ language plpgsql;
"""
)
commit()

add_attribute("ExternalUri", "extid")
add_attribute("ExternalUri", "source")
add_attribute("ExternalUri", "label")

sql("DROP TABLE IF EXISTS authority_history")
sql(
    "CREATE TABLE authority_history ( "
    "  fa_stable_id varchar(64),"
    "  type varchar(20),"
    "  indexrole varchar(2048),"
    "  label varchar(2048),"
    "  autheid int,"
    "  UNIQUE (fa_stable_id, type, label, indexrole)"
    ")"
)
commit()

# related to #62520518
add_attribute("Service", "thumbnail_url")
query = "SET S thumbnail_url %(url)s WHERE S is Service, S code %(code)s"
thumbnail_urls = [
    {
        "url": "https://www.archives05.fr/cgi-bin/iipsrv.fcgi?FIF=/home/httpd/ad05/diffusion/prod/app/webroot/data/files/ad05.diffusion/images/{url}&HEI=180&QLT=80&CVT=JPG",
        "code": "FRAD005",
    },
    {
        "url": "http://hatch.vtech.fr/cgi-bin/iipsrv.fcgi?FIF=/home/httpd/ad95/data/files/images/{url}&HEI=375&QLT=80&CVT=JPG&SIZE=3598345",
        "code": "FRAD095",
    },
    {
        "url": (
            "http://recherche-archives.vendee.fr/data/files/ad85.diffusion/vignettes_archives/{url}"
        ),
        "code": "FRAD085",
    },
    {
        "url": "http://cd84-import.s3.amazonaws.com/prepared_images/thumb/destination/{url}",
        "code": "FRAD084",
    },
]
with cnx.deny_all_hooks_but():
    for thumbnail_url in thumbnail_urls:
        rql(query, thumbnail_url)


add_relation_type("grouped_with")


# regenerate published.related_finding_aid_relation function
# to update published.index_relation for FAComponents


from cubicweb_frarchives_edition.mviews import (
    setup_published_triggers,
    formatted_ignored_cwproperties,
)

from jinja2 import Environment, PackageLoader


def get_published_tables(cnx, skipped_etypes=(), skipped_relations=()):
    etypes = ["FindingAid"]
    rtypes = {}
    rnames = set()
    skipped_relations = ("in_state",)  # in_state is handled separately
    for etype in etypes:
        if etype in skipped_etypes:
            continue
        eschema = cnx.repo.schema[etype]
        rtypes[etype] = {}
        for rschema, targetschemas, role in eschema.relation_definitions():
            # r.rule is not None for computed relations
            if (
                rschema.final
                or rschema.inlined
                or rschema.meta
                or rschema.rule is not None
                or rschema.type in skipped_relations
            ):
                continue
            rtypes[etype].setdefault(rschema.type, []).append(role)
            rnames.add(rschema.type)
    return etypes, rtypes, rnames


def setup_published_triggers(cnx, sql=None, sqlschema="published", bootstrap=True):
    """Create (or replace) SQL triggers to handle filtered copied of CMS
    entities postgresql tables (and the resuired relations) that are
    in the wfs_cmsobject_published WF state.
    """
    if sql is None:
        sql = cnx.system_sql
    skipped_etypes = ("CWProperty", "CWUser")  # idem
    skipped_relations = ("in_state",)  # in_state is handled separately
    etypes, rtypes, rnames = get_published_tables(cnx, skipped_etypes, skipped_relations)
    env = Environment(
        loader=PackageLoader("cubicweb_frarchives_edition", "templates"),
    )
    env.filters["sqlstr"] = lambda x: "'{}'".format(x)
    template = env.get_template("published.sql")
    sqlcode = template.render(
        schema=sqlschema,
        etypes=etypes,
        rtypes=rtypes,
        rnames=rnames,
        ignored_cwproperties=formatted_ignored_cwproperties(cnx),
    )
    if sql:
        print(sqlcode)
        sql(sqlcode)


setup_published_triggers(cnx)
cnx.commit()
