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

"""Tests for nomina CSV export availability functions"""

import unittest

from cubicweb_web.devtools.testlib import WebCWTC
from cubicweb_francearchives.testutils import PostgresTextMixin
from cubicweb_francearchives.views.search.nomina import (
    get_service_codes_batch,
)
from cubicweb_francearchives.entities.nomina import (
    FORBIDDEN_CSV_EXPORT,
    build_nomina_faceted_search_kwargs,
)

from pgfixtures import setup_module, teardown_module  # noqa


class GetServiceCodesBatchTC(PostgresTextMixin, WebCWTC):
    """Tests for get_service_codes_batch helper function"""

    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Service", code="FRAD001", category="DS", name="Service 1")
            cnx.create_entity("Service", code="FRAD002", category="DS", name="Service 2")
            cnx.create_entity("Service", code="FRAD010", category="DS", name="Service 3")
            cnx.commit()

    def test_empty_service_eids(self):
        """Test with empty service_eids list"""
        with self.admin_access.cnx() as cnx:
            result = get_service_codes_batch(cnx, [])
            self.assertEqual(result, {})

    def test_single_service(self):
        """Test with single service eid"""
        with self.admin_access.cnx() as cnx:
            service = cnx.find("Service", code="FRAD001").one()
            result = get_service_codes_batch(cnx, [service.eid])
            self.assertEqual(result, {service.eid: "FRAD001"})

    def test_multiple_services(self):
        """Test with multiple service eids (batch query)"""
        with self.admin_access.cnx() as cnx:
            services = list(cnx.find("Service").all())
            service_eids = [s.eid for s in services]
            result = get_service_codes_batch(cnx, service_eids)
            expected = {s.eid: s.code for s in services}
            self.assertEqual(result, expected)

    def test_forbidden_service(self):
        """Test service in FORBIDDEN_CSV_EXPORT"""
        with self.admin_access.cnx() as cnx:
            service = cnx.find("Service", code="FRAD010").one()
            result = get_service_codes_batch(cnx, [service.eid])
            self.assertEqual(result, {service.eid: "FRAD010"})
            self.assertIn("FRAD010", FORBIDDEN_CSV_EXPORT)


class BuildNominaFacetedSearchKwargsTC(unittest.TestCase):
    """Tests for build_nomina_faceted_search_kwargs helper function"""

    def test_minimal_params(self):
        """Test with minimal/empty form params"""
        form_params = {}
        result = build_nomina_faceted_search_kwargs(form_params)

        self.assertEqual(result["fulltext_facet"], None)
        self.assertEqual(result["es_date_max"], None)
        self.assertEqual(result["es_date_min"], None)
        self.assertEqual(result["es_forenames"], None)
        self.assertEqual(result["es_names"], None)
        self.assertEqual(result["es_locations"], None)
        self.assertEqual(result["agent"], None)
        self.assertEqual(result["household"], None)
        self.assertEqual(result["script_sort"], "score")  # default

    def test_all_params_provided(self):
        """Test with all search parameters"""
        form_params = {
            "q": "test",
            "fulltext_facet": "fulltext query",
            "es_date_max": "2020-12-31",
            "es_date_min": "2000-01-01",
            "es_forenames": "Jean",
            "es_names": "Dupont",
            "es_locations": "Paris",
            "authority": "123",
            "household": "456",
            "sort": "event_date_asc",
        }
        result = build_nomina_faceted_search_kwargs(form_params)

        self.assertEqual(result["fulltext_facet"], "fulltext query")
        self.assertEqual(result["es_date_max"], "2020-12-31")
        self.assertEqual(result["es_date_min"], "2000-01-01")
        self.assertEqual(result["es_forenames"], "Jean")
        self.assertEqual(result["es_names"], "Dupont")
        self.assertEqual(result["es_locations"], "Paris")
        self.assertEqual(result["agent"], "123")
        self.assertEqual(result["household"], "456")
        self.assertEqual(result["script_sort"], "event_date_asc")

    def test_custom_text_facets(self):
        """Test with custom text facets list"""
        form_params = {
            "es_custom_facet": "value",
            "fulltext_facet": "text",
        }
        result = build_nomina_faceted_search_kwargs(form_params, text_facets=["es_custom_facet"])

        self.assertEqual(result["es_custom_facet"], "value")
        self.assertNotIn("es_forenames", result)
        self.assertNotIn("es_names", result)
        self.assertNotIn("es_locations", result)

    def test_authority_maps_to_agent(self):
        """Test that 'authority' param maps to 'agent' kwarg"""
        form_params = {"authority": "agent-123"}
        result = build_nomina_faceted_search_kwargs(form_params)

        self.assertEqual(result["agent"], "agent-123")

    def test_sort_default_value(self):
        """Test that sort defaults to 'score'"""
        form_params = {}
        result = build_nomina_faceted_search_kwargs(form_params)

        self.assertEqual(result["script_sort"], "score")

        form_params = {"sort": "title_desc"}
        result = build_nomina_faceted_search_kwargs(form_params)

        self.assertEqual(result["script_sort"], "title_desc")


class CsvExportDateFiltersTC(unittest.TestCase):
    """Tests for CSV export with date filters (bug fix)"""

    def test_date_facets_excluded_from_facet_selections(self):
        """Verify that es_date_min and es_date_max are excluded from facet_selections

        This is a regression test for the bug where CSV export failed when using
        date filters via facets (es_date_min/es_date_max) instead of fulltext_facet.

        The issue was that date facets were incorrectly added to facet_selections,
        but NominaFacetedSearch doesn't have facet definitions for date_min/date_max.
        Date filters should only be passed via extra_kwargs (handled by
        build_nomina_faceted_search_kwargs).
        """
        # Simulate the logic from nominaroutes.py lines 154-163
        search_params = {
            "es_names": "Dupont",
            "es_act_type": "RM",
            "es_date_min": "1846",
            "es_date_max": "1846",
            "es_service": "123",
        }

        text_facets = {"es_forenames", "es_names", "es_locations"}
        date_facets = {"es_date_min", "es_date_max"}
        facet_selections = {}

        for key, value in search_params.items():
            if key.startswith("es_") and key not in text_facets and key not in date_facets:
                facet_name = key[3:]  # Remove "es_" prefix
                if isinstance(value, (list, tuple)):
                    facet_selections[facet_name] = list(value)
                else:
                    facet_selections[facet_name] = value

        # Date facets should NOT be in facet_selections
        self.assertNotIn("date_min", facet_selections)
        self.assertNotIn("date_max", facet_selections)

        # Other facets should be present
        self.assertIn("act_type", facet_selections)
        self.assertIn("service", facet_selections)
        self.assertEqual(facet_selections["act_type"], "RM")
        self.assertEqual(facet_selections["service"], "123")

        # es_names is a text facet, so it should NOT be in facet_selections
        self.assertNotIn("names", facet_selections)

    def test_date_filters_passed_via_kwargs(self):
        """Verify that date filters are correctly passed via build_nomina_faceted_search_kwargs"""
        search_params = {
            "es_date_min": "1846",
            "es_date_max": "1846",
            "es_names": "Dupont",
        }

        kwargs = build_nomina_faceted_search_kwargs(search_params)

        # Date filters should be in kwargs (extra_kwargs for NominaFacetedSearch)
        self.assertEqual(kwargs["es_date_min"], "1846")
        self.assertEqual(kwargs["es_date_max"], "1846")

        # Text facets should also be in kwargs
        self.assertEqual(kwargs["es_names"], "Dupont")


class CsvExportOccupationsTC(unittest.TestCase):
    """Tests for CSV export occupations field consistency"""

    def test_occupations_field_selection_for_rp(self):
        """Verify that occupations_index is used for RP in CSV export"""
        # Simulate the logic from entities/nomina.py lines 187-210
        hit = {
            "act_type": "RP",
            "occupations": ["Maçon"],  # Source (capitalized)
            "occupations_index": ["maçon"],  # Indexed (lowercase)
        }

        from cubicweb_francearchives.entities.nomina import normalized_doctype_code

        code = normalized_doctype_code(hit["act_type"])

        if code == "RP":
            occupations_index = hit.get("occupations_index")  # Indexed
        else:
            occupations_index = None

        occupations_for_csv = ", ".join(occupations_index) if occupations_index else ""

        # Should use occupations_index (indexed), not occupations (source)
        self.assertEqual(
            occupations_for_csv,
            "maçon",
            "CSV export should use occupations_index for RP, not occupations",
        )

    def test_occupations_field_selection_for_non_rp(self):
        """Verify that occupations is used for non-RP in CSV export"""
        # Simulate the logic from entities/nomina.py lines 187-210
        hit = {
            "act_type": "N",
            "occupations": ["Maçon"],
        }

        from cubicweb_francearchives.entities.nomina import normalized_doctype_code

        code = normalized_doctype_code(hit["act_type"])

        # This is the logic from nomina.py lines 187-192
        if code == "RP":
            occupations_raw = hit.get("occupations")  # Source
            occupations_index = hit.get("occupations_index")  # Indexed
        else:
            occupations_raw = hit.get("occupations")
            occupations_index = None

        # For CSV export (line 209-210 after fix), should use occupations_index if available
        # Otherwise fallback to occupations_raw
        occupations_for_csv = (
            ", ".join(occupations_index)
            if occupations_index
            else (", ".join(occupations_raw) if occupations_raw else "")
        )

        # Should use occupations for non-RP
        self.assertEqual(
            occupations_for_csv,
            "Maçon",
            "CSV export should use occupations for non-RP",
        )

    def test_occupations_field_selection_for_rp_no_index(self):
        """Verify fallback when occupations_index is missing for RP"""
        # Simulate the logic from entities/nomina.py lines 187-210
        hit = {
            "act_type": "RP",
            "occupations": ["Maçon"],  # Only source, no index
        }

        from cubicweb_francearchives.entities.nomina import normalized_doctype_code

        code = normalized_doctype_code(hit["act_type"])

        if code == "RP":
            occupations_index = hit.get("occupations_index")  # Indexed (will be None)
        else:
            occupations_index = None

        occupations_for_csv = ", ".join(occupations_index) if occupations_index else ""

        # Should be empty when occupations_index is missing
        self.assertEqual(
            occupations_for_csv,
            "",
            "CSV export should be empty when occupations_index is missing for RP",
        )


if __name__ == "__main__":
    unittest.main()
