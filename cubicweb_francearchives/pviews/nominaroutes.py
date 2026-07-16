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


import logging

from datetime import datetime

from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPNotFound

from cubicweb_francearchives.entities.cms import Service
from cubicweb_francearchives.entities.nomina import (
    FORBIDDEN_CSV_EXPORT,
    RM_DOCTYPE,
    format_event_location,
    nomina_translate_codetype,
    normalized_doctype_code,
    initialize_nominarecord_entity,
    build_nomina_faceted_search_kwargs,
)
from cubicweb_francearchives.views.search.facets import NominaFacetedSearch


LOG = logging.getLogger(__name__)


@view_config(route_name="basedenoms", request_method=("GET", "HEAD"))
def basedenoms_view(request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    stable_id = request.matchdict["stable_id"]
    try:
        entity = initialize_nominarecord_entity(cwreq, stable_id)
    except Exception as ex:
        cwreq.error(f"NominaRecord with stable_id {stable_id} not found: {ex}")
        raise HTTPNotFound()

    view = viewsreg.select("nomina-primary", cwreq, rset=None, stable_id=stable_id, entity=entity)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


def nominarecords_view(request, nomina_vid="nominarecords"):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    if cwreq.form:
        view = viewsreg.select(nomina_vid, cwreq, rset=None)
    else:
        view = viewsreg.select("nomina-home", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="nominarecords", request_method=("GET", "HEAD"))
def nominarecords_all_view(request):
    return nominarecords_view(request)


@view_config(route_name="nominacensusrecords", request_method=("GET", "HEAD"))
def nominarecords_census_view(request):
    return nominarecords_view(request, "nominacensusrecord")


@view_config(route_name="nominamilitaryrecords", request_method=("GET", "HEAD"))
def nominarecords_military_view(request):
    return nominarecords_view(request, "nominamilitaryrecord")


@view_config(route_name="nominacivilstatusrecords", request_method=("GET", "HEAD"))
def nominarecords_civilstatus_view(request):
    return nominarecords_view(request, "nominacivilstatusrecord")


@view_config(route_name="service-nominarecords", request_method=("GET", "HEAD"))
def service_documents_view(request):
    cwreq = request.cw_request
    service = Service.from_code(cwreq, request.matchdict["code"])
    if service is None:
        raise HTTPNotFound()
    cwreq.form.setdefault("es_service", service.eid)
    cwreq.form.setdefault("inventory", True)
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("nominarecords", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="agent-nominarecords", request_method=("GET", "HEAD"))
def agent_nominarecords(request):
    cwreq = request.cw_request
    eid = request.matchdict["eid"]
    rset = cwreq.find("AgentAuthority", eid=eid)
    if not rset:
        raise HTTPNotFound()
    viewsreg = cwreq.vreg["views"]
    cwreq.form["authority"] = eid
    view = viewsreg.select("agents-nomina", cwreq, rset=rset)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=rset, view=view))


@view_config(route_name="basedenoms-csv", renderer="csv", request_method=("GET", "HEAD"))
def nominarecord_csv_view(request):
    cwreq = request.cw_request
    stable_id = request.matchdict["stable_id"]
    try:
        entity = initialize_nominarecord_entity(cwreq, stable_id, csv_export=True)
    except Exception as ex:
        cwreq.error(f"NominaRecord with stable_id {stable_id} not found: {ex}")
        raise HTTPNotFound()
    data = entity.json_data.get("csv_export")
    filename = f"{entity.rest_path()}.csv".replace("/", "_")
    request.response.content_disposition = "attachment;filename=" + filename
    return {"headers": [d[0] for d in data], "rows": [[d[1] for d in data]]}


@view_config(route_name="basedenoms-export-csv", renderer="csv", request_method=("GET", "HEAD"))
def nominarecords_csv_export_view(request):
    """Export search results as CSV (up to 10000 results)"""
    cwreq = request.cw_request

    # Get all search parameters from the request
    search_params = cwreq.form.copy()
    # Pagination parameters (page, items_per_page) are ignored for export

    # Build facet selections from search params.
    # Exclude text facets and date facets as they are handled via extra_kwargs
    facet_selections = {}
    text_facets = {"es_forenames", "es_names", "es_locations"}
    date_facets = {"es_date_min", "es_date_max"}
    for key, value in search_params.items():
        if key.startswith("es_") and key not in text_facets and key not in date_facets:
            facet_name = key[3:]  # Remove "es_" prefix
            if isinstance(value, (list, tuple)):
                facet_selections[facet_name] = list(value)
            else:
                facet_selections[facet_name] = value

    # Get query string
    query_string = search_params.get("q", "")

    # Get index name from config
    cwconfig = cwreq.vreg.config
    index_name = cwconfig["nomina-index-name"]

    # Build kwargs for NominaFacetedSearch
    kwargs = build_nomina_faceted_search_kwargs(search_params)
    kwargs["csv_export"] = True

    # Execute search: export all results up to 10000 (pagination ignored)
    search = NominaFacetedSearch(query_string, facet_selections, index=index_name, **kwargs)
    results = search[0:10000].execute()

    # Build CSV headers
    headers = [
        cwreq._("FranceArchives link"),
        cwreq._("Name"),
        cwreq._("Forenames"),
        cwreq._("NMN_C_occupations"),
        cwreq._("Doctype_label"),
        cwreq._("Event date"),
        cwreq._("Event location"),
        cwreq._("Cote"),
        cwreq._("thumbnail_dest"),
        cwreq._("Partner service name"),
    ]

    # Collect all unique service eids for batch query
    service_eids = set()
    for hit in results:
        hit_dict = hit.to_dict()
        service_eid = hit_dict.get("service")
        if service_eid:
            service_eids.add(service_eid)

    # Single batch query to get all service names and codes
    service_names = {}
    service_codes = {}
    if service_eids:
        try:
            str_eids = ", ".join(str(eid) for eid in service_eids)
            rset = cwreq.execute(
                f"Any X, N, C WHERE X is Service, X name N, X code C, X eid IN ({str_eids})"
            )
            service_names = {eid: name for eid, name, _ in rset}
            service_codes = {eid: code for eid, _, code in rset}
        except Exception:
            pass

    rows = []
    for hit in results:
        hit_dict = hit.to_dict()
        service_eid = hit_dict.get("service")
        service_code = service_codes.get(service_eid, "")

        # Normalize act type code
        code = normalized_doctype_code(hit_dict.get("act_type", ""))
        act_type_label = nomina_translate_codetype(code)

        # Skip results from forbidden services (military records only)
        if code in RM_DOCTYPE and service_code in FORBIDDEN_CSV_EXPORT:
            continue

        # Get service name from batch query result
        service_name = service_names.get(service_eid, "")

        # Get occupations: use occupations_index for census records (RP)
        if code == "RP":
            # For RP: prefer occupations_index, fallback to occupations if missing/empty
            occupations = hit_dict.get("occupations_index")
            if not occupations:  # None or empty list
                occupations = []
        else:
            occupations = hit_dict.get("occupations", [])
        occupations_str = ", ".join(occupations) if occupations else ""

        # Format event location
        event_location = format_event_location(hit_dict, "event")

        # Build row
        row = [
            cwreq.build_url(f"basedenoms/{hit_dict.get('stable_id', '')}"),
            ", ".join(hit_dict.get("names", [])) or "",
            ", ".join(hit_dict.get("forenames", [])) or "",
            occupations_str,
            act_type_label,
            hit_dict.get("event_date", "") or "",
            event_location,
            hit_dict.get("cote", "") or "",
            hit_dict.get("source_url", "") or "",
            service_name,
        ]
        rows.append(row)

    timestamp = datetime.now().strftime("%Y%m%d_%Hh%Mm%Ss")
    filename = f"nominarecords_export_{timestamp}.csv"  # fallback name only
    request.response.content_disposition = f"attachment;filename={filename}"

    return {"headers": headers, "rows": rows}


def includeme(config):
    config.add_route("basedenoms-csv", r"/basedenoms/{stable_id}.csv")
    config.add_route("basedenoms", r"/basedenoms/{stable_id}", accept="text/html")
    config.add_route("basedenoms-export-csv", "/basedenomsexport/export.csv")

    config.add_route("nominarecords", "/basedenoms")
    config.add_route("nominacensusrecords", "/basedenoms_recensement")
    config.add_route("nominamilitaryrecords", "/basedenoms_militaire")
    config.add_route("nominacivilstatusrecords", "/basedenoms_etat_civil")
    config.add_route("service-nominarecords", "basedenoms/service/{code}")
    config.add_route("agent-nominarecords", "agent/{eid}/nomina")
    config.scan(__name__)
