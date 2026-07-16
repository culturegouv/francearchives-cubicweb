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

from string import ascii_uppercase

from elasticsearch_dsl.search import Search
from elasticsearch.exceptions import ConnectionError, RequestError
from elasticsearch_dsl import query as dsl_query

from cwtags import tag as T

from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.rset import ResultSet

from cubicweb_elasticsearch.views import ElasticSearchView

from cubicweb_francearchives.views import get_template, rebuild_url
from cubicweb_francearchives.utils import format_number

from . import EulerianMixin, PaginationMixin, FakeResponse


LETTERS_TO_LABEL = {"#": _("others alphabets"), "0": _("0-9"), "!": _("punctuation")}


class PniaAuthoritiesElasticSearchView(EulerianMixin, PaginationMixin, ElasticSearchView):
    __abstract__ = True
    title_count_templates = (_("No result"), _("1 result"), _("{count} results"))
    template = get_template("searchlist-authority.jinja2")
    items_per_page_options = [100, 200]
    default_items_per_page = 100
    eulerian_tag = True

    @property
    def breadcrumbs(self):
        return ((self._cw.build_url(""), self._cw._("Home")), (None, self._cw._(self.title)))

    def add_js(self):
        self._cw.add_js("bundle-pnia-search.js")

    # XXX This page does not have a query string, to modify or remove
    @cachedproperty
    def cached_search_response(self):
        query_string = self._cw.form.get("q")
        if hasattr(self, "_esresponse"):
            return self._esresponse, query_string
        try:
            self._esresponse = self.do_search(query_string)
        except Exception as err:
            self.exception(err)
            self._esresponse = FakeResponse()

        return self._esresponse, query_string

    def build_results(self, response):
        rset = self.rset_from_response(response)
        if not rset:
            return []
        results = []
        for entity, item_response in zip(rset.entities(), response):
            try:
                entity.complete()
            except Exception:
                self.exception(
                    "failed to build entity with eid %s (ES says etype is %s)",
                    entity.eid,
                    getattr(item_response, "cw_etype", "?"),
                )
                continue
            results.append(entity.view("pniasearch-item", es_response=item_response))
        return results

    def format_results_title(self, response):
        count = response.hits.total.value if response is not None else 0
        if count == 0:
            tmpl = self.title_count_templates[0]
        elif count == 1:
            tmpl = self.title_count_templates[1]
        else:
            tmpl = self.title_count_templates[2]
        return self._cw._(tmpl).format(count=format_number(count, self._cw))

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        """
        This is where one can customize the search by modifying the
        query string and facet selection in an inherited class.

        """
        stop = stop if stop != 10 else self.default_items_per_page
        cwconfig = self._cw.vreg.config
        index_name = f"{cwconfig['index-name']}_suggest"
        search = Search(index=index_name).sort("text.raw")
        search = search.extra(track_total_hits=True)
        must = [
            {"match": {"cw_etype": self.cw_etype}},
            {"match": {"quality": True}},
            {"range": {"count": {"gte": 1}}},
        ]
        fulltext_string = self._cw.form.get("fulltext_facet", "").strip()
        if fulltext_string:
            must.append(
                dsl_query.SimpleQueryString(
                    "simple_query_string",
                    query=fulltext_string,
                    fields=["text"],
                    default_operator="and",
                )
            )
        letter = self._cw.form.get("let")
        if letter:
            must.append({"match": {"letter": letter}})
        search.query = dsl_query.Bool(must=must)
        return search[start:stop]

    def rset_from_response(self, response):
        """transform an ES response into a CubicWeb rset

        This consists in iterating on current panigated response and
        inspect the ``cw_etype`` and ``eid`` document fields.

        NOTE: some etypes used for the ES indexation are not part of the
        actual CubicWeb schema and therefore require to be mapped on a
        valid entity type (e.g. ExternRef's reftypes)

        others, e.g Card are not indexed with their own etypes
        """

        def get_etype_from_result(result):
            return getattr(result, "cw_etype", self.cw_etype)

        req = self._cw
        descr, rows = [], []
        for idx, result in enumerate(response):
            # safety belt, in v0.6.0, PDF are indexed without a cw_etype field
            cw_etype = get_etype_from_result(result)
            # safety belt for import-ead with esonly=True: in that case,
            # ES documents don't have eids
            if not result.eid:
                # must not happen
                continue
            else:
                eid = result.eid
            descr.append((cw_etype, "String"))
            rows.append([eid, "foo"])
        rset = ResultSet(rows, "Any X", description=descr)
        rset.req = req
        return rset

    @cachedproperty
    def search_summary(self):
        if not hasattr(self, "_search_summary"):
            self._search_summary = self.compute_search_summary()
        return self._search_summary

    def compute_search_summary(self):
        """Do not translate labels here"""
        summary = []
        active_letter = self._cw.form.get("let", "").strip()
        if active_letter:
            reset_url = rebuild_url(self._cw, **{"let": None})
            value = LETTERS_TO_LABEL.get(active_letter, "")
            if not value:
                value = f'"{active_letter.upper()}"'
            summary.append({"name": _("Starts with"), "value": [(value, reset_url)]})
        key = "fulltext_facet"
        value = self._cw.form.get(key, "").strip()
        if value:
            reset_url = rebuild_url(self._cw, **{key: None})
            summary.append({"name": _("Contains"), "value": [(value, reset_url)]})
        search_summary = {}
        if summary:
            search_summary["summary"] = summary
        return search_summary

    def get_header_attrs(self):
        return {"title": self._cw._(self.title)}

    def letters(self, entity=None):
        data = {}
        active_letter = self._cw.form.get("let", "")
        data["all"] = [
            (
                self._cw._("all").capitalize(),
                self._cw.build_url(),
                "fr-btn fr-btn--primary" if not active_letter else "fr-btn fr-btn--tertiary",
            )
        ]
        letters = []
        for letter in ascii_uppercase:
            lower = letter.lower()
            letters.append(
                (
                    letter,
                    self._cw.build_url(let=lower),
                    (
                        "fr-btn fr-btn--primary"
                        if lower == active_letter
                        else "fr-btn fr-btn--tertiary"
                    ),
                )
            )
        # 0-9
        data["letters"] = letters
        return data

    def reset_all_facets_link(self):
        """Creates a URL which resets the values from the facets to display

        The value of the initial query (parameter q) is kept
        as well as values which come from other SearchView
        """
        url_params = {}
        facets = self.facets_to_display
        for facet in facets:
            url_params["es_{}".format(facet[0])] = None
        for key in ("fulltext_facet", "es_date_min", "es_date_max", "let"):
            url_params[key] = None
        return rebuild_url(self._cw, **url_params)

    def call(self, context=None, **kwargs):
        self.add_js()
        try:
            response, query_string = self.cached_search_response
        except ConnectionError:
            self.w(
                T.div(
                    self._cw._("failed to connect to elasticsearch"),
                    Class="alert alert-info",
                    role="alert",
                )
            )
            return
        except RequestError:
            self.exception("ES search failed")
            self.w(
                T.div(
                    self._cw._("there was a problem with the elasticsearch request"),
                    Class="alert alert-info",
                    role="alert",
                )
            )
            return
        except KeyError:
            self.exception(f"Key error on {self.__class__} do_search")
            response = FakeResponse()
        # FIXME fulltext don't work
        fulltext_params = self._cw.form.copy()
        fulltext_value = fulltext_params.pop("fulltext_facet", "")
        fulltext_params.pop("page", None)
        for key, value in fulltext_params.items():
            if not isinstance(value, (tuple, list)):
                fulltext_params[key] = [value]

        search_summary = self.search_summary
        self.w(
            self.template.render(
                req=self._cw,
                _=self._cw._,
                response=response,
                results_title=self.format_results_title(response),
                display_fulltext_facet=bool(response.hits.total.value),
                display_facets=bool(response.hits.total.value),
                fulltext_form_action=self._cw.build_url(
                    self._cw.relative_path(includeparams=False)
                ),
                fulltext_params=fulltext_params,
                fulltext_value=fulltext_value,
                search_results=self.build_results(response),
                search_summary=search_summary,
                reset_all_facets_link=self.reset_all_facets_link(),
                pagination=self.pagination(response.hits.total.value),
                header=self.get_header_attrs(),
                letters=self.letters(),
                items_per_page_links=self.items_per_page_links(),
                display_sort_options=False,
                page_number_params=self.page_number_params(),
                page_number_form_action=self._cw.build_url(
                    self._cw.relative_path(includeparams=False)
                ),
                text_lead=self._cw._("quality_authorities_explanation_text"),
                current_page=int(self._cw.form.get("page", 1)),
                number_of_pages=self.number_of_pages(response.hits.total.value),
            )
        )


class PniaSubjectAuthoriesElasticSearchView(PniaAuthoritiesElasticSearchView):
    __regid__ = "subjects"
    cw_etype = "SubjectAuthority"
    title = _("Quality themes")
    title_count_templates = (_("No themes"), _("1 theme"), _("{count} themes"))
    eulerian_search_engine = "subjects_search"
    eulerian_path = "/authorities/search/subjects"


class PniaAgentAuthoriesElasticSearchView(PniaAuthoritiesElasticSearchView):
    __regid__ = "agents"
    cw_etype = "AgentAuthority"
    title = _("Quality persons/organizations")
    title_count_templates = (
        _("No persons/organizations"),
        _("1 person/organization"),
        _("{count} persons/organizations"),
    )
    eulerian_search_engine = "agents_search"
    eulerian_path = "/authorities/search/agents"


class PniaLocationAuthoriesElasticSearchView(PniaAuthoritiesElasticSearchView):
    __regid__ = "locations"
    cw_etype = "LocationAuthority"
    title = _("Quality locations")
    title_count_templates = (_("No locations"), _("1 location"), _("{count} locations"))
    eulerian_search_engine = "locations_search"
    eulerian_path = "/authorities/search/locations"
