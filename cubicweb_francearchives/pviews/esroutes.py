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
"""elasticsearch-related views"""
from pyramid import httpexceptions
from pyramid.response import Response
from pyramid.renderers import render

from elasticsearch.exceptions import NotFoundError
from elasticsearch_dsl.search import Search
from elasticsearch_dsl import query as dsl_query


from pyramid.view import view_config

from cubicweb_elasticsearch.es import get_connection

from cubicweb_francearchives import FEATURE_ADVANCED_SEARCH, FEATURE_SPARQL


def jsonapi_error(status=None, details=None):
    error = {}
    if status:
        error["status"] = int(status)
    if details:
        error["details"] = details
    return error


class JSONBadRequest(httpexceptions.HTTPBadRequest):
    """Bad request exception with application/json Content-Type."""

    def __init__(self, *errors):
        body = {"errors": list(errors)}
        super(JSONBadRequest, self).__init__(
            content_type="application/json; charset=UTF-8",
            body=render("json", body),
        )


@view_config(route_name="suggest", renderer="json", request_method=("GET", "HEAD"))
def suggest_view(request):
    """Retrieve suggestions (e.g. for authorities to group with)."""
    query_string = request.params.get("q", "").strip()
    if not query_string:
        return []
    cwconfig = request.registry["cubicweb.config"]
    get_connection(cwconfig)
    results = []
    responses = []
    es_categories = ("archives", "siteres")
    count_attr = "count"
    req_escategories = request.params.get("escategory", "").strip()

    # if req_escategories is one of the categories
    build_url_kwargs = {}
    if req_escategories in es_categories:
        count_attr = req_escategories
        build_url_kwargs["es_escategory"] = req_escategories

    # else, take all categories together by default
    if not build_url_kwargs:
        build_url_kwargs["es_escategory"] = es_categories

    for cw_etype in ("AgentAuthority", "LocationAuthority", "SubjectAuthority"):
        search = Search(extra={"size": 15}, index="{}_suggest".format(cwconfig["index-name"])).sort(
            "-count"
        )
        must = [
            {"match": {"text": {"query": query_string, "operator": "and"}}},
            # do not show authorities without related documents
            {"range": {count_attr: {"gte": 1}}},
            {"match": {"cw_etype": cw_etype}},
        ]
        search.query = dsl_query.Bool(must=must)
        try:
            response = search.execute()
        except NotFoundError:
            return []
        build_url = request.cw_request.build_url
        if response and response.hits.total:
            responses.append(response)
    nb_results = 7 if len(responses) > 1 else 15
    for response in responses:
        _ = request.cw_request._
        countlabel_templates = (_("No result"), _("1 document"), _("{count} documents"))
        for result in response[:nb_results]:
            count = getattr(result, count_attr, 0)
            countlabel = countlabel_templates[min(count, 2)].format(count=count)
            indextype = result.type if "type" in result else result.cw_etype
            if result.cw_etype == "SubjectAuthority":
                url = build_url(result.urlpath, aug=True, **build_url_kwargs)
            else:
                url = build_url(result.urlpath, **build_url_kwargs)
            results.append(
                {
                    "url": url,
                    "text": result.text,
                    "countlabel": countlabel,
                    "etype": _(indextype).capitalize(),
                }
            )
    results.sort(key=lambda x: x.get("etype"))
    return results


def authorities_view(request, regid):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select(regid, cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="subjects", request_method=("GET", "HEAD"))
def subjects_view(request):
    return authorities_view(request, "subjects")


@view_config(route_name="agents", request_method=("GET", "HEAD"))
def agents_view(request):
    return authorities_view(request, "agents")


@view_config(route_name="locations", request_method=("GET", "HEAD"))
def locations_view(request):
    return authorities_view(request, "locations")


if FEATURE_ADVANCED_SEARCH:

    @view_config(route_name="advanced-search", request_method=("GET", "HEAD"))
    def advanced_search_view(request):
        cwreq = request.cw_request
        cwreq.form.setdefault("vid", "advanced-search")
        viewsreg = cwreq.vreg["views"]
        view = viewsreg.select("advanced-search", cwreq, rset=None)
        return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


if FEATURE_SPARQL:

    @view_config(route_name="sparql-yasgui", request_method=("GET", "HEAD"))
    def sparql_yasgui_view(request):
        cwreq = request.cw_request
        cwreq.form.setdefault("vid", "sparql-yasgui")
        viewsreg = cwreq.vreg["views"]
        view = viewsreg.select("sparql-yasgui", cwreq, rset=None)
        return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))

    @view_config(route_name="sparnatural", request_method=("GET", "HEAD"))
    def sparql_sparnatural(request):
        cwreq = request.cw_request
        cwreq.form.setdefault("vid", "sparnatural")
        viewsreg = cwreq.vreg["views"]
        view = viewsreg.select("sparnatural", cwreq, rset=None)
        return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


def json_config(**settings):
    """Wraps view_config for JSON rendering."""
    settings.setdefault("accept", "application/json")
    settings.setdefault("renderer", "json")
    return view_config(**settings)


if FEATURE_ADVANCED_SEARCH:

    def get_es_index(request, cwconfig):
        index = request.matchdict["index"]
        if index == "all":
            return f"{cwconfig['index-name']}_all"
        if index == "suggest":
            return f"{cwconfig['index-name']}_suggest"
        if index == "services":
            return cwconfig["kibana-services-index-name"]

    @json_config(route_name="advanced_search")
    def advanced_search(request):
        cwconfig = request.registry["cubicweb.config"]
        index = get_es_index(request, cwconfig)
        cwreq = request.cw_request
        if index:
            es = get_connection(cwconfig)
            if not es:
                cwreq.error("[advanced search] no connection to ES (not configured)")
                raise JSONBadRequest(
                    jsonapi_error(
                        status=501,
                        details=cwreq._("En error occurred (no es connection). Please, try again."),
                    )
                )
            try:
                return es.search(index=index, body=request.json_body).body
            except Exception as err:
                cwreq.error("[advanced seach] %s" % err)
                raise JSONBadRequest(jsonapi_error(status=501, details=err))
        else:
            cwreq.error("[advanced seach] no index provided")
        raise JSONBadRequest(
            jsonapi_error(status=501, details=cwreq._("En error occurred. Please, try again."))
        )


def includeme(config):
    config.add_route("suggest", "/_suggest")
    config.add_route("subjects", "/subjects")
    config.add_route("agents", "/agents")
    config.add_route("locations", "/locations")
    if FEATURE_ADVANCED_SEARCH:
        config.add_route("advanced-search", "/advancedSearch")
        config.add_route("advanced_search", r"/advanced_search/{index}")
    if FEATURE_SPARQL:
        config.add_route("sparql-yasgui", "/sparql")
        config.add_route("sparnatural", "/requeteurnaturel")
    config.scan(__name__)
