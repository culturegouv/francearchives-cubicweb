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

from elasticsearch_dsl import TermsFacet, HistogramFacet, Q, query as dsl_query

from logilab.common.decorators import cachedproperty
from logilab.common.textutils import unormalize
from logilab.mtconverter import xml_escape

from cubicweb import _

from cubicweb_elasticsearch.views import CWFacetedSearch

from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.entities.nomina import (
    nomina_translate_codetype,
    nomina_translate_gender_code,
)
from cubicweb_francearchives.views import rebuild_url, get_template
from cubicweb_francearchives.utils import format_number

# FIXME - this might end up being configurable by facet
FACET_SIZE = 15
MISSING_INT = -100000
ALL_VALUES_SIZE = 300


class MissingNAMixIn(object):
    def add_filter(self, filter_values):
        if "N/R" in filter_values:
            return Q("bool", **{"must_not": Q("exists", field=self._params["field"])})
        return super(MissingNAMixIn, self).add_filter(filter_values)


class MissingNATermsFacet(MissingNAMixIn, TermsFacet):
    pass


class MissingNAHistogramFacet(MissingNAMixIn, HistogramFacet):
    def get_values(self, data, filter_values):
        out = []
        for bucket in data:
            key = self.get_value(bucket)
            if key == MISSING_INT:
                key = _("N/R")
            try:
                key = int(key)
            except Exception:
                pass
            out.append((key, bucket["doc_count"], self.is_filtered(key, filter_values)))
        return out


class ServiceTermsFacet(MissingNAMixIn, TermsFacet):
    def get_values(self, data, filter_values):
        """publisher value is a keyword in ES, but an integer in Posgres (service eid)"""
        out = []
        for bucket in data:
            key = self.get_value(bucket)
            try:
                key = int(key)
            except Exception:
                continue
            out.append((key, bucket["doc_count"], self.is_filtered(key, filter_values)))
        return out


class PniaCWFacetedSearch(CWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title*^4",
        "did.unittitle^4",
        "text",
        "index_entries.label^2",
        "alltext*",
    ]
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        # custom
        "publisher": ServiceTermsFacet(field="service.eid", size=ALL_VALUES_SIZE),
        "digitalized": TermsFacet(field="digitized_all"),
        "originators": TermsFacet(field="originators", size=FACET_SIZE),
    }
    display_date_facet = True

    def highlight(self, search):
        """
        Add custom highlighting
        """
        search = search.highlight(*(f if "^" not in f else f.split("^", 1)[0] for f in self.fields))
        return search.highlight_options(fragment_size=100, encoder="html", order="score")

    def add_to_query(self, bool_query, search, query):
        if bool_query is None:
            return search
        if query:
            search.query.filter.append(bool_query)
        else:
            if search.query:
                search.query.filter.append(bool_query)
            else:
                search.query = bool_query
        return search

    def only_or_query(self, searches, get_term_query, types):
        term_queries = []
        for index, value in enumerate(searches):
            if value == "":
                continue
            term_query = get_term_query(value, index, types)
            term_queries.append(term_query)
        return Q("bool", should=term_queries, minimum_should_match=1)

    def only_and_query(self, searches, get_term_query, types):
        term_queries = []
        for index, value in enumerate(searches):
            if value == "":
                continue
            term_query = get_term_query(value, index, types)
            term_queries.append(term_query)
        return Q("bool", must=term_queries)

    def add_advanced_query(self, parameter_name, search, query, get_term_query):
        search_value = self.extra_kwargs.get(parameter_name)
        if search_value is None:
            return search
        searches = json.loads(search_value)
        search_op = json.loads(self.extra_kwargs.get(f"{parameter_name}_op"))
        search_t = json.loads(self.extra_kwargs.get(f"{parameter_name}_t"))

        if ("ET" not in search_op) and ("SAUF" not in search_op):
            return self.add_to_query(
                self.only_or_query(searches, get_term_query, search_t), search, query
            )
        if ("OU" not in search_op) and ("SAUF" not in search_op):
            return self.add_to_query(
                self.only_and_query(searches, get_term_query, search_t), search, query
            )

        bool_query = None
        for index, value in enumerate(searches):
            if value == "":
                continue
            term_query = get_term_query(value, index, search_t)
            if index == 0:
                bool_query = term_query
                continue
            if len(search_op) >= index:
                operator = search_op[index - 1]
                if operator == "SAUF":
                    bool_query = Q("bool", must=bool_query, must_not=term_query)
                elif operator == "OU":
                    bool_query = Q("bool", should=[bool_query, term_query], minimum_should_match=1)
                else:
                    bool_query = Q("bool", must=[bool_query, term_query])

        return self.add_to_query(bool_query, search, query)

    def test_or_authority_query(self, search, query):
        def get_term_query(value, index, types):
            if types[index] not in ["s", "l", "a"]:
                return Q(
                    "simple_query_string",
                    query=value,
                    default_operator="and",
                )
            else:
                return Q("term", **{"index_entries.authority": value})

        return self.add_advanced_query("searches", search, query, get_term_query)

    def producers_query(self, search, query):
        def get_term_query(value, index, types):
            if types[index] == "k":
                return Q("term", **{"originators": value})
            else:
                return Q(
                    "simple_query_string",
                    query=value,
                    default_operator="and",
                    fields=["originators.text"],
                )

        return self.add_advanced_query("producers", search, query, get_term_query)

    def service_query(self, search, query):
        services_value = self.extra_kwargs.get("services")
        if services_value is None:
            return search
        services = json.loads(services_value)
        services_op = json.loads(self.extra_kwargs.get("services_op"))

        services_query = []

        for service_eid in services:
            if not service_eid:
                continue
            term_query = Q("term", **{"service.eid": service_eid})
            services_query.append(term_query)

        if services_op == "SAUF":
            return self.add_to_query(Q("bool", must_not=services_query), search, query)
        return self.add_to_query(Q("bool", should=services_query), search, query)

    def query(self, search, query):
        if self.extra_kwargs.get("ancestors-query") and query:
            # we are in Section primary view
            search.query = dsl_query.Bool(must=Q("term", ancestors=query))
        else:
            search = super(PniaCWFacetedSearch, self).query(
                search,
                query,
                match_kwargs={
                    "analyzer": "french_stop_analyzer",
                    "minimum_should_match": "2<70%",
                },
                slop=10,
            )
        search = self.test_or_authority_query(search, query)
        search = self.producers_query(search, query)
        search = self.service_query(search, query)
        if self.display_date_facet:
            search = self.add_dates_range(search, query)
        search = self.fulltext_facet(search, query)
        search = self.add_escategory(search, query)

        return search

    def get_dates_ranges(self):
        dates_lte = self.extra_kwargs.get("es_date_max")
        dates_gte = self.extra_kwargs.get("es_date_min")
        date_range = {}
        if dates_lte:
            date_range["lte"] = dates_lte
        if dates_gte:
            date_range["gte"] = dates_gte
        return date_range

    def add_dates_range(self, search, query, dates_field="dates"):
        date_range = self.get_dates_ranges()
        if not date_range:
            return search
        must_query = Q("exists", field=dates_field) & dsl_query.Range(**{dates_field: date_range})
        if query:
            search.query.filter.append(must_query)
        else:
            if search.query:
                search.query.filter.append(must_query)
            else:
                search.query = dsl_query.Bool(must=must_query)
        return search

    def fulltext_facet(self, search, query):
        fulltext_query = self.extra_kwargs.get("fulltext_facet")
        if not fulltext_query:
            return search
        if query:
            search.query.filter.append(
                Q("simple_query_string", query=fulltext_query, default_operator="and")
            )

        else:
            must_query = Q("simple_query_string", query=fulltext_query, default_operator="and")
            if search.query:
                search.query.filter.append(must_query)
            else:
                search.query = dsl_query.Bool(must=must_query)
        return search

    def add_escategory(self, search, query):
        escategory = self.extra_kwargs.get("es_escategory", None)
        if not isinstance(escategory, str):
            return search
        must_query = dsl_query.Term(escategory=escategory)
        if query or search.query:
            search.query.filter.append(must_query)
        else:
            search.query = dsl_query.Bool(must=must_query)
        return search


class PniaFCFacetedSearch(PniaCWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title*^4",
        "did.unittitle^4",
        "index_entries.label^2",
        "alltext*",
        "text",
    ]


class NoHighlightMixin(object):
    def highlight(self, search):
        """
        don't highlight when searching for FAComponent children
        https://github.com/elastic/elasticsearch/issues/14999
        """
        return search


class PniaFAFacetedSearch(PniaCWFacetedSearch):
    fields = [
        "did.unitid^6",
        "title*^4",
        "did.unittitle^4",
        "index_entries.label^2",
        "alltext*",
    ]


# TODO provide generic mechanism for missing query


class PniaCircularFacetedSearch(PniaCWFacetedSearch):
    fields = ["title^4", "alltext"]

    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "status": TermsFacet(field="status"),
        "business_field": MissingNATermsFacet(
            field="business_field", missing=_("N/R"), size=ALL_VALUES_SIZE
        ),
        "historical_context": MissingNATermsFacet(field="historical_context", size=ALL_VALUES_SIZE),
        "document_type": MissingNATermsFacet(
            field="document_type", missing=_("N/R"), size=ALL_VALUES_SIZE
        ),
        "siaf_daf_signing_year": MissingNAHistogramFacet(
            field="siaf_daf_signing_year", interval=10, missing=MISSING_INT, min_doc_count=1
        ),
        "archival_field": MissingNATermsFacet(
            field="archival_field", missing=_("N/R"), size=FACET_SIZE
        ),
    }

    @cachedproperty
    def restrict_to_single_type(self):
        return bool(self.form.get("restrict_to_single_etype"))

    def filter(self, search):
        """
        if restricted restrict_to_single_etype, do not add a ``post_filter`` to the search
        request narrowing the results based on the facet filters.
        Instead use "query filter" as there is no need for facets to show all possible values,
        only the ones that match the current search.
        """
        # if self.restrict_to_single_type:
        # filters = [dsl_query.Terms(cw_etype=["Circular"])]
        # bool_filter = Q("bool", filter=filters + list(self._filters.values()))
        bool_filter = Q("bool", filter=list(self._filters.values()))
        return search.query(bool_filter)

    def query(self, search, query):
        search = super().query(search, query)
        return search.sort("-sortdate")


class PniaNewsContentFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
    }

    def query(self, search, query):
        search = super(PniaNewsContentFacetedSearch, self).query(search, query)
        return search.sort("-sortdate")


class IndexFacetedSearchMixin(object):
    def query(self, search, query):
        queries = [Q("term", **{"index_entries.authority": self.form["indexentry"]})]
        ancestors = self.form.get("ancestors")
        if ancestors:
            queries.append(Q("term", ancestors=ancestors))

        search.query = dsl_query.Bool(must=queries)
        search = self.add_dates_range(search, query)
        search = self.fulltext_facet(search, query)
        search = self.add_escategory(search, query)

        return search


class PniaIndexEntryFacetedSearch(IndexFacetedSearchMixin, PniaCWFacetedSearch):
    pass


class PniaSubjectAuthorityFacetedSearch(IndexFacetedSearchMixin, PniaCWFacetedSearch):
    fields = [
        "title*^4",
        "did.unittitle^4",
        "index_entries.label^3",  # boost indexed documents
        "alltext*",
        "text",
    ]

    def query(self, search, query, field="dates"):
        """
        for multiple fields text search use
          Q("multi_match", query=query, type="phrase", slop=0, fields=("title", "content"))
        """
        # We want "index_query" results to be displayed before "text_query" results
        # the max score for index_query is 1, so we boost it with an arbitrary value of 100
        # Note that if the autority label matches the label in index_entries.label
        # and alltext this score will increase
        if not self.form.get("aug"):
            # execute the basic IndexFacetedSearchMixin.query without augmented query
            # https://extranet.logilab.fr/ticket/74056123
            return super().query(search, query)
        # ancestors are not used with augmented query
        index_query_must = [
            Q("term", index_entries__authority={"value": self.form["indexentry"], "boost": 100})
        ]
        # match_phrase query can not be called on multiple fields
        text_query_must = [Q("multi_match", query=query, type="phrase", slop=0, fields=self.fields)]

        # We cannot use add_dates_range, fulltext_fact and add_escategory
        # because we have to manipulate both the indexentry query and the text query in parallel
        date_range = self.get_dates_ranges()
        if date_range:
            dates_query = Q("exists", field="dates") & dsl_query.Range(**{"dates": date_range})
            index_query_must.append(dates_query)
            text_query_must.append(dates_query)
        fulltext_query = self.extra_kwargs.get("fulltext_facet")
        if fulltext_query:
            fulltext_query = Q("simple_query_string", query=fulltext_query, default_operator="and")
            index_query_must.append(fulltext_query)
            text_query_must.append(fulltext_query)
        escategory = self.extra_kwargs.get("es_escategory", None)
        if isinstance(escategory, str):
            category_query = dsl_query.Term(escategory=escategory)
            index_query_must.append(category_query)
            text_query_must.append(category_query)

        index_query = dsl_query.Bool(must=index_query_must)
        text_query = dsl_query.Bool(must=text_query_must)
        search.query = dsl_query.Bool(should=[index_query, text_query])
        return search


class PniaCmsSectionFacetedSearch(PniaCWFacetedSearch):
    display_date_facet = False

    def query(self, search, query):
        search = super(PniaCmsSectionFacetedSearch, self).query(search, query)
        return search.sort("order", "-sortdate")


class PniaServiceFacetedSearch(PniaCWFacetedSearch):
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "level": MissingNATermsFacet(field="level", missing=_("N/R"), size=FACET_SIZE),
        "partner": TermsFacet(field="is_partner"),
    }
    display_date_facet = False

    def query(self, search, query):
        # XXX using query because there is no sort in faceted_search
        # https://github.com/elastic/elasticsearch-dsl-py/issues/532
        search = super().query(search, query)
        return search.sort("sort_name")


class PniaAuthorityRecordFacetedSearch(PniaCWFacetedSearch):
    fields = [
        "title*^4",
        "index_entries.label^2",
        "alltext*",
    ]
    facets = {
        "cw_etype": TermsFacet(field="cw_etype", size=FACET_SIZE),
        "publisher": ServiceTermsFacet(field="service.eid", size=ALL_VALUES_SIZE),
    }


def build_query_type(attr, value):
    has_wildcard = ("*" in value) or ("?" in value)
    if has_wildcard:
        return Q(
            "wildcard",
            **{attr: {"value": value, "case_insensitive": True}},  # only supported in ES 7.10+
        )
    if value.startswith('"') and value.endswith('"'):
        return Q("match_phrase", **{attr: value})
    return Q("match", **{attr: value})


class NominaFacetedSearch(PniaCWFacetedSearch, NoHighlightMixin):
    fields = [
        "alltext",
    ]
    facets = {
        "service": ServiceTermsFacet(field="service", size=ALL_VALUES_SIZE),
        "act_type": TermsFacet(field="act_type", size=100),
        "gender": TermsFacet(field="gender", size=5),
    }

    def __init__(self, *args, include_export_aggs=False, **kwargs):
        """
        Initialize NominaFacetedSearch.

        :param include_export_aggs: If True, adds act_type × service aggregations
                                    for CSV export availability check
        """
        self.include_export_aggs = include_export_aggs
        super().__init__(*args, **kwargs)

    def sort(self, search):
        """
        Override sort method to handle custom sorting for nomina records.

        Supported sort options:
        - score: by relevance (_score desc) - DEFAULT
        - title_asc: alphabetical A-Z (case-insensitive)
        - title_desc: alphabetical Z-A (case-insensitive)
        - event_date_asc: chronological old to recent
        - event_date_desc: chronological recent to old
        """
        sort_option = self.extra_kwargs.get("script_sort", "score")
        if sort_option == "title_asc":
            # Tri alphabétique sur title (script Painless car champ text)
            search = search.sort(
                {
                    "_script": {
                        "type": "string",
                        "script": {
                            "source": """
                                String title = params._source.title;
                                if (title == null || title.isEmpty()) {
                                    return 'zzzzz';
                                }
                                String s = title.toLowerCase();

                                s = s.replace('é', 'e').replace('è', 'e').replace('ê', 'e')
                                     .replace('ë', 'e').replace('à', 'a').replace('â', 'a')
                                     .replace('ä', 'a').replace('ù', 'u').replace('û', 'u')
                                     .replace('ü', 'u').replace('ô', 'o').replace('ö', 'o')
                                     .replace('î', 'i').replace('ï', 'i').replace('ç', 'c')
                                     .replace('œ', 'oe').replace('æ', 'ae');

                                return s;
                            """,
                            "lang": "painless",
                        },
                        "order": "asc",
                    }
                },
                {"stable_id": {"order": "asc"}},
            )
        elif sort_option == "title_desc":
            search = search.sort(
                {
                    "_script": {
                        "type": "string",
                        "script": {
                            "source": """
                                String title = params._source.title;
                                if (title == null || title.isEmpty()) {
                                    return 'zzzzz';
                                }
                                String s = title.toLowerCase();

                                s = s.replace('é', 'e').replace('è', 'e').replace('ê', 'e')
                                     .replace('ë', 'e').replace('à', 'a').replace('â', 'a')
                                     .replace('ä', 'a').replace('ù', 'u').replace('û', 'u')
                                     .replace('ü', 'u').replace('ô', 'o').replace('ö', 'o')
                                     .replace('î', 'i').replace('ï', 'i').replace('ç', 'c')
                                     .replace('œ', 'oe').replace('æ', 'ae');

                                return s;
                            """,
                            "lang": "painless",
                        },
                        "order": "desc",
                    }
                },
                {"stable_id": {"order": "asc"}},
            )
        elif sort_option == "event_date_asc":
            search = search.sort(
                {
                    "_script": {
                        "type": "number",
                        "script": {
                            "source": """
                                def dates = params._source.event_dates;
                                if (dates == null) {
                                    return -9999;
                                }
                                if (dates.containsKey('gte')) {
                                    def gte = dates.gte;
                                    try {
                                        return Integer.parseInt(gte);
                                    } catch (Exception e) {
                                        return -9999;
                                    }
                                }
                                return -9999;
                            """,
                            "lang": "painless",
                        },
                        "order": "asc",
                    }
                },
                {"stable_id": {"order": "asc"}},
            )
        elif sort_option == "event_date_desc":
            search = search.sort(
                {
                    "_script": {
                        "type": "number",
                        "script": {
                            "source": """
                                def dates = params._source.event_dates;
                                if (dates == null) {
                                    return -9999;
                                }
                                if (dates.containsKey('gte')) {
                                    def gte = dates.gte;
                                    try {
                                        return Integer.parseInt(gte);
                                    } catch (Exception e) {
                                        return -9999;
                                    }
                                }
                                return -9999;
                            """,
                            "lang": "painless",
                        },
                        "order": "desc",
                    }
                },
                {"stable_id": {"order": "asc"}},
            )
        else:
            search = search.sort({"_score": {"order": "desc"}}, {"stable_id": {"order": "asc"}})

        return search

    def query(self, search, query):
        forenames = self.extra_kwargs.get("es_forenames")
        names = self.extra_kwargs.get("es_names")
        locations = self.extra_kwargs.get("es_locations")
        authority = self.extra_kwargs.get("authority")
        household_id = self.extra_kwargs.get("household")
        must = []
        if forenames:
            must.append(build_query_type("forenames", forenames))
        if names:
            must.append(build_query_type("names", names))
        if locations:
            must.append(
                Q(
                    "multi_match",
                    type="phrase",
                    query=locations,
                    fields=[
                        "event_commune.text",
                        "event_department.text",
                        "event_country.text",
                    ],
                )
            )
        if authority:
            must.append(Q("match", authority=authority))
        if household_id:
            must.append(Q("match", household_id=household_id))

        search.query = dsl_query.Bool(must=must)
        search = self.add_dates_range(search, query, dates_field="event_dates")
        search = self.fulltext_facet(search, query)

        # Determine which fields to include based on csv_export parameter
        csv_export = self.extra_kwargs.get("csv_export", False)
        if csv_export:
            # Include all fields needed for CSV export
            search = search.source(
                [
                    "forenames",
                    "names",
                    "event_date",
                    "event_commune",
                    "event_department",
                    "event_country",
                    "act_type",
                    "service",
                    "stable_id",
                    "title",
                    "occupations",
                    "occupations_index",
                    "gender",
                    "cote",
                    "notice_id",
                    "source_url",
                ]
            )
        else:
            # Minimal fields for UI display
            search = search.source(
                [
                    "forenames",
                    "names",
                    "event_date",
                    "event_commune",
                    "event_department",
                    "event_country",
                    "act_type",
                    "service",
                    "stable_id",
                    "title",
                ]
            )
        # Add export aggregations if requested
        if self.include_export_aggs:
            agg_filter = Q("match_all")

            # Apply ALL filters from facet selections (including act_type and service)
            for facet_name, facet_filter in self._filters.items():
                agg_filter &= facet_filter

            # Add filtered nested aggregation
            search.aggs.bucket("act_type_filtered", "filter", filter=agg_filter).bucket(
                "act_type", "terms", field="act_type", size=100
            ).bucket("service", "terms", field="service", size=100)

        return search


FACETED_SEARCHES = {
    "default": PniaCWFacetedSearch,
    "newscontent": PniaNewsContentFacetedSearch,
    "circular": PniaCircularFacetedSearch,
    "section": PniaCmsSectionFacetedSearch,
    "service": PniaServiceFacetedSearch,
    "facomponent": PniaFCFacetedSearch,
    "findingaid": PniaFAFacetedSearch,
    "indexentry": PniaIndexEntryFacetedSearch,
    "agentauthority": PniaIndexEntryFacetedSearch,
    "locationauthority": PniaIndexEntryFacetedSearch,
    "subjectauthority": PniaSubjectAuthorityFacetedSearch,
    "authorityrecord": PniaAuthorityRecordFacetedSearch,
}


class PniaDefaultFacetRenderer(object):
    template = get_template("facet.jinja2")
    item = '<li class="{css}" style="{style}">{content}</li>'
    item_link = (
        '    <a href="{url}" title="{alt}" class="facet__focusable-item">'
        "      {content}"
        "    </a>"
        '    <span class="facet__item_count">{count}</span>'
    )
    item_nolink = (
        '<li class="facet__value">'
        "   {content}"
        '   <span class="facet__item_count">{count}</span>'
        "</li>"
    )
    filter_tags = True
    unfolded = False

    @staticmethod
    def build_content(req, content):
        if isinstance(content, str):
            content = xml_escape(content)
        return req._(content)

    def __init__(self, sort="count", items_size=FACET_SIZE, nr_tag="N/R"):
        assert sort in ("count", "item")
        self.item_sort = sort
        self.items_size = items_size
        self.nr_tag = nr_tag

    def __call__(self, req, bucket, facetid, facetlabel, searchcontext, response):
        # keep only items leading to more than 1 result
        bucket = self.build_bucket(bucket)
        if len(bucket) == 0:
            return None
        self.req = req
        self.facetid = facetid
        self.searchcontext = searchcontext
        self.selected = False
        if "es_{}".format(self.facetid) in self.req.form:
            self.selected = True
        self.total_count = response.hits.total.value if response is not None else 0
        return self.render(bucket, facetlabel)

    def item_css(self, idx, selected):
        css = ["facet__value"]
        if selected:
            css.append("facet__value--active")
        return css

    def item_style(self, idx):
        return ""

    def build_bucket(self, bucket):
        # keep only items leading to more than 1 result
        bucket = [item for item in bucket if item[1] > 0]
        if self.item_sort == "item":
            bucket.sort(key=lambda x: unormalize(x[0].lower()))
        # sort facet values to put selected first
        bucket = sorted(bucket, key=lambda x: -x[2])
        return bucket

    def build_item_content(self, content, selected):
        content = self.build_content(self.req, content)
        if selected:
            return '<span class="facet--active">{}</span>'.format(content)
        return content

    def translate_label(self, tag):
        return tag

    def render_nolink_item(self, idx, tag, count, selected):
        tag = self.translate_label(tag)
        return self.item_nolink.format(
            content=self.build_item_content(tag, selected), count=format_number(count, self.req)
        )

    def render_item(self, idx, tag, count, selected):
        return self.item.format(
            css=" ".join(self.item_css(idx, selected)),
            style=self.item_style(idx),
            content=self.render_item_link(idx, tag, count, selected),
        )

    def build_url_params(self, param_name, tag):
        return {
            "vid": None,
            "page": None,
            param_name: str(tag),
        }

    def render_item_link(self, idx, tag, count, selected):
        req = self.req
        _ = self.req._
        param_name = "es_{}".format(self.facetid)
        alt = _("select")
        url_params = self.build_url_params(param_name, tag)
        if selected:
            alt = _("deselect")
        return self.item_link.format(
            url=rebuild_url(req, **url_params),
            alt=alt,
            content=self.build_item_content(self.translate_label(tag), selected),
            count=format_number(count, req),
        )

    def render(self, bucket, facetlabel):
        items = []
        more_items = []
        last_item = None
        for idx, (tag, count, selected) in enumerate(bucket):
            if not tag and self.filter_tags:
                continue
            if len(bucket) == 1 and count == self.total_count:
                item = self.render_nolink_item(idx, tag, count, selected)
            else:
                item = self.render_item(idx, tag, count, selected)
            if item:
                # XXX do it in build_bucket ?
                if tag == self.nr_tag:
                    last_item = item
                elif idx <= self.items_size:
                    items.append(item)
                else:
                    more_items.append(item)
        if last_item:
            if idx <= self.items_size:
                items.append(last_item)
            else:
                more_items.append(last_item)
        if not items:
            return None
        return self.template.render(
            {
                "_": self.req._,
                "facetid": self.facetid,
                "facet_label": facetlabel,
                "facet_items": items,
                "facet_unfolded": self.unfolded or self.selected,
                "more_items_label": self.req._("More options (%(count)s)")
                % {"count": len(more_items)},
                "less_items_label": self.req._("Less options"),
                "more_facet_items": more_items,
            }
        )


class PniaEtypeFacetRenderer(PniaDefaultFacetRenderer):
    @staticmethod
    def build_content(req, content):
        if content == "Service":
            return req._("archive-services-label")
        return req.__("%s_plural" % content)


class PniaNominaDocumentTypeRenderer(PniaDefaultFacetRenderer):
    def translate_label(self, tag):
        return nomina_translate_codetype(tag)


class PniaNominaGenderRenderer(PniaDefaultFacetRenderer):
    def translate_label(self, tag):
        return nomina_translate_gender_code(tag)


class PniaServiceRenderer(PniaDefaultFacetRenderer):
    template = get_template("facet-service.jinja2")

    def render(self, bucket, facetlabel):
        self.services = {
            eid: name
            for eid, name in self.req.execute(
                """Any X, SN WHERE X is Service,
                   X short_name SN"""
            )
        }
        return super().render(bucket, facetlabel)

    def translate_label(self, tag):
        return self.services.get(tag, tag)


class PniaIsPublishedFacetRenderer(PniaDefaultFacetRenderer):
    filter_tags = False

    def build_bucket(self, bucket):
        # convert int value to boolean: 0 -> False and 1 -> True
        bucket = super().build_bucket(bucket)
        return [(bool(item[0]),) + item[1:] for item in bucket]

    @staticmethod
    def build_content(req, content):
        _ = req._
        return _("published") if content else _("draft")


class PniaDigitalizedFacetRenderer(DZFacetValues, PniaDefaultFacetRenderer):
    """for instnace only four following values can be found in this facet e.g DZFacetValues"""

    unfolded = True

    digitized_template = """
    <li class="facet__value">
      {parent}
      <ul>
      {children}
      </ul>
    </li>
    """

    def translate_label(self, tag):
        return f"{tag}_value"

    def process_bucket(self, bucket):
        digitized, digitized_items, non_digitized = None, [], None
        for item in bucket:
            terms = item[0].split("-")
            if terms[0] == self.dz:
                if len(terms) == 1:
                    digitized = item
                else:
                    digitized_items.append(item)
            else:
                non_digitized = item
        # if "all digitized" option is selected, "iiif" and "no iiif" options
        # must be selected
        if digitized and digitized[2]:
            digitized_items = [d[:2] + (True,) for d in digitized_items]
        else:
            digitized_items_selected = digitized_items and all([d[2] for d in digitized_items])
            # if "iiif" and "no iiif" options is selected, all digitized" option
            # must be selected
            if digitized_items_selected:
                digitized = digitized[:2] + (True,)
        return digitized, digitized_items, non_digitized

    def render(self, bucket, facetlabel):
        items = []
        digitized, digitized_items, non_digitized = self.process_bucket(bucket)
        if digitized:
            if digitized_items:
                items.append(
                    self.digitized_template.format(
                        parent=self.render_item(0, *(digitized)),
                        children="".join(
                            [self.render_item(0, *(di)) for di in digitized_items if di[0]]
                        ),
                    )
                )
            else:
                items.append(self.render_item(0, *(digitized)))
        if non_digitized:
            items.append(self.render_item(0, *(non_digitized)))
        if not items:
            return None
        return self.template.render(
            {
                "_": self.req._,
                "facetid": self.facetid,
                "facet_label": facetlabel,
                "facet_items": items,
                "facet_unfolded": self.unfolded or self.selected,
            }
        )

    def build_url_params(self, param_name, tag):
        """This function handle the multiselection of the digitalized facet value.

        The values of "iiif" and "no iiif" options are excusive expect if "all
        digitalized" option is selected (OR operator). Other options are used
        with the "AND" operator.

        """
        selected = self.req.form.get(param_name, [])
        if not isinstance(selected, (list, tuple)):
            selected = (selected,)
        selected = set(selected)
        tag = str(tag)
        replace_keys = True
        values = tag
        if tag == self.dz:
            params = set([*self.dzitems().keys(), self.dz])
            if self.dz not in selected:
                values = list(selected | params)
            else:
                values = list(selected - params)
        elif tag in self.dzitems():
            if self.dz in selected:
                if tag in selected:
                    values = list(selected - set([tag, self.dz]))
                else:
                    values = list(selected - set([self.dz]) | set([tag]))
            else:
                if tag in selected:
                    values = list(selected - set([tag]))
                else:
                    reverse_dzitems = list(self.dzitems().keys())
                    reverse_dzitems.remove(tag)
                    values = list(selected - set(reverse_dzitems) | set([tag]))
        elif tag == self.nondz:
            replace_keys = False
        return {
            "vid": None,
            "page": None,
            "replace_keys": replace_keys,
            param_name: values,
        }


class PniaDPartnerFacetRenderer(PniaDefaultFacetRenderer):
    filter_tags = False

    def build_bucket(self, bucket):
        # convert int value to boolean: 0 -> False and 1 -> True
        bucket = super().build_bucket(bucket)
        return [(bool(item[0]),) + item[1:] for item in bucket]

    @staticmethod
    def build_content(req, content):
        _ = req._
        return _("Services contributors") if content else _("Services non-contributors")


class PniaStatusFacetRenderer(PniaDefaultFacetRenderer):
    @staticmethod
    def build_content(req, content):
        _ = req._
        status_html = '<div class="circular-status circular-status-{}"></div> {}'
        return status_html.format(content, _(content))


def format_missing_year_item(req, year, incr):
    try:
        year_value = int(year)
        return "{} - {}".format(year_value, year_value + incr)
    except Exception:
        return req._(year)


class PniaSigningYearFacetRenderer(PniaDefaultFacetRenderer):
    @staticmethod
    def build_content(req, content):
        return format_missing_year_item(req, content, 9)


FACET_RENDERERS = {
    "default": PniaDefaultFacetRenderer(),
    "cw_etype": PniaEtypeFacetRenderer(),
    "digitalized": PniaDigitalizedFacetRenderer(sort="item"),
    "partner": PniaDPartnerFacetRenderer(),
    "status": PniaStatusFacetRenderer(),
    "siaf_daf_signing_year": PniaSigningYearFacetRenderer(),
    "business_field": PniaDefaultFacetRenderer(sort="item"),
    "historical_context": PniaDefaultFacetRenderer(sort="item"),
    "document_type": PniaDefaultFacetRenderer(sort="item"),
    "action": PniaDefaultFacetRenderer(sort="item"),
    "service": PniaServiceRenderer(),
    "act_type": PniaNominaDocumentTypeRenderer(),
    "gender": PniaNominaGenderRenderer(),
    "publisher": PniaServiceRenderer(),
    "is_published": PniaIsPublishedFacetRenderer(),
}
