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
# data to be ensured and, more generally, to use and operate it in
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.
#

import unittest
from unittest import mock

from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.dataimport import (
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.csv_nomina.nomina import (
    CSVNominaUpdateReader,
    DEFAULT_EVENT_COUNTRY,
)
from cubicweb_francearchives.storage import S3BfssStorageMixIn
from cubicweb_francearchives.testutils import (
    NominaImportMixin,
    PostgresTextMixin,
)

from pgfixtures import setup_module, teardown_module  # noqa


def create_mock_es_client():
    """Create a mock Elasticsearch client."""
    mock_es = mock.Mock()
    mock_es.ping.return_value = True
    mock_es.mget.return_value = {"docs": []}
    return mock_es


class CSVNominaUpdateReaderTC(PostgresTextMixin, NominaImportMixin, WebCWTC):
    """Test CSVNominaUpdateReader for SOCFACE partial updates.

    Note: These tests focus on validation and ES interaction.
    The actual data transformation for SOCFACE format requires
    a separate implementation (similar to CSVNominaSocfaceReader).
    """

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

    def test_check_update_fieldnames_valid(self):
        """Test fieldnames validation with valid CSV columns.

        Trying: validate CSV with required and allowed columns
        Expecting: no errors
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            fieldnames = [
                "Identifiant Arkindex",
                "Nom de famille",
                "Prénoms",
                "Profession (source)",
            ]
            errors = reader.check_update_fieldnames(fieldnames)
            self.assertEqual(0, len(errors))

    def test_check_update_fieldnames_missing_required(self):
        """Test fieldnames validation missing required column.

        Trying: validate CSV without "Identifiant Arkindex"
        Expecting: error about missing required column
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            fieldnames = [
                "Nom de famille",
                "Prénoms",
                "Profession (source)",
            ]
            errors = reader.check_update_fieldnames(fieldnames)
            self.assertEqual(1, len(errors))
            self.assertTrue(any("Required column" in e for e in errors))

    def test_check_update_fieldnames_no_update_columns(self):
        """Test fieldnames validation with no update columns.

        Trying: validate CSV with only required column
        Expecting: error about missing update columns
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            fieldnames = ["Identifiant Arkindex"]
            errors = reader.check_update_fieldnames(fieldnames)
            self.assertEqual(1, len(errors))
            self.assertTrue(any("at least one update column" in e.lower() for e in errors))

    def test_check_update_fieldnames_invalid_columns(self):
        """Test fieldnames validation with invalid columns.

        Trying: validate CSV with forbidden columns
        Expecting: error about invalid columns
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            fieldnames = [
                "Identifiant Arkindex",
                "Nom de famille",
                "Colonne interdite",
            ]
            errors = reader.check_update_fieldnames(fieldnames)
            self.assertEqual(1, len(errors))
            self.assertTrue(any("Invalid columns" in e for e in errors))

    def test_update_socface_wrong_doctype(self):
        """Test SOCFACE update with wrong doctype.

        Trying: update with doctype other than "SOCFACE"
        Expecting: import is aborted, error logged
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("socface_update_valid.csv")

            mock_es = create_mock_es_client()

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
                st = S3BfssStorageMixIn()

                es_docs = list(reader.import_records(st, filepath, doctype="RM", delimiter="\t"))

                # Verify generator returns empty list when exhausted
                self.assertEqual([], es_docs)
                self.assertEqual(0, reader.processed_records)

    def test_update_socface_missing_required_column(self):
        """Test SOCFACE update validation with missing required column.

        Trying: validate CSV missing "Identifiant Arkindex"
        Expecting: validation error about missing required column
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            fieldnames = [
                "Nom de famille",
                "Prénoms",
                "Profession (source)",
            ]
            errors = reader.check_update_fieldnames(fieldnames)
            self.assertEqual(1, len(errors))
            self.assertTrue(any("Required column" in e for e in errors))

    def test_update_socface_no_update_columns(self):
        """Test SOCFACE update validation with no update columns.

        Trying: validate CSV containing only "Identifiant Arkindex"
        Expecting: validation error about missing update columns
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            fieldnames = ["Identifiant Arkindex"]
            errors = reader.check_update_fieldnames(fieldnames)
            self.assertEqual(1, len(errors))
            self.assertTrue(any("at least one update column" in e.lower() for e in errors))

    def test_update_socface_invalid_columns(self):
        """Test SOCFACE update validation with invalid columns.

        Trying: validate CSV with forbidden columns
        Expecting: validation error about invalid columns
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            fieldnames = [
                "Identifiant Arkindex",
                "Nom de famille",
                "Colonne interdite",
            ]
            errors = reader.check_update_fieldnames(fieldnames)
            self.assertEqual(1, len(errors))
            self.assertTrue(any("Invalid columns" in e for e in errors))

    def test_update_socface_es_unavailable(self):
        """Test SOCFACE update when ES is unavailable.

        Trying: update when ES connection fails
        Expecting: import is aborted, no documents processed
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("socface_update_valid.csv")

            mock_es = create_mock_es_client()
            mock_es.ping.return_value = False

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
                st = S3BfssStorageMixIn()

                es_docs = list(
                    reader.import_records(st, filepath, doctype="SOCFACE", delimiter="\t")
                )

                self.assertEqual(0, len(es_docs))
                self.assertEqual(0, reader.processed_records)

    def test_update_socface_validation_errors_returns_none(self):
        """Test that import_records returns empty list on CSV validation errors.

        Trying: import with invalid CSV columns
        Expecting: import_records returns empty generator (exhausts to [])
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.csv_filepath("socface_update_invalid_columns.csv")
            st = S3BfssStorageMixIn()

            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

            # Call import_records with invalid columns - returns generator
            result = list(reader.import_records(st, filepath, doctype="SOCFACE", delimiter="\t"))

            # Verify generator exhausts to empty list (not None)
            self.assertEqual([], result)

    def test_bulk_check_documents_exist(self):
        """Test bulk_check_documents_exist method.

        Trying: check existence of multiple documents
        Expecting: returns list of existing stable_ids
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()
            mock_es.mget.return_value = {
                "docs": [
                    {"found": True},
                    {"found": False},
                    {"found": True},
                ]
            }

            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            stable_ids = ["id1", "id2", "id3"]

            result = reader.bulk_check_documents_exist(mock_es, stable_ids)

            self.assertEqual(["id1", "id3"], result)
            mock_es.mget.assert_called_once_with(
                index=self.readerconfig["nomina-index-name"], body={"ids": stable_ids}
            )

    def test_bulk_check_documents_exist_empty(self):
        """Test bulk_check_documents_exist with empty list.

        Trying: check existence with no IDs
        Expecting: returns empty list
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()

            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

            result = reader.bulk_check_documents_exist(mock_es, [])

            self.assertEqual([], result)
            mock_es.mget.assert_not_called()

    def test_bulk_check_documents_exist_error(self):
        """Test bulk_check_documents_exist with ES error.

        Trying: check existence when ES raises exception
        Expecting: returns empty list (fallback)
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()
            mock_es.mget.side_effect = Exception("ES error")

            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)
            stable_ids = ["id1", "id2"]

            result = reader.bulk_check_documents_exist(mock_es, stable_ids)

            self.assertEqual([], result)

    def test_build_es_doc_update_format(self):
        """Test build_es_doc produces correct update format.

        Trying: build ES document for update
        Expecting: _op_type is "update" with "doc" field
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

                values = {
                    "stable_id": "test_stable_id",
                    "json_data": '{"p": [{"n": "Test"}], "t": "RP"}',
                }

                es_doc = reader.build_es_doc(values)

                self.assertEqual("update", es_doc["_op_type"])
                self.assertEqual(self.readerconfig["nomina-index-name"], es_doc["_index"])
                self.assertEqual("test_stable_id", es_doc["_id"])
                self.assertIn("doc", es_doc)

    def test_build_es_source_modification_date(self):
        """Test build_es_source includes modification_date.

        Trying: build ES source for update
        Expecting: modification_date present
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

                attrs = {
                    "stable_id": "test_stable_id",
                    "json_data": '{"p": [{"n": "Test"}], "t": "RP"}',
                }

                es_source = reader.build_es_source(attrs)

                self.assertIn("modification_date", es_source)
                self.assertEqual(self.service.eid, es_source["service"])
                self.assertEqual("test_stable_id", es_source["stable_id"])

    def test_build_es_source_for_update_includes_service(self):
        """Test build_es_source_for_update includes service field.

        Trying: build ES source for update
        Expecting: service field is present with correct eid
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

                attrs = {
                    "stable_id": "test_service",
                    "json_data": '{"p": [{"n": "Test"}], "t": "RP"}',
                }
                es_source = reader.build_es_source_for_update(attrs)

                # Verify service field exists and has correct value
                self.assertIn("service", es_source)
                self.assertEqual(self.service.eid, es_source["service"])

    def test_build_es_source_for_update_event_country_single_field(self):
        """Test event_country is set with single event field.

        Trying: build ES source with one event field
        Expecting: event_country is set to "France"
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

                # Test with only event_place (maps to event_commune)
                attrs = {
                    "stable_id": "test1",
                    "json_data": '{"p": [{"n": "Test"}], "t": "RP"}',
                    "event_place": "Paris",
                }
                es_source = reader.build_es_source_for_update(attrs)
                self.assertEqual(DEFAULT_EVENT_COUNTRY, es_source.get("event_country"))
                self.assertEqual("Paris", es_source.get("event_commune"))

                # Test with only event_department
                attrs = {
                    "stable_id": "test2",
                    "json_data": '{"p": [{"n": "Test"}], "t": "RP"}',
                    "event_department": "Rhône",
                }
                es_source = reader.build_es_source_for_update(attrs)
                self.assertEqual(DEFAULT_EVENT_COUNTRY, es_source.get("event_country"))
                self.assertEqual("Rhône", es_source.get("event_department"))

                # Test with only event_commune
                attrs = {
                    "stable_id": "test3",
                    "json_data": '{"p": [{"n": "Test"}], "t": "RP"}',
                    "event_commune": "Lyon",
                }
                es_source = reader.build_es_source_for_update(attrs)
                self.assertEqual(DEFAULT_EVENT_COUNTRY, es_source.get("event_country"))
                self.assertEqual("Lyon", es_source.get("event_commune"))

    def test_build_es_source_for_update_event_country_no_duplication(self):
        """Test event_country is set only once with multiple event fields.

        Trying: build ES source with multiple event fields
        Expecting: event_country appears exactly once (no duplicate assignment)
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

                # Test with all three event fields
                attrs = {
                    "stable_id": "test_multi",
                    "json_data": '{"p": [{"n": "Test"}], "t": "RP"}',
                    "event_place": "Paris",
                    "event_department": "Seine",
                    "event_commune": "Versailles",
                }
                es_source = reader.build_es_source_for_update(attrs)

                # Verify event_country is set
                self.assertEqual(DEFAULT_EVENT_COUNTRY, es_source.get("event_country"))

                # Verify event_country appears only once in the dict
                country_count = sum(
                    1 for k, v in es_source.items() if v == "France" and k == "event_country"
                )
                self.assertEqual(1, country_count)

                # Verify event fields are present (note: event_place maps to event_commune)
                self.assertEqual("Versailles", es_source.get("event_commune"))
                self.assertEqual("Seine", es_source.get("event_department"))

    def test_build_es_doc_empty_value_sets_empty_list(self):
        """Test that empty CSV values set field to empty list in ES.

        Trying: Update with a field set to empty string
        Expecting: ES document includes field with empty list
        """
        with self.admin_access.cnx() as cnx:
            mock_es = create_mock_es_client()

            with mock.patch.object(cnx.vreg["es"], "select") as mock_select:
                mock_indexer = mock.Mock()
                mock_indexer.get_connection.return_value = mock_es
                mock_select.return_value = mock_indexer

                reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

                # Test with empty value
                values = {
                    "stable_id": "test_stable_id",
                    "names": "",  # Empty value should set to []
                    "birth_place": "Paris",  # Non-empty should update
                }

                es_doc = reader.build_es_doc(values)

                # Verify doc contains all fields
                self.assertIn("doc", es_doc)
                self.assertEqual("Paris", es_doc["doc"].get("birth_place"))
                self.assertEqual([], es_doc["doc"].get("names"))

                # Verify no script (using simple doc update)
                self.assertNotIn("script", es_doc)

    def test_build_es_doc_empty_list_sets_empty_list(self):
        """Test that empty list values set field to empty list in ES.

        Trying: Update with a field set to empty list
        Expecting: ES document includes field with empty list
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

            values = {
                "stable_id": "test_stable_id",
                "occupations": [],  # Empty list
            }

            es_doc = reader.build_es_doc(values)

            # Verify field is set to empty list
            self.assertIn("doc", es_doc)
            self.assertEqual([], es_doc["doc"].get("occupations"))

    def test_build_es_doc_protected_fields_not_updated(self):
        """Test that protected fields are not included in doc update.

        Trying: Update with stable_id and service in values
        Expecting: These fields are not included in doc
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

            values = {
                "stable_id": "test_stable_id",
                "service": self.service.eid,
                "names": "",  # This should be in doc as []
            }

            es_doc = reader.build_es_doc(values)

            # Verify protected fields are not in doc
            self.assertNotIn("stable_id", es_doc["doc"])
            # But names should be there as empty list
            self.assertEqual([], es_doc["doc"].get("names"))

    def test_build_es_doc_none_value_sets_null(self):
        """Test that None values set field to null in ES.

        Trying: Update with a field set to None
        Expecting: ES document includes field with null value
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

            values = {
                "stable_id": "test_stable_id",
                "gender": None,  # None value should set to null
                "age": "25",  # Non-empty should update
            }

            es_doc = reader.build_es_doc(values)

            # Verify doc contains all fields
            self.assertIn("doc", es_doc)
            self.assertEqual("25", es_doc["doc"].get("age"))
            self.assertIsNone(es_doc["doc"].get("gender"))

    def test_build_es_doc_no_empty_values(self):
        """Test that non-empty values update fields normally.

        Trying: Update with all fields having values
        Expecting: ES document has all fields with values
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

            values = {
                "stable_id": "test_stable_id",
                "names": "Dupont",
                "forenames": "Jean",
            }

            es_doc = reader.build_es_doc(values)

            # Verify doc contains fields with values
            self.assertIn("doc", es_doc)
            self.assertEqual(["Dupont"], es_doc["doc"].get("names"))
            self.assertEqual(["Jean"], es_doc["doc"].get("forenames"))

    def test_build_es_doc_only_empty_values(self):
        """Test that only empty values generate doc with empty values.

        Trying: Update with all fields empty
        Expecting: ES document has all fields set to [] or None
        """
        with self.admin_access.cnx() as cnx:
            reader = CSVNominaUpdateReader(self.readerconfig, cnx, self.service.code)

            values = {
                "stable_id": "test_stable_id",
                "names": "",
                "forenames": "",
                "gender": None,
            }

            es_doc = reader.build_es_doc(values)

            # Verify doc contains all fields with empty values
            self.assertIn("doc", es_doc)
            self.assertEqual([], es_doc["doc"].get("names"))
            self.assertEqual([], es_doc["doc"].get("forenames"))
            self.assertIsNone(es_doc["doc"].get("gender"))


if __name__ == "__main__":
    unittest.main()
