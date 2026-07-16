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
from lxml.html.clean import clean_html
import re

from cwtags import tag as T

from datetime import date

from cubicweb_web.view import EntityView
from cubicweb_web.views.baseviews import ListView

from cubicweb.predicates import is_instance
from cubicweb_francearchives.entities.eac import format_eac_dates
from cubicweb_francearchives.views import exturl_link


class EacEntityView(EntityView):
    __regid__ = "francearchives.eac"

    def entity_call(self, entity, **kw):
        self.w(entity.view("incontext"))

    def display_children(self, entity, child_rtype, **kw):
        children = entity.related(child_rtype)
        if children:
            self.wview("list", children, subvid="francearchives.eac", klass="eac-children-list")

    @staticmethod
    def formatted_dates(entity):
        def sortdate(date_entity):
            if date_entity.start_date is not None:
                return date_entity.start_date
            return date.max

        if entity.related("date_relation"):
            dates = sorted(entity.related("date_relation", entities=True), key=sortdate)
            return " ; ".join(
                [d.displayable_attributes for d in dates if d.displayable_attributes is not None]
            )
        return ""


class CitationEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("Citation")

    def entity_call(self, entity, **kw):
        for v in list(entity.displayable_attributes.values()):
            self.w(v)


class PostalAddressEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("PostalAddress")

    def entity_call(self, entity, **kw):
        if entity.raw_address:
            self.w(entity.printable_value("raw_address"))


class AgentPlaceEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("AgentPlace")

    def entity_call(self, entity, **kw):
        dates = self.formatted_dates(entity)
        with T.div(self.w, klass="eac-agent-place"):
            if entity.role:
                self.w(T.p(entity.role, klass="eac-agent-place--role"))
            if dates:
                self.w(T.span(dates, klass="eac-agent-place--dates"))
            if entity.items:
                self.w(T.p(entity.items, klass="eac-agent-place--items"))
        self.display_children(entity, "place_entry_relation", **kw)
        self.display_children(entity, "place_address", **kw)
        self.display_children(entity, "has_citation")


class PlaceEntryEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("PlaceEntry")

    def entity_call(self, entity, **kw):
        self.w(entity.dc_long_title())


class NameEntryEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("NameEntry")

    def entity_call(self, entity, **kw):
        title = entity.parts
        dates = self.formatted_dates(entity)
        if dates:
            title = "{} ({})".format(title, dates)
        self.w(title)


class DatedEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance(
        "AgentFunction", "Occupation", "LegalStatus", "Mandate"
    )

    def entity_call(self, entity, **kw):
        title = entity.dc_title()
        dates = self.formatted_dates(entity)
        if dates:
            title = f"{title} ({dates})" if title else dates
        if title:
            self.w(title)
        description = entity.printable_value("description")
        if description:
            self.w(description)
        if entity.items:
            self.w(entity.items)
        for relation in ("has_citation", "place_entry_relation"):
            if hasattr(entity, relation):
                self.display_children(entity, relation, **kw)


class SourceEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("EACSource")

    def entity_call(self, entity, **kw):
        url, title = entity.url, entity.title
        if entity.url:
            self.w(exturl_link(self._cw, url, label=title or url))
        elif title:
            self.w(title)
        description = entity.printable_value("description")
        if description:
            self.w(description)


class StructureEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("Structure")

    def entity_call(self, entity, **kw):
        self.w(T.span(entity.dc_title()))
        if entity.items:
            self.w(entity.items)
        self.display_children(entity, "has_citation", **kw)


class ParallelNamesEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("ParallelNames")

    def entity_call(self, entity, **kw):
        dates = self.formatted_dates(entity)
        if dates:
            self.w(dates)
        self.display_children(entity, "simple_name_relation", **kw)


class ActivityEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("Activity")

    def entity_call(self, entity, **kw):
        with T.span(self.w, klass="eac-maintenance-event--title"):
            # Activity dates are datetime.datetime
            start_date = entity.start.date() if entity.start else None
            end_date = entity.end.date() if entity.end else None
            self.w(format_eac_dates(start_date, end_date))


class RelationEacListView(ListView):
    __regid__ = "francearchives.eac.list"

    def call(self, klass=None, title=None, subvid=None, listid=None, **kwargs):
        if not self.cw_rset:
            return
        processed = set()
        with T.ul(self.w, klass="fr-list eac-related-productors"):
            for relation, target in self.cw_rset.iter_rows_with_entities():
                if target.eid in processed:
                    continue
                processed.add(target.eid)
                with T.li(self.w):
                    if target.__regid__ == "AuthorityRecord":
                        self.w(target.view("outofcontext"))
                    else:
                        self.w(relation.dc_title())
                    self.w(relation.view("francearchives.eac"))


class HistoryEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("History")

    def entity_call(self, entity, **kw):
        _ = self._cw._
        if entity.abstract:
            self.w(T.span(_("abstract"), klass="eac-sub-label"))
            self.w(entity.dc_title())
        if entity.text:
            self.w(clean_html(entity.text))
        if entity.has_event:
            self.w(T.span(_("events"), klass="eac-sub-label"))
            self.display_children(entity, "has_event", **kw)
        if entity.items:
            self.w(T.span(_("items_label"), klass="eac-sub-label"))
            self.w(entity.items)
        if entity.has_citation:
            self.w(T.span(_("citation_label"), klass="eac-sub-label"))
            self.display_children(entity, "has_citation", **kw)


class HistoricalEventEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance("HistoricalEvent")

    def entity_call(self, entity, **kw):
        _ = self._cw._
        with T.div(self.w):
            title = entity.dc_title()
            dates = self.formatted_dates(entity)
            if dates:
                title = f"{title} ({dates})"
            self.w(title)
            if entity.place_entry_relation:
                with T.div(self.w):
                    self.w(T.span(_("places_sub_label"), klass="eac-sub-label"))
                    self.display_children(entity, "place_entry_relation", **kw)


class RelationEacView(EacEntityView):
    __select__ = EacEntityView.__select__ & is_instance(
        "EACFunctionRelation",
        "EACResourceRelation",
        "AssociationRelation",
        "HierarchicalRelation",
        "ChronologicalRelation",
        "IdentityRelation",
        "FamilyRelation",
    )

    @staticmethod
    def is_displayable(desc):
        if re.match(r"^<p>\s*@.*@\s*</p>$", desc):
            return False
        return True

    def entity_call(self, entity, **kw):
        _ = self._cw._
        if entity.description and self.is_displayable(entity.printable_value("description")):
            self.w(entity.printable_value("description"))
        dates = self.formatted_dates(entity)
        if dates:
            self.w(T.span(_("dates_sub_label"), klass="eac-sub-label"))
            self.w(dates)
        places = entity.place_entry_relation
        if places:
            with T.ul(self.w, klass="fr-list"):
                for entry in entity.place_entry_relation:
                    with T.li(self.w):
                        self.w(entry.dc_long_title())
