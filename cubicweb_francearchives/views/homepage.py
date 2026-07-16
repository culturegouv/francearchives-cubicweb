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

"""pnia_content views/homepage views and components"""
from random import randint

from cubicweb import _

from cubicweb_web.views.startup import IndexView

from cubicweb_francearchives.utils import (
    get_hp_articles,
    get_key_figures,
    get_key_figures_card,
)


class PniaIndexView(IndexView):
    needs_css = ()
    eulerian_tag = True
    eulerian_pagegroup = "home"
    editable = False
    homepage_title = _("Discover 15 centuries of archives")
    card_prefix = "hp_focus_"
    page_option = "onhp_hp"

    def heroimage_desc(self):
        res = self._cw.execute(
            "Any I, N WHERE  X is CssImage, "
            'X cssid LIKE "hero-%%", X cssid I, '
            "X cssimage_of S, S name N"
        ).rows
        build_url = self._cw.build_url
        if res:
            hcls, section_name = res[randint(0, len(res) - 1)]
        else:
            hcls, section_name = "", ""
        return {
            "hero_src": build_url("static/css/hero-{}-lr.jpg".format(section_name)),
            "hero_xl_src": build_url("static/css/hero-{}-xl.jpg".format(section_name)),
            "hero_lg_src": build_url("static/css/hero-{}-lg.jpg".format(section_name)),
            "hero_md_src": build_url("static/css/hero-{}-md.jpg".format(section_name)),
            "hero_sm_src": build_url("static/css/hero-{}-sm.jpg".format(section_name)),
            "hero_xs_src": build_url("static/css/hero-{}-xs.jpg".format(section_name)),
            "hero_class": hcls,
        }

    @property
    def icons(self):
        return {
            "hp_focus_archives": "document/document.svg",
            "hp_focus_subjects": "leisure/book.svg",
            "hp_focus_locations": "map/map.svg",
        }

    def focus(self):
        entities = []
        rset = self._cw.execute(
            f"Any X,XW,XT,XC,XCF,XS WHERE X is Card, "
            f"X wikiid XW, X title XT, X content XC, X content_format XCF, "
            f"X synopsis XS, X wikiid ILIKE '{self.card_prefix}_%'"
        )
        candidates_wikiids = []
        cards = {e.wikiid: e for e in rset.entities()}
        lang = self._cw.lang
        for wikiid in self.icons:
            card = cards.get(f"{wikiid}-fr")
            if lang != "fr":
                card = cards.get(f"{wikiid}-{lang}", card)
            if card:
                candidates_wikiids.append(card)
        for entity in candidates_wikiids:
            entities.append(
                {
                    "url": self._cw.build_url(f"card/{entity.wikiid}"),
                    "title": entity.title,
                    "content": entity.content,
                    "link_title": entity.title,
                    "icon": self.icons[entity.wikiid.split("-")[0]],
                    "lang_attr": 'lang="fr"' if lang != entity.lang else "",
                }
            )
        return entities

    def template_context(self):
        req = self._cw
        meta = req.vreg["adapters"].select("IMeta", req, homepage=True)
        og = req.vreg["adapters"].select("IOpenGraph", req, homepage=True)
        context = {
            "req": req,
            "open_graph": og.og_data(),
            "meta": meta.meta_data(),
            "entities": get_hp_articles(req, self.page_option),
            "figures": get_key_figures(req),
            "heroimage": self.heroimage_desc(),
            "focus": self.focus(),
            "editable": self.editable,
            "homepage_title": req._(self.homepage_title),
        }
        context.update(get_key_figures_card(req))
        return context

    def call(self):
        pass


class PniaNominaIndexView(PniaIndexView):
    __regid__ = "nomina-home"
    homepage_title = _("Perform a nominative search")
    card_prefix = "no_focus_"
    page_option = "onhp_nhp"

    @property
    def is_nomina(self):
        return True

    @property
    def icons(self):
        return {
            "no_focus_census": "buildings/city-hall.svg",
            "no_focus_military_register": "institutions/gendarmerie.svg",
            "no_focus_civilstatus": "document/national-identity-card.svg",
        }


def registration_callback(vreg):
    vreg.unregister(IndexView)
    vreg.register_all(list(globals().values()), __name__)
