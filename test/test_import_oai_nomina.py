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

import io

from cubicweb_web.devtools.testlib import WebCWTC
from lxml import etree

import unittest
import os
import os.path

from cubicweb_francearchives.dataimport import oai
from cubicweb_francearchives.dataimport import (
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.oai_nomina import (
    compute_nomina_stable_id,
    build_persons,
)
from cubicweb_francearchives.dataimport.csv_nomina.nomina import CSVNominaReader
from cubicweb_francearchives.entities.nomina import (
    NominaIndexJsonDataSerializable,
    format_date_location,
    format_event_location,
    nominarecord_from_esdoc,
)
from cubicweb_francearchives.testutils import (
    NominaImportMixin,
    PostgresTextMixin,
    OaiSickleMixin,
)
from cubicweb_francearchives.storage import S3BfssStorageMixIn

from pgfixtures import setup_module, teardown_module  # noqa


class OaiNominaUtilsTest(WebCWTC):
    def test_compute_nomina_stable_id_with_service_code(self):
        expected = "299648bc990b977d5ee1852ffad08d5840b36985"
        self.assertEqual(expected, compute_nomina_stable_id("FRAD003", "FRAD003_34"))

    def test_compute_nomina_stable_id_without_noservice(self):
        expected = "299648bc990b977d5ee1852ffad08d5840b36985"
        self.assertEqual(expected, compute_nomina_stable_id("FRAD003", "34"))


class OaiNominaImportTC(PostgresTextMixin, NominaImportMixin, OaiSickleMixin, WebCWTC):
    def filepath(self, filename=None):
        filename = filename or self.filename
        assert filename is not None
        return self.datapath(os.path.join("oai_nomina", filename))

    def create_repo(self, cnx, url):
        return cnx.create_entity(
            "OAIRepository",
            name="{} repo".format(self.service.code),
            service=self.service,
            url=url,
        )

    @property
    def path(self):
        return "{nomina_services_dir}/{code}/oaipmh/".format(
            nomina_services_dir=self.config["nomina-services-dir"], **self.service_infos
        )

    def setup_database(self):
        super(OaiNominaImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service",
                name="Département des Ardennes",
                code="FRAD008",
                category="DS",
            )
            cnx.commit()
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(self.service.code, services_map)

    def test_build_persons(self):
        """
        Trying: parse a valid OAI-PMH recorde
        Expecting: persons data are build as expected
        """
        document = io.StringIO(
            """
<nomina:document xmlns:nomina="http://www.france-genealogie.fr/ns/nomina/1.0"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://www.france-genealogie.fr/ns/nomina/1.0 genealogie1.4.xsd"
id="6" uri="http://bla.org/6">
    <nomina:personne>
     <nomina:nom>MARGUERITAT</nomina:nom>
     <nomina:prenoms>Jean</nomina:prenoms>
     <nomina:prenoms>Pierre</nomina:prenoms>
    </nomina:personne>
    <nomina:personne>
     <nomina:nom>PATUREAU</nomina:nom>
    <nomina:prenoms>Roberte Marie Jacqueline</nomina:prenoms>
    </nomina:personne>
    <nomina:localisation code="RM">
     <nomina:precision/>
    </nomina:localisation>
    <nomina:date annee="1868">1868</nomina:date>
</nomina:document>
                                     """
        )
        tree = etree.parse(document)
        self.assertCountEqual(
            build_persons(tree.getroot()),
            [
                {"f": "Jean Pierre", "n": "MARGUERITAT"},
                {"f": "Roberte Marie Jacqueline", "n": "PATUREAU"},
            ],
        )

    def test_harvest_nominarecords(self):
        """Test OAI nomina harvesting.

        Trying: valid OAI-PMH
        Expecting: import and create 7 NominaRecords
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_simple.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = f"file://{self.filepath()}"
            filepaths = oai.harvest_oai_nomina(
                cnx, url, service_infos, dry_run=True, csv_rows_limit=3
            )
            filpathes = sorted(filepaths)
            self.assertEqual(3, len(filpathes))
            for i, filepath in enumerate(filpathes, start=1):
                self.assertRegex(
                    filepath,
                    r"tmp/FRAD008/oaipmh/FRAD008_nomina_\d+_{i}.csv".format(i=i),
                )

    def test_import_nominarecords(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: import and create 7 NominaRecords created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_simple.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepath = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)[0]
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            es_docs = self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertEqual(7, len(es_docs))
            expected_titles = [
                "Ratier, Isidore Louis Alexandre",
                "Suquez, Léon Gustave; Suquez, Jean Gustave",
                "Christel, Alcide Fernand",
                "Mathieu, Jean Louis Auguste",
                "Buzy, Léon Charles",
                "Croïet, Alexandre Théophile",
                "Renel, Jules Nicolas",
            ]
            for doc in es_docs:
                self.assertEqual(doc["_source"]["act_type"], "RM")
                # self.assertEqual(nomina.acte_year, nomina.get_dates(nomina.doctype_code))
                self.assertIn(doc["_source"]["title"], expected_titles)
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "5")
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "absolute_url": "https://testing.cubicweb/basedenoms/c21e8a4dafe0d22cf14a7215adecf40e2f47ba5e",  # noqa
                "act_date": None,
                "act_number": "53",
                "act_type": "RM",
                "additional_info": None,
                "agent": [],
                "alltext": "1R 013 Sait lire et écrire homme Matricule militaire Mézières Ardennes France Gespunsart",  # noqa
                "birth_commune": "Gespunsart",
                "birth_country": None,
                "birth_date": "1851",
                "birth_dates": {"gte": "1851", "lte": "1851"},
                "birth_department": "Ardennes",
                "cote": "1R 013",
                "creation_date": entity_data["creation_date"],
                "death_date": None,
                "death_dates": None,
                "event_commune": "Mézières",
                "event_country": "France",
                "event_date": "1871",
                "event_dates": {"gte": "1871", "lte": "1871"},
                "event_department": "Ardennes",
                "event_year": "1871",
                "forenames": ["Jean Louis Auguste"],
                "gender": "h",
                "historical_context": None,
                "instruction": "2",
                "mention_mpf": None,
                "modification_date": entity_data["modification_date"],
                "names": ["Mathieu"],
                "notice_id": None,
                "oai_id": "5",
                "occupations": ["charpentier"],
                "occupations_index": ["charpentier"],
                "recruitment_commune": "Mézières",
                "recruitment_country": "France",
                "recruitment_date": "1871",
                "recruitment_dates": {"gte": "1871", "lte": "1871"},
                "recruitment_department": "Ardennes",
                "residence_commune": "Gespunsart",
                "residence_country": None,
                "residence_department": "Ardennes",
                "service": entity_data["service"],
                "source_url": "https://archives.cd08.fr/ark:/75583/s005328744149810/532874414b2bd",
                "stable_id": "c21e8a4dafe0d22cf14a7215adecf40e2f47ba5e",
                "title": "Mathieu, Jean Louis Auguste",
            }
            self.assertEqual(expected, entity_data)
            self.assertEqual(entity_data["act_type"], "RM")
            self.assertEqual(
                "1871; Mézières (Ardennes, France)",
                format_date_location(cnx, entity_data, "event"),
            )
            self.assertEqual(
                "Gespunsart (Ardennes)", format_event_location(entity_data, "residence")
            )
            self.assertEqual(
                "1851; Gespunsart (Ardennes)",
                format_date_location(cnx, entity_data, "birth"),
            )
            self.assertEqual("", format_date_location(cnx, entity_data, "death"))
            adapter = es_nomina.data["main_props"]
            self.assertEqual("Sait lire et écrire", adapter["NMN_C_education"])
            self.assertEqual("charpentier", adapter["NMN_C_occupations"])
            # self.assertFalse(es_nomina.digitized)
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "888")
            # test MARGUERITAT is not imported (no doctype)
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "5121")
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
            self.assertFalse(es_doc)

    def test_import_mariage_nominarecords(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH

        Expecting: import and create 3 NominaRecords created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd85_simple.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad85_registres_mariage"  # noqa
            filepath = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)[0]
            self.assertTrue(self.fileExists(self.get_filepath_by_storage(filepath)))
            es_docs = self.import_filepath(cnx, filepath, doctype="OAI")
            self.assertEqual(6, len(es_docs))
            expected_titles = [
                "GORON, Etienne",
                "PAUTON, Mathurin",
                "BERTHOME, Henri",
                "BALANGER, Marie",
                "SORET, Marie",
                "JAGUENEAU, Hyacinthe",
            ]
            for doc in es_docs:
                self.assertEqual(doc["_source"]["act_type"], "M")
                self.assertIn(doc["_source"]["title"], expected_titles)
            # test one og the records
            oai_id = "oai:nomsdevendee.fr:4387519"
            stable_id = compute_nomina_stable_id(self.service_infos["code"], oai_id)
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            stable_id = "196e6e3e3781c1498313b41efc97b4d04c79f8b6"
            household = [
                doc["_source"]["stable_id"]
                for doc in es_docs
                if doc["_source"]["household_id"] == f"m_{stable_id}"
            ]
            self.assertEqual(2, len(household))

            expected = {
                "absolute_url": f"https://testing.cubicweb/basedenoms/{stable_id}",  # noqa
                "act_date": None,
                "act_number": None,
                "act_type": "M",
                "additional_info": None,
                "agent": [],
                "alltext": "non renseigné Mariage CHAILLÉ-LES-MARAIS Vendée France",
                "birth_date": None,
                "birth_dates": None,
                "cote": None,
                "creation_date": entity_data["creation_date"],
                "death_date": None,
                "death_dates": None,
                "event_commune": "CHAILLÉ-LES-MARAIS",
                "event_country": "France",
                "event_date": "08/02/1655",
                "event_dates": {"gte": "1655", "lte": "1655"},
                "event_department": "Vendée",
                "event_year": "1655",
                "forenames": ["Etienne"],
                "gender": "i",
                "historical_context": None,
                "household_id": f"m_{stable_id}",
                "instruction": None,
                "mention_mpf": None,
                "modification_date": entity_data["modification_date"],
                "names": ["GORON"],
                "notice_id": None,
                "oai_id": "oai:nomsdevendee.fr:4387519",
                "occupations": None,
                "occupations_index": None,
                "recruitment_date": None,
                "recruitment_dates": None,
                "service": entity_data["service"],
                "source_url": "http://nomsdevendee.fr/details.php?id=4387519",
                "stable_id": stable_id,
                "title": "GORON, Etienne",
            }
            self.assertEqual(expected, entity_data)
            self.assertEqual(
                "08/02/1655; CHAILLÉ-LES-MARAIS (Vendée, France)",
                format_date_location(cnx, entity_data, "event"),
            )
            self.assertEqual("", format_date_location(cnx, entity_data, "birth"))
            self.assertEqual("", format_date_location(cnx, entity_data, "death"))
            self.assertEqual("1655", entity_data["event_year"])  # act_year
            self.assertEqual(
                "http://nomsdevendee.fr/details.php?id=4387519",
                entity_data["source_url"],
            )

    def test_import_mariage_no_person(self):
        json_data = {"t": "M"}

        with self.admin_access.cnx() as cnx:
            data = NominaIndexJsonDataSerializable(cnx, json_data).process_json_data(
                "service_code", "identifiant"
            )
            self.assertEqual([], data)

    def test_import_mariage_one_person_without_gender(self):
        json_data = {"p": [{"f": "Mathurin", "n": "PAUTON"}], "t": "M"}

        with self.admin_access.cnx() as cnx:
            data = NominaIndexJsonDataSerializable(cnx, json_data).process_json_data(
                "service_code", "identifiant"
            )
            self.assertEqual(1, len(data))
            self.assertEqual("PAUTON, Mathurin", data[0]["title"])

    def test_import_mariage_one_person_with_gender(self):
        json_data = {"p": [{"f": "Mathurin", "n": "PAUTON", "g": "m"}], "t": "M"}

        with self.admin_access.cnx() as cnx:
            data = NominaIndexJsonDataSerializable(cnx, json_data).process_json_data(
                "service_code", "identifiant"
            )
            self.assertEqual(1, len(data))
            self.assertEqual("PAUTON, Mathurin", data[0]["title"])

    def test_import_mariage_two_person(self):
        json_data = {
            "p": [
                {"f": "Mathurin", "n": "PAUTON", "g": "m"},
                {"f": "Marie", "n": "SORET"},
            ],
            "t": "M",
        }

        with self.admin_access.cnx() as cnx:
            data = NominaIndexJsonDataSerializable(cnx, json_data).process_json_data(
                "service_code", "identifiant"
            )
            self.assertEqual(2, len(data))
            self.assertEqual("PAUTON, Mathurin", data[0]["title"])
            self.assertEqual("SORET, Marie", data[1]["title"])

    def test_import_mariage_three_person(self):
        json_data = {
            "p": [
                {"f": "Anna", "n": "PAUTON"},
                {"f": "Mathurin", "n": "PAUTON"},
                {"f": "Marie", "n": "SORET", "g": "f"},
            ],
            "t": "M",
        }

        with self.admin_access.cnx() as cnx:
            data = NominaIndexJsonDataSerializable(cnx, json_data).process_json_data(
                "service_code", "identifiant"
            )
            self.assertEqual(3, len(data))
            self.assertEqual("PAUTON, Anna", data[0]["title"])
            self.assertEqual("PAUTON, Mathurin", data[1]["title"])
            self.assertEqual("SORET, Marie", data[2]["title"])

    def test_import_wrong_namespace(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: do not import record with wrong namespace
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_wrong_namespace.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.assertEqual(0, len(filepaths))

    def test_import_no_doctype(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: do not import record without doctype
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_no_doctype.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.assertEqual(0, len(filepaths))

    def test_import_no_person_data(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: do not import record without person_data
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_no_person.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            self.assertEqual(0, len(filepaths))

    def test_deleted_nominarecord(self):
        """Test OAI nomina standard importing.

        Trying: valid OAI-PMH
        Expecting: import 10 NominaRecords with only 7 valid and delete one of them
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "archives_cd08_simple.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepaths = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)
            es_docs = self.import_filepath(cnx, filepaths[0], doctype="OAI")
            stable_id = compute_nomina_stable_id(self.service_infos["code"], "888")
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
            self.assertTrue(es_docs)
            self.filename = "archives_cd08_delete.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=nomina&set=ad08_registres_matricules"  # noqa
            filepath = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)[0]
            reader = CSVNominaReader(self.readerconfig, cnx, self.service.code)
            st = S3BfssStorageMixIn()
            filepath = oai.harvest_oai_nomina(cnx, url, self.service_infos, dry_run=False)[0]

            es_docs = list(reader.import_records(st, filepath, doctype="OAI"))
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
            self.assertFalse(es_doc)
            self.assertEqual([(stable_id, "OAI")], reader.nomina_records_to_delete)


if __name__ == "__main__":
    unittest.main()
