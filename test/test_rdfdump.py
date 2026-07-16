# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2023
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
import logging
import unittest

from cubicweb_web.devtools.testlib import WebCWTC, WebPostgresApptestConfiguration
from rdflib import Graph, Namespace
from jinja2 import Environment, FileSystemLoader

from rdflib.compare import graph_diff

from cubicweb.devtools import BASE_URL
from cubicweb_francearchives.rdf.rdfdump import (
    CACHER_CLASSES,
    add_etype_to_graph,
    SQL_HELPERS,
)

from cubicweb_eac import testutils as eac_testutils

from pgfixtures import setup_module, teardown_module  # noqa

LOGGER = logging.getLogger("testing.francearchives.rdfdump")
# LOGGER.setLevel(logging.INFO)

TESTING = Namespace(BASE_URL)
RICO = Namespace("https://www.ica.org/standards/RiC/ontology#")

env = Environment(
    loader=FileSystemLoader("test/data/rdf"),
)


# Because of the _unbind_orm_relation, no other test can be executed after
# test_rdfdump, same attributes/relations of the entities are unbound and
# therefore unaccessible


class RDFDumpTC(WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def create_findingaid(self, cnx, service, stable_id, **kwargs):
        return cnx.create_entity(
            "FindingAid",
            name=stable_id,
            stable_id=stable_id,
            eadid="FRAD084_xxx",
            did=cnx.create_entity(
                "Did", unitid="maindid", unittitle="maindid-title", physdesc="un beau rouleau"
            ),
            publisher="FRAD084",
            fa_header=cnx.create_entity("FAHeader"),
            service=service,
            **kwargs,
        )

    def create_facomponent(self, cnx, finding_aid, stable_id, **kwargs):
        return cnx.create_entity(
            "FAComponent",
            finding_aid=finding_aid,
            stable_id=stable_id,
            did=cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
            ),
            scopecontent="<div>fc-scoppecontent</div>",
            description="<div>fc-descr</div>",
            **kwargs,
        )

    def add_all_etypes_to_graph(self, cnx, graph, graph_name):
        for etype in CACHER_CLASSES[graph_name].keys():
            cacher = CACHER_CLASSES[graph_name][etype](LOGGER)
            add_etype_to_graph(
                cnx,
                graph,
                etype,
                100,
                0,
                LOGGER,
                cacher,
            )

    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            """
            In the data, description expected in B: base only (non quality), Q: quality:
            - B FindingAid: FA-unqualified
            - Q FindingAid: FA-qualified -index- quality_auth
            - Q FindingAid: FA-child-qualified
              |_B parent-facomponent
              | |_Q qualified-facomponent -index- quality_auth
              |_B unqualified-facomponent -index- unqualified_auth

            - Q AuthorityRecord: QUALIFIED_AR -reverse_same_as- quality_auth_agent
            - B AuthorityRecord: UNQUALIFIED_AR

            - Q Service: FRAD084
            - B Service: FRAD082
            """
            service = cnx.create_entity(
                "Service", code="FRAD084", category="foo", name="Archives dep"
            )
            not_partner_service = cnx.create_entity(
                "Service", code="FRAD082", category="foo", name="Archives nulles"
            )

            ir = self.create_findingaid(cnx, service, stable_id="FA-child-qualified")
            facomp_parent = self.create_facomponent(cnx, ir, "parent-facomponent")
            facomp_qual = self.create_facomponent(
                cnx, ir, "qualified-facomponent", parent_component=facomp_parent
            )
            facomp_unqual = self.create_facomponent(cnx, ir, "unqualified-facomponent")
            quality_authority_record = eac_testutils.authority_record(
                cnx, "QUALIFIED_AR", "Toto", xml_support="foo"
            )
            eac_testutils.authority_record(cnx, "UNQUALIFIED_AR", "Titi", xml_support="foo")

            unqualified_auth = cnx.create_entity("SubjectAuthority", label="Jean Valjean")
            quality_auth = cnx.create_entity("SubjectAuthority", label="Loutre", quality=True)
            quality_agent_auth = cnx.create_entity(
                "AgentAuthority",
                label="Jeanne Poulet",
                quality=True,
                same_as=quality_authority_record,
            )
            cnx.create_entity(
                "Subject",
                label="loutre",
                authority=quality_auth,
                index=facomp_qual,
                type="occupation",
            )
            cnx.create_entity(
                "Subject",
                label="loutre",
                authority=unqualified_auth,
                index=facomp_unqual,
                type="function",
            )
            ir_unqualified = self.create_findingaid(cnx, service, stable_id="FA-unqualified")
            ir_qualified = self.create_findingaid(cnx, service, stable_id="FA-qualified")
            cnx.create_entity(
                "Subject",
                label="loutre",
                authority=quality_auth,
                index=ir_qualified,
                type="index",
            )
            cnx.commit()
            for etype in SQL_HELPERS:
                helper = SQL_HELPERS[etype](cnx, LOGGER)
                helper.create_sql_tables()
            cnx.commit()
        self.service_eid = service.eid
        self.not_partner_service_eid = not_partner_service.eid
        self.qualified_auth_eid = quality_auth.eid
        self.unqualified_auth_eid = unqualified_auth.eid
        self.qualified_agent_auth_eid = quality_agent_auth.eid
        self.ir_unqualified = ir_unqualified.eid
        self.ir_qualified = ir_qualified.eid
        self.ir_child_qualified = ir.eid
        self.fa_unqualified = facomp_unqual.eid
        self.fa_qualified = facomp_qual.eid
        self.fa_parent_of_fa_qualified = facomp_parent.eid

    def assertGraphEqual(self, graph1, graph2):
        common, tested_only, target_only = graph_diff(graph1, graph2)
        print("---------EXPECTED-ONLY--------")
        print(target_only.serialize(format="ttl"))
        print("---------GOTTEN-ONLY--------")
        print(tested_only.serialize(format="ttl"))
        self.assertEqual(len(tested_only), 0)
        self.assertEqual(len(target_only), 0)

    def test_rdfdump(self):
        with self.admin_access.cnx() as cnx:
            sql = cnx.system_sql
            rows = sql("select eid from tmp_findingaid_qualified ORDER BY eid").fetchall()
            self.assertEqual(rows, sorted([(self.ir_qualified,), (self.ir_child_qualified,)]))
            rows = sql("select * from tmp_findingaid_not_qualified").fetchall()
            self.assertEqual(rows, [(self.ir_unqualified,)])
            rows = sql("select eid from tmp_facomponent_qualified ORDER BY eid").fetchall()
            self.assertEqual(rows, [(self.fa_qualified,)])
            rows = sql("select * from tmp_facomponent_not_qualified").fetchall()
            self.assertEqual(
                rows, sorted([(self.fa_parent_of_fa_qualified,), (self.fa_unqualified,)])
            )
            base_graph = Graph()
            quality_graph = Graph()

            self.add_all_etypes_to_graph(cnx, base_graph, "BASE")
            self.add_all_etypes_to_graph(cnx, quality_graph, "QUALITY")
            self.add_all_etypes_to_graph(cnx, quality_graph, "AUTHORITY")

        dump_not_qual = env.get_template("dump_non_quality.ttl").render(
            service_eid=self.service_eid, service_nul_eid=self.not_partner_service_eid
        )
        g_expected_non_qual = Graph().parse(data=dump_not_qual, format="ttl")

        self.assertGraphEqual(base_graph, g_expected_non_qual)

        dump_qual = env.get_template("dump_quality.ttl").render(
            service_eid=self.service_eid,
            auth_eid=self.qualified_auth_eid,
            agent_auth_eid=self.qualified_agent_auth_eid,
        )
        g_expected_qual = Graph().parse(data=dump_qual, format="ttl")

        self.assertGraphEqual(quality_graph, g_expected_qual)


if __name__ == "__main__":
    unittest.main()
