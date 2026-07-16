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

"""pnia_content views/templates_components"""

from cubicweb_web.view import Component
from cubicweb_web.views.basecomponents import ApplicationName, CookieLoginComponent
from cubicweb_web.views.boxes import SearchBox

ApplicationName.context = None
SearchBox.context = None


class PniaLangSwitchComponent(Component):
    __regid__ = "pnia.langswitch.component"
    order = 1

    def url(self, cur_lang, lang):
        base_url = self._cw.base_url()
        path = self._cw.url(includeparams=True)
        path = path[len(base_url) :]
        if cur_lang and (path.startswith(cur_lang + "/") or path == cur_lang):
            path = path[len(cur_lang) :]
        return "%s%s/%s" % (base_url, lang, path)

    def get_lang_info(self, cur_lang, lang):
        title = self._cw._("%s_lang" % lang)
        url = self.url(cur_lang, lang)
        return (title, url, lang.upper())

    def lang_urls(self):
        cur_lang = self._cw.lang
        yield self.get_lang_info(cur_lang, cur_lang)
        for lang in self._cw.vreg.config.available_languages():
            if lang == cur_lang:
                continue
            yield self.get_lang_info(cur_lang, lang)


def registration_callback(vreg):
    vreg.unregister(CookieLoginComponent)
    vreg.register_all(list(globals().values()), __name__)
