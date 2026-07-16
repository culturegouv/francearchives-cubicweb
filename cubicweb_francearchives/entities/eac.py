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
"""cubicweb-pnia-eac entity's classes"""
from collections import OrderedDict
import datetime

from cubicweb.predicates import is_instance


import cubicweb_eac.entities as eac

from cubicweb_francearchives.entities.adapters import EntityMainPropsAdapter
from cubicweb_francearchives.entities.es import PniaIFullTextIndexSerializable
from cubicweb_francearchives.views import html_link
from cubicweb_francearchives.utils import (
    format_entity_attributes,
    cut_words,
    remove_html_tags,
    format_date,
)
from cubicweb_francearchives.xmlutils import process_html_for_csv


format_dates = "{0.day:2d}/{0.month:02d}/{0.year:4d}"


def format_eac_dates(start_date, end_date):
    """for dates processing see https://extranet.logilab.fr/ticket/663769906"""
    dates = []
    today = datetime.date.today()
    for date_ in (start_date, end_date):
        if date_:
            if date_ > today:
                continue
            date_ = format_dates.format(date_)
        if date_ and date_ not in dates:
            # avoid start_date == end_date
            dates.append(date_)
    return "-".join(dates)


def filter_none(func):
    def wrapper(*args, **kwargs):
        def filter_values(value):
            if isinstance(value, dict):
                return OrderedDict([(k, filter_values(v)) for (k, v) in list(value.items()) if v])
            elif isinstance(value, list):
                return [filter_values(v) for v in value if v]
            elif value:
                return value

        result = func(*args, **kwargs)
        return OrderedDict([(k, filter_values(v)) for (k, v) in list(result.items()) if v])

    return wrapper


class AuthorityRecord(eac.AuthorityRecord):
    rest_attr = "record_id"
    lang = "fr"

    def __init__(self, req, **extra):
        super(AuthorityRecord, self).__init__(req, **extra)
        self._authorized_name_entry = None

    @property
    def authorized_name_entry(self):
        """Initialize the NameEntry of "authorized" form variant, if any; otherwise any
        NameEntry.
        """
        if self._authorized_name_entry is None:
            rset = self._cw.find("NameEntry", name_entry_for=self, form_variant="authorized")
            if not rset:
                rset = self._cw.find("NameEntry", name_entry_for=self)
            if rset:
                self._authorized_name_entry = next(rset.entities())
        return self._authorized_name_entry

    def dc_title(self):
        """A NameEntry of "authorized" form variant, if any; otherwise any
        NameEntry.
        """
        if self.authorized_name_entry:
            return self.authorized_name_entry.parts
        return ""

    def other_names_rset(self):
        """Get all declared NameEntries for this AuthorityRecord other then the authorized one"""
        return self._cw.execute(
            """
        Any X, P, SD, ED ORDERBY SD, ED, P WHERE
        X is NameEntry, X parts P,
        X name_entry_for A, NOT X eid  %(auteid)s,
        X date_relation D?, D start_date SD, D end_date ED,
        A eid %(eid)s
        """,
            {"auteid": self.authorized_name_entry.eid, "eid": self.eid},
        )

    def parallel_names_rset(self):
        """Get all declared ParallelNames for this AuthorityRecord"""
        return self._cw.execute(
            """
        Any P WHERE P is ParallelNames,
        P parallel_names_of X,
        X eid %(eid)s""",
            {"eid": self.eid},
        )

    def ternary_relations_rset(self, etype, rtype_from, rtype_to):
        query = """
        DISTINCT Any H, C WITH H, C BEING (
        (Any H, C WHERE H is {etype},
         H {rtype_from} X, H {rtype_to} C, X eid %(eid)s, NOT C eid %(eid)s)
        UNION
        (Any H, C WHERE H is {etype},
        H {rtype_to} X, H {rtype_from} C, X eid %(eid)s, NOT C eid %(eid)s)
        )
        """
        return self._cw.execute(
            query.format(etype=etype, rtype_from=rtype_from, rtype_to=rtype_to), {"eid": self.eid}
        )

    def resource_relations_rset(self):
        return self._cw.execute(
            """
        Any R ,C  WHERE R is EACResourceRelation,
        R resource_relation_agent X,
        R resource_relation_resource C, NOT C eid %(eid)s,
        X eid %(eid)s""",
            {"eid": self.eid},
        )

    def function_relations_rset(self):
        return self._cw.execute(
            """
        Any R, C WHERE R is EACFunctionRelation,
        R function_relation_agent X,
        R function_relation_function C, NOT C eid %(eid)s,
        X eid %(eid)s
        """,
            {"eid": self.eid},
        )

    def agent_place_rset(self):
        return self._cw.execute(
            """
        Any A, C, R, I, CN, CI WHERE A is AgentPlace,
        A place_agent X, A role R, A items I,
        A has_citation C?, C note CN, C uri CI,
        X eid %(eid)s""",
            {"eid": self.eid},
        )

    def maintenance_events_rset(self, limit=None):
        limit = f" LIMIT {limit}" if limit else ""
        return self._cw.execute(
            """
        Any M, S, E, D, T, A, AT ORDERBY S DESC {} WHERE M is Activity,
        M generated X OR M used X,
        M start S, M end E, M description D,
        M type T, M agent A, M agent_type AT,
        X eid %(eid)s""".format(
                limit
            ),
            {"eid": self.eid},
        )

    def main_infos(self, export=False):
        _ = self._cw._
        if export:
            data = [(_("record_id_label"), self.record_id)]
            if self.isni:
                data.append(((_("ISNI"), self.isni)))
            return OrderedDict(data)
        if self.isni:
            return OrderedDict([(_("record_isni_label"), self.isni)])

    @property
    def main_date(self):
        """A NameEntry of "authorized" form variant, if any; otherwise any
        NameEntry.
        """
        return format_eac_dates(self.start_date, self.end_date)

    @property
    def dates(self):
        if self.start_date and self.end_date:
            if self.start_date == self.end_date:
                return format_date(self.start_date, self._cw, fmt="d MMMM y")
            start_date = format_date(self.start_date, self._cw, fmt="d MMMM y")
            end_date = format_date(self.end_date, self._cw, fmt="d MMMM y")
            return "-".join([start_date, end_date])
        date = self.start_date or self.end_date
        return format_date(date, self._cw, fmt="d MMMM y")

    def name_entry(self, klass="fr-list", subvid="francearchives.eac"):
        rset_names = self.other_names_rset()
        rset_parallel = self.parallel_names_rset()
        views = []
        if rset_names:
            view_names = self._cw.vreg["views"].select("list", self._cw, rset=rset_names)
            views.append(view_names.render(klass=klass, subvid=subvid))
        if rset_parallel:
            view_parallel = self._cw.vreg["views"].select("list", self._cw, rset=rset_parallel)
            views.append(view_parallel.render(klass=klass, subvid=subvid))
        if views:
            return {self._cw._("name_entries_label"): "".join(views)}
        return {}

    @property
    def agency(self):
        return self.reverse_agency_of[0] if self.reverse_agency_of else None

    @property
    def related_service(self):
        return self.maintainer[0] if self.maintainer else None

    @property
    def language_used(self):
        if self.languages:
            return {self._cw._("language_used_label"): self.languages}
        return {}

    @property
    def function_relations(self):
        return {
            self._cw._("function_relation_label"): self.relation_views(self.function_relations_rset)
        }

    def relation_views(self, rset_generator, **kw):
        rset = rset_generator()
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac.list", self._cw, rset=rset)
            return view.render()
        return {}

    @property
    def cpf_relations(self):
        return {
            self._cw._("cpf_relations_label"): OrderedDict(
                [
                    (
                        self._cw._("associative_link_label"),
                        self.ternary_relation_views(
                            "AssociationRelation",
                            rtype_from="association_from",
                            rtype_to="association_to",
                        ),
                    ),
                    (
                        self._cw._("temporal_link_label"),
                        self.ternary_relation_views(
                            "ChronologicalRelation",
                            rtype_from="chronological_predecessor",
                            rtype_to="chronological_successor",
                        ),
                    ),
                    (
                        self._cw._("hierarchical_link_label"),
                        self.ternary_relation_views(
                            "HierarchicalRelation",
                            rtype_from="hierarchical_parent",
                            rtype_to="hierarchical_child",
                        ),
                    ),
                    (
                        self._cw._("identity_link_label"),
                        self.ternary_relation_views(
                            "IdentityRelation", rtype_from="identity_from", rtype_to="identity_to"
                        ),
                    ),
                    (
                        self._cw._("family_link_label"),
                        self.ternary_relation_views(
                            "FamilyRelation", rtype_from="family_from", rtype_to="family_to"
                        ),
                    ),
                ]
            )
        }

    def ternary_relation_views(self, etype, **kw):
        rset = self.ternary_relations_rset(etype, kw["rtype_from"], kw["rtype_to"])
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac.list", self._cw, rset=rset)
            return view.render()
        return {}

    @property
    def record_dates(self):
        date = self.main_date
        if date:
            return {f"{self._cw._('Date')}{self._cw._(':')}": date}
        return {}

    @property
    def places(self):
        rset = self.agent_place_rset()
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("places_label"): view.render()}
        return {}

    @property
    def maintenance_events(self):
        rset = self.maintenance_events_rset(limit=1)
        if rset:
            view = self._cw.vreg["views"].select("list", self._cw, rset=rset)
            return {
                self._cw._("maintenance_event_label"): view.render(
                    klass="fr-raw-list maintenance-event", subvid="francearchives.eac"
                )
            }
        return {}

    @property
    def history(self):
        rset = self.related("history_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("history_label"): view.render()}
        return {}

    @property
    def functions(self):
        """Try to sort functions by dates"""

        rset = self._cw.execute(
            """Any X, A, SD, ED ORDERBY SD, ED WHERE X function_agent A,
               A eid %(e)s, X date_relation D?, D start_date SD, D end_date ED""",
            {"e": self.eid},
        )
        if rset:
            view = self._cw.vreg["views"].select("list", self._cw, rset=rset)
            return {
                self._cw._("functions_label"): view.render(
                    klass="fr-raw-list", subvid="francearchives.eac"
                )
            }
        return {}

    @property
    def mandates(self):
        """Try to sort mandates by dates"""

        rset = self._cw.execute(
            """Any X, A, SD, ED ORDERBY SD, ED, X WHERE X mandate_agent A,
               A eid %(e)s, X date_relation D?, D start_date SD, D end_date ED""",
            {"e": self.eid},
        )
        if rset:
            view = self._cw.vreg["views"].select("list", self._cw, rset=rset)
            return {
                self._cw._("mandates_label"): view.render(
                    klass="fr-raw-list", subvid="francearchives.eac"
                )
            }
        return {}

    @property
    def resource_relations(self):
        return {
            self._cw._("resource_relation_label"): self.relation_views(self.resource_relations_rset)
        }

    @property
    def general_context(self):
        return {
            self._cw._("general_context_label"): [
                e.content for e in self.reverse_general_context_of
            ]
        }

    @property
    def occupations(self):
        """Try to sort occupations by dates"""
        rset = self._cw.execute(
            """Any X, A, SD, ED ORDERBY SD, ED WHERE X occupation_agent A,
               A eid %(e)s, X date_relation D?, D start_date SD, D end_date ED""",
            {"e": self.eid},
        )
        if rset:
            view = self._cw.vreg["views"].select("list", self._cw, rset=rset)
            return {
                self._cw._("occupation_label"): view.render(
                    klass="fr-list eac-occupation", subvid="francearchives.eac"
                )
            }
        return {}

    @property
    def legal_statuses(self):
        """Try to sort  legal status by dates"""
        rset = self._cw.execute(
            """Any X, A, SD, ED ORDERBY SD, ED, X WHERE X legal_status_agent A,
               A eid %(e)s, X date_relation D?, D start_date SD, D end_date ED""",
            {"e": self.eid},
        )
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("legal_statuses_label"): view.render()}
        return {}

    @property
    def structure(self):
        rset = self.related("structure_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("francearchives.eac", self._cw, rset=rset)
            return {self._cw._("structure_label"): view.render()}
        return {}

    @property
    def source_entry(self):
        rset = self.related("source_agent", role="object")
        if rset:
            view = self._cw.vreg["views"].select("list", self._cw, rset=rset)
            return {
                self._cw._("source_entry_label"): view.render(
                    klass="fr-list", subvid="francearchives.eac"
                )
            }
        return {}

    def es_indexes(self):
        return self._cw.execute(
            """
            DISTINCT Any L, X, 'AgentAuthority' ORDERBY X WHERE E eid %(e)s,
            X is AgentAuthority, X same_as E, X label L
            """,
            {"e": self.eid},
        )

    @property
    def authorities(self):
        _ = self._cw._
        indexes = []
        for label, etype in ((_("all_archives_label"), "AgentAuthority"),):
            rset = self._cw.execute(
                """
                DISTINCT Any X, XP WHERE E eid %%(e)s,
                X is %s, EXISTS(R related_authority X) OR EXISTS(I authority X, I index FA),
                X same_as E, X label XP"""
                % etype,
                {"e": self.eid},
            )
            if rset:
                view_names = self._cw.vreg["views"].select("list", self._cw, rset=rset)
                indexes.append(
                    (
                        label,
                        view_names.render(
                            klass="fr-list eac-related-productors", subvid="outofcontext"
                        ),
                    )
                )
        return OrderedDict(indexes)

    @property
    def qualified_authority(self):
        return list(
            self._cw.execute(
                "Any X, L, B, C, Q ,MD, CD, E LIMIT 1 WHERE X is AgentAuthority,"
                "X same_as AR, AR is AuthorityRecord, AR eid %(eid)s, "
                "X label L, X quality True, X quality Q, X birthyear B, X deathyear C, "
                "X modification_date MD, X creation_date CD, X cwuri E",
                {"eid": self.eid},
            ).entities()
        )

    @property
    def abstract_text(self):
        """used in the linked Authority description or in AuthorityRecord search result digest"""
        description = "\n".join(
            remove_html_tags(f.text or f.abstract or "") for f in self.reverse_history_agent
        )
        return cut_words(description, 280)


class Citation(eac.Citation):
    @property
    @filter_none
    def displayable_attributes(self):
        note = self.printable_value("note")
        if self.uri:
            note += str(html_link(self._cw, self.uri, label=self._cw._("Consult the source")))
        return OrderedDict([(None, note)])


class GeneralContext(eac.GeneralContext):
    @property
    @filter_none
    def displayable_attributes(self):
        _ = self._cw._
        return OrderedDict([(_("content"), self.content), (_("items_label"), self.items)])


class EACRelation(object):
    def dc_title(self):
        return self.relation_entry or self._cw._("Missing title")


class EACFunctionRelation(EACRelation, eac.EACFunctionRelation):
    pass


class EACResourceRelation(EACRelation, eac.EACResourceRelation):
    pass


class DateEntity(eac.DateEntity):
    @property
    def raw_dates(self):
        if self.raw_date:
            dates = self.raw_date.split("-")
            if len(dates) == 1:
                return self.raw_date, None
            elif len(dates) == 2:
                return dates
        return None, None

    def format_date(self):
        """for dates processing see https://extranet.logilab.fr/ticket/6637699066376990"""
        dates = []
        today = datetime.date.today()
        raw_start_date, raw_end_date = self.raw_dates
        for date_, raw_date_ in ((self.start_date, raw_start_date), (self.end_date, raw_end_date)):
            if date_:
                if date_ > today:
                    continue
                if date_.day == 1 and date_.month == 1 and raw_date_:
                    date_ = raw_date_
                else:
                    date_ = format_dates.format(date_)
            else:
                date_ = raw_date_
            if date_ and date_ not in dates:
                # avoid start_date == end_date
                dates.append(date_)
        return "-".join(dates)

    @property
    def displayable_attributes(self):
        return self.format_date()


class PlaceEntry(eac.PlaceEntry):
    def dc_long_title(self):
        return self.name


class History(eac.History):
    def dc_title(self):
        return self.abstract or ""


class HistoricalEvent(eac.HistoricalEvent):
    def dc_title(self):
        return self.event or ""


class Occupation(eac.Occupation):
    def dc_title(self):
        return self.term or ""


class AgentFunction(eac.AgentFunction):
    def dc_title(self):
        return self.name or ""


class Mandate(eac.Mandate):
    def dc_title(self):
        return self.term or ""


class EACSource(eac.EACSource):
    def dc_title(self):
        return self.title or ""


class LegalStatus(eac.LegalStatus):
    def dc_title(self):
        return self.term or ""


class NameEntry(eac.NameEntry):
    @classmethod
    def cw_fetch_order(cls, select, attr, var):
        if attr == "parts":
            select.add_sort_var(var)


class AuthorityRecordMainPropsAdapter(EntityMainPropsAdapter):
    __regid__ = "entity.main_props"
    __select__ = is_instance("AuthorityRecord")

    def __init__(self, _cw, **kwargs):
        fmt = kwargs.get("fmt", {"text": "text/html", "vid": "incontext"})
        self.text_format = fmt["text"]
        self.vid = fmt["vid"]
        super(AuthorityRecordMainPropsAdapter, self).__init__(_cw, **kwargs)

    def csv_export_props(self):
        title = self._cw._("Download shelfmark")
        return {
            "url": self._cw.build_url("%s.csv" % self.entity.rest_path()),
            "title": title,
            "link": title,
            "filename": f"{self.entity.record_id}.csv",
        }

    def process_values_for_export(self, label, values):
        """
        For a given attribute, return its label and text values without html
        :param label: attribute label
        :param values: values to be cleaned
        :return: A list if tuple label, value

        """
        attrs = []
        label = label.strip().strip(":").strip()  # remove ":"
        cnx = self._cw
        if isinstance(values, (list, tuple)):
            attrs.append((label, "; ".join(process_html_for_csv(v, cnx) for v in values)))
        elif isinstance(values, (dict, OrderedDict)):
            for key, data in values.items():
                if data:
                    attrs.append(
                        (
                            f"{label.strip()}, {key.strip().strip(':')}",
                            process_html_for_csv(data, cnx),
                        )
                    )
        else:
            attrs.append(
                (
                    label,
                    process_html_for_csv(format_entity_attributes(values, " "), cnx),
                )
            )
        return attrs

    def metadata(self):
        last_modified = None
        metadata = []
        for (
            eid,
            start,
            end,
            description,
            activity_type,
            agent,
            agent_type,
        ) in self.entity.maintenance_events_rset():
            if activity_type == "create":
                date = start or end
                if date:
                    metadata.append(
                        (self._cw._("Creation date"), format_date(date, self._cw, fmt="d MMMM y"))
                    )
            elif activity_type == "modify":
                date = start or end
                if date:
                    last_modified = date
        if last_modified:
            metadata.append(
                (
                    self._cw._("Last update date"),
                    format_date(last_modified, self._cw, fmt="d MMMM y"),
                )
            )
        metadata.append((self._cw._("Identifier"), self.entity.record_id))
        return metadata

    def properties(self, export=False, vid="incontext", text_format="text/html"):
        self.text_format = text_format
        self.vid = vid
        entity = self.entity
        props = [
            entity.record_dates,
            entity.name_entry(),
            entity.places,
            entity.functions,
            entity.function_relations,
            entity.occupations,
            entity.legal_statuses,
            entity.language_used,
            entity.history,
            entity.general_context,
            entity.structure,
            entity.mandates,
            entity.source_entry,
            entity.main_infos(export=export),
            entity.cpf_relations,
            entity.resource_relations,
            entity.authorities,
        ]
        if export:
            if entity.related_service:
                props.insert(0, {self._cw._("FranceArchives link"): entity.absolute_url()})
                props.insert(1, {self._cw._("Name"): entity.dc_title()})
                props.append({self._cw._("publisher"): entity.related_service.dc_title()})
            props.append(entity.maintenance_events)
        attrs = []
        for data in props:
            if not data:
                continue
            for label, values in data.items():
                if export:
                    attrs.extend(self.process_values_for_export(label, values))
                else:
                    values = format_entity_attributes(values, "")
                    if values:
                        attrs.append((label, values))
        return attrs


def clean_values(data):
    return "".join([remove_html_tags(v).strip() for v in data])


class AuthorityRecordIFTIAdapter(PniaIFullTextIndexSerializable):
    __select__ = PniaIFullTextIndexSerializable.__select__ & is_instance("AuthorityRecord")

    @property
    def es_id(self):
        return self.entity.record_id

    def build_all_text(self):
        """add all indexed data in ES alltext field"""
        entity = self.entity
        all_text = [self.entity.record_id]
        for data in (
            entity.name_entry(),
            entity.functions,
            entity.occupations,
            entity.history,
            entity.legal_statuses,
        ):
            all_text.append(clean_values(data.values()))
        return " ".join(all_text).strip()

    def serialize(self, complete=True):
        data = super(AuthorityRecordIFTIAdapter, self).serialize(complete)
        data.pop("cwuri", None)
        data["title"] = self.entity.dc_title()
        data["alltext"] = self.build_all_text()
        # for the moment don't show AuthorityRecord in global search
        # data["escategory"] = ETYPE_CATEGORIES[self.entity.cw_etype]
        start_date = self.entity.start_date
        end_date = self.entity.end_date
        # bad formatted date / date range, ES will fail for those dates
        if start_date and start_date.year < 1000:
            start_date = None
        if end_date and end_date.year < 1000:
            end_date = None
        dates = {}
        if start_date:
            dates["gte"] = start_date.year
        if end_date:
            dates["lte"] = end_date.year
        if dates:
            data["dates"] = dates
            sort_date = start_date or end_date
            data["sortdate"] = sort_date.strftime("%Y-%m-%d")
        service = self.entity.related_service
        if service:
            data["service"] = {
                "eid": service.eid,
                "code": service.code,
                "level": service.level,
                "title": service.publisher(),
            }

        # for the moment don't show AuthorityRecord on related AgentAuthority pages
        # data["index_entries"] = [
        #     {"label": label, "authority": auth}
        #     for label, normalized, auth in self.entity.es_indexes()
        # ]
        return data
