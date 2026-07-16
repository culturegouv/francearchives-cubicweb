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

from datetime import datetime
import pytz

from elasticsearch.exceptions import ConnectionError, RequestError

from logilab.common.decorators import cachedproperty

from cwtags import tag as T
from cubicweb import _
from cubicweb.predicates import match_form_params
from cubicweb_web.view import StartupView

from cubicweb_francearchives.views import rebuild_url

from cubicweb_francearchives.entities.nomina import (
    nomina_translate_codetype,
    format_event_location,
    FORBIDDEN_CSV_EXPORT,
    RM_DOCTYPE,
    normalized_doctype_code,
    build_nomina_faceted_search_kwargs,
)
from cubicweb_francearchives.views import get_template
from cubicweb_francearchives.views.search import (
    FakeResponse,
    PniaElasticSearchView,
    InventoryMixin,
)
from cubicweb_francearchives.utils import formatted_size
from cubicweb_francearchives.entities.nomina import NominaActCodeTypes
from cubicweb_francearchives.views.search.facets import NominaFacetedSearch


def get_service_codes_batch(cw, service_eids):
    """Get service codes for a list of service eids in a single query."""
    if not service_eids:
        return {}
    eids_str = ", ".join(str(eid) for eid in service_eids)
    rset = cw.execute(f"Any X, C WHERE X is Service, X code C, X eid IN ({eids_str})")
    return {eid: code for eid, code in rset}


class PniaNominaElasticSearchView(PniaElasticSearchView):
    __regid__ = "nominarecords"
    items_per_page_options = [100, 200]
    default_items_per_page = 100
    text_facets = ["es_forenames", "es_names", "es_locations"]
    title = _("Search in the name base")
    service_facet_name = "service"
    eulerian_search_engine = "namebase_search"
    eulerian_path = "/nominarecords/search"
    base_search_route = "basedenoms"
    sort_options_threshold = 1000000

    def breadcrumbs(self):
        return (
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self._cw._(self.title)),
        )

    def add_js(self):
        self._cw.add_js("bundle-pnia-search.js")

    def translate_acte_type(self, acte_type):
        return nomina_translate_codetype(acte_type)

    faq_category = "07_faq_nomina"

    @property
    def is_nomina(self):
        return True

    def template_context(self):
        ctx = super().template_context()
        ctx.update(
            {
                "nomina": True,
                "query_forenames": self._cw.form.get("es_forenames", ""),
                "query_names": self._cw.form.get("es_names", ""),
                "query_locations": self._cw.form.get("es_locations", ""),
                "query_fulltext": self._cw.form.get("fulltext_facet", ""),
                "display_nomina_search": False,
                "faqs": self.faqs_attrs(),
            }
        )
        return ctx

    def reset_all_facets_link(self):
        """Creates a URL which resets the values from the facets to display

        The value of the initial query (parameter q) is kept
        as well as values which come from other SearchView
        """
        url_params = {}
        facets = self.facets_to_display
        for facet in facets:
            url_params["es_{}".format(facet[0])] = None
        for key in self.text_facets:
            url_params[key] = None
        url_params["fulltext_facet"] = None
        url_params["es_date_min"] = None
        url_params["es_date_max"] = None
        return rebuild_url(self._cw, **url_params)

    @property
    def is_military_search(self):
        act_types = self._cw.form.get("es_act_type", [])
        if not isinstance(act_types, list):
            act_types = [act_types]
        return any(code in MILITARY_CODES for code in act_types)

    @property
    def typology(self):
        return "basedenoms"

    def _check_export_from_aggregations(self, aggregations, form_params):
        """Check export availability using existing aggregations from main search.

        This avoids making a second ES call by reusing aggregations already
        computed during the main search.

        :param aggregations: ES aggregations from main search response
        :param form_params: search form parameters (not used but kept for API compatibility)
        :return: dict with keys: total (int), has_exportable (bool)
        """
        # Check if aggregations are present
        if not hasattr(aggregations, "act_type_filtered"):
            return {"total": 0, "has_exportable": False}

        has_exportable = False
        service_eids_to_check = set()

        # Analyze aggregations - use filtered aggregation
        act_type_agg = aggregations.act_type_filtered.act_type
        for act_bucket in act_type_agg.buckets:
            code = normalized_doctype_code(act_bucket.key)

            if code not in RM_DOCTYPE:
                # Non-military = exportable
                has_exportable = True
                break
            else:
                # Military: collect service eids
                if hasattr(act_bucket, "service"):
                    for service_bucket in act_bucket.service.buckets:
                        service_eids_to_check.add(int(service_bucket.key))

        # If only military records, check services
        if not has_exportable and service_eids_to_check:
            service_codes = get_service_codes_batch(self._cw, service_eids_to_check)
            for service_code in service_codes.values():
                if service_code not in FORBIDDEN_CSV_EXPORT:
                    has_exportable = True
                    break

        return {
            "total": getattr(self, "total_count", 0),
            "has_exportable": has_exportable,
        }

    def csv_export_props(self):
        """Generate CSV export button properties for search results"""
        _ = self._cw._
        MAX_EXPORT_LIMIT = 10000

        export_info = self._check_export_from_aggregations(
            self._export_aggregations,
            self._cw.form,
        )

        total_results = export_info["total"]
        has_exportable = export_info["has_exportable"]

        # Determine if export is allowed
        can_export = total_results > 0 and total_results <= MAX_EXPORT_LIMIT and has_exportable

        # Build URL with all current search parameters (including pagination)
        url_params = self._cw.form.copy()

        # Inject es_act_type parameter if missing, based on the current view typology
        # This ensures CSV export respects the act_type filtering of specialized views
        if "es_act_type" not in url_params:
            if hasattr(self, "typology"):
                if self.typology == "matricules":
                    url_params["es_act_type"] = MILITARY_CODES
                elif self.typology == "recensements":
                    url_params["es_act_type"] = CENSUS_CODES
                elif self.typology == "etat_civil":
                    url_params["es_act_type"] = CIVILSTATUS_CODES

        csv_url = (
            self._cw.build_url("basedenomsexport/export.csv", **url_params) if can_export else None
        )

        # Calculate estimated size based on total results (up to 10000)
        estimated_size = min(total_results, MAX_EXPORT_LIMIT) * 200  # ~200 bytes per line

        size_label = formatted_size(self._cw, estimated_size)

        tz = pytz.timezone("Europe/Paris")
        timestamp = tz.localize(datetime.now()).strftime("%Y%m%d_%Hh%Mm%Ss")

        # Build filename
        filename = f"francearchives_{self.typology}_{timestamp}.csv" if can_export else None

        # Determine message and title based on export availability
        title = _("Exporter les résultats")
        link = _("Exporter les résultats")
        if can_export:
            info_message = _("L'export CSV contient au maximum 10000 notices.")
        elif total_results == 0:
            info_message = _("Aucun résultat à exporter.")
        elif total_results > MAX_EXPORT_LIMIT:
            info_message = _(
                "L'export CSV est indisponible car votre recherche retourne plus de "
                "{limit} résultats ({total} résultats). Veuillez affiner votre recherche "
                "pour exporter moins de {limit} notices."
            ).format(limit=MAX_EXPORT_LIMIT, total=total_results)
        else:  # not has_exportable
            info_message = _("Aucun résultat exportable (matricules de départements interdits).")

        return {
            "url": csv_url,
            "filename": filename,
            "title": title,
            "link": link,
            "size": size_label if size_label else "~20 KB",
            "can_export": can_export,
            "info_message": info_message,
            "total_results": total_results,
        }

    def compute_search_summary(self):
        """Do not translate labels here"""
        facets = self._cw.form
        summary = []
        inventory = facets.pop("inventory", None)
        facets_to_display = self.facets_to_display
        service_labels = {}
        for key, value in facets.items():
            summary_value = {}
            if key in self.skip_in_summary:
                continue
            if key.startswith("es_"):
                # get the facet label requires to remove the "es_" substring
                facetlabel = [x[1] for x in facets_to_display if x[0] == key[3:]]
                if key == "es_service" and value:
                    service_labels = self.get_selected_services_names
                    if inventory:
                        if service_labels:
                            inventory = service_labels[0]
                        else:
                            inventory = ""
                        continue
                    summary_value["name"] = value
                if key == "es_date_min" and value:
                    summary_value["name"] = _("date-min-facet")
                elif key == "es_date_max" and value:
                    summary_value["name"] = _("date-max-facet")
                elif len(facetlabel) > 0:
                    summary_value["name"] = facetlabel[0]
                elif key in self.text_facets:
                    summary_value["name"] = _(key.split("es_")[1].capitalize())
                else:
                    continue
                if not isinstance(value, (list, tuple)):
                    value = [value]
                value = [str(val).strip() for val in value if val]
                data = []
                services_codes = self.get_selected_services
                for val in value:
                    if val:
                        url_params = {key: list(set(value).difference([val]))}
                        reset_url = rebuild_url(self._cw, replace_keys=True, **url_params)
                        if key == "es_service":
                            if val.isnumeric():
                                res = services_codes.get(int(val))
                                if res:
                                    val = res["name"]
                        elif key == "es_act_type":
                            val = self.translate_acte_type(val)
                        data.append([val, reset_url])
                if data:
                    summary_value["value"] = data
                    summary.append(summary_value)
            elif key == "fulltext_facet":
                value = value.strip()
                if value:
                    reset_url = rebuild_url(self._cw, **{key: None})
                    summary.insert(
                        0,
                        {
                            "name": self._cw._("Contains"),
                            "value": ((value, reset_url),),
                        },
                    )
        context = {}
        if inventory:
            context["inventory"] = inventory
        search_summary = {}
        if context:
            search_summary["context"] = context
        if summary:
            search_summary["summary"] = summary
        return search_summary

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

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        """
        This is where one can customize the search by modifying the
        query string and facet selection in an inherited class.

        """
        stop = stop if stop != 10 else self.default_items_per_page
        cwconfig = self._cw.vreg.config
        index_name = cwconfig["nomina-index-name"]
        for facet_searched in list(facet_selections.keys()):
            if facet_searched not in list(NominaFacetedSearch.facets.keys()):
                del facet_selections[facet_searched]
        kwargs = build_nomina_faceted_search_kwargs(self._cw.form)
        return NominaFacetedSearch(
            query_string,
            facet_selections,
            index=index_name,
            include_export_aggs=True,
            **kwargs,
        )[start:stop]

    @property
    def facets_to_display(self):
        """
        Method to list facets to display (can be customized)
        """
        _ = self._cw._
        return (
            ("service", _("publishers_facet")),
            ("act_type", _("acte_type_facet")),
            ("gender", _("gender_facet")),
        )

    def build_search_result(self, hit, cache):
        service_eid = hit["service"]
        service = cache.get(service_eid, {})
        if not service and service_eid:
            rset = self._cw.execute(
                """Any X, C, N, N2, SN, L WHERE X is Service,
                X code C, X name N, X name2 N2, X short_name SN,
                X level L, X eid %(eid)s""",
                {"eid": service_eid},
            )
            if rset:
                entity = rset.one()
                images = self._cw.execute(
                    """Any F, CAP, COP, D, H, N WHERE E service_image X, X caption CAP,
                        X copyright COP, X description D,
                        X image_file F, F data_hash H, F data_name N,
                        E eid %(eid)s""",
                    {"eid": service_eid},
                )
                service = {
                    "code": entity.code,
                    "eid": service_eid,
                    "view": entity.view("outofcontext"),
                    "logo": {
                        "src": (
                            images.get_entity(0, 0).cw_adapt_to("IDownloadable").download_url()
                            if images
                            else ""
                        ),
                        "srcs": cache["default_picto_src"],
                    },
                }
                cache[service_eid] = service
        act_type = cache.get(hit["act_type"])
        if not act_type:
            act_type = nomina_translate_codetype(hit["act_type"])
            cache[hit["act_type"]] = act_type
        item_properties = [
            # (cache["doctype_label"], act_type),
            (cache["document_date_label"], hit["event_date"]),
            (cache["document_location_label"], format_event_location(hit, "event")),
            (cache["publisher_label"], service.get("view", "")),
        ]
        item_properties = [item for item in item_properties if item[1]]
        return {
            "_": self._cw._,
            "title": hit["title"],
            "url": self._cw.build_url(f"basedenoms/{hit['stable_id']}"),
            "item_properties": item_properties,
            "modification_date": hit["modification_date"] if "modification_date" in hit else None,
            "eulerian": {
                "document_title": f"basedenoms_{hit['stable_id']}",
                "page_type": "nomina",
                "service_code": service.get("code", ""),
                "type_doc": "nominarecord",
            },
            "labels": {
                "consult_dz_version": cache["consult_dz_version"],
                "modification_date": cache["modification_date"],
            },
            "act_type": act_type,
            "logo": service.get("logo", ""),
        }

    def build_results(self, response):
        results = []
        cache = {
            "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            "publisher_label": self._cw._("Publisher"),
            "doctype_label": self._cw._("Doctype_label"),
            "document_date_label": self._cw._("Document date label"),
            "document_location_label": self._cw._("Document location label"),
            "consult_dz_version": self._cw._("Consult the digitized version"),
            "modification_date": self._cw._("modification_date"),
        }
        for idx, result in enumerate(response):
            view = self._cw.vreg["views"].select("nominasearch-item", self._cw)
            result = self.build_search_result(result, cache)
            results.append(view.render(es_response=result))
        return results

    def sort_options(self, response):
        """
        Returns links with the sort_options and their label
        """
        _ = self._cw._
        url_params = {}
        url_params["page"] = None  # reset page number on new sort
        counts = response.hits.total.value or 0

        sort_options = {
            "score": _("Pertinence"),
        }

        if counts < self.sort_options_threshold:
            sort_options.update(
                {
                    "event_date_asc": _("Date ascending"),
                    "event_date_desc": _("Date descending"),
                    "title_asc": _("Titre (A-Z)"),
                    "title_desc": _("Titre (Z-A)"),
                }
            )

        current_sort_option = self._cw.form.get("sort", "score")

        # fallback to the default sort option if the requested option doesn't exist
        if current_sort_option not in sort_options:
            current_sort_option = "score"

        links = []
        for value, label in sort_options.items():
            url_params["sort"] = value
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

        # Store total count for csv_export_props to determine if export is allowed
        self.total_count = response.hits.total.value if response else 0

        # Store aggregations for csv_export_props to reuse (avoid second ES call)
        self._export_aggregations = (
            response.aggregations if hasattr(response, "aggregations") else None
        )

        date_params = self._cw.form.copy()
        facet_date_unfolded = any((p in date_params for p in ("es_date_min", "es_date_max")))
        es_date_min = date_params.pop("es_date_min", "")
        es_date_max = date_params.pop("es_date_max", "")
        date_params.pop("page", None)
        for key, value in date_params.items():
            if not isinstance(value, (tuple, list)):
                date_params[key] = [value]

        search_summary = self.search_summary
        self.w(
            self.template.render(
                req=self._cw,
                _=self._cw._,
                response=response,
                display_facets=bool(response.hits.total.value),
                facets=self.build_facets(response, context),
                results_title=self.format_results_title(response),
                display_fulltext_facet=False,
                search_results=self.build_results(response),
                search_summary=search_summary,
                reset_all_facets_link=self.reset_all_facets_link(),
                pagination=self.pagination(response.hits.total.value),
                header=self.get_header_attrs(),
                items_per_page_links=self.items_per_page_links(),
                display_sort_options=True,
                sort_options=self.sort_options(response),
                display_date_facet=True,
                date_facet_unfolded=self.display_date_facet and (es_date_min or es_date_max),
                es_date_min=es_date_min,
                es_date_max=es_date_max,
                date_params=date_params,
                facet_date_unfolded=facet_date_unfolded,
                page_number_params=self.page_number_params(),
                page_number_form_action=self._cw.build_url(
                    self._cw.relative_path(includeparams=False)
                ),
                current_page=int(self._cw.form.get("page", 1)),
                number_of_pages=self.number_of_pages(response.hits.total.value),
                fulltext_form_action=self._cw.build_url(
                    self._cw.relative_path(includeparams=False)
                ),  # needed for date-facet action
                csv_export_props=self.csv_export_props(),
            )
        )


class NominaRecordSearchResultAdaptor(StartupView):
    __regid__ = "nominasearch-item"
    template = get_template("searchitem-nominarecord.jinja2")

    def call(self, es_response):
        self.w(self.template.render(es_response))


def _force_act_type(facet_selections, forced_codes):
    """Inject a fixed list of act_type codes into facet selections.
    This overwrites any user‑provided selection for ``act_type``.
    """
    # ``facet_selections`` is a dict mapping facet names (without the ``es_`` prefix)
    if "act_type" in facet_selections:
        if not isinstance(facet_selections["act_type"], list):
            facet_selections["act_type"] = [facet_selections["act_type"]]
        facet_selections["act_type"] = [
            fs for fs in facet_selections["act_type"] if fs in forced_codes
        ]
    else:
        facet_selections["act_type"] = list(forced_codes)
    return facet_selections


def _filter_facet_values(response, facet_name, allowed_keys):
    """Mutate ``response`` to keep only allowed keys for a given facet.

    ``allowed_keys`` should be an iterable of the act_type codes that are
    relevant for the view (e.g. ``CENSUS_CODES``).  If the facet is missing the
    function simply returns without error.
    """
    try:
        buckets = response.facets[facet_name]
    except KeyError:
        pass
    else:
        response.facets[facet_name] = [b for b in buckets if b[0] in allowed_keys]


# Fixed code sets
CENSUS_CODES = ["RP"]
MILITARY_CODES = ["MPF", "MPF14-18", "MORT 14-18", "RM"]
# All act types defined in the mapping, minus the two sets above
ALL_ACT_CODES = list(NominaActCodeTypes.keys())
CIVILSTATUS_CODES = [
    code for code in ALL_ACT_CODES if code not in set(CENSUS_CODES + MILITARY_CODES)
]


class NominaCensusRecordView(PniaNominaElasticSearchView):
    __regid__ = "nominacensusrecord"
    title = _("Search in the name base - Census")

    def build_facets(self, response, context):
        _filter_facet_values(response, "act_type", set(CENSUS_CODES))
        return super().build_facets(response, context)

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        facet_selections = _force_act_type(facet_selections, CENSUS_CODES)
        return super().customize_search(
            query_string, facet_selections, start=start, stop=stop, **kwargs
        )

    @property
    def is_military_search(self):
        return False

    @property
    def typology(self):
        return "recensements"


class NominaMilitaryRecordView(PniaNominaElasticSearchView):
    __regid__ = "nominamilitaryrecord"
    title = _("Search in the name base - Military acts")

    def build_facets(self, response, context):
        _filter_facet_values(response, "act_type", set(MILITARY_CODES))
        return super().build_facets(response, context)

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        facet_selections = _force_act_type(facet_selections, MILITARY_CODES)
        return super().customize_search(
            query_string, facet_selections, start=start, stop=stop, **kwargs
        )

    @property
    def is_military_search(self):
        return True

    @property
    def typology(self):
        return "matricules"


class NominaCivilstatusRecordView(PniaNominaElasticSearchView):
    __regid__ = "nominacivilstatusrecord"
    title = _("Search in the name base - Civil status and other acts")

    def build_facets(self, response, context):
        _filter_facet_values(response, "act_type", set(CIVILSTATUS_CODES))
        return super().build_facets(response, context)

    def customize_search(self, query_string, facet_selections, start=0, stop=10, **kwargs):
        facet_selections = _force_act_type(facet_selections, CIVILSTATUS_CODES)
        return super().customize_search(
            query_string, facet_selections, start=start, stop=stop, **kwargs
        )

    @property
    def is_military_search(self):
        return False

    @property
    def typology(self):
        return "etat_civil"


class InventoryNominaPrimaryView(InventoryMixin, PniaNominaElasticSearchView):
    __select__ = PniaNominaElasticSearchView.__select__ & match_form_params(inventory=True)

    def get_current_form_params(self):
        all_params = super().get_current_form_params()
        all_params.pop("es_service", None)
        return all_params

    @cachedproperty
    def service_name(self):
        services = self.get_selected_services_names
        if services:
            return services[0]

    def breadcrumbs(self):
        breadcrumbs = [
            (self._cw.build_url(""), self._cw._("Home")),
            (self._cw.build_url("basedenoms"), self._cw._("Search in the name base")),
        ]
        if self.service_name:
            breadcrumbs.append((None, self.service_name))
        return breadcrumbs

    def get_header_attrs(self):
        _ = self._cw._
        if self.service_name:
            return {"title": "{}{}{}".format(self.service_name, _(":"), _("see all the names"))}
        return _("see all the names")
