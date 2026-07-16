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


from functools import partial
import logging

from pyramid.view import view_config
from pyramid.response import Response
from pyramid.httpexceptions import HTTPNotFound, HTTPFound
from rdflib.graph import ConjunctiveGraph

from rql import TypeResolverException


from cubicweb import crypto, NoResultError

from cubicweb_francearchives.xy import add_statements_to_graph
from cubicweb_francearchives.utils import find_card
from cubicweb_francearchives.entities.cms import Service
from .cwroutes import startup_view_factory
from .csvutils import alignment_csv, indices_csv


LOG = logging.getLogger(__name__)


def create_rdf_response(entity, format):
    RDF_FORMAT_TO_MIMETYPE = {
        "nt": "application/n-triples",
        "n3": "text/n3",
        "ttl": "text/turtle",
        "jsonld": "application/ld+json",
    }
    rdf_adapter = entity.cw_adapt_to("rdf")
    graph = ConjunctiveGraph()
    add_statements_to_graph(graph, rdf_adapter)
    if format in RDF_FORMAT_TO_MIMETYPE:
        content_type = RDF_FORMAT_TO_MIMETYPE[format]
    else:  # fallback to xml
        content_type = "application/rdf+xml"

    return Response(
        graph.serialize(format=content_type), content_type=f"{content_type}; charset=UTF-8"
    )


def rqlrequest_factory(request, rql, vid=None):
    cwreq = request.cw_request
    try:
        rset = cwreq.execute(rql, request.matchdict)
    except TypeResolverException:
        LOG.exception("seems there is no result for this rql")
        raise HTTPNotFound()
    if vid is None:
        if len(rset) == 1:
            vid = "primary"
        elif rset:
            vid = "list"
        else:
            vid = "noresult"
    if not rset and vid != "noresult":
        # unexpected empty rset raise 404
        raise HTTPNotFound()
    return {
        "vid": vid,
        "rset": rset,
    }


def rqlbased_view(request):
    cwreq = request.cw_request
    viewsreg = cwreq.vreg["views"]
    ctx = request.context
    view = viewsreg.select(ctx["vid"], cwreq, rset=ctx["rset"])
    return Response(viewsreg.main_template(cwreq, "main-template", rset=ctx["rset"], view=view))


def all_services(req):
    rset = req.execute(
        "Any S,SN,SN2,SSN,SPN,SINSEE,SE,SA,SZ,SC,SCC,SU,SOP,SCODE,"
        "SWU,SL,SI,SIF,SIFH,SIFN,PARENT,SDC,SML,SLAT,SLON "
        "ORDERBY SL,SN,PARENT "
        "WHERE S is Service, S name SN, S name2 SN2, S short_name SSN, "
        "S mailing_address SML, S dpt_code SDC, "
        "S phone_number SPN, S code_insee_commune SINSEE, S email SE, S address SA, "
        "S zip_code SZ, S city SC, S contact_name SCC, "
        "S service_image SI?, SI image_file SIF?, "
        "SIF data_hash SIFH, SIF data_name SIFN, "
        "S uuid SU, S opening_period SOP, S code SCODE, "
        "S website_url SWU, S level SL, S annex_of PARENT?, "
        "S latitude SLAT, S longitude SLON"
    )
    return rset


@view_config(route_name="annuaire-vcard", request_method=("GET", "HEAD"))
def annuaire_vcard_view(request):
    cwreq = request.cw_request
    vcards = []
    for service in all_services(cwreq).entities():
        card = service.cw_adapt_to("vcard").vcard()
        vcards.append(card.serialize())
    return Response("\n\n".join(vcards), content_type="text/vcard")


@view_config(route_name="annuaire-csv", request_method=("GET", "HEAD"), renderer="csv")
def annuaire_csv_view(request):
    cwreq = request.cw_request
    rows = []
    for service in all_services(cwreq).entities():
        icsv = service.cw_adapt_to("csv-props")
        rows.append(icsv.csv_row())
    headers = icsv.headers  # pick headers from any adapaters
    return {"rows": rows, "headers": headers}


@view_config(route_name="alignment", request_method=("GET", "HEAD"), renderer="csv")
def alignment_csv_view(request):
    return alignment_csv(request.cw_request)


@view_config(route_name="glossary", request_method=("GET", "HEAD"))
def glossary_view(request):
    cwreq = request.cw_request
    rset = cwreq.execute("Any X, T, D WHERE X is GlossaryTerm, X term T, X short_description D")
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("glossary", cwreq, rset=rset)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=rset, view=view))


@view_config(route_name="indices-csv", request_method=("GET", "HEAD"), renderer="csv")
def indices_csv_view(request):
    auth_type = request.matchdict["type"]
    return indices_csv(request.cw_request, auth_type)


def card_view(request):
    cwreq = request.cw_request
    card = find_card(cwreq, request.matchdict["wiki"])
    if card is None:
        raise HTTPNotFound()
    rset = card.as_rset()
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("primary", cwreq, rset=rset)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=rset, view=view))


@view_config(route_name="all-documents", request_method=("GET", "HEAD"))
def all_documents_view(request):
    cwreq = request.cw_request
    cwreq.form.setdefault("vid", "esearch")
    cwreq.form.setdefault("es_escategory", "archives")
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("esearch", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="virtualexhibits", request_method=("GET", "HEAD"))
def virtualexhibitsview(request):
    cwreq = request.cw_request
    cwreq.form.setdefault("vid", "esearch")
    cwreq.form.setdefault("es_cw_etype", "Virtual_exhibit")
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("esearch", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="faq", request_method=("GET", "HEAD"))
def faq_view(request):
    cwreq = request.cw_request
    rset = cwreq.execute("Any X, A, Q WHERE X is FaqItem, X question Q, X answer A")
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("faq", cwreq, rset=rset)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=rset, view=view))


@view_config(route_name="service-documents", request_method=("GET", "HEAD"))
def service_documents_view(request):
    cwreq = request.cw_request
    service = Service.from_code(cwreq, request.matchdict["service"])
    if service is None:
        raise HTTPNotFound()
    cwreq.form.setdefault("vid", "esearch")
    cwreq.form.setdefault("es_escategory", "archives")
    cwreq.form.setdefault("es_publisher", service.eid)
    cwreq.form["inventory"] = True
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("esearch", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="findingaid-rdf", request_method=("GET", "HEAD"))
def findingaid_rdf_view(request):
    cwreq = request.cw_request
    etype = cwreq.vreg.case_insensitive_etypes[request.matchdict["etype"]]
    entity = cwreq.find(etype, stable_id=request.matchdict["stable_id"]).one()
    # XXX HTTPNotFound() on error
    format = request.matchdict["format"].split(".", 1)[1]
    return create_rdf_response(entity, format)


@view_config(route_name="eid-rdf", request_method=("GET", "HEAD"))
def eid_rdfformat_view(request):
    cwreq = request.cw_request
    request_etype = request.matchdict["etype"]
    if request_etype in ("agent", "location", "subject"):
        request_etype = f"{request_etype}authority"
    etype = cwreq.vreg.case_insensitive_etypes[request_etype]
    entity = cwreq.find(etype, eid=request.matchdict["eid"]).one()
    # XXX HTTPNotFound() on error
    format = request.matchdict["format"].split(".", 1)[1]
    return create_rdf_response(entity, format)


@view_config(route_name="authorityrecord-rdf", request_method=("GET", "HEAD"))
def authorityrecord_rdfformat_view(request):
    cwreq = request.cw_request
    entity = cwreq.find("AuthorityRecord", record_id=request.matchdict["record_id"]).one()
    # XXX HTTPNotFound() on error
    format = request.matchdict["format"].split(".", 1)[1]
    return create_rdf_response(entity, format)


@view_config(route_name="findingaid-csv", renderer="csv", request_method=("GET", "HEAD"))
def findingaid_csv_view(request):
    cwreq = request.cw_request
    etype = cwreq.vreg.case_insensitive_etypes[request.matchdict["etype"]]
    entity = cwreq.find(etype, stable_id=request.matchdict["stable_id"]).one()
    adapter = entity.cw_adapt_to("entity.main_props")
    data = adapter.properties(export=True, vid="text", text_format="text/plain")
    filename = "%s.csv" % entity.rest_path()
    request.response.content_disposition = "attachment;filename=" + filename
    return {"headers": [d[0] for d in data], "rows": [[d[1] for d in data]]}


@view_config(route_name="circulars-csv", request_method=("GET", "HEAD"), renderer="csv")
def circulars_csv_view(request):
    cwreq = request.cw_request
    rset = cwreq.execute(
        "Any JV ORDERBY SDSD, SD "
        "WHERE S is Circular, S json_values JV, "
        "S siaf_daf_signing_date SDSD, S signing_date SD"
    )
    rows = []
    for json_values in rset:
        rows.append([v or "" for li, v in json_values[0]])
    headers = [cwreq._(e[0]) for e in json_values[0]]
    return {"rows": rows, "headers": headers}


@view_config(route_name="entityrecord-csv", renderer="csv", request_method=("GET", "HEAD"))
def entiyiyrecord_csv_view(request):
    cwreq = request.cw_request
    etype = cwreq.vreg.case_insensitive_etypes[request.matchdict["etype"]]
    entity = cwreq.find(etype, record_id=request.matchdict["record_id"]).one()
    adapter = entity.cw_adapt_to("entity.main_props")
    data = adapter.properties(export=True, vid="text", text_format="text/plain")
    request.response.content_disposition = f"attachment;filename={entity.record_id}.csv"
    return {"headers": [d[0] for d in data], "rows": [[d[1] for d in data]]}


@view_config(route_name="agentrecord-xml", request_method=("GET", "HEAD"))
def agentrecord_xml_view(request):
    cwreq = request.cw_request
    etype = cwreq.vreg.case_insensitive_etypes[request.matchdict["etype"]]
    entity = cwreq.find(etype, record_id=request.matchdict["record_id"]).one()
    data = entity.cw_adapt_to("EAC-CPF-v2").dump()
    request.response.content_disposition = f"attachment;filename={entity.record_id}.xml"
    return Response(
        data,
        content_type="application/xml",
        content_disposition=f"attachment;filename={entity.record_id}.xml",
    )


REWRITE_RULES = [
    (
        # XXX should we remove this route ?
        "commemoitem",
        r"/commemo/recueil-{year:\d+}/{commemo:\d+}",
        {
            "vid": "primary",
            "rql": "Any X WHERE X commemoration_year %(year)s, X eid %(commemo)s",
        },
    ),
    (
        "annuaire",
        r"/annuaire/{eid:\d+}",
        {
            "vid": "primary",
            "rql": "Any X WHERE X is Service, X eid %(eid)s",
        },
    ),
    (
        "topsection",
        r"/{section:(rechercher|decouvrir|comprendre|gerer)}",
        {
            "vid": "primary",
            "rql": "Any S WHERE S is Section, NOT EXISTS(X children S), " "S name %(section)s",
        },
    ),
]


def form_controller(request, regid):
    cwreq = request.cw_request
    form = cwreq.vreg["forms"].select(regid, cwreq)
    kwargs = form.publish_form()
    viewsreg = cwreq.vreg["views"]
    cwreq.form["_ctrl"] = kwargs
    view = cwreq.vreg["views"].select(regid, cwreq)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="contact", request_method="POST")
def contact_controller(request):
    return form_controller(request, "contact")


@view_config(route_name="lettre-info", request_method="POST")
def newsletter_controller(request):
    return form_controller(request, "newsletter")


@view_config(route_name="nlconfirm", request_method=("GET", "HEAD"))
def newsletter_confirm_controller(request):
    cwreq = request.cw_request
    view = cwreq.vreg["views"].select("nlconfirm", cwreq)
    viewsreg = cwreq.vreg["views"]
    if "key" not in cwreq.form:
        return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))
    try:
        email = crypto.decrypt(cwreq.form["key"], cwreq.vreg.config["newsletter-cypher-seed"])
    except Exception:
        msg = cwreq._("Invalid subscription data. Please try subscription again.")
        # '_d' arg stand for 'dispaly subscription form'
        cwreq.form["_ctrl"] = {"msg": msg, "_d": 1}
        return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))
    with cwreq.cnx.repo.internal_cnx() as cnx:
        existing = cnx.find("NewsLetterSubscriber", email=email)
        if not existing:
            try:
                cnx.create_entity("NewsLetterSubscriber", email=email)
                cnx.commit()
                msg = cwreq._("Your email has been successfully added.")
                cwreq.form["_ctrl"] = {"msg": msg}
            except Exception:
                msg = cwreq._("Your subscription has failed. Please try subscription again.")
                cwreq.form["_ctrl"] = {"msg": msg, "_d": 1}
        else:
            msg = cwreq._("Your are already subscribed to the newsletter.")
            cwreq.form["_ctrl"] = {"msg": msg}
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(route_name="absolute-url", request_method=("GET", "HEAD"))
def uuid2absolute_url(request):
    req = request.cw_request
    rset = req.execute(
        "Any X WHERE X is {}, X uuid %(uuid)s".format(request.matchdict["etype"]), request.matchdict
    )
    return HTTPFound(location=rset.one().absolute_url())


@view_config(route_name="fa-map", request_method=("GET", "HEAD"))
def famap_view(request):
    cwreq = request.cw_request
    cwreq.form.setdefault("vid", "fa-map")
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("fa-map", cwreq, rset=None)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=None, view=view))


@view_config(
    route_name="fa-map-json", renderer="json", http_cache=600, request_method=("GET", "HEAD")
)
def famap_data(request):
    cnx = request.cw_request
    res = cnx.execute(
        """
        Any V WHERE X is Caches, X name "geomap",
        X instance_type %(instance_type)s,
        X values V""",
        {"instance_type": cnx.vreg.config.get("instance-type")},
    )
    if res:
        return res[0][0]
    return []


@view_config(context=NoResultError)
def rql_error_view(request):
    return HTTPNotFound()


@view_config(
    route_name="facontext-data-json",
    renderer="json",
    http_cache=600,
    request_method=("GET", "HEAD"),
)
def facontext_data_view(request):
    cnx = request.cw_request
    cw_etype = request.matchdict["etype"]
    stable_id = request.matchdict["stable_id"]
    try:
        entity = cnx.find(cw_etype, stable_id=stable_id).one()
    except NoResultError:
        LOG.exception("seems there is no result for this rql")
        raise HTTPNotFound()
    return entity.cw_adapt_to("IFAContextTree").get_tree()


def includeme(config):
    config.add_route("absolute-url", r"/uuid/{etype:\w+}/{uuid:\w+}")
    config.add_route("annuaire-vcard", "/annuaire.vcf")
    config.add_route("annuaire-csv", "/annuaire.csv")
    config.add_route("indices-csv", "/indices-{type}.csv")
    for route, path, context in REWRITE_RULES:
        config.add_route(route, path, factory=partial(rqlrequest_factory, **context))
        config.add_view(rqlbased_view, route_name=route, request_method=("GET", "HEAD"))
    wiki_words = (
        "cgu",
        "open_data",
        "about",
        "emplois",
        "privacy_policy",
        "legal_notices",
        "accessibility",
        "newsletter",
        "glossary-card",
        "cookies_policy",
    )
    config.add_route("entrypoint-card", "/{{wiki:({})}}".format("|".join(wiki_words)))
    config.add_view(card_view, route_name="entrypoint-card", request_method=("GET", "HEAD"))
    for path, vid in (
        ("sitemap", "sitemap"),
        ("search", "esearch"),
        ("recherche", "esearch"),
        ("contact", "contact"),
        ("lettre-info", "newsletter"),
    ):
        config.add_route(path, "/" + path)
        # NOTE: lambda req, vid=vid: cw_startup_view(vid, req) doesn't work
        #       because pyramid seems to introspect the view object and behaves
        #       differently according to the number of parameters (e.g. 2 here)
        config.add_view(startup_view_factory(vid), route_name=path, request_method=("GET", "HEAD"))
    config.add_route("all-documents", "/inventaires")
    config.add_route("nlconfirm", "/nlconfirm")
    config.add_route("service-documents", "/inventaires/{service}")
    config.add_route(
        "findingaid-rdf",
        r"/{etype:(findingaid|facomponent)}/{stable_id}/{format:rdf\.(xml|n3|nt|ttl|jsonld)}",
    )
    config.add_route(
        "eid-rdf",
        r"/{etype:(service|agent|location|subject)}/{eid}/{format:rdf\.(xml|n3|nt|ttl|jsonld)}",
    )
    config.add_route(
        "authorityrecord-rdf",
        r"/{etype:authorityrecord}/{record_id}/{format:rdf\.(xml|n3|nt|ttl|jsonld)}",
    )
    config.add_route("findingaid-csv", r"/{etype:(findingaid|facomponent)}/{stable_id}.csv")
    config.add_route("entityrecord-csv", r"/{etype:(authorityrecord|agentrecord)}/{record_id}.csv")
    config.add_route("agentrecord-xml", r"/{etype:agentrecord}/{record_id}.xml")
    config.add_route("alignment", "/alignment.csv")
    config.add_route("fa-map", "/carte-inventaires")
    config.add_route("fa-map-json", "/fa-map.json")
    config.add_route("virtualexhibits", "/expositions")
    config.add_route("faq", "/faq")
    config.add_route("circulars-csv", "/circulaires.csv")
    config.add_route("glossary", "/glossaire")
    config.add_notfound_view(startup_view_factory("404", status_code=404), append_slash=HTTPFound)
    config.add_route(
        "facontext-data-json", r"/facontext-data/{etype:(FindingAid|FAComponent)}/{stable_id}"
    )

    config.scan(__name__)
