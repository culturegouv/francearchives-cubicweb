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
from pyramid.decorator import reify
from pyramid.view import view_config
from pyramid.httpexceptions import HTTPNotFound, HTTPFound
from pyramid.response import Response

from cubicweb.pyramid.resources import EntityResource
from cubicweb import MultipleResultsError
from cubicweb.rdf import RDF_MIMETYPE_TO_FORMAT
from rdflib.graph import ConjunctiveGraph

from cubicweb_francearchives import INDEX_ETYPE_2_URLSEGMENT


from cubicweb_francearchives.pviews.helpers import update_headers
from cubicweb_francearchives.pviews.predicates import (
    MultiAcceptPredicate,
    SegmentIsEnlargedETypePredicate,
)
from cubicweb_francearchives.utils import remove_html_tags
from cubicweb_francearchives.xy import add_statements_to_graph


class ApplicationSchema(object):
    """The root schema resource, describing the application schema."""

    translations = {
        "article": "BaseContent",
        "articles": "BaseContent",
        "actualite": "NewsContent",
        "actualites": "NewsContent",
        "circulaire": "Circular",
        "circulaires": "Circular",
        "services": "Service",
        "annuaire": "Service",
        "agent": "AgentAuthority",
        "location": "LocationAuthority",
        "subject": "SubjectAuthority",
        "subjectname": "Subject",
        "pages_histoire": "CommemorationItem",
        # "basedenoms": "NominaRecord",
    }

    def __init__(self, request):
        self.request = request
        vreg = self.request.registry["cubicweb.registry"]
        etype = self.request.matchdict.get("etype", "").lower()
        try:
            self.etype = self.translations[etype]
        except KeyError:
            # this can't raise a KeyError since we are here after
            # segment_is_enlarged_etype predicate.
            try:
                self.etype = vreg.case_insensitive_etypes[etype]
            except KeyError:
                raise HTTPNotFound()

    @reify
    def rset(self):
        """Do not compute the rset, it will be done be ElasticSearch"""
        return None

    def __getitem__(self, value):
        vreg = self.request.registry["cubicweb.registry"]
        etype_cls = vreg["etypes"].etype_class(self.etype)
        (rest_attr, needcheck) = etype_cls.cw_rest_attr_info()
        resource = EntityResource(self.request, etype_cls, rest_attr, value)
        resource.rset.req = (
            self.request.cw_request
        )  # we need a CubicWebRequest instead of a Connection
        return resource


RDF_MAPPING = {
    "application/ld+json": "json-ld",
    "text/rdf+n3": "n3",
    "text/n3": "n3",
    "text/plain": "nt",
    "application/n-triples": "nt",
    "application/x-turtle": "turtle",
    "application/rdf+xml": "pretty-xml",
    **RDF_MIMETYPE_TO_FORMAT,
}


@view_config(
    route_name="restpath",
    request_method=("GET", "HEAD"),
    multi_accept=list(RDF_MAPPING.keys()),
    context=EntityResource,
)
def rdf_view(context, request):
    content_type = request.accept.best_match(list(RDF_MAPPING.keys()))
    fmt = RDF_MAPPING[content_type]
    entity = context.rset.one()
    to_entity = getattr(entity, "grouped_with", None)
    if to_entity:
        rdf_adapter = to_entity[0].cw_adapt_to("rdf")
    else:
        rdf_adapter = entity.cw_adapt_to("rdf")
    if rdf_adapter is None:
        raise HTTPNotFound()
    graph = ConjunctiveGraph()
    add_statements_to_graph(graph, rdf_adapter)
    context = {prefix: str(ns) for prefix, ns in rdf_adapter.used_namespaces.items()}
    return Response(
        graph.serialize(format=fmt, context=context), content_type=content_type, charset="UTF8"
    )


@view_config(route_name="restpath", request_method=("GET", "HEAD"), context=EntityResource)
def primary_view(context, request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    # several Files may be created for a single file in which case do not raise
    # MultipleResultsError but display the list
    if not context.rset:
        # EntityResource.rset may be empty
        raise HTTPNotFound()
    try:
        entity = context.rset.one()
    except MultipleResultsError:
        entity = context.rset.get_entity(0, 0)
        if context.rset.description and not context.rset.description[0][0] == "File":
            raise HTTPNotFound()
    to_entity = getattr(entity, "grouped_with", None)
    if to_entity:
        raise HTTPFound(location=to_entity[0].absolute_url())
    view = viewsreg.select("primary", cwreq, rset=context.rset)
    return update_headers(
        cwreq,
        Response(viewsreg.main_template(cwreq, "main-template", rset=context.rset, view=view)),
    )


@view_config(route_name="es_etype", request_method=("GET", "HEAD"), context=ApplicationSchema)
@view_config(route_name="restpath", request_method=("GET", "HEAD"), context=ApplicationSchema)
def list_view(context, request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    cw_etype = "Article" if context.etype == "BaseContent" else context.etype
    if cw_etype in INDEX_ETYPE_2_URLSEGMENT.keys():
        raise HTTPNotFound()
    cwreq.form.update(
        {
            "vid": "esearch",
            "search": "",
            "es_cw_etype": cw_etype,
            "restrict_to_single_etype": True,
        }
    )
    view = viewsreg.select("esearch", cwreq, rset=None)
    return update_headers(
        cwreq,
        Response(viewsreg.main_template(cwreq, "main-template", rset=context.rset, view=view)),
    )


@view_config(
    route_name="glossary-terms", renderer="json", http_cache=600, request_method=("GET", "HEAD")
)
def glossary_terms(request):
    cwreq = request.cw_request
    rset = cwreq.execute(
        "Any T, D WHERE T is GlossaryTerm, T short_description D", build_descr=False
    )
    return {eid: remove_html_tags(desc) for eid, desc in rset.rows}


def includeme(config):
    config.add_view_predicate("multi_accept", MultiAcceptPredicate)
    config.add_route_predicate("segment_is_enlarged_etype", SegmentIsEnlargedETypePredicate)
    config.add_route("glossary-terms", "/_glossaryterms")
    config.add_route(
        "es_etype",
        "/{etype}",
        factory=ApplicationSchema,
        segment_is_enlarged_etype=("etype", ApplicationSchema.translations),
    )  # route an entities liste without "/" (e.g /article)
    config.add_route(
        "restpath",
        "/{etype}/*traverse",
        factory=ApplicationSchema,
        segment_is_enlarged_etype=("etype", ApplicationSchema.translations),
    )  # route for an Entity (PrimaryView) or an entities liste with a final "/" (e.g /article/)
    config.scan(__name__)
