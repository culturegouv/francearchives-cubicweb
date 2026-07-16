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

from cubicweb_web.view import View

from cubicweb_francearchives.views import get_template, JinjaViewMixin


class FAMapView(JinjaViewMixin, View):
    template = get_template("fa-map.jinja2")
    __regid__ = "fa-map"
    eulerian_tag = True
    eulerian_pagegroup = "ir_map"

    @property
    def breadcrumbs(self):
        return (
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self._cw._("Carte des inventaires")),
        )

    def page_title(self):
        return self._cw._("Carte des inventaires")

    def add_css(self):
        for css in ("leaflet.css", "LeafletStyleSheet.css"):
            self._cw.add_css(css)

    def add_js(self):
        for js in ("leaflet.js", "PruneCluster.js", "bundle-pnialocation-map.js"):
            self._cw.add_js(js)

    def call(self):
        self.add_css()
        self.add_js()
        self.call_template(
            a11y_alert=self._cw._("a11y_ir_map_info").format(
                link=self._cw.build_url("inventaires")
            ),
            title=self._cw._("Carte des inventaires"),
            iconurl=self._cw.data_url("images/marker-jaune.png"),
            markerurl=self._cw.build_url("fa-map.json"),
        )
