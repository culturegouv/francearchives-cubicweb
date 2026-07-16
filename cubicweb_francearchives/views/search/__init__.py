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
import math

from logilab.common.decorators import cachedproperty
from logilab.mtconverter import xml_escape

from elasticsearch.exceptions import RequestError

from elasticsearch_dsl.response import Response
from elasticsearch_dsl.search import Search

from cubicweb_elasticsearch.views import ElasticSearchView
from cubicweb_elasticsearch.search_helpers import is_simple_query_string

from cwtags import tag as T

from cubicweb import _, NoResultError
from cubicweb.predicates import is_instance, match_form_params
from cubicweb.schema import display_name
from cubicweb.uilib import cut
from cubicweb.rset import ResultSet
from cubicweb_web.views.baseviews import InContextView
from cubicweb_web.views.primary import PrimaryView

from cubicweb_skos.views import ConceptPrimaryView
from cubicweb_francearchives.entities import DOC_CATEGORY_ETYPES
from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.views import get_template, rebuild_url, FaqMixin
from cubicweb_francearchives.views.eulerian import normalize_eulerian_value
from cubicweb_francearchives.views.search.facets import (
    FACETED_SEARCHES,
    PniaCWFacetedSearch,
    FACET_RENDERERS,
)
from cubicweb_francearchives.utils import reveal_glossary, format_number, find_card


ETYPES_MAP = {
    "Virtual_exhibit": "ExternRef",
    "Blog": "ExternRef",
    "Other": "ExternRef",
    "Publication": "BaseContent",
    "SearchHelp": "BaseContent",
    "Article": "BaseContent",
}


class FakeResponse(Response):
    def __init__(self):
        response = {
            "hits": {"hits": [], "total": {"value": 0, "relation": ""}},
            "facets": {},
        }
        super(FakeResponse, self).__init__(Search(), response)


class PaginationMixin:
    items_per_page_options = [10, 25, 50]
    default_items_per_page = 10

    def get_current_form_params(self):
        return self._cw.form.copy()

    @cachedproperty
    def current_items_per_page(self):
        try:
            current_items_per_page = int(
                self.get_current_form_params().get("items_per_page", self.default_items_per_page)
            )
        except ValueError:
            current_items_per_page = self.default_items_per_page
        return current_items_per_page

    def items_per_page_links(self):
        """
        Returns links with the items_per_page and their label
        """
        url_params = {}

        links = []
        for value in self.items_per_page_options:
            if value != self.default_items_per_page:
                url_params["items_per_page"] = value
            else:
                url_params["items_per_page"] = None
            links.append(
                {
                    "label": value,
                    "url": rebuild_url(self._cw, replace_keys=True, **url_params),
                }
            )
        return {"current_label": self.current_items_per_page, "options_links": links}

    def page_number_params(self):
        """
        Returns a set of arguments for the page number input form
        """
        page_number_params = self._cw.form.copy()
        page_number_params.pop("page", None)
        for key, value in page_number_params.items():
            if not isinstance(value, (tuple, list)):
                page_number_params[key] = [value]
        return page_number_params

    def number_of_pages(self, number_of_items):
        items_per_page = self.current_items_per_page
        number_of_pages = int(math.ceil(number_of_items / float(items_per_page)))
        max_pages = int(math.ceil(10000 / float(items_per_page)))  # elasticsearch limit
        return min(number_of_pages, max_pages)

    @cachedproperty
    def get_current_page(self):
        try:
            return int(self._cw.form.get("page", 1))
        except ValueError:
            return 1

    def pagination(
        self, number_of_items, items_per_page=10, max_pages=1000, max_pagination_links=4
    ):
        """
        Pagination structure generation
        """
        _ = self._cw._
        url_params = self._cw.form.copy()
        # 10 is the default items_per_page value in the elasticsearch cube
        items_per_page = int(url_params.get("items_per_page", self.default_items_per_page))

        pagination = []
        if number_of_items <= items_per_page:
            return pagination

        url_params = self._cw.form.copy()
        try:
            current_page = int(url_params.get("page", 1))
        except ValueError:
            current_page = 1

        number_of_pages = self.number_of_pages(number_of_items)
        if current_page < 1 or current_page > number_of_pages:
            return pagination

        pages_to_show = self.get_pages_to_show(current_page, number_of_pages)
        url_params["page"] = 1
        # pagination.append(
        #     {
        #         "name": _("First page"),
        #         "link": xml_escape(self._cw.build_url(**url_params)),
        #         "title": xml_escape(_("Go to the first page")),
        #         "class": "fr-pagination__link fr-pagination__link--first",
        #         "disabled": bool(current_page == 1),
        #     }
        # )
        if current_page > 1:
            url_params["page"] = current_page - 1
            pagination.append(
                {
                    "name": _("Previous page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to the previous page")),
                    "class": "fr-pagination__link fr-pagination__link--prev",  # noqa
                }
            )
        previous = 0
        for page_to_show in pages_to_show:
            if previous + 1 != page_to_show:
                pagination.append(
                    {
                        "name": "&#8230;",
                        "class": "fr-pagination__item fr-ellipsis",
                        "ellipsis": True,
                    }
                )
            pagination.append(self.page_link(url_params, page_to_show, current_page))
            previous = page_to_show
        # Link to next page and last page
        if current_page < number_of_pages:
            url_params["page"] = current_page + 1
            pagination.append(
                {
                    "name": _("Next page"),
                    "link": xml_escape(self._cw.build_url(**url_params)),
                    "title": xml_escape(_("Go to the next page")),
                    "class": "fr-pagination__link fr-pagination__link--next",  # noqa
                }
            )
        url_params["page"] = number_of_pages
        # pagination.append(
        #     {
        #         "name": _("Last page"),
        #         "link": xml_escape(self._cw.build_url(**url_params)),
        #         "title": xml_escape(_("Go to the last page")),
        #         "class": "fr-pagination__link fr-pagination__link--last",
        #         "disabled": bool(current_page == number_of_pages),
        #     }
        # )
        return pagination

    def get_pages_to_show(self, current_page, number_of_pages):
        # we will always display the fist and the last page
        pages_to_show = [1]
        if number_of_pages == 1:
            return pages_to_show
        if 1 < current_page < number_of_pages:
            if (current_page - 1) > 1:
                pages_to_show.append(current_page - 1)
            pages_to_show.append(current_page)
            if (current_page + 1) < number_of_pages:
                pages_to_show.append(current_page + 1)
        if number_of_pages > 2:
            if current_page == 1:
                pages_to_show.append(current_page + 1)
            if current_page == number_of_pages:
                pages_to_show.append(current_page - 1)
        pages_to_show.append(number_of_pages)
        return pages_to_show

    def page_link(self, url_params, page, current_page):
        """
        Return info on a given page number
        """
        url_params["page"] = page
        url = self._cw.build_url(**url_params)
        page_link = {
            "name": page,
            "link": xml_escape(url),
            "title": xml_escape("{} {}".format(self._cw._("Page"), page)),
            "class": "fr-pagination__link",
        }
        if page == current_page:
            page_link["current"] = True
        return page_link


class EulerianMixin:
    eulerian_tag = True
    eulerian_pagegroup = "search"

    @property
    def eulerian_events(self):
        return self.eulerian_global_search_event()

    @property
    def eulerian_actions(self):
        return {"page_type": self.eulerian_pagegroup}

    @property
    def get_results_number(self):
        response, query_string = self.cached_search_response
        return response.hits.total.value

    def eulerian_global_search_event(self):
        search_summary = self.search_summary
        globalargs = [("isearchengine", self.eulerian_search_engine)]
        globalargs.append(("isearchresults", str(self.get_results_number)))
        query = self._cw.form.get("q", self._cw.form.get("search", "")).strip()
        if query:
            globalargs.extend(
                (
                    ("isearchkey", "search_term"),
                    ("isearchdata", normalize_eulerian_value(query)),
                )
            )
        # retrieve data from facets
        context = search_summary.get("context")
        categories = self._cw.form.get("es_escategory")
        if categories:
            if not isinstance(categories, (list, tuple)):
                categories = normalize_eulerian_value(categories)
            else:
                categories = ",".join([normalize_eulerian_value(c) for c in categories])
            globalargs.extend((("isearchkey", "category"), ("isearchdata", categories)))
        if context and "inventory" in context:
            services = self.get_selected_services_codes
            if services:
                value = [normalize_eulerian_value(s) for s in services]
                globalargs.extend((("isearchkey", "service"), ("isearchdata", value[0])))
        for data in search_summary.get("summary", ()):
            key = normalize_eulerian_value(data["name"])
            value = ",".join([normalize_eulerian_value(v[0]) for v in data["value"]])
            globalargs.extend((("isearchkey", key), ("isearchdata", value)))
        return tuple(globalargs)


class PniaElasticSearchView(EulerianMixin, FaqMixin, PaginationMixin, ElasticSearchView):
    no_term_msg = _("Contenu")
    title_count_templates = (_("No result"), _("1 result"), _("{count} results"))
    display_results_info = True
    template = get_template("searchlist.jinja2")
    document_categories = (
        ("", _("All documents")),
        ("archives", _("###in archives###")),
        ("siteres", _("###site resources###")),
    )
    faq_category = "02_faq_search"
    site_tour_url = "search-tour.json"
    display_sort_options = True
    service_facet_name = "publisher"
    display_date_facet = True
    _es_error = False

    @property
    def eulerian_path(self):
        if self.advanced_search:
            return "/advanced_search"
        relative_path = f"/{self._cw.relative_path(False).rstrip('/')}"
        if not relative_path or relative_path == "/search":
            return "/search"
        return f"/search{normalize_eulerian_value(relative_path)}"

    @property
    def eulerian_search_engine(self):
        if self.advanced_search:
            return "advanced_search"
        return "main_search"

    @property
    def eulerian_pagegroup(self):
        if self.advanced_search:
            return "advanced_search"
        return "search"

    @property
    def eulerian_events(self):
        if self.advanced_search:
            return self.eulerian_advanced_search_event()
        return self.eulerian_global_search_event()

    def eulerian_advanced_search_event(self):
        globalargs = [("isearchengine", "advanced_search")]
        globalargs.append(("isearchresults", str(self.get_results_number)))
        for key, value in self._cw.form.items():
            if key in ("advanced",):
                continue
            if key == "searches":
                key = "search_term"
            if not isinstance(value, (list, tuple)):
                value = normalize_eulerian_value(value)
            else:
                value = ",".join([normalize_eulerian_value(c) for c in value])
            if value:
                globalargs.extend((("isearchkey", key), ("isearchdata", value)))
        return tuple(globalargs)

    @cachedproperty
    def skip_in_summary(self):
        hide_cw_facet = self._cw.form.get("restrict_to_single_etype", False)
        if hide_cw_facet:
            return ("es_cw_etype",)
        return ()

    @cachedproperty
    def cached_search_response(self):
        query_string = self._cw.form.get("q", self._cw.form.get("search", ""))
        if hasattr(self, "_esresponse"):
            return self._esresponse, query_string
        # TODO - remove _cw.form.get('search') when URL transition is over
        try:
            self._esresponse = self.do_search(query_string)
        except Exception as err:
            self.exception(err)
            self._esresponse = FakeResponse()
            self._es_error = err
        return self._esresponse, query_string

    def search_etype_label(self):
        _ = self._cw._
        etype = self._cw.form.get("es_cw_etype")
        bc_label = None
        if etype:
            if etype == "Service":
                bc_label = _("Service Directory")
            elif not isinstance(etype, list):
                bc_label = display_name(self._cw, etype, "plural")
        return bc_label

    def search_title(self):
        _ = self._cw._
        response, query_string = self.cached_search_response
        title = []
        form = self._cw.form
        search_term = form.get("q", form.get("fulltext_facet"))
        title.append(_("Search results"))
        if search_term:
            title.append(_('on term "%s"') % search_term)
        etype_label = self.search_etype_label()
        if etype_label:
            title.append(_('for "%s"') % etype_label)
        if not title:
            title.append(self._cw._(self.title))
        if response:
            number_of_pages = self.number_of_pages(response.hits.total.value)
            if number_of_pages:
                page = form.get("page", 1)
                page = page if str(page).isdigit() else 1
                title.append("[{}]".format(_("page %s on %s") % (page, number_of_pages)))
        title.append("({})".format(self._cw.property_value("ui.site-title")))
        return xml_escape(" ".join(title))

    def page_title(self):
        """returns a title according to the result set - used for the
        title in the HTML header. Add"""
        title = self.search_title()
        return "{} ({})".format(title, self._cw.property_value("ui.site-title"))

    def breadcrumbs(self):
        _ = self._cw._
        bc_label = self.search_etype_label()
        if not bc_label or len(bc_label) > 1:
            bc_label = _("search-breadcrumb-label")
        return [
            (self._cw.build_url(""), _("Home")),
            # don't use dc_title() to avoid displaying wikiid
            (None, bc_label),
        ]

    @cachedproperty
    def get_selected_services_names(self):
        return [v["name"] for v in self.get_selected_services.values()]

    @cachedproperty
    def get_selected_services_codes(self):
        return [v["code"] for v in self.get_selected_services.values()]

    @cachedproperty
    def get_selected_services(self):
        if hasattr(self, "_selected_services"):
            return self._selected_services
        self._selected_services = {}
        value = self._cw.form.get(f"es_{self.service_facet_name}", None)
        if not isinstance(value, (list, tuple)):
            value = [value]
        try:
            for eid, name, code in self._cw.execute(
                """Any X, SN, C WHERE X is Service, X eid IN (%(s)s),
                      X code C, X short_name SN"""
                % {"s": ", ".join([str(v) for v in value])},
            ):
                self._selected_services[eid] = {"name": name, "code": code}
        except Exception:
            pass
        return self._selected_services

    def template_context(self):
        return {
            "heroimages": False,
            "breadcrumbs": self.breadcrumbs(),
            "meta": [("robots", "noindex")],
            "faqs": self.faqs_attrs(),
        }

    def format_results_title(self, response):
        count = response.hits.total.value if response is not None else 0
        if count == 0:
            tmpl = self.title_count_templates[0]
        elif count == 1:
            tmpl = self.title_count_templates[1]
        else:
            tmpl = self.title_count_templates[2]
        return self._cw._(tmpl).format(count=format_number(count, self._cw))

    @cachedproperty
    def search_summary(self):
        if not hasattr(self, "_search_summary"):
            self._search_summary = self.compute_search_summary()
        return self._search_summary

    def compute_search_summary(self):
        """Do not translate labels here as this function is used for
        eulerian tags as well"""
        facets = self._cw.form
        summary = []
        fulltext_summary = []
        inventory = facets.get("inventory", None)
        service_labels = {}
        skip_in_summary = self.skip_in_summary
        if facets.get("advanced"):
            skip_in_summary += ("es_date_max", "es_date_min")
        dzfv = DZFacetValues
        for key, value in facets.items():
            summary_value = {}
            if key == "es_publisher" and value:
                service_labels = self.get_selected_services_names
                if inventory:
                    if service_labels:
                        inventory = service_labels[0]
                    else:
                        inventory = ""
                    continue
            if key in skip_in_summary:
                continue
            if key.startswith("es_"):
                # get the facet label requires to remove the "es_" substring
                facetlabel = [x[1] for x in self.facets_to_display if x[0] == key[3:]]
                if key == "es_date_min" and value:
                    summary_value["name"] = _("date-min-facet")
                elif key == "es_date_max" and value:
                    summary_value["name"] = _("date-max-facet")
                elif len(facetlabel) > 0:
                    summary_value["name"] = facetlabel[0]
                else:
                    continue
                if not isinstance(value, (list, tuple)):
                    value = [value]
                data = []
                value = sorted([str(val).strip() for val in value if val])
                for val in value:
                    if key == "es_digitized_all":
                        vals = [val]
                        if val == dzfv.dz:
                            vals += dzfv.dzitems().keys()
                        if val in dzfv.dzitems().keys():
                            vals += [dzfv.dz]
                        url_params = {key: list(set(value).difference(vals))}
                        val = f"{val}_value"
                    else:
                        url_params = {key: list(set(value).difference([val]))}
                    reset_url = rebuild_url(self._cw, replace_keys=True, **url_params)
                    if key == "es_publisher":
                        if val.isnumeric():
                            res = self.get_selected_services.get(int(val))
                            if res:
                                val = res["name"]
                    elif key == "es_is_published":
                        val = (
                            self._cw._("published")
                            if (val == "True" or val is True)
                            else self._cw._("draft")
                        )
                    data.append([val, reset_url])
                summary_value["value"] = data
            elif key == "fulltext_facet":
                value = value.strip()
                if value:
                    reset_url = rebuild_url(self._cw, **{key: None})
                    fulltext_summary.append((value, reset_url))

            if summary_value and key != "es_escategory":
                summary.append(summary_value)
        if fulltext_summary:
            summary.insert(0, {"name": _("Contains"), "value": fulltext_summary})
        context = {}
        query = self._cw.form.get("q", self._cw.form.get("search", "")).strip()
        if query:
            context["query"] = query
        section = self._cw.form.get("ancestors")
        if section:
            try:
                section = self._cw.find("Section", eid=self._cw.form["ancestors"]).one()
                context["section"] = section.cw_adapt_to("ITemplatable").entity_param().title
            except NoResultError:
                pass
        if inventory:
            context["inventory"] = inventory
        search_summary = {}
        if context:
            search_summary["context"] = context
        if summary:
            search_summary["summary"] = summary
        return search_summary

    def reset_all_facets_link(self):
        """Creates a URL which resets the values from the facets to display

        The value of the initial query (parameter q) is kept
        as well as values which come from other SearchView
        """
        url_params = {}
        facets = self.facets_to_display
        for facet in facets:
            url_params["es_{}".format(facet[0])] = None
        url_params["fulltext_facet"] = None
        url_params["es_date_min"] = None
        url_params["es_date_max"] = None
        return rebuild_url(self._cw, **url_params)

    @cachedproperty
    def sort_with_pertinance(self):
        for f in ("q", "fulltext_facet"):
            if self._cw.form.get(f):
                return True
        return False

    @cachedproperty
    def is_archives_sort(self):
        return (
            self._cw.form.get("es_cw_etype") in ("FAComponent", "FindingAid")
            or self._cw.form.get("inventory")
            or self._cw.form.get("es_escategory") == "archives"
            or not set(self._cw.form.get("es_cw_etype")).difference({"FAComponent", "FindingAid"})
        )

    @cachedproperty
    def get_search_sort(self):
        current_sort_option = self._cw.form.get("sort", ())
        if not current_sort_option and not self.sort_with_pertinance:
            # if pertinance restriction is not involved, we sort on creation_date desc
            return "-creation_date"
        # the option bellow add ~20% to the search time
        # if current_sort_option == "service.title" or self.is_archives_sort:
        #    return (current_sort_option, "-creation_date")
        return current_sort_option

    def sort_options(self, response):
        """
        Returns links with the sort_options and their label
        """
        _ = self._cw._
        url_params = {}
        url_params["page"] = None  # reset page number on new sort
        sort_options = {
            "pertinence": _("Pertinence"),
            "sortdate": _("Date ascending"),
            "-sortdate": _("Date descending"),
            "service.title": _("Publisher"),
        }
        cw_etypes_facet = [x[0] for x in getattr(response.facets, "cw_etype", ())]
        selected_cw_etype = self._cw.form.get("es_cw_etype", None)

        etypes_with_publisher = [
            "Publication",
            "FAComponent",
            "Virtual_exhibit",
            "FindingAid",
            "AuthorityRecord",
        ]

        current_sort_option = self._cw.form.get("sort", "pertinence")

        # Remove publisher sort option when the cw_etype facet does not contain
        # a etypes_with_publisher or when a cw_etype is selected and is not
        # one of etypes_with_publisher
        if (not any(etype in cw_etypes_facet for etype in etypes_with_publisher)) or (
            selected_cw_etype
            and not any(etype in selected_cw_etype for etype in etypes_with_publisher)
        ):
            sort_options.pop("service.title", None)

        # fallback to the default sort option option if the requested option doesn't exist
        if current_sort_option not in sort_options:
            current_sort_option = "pertinence"

        links = []
        for value, label in sort_options.items():
            if value != "pertinence":
                url_params["sort"] = value
            else:
                url_params["sort"] = None
            links.append(
                {
                    "label": label,
                    "url": rebuild_url(self._cw, replace_keys=True, **url_params),
                }
            )
        return {
            "current_label": sort_options[current_sort_option],
            "options_links": links,
        }

    def add_css(self):
        pass

    def add_js(self):
        self._cw.add_js("bundle-pnia-search.js")

    @property
    def advanced_search(self):
        if not hasattr(self, "_advanced_search"):
            self._advanced_search = bool(self._cw.form.get("advanced", False))
        return self._advanced_search

    def call(self, context=None, **kwargs):
        self.add_js()
        self.add_css()
        results = self.build_template_data(context=context)
        self.write_template(results)

    def handle_error(self):
        if not self._es_error:
            return {}
        _ = self._cw._
        if isinstance(self._es_error, (RequestError, KeyError)):
            alert = {
                "text": _(
                    "There is a problem with request's parameters. "
                    "Please, retry an other request."
                ),
                "title": _("Search inaccessible"),
            }
        else:
            # isinstance(self._es_error, ConnectionError):
            alert = {
                "text": _("es_inaccessible_search"),
                "title": _("Search inaccessible"),
            }
        return alert

    def build_template_data(self, context=None):
        response, query_string = self.cached_search_response
        # handle fuzzy options
        if not self._es_error:
            fuzzy_options = self.compute_fuzzy_search_options(response, query_string)
            # augmented search (SubjectAuhtorities only)
            augmented_search_options = self.compute_augmented_search_options(response, query_string)
        else:
            fuzzy_options, augmented_search_options = {}, {}
        # handle fulltext
        fulltext_params = self.get_current_form_params()
        fulltext_value = fulltext_params.pop("fulltext_facet", "")
        fulltext_params.pop("page", None)
        for key, value in fulltext_params.items():
            if not isinstance(value, (tuple, list)):
                fulltext_params[key] = [value]

        date_params = self.get_current_form_params()
        facet_date_unfolded = any((p in date_params for p in ("es_date_min", "es_date_max")))
        es_date_min = date_params.pop("es_date_min", "")
        es_date_max = date_params.pop("es_date_max", "")
        date_params.pop("page", None)
        for key, value in date_params.items():
            if not isinstance(value, (tuple, list)):
                date_params[key] = [value]

        search_summary = self.search_summary
        return dict(
            req=self._cw,
            _=self._cw._,
            response=response,
            error=self.handle_error(),
            results_title=self.format_results_title(response),
            query_string=query_string,
            display_facets=bool(response.hits.total.value),
            display_fulltext_facet=True,
            fulltext_form_action=self._cw.build_url(self._cw.relative_path(includeparams=False)),
            fulltext_params=fulltext_params,
            fulltext_value=fulltext_value,
            facets=self.build_facets(response, context),
            search_title=self._cw._(self.no_term_msg),
            search_results=self.build_results(response),
            pagination=self.pagination(response.hits.total.value),
            restrict_to_single_etype=self._cw.form.get("restrict_to_single_etype", False),
            search_summary=search_summary,
            reset_all_facets_link=self.reset_all_facets_link(),
            header=self.get_header_attrs(),
            is_authority_view=self.__regid__ == "indexes-esearch",
            items_per_page_links=self.items_per_page_links(),
            sort_options=self.sort_options(response),
            display_sort_options=self.display_sort_options,
            page_number_params=self.page_number_params(),
            page_number_form_action=self._cw.build_url(self._cw.relative_path(includeparams=False)),
            current_page=self.get_current_page,
            number_of_pages=self.number_of_pages(response.hits.total.value),
            display_date_facet=self.display_date_facet,
            date_facet_unfolded=self.display_date_facet and (es_date_min or es_date_max),
            es_date_min=es_date_min,
            es_date_max=es_date_max,
            date_params=date_params,
            facet_date_unfolded=facet_date_unfolded,
            fuzzy_extra_link=fuzzy_options.get("extra_link"),
            augmented_extra_link=augmented_search_options.get("extra_link"),
            site_tour_url=self.get_site_tour_url(),
            rdf_formats=self.get_rdf_formats(),
            advanced_search=self.advanced_search,
            eulerian=self.eulerian_actions,
            lang=self._cw.lang,
        )

    def write_template(self, data):
        self.w(self.template.render(data))

    def get_site_tour_url(self):
        if self.site_tour_url:
            return self._cw.build_url(self.site_tour_url)

    def get_header_attrs(self):
        return None

    def get_rdf_formats(self):
        return None

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
            cw_etype = getattr(result, "cw_etype", "FindingAid")
            if cw_etype == "Article":
                cw_etype = getattr(result, "estype", cw_etype)
            return cw_etype

        req = self._cw
        descr, rows = [], []
        for idx, result in enumerate(response):
            # safety belt, in v0.6.0, PDF are indexed without a cw_etype field
            cw_etype = get_etype_from_result(result)
            # safety belt for import-ead with esonly=True: in that case,
            # ES documents don't have eids
            if not result.eid:
                ir_rset = self._cw.execute(
                    "Any X WHERE X is {}, X stable_id %(s)s".format(cw_etype),
                    {"s": result.stable_id},
                )
                if ir_rset:
                    eid = ir_rset[0][0]
                else:
                    continue
            else:
                eid = result.eid
            descr.append((ETYPES_MAP.get(cw_etype, cw_etype), "String"))
            if hasattr(result, "stable_id"):
                rows.append([eid, result.stable_id])
            else:
                rows.append([eid, "foo"])
        rset = ResultSet(rows, "Any X", description=descr)
        if not rset and descr == "Article":
            rset = ResultSet(rows, "Any X", description="Card")
        rset.req = req
        return rset

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
                    getattr(item_response, "cw_etype", "?FindingAid?"),
                )
                continue
            results.append(entity.view("pniasearch-item", es_response=item_response))
        return results

    def compute_augmented_search_options(self, response, query_string):
        """augmented_search is active only in SubjectAuhtorities"""
        return {}

    def compute_fuzzy_search_options(self, response, query_string):
        search_is_fuzzy = "fuzzy" in self._cw.form
        extra_link = {}
        search_contains_operators = is_simple_query_string(query_string)
        if search_is_fuzzy and query_string:
            url_params = self._cw.form.copy()
            del url_params["fuzzy"]

            if "page" in self._cw.form:
                del url_params["page"]
            pretext = self._cw._("Fuzzy search is activated.")
            # if self._cw.lang == "fr":
            #     pretext = reveal_glossary(self._cw, pretext)
            extra_link = {
                "href": self._cw.build_url(**url_params),
                "title": self._cw._("regular search"),
                "pretext": pretext,
                "text": self._cw._("Restart the query with regular search."),
            }
        if response.hits.total.value == 0 and not search_is_fuzzy and not search_contains_operators:
            url_params = self._cw.form.copy()
            url_params["fuzzy"] = True
            if "indexentry" in self._cw.form:
                del url_params["indexentry"]

            if "page" in self._cw.form:
                del url_params["page"]

            text = self._cw._("with fuzzy search option.")
            if self._cw.lang == "fr":
                text = reveal_glossary(self._cw, text)
            extra_link = {
                "href": self._cw.build_url(**url_params),
                "title": self._cw._("fuzzy search activation"),
                "pretext": self._cw._("For more results,"),
                "text": self._cw._("restart the query"),
                "posttext": text,
            }

        # if more than 200 results and search is not already exact and not in a fuzzy search
        if (
            response.hits.total.value >= 200
            and " " in query_string.strip()
            and not search_contains_operators
            and not search_is_fuzzy
        ):
            url_params = self._cw.form.copy()
            exact_expression = f'"{query_string}"'
            url_params["q"] = exact_expression
            if "page" in self._cw.form:
                del url_params["page"]
            extra_link = {
                "href": self._cw.build_url(**url_params),
                "title": self._cw._("Exact search"),
                "pretext": self._cw._("For more specific results,"),
                "text": self._cw._("try the exact expression search {}").format(
                    xml_escape(exact_expression)
                ),
            }
        return {"extra_link": extra_link, "search_is_fuzzy": search_is_fuzzy}

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        """
        Customized search with :

        * cote:unittid
        """
        if query_string.startswith("cote:"):
            query_string = query_string.split(":")[1]
            facet_selections["unitid"] = query_string
        # use .get() instead of "key in" to ensure we have a non-empty value
        if facet_selections.get("cw_etype"):
            etype = facet_selections["cw_etype"]
            if etype and not isinstance(etype, list):
                search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
            else:
                search_class = PniaCWFacetedSearch
        elif facet_selections.get("escategory"):
            categories = facet_selections.get("escategory")
            # if category corresponds to a single etype and if this etype
            # has a specific facet definition, use it
            if not isinstance(categories, list):
                categories = [categories]
            for category in categories:
                # FIXME To be changed to suit the new facet interface with no vertical facets
                if category in DOC_CATEGORY_ETYPES and len(DOC_CATEGORY_ETYPES[category]) == 1:
                    etype = DOC_CATEGORY_ETYPES[category][0]
                    search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
                else:
                    search_class = PniaCWFacetedSearch
        else:
            search_class = PniaCWFacetedSearch
        if "indexentry" in self._cw.form:
            rset = self._cw.execute(
                "Any L, E WHERE X eid %(e)s, X label L, X is ET, ET name E",
                {"e": self._cw.form["indexentry"]},
            )
            if rset:
                query_string, cw_etype = rset[0]
                search_class = FACETED_SEARCHES.get(cw_etype.lower())
            else:
                search_class = FACETED_SEARCHES.get("indexentry")
        default_index_name = "{}_all".format(self._cw.vreg.config.get("index-name"))
        # remove selected items not available in facet eg : select FAComponent,
        # then select digitized, then deselected FAComponent digitized is then
        # not available anymore - should that deselect not be shown ?  should
        # the deselect link take that into account and remove that item from the
        # url_params ? (more difficult) - this avoids having a confusing param
        # in URL
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(search_class.facets.keys()):
                del facet_selections[facet_searched]
        kwargs["fulltext_facet"] = self._cw.form.get("fulltext_facet")
        kwargs["es_date_max"] = self._cw.form.get("es_date_max")
        kwargs["es_date_min"] = self._cw.form.get("es_date_min")
        kwargs["es_escategory"] = self._cw.form.get("es_escategory")
        kwargs["cw_etype"] = facet_selections.get("cw_etype")
        kwargs["sort"] = self.get_search_sort
        kwargs["fulltext_facet"] = self._cw.form.get("fulltext_facet")
        kwargs["es_date_max"] = self._cw.form.get("es_date_max")
        kwargs["es_date_min"] = self._cw.form.get("es_date_min")
        kwargs["searches"] = self._cw.form.get("searches")
        kwargs["searches_op"] = self._cw.form.get("searches_op")
        kwargs["searches_t"] = self._cw.form.get("searches_t")
        kwargs["services"] = self._cw.form.get("services")
        kwargs["services_op"] = self._cw.form.get("services_op")
        kwargs["producers"] = self._cw.form.get("producers")
        kwargs["producers_op"] = self._cw.form.get("producers_op")
        kwargs["producers_t"] = self._cw.form.get("producers_t")
        return search_class(
            query_string,
            facet_selections,
            index=default_index_name,
            form=self._cw.form,
            **kwargs,
        )[start:stop]

    def build_facets(self, response, context):
        """
        Generate HTML for facets
        """
        req = self._cw
        facets = []
        hide_cw_facet = self._cw.form.get("restrict_to_single_etype", False)
        for facetid, facetlabel in self.facets_to_display:
            if facetid == "cw_etype" and hide_cw_facet:
                continue
            # response.facets is an instance of AttrDict
            facet = getattr(response.facets, facetid, ())
            if len(facet) == 0:
                continue
            facet_render = FACET_RENDERERS.get(facetid) or FACET_RENDERERS["default"]
            facet_html = facet_render(req, facet, facetid, facetlabel, context, response)
            if facet_html:
                facets.append(facet_html)
        return facets

    def customize_infos(self, infos):
        """
        This is where one can customize the infos being displayed

        For example : set the title according to your rules and data set
        """
        infos.setdefault(
            "title",
            infos.get("name", infos.get("reference", infos.get("unittitle", "n/a"))),
        )

    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        """
        _ = self._cw._
        return (
            ("digitalized", _("digitalized_facet")),
            ("cw_etype", _("document_type_facet")),
            ("publisher", _("publishers_facet")),
            ("status", _("status_facet")),
            ("originators", _("originators_facet")),
        )


class PniaElasticSearchWithContextView(PniaElasticSearchView):
    __abstract__ = True
    site_tour_url = None

    def display_contextual_info(self):
        w, _ = self.w, self._cw._
        with T.div(w, id="section-article-header"):
            w(T.h2(_("contexte de la recherche")))
            for info in self.get_infos():
                with T.div(w, Class="documents-fonds"):
                    w(info)

    def call(self, **kwargs):
        self.display_contextual_info()
        super(PniaElasticSearchWithContextView, self).call(**kwargs)


circular_facet_active = match_form_params(es_cw_etype="Circular")

service_facet_active = match_form_params(es_cw_etype="Service")

section_facet_active = match_form_params(es_cw_etype="Section")


class SearchCmsChildrenView(PniaElasticSearchView):
    __select__ = (
        PniaElasticSearchView.__select__
        & match_form_params("ancestors")
        & ~circular_facet_active
        & ~service_facet_active
    )
    display_sort_options = False
    display_results_info = False
    title_count_templates = (
        _("No documents in this section"),
        _("1 document in this section"),
        _("{count} documents in this section"),
    )

    @cachedproperty
    def get_search_sort(self):
        entity = self._cw.find("Section", eid=self._cw.form["ancestors"]).one()
        order = entity.children_sorting_order
        if order:
            order = entity.children_sorting_order.split()
        return order or "-creation_date"

    def get_themes_for_section(self, section, url_params=None):
        req = self._cw
        themes_rset = req.execute(
            """Any A, L, DH, DN, O ORDERBY O, L LIMIT 9 WHERE
            X eid %(e)s,
            X section_themes OA, OA order O,
            OA subject_entity A, A label L,
            A subject_image I, I image_file F,
            F data_hash DH, F data_name DN
            """,
            {"e": section.eid},
        )
        if not themes_rset:
            return []
        entities = []
        for auth_eid, label, dh, dn, order in themes_rset:
            image_src = req.build_url(f"file/{dh}/{dn}")
            url = f"subject/{auth_eid}"
            if url_params:
                url = rebuild_url(req, url=url, replace_keys=True, **url_params)
            entities.append(
                {
                    "url": req.build_url(url),
                    "label": label,
                    "image_src": image_src,
                    "order": order,
                }
            )
        return entities

    def call(self, context=None, **kwargs):
        self.add_js()
        self.add_css()
        results = self.build_template_data(context=context)
        entity = self._cw.find("Section", eid=self._cw.form["ancestors"]).one()
        if entity.display_mode == "mode_themes":
            # compute themes from results and add ancestors and cw_etype params
            # in subject url (cf. #74094377)
            url_params = {"ancestors": self._cw.form["ancestors"]}
            response = results["response"]
            etype = self._cw.form.get("restrict_to_single_etype", None)
            if etype is None:
                etypes = getattr(response.facets, "cw_etype", ())
                if len(etypes) == 1:
                    etype = etypes[0][0]
            if etype:
                url_params["cw_etype"] = etype
            themes = self.get_themes_for_section(entity, url_params=url_params)
            if themes:
                self.w(entity.view("section-themes", themes=themes))
        self.write_template(results)

    def customize_search(self, query_string, facet_selections, start=10, stop=None, **kwargs):
        req = self._cw
        # a req.form.pop("ancestors") was previously used
        query_string = req.form["ancestors"]
        etype = facet_selections.get("cw_etype", "section")
        if not isinstance(etype, list):
            search_class = FACETED_SEARCHES.get(etype.lower(), PniaCWFacetedSearch)
        else:
            search_class = PniaCWFacetedSearch
        default_index_name = "{}_all".format(self._cw.vreg.config.get("index-name"))
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(search_class.facets.keys()):
                del facet_selections[facet_searched]
        kwargs["ancestors-query"] = True
        kwargs["fulltext_facet"] = req.form.get("fulltext_facet")
        kwargs["es_date_min"] = req.form.get("es_date_min")
        kwargs["es_date_max"] = req.form.get("es_date_max")
        kwargs["sort"] = self.get_search_sort
        return search_class(
            query_string,
            facet_selections,
            index=default_index_name,
            form=self._cw.form,
            **kwargs,
        )[start:stop]


class PniaElasticSearchNewsContent(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & match_form_params(es_cw_etype="NewsContent")
    display_sort_options = False


class PniaElasticSearchMapContent(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & match_form_params(es_cw_etype="Map")
    display_date_facet = False


class PniaElasticSearchService(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & service_facet_active
    site_tour_url = None
    display_date_facet = False

    @property
    def facets_to_display(self):
        _ = self._cw._
        return (
            ("cw_etype", _("document_type_facet")),
            ("level", _("service_level_facet")),
            ("partner", _("service_partner_facet")),
        )

    def get_header_attrs(self):
        return {"title": self._cw._("Directory of archival institutions")}


class PniaElasticSearchSection(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & section_facet_active
    display_date_facet = False


class PniaElasticSearchCirculaires(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & circular_facet_active
    title_count_templates = (
        _("No result"),
        _("1 circulaire"),
        _("{count} circulaires"),
    )
    template = get_template("searchlist-circular.jinja2")
    site_tour_url = None
    display_sort_options = False

    @cachedproperty
    def get_search_sort(self):
        return "-sortdate"

    @property
    def facets_to_display(self):
        _ = self._cw._
        return (
            ("cw_etype", _("document_type_facet")),
            ("status", _("status")),
            ("business_field", _("business_field_facet")),
            ("siaf_daf_signing_year", _("period_facet")),
            ("archival_field", _("archival_field_facet")),
            ("historical_context", _("historical_context_facet")),
        )

    def get_header_attrs(self):
        header = {"title": self._cw._("Circulars")}
        card = find_card(self._cw, "tableau-circulaires")
        if card is not None:
            header["content"] = card.content
        return header


class PniaConceptPrimaryView(PniaElasticSearchCirculaires):
    __regid__ = "primary"
    __select__ = PrimaryView.__select__ & is_instance("Concept")
    title_count_templates = (
        _("No result"),
        _("1 circulaire"),
        _("{count} circulaires"),
    )
    template = get_template("searchlist-concept.jinja2")
    skip_facet = None

    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        Display PniaElasticSearchView but "publisher" facet
        """
        for facet in super().facets_to_display:
            if facet[0] != self.skip_facet:
                yield facet

    @cachedproperty
    def entity(self):
        return self.cw_rset.get_entity(0, 0)

    def breadcrumbs(self):
        return [
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self.entity.dc_title()),
        ]

    def get_header_attrs(self):
        return {"title": self.entity.dc_title()}

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        entity = self.entity
        req = self._cw
        search_class = FACETED_SEARCHES.get("circular", PniaCWFacetedSearch)
        default_index_name = "{}_all".format(self._cw.vreg.config.get("index-name"))
        kwargs["fulltext_facet"] = req.form.get("fulltext_facet")
        kwargs["es_date_max"] = self._cw.form.get("es_date_max")
        kwargs["es_date_min"] = self._cw.form.get("es_date_min")
        req.form["restrict_to_single_etype"] = True
        title = entity.dc_title()
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(search_class.facets.keys()):
                del facet_selections[facet_searched]
        related_circulars = False
        for facet_field in ("business_field", "historical_context", "action"):
            if facet_field not in facet_selections:
                if entity.related(facet_field, role="object"):
                    facet_selections[facet_field] = title
                    self.skip_facet = facet_field
                    related_circulars = True
        if not related_circulars:
            # as there is no documents index on this concept,
            # build a request with no results with a random circular field
            facet_selections["business_field"] = title
        return search_class(query_string, facet_selections, index=default_index_name, **kwargs)[
            start:stop
        ]


class FAInContextView(InContextView):
    __regid__ = "incontext"
    __select__ = InContextView.__select__ & is_instance("FindingAid", "FAComponent")

    max_title_size = 140

    def cell_call(self, row, col, **kwargs):
        entity = self.cw_rset.get_entity(row, col)
        full_title = entity.dc_title()
        cut_title = cut(full_title, self.max_title_size)
        kwargs = {"href": entity.absolute_url()}
        if cut_title != full_title:
            kwargs["title"] = xml_escape(full_title)
        if self._cw.lang == "fr":
            self.w(T.a(xml_escape(cut_title), **kwargs))
        else:
            with T.a(self.w, **kwargs):
                self.w(T.span(xml_escape(cut_title), lang="fr"))


class ServiceInContextView(InContextView):
    __select__ = InContextView.__select__ & is_instance("Service")

    def cell_call(self, row, col, es_response=None, **kwargs):
        entity = self.cw_rset.get_entity(row, col)
        title = entity.dc_title()
        title = xml_escape(title) if title else ""
        if self._cw.lang == "fr":
            self.w(T.a(title, href=entity.absolute_url()))
        else:
            with T.a(self.w, href=entity.absolute_url()):
                self.w(T.span(title, lang="fr"))


class InventoryMixin:
    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        Display PniaElasticSearchView but "publisher" facet
        """
        for facet in super().facets_to_display:
            if facet[0] != self.service_facet_name:
                yield facet

    @cachedproperty
    def service_name(self):
        services = self.get_selected_services_names
        if services:
            return services[0]


class InventoryPrimaryView(InventoryMixin, PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & match_form_params(inventory=True)
    skip_in_summary = ("es_publisher",)

    def get_current_form_params(self):
        all_params = super().get_current_form_params()
        all_params.pop("inventory", None)
        all_params.pop("vid", None)
        all_params.pop("es_publisher", None)
        all_params.pop("es_escategory", None)
        return all_params

    def get_header_attrs(self):
        if self.service_name:
            return {
                "title": "{}{}{}".format(
                    self.service_name,
                    self._cw._(":"),
                    self._cw._("see all referenced archives"),
                )
            }


class PniaElasticSearchAuthorityRecord(PniaElasticSearchView):
    __select__ = PniaElasticSearchView.__select__ & match_form_params(es_cw_etype="AuthorityRecord")
    site_tour_url = None

    def get_header_attrs(self):
        return {"title": self._cw._("AuthorityRecords")}

    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        """
        return (
            ("cw_etype", self._cw._("document_type_facet")),
            ("publisher", self._cw._("publishers_facet")),
        )


def registration_callback(vreg):
    components = (
        (PniaElasticSearchView, ElasticSearchView),
        (PniaConceptPrimaryView, ConceptPrimaryView),
    )
    vreg.register_all(list(globals().values()), __name__, [new for (new, old) in components])
    for new, old in components:
        vreg.register_and_replace(new, old)
