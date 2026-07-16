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

from logilab.common.decorators import cachedproperty

from logilab.mtconverter import xml_escape

from cubicweb.predicates import is_instance, match_kwargs
from cubicweb.entity import EntityAdapter, Adapter

from cubicweb_francearchives import SUPPORTED_LANGS


class OpenGraphMixin(object):
    og_type = "article"

    def authors(self):
        return []

    def images(self):
        return ()

    def locale(self):
        return "fr_FR"

    def url(self):
        pass

    def og_data(self):
        data = [
            ("locale", self.locale()),
            ("site_name", self._cw.property_value("ui.site-title")),
            ("url", self.url()),
            ("title", self.meta.title()),
            ("description", self.meta.description()),
            ("type", self.og_type),
        ]
        data.extend([("{}:author".format(self.og_type), a) for a in self.authors()])
        data.extend([("image", i) for i in self.images()])
        return [(name, xml_escape(value)) for name, value in data if value]


class HomePageOpenGrapAdpater(Adapter, OpenGraphMixin):
    __regid__ = "IOpenGraph"
    __select__ = match_kwargs({"homepage": True})
    og_type = "website"

    def locale(self):
        lang = self._cw.lang
        return "{}-{}".format(lang, lang.upper())

    def url(self):
        return xml_escape(self._cw.url())

    @cachedproperty
    def meta(self):
        return self._cw.vreg["adapters"].select("IMeta", self._cw, homepage=True)


class OpenGrapAdpater(EntityAdapter, OpenGraphMixin):
    __regid__ = "IOpenGraph"

    @cachedproperty
    def meta(self):
        return self.entity.cw_adapt_to("IMeta")

    def url(self):
        return self.entity.absolute_url()

    def images(self):
        url = getattr(self.entity, "illustration_url", None)
        if url:
            return [url]
        return []


class CommemorationItemOpenGrapAdpater(OpenGrapAdpater):
    __select__ = OpenGrapAdpater.__select__ & is_instance("CommemorationItem")

    def authors(self):
        if self.meta:
            return self.meta.author()


class CardOpenGraphAdapter(OpenGrapAdpater):
    __select__ = OpenGrapAdpater.__select__ & is_instance("Card")

    def locale(self):
        card = self.entity
        if card.wikiid:
            for lang in SUPPORTED_LANGS:
                if card.wikiid.endswith("-{}".format(lang)):
                    return "{}_{}".format(lang, lang.upper())
        return "fr_FR"
