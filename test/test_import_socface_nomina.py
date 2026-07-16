# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2026
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
from cubicweb_francearchives.dataimport.csv_nomina.socface import CSVNominaSocfaceReader
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


class CSVNominaSocfaceImportTC(PostgresTextMixin, NominaImportMixin, WebCWTC):
    def csv_filepath(self, filepath):
        return self.get_or_create_imported_filepath(f"nomina/{filepath}")

    def setup_database(self):
        super().setup_database()
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

    def test_import_socface_nominarecords(self):
        """Test CSV SOCFACE standard importing.

        Trying: import 11 records from a valid CSV
        Expecting: 10 NominaRecords are processed: the last record has no id_arkindex ni notice_id
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("socface_nomina.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="SOCFACE", delimiter="\t")
            self.assertEqual(10, len(es_docs))
            stable_id = "4e5929b457f5395860b0c92ac0df11ab99499355"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            es_nomina = nominarecord_from_esdoc(cnx, stable_id, es_doc)
            entity_data = es_nomina.data["entity"]
            expected = {
                "absolute_url": "https://testing.cubicweb/basedenoms/4e5929b457f5395860b0c92ac0df11ab99499355",  # noqa
                "act_type": "RP",
                "additional_info": "",
                "age": "55",
                "alltext": "femme Recensement de la population Dordogne Sarlat-la-Canéda  France",
                "birth_date": None,
                "birth_place": "",
                "civil_status": "",
                "cote": "FRAD024_6MI140",
                "creation_date": entity_data["creation_date"],
                "doc_page_line_id": "56-2 ; 2",
                "employer": "",
                "event_commune": "Sarlat-la-Canéda ",
                "event_country": "France",
                "event_date": "1886",
                "event_dates": {"gte": "1886", "lte": "1886"},
                "event_department": "Dordogne",
                "event_year": "1886",
                "forenames": ["Marie"],
                "gender": "f",
                "household_id": "31482_775",
                "household_role": "femme",
                "id_arkindex": "fc03d38e-c76c-4c57-996e-fe1e48f700e8",
                "modification_date": entity_data["modification_date"],
                "names": ["Leborderie"],
                "nationality": "française",
                "notice_id": "",
                "occupations": ["sp"],
                "occupations_index": ["s.p."],
                "service": self.service.eid,
                "source_url": "",
                "stable_id": "4e5929b457f5395860b0c92ac0df11ab99499355",
                "teklia_url": "https://europe.iiif.teklia.com/iiif/2/frad024%2Frecensements_6_MI%2FFRAD024_6MI140%2FFRAD024_6MI140_0764.JPG",  # noqa
                "title": "Leborderie, Marie",
            }
            self.maxDiff = None
            self.assertEqual(expected, entity_data)
            self.assertEqual("Leborderie, Marie", es_nomina.dc_title())
            self.assertEqual(
                "Recensement de la population", nomina_translate_codetype(entity_data["act_type"])
            )
            self.assertEqual("RP", normalized_doctype_code(entity_data["act_type"]))
            self.assertEqual("RP", es_nomina.processed_acte_type_code)
            # dates
            self.assertEqual("1886", entity_data["event_year"])
            self.assertEqual("1886", entity_data["event_date"])
            self.assertEqual(
                "1886; Sarlat-la-Canéda  (Dordogne, France)",
                format_date_location(cnx, entity_data, "event"),
            )
            self.assertEqual(
                "Sarlat-la-Canéda  (Dordogne, France)",
                format_event_location(entity_data, "event"),
            )
            self.assertEqual("", format_date_location(cnx, entity_data, "birth"))
            self.assertEqual("", format_date_location(cnx, entity_data, "death"))
            self.assertNotIn(["sp"], entity_data["occupations"])
            for attr in ("instruction", "act_date", "act_number"):
                self.assertNotIn(attr, entity_data)
            self.assertEqual("FRAD024_6MI140", entity_data["cote"])
            self.assertEqual("", entity_data["additional_info"])

    def test_delete_socface_nominarecords(self):
        """Test SOCFACE format data standard importing.

        Trying: import 10 new NominaRecords and reimport same data with 1 NominaRecord deleted
        Expecting: 9 NominaRecords are found after reimport
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("socface_nomina.csv")
            es_docs = self.import_filepath(cnx, filepath, doctype="SOCFACE", delimiter="\t")
            # the last record has no id_arkindex ni notice_id
            self.assertEqual(10, len(es_docs))

            stable_id = "4e5929b457f5395860b0c92ac0df11ab99499355"
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id][0]
            # reimport with deleted fc03d38e-c76c-4c57-996e-fe1e48f700e8 id_arkindex
            filepath = self.csv_filepath("socface_nomina_deleted.csv")
            reader = CSVNominaSocfaceReader(self.readerconfig, cnx, self.service.code)
            es_docs = list(
                reader.import_records(
                    S3BfssStorageMixIn(), filepath, doctype="SOCFACE", delimiter="\t"
                )
            )
            self.assertEqual(10, len(es_docs))
            es_doc = [doc for doc in es_docs if doc["_source"]["stable_id"] == stable_id]
            self.assertFalse(es_doc)
            es_doc = [
                doc
                for doc in es_docs
                if doc["_source"]["id_arkindex"] == "30882b3e-2419-45ce-ad9f-fc71f694a2e2"
            ][0]
            self.assertEqual([(stable_id, "RP")], reader.nomina_records_to_delete)


if __name__ == "__main__":
    unittest.main()
