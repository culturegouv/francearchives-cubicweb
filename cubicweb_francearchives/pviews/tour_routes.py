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
from pyramid.view import view_config


def initiate_tour_data(cnx):
    _ = cnx._
    return {
        "nextLabel": _("Next"),
        "prevLabel": _("Previous"),
        "doneLabel": _("Done"),
        "skipLabel": _("Close"),
        "hidePrev": True,
        "scrollTo": "tooltip",
        "autoPosition": False,
        "showBullets": False,
    }


@view_config(
    route_name="search-tour.json", renderer="json", http_cache=600, request_method=("GET", "HEAD")
)
def search_tour_data(request):
    cnx = request.cw_request
    intro_data = initiate_tour_data(cnx)
    _ = cnx._
    intro_data["steps"] = [
        {
            "intro": _("tour_search_intro"),
        },
        {
            "element": "#header-search-bar-form",
            "intro": _("tour_search_query"),
        },
        {
            "element": ".fa-search-results--title",
            "intro": _("tour_search_results_number"),
            "position": "right",
        },
        {
            "element": ".fa-search-options--sort",
            "intro": _("tour_search_results_sort_options"),
            "position": "right",
        },
        {
            "element": ".fa-search-options--items",
            "intro": _("tour_search_number_items"),
            "position": "left",
        },
        {
            "element": ".fr-card",
            "intro": _("tour_search_result"),
        },
        {
            "element": ".fa-search--filters",
            "intro": _("tour_search_summary"),
        },
        {
            "element": "#fulltext-facet",
            "intro": _("tour_search_facet_fulltext"),
        },
        {
            "element": ".fa-facets",
            "intro": _("tour_search_facets"),
        },
        {
            "element": ".fr-pagination",
            "intro": _("tour_search_results_pagination"),
        },
    ]
    return intro_data


@view_config(
    route_name="findingaid-tour.json",
    renderer="json",
    http_cache=600,
    request_method=("GET", "HEAD"),
)
def findingaid_tour_data(request):
    cnx = request.cw_request
    intro_data = initiate_tour_data(cnx)
    _ = cnx._
    intro_data["steps"] = [
        {
            "element": ".fa-inventory-content__title h1",
            "intro": _("fi_tour_title"),
        },
        {
            "element": "#breadcrumb-line",
            "intro": _("fi_tour_breadcrumbs"),
        },
        {
            "element": ".fa-inventory-content__pdf",
            "intro": _("fi_tour_pdf"),
        },
        {
            "element": ".fa_tour_dv",
            "intro": _("fi_tour_digit_versions"),
        },
        {
            "element": ".fa-inventory-content__context",
            "intro": _("fi_tour_context"),
        },
        {
            "element": ".detailed-path-list-item-active",
            "intro": _("fi_tour_fatree"),
        },
        {
            "element": ".fa-inventory-content__index",
            "intro": _("fi_tour_indexes"),
        },
        {
            "element": ".fa-inventory-content__service-site",
            "intro": _("fi_tour_goto_service"),
        },
        {
            "element": ".fa-inventory-content__service-info",
            "intro": _("fi_tour_service_url"),
        },
        {
            "element": ".fa-inventory-content__csv",
            "intro": _("fi_tour_download-cvs"),
        },
    ]
    return intro_data


@view_config(
    route_name="facomponent-tour.json",
    renderer="json",
    http_cache=600,
    request_method=("GET", "HEAD"),
)
def facomponent_tour_data(request):
    cnx = request.cw_request
    intro_data = initiate_tour_data(cnx)
    _ = cnx._
    intro_data["steps"] = [
        {
            "element": ".fa-inventory-content__title h1",
            "intro": _("fa_tour_title"),
        },
        {
            "element": "#breadcrumb-line",
            "intro": _("fi_tour_breadcrumbs"),
        },
        {
            "element": ".fa_tour_dv",
            "intro": _("fi_tour_digit_versions"),
        },
        {
            "element": ".fa-inventory-content__context",
            "intro": _("fa_tour_context"),
        },
        {
            "element": ".detailed-path-list-item-active",
            "intro": _("fi_tour_fatree"),
        },
        {
            "element": ".fa-inventory-content__index",
            "intro": _("fi_tour_indexes"),
        },
        {
            "element": ".fa-inventory-content__service-site",
            "intro": _("fi_tour_goto_service"),
        },
        {
            "element": ".fa-inventory-content__service-info",
            "intro": _("fi_tour_service_url"),
        },
        {
            "element": ".fa-inventory-content__csv",
            "intro": _("fi_tour_download-cvs"),
        },
    ]
    return intro_data


def includeme(config):
    config.add_route("search-tour.json", "/search-tour.json")
    config.add_route("findingaid-tour.json", "/findingaid-tour.json")
    config.add_route("facomponent-tour.json", "/facomponent-tour.json")
    config.scan(__name__)
