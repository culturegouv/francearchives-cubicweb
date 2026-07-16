# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2021
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

import unittest

from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.dataimport import (
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.csv_nomina.nomina import CSVNominaReader
from cubicweb_francearchives.entities.nomina import (
    nominarecord_from_esdoc,
    normalized_doctype_code,
    nomina_translate_codetype,
    format_date_location,
    format_event_location,
)
from cubicweb_francearchives.storage import S3BfssStorageMixIn

from cubicweb_francearchives.testutils import (
    NominaImportMixin,
    PostgresTextMixin,
)

from pgfixtures import setup_module, teardown_module  # noqa


class CSVNominaImportTC(PostgresTextMixin, NominaImportMixin, WebCWTC):
    def csv_filepath(self, filepath):
        return self.get_or_create_imported_filepath(f"nomina/{filepath}")

    def setup_database(self):
        super(CSVNominaImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service",
                name="Département des Landes",
                code="FRAD040",
                category="DS",
                short_name="Landes",
            )
            cnx.commit()
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(self.service.code, services_map)

    def test_import_rm_nominarecords(self):
        """Test CSV RM standard importing.

        Trying: valid OAI-PMH
        Expecting: 22 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, len(es_docs))
            stable_id = "dcd84014de91455b33bb622ba969fd828815a7b0"
            for doc in es_docs:
                self.assertEqual(doc["_source"]["act_type"], "RM")
                self.assertEqual(doc["_source"]["cote"], "R P 392")
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "absolute_url": f"https://testing.cubicweb/basedenoms/{stable_id}",
                "act_date": None,
                "act_number": "1",
                "act_type": "RM",
                "additional_info": None,
                "alltext": "R P 392 Sait lire, écrire et compter homme Matricule militaire Mont-de-Marsan "  # noqa
                "Landes France Labrit",
                "agent": [],
                "birth_commune": "Labrit",
                "birth_country": "France",
                "birth_date": "1867",
                "birth_dates": {"gte": "1867", "lte": "1867"},
                "birth_department": "Landes",
                "cote": "R P 392",
                "creation_date": entity_data["creation_date"],
                "death_date": None,
                "death_dates": None,
                "event_commune": "Mont-de-Marsan",
                "event_country": "France",
                "event_date": "1887",
                "event_dates": {"gte": "1887", "lte": "1887"},
                "event_department": "Landes",
                "event_year": "1887",
                "forenames": ["Jean"],
                "gender": "h",
                "historical_context": None,
                "instruction": "3",
                "mention_mpf": None,
                "modification_date": entity_data["modification_date"],
                "names": ["Dubos"],
                "notice_id": "FRAD040_2",
                "oai_id": None,
                "occupations": ["charron"],
                "occupations_index": ["charron"],
                "recruitment_commune": "Mont-de-Marsan",
                "recruitment_country": "France",
                "recruitment_date": "1887",
                "recruitment_dates": {"gte": "1887", "lte": "1887"},
                "recruitment_department": "Landes",
                "residence_commune": "Labrit",
                "residence_country": "France",
                "residence_department": "Landes",
                "service": entity_data["service"],
                "source_url": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a20d4f",  # noqa
                "stable_id": "dcd84014de91455b33bb622ba969fd828815a7b0",
                "title": "Dubos, Jean",
            }
            self.assertEqual(expected, entity_data)
            self.assertEqual("Dubos, Jean", es_nomina.dc_title())
            self.assertEqual("1867", entity_data["birth_date"])
            self.assertEqual(None, entity_data["death_date"])
            self.assertEqual("1887", entity_data["event_date"])
            self.assertEqual(None, entity_data["act_date"])

            self.assertEqual(
                "1867; Labrit (Landes, France)", format_date_location(cnx, entity_data, "birth")
            )

            self.assertEqual(["charron"], entity_data["occupations"])
            self.assertEqual(["charron"], entity_data["occupations_index"])

            self.assertEqual("3", entity_data["instruction"])
            self.assertEqual(
                "1887; Mont-de-Marsan (Landes, France)",
                format_date_location(cnx, entity_data, "event"),
            )
            self.assertEqual(
                "1887; Mont-de-Marsan (Landes, France)",
                format_date_location(cnx, entity_data, "recruitment"),
            )

            self.assertEqual("", format_date_location(cnx, entity_data, "death")),
            self.assertEqual(
                "Labrit (Landes, France)", format_event_location(entity_data, "residence")
            ),
            self.assertEqual("R P 392", entity_data["cote"])
            self.assertEqual("1", entity_data["act_number"])
            self.assertEqual(
                "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a20d4f",
                entity_data["source_url"],
            )
            self.assertEqual("FRAD040_2", entity_data["notice_id"])

    def test_import_rm_nominarecords_with_agent(self):
        """Test CSV RM standard importing.

        Trying: valid OAI-PMH with a preexisting agent
        Expecting: 22 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            nomina_uri = f"https://testing.cubicweb/basedenoms/{stable_id}"
            agent = cnx.create_entity("AgentAuthority", label="Toto Poulet")
            exturi = cnx.create_entity(
                "ExternalUri", extid=stable_id, uri=nomina_uri, source="nomina"
            )
            cnx.execute(
                "SET X same_as Y WHERE X eid %(agent)s, Y eid %(uri)s, NOT EXISTS(X same_as Y)",
                {"agent": agent.eid, "uri": exturi.eid},
            )
            cnx.commit()
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, len(es_docs))
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]

            for doc in es_docs:
                self.assertEqual(doc["_source"]["act_type"], "RM")
                self.assertEqual(doc["_source"]["cote"], "R P 392")
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "absolute_url": nomina_uri,
                "act_date": None,
                "act_number": "15",
                "act_type": "RM",
                "additional_info": None,
                "alltext": "R P 392 Ne sait ni lire ni écrire homme Matricule militaire Mont-de-Marsan Landes France Canenx (Canenx-et-Réaut) Toto Poulet",  # noqa
                "agent": [agent.eid],
                "birth_commune": "Canenx (Canenx-et-Réaut)",
                "birth_country": "France",
                "birth_date": "1867",
                "birth_dates": {"gte": "1867", "lte": "1867"},
                "birth_department": "Landes",
                "cote": "R P 392",
                "creation_date": entity_data["creation_date"],
                "death_date": None,
                "death_dates": None,
                "event_commune": "Mont-de-Marsan",
                "event_country": "France",
                "event_date": "1887",
                "event_dates": {"gte": "1887", "lte": "1887"},
                "event_department": "Landes",
                "event_year": "1887",
                "forenames": ["Pierre"],
                "gender": "h",
                "historical_context": None,
                "instruction": "0",
                "mention_mpf": None,
                "modification_date": entity_data["modification_date"],
                "names": ["Béton"],
                "notice_id": "FRAD040_16",
                "oai_id": None,
                "occupations": ["domestique"],
                "occupations_index": ["domestique"],
                "recruitment_commune": "Mont-de-Marsan",
                "recruitment_country": "France",
                "recruitment_date": "1887",
                "recruitment_dates": {"gte": "1887", "lte": "1887"},
                "recruitment_department": "Landes",
                "residence_commune": "Canenx (Canenx-et-Réaut)",
                "residence_country": "France",
                "residence_department": "Landes",
                "service": entity_data["service"],
                "source_url": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a252be",  # noqa
                "stable_id": "d0d3c2e7cc1c96232f942996a593354891cc5fbb",
                "title": "Béton, Pierre",
            }
            self.assertEqual(expected, entity_data)
            self.assertEqual("Béton, Pierre", es_nomina.dc_title())
            self.assertEqual(
                "1867; Canenx (Canenx-et-Réaut) (Landes, France)",
                format_date_location(cnx, entity_data, "birth"),
            )
            self.assertEqual(
                "",
                format_date_location(cnx, entity_data, "death"),
            )
            self.assertEqual(
                "1887; Mont-de-Marsan (Landes, France)",
                format_date_location(cnx, entity_data, "event"),
            )
            self.assertEqual(
                "1887; Mont-de-Marsan (Landes, France)",
                format_date_location(cnx, entity_data, "recruitment"),
            )

            self.assertEqual(
                "Canenx (Canenx-et-Réaut) (Landes, France)",
                format_event_location(entity_data, "residence"),
            )
            self.assertEqual(["domestique"], entity_data["occupations"])
            self.assertEqual("0", entity_data["instruction"])
            self.assertEqual(None, entity_data["death_date"])
            self.assertEqual(None, entity_data["act_date"])
            self.assertEqual("15", entity_data["act_number"])
            self.assertEqual("RM", entity_data["act_type"])
            self.assertEqual("R P 392", entity_data["cote"])
            self.assertEqual("FRAD040_16", entity_data["notice_id"])

    def test_import_mpf1418_nominarecords(self):
        """Test CSV MPF14-18 standard importing.

        Trying: import 23 NominaRecords one of which is duplicated
        Expecting: 22 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="MPF14-18")
            self.assertEqual(22, len(es_docs))
            es_doc = None
            stable_id = "dcd84014de91455b33bb622ba969fd828815a7b0"

            for doc in es_docs:
                self.assertEqual(doc["_source"]["act_type"], "MPF14-18")
                self.assertEqual(doc["_source"]["cote"], "R P 392")
                if doc["_source"]["stable_id"] == stable_id:
                    es_doc = doc
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            self.assertEqual("MPF14-18", entity_data["act_type"])
            self.assertIsNone(entity_data["death_date"])
            self.assertEqual(
                "1867; Labrit (Landes, France)",
                format_date_location(cnx, entity_data, "birth"),
            )
            self.assertEqual("", format_date_location(cnx, entity_data, "death"))
            self.assertEqual("", format_date_location(cnx, entity_data, "event"))
            self.assertEqual(
                "1887; Mont-de-Marsan (Landes, France)",
                format_date_location(cnx, entity_data, "recruitment"),
            )
            self.assertIsNone(entity_data["act_date"])

    def test_import_nominarecords_wrong_headers(self):
        """Test CSV RM standard importing.

        Trying: import a CSV file with wrong headers
        Expecting: No NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise_ko.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertFalse(es_docs)

    def test_delete_nominarecords(self):
        """Test OAI nomina standard importing.


        Trying: import 22 new NominaRecords and reimport same data with 1 NominaRecord deleted
        Expecting: 21 NominaRecords are found after reimport
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, len(es_docs))
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
            # reimport with deleted FRAD040_16
            filepath = self.csv_filepath("Landes_RM_normalise_delete.csv")
            reader = CSVNominaReader(self.readerconfig, cnx, self.service.code)
            st = S3BfssStorageMixIn()
            es_docs = list(reader.import_records(st, filepath, doctype="RM", delimiter=","))
            self.assertEqual(21, len(es_docs))
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
            self.assertFalse(es_doc)
            self.assertEqual([(stable_id, "RM")], reader.nomina_records_to_delete)

    def test_import_nominarecords_csv_oai_FRAD003(self):
        """Test CSV nomina importing with data in OAI CSV form.

        Trying: import 5 NominaRecords one of which is duplicated
        Expecting: 4 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("FRAD003_oai.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertEqual(4, len(es_docs))
            stable_id = "299648bc990b977d5ee1852ffad08d5840b36985"
            for doc in es_docs:
                self.assertEqual(doc["_source"]["act_type"], "RM")
                if doc["_source"]["stable_id"] == stable_id:
                    es_doc = doc
            nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = nomina.data["entity"]
            self.assertEqual("Ratier, Isidore Louis Alexandre", nomina.dc_title())
            self.assertEqual(None, entity_data["notice_id"])
            adapter = nomina.data["main_props"]
            self.assertEqual("1872; Illiers (Eure-et-Loir, France)", adapter["Birth"])
            self.assertEqual("Charretier", adapter["NMN_C_occupations"])
            self.assertEqual("Ne sait ni lire ni écrire", adapter["NMN_C_education"])
            self.assertEqual("1892; Eure-et-Loir (France)", adapter["Enrolment year and place"])
            self.assertEqual("", adapter["Death"])
            self.assertEqual("Epernon (Eure-et-Loir)", adapter["NMN_R"])
            self.assertEqual("Matricule militaire", adapter["Doctype_label"])
            self.assertEqual("1 R 453", adapter["NMN_C_cote"])
            self.assertEqual("21", adapter["NMN_C_nro"])

    def test_import_nominarecords_csv_oai_FRAD056(self):
        """Test CSV nomina importing with data in OAI CSV form.

        Trying: import 5 NominaRecords one of which is duplicated
        Expecting: 4 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("FRAD056_oai.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertEqual(4, len(es_docs))
            stable_id = "5f3d4834dbac9b63055011b32dd59804d006a110"
            for doc in es_docs:
                self.assertEqual(doc["_source"]["act_type"], "RM")
                if doc["_source"]["stable_id"] == stable_id:
                    es_doc = doc
            nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = nomina.data["entity"]
            expected = {
                "absolute_url": "https://testing.cubicweb/basedenoms/5f3d4834dbac9b63055011b32dd59804d006a110",  # noqa
                "act_date": None,
                "act_number": "29",
                "act_type": "RM",
                "additional_info": None,
                "agent": [],
                "alltext": "1 R757/29 Ne sait ni lire ni écrire homme Matricule militaire Grand-Champ Morbihan",  # noqa
                "birth_commune": "Grand-Champ",
                "birth_country": None,
                "birth_date": None,
                "birth_dates": None,
                "birth_department": "Morbihan",
                "cote": "1 R757/29",
                "creation_date": entity_data["creation_date"],
                "death_date": None,
                "death_dates": None,
                "event_date": "[1875-1882]",
                "event_dates": {"gte": "1875", "lte": "1882"},
                "event_year": "1875",
                "forenames": ["Joseph Marie"],
                "gender": "h",
                "historical_context": None,
                "instruction": "0",
                "mention_mpf": None,
                "modification_date": entity_data["modification_date"],
                "names": ["Granvallet"],
                "notice_id": None,
                "oai_id": "/ark:/15049/2743974/setSpec:matricules/metadataPrefix:nomina",
                "occupations": ["laboureur"],
                "occupations_index": ["laboureur"],
                "recruitment_date": "[1875-1882]",
                "recruitment_dates": {"gte": "1875", "lte": "1882"},
                "service": self.service.eid,
                "source_url": "https://rechercher.patrimoines-archives.morbihan.fr/ark:/15049/2743974/setSpec:matricules/metadataPrefix:nomina",  # noqa
                "stable_id": "5f3d4834dbac9b63055011b32dd59804d006a110",
                "title": "Granvallet, Joseph Marie",
            }
            self.assertEqual(expected, entity_data)
            self.assertEqual("Granvallet, Joseph Marie", nomina.dc_title())
            self.assertEqual(None, entity_data["notice_id"])
            adapter = nomina.data["main_props"]
            self.assertEqual("Grand-Champ (Morbihan)", adapter["Birth"])
            self.assertEqual("laboureur", adapter["NMN_C_occupations"])
            self.assertEqual("Ne sait ni lire ni écrire", adapter["NMN_C_education"])
            self.assertEqual("[1875-1882]", adapter["Enrolment year and place"])
            self.assertEqual("", adapter["Death"])
            self.assertEqual("", adapter["NMN_R"])
            self.assertEqual("Matricule militaire", adapter["Doctype_label"])
            self.assertEqual("1 R757/29", adapter["NMN_C_cote"])
            self.assertEqual("29", adapter["NMN_C_nro"])

    def test_import_nominarecords_csv_oai_no_doctype(self):
        """Test CSV nomina importing with data in OAI CSV form without doctype.

        Trying: valid CSV
        Expecting: 0 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("FRAD003_oai_no_doctype.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertFalse(es_docs)

    def test_import_nominarecords_csv_oai_no_person(self):
        """Test CSV nomina importing with data in OAI CSV form without person data.

        Trying: valid CSV
        Expecting: 0 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("FRAD003_oai_no_person.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertFalse(es_docs)

    def test_esdocs_nominarecord(self):
        """Test OAI nomina standard importing.


        Trying: import 23 NominaRecords one of which is duplicated
        Expecting: ES documents are generated as expected
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("Landes_RM_normalise.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="RM")
            self.assertEqual(22, len(es_docs))
            stable_id = "d0d3c2e7cc1c96232f942996a593354891cc5fbb"
            es_doc = [doc for doc in es_docs if doc["_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "_id": stable_id,
                "_index": "dummy_nomina",
                "_op_type": "index",
                "_source": {
                    "absolute_url": "https://testing.cubicweb/basedenoms/d0d3c2e7cc1c96232f942996a593354891cc5fbb",  # noqa
                    "act_date": None,
                    "act_number": "15",
                    "act_type": "RM",
                    "additional_info": None,
                    "alltext": "R P 392 Ne sait ni lire ni écrire homme Matricule militaire Mont-de-Marsan Landes "  # noqa
                    "France Canenx (Canenx-et-Réaut)",
                    "agent": [],
                    "birth_commune": "Canenx (Canenx-et-Réaut)",
                    "birth_country": "France",
                    "birth_date": "1867",
                    "birth_dates": {"gte": "1867", "lte": "1867"},
                    "birth_department": "Landes",
                    "cote": "R P 392",
                    "creation_date": es_doc["_source"]["creation_date"],
                    "death_date": None,
                    "death_dates": None,
                    "event_commune": "Mont-de-Marsan",
                    "event_country": "France",
                    "event_date": "1887",
                    "event_dates": {"gte": "1887", "lte": "1887"},
                    "event_department": "Landes",
                    "event_year": "1887",
                    "forenames": ["Pierre"],
                    "gender": "h",
                    "historical_context": None,
                    "instruction": "0",
                    "mention_mpf": None,
                    "modification_date": entity_data["modification_date"],
                    "names": ["Béton"],
                    "notice_id": "FRAD040_16",
                    "oai_id": None,
                    "occupations": ["domestique"],
                    "occupations_index": ["domestique"],
                    "recruitment_commune": "Mont-de-Marsan",
                    "recruitment_country": "France",
                    "recruitment_date": "1887",
                    "recruitment_dates": {"gte": "1887", "lte": "1887"},
                    "recruitment_department": "Landes",
                    "residence_commune": "Canenx (Canenx-et-Réaut)",
                    "residence_country": "France",
                    "residence_department": "Landes",
                    "service": entity_data["service"],
                    "source_url": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a252be",  # noqa
                    "stable_id": "d0d3c2e7cc1c96232f942996a593354891cc5fbb",
                    "title": "Béton, Pierre",
                },
            }
            self.assertEqual(expected, es_doc)

    def test_import_mariage_nominarecords(self):
        """Test CSV M standard importing.

        Trying: import 2O records from a valid CSV
        Expecting: 37 NominaRecords are created
            (one is ignored because it has wrong type: "Décès", one without wife data)
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("modele_etat-civil_mariage.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="M")
            self.assertEqual(37, len(es_docs))

            # notice 3E13/133 has document type Décès and is ignored
            stable_id = "33b92b1bc6ba4a8f7d17b3a3ba36270c7db638f3"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            self.assertEqual("RAILLAN, Charles", es_nomina.dc_title())

            husband_stable_id = "ba033e0153bf0be7b3d0e6ab345fee4047f5e84d"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == husband_stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, husband_stable_id, es_doc)
            husband = es_nomina.data["entity"]

            self.assertEqual("FLOURY, Arthur", husband["title"])
            self.assertEqual("m", husband["gender"])
            self.assertEqual(["Arthur"], husband["forenames"])
            self.assertEqual(["FLOURY"], husband["names"])

            wife_stable_id = "8175f23a42121f958680be68878f8a69e7a4a11b"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == wife_stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, wife_stable_id, es_doc)
            wife = es_nomina.data["entity"]

            self.assertEqual("DHIEUX, Eugènie Joséphine", wife["title"])

            self.assertEqual("f", wife["gender"])
            self.assertEqual(["Eugènie Joséphine"], wife["forenames"])
            self.assertEqual(["DHIEUX"], wife["names"])
            self.assertEqual("m_ba033e0153bf0be7b3d0e6ab345fee4047f5e84d", wife["household_id"])
            for entity_data in (husband, wife):
                self.assertEqual(
                    "m_ba033e0153bf0be7b3d0e6ab345fee4047f5e84d", husband["household_id"]
                )
                self.assertEqual("Mariage", nomina_translate_codetype(husband["act_type"]))
                self.assertEqual("M", normalized_doctype_code(husband["act_type"]))
                self.assertEqual("M", es_nomina.processed_acte_type_code)
                self.assertEqual("3E13/19", husband["notice_id"])
                self.assertEqual("11", husband["act_number"])

                # dates
                self.assertEqual("1894", entity_data["event_year"])
                self.assertEqual("01/03/1895", entity_data["act_date"])
                self.assertEqual("24/01/1894", entity_data["event_date"])
                self.assertEqual("", format_date_location(cnx, entity_data, "birth"))
                self.assertEqual("", format_date_location(cnx, entity_data, "death"))
                self.assertEqual(None, entity_data["occupations"])
                self.assertEqual(None, entity_data["instruction"])
                self.assertEqual(
                    "24/01/1894; Antibes (Alpes-Maritimes)",
                    format_date_location(cnx, entity_data, "event"),
                )
                self.assertEqual("01/03/1895", entity_data["act_date"])
                self.assertEqual("30000000000000", entity_data["cote"])
                self.assertEqual("divorce", entity_data["additional_info"])
                self.assertEqual(
                    "https://archives.ville-antibes.fr/4DCGI/Web_RegistreActes3E13xzx19*141/1/ILUMP99999",  # noqa
                    entity_data["source_url"],
                )

    def test_delete_mariage_nominarecords(self):
        """Test OAI nomina standard importing.

        Trying: import 30 new NominaRecords and reimport same data with 1 NominaRecord deleted
         Expecting: 21 NominaRecords are found after reimport
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("modele_etat-civil_mariage.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="M")
            self.assertEqual(37, len(es_docs))
            husband_stable_id = "ba033e0153bf0be7b3d0e6ab345fee4047f5e84d"
            wife_stable_id = "8175f23a42121f958680be68878f8a69e7a4a11b"
            for stable_id in (husband_stable_id, wife_stable_id):
                self.assertTrue(
                    [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
                )
            # reimport with1 deleted record
            filepath = self.csv_filepath("modele_etat-civil_mariage_deleted.csv")
            reader = CSVNominaReader(self.readerconfig, cnx, self.service.code)
            es_docs = list(reader.import_records(S3BfssStorageMixIn(), filepath, doctype="M"))
            self.assertEqual(35, len(es_docs))
            for stable_id in (husband_stable_id, wife_stable_id):
                self.assertFalse(
                    [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
                )
            self.assertEqual([(husband_stable_id, "M")], reader.nomina_records_to_delete)

    def test_esdoc_mariage_nominarecord(self):
        """Test ES indexation for CSV M standard importing.


        Trying: import Mariage NominaRecords
        Expecting: one ES documents are generated as expected
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("modele_etat-civil_mariage.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="M")
            stable_id = "ba033e0153bf0be7b3d0e6ab345fee4047f5e84d"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "_id": stable_id,
                "_index": "dummy_nomina",
                "_op_type": "index",
                "_source": {
                    "absolute_url": f"https://testing.cubicweb/basedenoms/{stable_id}",  # noqa
                    "act_date": "01/03/1895",
                    "act_number": "11",
                    "act_type": "M",
                    "additional_info": "divorce",
                    "alltext": "30000000000000 divorce non renseigné Mariage Antibes Alpes-Maritimes",  # noqa
                    "agent": [],
                    "birth_date": None,
                    "birth_dates": None,
                    "cote": "30000000000000",
                    "creation_date": entity_data["creation_date"],
                    "death_date": None,
                    "death_dates": None,
                    "event_commune": "Antibes",
                    "event_country": None,
                    "event_date": "24/01/1894",
                    "event_dates": {"gte": "1894", "lte": "1894"},
                    "event_department": "Alpes-Maritimes",
                    "event_year": "1894",
                    "forenames": ["Arthur"],
                    "gender": "m",
                    "historical_context": None,
                    "household_id": f"m_{stable_id}",
                    "instruction": None,
                    "mention_mpf": None,
                    "modification_date": entity_data["modification_date"],
                    "names": ["FLOURY"],
                    "notice_id": "3E13/19",
                    "oai_id": None,
                    "occupations": None,
                    "occupations_index": None,
                    "recruitment_date": None,
                    "recruitment_dates": None,
                    "service": entity_data["service"],
                    "source_url": "https://archives.ville-antibes.fr/4DCGI/Web_RegistreActes3E13xzx19*141/1/ILUMP99999",  # noqa
                    "stable_id": stable_id,
                    "title": "FLOURY, Arthur",
                },
            }
            self.assertEqual(expected, es_doc)

    def test_import_birth_nominarecords(self):
        """Test CSV B standard importing.

        Trying: import 12 records from a valid CSV
        Expecting: 11 NominaRecords are created
            (one is ignored because it has wrong type: "Décès")
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("modele_etat-civil_naissance.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="B")
            self.assertEqual(11, len(es_docs))
            # notice 347W1/60260 has document type Décès and is ignored
            stable_id = "b2eecffb58f2e28d3cc9d17d186830a671797368"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            self.assertEqual("BN", es_nomina.processed_acte_type_code)
            self.assertEqual("BN", entity_data["act_type"])

            self.assertEqual("ANGO, Antoinette Rose Alix", es_nomina.dc_title())
            self.assertEqual("2E10/15558", entity_data["notice_id"])
            self.assertEqual("22", entity_data["act_number"])  # nro

            # dates
            self.assertEqual("1817", entity_data["event_year"])  # act_year
            self.assertEqual("05/03/1869", entity_data["act_date"])
            self.assertEqual("20/01/1817", entity_data["event_date"])
            self.assertEqual(
                "20/01/1817; Antibes (Alpes-Maritimes)",
                format_date_location(cnx, entity_data, "event"),
            )  # should be birth
            self.assertEqual(
                "Antibes (Alpes-Maritimes)", format_event_location(entity_data, "event")
            )  # should be birth
            self.assertEqual(None, entity_data["birth_date"])
            self.assertEqual("", format_date_location(cnx, entity_data, "birth"))
            self.assertEqual("rectification patronyme", entity_data["additional_info"])
            self.assertEqual(
                "https://archives.ville-antibes.fr/4DCGI/Web_RegistreActes2E10xzx15558*259/2/ILUMP99999",  # noqa
                entity_data["source_url"],
            )

    def test_esdoc_birth_nominarecord(self):
        """Test ES indexation for CSV B standard importing.


        Trying: import Birth NominaRecords
        Expecting: one ES document is generated as expected
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("modele_etat-civil_naissance.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="B")
            stable_id = "223c9b412839f401309eb373a57b551b0d6b50b6"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "_id": "223c9b412839f401309eb373a57b551b0d6b50b6",
                "_index": "dummy_nomina",
                "_op_type": "index",
                "_source": {
                    "absolute_url": "https://testing.cubicweb/basedenoms/223c9b412839f401309eb373a57b551b0d6b50b6",  # noqa
                    "act_date": "31/03/1869",
                    "act_number": "31",
                    "act_type": "BN",
                    "additional_info": "enfant naturel",
                    "alltext": "20000000000 enfant naturel non renseigné Baptême ou naissance "
                    "Antibes Alpes-Maritimes",
                    "agent": [],
                    "birth_date": None,
                    "birth_dates": None,
                    "cote": "20000000000",
                    "creation_date": entity_data["creation_date"],
                    "death_date": None,
                    "death_dates": None,
                    "event_commune": "Antibes",
                    "event_country": None,
                    "event_date": "30/03/1869",
                    "event_dates": {"gte": "1869", "lte": "1869"},
                    "event_department": "Alpes-Maritimes",
                    "event_year": "1869",
                    "forenames": ["Claire"],
                    "gender": "i",
                    "historical_context": None,
                    "instruction": None,
                    "mention_mpf": None,
                    "modification_date": entity_data["modification_date"],
                    "names": ["FERRALLY"],
                    "notice_id": "2E10/15567",
                    "oai_id": None,
                    "occupations": None,
                    "occupations_index": None,
                    "recruitment_date": None,
                    "recruitment_dates": None,
                    "service": entity_data["service"],
                    "source_url": "https://archives.ville-antibes.fr/4DCGI/Web_RegistreActes2E10xzx15567*262/1/ILUMP99999",  # noqa
                    "stable_id": "223c9b412839f401309eb373a57b551b0d6b50b6",
                    "title": "FERRALLY, Claire",
                },
            }
            self.assertEqual(expected, es_doc)

    def test_import_death_nominarecords(self):
        """Test CSV D standard importing.

        Trying: import 12 records from a valid CSV
        Expecting: 12 NominaRecords are created
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("modele_etat-civil_deces.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="S")
            self.assertEqual(12, len(es_docs))
            stable_id = "55654ddf334784a4621daef060aa4a2d40b062c3"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            self.assertEqual("S", es_nomina.processed_acte_type_code)
            self.assertEqual("S", entity_data["act_type"])

            self.assertEqual("BELUSIO, Gérardo", es_nomina.dc_title())

            self.assertEqual("4E25/73247", entity_data["notice_id"])
            self.assertEqual("258 bis", entity_data["act_number"])  # nro

            # dates
            self.assertEqual("1946", entity_data["event_year"])  # act_year
            self.assertEqual("12/04/1960", entity_data["act_date"])
            self.assertEqual(
                "Antibes (Alpes-Maritimes)", format_event_location(entity_data, "event")
            )  # should be death
            self.assertEqual(
                "28/10/1946; Antibes (Alpes-Maritimes)",
                format_date_location(cnx, entity_data, "event"),
            )  # should be death
            self.assertEqual("", format_date_location(cnx, entity_data, "death"))
            self.assertEqual("transcription", entity_data["additional_info"])
            self.assertEqual(
                "https://archives.ville-antibes.fr/4DCGI/Web_RegistreActes4E25xzx73247*176/1/ILUMP99999",  # noqa
                entity_data["source_url"],
            )

    def test_esdoc_death_nominarecord(self):
        """Test ES indextation for CSV D standard importing.

        Trying: import Death NominaRecords
        Expecting: one ES document is generated as expected
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("modele_etat-civil_deces.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="S")
            stable_id = "c873780f29f71e0ad8cfcec3d65a50d88549534c"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "_op_type": "index",
                "_index": "dummy_nomina",
                "_id": "c873780f29f71e0ad8cfcec3d65a50d88549534c",
                "_source": {
                    "absolute_url": "https://testing.cubicweb/basedenoms/c873780f29f71e0ad8cfcec3d65a50d88549534c",  # noqa
                    "act_date": "19/12/1937",
                    "act_number": "299",
                    "act_type": "S",
                    "additional_info": "mort-né",
                    "alltext": "4E+021 mort-né non renseigné Sépulture ou décès Antibes Alpes-Maritimes",  # noqa
                    "agent": [],
                    "birth_date": None,
                    "birth_dates": None,
                    "cote": "4E+021",
                    "creation_date": entity_data["creation_date"],
                    "death_date": None,
                    "death_dates": None,
                    "event_commune": "Antibes",
                    "event_country": None,
                    "event_date": "18/12/1937",
                    "event_dates": {"gte": "1937", "lte": "1937"},
                    "event_department": "Alpes-Maritimes",
                    "event_year": "1937",
                    "forenames": [],
                    "gender": "i",
                    "historical_context": None,
                    "instruction": None,
                    "mention_mpf": None,
                    "modification_date": entity_data["modification_date"],
                    "names": ["BELBEOCH"],
                    "notice_id": "4E21/41046",
                    "oai_id": None,
                    "occupations": None,
                    "occupations_index": None,
                    "recruitment_date": None,
                    "recruitment_dates": None,
                    "service": entity_data["service"],
                    "source_url": "https://archives.ville-antibes.fr/4DCGI/Web_RegistreActes4E21xzx41046*253/1/ILUMP99999",  # noqa
                    "stable_id": "c873780f29f71e0ad8cfcec3d65a50d88549534c",
                    "title": "BELBEOCH, ?",
                },
            }
            self.assertEqual(expected, es_doc)


if __name__ == "__main__":
    unittest.main()
