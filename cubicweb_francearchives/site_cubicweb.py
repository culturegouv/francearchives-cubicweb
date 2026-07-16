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
import json

from logilab.common.configuration import REQUIRED
from logilab.database import FunctionDescr, get_db_helper, AggrFunctionDescr
from logilab.database.sqlgen import SQLExpression

from rql.utils import register_function

from yams import register_base_type


options = (
    (
        "contact-email",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "FranceArchive portal email used in the contact form.",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "contact-adocs-email",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "@Docs site email used in the contact form.",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "contact-simplead-email",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "SimplEAD site email used in the contact form.",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "sitemap-dir",
        {
            "type": "string",
            "default": "/tmp",
            "help": "directory where gen-sitemap will output sitemap files",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "appfiles-dir",
        {
            "type": "string",
            "default": "/tmp",
            "help": "directory where BFSS will store application files",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "ead-services-dir",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "directory containing findinaid  original files",
            "group": "ir",
            "level": 2,
        },
    ),
    (
        "eac-services-dir",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "directory containing eac original files",
            "group": "eac",
            "level": 2,
        },
    ),
    (
        "nomina-services-dir",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "directory containing nomina harvested/imported files",
            "group": "nomina",
            "level": 2,
        },
    ),
    (
        "nomina-index-name",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "name of the elasticsearch index for nomina data",
            "group": "nomina",
            "level": 2,
        },
    ),
    (
        "agents-reference-index-name",
        {
            "type": "string",
            "default": REQUIRED,
            "help": "name of the elasticsearch index for agents reference data",
            "group": "agents",
            "level": 2,
        },
    ),
    (
        "newsletter-cypher-seed",
        {
            "type": "string",
            "default": "this is a newsletter cypher seed",
            "help": "seed used to cypher newsletter email in confirmation email link",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "consultation-base-url",
        {
            "type": "string",
            "default": "https://francearchives.gouv.fr",
            "help": "public base url to make link between synchronized entity",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "nginx-configs",
        {
            "type": "string",
            "default": "/tmp",
            "help": "directory where nginx redirection files are stored",
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "instance-type",
        {
            "type": "string",
            "default": REQUIRED,
            "help": 'Type of the instance: "cms" or "consultation"',
            "group": "pnia",
            "level": 2,
        },
    ),
    (
        "enable-kibana-indexes",
        {
            "type": "yn",
            "default": "yes",
            "help": "defines if kibana indexes are used",
            "group": "elasticsearch",
            "level": 2,
        },
    ),
    (
        "kibana-ir-index-name",
        {
            "type": "string",
            "default": "document_siaf",
            "help": "Name of kibana FindingAid / FAComponents Elastic Search index",
            "group": "elasticsearch",
            "level": 2,
        },
    ),
    (
        "kibana-authorities-index-name",
        {
            "type": "string",
            "default": "authority_siaf",
            "help": (
                "Name of kibana AgentAuthority, LocationAuthority, "
                "SubjectAuthority Elastic Search index"
            ),
            "group": "elasticsearch",
            "level": 2,
        },
    ),
    (
        "kibana-services-index-name",
        {
            "type": "string",
            "default": "service_siaf",
            "help": "Name of kibana Services Elastic Search index",
            "group": "elasticsearch",
            "level": 2,
        },
    ),
    (
        "sparql_endpoint",
        {
            "type": "string",
            "default": "",
            "help": "Sparql endpoint",
            "group": "Sparql",
            "level": 2,
        },
    ),
    (
        "sparnatural_graph",
        {
            "type": "string",
            "default": "urn:francearchives:graph:sparnatural",
            "help": "Sparnatural data named graph",
            "group": "Sparql",
            "level": 2,
        },
    ),
    (
        "eulerian_domain",
        {
            "type": "string",
            "default": "",
            "help": "Tracking domain for Eulerian",
            "group": "Eulerian",
            "level": 2,
        },
    ),
    (
        "tac_uuid",
        {
            "type": "string",
            "default": "",
            "help": "uuid tarteaucitron uuid",
            "group": "tarteaucitron",
            "level": 2,
        },
    ),
    (
        "tac_domain",
        {
            "type": "string",
            "default": "",
            "help": "tarteaucitron domain",
            "group": "tarteaucitron",
            "level": 2,
        },
    ),
)


class NORMALIZE_ENTRY(FunctionDescr):
    minargs = maxargs = 1
    rtype = "String"
    supported_backends = ("postgres", "sqlite")

    def as_sql_sqlite(self, args):
        # normalize_entry is a noop for sqlite
        return ", ".join(args)


register_function(NORMALIZE_ENTRY)


class TRANSLATE_ENTITY(FunctionDescr):
    minargs = maxargs = 4
    rtype = "String"
    supported_backends = ("postgres", "sqlite")

    def as_sql_sqlite(self, args):
        # translate_entity is a noop for sqlite
        return ", ".join(args)


register_function(TRANSLATE_ENTITY)


#
# Json type
#


class JSON_AGG(AggrFunctionDescr):
    supported_backends = ("postgres",)


register_function(JSON_AGG)


def convert_json(x):
    if isinstance(x, SQLExpression):
        return x
    elif isinstance(x, str):
        try:
            json.loads(x)
        except (ValueError, TypeError):
            raise ValueError("Invalid JSON value: {0}".format(x))
        return SQLExpression("%(json_obj)s::json", json_obj=x)
    return SQLExpression("%(json_obj)s::json", json_obj=json.dumps(x))


# Register the new type
register_base_type("Json")

# Map the new type with PostgreSQL
pghelper = get_db_helper("postgres")
pghelper.TYPE_MAPPING["Json"] = "json"
pghelper.TYPE_CONVERTERS["Json"] = convert_json

# Map the new type with SQLite3
sqlitehelper = get_db_helper("sqlite")
sqlitehelper.TYPE_MAPPING["Json"] = "text"
sqlitehelper.TYPE_CONVERTERS["Json"] = json.dumps
