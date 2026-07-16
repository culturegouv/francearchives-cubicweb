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
from collections import defaultdict
import logging

from pyramid.httpexceptions import HTTPNotFound
from pyramid.response import Response
from pyramid.view import view_config
from geojson import Feature, FeatureCollection, Point

LOG = logging.getLogger(__name__)


@view_config(
    route_name="services-map-json", renderer="json", http_cache=600, request_method=("GET", "HEAD")
)
def services_maps_view(request):
    cnx = request.cw_request
    service_eid = cnx.form.get("srv")
    if service_eid:
        return service_data(cnx, service_eid)
    return services_data(cnx, cnx.form.get("dpt"))


def service_data(cnx, service_eid):
    query = """
    Any S, SN, SN2, SSN, SL, LAT, LONG
    WHERE S is Service, S name SN, S name2 SN2,  S short_name SSN,
    S level SL,
    S latitude LAT, S longitude LONG, S eid %(eid)s"""
    rset = cnx.execute(query, {"eid": service_eid})
    if rset:
        service = rset.one()
        return [
            {
                "name": service.dc_title(),
                "lat": service.latitude,
                "lng": service.longitude,
                "level": service.level,
            }
        ]
    return []


def services_data(cnx, dpt=None):
    kwargs = {}
    _ = cnx.__
    overlays = {
        _("level-N"): "N",
        _("level-R"): "R",
        _("level-D"): "D",
        _("level-C"): "C",
        _("level-M"): "M",
        _("level-P"): "P",
        _("level-Y"): "Y",
        _("level-U"): "U",
        _("level-H"): "H",
        _("level-I"): "I",
        _("level-E"): "E",
        _("Autres services"): "XX",
    }
    i18n = {
        "partners": {
            "partners": _("Only services contributors"),
            "nopartners": _("Services non-contributors"),
        },
        "services": {
            "allTitle": _("All services"),
        },
        "markerInfo": _("services_marker_info"),
    }

    query = (
        "Any S,SN,SN2,SSN,SPN,SINSEE,SE,SA,SZ,SC,SCC,SU,SOP,SAC,SCODE,"
        "SWU,SL,SDC,SML,LAT,LONG "
        "ORDERBY SL,SN "
        "WHERE S is Service, S name SN, S name2 SN2, S short_name SSN, "
        "S mailing_address SML, S dpt_code SDC, "
        "S phone_number SPN, S code_insee_commune SINSEE, S email SE, S address SA, "
        "S zip_code SZ, S city SC, S contact_name SCC, "
        "S uuid SU, S opening_period SOP, S annual_closure SAC, S code SCODE, "
        "S website_url SWU, S level SL, "
        "S latitude LAT, S longitude LONG, "
        "NOT S latitude NULL, NOT S longitude NULL"
    )
    if dpt:
        if not isinstance(dpt, str):
            # dpt must by a string, not a list
            dpt = ""
        kwargs = {"dpt": dpt.upper()}
        query += ", S dpt_code %(dpt)s"
    rset = cnx.execute(query, kwargs)
    features = []
    partner_services = [
        e[0] for e in cnx.execute("Any X WHERE X is Service, EXISTS(F service X, F is FindingAid)")
    ]
    nomina_services = [
        e[0]
        for e in cnx.execute("Any X WHERE X is Service, EXISTS(F service X, F is NominaRecord)")
    ]

    networks = defaultdict(list)
    data = defaultdict(list)
    for eid, name, url in cnx.execute(
        """Any S, N, U WHERE S service_social_network SN, SN name N, SN url U"""
    ):
        networks[eid].append((name, url))
    for (
        eid,
        SN,
        SN2,
        SSN,
        SPN,
        SINSEE,
        SE,
        SA,
        SZ,
        SC,
        SCC,
        SU,
        SOP,
        SAC,
        SCODE,
        SWU,
        SL,
        SDC,
        SML,
        LAT,
        LONG,
    ) in rset:
        level = SL.split("level-")[1] if SL else "XX"
        if level == "D":
            name = SN2 or SN
        else:
            name = SN or SN2
        address = " ".join([e for e in (SA, SZ, SC) if e])
        nomina = eid in nomina_services
        ead = eid in partner_services
        props = {
            "eid": str(eid),
            "name": name,
            "code": SCODE,
            "category": level,
            "mailing_address": SML,
            "dpt_code": SDC,
            "phone_number": SPN,
            "code_insee": SINSEE,
            "email": SE,
            "address": address,
            "opening_period": SOP,
            "annual_closure": SAC,
            "contact_name": SCC,
            "contact_label": _("Director") if level == "D" else _("Contact"),
            "website": SWU,
            "latitude": LAT,
            "longitude": LONG,
            "service_social_network": networks.get(eid, []),
            "partner": str(int(ead or nomina)),
            "nomina": str(int(nomina)),
            "ead": str(int(ead)),
        }
        data[level].append(Feature(geometry=Point((LONG, LAT)), properties=props))
    for level, features in data.items():
        data[level] = FeatureCollection(features)

    return {"data": data, "overlays": overlays, "i18n": i18n}


@view_config(route_name="annuaire-dpt", request_method=("GET", "HEAD"))
def annuaire_dpt_view(request):
    cwreq = request.cw_request
    return dpt_map_view(cwreq, cwreq.form.get("dpt"))


@view_config(route_name="annuaire-explicit-dpt", request_method=("GET", "HEAD"))
def annuaire_explicitdpt_view(request):
    return dpt_map_view(request.cw_request, request.matchdict["dpt"])


def dpt_map_view(cwreq, dpt=None):
    if not isinstance(dpt, str):
        # dpt must by a string, not a list
        dpt = ""
    if dpt:
        rset = cwreq.execute(
            "Any X,XN,XC ORDERBY X "
            'WHERE X is Service, X level "level-D", '
            "X dpt_code %(dpt)s, X name XN, X dpt_code XC, "
            "NOT X annex_of Y, NOT X code NULL",
            {"dpt": dpt.upper()},
        )
        if rset:
            if len(rset) != 1:
                LOG.warning(
                    "Got %s service(s) instead of 1 for dpt %s " 'and level "level-D"',
                    len(rset),
                    dpt.upper(),
                )
                # the dpt-service-map view assumes there's either 0 or 1 result.
                # if there's more than one, pick arbitrarily the first one created
                # in order to display a service and make everything editable.
                # It's just a safety belt, a hook should forbid this specific case
                rset = rset.limit(1)
        else:
            rset = None
    else:
        rset = None
    viewsreg = cwreq.vreg["views"]
    view = viewsreg.select("dpt-service-map", cwreq, rset=rset)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=rset, view=view))


@view_config(route_name="service-on-map", request_method=("GET", "HEAD"))
def annuaire_explicitservice_view(request):
    cwreq = request.cw_request
    service_eid = request.matchdict["eid"]
    rset = cwreq.execute(
        """Any X, D, Z, C, LAT, LONG WHERE X is Service, X eid %(e)s,
        X dpt_code D, X zip_code Z, X code_insee_commune C,
        X latitude LAT, X longitude LONG""",
        {"e": service_eid},
    )
    if not rset:
        LOG.exception("dpt_map_view: service %s not found", service_eid)
        raise HTTPNotFound()
    viewsreg = cwreq.vreg["views"]
    # add the service eid to zoom on
    cwreq.form["zoom"] = service_eid
    view = viewsreg.select("primary", cwreq, rset=rset)
    return Response(viewsreg.main_template(cwreq, "main-template", rset=rset, view=view))


def includeme(config):
    config.add_route("services-map-json", r"/services-map.json")
    config.add_route("service-on-map", r"/service/{eid:\d+}/*traverse")
    config.add_route("annuaire-dpt", "/annuaire/departements")
    config.add_route("annuaire-explicit-dpt", r"/annuaire/departements/{dpt:\d+[AB]}")
    config.scan(__name__)
