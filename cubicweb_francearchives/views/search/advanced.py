# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2022
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

from logilab.common.decorators import cachedproperty

from cubicweb_web.view import StartupView

from cubicweb_francearchives import display_advanced_search_predicate
from cubicweb_francearchives.views import JinjaViewMixin, get_template, add_js_translations
from cubicweb_francearchives.views import FaqMixin


class AdvancedSearchFormView(FaqMixin, JinjaViewMixin, StartupView):
    __select__ = StartupView.__select__ & display_advanced_search_predicate()
    __regid__ = "advanced-search"
    template = get_template("advanced-search.jinja2")
    faq_category = "02_faq_search"
    eulerian_tag = True
    eulerian_pagegroup = "advanced_search"
    eulerian_path = "/advanced_search"
    noreact = False

    def page_title(self):
        return f'{self._cw._("Advanced search")} ({self._cw.property_value("ui.site-title")})'

    def add_js(self):
        self._cw.add_js("bundle-advanced-search.js")

    @cachedproperty
    def breadcrumbs(self):
        return [
            (self._cw.build_url(""), self._cw._("Home")),
            (None, self._cw._("Advanced search")),
        ]

    def call(self):
        self.add_js()
        add_js_translations(self._cw)
        self.call_template(**self.template_context())

    def template_context(self):
        return {
            "display_search_bar": True,
            "faqs": self.faqs_attrs(),
        }
