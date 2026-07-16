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
from cubicweb.entity import EntityAdapter
from cubicweb.predicates import is_instance
from cubicweb.uilib import cut

from cubicweb_card.views import CardBreadCrumbsAdapter

from cubicweb_francearchives.utils import remove_html_tags


class FindingAidBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("FindingAid", accept_none=False)

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        fa = self.entity
        path = [(self._cw.build_url(""), _("Home"))]
        service = fa.related_service
        if service:
            path.append((service.documents_url(), service.short_name or fa.publisher))
        if fa.did[0].unitid:
            fa_label = "{} - {}".format(_("Inventory"), fa.did[0].unitid)
        else:
            fa_label = _("Inventory")
        path.append((None, fa_label))
        return path


class FAComponentBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("FAComponent", accept_none=False)

    def breadcrumbs(self, view=None, recurs=None):
        """return a list containing some:

        * tuple (url, label)
        * entity
        * simple label string

        defining path from a root to the current view

        the main view is given as argument so breadcrumbs may vary according to
        displayed view (may be None). When recursing on a parent entity, the
        `recurs` argument should be a set of already traversed nodes (infinite
        loop safety belt).
        """
        _ = self._cw._
        fa = self.entity.finding_aid[0]
        path = [(self._cw.build_url(""), _("Home"))]
        service = fa.related_service
        if service:
            path.append((service.documents_url(), service.short_name or fa.publisher))
        if fa.did[0].unitid:
            fa_label = "{} - {}".format(_("Inventory"), fa.did[0].unitid)
        else:
            fa_label = _("Inventory")
        path.extend(((fa.absolute_url(), fa_label), (cut(self.entity.dc_title(), 40))))
        return path


class AuthorityRecordBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("AuthorityRecord", accept_none=False)

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        return [
            (self._cw.build_url(""), _("Home")),
            (self._cw.build_url("authorityrecord"), _("AuthorityRecords")),
            (None, self.entity.dc_title()),
        ]


class AgentRecordBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("AgentRecord", accept_none=False)

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        return [
            (self._cw.build_url(""), _("Home")),
            (self._cw.build_url("agentrecord"), _("AgentRecords")),
            (None, self.entity.dc_title()),
        ]


class SectionBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("Section", accept_none=False)

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        path = []
        parents = self.entity.reverse_children
        while parents:
            parent = parents[0]
            path.append((parent.absolute_url(), parent.breadcrumbs_title()))
            parents = parent.reverse_children
        path.reverse()
        if recurs:
            item_path = (self.entity.absolute_url(), self.entity.breadcrumbs_title())
        else:
            item_path = (None, self.entity.breadcrumbs_title())
        return [(self._cw.build_url(""), _("Home"))] + path + [item_path]


class FACardBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("Card")

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        if self.entity.wikiid.startswith("tableau-circulaires"):
            return [
                (self._cw.build_url(""), _("Home")),
                (self._cw.build_url("circulaires"), _("Circular_plural")),
                (None, self.entity.title),
            ]
        return [
            (self._cw.build_url(""), _("Home")),
            # don't use dc_title() to avoid displaying wikiid
            (None, self.entity.title),
        ]


class CircularBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("Circular")

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        return [
            (self._cw.build_url(""), _("Home")),
            (self._cw.build_url("circulaires"), _("Circular_plural")),
            (None, self.entity.dc_title()),
        ]


class ServiceBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("Service")

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        paths = [
            (self._cw.build_url(""), _("Home")),
            (self._cw.build_url("services"), _("Service Directory")),
            (None, self.entity.dc_title()),
        ]
        if self.entity.annex_of:
            parent = self.entity.annex_of[0]
            paths.insert(
                -1,
                (parent.absolute_url(), parent.dc_title()),
            )
        return paths


class FaqItemBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("FaqItem")

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        return [
            (self._cw.build_url(""), _("Home")),
            (self._cw.build_url("faq"), _("FAQ")),
            (None, remove_html_tags(self.entity.dc_title())),
        ]


class GlossaryTermBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("GlossaryTerm")

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        return [
            (self._cw.build_url(""), _("Home")),
            (self._cw.build_url("glossaire"), _("Glossary")),
            (None, remove_html_tags(self.entity.dc_title())),
        ]


class PniaTranslationsBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance(
        "SectionTranslation", "BaseContentTranslation", "CommemorationItemTranslation"
    )

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        path = [(self._cw.build_url(""), _("Home"))]
        original = self.entity.original_entity
        path.append((original.absolute_url(), original.dc_title()))
        path.append((None, self.entity.dc_title()))
        return path


class NominaRecordBreadCrumbsAdapter(EntityAdapter):
    __regid__ = "IBreadCrumbs"
    __select__ = is_instance("NominaRecord", accept_none=False)

    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        path = [
            (self._cw.build_url(""), _("Home")),
            (self._cw.build_url("basedenoms"), _("Search in the name base")),
        ]
        if self.entity.related_service:
            service = self.entity.related_service
            path.append((service.nominarecords_url(), service.publisher()))
        path.append((None, self.entity.dc_title()))
        return path


def registration_callback(vreg):
    vreg.register_all(list(globals().values()), __name__, (FACardBreadCrumbsAdapter,))
    vreg.register_and_replace(FACardBreadCrumbsAdapter, CardBreadCrumbsAdapter)
