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
from lxml import etree
from os import path as osp
import unittest
from unittest import mock

from cubicweb_web.devtools.testlib import WebCWTC, WebPostgresApptestConfiguration
from cubicweb_francearchives import SIAF_CODE, SIAF_AGENTS_REF_CODE
from cubicweb_francearchives.testutils import (
    S3BfssStorageTestMixin,
    PostgresTextMixin,
    XMLCompMixin,
    create_authority_record,
)

from cubicweb_francearchives.entities.agentrecord import (
    format_live_info,
    format_dates_for_activity,
    sort_activities,
    sort_relations,
)

from pgfixtures import setup_module, teardown_module  # noqa


def simone_veil_data(nice_eid=None, paris_eid=None, antoine_veil_id=None):
    birth_place = {
        "geographicCoordinates": "43.70313, 7.26608",
        "lang": "fr",
        "placeName": "Nice (Alpes-Maritimes, France)",
    }
    if nice_eid:
        birth_place["authority"] = {"label": "Nice (Alpes-Maritimes, France)", "value": nice_eid}
    death_place = {
        "geographicCoordinates": "48.86, 2.34444",
        "lang": "fr",
        "placeName": "Paris (Paris, France)",
    }
    if paris_eid:
        death_place["authority"] = {"label": "Nice (Alpes-Maritimes, France)", "value": paris_eid}
    relations = []
    if antoine_veil_id:
        relations = [
            {
                "agentType": "agent_ref",
                "targetType": "person",
                "reverseTargetType": "person",
                "targetEntity": {"label": "Antoine Veil", "value": antoine_veil_id},
                "relationType": {"value": "familly", "label": "family"},
                "targetRole": {"value": "parent", "label": "parent"},
                "reverseTargetRole": {"value": "parent", "label": "parent"},
                "dates": {
                    "fromDate": {"certainty": "certain", "date": "1946"},
                    "toDate": {"certainty": "certain", "date": "2013"},
                },
                "place": {
                    "placeName": "Paris",
                    "placeRole": "",
                    "authority": {"label": "Paris (Paris, France)", "value": paris_eid},
                },
            }
        ]

    return {
        "authorityRecordsSources": [{"id": "FRAN_NP_009941", "label": "Simone Veil"}],
        "biogHist": "<p class='abstract'>Née à Nice en 1927, Simone Veil est une figure "
        "incontournable de la vie politique française et européenne à partir du milieu "
        "des années 1970.</p>\n"
        "<p>Pionnière, elle occupe au sein de l'administration des postes "
        "réservés jusqu'alors aux hommes.</p>\n"
        "<p>Elle occupe par la suite les fonctions suivantes :</p>\n"
        "<ul>\n"
        "<li>ministre de la Santé</li>\n"
        "<li>présidete du Parlement de Strasbourg</li>\n"
        "<li>présidente du Haut conseil à l’intégration (1997-1998)</li>\n"
        "</ul>\n"
        "<p>Simone Jacob est née le 13 juillet 1927 à Nice.</p>",
        "birthPlace": birth_place,
        "creationMode": "manual",
        "deathPlace": death_place,
        "entityGender": "female",
        "entityType": "person",
        "existDates": {
            "fromDate": {"certainty": "certain", "date": "1927", "status": ""},
            "toDate": {"certainty": "certain", "date": "2017"},
        },
        "identityIds": [
            {
                "id": "Q298180",
                "source": "Wikidata",
                "url": "https://www.wikidata.org/wiki/Q298180",
                "titleLink": "",
            },
            {"id": "283626992", "source": "IDREF"},
        ],
        "lastValidatedStep": 3,
        "maintenanceHistory": [
            {
                "maintenanceEventType": "created",
                "agent": "Jean Valjean",
                "eventDateTime": "2025-01-09T14:35:52.289162+00:00",
            },
            {
                "maintenanceEventType": "revised",
                "agent": "Jean Valjean",
                "eventDateTime": "2025-07-09T14:35:52.289162+00:00",
            },
        ],
        "maintenanceStatus": "derived",
        "nameEntry": "Simone Veil",
        "occupations": [
            {
                "term": {
                    "label": "ministre de la Santé",
                },
                "dates": {
                    "fromDate": {"certainty": "certain", "date": "1974"},
                    "toDate": {"certainty": "certain", "date": "1979"},
                },
                "place": {
                    "placeName": "Paris",
                    "authority": {"label": "Paris (Paris, France)", "value": paris_eid},
                },
            },
            {
                "term": {"label": "elu"},
                "dates": {
                    "fromDate": {"certainty": "certain", "date": "1993"},
                    "toDate": {"certainty": "certain", "date": "1995"},
                },
            },
            {
                "term": {"label": "magistrat"},
            },
        ],
        "otherNameEntries": [
            {
                "part": "Simone Annie Liline Jacob",
                "language": "fr",
                "useDates": {
                    "fromDate": {"date": 1927, "certainty": "certain"},
                    "toDate": {"date": 2017, "certainty": "certain"},
                },
            },
            {
                "part": "Simone Jacob",
                "language": "fr",
                "useDates": {
                    "fromDate": {},
                    "toDate": {},
                },
            },
        ],
        "publicationStatus": "inProcess",
        "relations": relations,
        "sourceIds": [
            {
                "source": "1927-2017 : c’était Simone Veil",
                "url": "https://www.info.gouv.fr/actualite/1927-2017-cetait-simone-veil",
            },
        ],
        "sourceDataBnf": "https://data.bnf.fr/ark:/12148/cb11927825h",
        "sourceAuthorityRecords": [
            {
                "url": "https://francearchives.gouv.fr/authorityrecord/FRAN_NP_009941",
                "service": "Archives nationales",
            },
            {
                "url": "https://francearchives.gouv.fr/fr/authorityrecord/FRAN_NP_009871",
                "service": "Archives nationales",
            },
        ],
    }


def antoine_veil_data():
    return {
        "entityGender": "male",
        "entityType": "person",
        "existDates": {
            "fromDate": {"certainty": "certain", "date": "1926"},
            "toDate": {"certainty": "certain", "date": "2013"},
        },
        "nameEntry": "Antoine Veil",
        "sourceWikiData": "https://www.wikidata.org/wiki/Q2856787",
    }


def corporate_body_agent_data(nice_eid=None, paris_eid=None, parti_eid=None):
    return {
        "activityPlaces": [
            {
                "address": None,
                "authority": None,
                "dates": {
                    "fromDate": {"certainty": "certain", "date": 1980},
                    "toDate": {"certainty": "certain", "date": 1980},
                },
                "lang": None,
                "placeName": "Rouen (76000), Communes françaises",
            },
            {
                "address": "rue d’Ulm 75005",
                "authority": {"label": "Paris (Paris, France)", "value": paris_eid},
                "dates": {
                    "fromDate": {"certainty": "certain", "date": 1980, "status": ""},
                    "toDate": {"certainty": "certain", "date": 2010},
                },
                "geographicCoordinates": "48.86, 2.34444",
                "lang": None,
                "placeName": "Paris (Paris, France)",
            },
        ],
        "creationMode": "external",
        "entityType": "corporateBody",
        "existDates": {
            "fromDate": {"certainty": "certain", "date": "1904", "status": ""},
            "toDate": {"status": "ongoing"},
        },
        "functions": [{"term": {"label": "Parti politique", "value": parti_eid}}],
        "lastModificationDate": "2025-07-16T20:43:37.460767+00:00",
        "lastModifiedBy": "admin",
        "lastValidatedStep": 5,
        "legalStatus": [{"label": "Parti politique", "value": "1234"}],
        "maintenanceHistory": [
            {
                "maintenanceEventType": "created",
                "agent": "Jean Valjean",
                "eventDateTime": "2025-01-09T14:35:52.289162+00:00",
            },
        ],
        "maintenanceStatus": "derived",
        "nameEntry": "Section Française de l'Internationale Ouvrière",
        "otherNameEntries": [
            {
                "language": "en",
                "part": "French Section of the Workers' International",
                "useDates": {
                    "fromDate": {"certainty": "certain", "date": "1904"},
                    "toDate": {"certainty": "certain", "date": "1969"},
                },
            },
            {
                "language": "fr",
                "part": "Section française de l'Internationale ouvrière",
                "useDates": {
                    "toDate": {"certainty": "certain", "date": "1969"},
                },
            },
            {
                "language": "fr",
                "part": "PSU-SFIO",
                "useDates": {
                    "fromDate": {"certainty": "uncertain", "date": "1905"},
                },
            },
        ],
        "publicationStatus": "inProcess",
        "relations": [],
        "sourceAuthority": 166342993,
        "sourceAuthorityRecords": [""],
        "sourceDataBnf": "https://data.bnf.fr/fr/ark:/12148/cb119909",
    }


def create_occupations_field(cnx, expected_occupations):
    occupations = []
    for occupation, fdate, fdate_cert, tdate, tdate_cert, place in expected_occupations:
        occupation_entity = cnx.create_entity("AgentRecordOccupation", label=occupation)
        occupations.append(
            {
                "term": {
                    "label": occupation,
                    "value": occupation_entity.eid,
                },
                "dates": {
                    "fromDate": {"certainty": fdate_cert, "date": fdate},
                    "toDate": {"certainty": tdate_cert, "date": tdate},
                },
                "place": {
                    "placeName": place,
                },
            }
        )
    cnx.commit()
    return occupations


def create_simple_corporate_body(minister_label):
    return {
        "entityType": "corporateBody",
        "nameEntry": minister_label,
        "otherNameEntries": [],
        "legalStatus": [{"label": "ministère", "value": 5611}],
    }


def add_work_for_minister(target_lbl, target_id, fdate, tdate, role, ministre_eid):
    return {
        "agentType": "agent_ref",
        "targetType": "corporateBody",
        "reverseTargetType": "person",
        "targetEntity": {
            "label": target_lbl,
            "value": target_id,
        },
        "relationType": {"label": "professionnelle", "value": "professional"},
        "reverseTargetRole": {
            "label": role.label,
            "value": role.eid,
        },
        "dates": {
            "fromDate": {"date": fdate, "status": "", "certainty": "uncertain"},
            "toDate": {"date": tdate, "status": "", "certainty": "uncertain"},
        },
        "targetRole": {"label": "ministre", "value": ministre_eid},
    }


class AgentRecord(S3BfssStorageTestMixin, PostgresTextMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def test_agent_creation(self):
        with self.admin_access.cnx() as cnx:
            for index in range(1, 3):
                record_id = f"{SIAF_CODE}_{SIAF_AGENTS_REF_CODE}_0000000{index}"
                cnx.create_entity("AgentRecord", json_data=simone_veil_data(), record_id=record_id)
                cnx.commit()


class AgentRecordMainProps(S3BfssStorageTestMixin, PostgresTextMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def test_agent_record_personal_info(self):
        with self.admin_access.cnx() as cnx:
            record_id = f"{SIAF_CODE}_{SIAF_AGENTS_REF_CODE}_00000001"
            data = antoine_veil_data()
            data["occupations"] = create_occupations_field(
                cnx,
                [
                    ["facteur", "1946", "approximate", "1948", "uncertain", "Limoges"],
                    ["enseignant", "1949", "certain", "1955", "uncertain", "Nice"],
                    ["écrivain", "1952", "certain", "1999", "certain", "Paris"],
                ],
            )
            antoine_veil = cnx.create_entity("AgentRecord", record_id=record_id, json_data=data)
            minister_json_data = create_simple_corporate_body("Ministère de la santé")
            minister_id = f"{SIAF_CODE}_{SIAF_AGENTS_REF_CODE}_00000002"
            cnx.create_entity("AgentRecord", record_id=minister_id, json_data=minister_json_data)
            role_ministre = cnx.create_entity("AgentRecordOccupation", label="Ministre")
            ministre_eid = cnx.create_entity("AgentRecordOccupation", label="ministre").eid
            cnx.commit()

            #  update relations
            data["relations"] = []
            for fdate, tdate in [("1975", "1980"), ("1984", "1986")]:
                data["relations"].append(
                    add_work_for_minister(
                        "Ministère de la santé",
                        minister_id,
                        fdate,
                        tdate,
                        role_ministre,
                        ministre_eid,
                    )
                )
            antoine_veil.cw_set(json_data=data)
            cnx.commit()
            adapter = antoine_veil.cw_adapt_to("entity.main_props")
            birth_info, death_info = antoine_veil.processed_person_exist_infos()
            self.assertDictEqual(
                birth_info, {"date": "1926", "certainty": "certain", "place": None}
            )
            self.assertDictEqual(
                death_info, {"date": "2013", "certainty": "certain", "place": None}
            )
            personal_info = adapter.build_personal_info()
            self.assertEqual(format_live_info(cnx, birth_info), personal_info["birth_info_label"])
            self.assertEqual(format_live_info(cnx, death_info), personal_info["death_info_label"])
            antoine_veil.cw_clear_all_caches()
            adapter.format_person_infos()
            antoine_veil = cnx.entity_from_eid(antoine_veil.eid)
            occupations = antoine_veil.processed_occupations
            adapter.format_activities("activities", occupations)

    def test_format_live_info(self):
        with self.admin_access.cnx() as cnx:
            b_info = {"date": "1926", "certainty": "approximate", "place": None}
            self.assertEqual(format_live_info(cnx, b_info), "<p>environ 1926</p>")
            b_info = {"date": "1926", "certainty": "uncertain", "place": None}
            self.assertEqual(format_live_info(cnx, b_info), "<p>1926?</p>")
            b_info = {"date": "1926", "certainty": "approximate", "place": "Paris"}
            self.assertEqual(format_live_info(cnx, b_info), "<p>environ 1926 à Paris</p>")
            b_info = {"date": "1926", "place": "Nice"}
            self.assertEqual(format_live_info(cnx, b_info), "<p>1926 à Nice</p>")

    def test_format_dates_for_activity(self):
        fdate = {"date": "1926", "certainty": "approximate"}
        tdate = {"date": "1927", "certainty": "uncertain"}
        dates = {
            "fromDate": fdate,
            "toDate": tdate,
        }
        self.assertEqual(format_dates_for_activity(dates), "dates : environ 1926-1927?")
        fdate = {"date": "2022", "certainty": "certain"}
        tdate = {"date": None, "certainty": "", "status": "ongoing"}
        dates = {
            "fromDate": fdate,
            "toDate": tdate,
        }
        format_dates_for_activity(dates)
        self.assertEqual(format_dates_for_activity(dates), "dates : 2022-en cours")
        dates = {}
        self.assertEqual(format_dates_for_activity(dates), "")


class TestSortFunctions(unittest.TestCase):
    def test_sort_activities_with_none_date(self):
        item = {"dates": {"fromDate": {}}, "term": {"label": "Test"}}
        result = sort_activities(item)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], "Test")

    def test_sort_activities_with_empty_date(self):
        item = {"dates": {"fromDate": {"date": ""}}, "term": {"label": "Test"}}
        result = sort_activities(item)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], "Test")

    def test_sort_activities_with_invalid_date(self):
        item = {"dates": {"fromDate": {"date": "invalid"}}, "term": {"label": "Test"}}
        result = sort_activities(item)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], "Test")

    def test_sort_activities_with_valid_date(self):
        item = {"dates": {"fromDate": {"date": "1990"}}, "term": {"label": "Test"}}
        result = sort_activities(item)
        self.assertEqual(result[0], 1)
        self.assertEqual(result[1], -1990)
        self.assertEqual(result[2], "Test")

    def test_sort_activities_with_int_date(self):
        item = {"dates": {"fromDate": {"date": 1990}}, "term": {"label": "Test"}}
        result = sort_activities(item)
        self.assertEqual(result[0], 1)
        self.assertEqual(result[1], -1990)
        self.assertEqual(result[2], "Test")

    def test_sort_activities_with_none_item(self):
        result = sort_activities(None)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], "")

    def test_sort_activities_with_missing_dates(self):
        item = {"term": {"label": "Test"}}
        result = sort_activities(item)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], "Test")

    def test_sort_activities_ordering(self):
        items = [
            {"dates": {"fromDate": {"date": "1990"}}, "term": {"label": "B"}},
            {"dates": {"fromDate": {}}, "term": {"label": "A"}},
            {"dates": {"fromDate": {"date": "1980"}}, "term": {"label": "C"}},
            {"dates": {"fromDate": {"date": "2000"}}, "term": {"label": "D"}},
        ]
        sorted_items = sorted(items, key=sort_activities)
        self.assertEqual(sorted_items[0]["term"]["label"], "A")
        self.assertEqual(sorted_items[1]["term"]["label"], "D")
        self.assertEqual(sorted_items[2]["term"]["label"], "B")
        self.assertEqual(sorted_items[3]["term"]["label"], "C")

    def test_sort_relations_with_none_date(self):
        mock_entity = mock.Mock()
        mock_entity.dc_title.return_value = "Test Entity"
        item = {"dates": {"fromDate": {}}, "targetEntity": {"entity": mock_entity}}
        result = sort_relations(item)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], "Test Entity")

    def test_sort_relations_with_valid_date(self):
        mock_entity = mock.Mock()
        mock_entity.dc_title.return_value = "Test Entity"
        item = {
            "dates": {"fromDate": {"date": "1995"}},
            "targetEntity": {"entity": mock_entity},
        }
        result = sort_relations(item)
        self.assertEqual(result[0], 1)
        self.assertEqual(result[1], -1995)
        self.assertEqual(result[2], "Test Entity")

    def test_sort_relations_with_invalid_date(self):
        mock_entity = mock.Mock()
        mock_entity.dc_title.return_value = "Test Entity"
        item = {
            "dates": {"fromDate": {"date": None}},
            "targetEntity": {"entity": mock_entity},
        }
        result = sort_relations(item)
        self.assertEqual(result[0], 0)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], "Test Entity")

    def test_sort_relations_ordering(self):
        mock_entity_1 = mock.Mock()
        mock_entity_1.dc_title.return_value = "Entity 1"
        mock_entity_2 = mock.Mock()
        mock_entity_2.dc_title.return_value = "Entity 2"
        mock_entity_3 = mock.Mock()
        mock_entity_3.dc_title.return_value = "Entity 3"

        items = [
            {
                "dates": {"fromDate": {"date": "1990"}},
                "targetEntity": {"entity": mock_entity_1},
            },
            {"dates": {"fromDate": {}}, "targetEntity": {"entity": mock_entity_2}},
            {
                "dates": {"fromDate": {"date": "2000"}},
                "targetEntity": {"entity": mock_entity_3},
            },
        ]
        sorted_items = sorted(items, key=sort_relations)
        self.assertEqual(sorted_items[0]["targetEntity"]["entity"].dc_title(), "Entity 2")
        self.assertEqual(sorted_items[1]["targetEntity"]["entity"].dc_title(), "Entity 3")
        self.assertEqual(sorted_items[2]["targetEntity"]["entity"].dc_title(), "Entity 1")


class AgentRecordEACCPF(S3BfssStorageTestMixin, XMLCompMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            record_id = f"{SIAF_CODE}_{SIAF_AGENTS_REF_CODE}_00000001"
            antoine_veil = cnx.create_entity(
                "AgentRecord", record_id=record_id, json_data=antoine_veil_data()
            )
            paris_eid = cnx.create_entity(
                "LocationAuthority", label="Paris (Paris, France)", quality=True
            ).eid
            nice_eid = cnx.create_entity(
                "LocationAuthority", label="Nice (Alpes-Maritimes, France)", quality=True
            ).eid
            self.simone_veil_eid = cnx.create_entity(
                "AgentRecord",
                record_id=f"{SIAF_CODE}{SIAF_AGENTS_REF_CODE}__00000001",
                json_data=simone_veil_data(
                    paris_eid=paris_eid,
                    nice_eid=nice_eid,
                    antoine_veil_id=antoine_veil.record_id,
                ),
            ).eid
            self.antoine_veil_eid = antoine_veil.eid
            self.cbody_agent_eid = cnx.create_entity(
                "AgentRecord",
                record_id=f"{SIAF_CODE}_{SIAF_AGENTS_REF_CODE}_00000003",
                json_data=corporate_body_agent_data(paris_eid=paris_eid, nice_eid=nice_eid),
            ).eid
            self.authority_record_1_eid = create_authority_record(
                cnx,
                name="Veil, Simone (1927-2017)",
                record_id="FRAN_NP_009941",
            )
            self.authority_record_2_eid = create_authority_record(
                cnx,
                name="Cabinet de Simone Veil, ministre des Affaires sociales, de la Santé et de la Ville",  # noqa
                record_id="FRAN_NP_009871",
            )
            cnx.commit()

    @unittest.skip("Wait for eac cpf new specifications")
    def test_person_eac_cpf_export(self):
        with self.admin_access.cnx() as cnx:
            simone_veil = cnx.entity_from_eid(self.simone_veil_eid)
            adapter = simone_veil.cw_adapt_to("EAC-CPF-v2")
            generated_eac = adapter.dump()
            filepath = self.datapath(osp.join("eac"), "SimoneVeil.xml")
            with open(filepath, "wb") as expected:
                expected.write(generated_eac)
            with open(filepath, "r") as expected:
                self.assertXMLEqual(
                    etree.parse(expected).getroot(), etree.fromstring(generated_eac)
                )
            self.assertXmlValid(
                generated_eac, self.datapath(osp.join("eac"), "eac_cpf_v2.xsd"), debug=True
            )

    def test_cbody_eac_cpf_export(self):
        with self.admin_access.cnx() as cnx:
            agent = cnx.entity_from_eid(self.cbody_agent_eid)
            adapter = agent.cw_adapt_to("EAC-CPF-v2")
            generated_eac = adapter.dump()
            filepath = self.datapath(osp.join("eac"), "SFIO.xml")
            with open(filepath, "wb") as expected:
                expected.write(generated_eac)
            with open(filepath, "r") as expected:
                self.assertXMLEqual(
                    etree.parse(expected).getroot(), etree.fromstring(generated_eac)
                )
            self.assertXmlValid(
                generated_eac, self.datapath(osp.join("eac"), "eac_cpf_v2.xsd"), debug=True
            )


if __name__ == "__main__":
    unittest.main()
