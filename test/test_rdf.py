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


import csv
import datetime
import unittest

from cubicweb_web.devtools.testlib import WebCWTC, WebPostgresApptestConfiguration
from rdflib import Graph
from rdflib.compare import graph_diff

from jinja2 import Environment, FileSystemLoader

from cubicweb.rdf import add_entity_to_graph

from cubicweb_eac import testutils as eac_testutils

from cubicweb_francearchives import IIIF_MANIFEST_ROLE

from pgfixtures import setup_module, teardown_module  # noqa


env = Environment(
    loader=FileSystemLoader("test/data/rdf"),
)


class RDFAdapterTest(WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                code="FRAD084",
                category="foo",
                name="Archives dep",
                iiif_extptr=True,
            )
            fadid = cnx.create_entity(
                "Did", unitid="maindid", unittitle="maindid-title", physdesc="un beau rouleau"
            )
            fcdid = cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
            )
            dv = cnx.create_entity(
                "DigitizedVersion",
                illustration_url="https://archive.loutre/poulet.jpg",
            )
            iiif = cnx.create_entity(
                "DigitizedVersion",
                url="https://archive.loutre/manfest.json",
                role=IIIF_MANIFEST_ROLE,
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                did=fadid,
                publisher="FRAD084",
                fa_header=cnx.create_entity("FAHeader"),
                service=service,
            )
            facomp = cnx.create_entity(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                digitized_versions=[dv, iiif],
                scopecontent="<div>fc-scoppecontent</div>",
                description="<div>fc-descr</div>",
            )
            valjean = cnx.create_entity("SubjectAuthority", label="Jean Valjean")
            loutre = cnx.create_entity("SubjectAuthority", label="Loutre", quality=True)
            vigneron = cnx.create_entity("SubjectAuthority", label="Vigneron", quality=True)
            originator = cnx.create_entity("AgentAuthority", label="CNRS", quality=True)
            location = cnx.create_entity(
                "LocationAuthority",
                label="Poulailler",
                quality=True,
                longitude=42,
                latitude=4.2,
                same_as=cnx.create_entity("ExternalUri", uri="http://geonames.org/123456"),
            )
            cnx.create_entity("Subject", label="Jean Valjean", authority=valjean, index=facomp)
            cnx.create_entity(
                "Subject", label="loutre", authority=loutre, index=facomp, type="function"
            )
            cnx.create_entity(
                "Subject", label="loutre", authority=vigneron, index=facomp, type="occupation"
            )
            cnx.create_entity(
                "AgentName",
                label="Coin Nature Ressource Suivante",
                authority=originator,
                index=fa,
                role="originator",
                type="corpname",
            )
            cnx.create_entity(
                "AgentName",
                label="Coin Nature Ressource Suivante",
                authority=originator,
                index=fa,
                role="originator",
                type="name",
            )  # duplicate index but with the "name" type which should not be regarded for type
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid
            self.subject_eid = valjean.eid
            self.subject_loutre_eid = loutre.eid
            self.subject_vigneron_eid = vigneron.eid
            self.service_eid = service.eid
            self.originator_eid = originator.eid
            self.location_eid = location.eid

            with open("test/data/rdf/fake_geonames.csv") as csvfile:
                csvreader = csv.reader(csvfile)
                for row in csvreader:
                    cnx.system_sql(
                        "INSERT INTO geonames (geonameid, name, asciiname, alternatenames, "
                        "latitude, longitude, fclass, fcode, country_code, cc2, admin1_code, "
                        "admin2_code, admin3_code, admin4_code, population, elevation, dem, "
                        f"timezone, moddate) VALUES ({row[0]});"
                    )
                cnx.system_sql(
                    "INSERT INTO adm4_geonames SELECT * FROM geonames WHERE fcode='ADM4' "
                    "AND country_code='FR';"
                )
                cnx.system_sql(
                    "INSERT INTO adm3_geonames SELECT * FROM geonames WHERE fcode='ADM3' "
                    "AND country_code='FR';"
                )
                cnx.system_sql(
                    "INSERT INTO adm2_geonames SELECT * FROM geonames WHERE fcode='ADM2' "
                    "AND country_code='FR';"
                )
                cnx.system_sql(
                    "INSERT INTO adm1_geonames SELECT * FROM geonames WHERE fcode='ADM1' "
                    "AND country_code='FR';"
                )
                cnx.system_sql(
                    "INSERT INTO country_geonames SELECT * FROM geonames WHERE fcode='PCLI';"
                )
            cnx.commit()

    def assertGraphEqual(self, graph1, graph2):
        common, tested_only, target_only = graph_diff(graph1, graph2)
        self.assertEqual(len(tested_only), 0)
        self.assertEqual(len(target_only), 0)

    def test_content_rdf_RICO_facomponent(self):
        with self.admin_access.cnx() as cnx:
            facomp = cnx.find("FAComponent", eid=self.facomp_eid).one()
            facomp_adapted = facomp.cw_adapt_to("rdf")
            data = env.get_template("facomponent.ttl").render(
                service_eid=self.service_eid,
                subject_eid=self.subject_loutre_eid,
                occupation_eid=self.subject_vigneron_eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")

            g_got = Graph()
            for triple in facomp_adapted.triples():
                g_got.add(triple)
            self.assertGraphEqual(g_got, g_expected)

    def test_content_rdf_RICO_findingaid(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.find("FindingAid", eid=self.fa_eid).one()
            fa_adapted = fa.cw_adapt_to("rdf")
            data = env.get_template("findingaid.ttl").render(
                subject_eid=self.subject_loutre_eid,
                service_eid=self.service_eid,
                originator_eid=self.originator_eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")
            g_got = Graph()

            for triple in fa_adapted.triples():
                g_got.add(triple)
            self.assertGraphEqual(g_got, g_expected)

    def test_rdf_agentauthority_no_quality(self):
        with self.admin_access.cnx() as cnx:
            agent = cnx.find("AgentAuthority", eid=self.originator_eid).one()
            agent.cw_set(quality=False)
            cnx.commit()
            g_got = Graph()
            add_entity_to_graph(g_got, agent)
            self.assertEqual(len(g_got), 0)

    def test_rdf_subjectauthority_no_quality(self):
        with self.admin_access.cnx() as cnx:
            subject = cnx.find("SubjectAuthority", eid=self.subject_loutre_eid).one()
            subject.cw_set(quality=False)
            cnx.commit()
            g_got = Graph()
            add_entity_to_graph(g_got, subject)
            self.assertEqual(len(g_got), 0)

    def test_rdf_locationauthority_no_quality(self):
        with self.admin_access.cnx() as cnx:
            location = cnx.find("LocationAuthority", eid=self.location_eid).one()
            location.cw_set(quality=False)
            cnx.commit()
            g_got = Graph()
            add_entity_to_graph(g_got, location)
            self.assertEqual(len(g_got), 0)

    def test_content_rdf_RICO_subject(self):
        with self.admin_access.cnx() as cnx:
            subject = cnx.find("SubjectAuthority", eid=self.subject_loutre_eid).one()
            data = env.get_template("subject.ttl").render(
                eid=self.subject_loutre_eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")
            g_got = Graph()
            add_entity_to_graph(g_got, subject)
            self.assertGraphEqual(g_got, g_expected)

    def test_content_rdf_RICO_agent(self):
        with self.admin_access.cnx() as cnx:
            agent = cnx.find("AgentAuthority", eid=self.originator_eid).one()
            data = env.get_template("agent.ttl").render(
                eid=self.originator_eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")
            g_got = Graph()
            add_entity_to_graph(g_got, agent)
            self.assertGraphEqual(g_got, g_expected)

    def test_content_rdf_RICO_location(self):
        with self.admin_access.cnx() as cnx:
            location = cnx.find("LocationAuthority", eid=self.location_eid).one()
            data = env.get_template("location.ttl").render(
                eid=self.location_eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")
            g_got = Graph()
            add_entity_to_graph(g_got, location)
            self.assertGraphEqual(g_got, g_expected)

    def test_content_rdf_RICO_service(self):
        with self.admin_access.cnx() as cnx:
            s1 = cnx.create_entity(
                "Service",
                category="?1",
                name="s1",
                phone_number="s1-phone",
                code_insee_commune="23910",
                email="s1-email",
                address="s1-address",
                mailing_address="s1-maddress",
                zip_code="75",
                city="Paris",
                website_url="http://www.s1.fr",
                opening_period="op-period",
                contact_name="jean michel",
                level="level-F",
            )
            s2 = cnx.create_entity(
                "Service",
                category="?2",
                name="s2",
                phone_number="s2-phone",
                city="Paris",
                website_url="http://www.s2.fr",
                opening_period="op-period2",
                contact_name="jean paul",
                annex_of=s1,
            )
            cnx.commit()
            service = cnx.find("Service", eid=s1.eid).one()

            g_got = Graph()
            add_entity_to_graph(g_got, service)
            data = env.get_template("service.ttl").render(
                eid=s1.eid,
                s2_eid=s2.eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")
            self.assertGraphEqual(g_got, g_expected)

    def test_geonames_hierarchy_france(self):
        with self.admin_access.repo_cnx() as cnx:
            # Place du capitole
            capitole = cnx.create_entity(
                "LocationAuthority",
                label="Capitole",
                quality=True,
                same_as=cnx.create_entity(
                    "ExternalUri",
                    source="geoname",
                    extid="6301915",
                    uri="http://www.geonames.org/6301915",
                ),
            )
            # toulouse (adm4 and ppl)
            toulouse = cnx.create_entity(
                "LocationAuthority",
                label="Toulouse",
                quality=True,
                same_as=(
                    cnx.create_entity(
                        "ExternalUri",
                        source="geoname",
                        extid="2972315",
                        uri="http://www.geonames.org/2972315",
                    ),
                    cnx.create_entity(
                        "ExternalUri",
                        source="geoname",
                        extid="6453974",
                        uri="http://www.geonames.org/6453974",
                    ),
                ),
            )
            # Haute-Garonne (adm2)
            haute_garonne = cnx.create_entity(
                "LocationAuthority",
                label="HG",
                quality=True,
                same_as=cnx.create_entity(
                    "ExternalUri",
                    source="geoname",
                    extid="3013767",
                    uri="http://www.geonames.org/3013767",
                ),
            )
            # Occitanie (adm1)
            occitanie = cnx.create_entity(
                "LocationAuthority",
                label="Occitanie",
                quality=True,
                same_as=cnx.create_entity(
                    "ExternalUri",
                    source="geoname",
                    extid="11071623",
                    uri="http://www.geonames.org/11071623",
                ),
            )
            # France (country)
            france = cnx.create_entity(
                "LocationAuthority",
                label="France",
                quality=True,
                same_as=cnx.create_entity(
                    "ExternalUri",
                    source="geoname",
                    extid="3017382",
                    uri="http://www.geonames.org/3017382",
                ),
            )
            cnx.commit()
            capitole = cnx.entity_from_eid(capitole.eid)
            graph = Graph()
            add_entity_to_graph(graph, capitole)
            data = env.get_template("location_hierarchy_france.ttl").render(
                capitole=capitole.eid,
                toulouse=toulouse.eid,
                haute_garonne=haute_garonne.eid,
                occitanie=occitanie.eid,
                france=france.eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")
            self.assertGraphEqual(graph, g_expected)
            toulouse = cnx.entity_from_eid(toulouse.eid)
            graph = Graph()
            add_entity_to_graph(graph, toulouse)
            data = env.get_template("location_hierarchy_france_adm4_ppl.ttl").render(
                toulouse=toulouse.eid,
                haute_garonne=haute_garonne.eid,
                occitanie=occitanie.eid,
                france=france.eid,
            )
            g_expected = Graph().parse(data=data, format="ttl")
            self.assertGraphEqual(graph, g_expected)

    def test_geonames_hierarchy_country(self):
        with self.admin_access.repo_cnx() as cnx:
            # Place du capitole
            nhatran = cnx.create_entity(
                "LocationAuthority",
                label="Nha Tran (Vietnam)",
                quality=True,
                same_as=cnx.create_entity(
                    "ExternalUri",
                    source="geoname",
                    extid="1572151",
                    uri="http://www.geonames.org/1572151",
                ),
            )
            # toulouse (adm4)
            vietnam = cnx.create_entity(
                "LocationAuthority",
                label="Vietnam",
                quality=True,
                same_as=cnx.create_entity(
                    "ExternalUri",
                    source="geoname",
                    extid="1562822",
                    uri="http://www.geonames.org/1562822",
                ),
            )
            cnx.commit()
            nhatran = cnx.entity_from_eid(nhatran.eid)
            graph = Graph()
            add_entity_to_graph(graph, nhatran)
            data = env.get_template("location_hierarchy_country.ttl").render(
                nhatran=nhatran.eid, vietnam=vietnam.eid
            )
            g_expected = Graph().parse(data=data, format="ttl")
            self.assertGraphEqual(graph, g_expected)


class AuthorityRecordRdfTC(WebCWTC):
    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                category="?1",
                name="s1",
                phone_number="s1-phone",
                code_insee_commune="23910",
                email="s1-email",
                address="s1-address",
                mailing_address="s1-maddress",
                zip_code="75",
                city="Paris",
                website_url="http://www.s1.fr",
                opening_period="op-period",
                contact_name="jean michel",
                level="level-F",
            )
            copain = eac_testutils.authority_record(cnx, "B123", "Toto", xml_support="foo")
            copine = eac_testutils.authority_record(cnx, "B234", "Titi", xml_support="foo")
            occupation = cnx.create_entity(
                "Occupation",
                term="fan de poules",
                equivalent_concept=cnx.create_entity("ExternalUri", uri="1234567--aadd4445"),
            )
            person = eac_testutils.authority_record(
                cnx,
                "A123",
                "Jean Jacques",
                kind="person",
                start_date=datetime.date(2010, 1, 1),
                end_date=datetime.date(2050, 5, 2),
                reverse_occupation_agent=occupation,
                reverse_history_agent=cnx.create_entity(
                    "History", text="<p>loutre gentille<p>", text_format="text/html"
                ),
                reverse_family_from=(
                    cnx.create_entity("FamilyRelation", family_to=copain, entry="Toto"),
                    cnx.create_entity("FamilyRelation", family_to=copine, entry="Titi"),
                ),
                xml_support="foo",
                maintainer=service,
            )
            person_agent = cnx.create_entity(
                "AgentAuthority", label="Jean JACQUES", same_as=person, quality=True
            )

            parent_organization = eac_testutils.authority_record(
                cnx, "P123", "Toto Cie", kind="authority", xml_support="foo"
            )
            child_organization = eac_testutils.authority_record(
                cnx, "P243", "Titi Cie", kind="authority", xml_support="foo"
            )
            organization = eac_testutils.authority_record(
                cnx,
                "C123",
                "Entreprise",
                kind="authority",
                start_date=datetime.date(2010, 1, 1),
                end_date=datetime.date(2050, 5, 2),
                xml_support="foo",
                maintainer=service,
                reverse_name_entry_for=(
                    cnx.create_entity(
                        "NameEntry",
                        parts="PouletCorp",
                        form_variant="alternative",
                        date_relation=cnx.create_entity(
                            "DateEntity",
                            start_date=datetime.date(2019, 12, 12),
                            end_date=datetime.date(2021, 1, 1),
                        ),
                    ),
                    cnx.create_entity("NameEntry", parts="Entreprise", form_variant="authorized"),
                ),
            )
            organization_agent = cnx.create_entity(
                "AgentAuthority", label="Entreprise Corp", same_as=organization, quality=True
            )
            cnx.create_entity(
                "HierarchicalRelation",
                hierarchical_child=(child_organization),
                hierarchical_parent=(organization),
                entry="Titi Cie",
            )
            cnx.create_entity(
                "HierarchicalRelation",
                hierarchical_child=(organization),
                hierarchical_parent=(parent_organization),
                entry="Titi Cie",
            )
            fam1 = eac_testutils.authority_record(
                cnx, "F123", "Famille Pigeon", kind="family", xml_support="foo", maintainer=service
            )
            family_agent = cnx.create_entity(
                "AgentAuthority", label="Famille Pigeon", same_as=fam1, quality=True
            )
            fam2 = eac_testutils.authority_record(
                cnx, "F234", "Famille Poulet", kind="family", xml_support="foo"
            )
            cnx.create_entity(
                "FamilyRelation",
                family_from=fam1,
                family_to=fam2,
                entry="Famille Poulet",
            )
            cnx.create_entity(
                "FamilyRelation",
                family_from=fam1,
                family_to=person,
                entry="Jean Jacques",
            )
            cnx.create_entity(
                "FamilyRelation",
                family_from=person,
                family_to=fam1,
                entry="Famille Poulet",
            )

            cnx.commit()
            self.person_record_eid = person.eid
            self.person_agent_eid = person_agent.eid
            self.organization_record_eid = organization.eid
            self.organization_agent_eid = organization_agent.eid
            self.family_record_eid = fam1.eid
            self.family_agent_eid = family_agent.eid
            self.fam2_eid = fam2.eid
            self.service_eid = service.eid

    def compare_graphs(self, graph, eid_dict, target_ttl_file_name):
        data = env.get_template(target_ttl_file_name).render(**eid_dict)
        target_graph = Graph().parse(data=data, format="ttl")
        common, tested_only, target_only = graph_diff(graph, target_graph)
        self.assertEqual(len(tested_only), 0)
        self.assertEqual(len(target_only), 0)

    def test_family_authorityrecord_rico(self):
        with self.admin_access.repo_cnx() as cnx:
            record = cnx.entity_from_eid(self.family_record_eid)
            graph = Graph()
            add_entity_to_graph(graph, record)
            self.compare_graphs(
                graph,
                {
                    "agent_eid": self.family_agent_eid,
                    "service_eid": self.service_eid,
                },
                "family_authorityrecord.ttl",
            )

    def test_family_agent_rico(self):
        with self.admin_access.repo_cnx() as cnx:
            agent = cnx.entity_from_eid(self.family_agent_eid)
            graph = Graph()
            add_entity_to_graph(graph, agent)
            self.compare_graphs(
                graph,
                {
                    "agent_eid": self.family_agent_eid,
                    "person_eid": self.person_agent_eid,
                },
                "family_agent.ttl",
            )

    def test_person_authorityrecord_rico(self):
        with self.admin_access.repo_cnx() as cnx:
            record = cnx.entity_from_eid(self.person_record_eid)

            graph = Graph()
            add_entity_to_graph(graph, record)
            self.compare_graphs(
                graph,
                {
                    "agent_eid": self.person_agent_eid,
                    "service_eid": self.service_eid,
                },
                "person_authorityrecord.ttl",
            )

    def test_person_agent_rico(self):
        with self.admin_access.repo_cnx() as cnx:
            agent = cnx.entity_from_eid(self.person_agent_eid)

            graph = Graph()
            add_entity_to_graph(graph, agent)
            self.compare_graphs(
                graph,
                {"agent_eid": self.person_agent_eid, "family_eid": self.family_agent_eid},
                "person_agent.ttl",
            )

    def test_organization_authorityrecord_rico(self):
        with self.admin_access.repo_cnx() as cnx:
            record = cnx.entity_from_eid(self.organization_record_eid)

            graph = Graph()
            add_entity_to_graph(graph, record)
            self.compare_graphs(
                graph,
                {
                    "agent_eid": self.organization_agent_eid,
                    "service_eid": self.service_eid,
                },
                "organization_authorityrecord.ttl",
            )

    def test_organization_agent_rico(self):
        with self.admin_access.repo_cnx() as cnx:
            agent = cnx.entity_from_eid(self.organization_agent_eid)

            graph = Graph()
            add_entity_to_graph(graph, agent)
            self.compare_graphs(
                graph,
                {
                    "agent_eid": self.organization_agent_eid,
                },
                "organization_agent.ttl",
            )

    def test_record_no_authority_rico(self):
        with self.admin_access.repo_cnx() as cnx:
            agent = cnx.entity_from_eid(self.fam2_eid)

            graph = Graph()
            add_entity_to_graph(graph, agent)
            self.compare_graphs(
                graph,
                {},
                "record_no_authority.ttl",
            )

    def test_wikidata_relations(self):
        with self.admin_access.repo_cnx() as cnx:
            parent = cnx.create_entity("AgentAuthority", label="Parent", quality=True)
            sibling = cnx.create_entity("AgentAuthority", label="Adelphe", quality=True)
            spouse = cnx.create_entity("AgentAuthority", label="Amour", quality=True)
            institution = cnx.create_entity("AgentAuthority", label="PouletCorp", quality=True)
            person = cnx.create_entity(
                "AgentAuthority",
                label="Jean Poulet",
                wikidata_child_of=parent,
                wikidata_sibling_of=sibling,
                wikidata_spouse_of=spouse,
                wikidata_member_of=institution,
                quality=True,
            )
            child = cnx.create_entity(
                "AgentAuthority", label="Enfant", wikidata_child_of=person, quality=True
            )
            cnx.create_entity("AgentAuthority", label="Enfant nul", wikidata_child_of=person)
            cnx.commit()
            person = cnx.entity_from_eid(person.eid)

            graph = Graph()
            add_entity_to_graph(graph, person)
            self.compare_graphs(
                graph,
                {
                    "person": person.eid,
                    "parent": parent.eid,
                    "child": child.eid,
                    "sibling": sibling.eid,
                    "spouse": spouse.eid,
                    "institution": institution.eid,
                },
                "wikidata_relations.ttl",
            )


if __name__ == "__main__":
    unittest.main()
