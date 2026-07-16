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
from datetime import date
import unittest

from cubicweb_web.devtools.testlib import WebCWTC
from rdflib import Graph
from rdflib.compare import graph_diff

from cubicweb import Binary

from cubicweb_francearchives.entities import entity2schemaorg

from cubicweb_francearchives.testutils import PostgresTextMixin, S3BfssStorageTestMixin
from pgfixtures import setup_module, teardown_module  # noqa


class SchemaOrgTests(S3BfssStorageTestMixin, WebCWTC):
    def compare_graphs(self, graph, target_rdf_filepath, template_params={}):
        with open(self.datapath(target_rdf_filepath), "r") as f:
            target_rdf_content = f.read()
            for key, value in template_params.items():
                target_rdf_content = target_rdf_content.replace("{{" + key + "}}", str(value))
            target_graph = Graph().parse(data=target_rdf_content, format="json-ld")
            common, tested_only, target_only = graph_diff(graph, target_graph)

            self.assertEqual(len(tested_only), 0)
            self.assertEqual(len(target_only), 0)


class SchemaOrgFindingAidTests(SchemaOrgTests, PostgresTextMixin):
    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", code="FRAD084", category="foo", name="Archives dep"
            )
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fcdid = cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD084_xxx",
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                service=service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            facomp = cnx.create_entity(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent="fc-scoppecontent",
                description="fc-descr",
            )
            cnx.create_entity(
                "Subject",
                role="indextest",
                label="Paris",
                authority=cnx.create_entity(
                    "SubjectAuthority",
                    label="Paris",
                    same_as=cnx.create_entity(
                        "ExternalUri", uri="https://fr.wikipedia.org/wiki/Paris"
                    ),
                ),
                index=fa,
            )
            savonarole = cnx.create_entity(
                "AgentAuthority",
                label="Jérôme Savonarole",
            )
            cnx.create_entity(
                "NominaRecord",
                stable_id="FRAD084_42",
                json_data={"p": [{"f": "Jérôme", "n": "Savonarole"}], "t": "AA"},
                service=service,
                same_as=savonarole,
            )
            cnx.create_entity(
                "AgentName",
                role="indextest",
                authority=savonarole,
                index=facomp,
            )
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid

    def test_facomponent(self):
        with self.admin_access.cnx() as cnx:
            cnx.entity_from_eid(self.fa_eid)
            facomp = cnx.entity_from_eid(self.facomp_eid)
            graph = Graph().parse(data=entity2schemaorg(facomp), format="json-ld")
            self.compare_graphs(graph, "rdf/facomponent.json")

    def test_findingaid(self):
        with self.admin_access.cnx() as cnx:
            fa = cnx.entity_from_eid(self.fa_eid)
            authority = cnx.find("SubjectAuthority", label="Paris").one()
            graph = Graph().parse(data=entity2schemaorg(fa), format="json-ld")
            self.compare_graphs(
                graph, "rdf/findingaid.json", template_params={"subjectEid": authority.eid}
            )


class SchemaOrgCmsTests(SchemaOrgTests):
    def test_service(self):
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
            graph = Graph().parse(data=entity2schemaorg(s1), format="json-ld")
            self.compare_graphs(
                graph, "rdf/service.json", template_params={"eid": s1.eid, "eidSub": s2.eid}
            )

    def test_base_content(self):
        base_content_data = {
            "title": "the-title",
            "keywords": "entity-keywords",
            "content": "the-content",
            "content_format": "text/plain",
            "creation_date": "1970-01-01",
            "modification_date": "2000-01-01",
            "description": "the-description",
            "order": 1,
            "uuid": "the-uuid",
            "header": "header",
        }

        metadata_data = {"creator": "toto", "keywords": "the-keywords"}
        image_data = {
            "caption": "caption",
            "description": "description",
            "copyright": "copyright",
        }
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", **metadata_data)
            image = cnx.create_entity(
                "Image",
                image_file=cnx.create_entity(
                    "File",
                    data=Binary(b"some-file-data"),
                    data_name="image.png",
                    data_format="image/png",
                ),
                **image_data,
            )
            entity = cnx.create_entity(
                "BaseContent", metadata=metadata, basecontent_image=image, **base_content_data
            )

            cnx.commit()
            entity.cw_clear_all_caches()

            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/basecontent.json", template_params={"eid": entity.eid})

    def test_news_content(self):
        news_content_data = {
            "title": "the-title",
            "content": "the-content",
            "content_format": "text/plain",
            "creation_date": "1970-01-01",
            "modification_date": "2000-01-01",
            "order": 1,
            "uuid": "the-uuid",
            "start_date": "2017-03-10",
        }
        metadata_data = {"creator": "toto", "keywords": "the-keywords"}
        image_data = {
            "caption": "caption",
            "description": "description",
            "copyright": "copyright",
        }
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", **metadata_data)
            image = cnx.create_entity(
                "Image",
                image_file=cnx.create_entity(
                    "File",
                    data=Binary(b"some-file-data"),
                    data_name="image.png",
                    data_format="image/png",
                ),
                **image_data,
            )
            entity = cnx.create_entity(
                "NewsContent", metadata=metadata, news_image=image, **news_content_data
            )
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/newscontent.json", template_params={"eid": entity.eid})

    def test_commemoration_item(self):
        commemoration_item_data = {
            "title": "the-title",
            "content": "the-content",
            "content_format": "text/plain",
            "order": 1,
            "uuid": "the-uuid",
            "subtitle": "the-subtitle",
            "alphatitle": "the-alphatitle",
            "start_year": "1980",
            "commemoration_year": "2080",
            "on_homepage": "onhp_hp",
            "creation_date": "1970-01-01",
            "modification_date": "2000-01-01",
        }

        metadata_data = {"creator": "toto"}

        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", **metadata_data)
            entity = cnx.create_entity(
                "CommemorationItem", metadata=metadata, **commemoration_item_data
            )
            cnx.commit()
            entity.cw_clear_all_caches()

            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/commemoitem.json", template_params={"eid": entity.eid})

    def test_agentauthority(self):
        agent_data = {
            "label": "Camus, Albert (1913-1960)",
        }
        with self.admin_access.repo_cnx() as cnx:
            entity = cnx.create_entity("AgentAuthority", **agent_data)
            cnx.commit()
            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/agent.json", template_params={"eid": entity.eid})

    def test_person_authority(self):
        agent_data = {
            "label": "Camus, Albert (1913-1960)",
        }
        agent_name_data = {
            "type": "persname",
            "label": "Albert Camus",
        }
        with self.admin_access.repo_cnx() as cnx:
            entity = cnx.create_entity("AgentAuthority", **agent_data)
            cnx.create_entity("AgentName", authority=entity, **agent_name_data)
            cnx.commit()
            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/personagent.json", template_params={"eid": entity.eid})

    def test_organization_authority(self):
        agent_data = {
            "label": "ACME",
        }
        agent_name_data = {
            "type": "corpname",
            "label": "ACME",
        }
        with self.admin_access.repo_cnx() as cnx:
            entity = cnx.create_entity("AgentAuthority", **agent_data)
            cnx.create_entity("AgentName", authority=entity, **agent_name_data)
            cnx.commit()
            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(
                graph, "rdf/organizationagent.json", template_params={"eid": entity.eid}
            )

    def test_subjectauthority(self):
        agent_data = {
            "label": "le vélo",
        }
        with self.admin_access.repo_cnx() as cnx:
            entity = cnx.create_entity("SubjectAuthority", **agent_data)
            cnx.commit()
            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/subject.json", template_params={"eid": entity.eid})

    def test_locationauthority(self):
        with self.admin_access.repo_cnx() as cnx:
            location_data = {
                "label": "Saint-Pétersbourg",
                "latitude": 59.9,
                "longitude": 30.3,
            }
            entity = cnx.create_entity(
                "LocationAuthority",
                same_as=[
                    cnx.create_entity(
                        "ExternalUri",
                        uri="https://fr.wikipedia.org/wiki/Saint-P%C3%A9tersbourg",
                    ),
                    cnx.create_entity(
                        "ExternalUri",
                        uri="http://www.geonames.org/498817/saint-petersburg.html",
                    ),
                ],
                **location_data,
            )
            cnx.commit()
            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/location.json", template_params={"eid": entity.eid})

    def test_person_authority_record(self):
        with self.admin_access.repo_cnx() as cnx:
            kind_eid = cnx.find("AgentKind", name="person")[0][0]
            name = "Jean toto"
            entity = cnx.create_entity(
                "AuthorityRecord",
                record_id="FRAN_NP_006883",
                agent_kind=kind_eid,
                reverse_name_entry_for=cnx.create_entity(
                    "NameEntry", parts=name, form_variant="authorized"
                ),
                xml_support="foo",
                start_date=date(1940, 1, 1),
                end_date=date(2000, 5, 1),
                reverse_occupation_agent=cnx.create_entity("Occupation", term="éleveur de poules"),
                reverse_history_agent=cnx.create_entity(
                    "History", text="<p>Il aimait les poules</p>"
                ),
                reverse_family_from=cnx.create_entity(
                    "FamilyRelation",
                    entry="Jean Lapin",
                    family_to=cnx.create_entity(
                        "AuthorityRecord",
                        record_id="FRAN_NP_006884",
                        xml_support="bar",
                        agent_kind=kind_eid,
                        reverse_name_entry_for=cnx.create_entity(
                            "NameEntry", parts="Jean Lapin", form_variant="authorized"
                        ),
                    ),
                ),
                reverse_identity_from=cnx.create_entity(
                    "IdentityRelation",
                    entry="Toto, Jean",
                    identity_to=cnx.create_entity("ExternalUri", uri="http://toto.fr#me"),
                ),
            )
            cnx.commit()
            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/authorityrecord_person.json")

    def test_organization_authority_record(self):
        with self.admin_access.repo_cnx() as cnx:
            kind_eid = cnx.find("AgentKind", name="authority")[0][0]
            name = "La Toto compagnie"
            entity = cnx.create_entity(
                "AuthorityRecord",
                record_id="FRAN_NP_00644",
                agent_kind=kind_eid,
                reverse_name_entry_for=cnx.create_entity(
                    "NameEntry", parts=name, form_variant="authorized"
                ),
                xml_support="foo",
                start_date=date(1940, 1, 1),
                end_date=date(2000, 5, 1),
                reverse_hierarchical_parent=cnx.create_entity(
                    "HierarchicalRelation",
                    entry="Toto poules",
                    hierarchical_child=cnx.create_entity(
                        "AuthorityRecord",
                        record_id="FRAN_NP_006884",
                        xml_support="bar",
                        agent_kind=kind_eid,
                        reverse_name_entry_for=cnx.create_entity(
                            "NameEntry", parts="Toto poules", form_variant="authorized"
                        ),
                    ),
                ),
                reverse_hierarchical_child=cnx.create_entity(
                    "HierarchicalRelation",
                    entry="ACME",
                    hierarchical_parent=cnx.create_entity(
                        "AuthorityRecord",
                        record_id="FRAN_NP_006874",
                        xml_support="bar",
                        agent_kind=kind_eid,
                        reverse_name_entry_for=cnx.create_entity(
                            "NameEntry", parts="ACME", form_variant="authorized"
                        ),
                    ),
                ),
                reverse_identity_from=cnx.create_entity(
                    "IdentityRelation",
                    entry="Toto cie",
                    identity_to=cnx.create_entity("ExternalUri", uri="http://toto.fr#me"),
                ),
            )
            cnx.commit()
            graph = Graph().parse(data=entity2schemaorg(entity), format="json-ld")
            self.compare_graphs(graph, "rdf/authorityrecord_organization.json")


if __name__ == "__main__":
    unittest.main()
