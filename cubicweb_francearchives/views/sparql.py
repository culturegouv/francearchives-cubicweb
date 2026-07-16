# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2023
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

import urllib.parse

from cwtags import tag as T

from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb_web.view import StartupView
from cubicweb_francearchives.utils import find_card

from cubicweb_francearchives.views import JinjaViewMixin, get_template, add_js_translations
from cubicweb_francearchives.views import FaqMixin


class SparqlYasguiView(FaqMixin, JinjaViewMixin, StartupView):
    __regid__ = "sparql-yasgui"
    template = get_template("sparql-yasgui.jinja2")
    title = _("SPARQL Editor")
    eulerian_tag = True
    eulerian_pagegroup = "sparql"
    eulerian_path = "/sparql"

    def add_js(self):
        self._cw.add_js("bundle-yasgui.js")
        self._cw.add_css("yasgui.css")

    @cachedproperty
    def breadcrumbs(self):
        return [
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self._cw._("SPARQL Editor")),
        ]

    def call(self):
        self.add_js()
        add_js_translations(self._cw)
        sparql_endpoint = self._cw.vreg.config.get("sparql_endpoint")
        if not sparql_endpoint:
            with T.section(self.w, klass="document-view"):
                self.w(T.h1(self._cw._(self.title)))
                with T.div(self.w, self.w, klass="alert alert-danger"):
                    self.w(self._cw._("No sparql endpoint declared"))
        else:
            self._cw.html_headers.define_var("SPARQL_ENDPOINT", sparql_endpoint)
            self.call_template(**self.template_context())

    def template_context(self):
        return {
            "display_search_bar": True,
        }


class SparnaturalView(FaqMixin, JinjaViewMixin, StartupView):
    __regid__ = "sparnatural"
    template = get_template("sparnatural.jinja2")
    title = _("Sparnatural")
    eulerian_tag = True
    eulerian_pagegroup = "sparnatural"
    eulerian_path = "/sparnatural"

    def add_js(self):
        self._cw.add_js("sparnatural/yasgui.min.js")
        self._cw.add_js("sparnatural/sparnatural.js")
        self._cw.add_js("sparnatural/sparnatural-yasgui-plugins.js")
        self._cw.add_js("bundle-sparnatural.js")
        self._cw.add_js("sparnatural/initSparnatural.js")

        self._cw.add_css("sparnatural/sparnatural.css")
        self._cw.add_css("sparnatural/yasgui.min.css")
        self._cw.add_css(
            "https://cdn.jsdelivr.net/npm/remixicon@2.5.0/fonts/remixicon.min.css", localfile=False
        )
        self._cw.add_css("sparnatural/fa_sparnatural.css")

    @cachedproperty
    def breadcrumbs(self):
        return [
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self._cw._("Sparnatural")),
        ]

    def call(self):
        self.add_js()
        add_js_translations(self._cw)
        card = find_card(self._cw, self.__regid__, display_empty=True)
        if card is not None:
            self.wview("primary", entity=card)
        sparnatural_graph = self._cw.vreg.config.get("sparnatural_graph")
        sparql_endpoint = self._cw.vreg.config.get("sparql_endpoint")
        if sparnatural_graph:
            sparql_endpoint = (
                f"{sparql_endpoint}?default-graph-uri={urllib.parse.quote_plus(sparnatural_graph)}"
            )

        if not sparql_endpoint:
            with T.section(self.w, klass="document-view"):
                self.w(T.h1(self._cw._(self.title)))
                with T.div(self.w, self.w, klass="alert alert-danger"):
                    self.w(self._cw._("No sparql endpoint declared"))
        else:
            self._cw.html_headers.define_var("SPARQL_ENDPOINT", sparql_endpoint)
            self.call_template(**self.template_context(), endpoint=sparql_endpoint)

    def template_context(self):
        return {
            "display_search_bar": True,
            "config": self._cw.data_url("sparnatural/sparnatural_siaf.ttl"),
            "_": self._cw._,
            "lang": self._cw.lang,
            "a11y_alert": self.a11y_alert,
        }

    @property
    def a11y_alert(self):
        return self._cw._("a11y_alert_sparnatural {link}").format(
            link=self._cw.build_url("inventaires")
        )
