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

from cubicweb.utils import json_dumps
from cubicweb.predicates import is_instance, empty_rset, one_line_rset, none_rset
from cubicweb_web.view import View
from cubicweb_web.views.primary import URLAttributeView

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.views import (
    JinjaViewMixin,
    get_template,
    blank_link_title,
    exturl_link,
)


def all_services(req):
    return req.execute(
        "Any X, D, N, LAT, LONG ORDERBY Z WHERE X is Service, X dpt_code D, "
        'X zip_code Z, X name N, X level "level-D", NOT X annex_of Y, '
        "X latitude LAT, X longitude LONG"
    ).entities()


class SocialNetworkUrLAttributeView(URLAttributeView):
    """open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance("SocialNetwork")

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        label = entity.printable_value("name")
        title = blank_link_title(self._cw, url)
        if url:
            self.w(exturl_link(self._cw, url, label=label, title=title))


class DeptMapForm(object):
    template = get_template("dpt-map-form.jinja2")

    map_defaults = {"disabledRegions": ["97133"]}

    def __init__(self, custom_settings=None):
        self.map_settings = merge_dicts({}, self.map_defaults, custom_settings or {})

    def render(self, req, services, selected_dpt=None):
        req.add_js("jqvmap/jquery.vmap.js")
        req.add_js("jqvmap/jquery.vmap.dpt.js")
        req.add_js("cubes.pnia_map.js")
        req.add_css("jqvmap/jqvmap.css")
        self.init_onload(req)
        return self.template.render(
            _=req._, base_url=req.base_url(), services=services, selected_dpt=selected_dpt
        )

    def init_onload(self, req):
        jscmd = "$('#dpt-vmap').dptMap(%s);" % (json_dumps(self.map_settings))
        req.add_onload(jscmd)


class DeptGeoMapForm(object):
    template = get_template("dpt-map-geo-form.jinja2")

    def render(self, req, services, selected_dpt=None):
        req.add_js("cubes.pnia_map.js")
        return self.template.render(
            _=req._, base_url=req.base_url(), services=services, selected_dpt=selected_dpt
        )


class LeafletServiceMapView(JinjaViewMixin, View):
    __regid__ = "leaflet-service-map"
    template = get_template("services-leaflet-map.jinja2")

    @property
    def breadcrumbs(self):
        return (
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self._cw._("Carte des inventaires")),
        )

    def add_css(self):
        for css in (
            "leaflet.css",
            "LeafletStyleSheet.css",
            "MarkerCluster.Default.css",
        ):
            self._cw.add_css(css)

    def add_js(self):
        for js in (
            "leaflet.js",
            "leaflet-sidebar.min.js",
            "leaflet.markercluster.js",
            "bundle-pniaservices-map.js",
            "leaflet.zoomhome.min.js",
        ):
            self._cw.add_js(js)

    def call(self):
        _ = self._cw._
        self.add_css()
        self.add_js()
        dept_map_form = DeptGeoMapForm()
        dpt = self._cw.form.get("dpt")
        if not isinstance(dpt, str):
            # dpt must by a string, not a list
            dpt = ""
        render = dept_map_form.render(self._cw, all_services(self._cw), dpt)
        self.call_template(
            map_form=render,
            markerurl=self._cw.build_url("services-map.json", dpt=self._cw.form.get("dpt", "")),
            geojson=self._cw.data_url("departements-version-simplifiee.geojson"),
            zoom=self._cw.form.get("zoom", ""),
            _=self._cw._,
            labels={
                "contact": _("Contact"),
                "address": _("Address"),
                "phone": _("Phone number"),
                "email": _("Email"),
                "mailing_address": _("Write to us"),
                "website": _("Website"),
                "code_insee": _("Code INSEE commune"),
                "opening": _("Opening period"),
                "annual_closure": _("Annual closure"),
                "coordinates": _("GPS coordinates"),
                "social_network": _("SocialNetwork_plural"),
                "useful_info": _("Useful information"),
                "fa_link": _("see service related documents"),
                "nomina_link": _("see service related nominarecords"),
            },
        )


class AbstractDptServiceMapView(JinjaViewMixin, View):
    __abstract__ = True
    __regid__ = "dpt-service-map"
    template = get_template("services-map.jinja2")
    title = None

    @property
    def breadcrumbs(self):
        return (
            (self._cw.build_url(""), self._cw._("Home")),
            (self._cw.build_url("services"), self._cw._("Service Directory")),
        )

    def call(self):
        self.call_template(
            _=self._cw._,
            title=self.title,
            a11y_alert=self.a11y_alert,
            mobile_alert=self._cw._("map_mobile_alert"),
            map=self._cw.view("leaflet-service-map", rset=self.cw_rset),
        )

    def service_directory_content(self):
        return ""

    def selected_service(self):
        raise NotImplementedError()

    @property
    def a11y_alert(self):
        return self._cw._("a11y_all_services_map_info: {link}").format(
            link=self._cw.build_url("services")
        )


class NoDepartmentMapView(AbstractDptServiceMapView):
    """XXX add a message for users?"""

    __select__ = empty_rset() | none_rset()
    eulerian_tag = True
    eulerian_pagegroup = "department_map"
    eulerian_path = "/department_map"

    @property
    def breadcrumbs(self):
        return (
            (self._cw.build_url(""), self._cw._("Home")),
            (self._cw.build_url("services"), self._cw._("Service Directory")),
            (self._cw.build_url("annuaire/departements"), self.title),
        )

    @property
    def title(self):
        return self._cw._("Map of archival")

    def selected_service(self):
        return None


class DepartmentMapView(AbstractDptServiceMapView):
    __select__ = one_line_rset() & is_instance("Service")

    @property
    def title(self):
        return self.cw_rset.one().name

    def service_directory_content(self):
        return self._cw.view("service-dpt-content", rset=self.cw_rset)

    def selected_service(self):
        return self.cw_rset.one().dpt_code
