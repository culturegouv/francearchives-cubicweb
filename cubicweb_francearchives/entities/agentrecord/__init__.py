# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2025
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

"""cubicweb-pnia-content persons's classes"""

from collections import OrderedDict
from datetime import datetime
import json
import re

from logilab.common.decorators import cachedproperty
from cubicweb import NoResultError, _
from cubicweb.entities import AnyEntity, fetch_config
from cubicweb.predicates import is_instance

from cubicweb_elasticsearch.entities import IFullTextIndexSerializable

from cubicweb_francearchives import INDEX_ETYPE_2_URLSEGMENT
from cubicweb_francearchives.entities.adapters import EntityMainPropsAdapter
from cubicweb_francearchives.entities.cms import compute_service_title
from cubicweb_francearchives.views import exturl_link
from cubicweb_francearchives.utils import format_date

DATABNF_ARK_RE = re.compile(r"data.bnf.fr/.{0,3}(?P<ark_id>ark:/12148/\w{2}\d{8}\w)")
WIKIDATA_RE = re.compile(r"wikidata.org/.*/(?P<wikiid>Q\d+)")

GENDER_VOCABULARY = {
    "male": "Homme",
    "female": "Femme",
    "undefined": "Non déterminé",
    "unspecified": "Non spécifié",
}

RELATIONS_GROUPS = {
    "person": OrderedDict(
        [
            ("family", "Famille"),
            ("acquaintance", "Connaissance"),
            ("professional", "Membre de"),
            ("temporal", "Lien temporel"),
            ("associative", "Association"),
            ("period", "Contexte historique"),
        ]
    ),
    "family": OrderedDict(
        [
            ("family", "Famille"),
        ]
    ),
    "corporateBody": OrderedDict(
        [
            ("professional", "Membre / professions"),
            ("temporal", "Lien temporel"),
            ("associative", "Association"),
            ("hierarchical", "Hiérarchique"),
            ("period", "Contexte historique"),
        ]
    ),
}


def sort_activities(item):
    if item is None:
        item = {}
    dates = item.get("dates", {}) or {}
    date_from = dates.get("fromDate", {}).get("date")
    term = item.get("term", {}).get("label", "")
    try:
        date_int = int(date_from) if date_from not in (None, "") else None
    except (ValueError, TypeError):
        date_int = None
    if date_int is not None:
        return (1, -date_int, term)
    else:
        return (0, 0, term)


def sort_relations(item):
    if item is None:
        item = {}
    dates = item.get("dates", {}) or {}
    date_from = dates.get("fromDate", {}).get("date")
    term = item["targetEntity"]["entity"].dc_title()
    try:
        date_int = int(date_from) if date_from not in (None, "") else None
    except (ValueError, TypeError):
        date_int = None
    if date_int is not None:
        return (1, -date_int, term)
    else:
        return (0, 0, term)


def sort_other_names(item):
    dates = item.get("useDates", {}) or {}
    date_from = dates.get("fromDate", {}).get("date")
    if date_from is not None:
        return (0, date_from, item["part"])
    else:
        return (1, None, item["part"])


class AgentRecord(AnyEntity):
    __regid__ = "AgentRecord"
    fetch_attrs, cw_fetch_order = fetch_config(["record_id", "json_data"], pclass=None)
    lang = "fr"

    def dc_title(self):
        """nameEntry may not exist on the creation"""
        return self.name_entry or self.record_id

    def rest_path(self, use_ext_eid=False):
        return f"agentrecord/{self.record_id}"

    @cachedproperty
    def data(self):
        data = self.json_data
        if isinstance(data, str):
            # sqlite return unicode instead of dict
            return json.loads(data)
        return data

    @property
    def bioghist(self):
        return self.data.get("biogHist")

    @property
    def creator(self):
        return self.created_by[0].name() if self.created_by else self.data.get("createdBy")

    @property
    def creation_mode(self):
        return self.data.get("creationMode", "manual")

    @property
    def is_derived_from_sources(self):
        return any(
            self.data.get(source)
            for source in (
                "sourceDataBnf",
                "sourceWikiData",
                "sourceAuthorityRecords",
                "sourceAuthority",
            )
        )

    @property
    def entity_type(self):
        return self.data.get("entityType")

    @property
    def exist_dates(self):
        return self.data.get("existDates")

    @property
    def gender(self):
        return (
            GENDER_VOCABULARY[self.data.get("entityGender", "unspecified")]
            if self.entity_type == "person"
            else None
        )

    @property
    def last_modification_date(self):
        return self.data.get("lastModificationDate")

    @property
    def last_modified_by(self):
        return self.data.get("lastModifiedBy")

    @property
    def legal_status(self):
        data = []
        for status in self.data.get("legalStatus", []):
            label = status.get("label").strip()
            if not label:
                continue
            value = status.get("value")
            if not value:
                data.append(label)
            else:
                try:
                    rset = self._cw.execute(
                        "Any X, L WHERE X eid %(eid)s, X label L", {"eid": value}
                    )
                except Exception:
                    self.error(f"No AgentRecordLegalStatus {label} with eid {value}  was found")
                    continue
                if rset:
                    data.append(label)
                else:
                    self.error(f"No AgentRecordLegalStatus {label} with eid {value}  was found")
                    # skip the legalStatus
                    continue
        return data

    @property
    def name_entry(self):
        return self.data.get("nameEntry")

    @property
    def maintenance_history(self):
        return self.data.get("maintenanceHistory", [])

    @property
    def maintenance_status(self):
        return self.data.get("maintenanceStatus")

    @property
    def other_names_entries(self):
        return sorted(self.data.get("otherNameEntries", []), key=sort_other_names)

    @property
    def other_names_parts(self):
        return [name["part"] for name in self.other_names_entries]

    @property
    def publication_status(self):
        return self.data.get("publicationStatus")

    @cachedproperty
    def processed_authority_records(self):
        notices = [
            s.get("value", s.get("id")) for s in self.data.get("authorityRecordsSources", [])
        ]
        if notices:
            # retrieve data from sources
            records = {url.strip("/").split("/")[-1]: url for url in notices}
            rset = self._cw.execute(
                """Any X, N, N2, L, R WHERE X is AuthorityRecord,
                   X record_id IN (%(rids)s), X record_id R,
                   X maintainer S, S name N, S name2 N2, S level L
                """
                % {"rids": ", ".join([f'"{s}"' for s in records.keys()])}
            )
            return self.build_data_from_authorityrecords(rset, records)
        return []

    @cachedproperty
    def processed_identityids(self):
        sources = []
        prefix = _("notice in %s")
        for entry in self.data.get("identityIds", []):
            url = entry.get("url")
            source = entry["source"]
            title = entry.get("linkTitle")
            if url:
                value = exturl_link(self._cw, url, label=entry["id"])
            else:
                value = entry["id"]
            label = f"{title} {source}" if title else self._cw._(prefix) % source
            html = f"{label}{self._cw._(':')} {value}"
            sources.append(
                {
                    "label": label,
                    "url": url,
                    "id": entry["id"],
                    "vocab": source,
                    "html": html,
                }
            )
        return sources

    @cachedproperty
    def processed_functions(self):
        functions = [r for r in self.data.get("relations", []) if r.get("targetType") == "function"]
        return [
            {
                "place": self.process_place(field.get("place")),
                "dates": field.get("dates"),
                "term": field["targetEntity"],
            }
            for field in functions
        ]

    def get_processed_relation(self, field):
        target_entity = field.get("targetEntity")
        target_agent = self.get_related_agent_info(target_entity["value"], field)
        return {
            "targetEntity": target_agent or target_entity,
            "targetRole": field.get("targetRole"),
            "place": self.process_place(field.get("place")),
            "dates": field.get("dates"),
        }

    @cachedproperty
    def processed_relations(self):
        relation_groups = RELATIONS_GROUPS.get(self.entity_type, {})
        relations = OrderedDict({key: [] for key in relation_groups.values()})
        for field in self.data.get("relations", []):
            relation_type = field["relationType"]["value"]
            if relation_type == "function":
                # this relation will be displayed as function in processed_functions
                continue
            if relation_type == "partial":
                relation_type = "professional"
            group = relation_groups.get(relation_type, relation_type)
            if group not in relations:
                relations.update({group: []})
            relations[group].append(self.get_processed_relation(field))
        return relations

    def get_occupations_from_relation(self):
        occupations = []
        for relation in self.data.get("relations", []):
            if relation.get("relationType", {}).get("value") == "professional":
                occupations.append(
                    {
                        "term": relation["targetRole"],
                        "dates": relation.get("dates"),
                        "institution": relation["targetEntity"],
                        "place": self.process_place(relation.get("place")),
                    }
                )
        return occupations

    @cachedproperty
    def processed_occupations(self):
        if self.entity_type not in ("person", "corporateBody"):
            return []
        occupation_field = "occupations" if self.entity_type == "person" else "functions"
        activities = [
            {
                "place": self.process_place(field.get("place")),
                "dates": field.get("dates"),
                "term": field["term"],
            }
            for field in self.data.get(occupation_field, [])
        ]
        return sorted(activities, key=sort_activities)

    def processed_person_exist_infos(self):
        birth_info = dict.fromkeys(["date", "certainty", "place"])
        death_info = dict.fromkeys(["date", "certainty", "place"])
        if self.exist_dates:
            birth_info["date"] = self.exist_dates["fromDate"].get("date")
            birth_info["certainty"] = self.exist_dates["fromDate"].get("certainty")
            death_info["date"] = self.exist_dates["toDate"].get("date")
            death_info["certainty"] = self.exist_dates["toDate"].get("certainty")
        for name, place in self.processed_exist_places.items():
            place = format_place(self._cw, place)
            if name == "birthPlace":
                birth_info["place"] = place
            if name == "deathPlace":
                death_info["place"] = place
        return birth_info, death_info

    def processed_corporate_body_exist_infos(self):
        start_info = dict.fromkeys(["date", "certainty", "place"])
        stop_info = dict.fromkeys(["date", "certainty", "place"])
        if self.exist_dates:
            start_info["date"] = self.exist_dates["fromDate"].get("date")
            start_info["certainty"] = self.exist_dates["fromDate"].get("certainty")
            stop_info["date"] = self.exist_dates["toDate"].get("date")
            stop_info["certainty"] = self.exist_dates["toDate"].get("certainty")
        activity_info = []
        for name, place in self.processed_exist_places.items():
            if name == "activityPlaces":
                activity_info.extend([format_place(self._cw, p) for p in place])
        return start_info, stop_info, activity_info

    @cachedproperty
    def processed_exist_places(self):
        places = {}
        for field in ("birthPlace", "deathPlace", "activityPlaces"):
            place = self.data.get(field)
            if not place:
                continue
            if field == "activityPlaces":
                data = [self.process_place(p) for p in place]
            else:
                data = self.process_place(place)
            places[field] = data
        return places

    def process_place(self, place):
        if not place:
            return
        data = {"placeName": place.get("placeName")}
        if place.get("geographicCoordinates"):
            data["geographicCoordinates"] = place["geographicCoordinates"]
        if place and "authority" in place:
            authority = place.get("authority")
            if authority and authority.get("value"):
                data["authority"] = self.get_related_authority_info(
                    "LocationAuthority", authority["value"]
                )
        data.update({"dates": place.get("dates"), "address": place.get("address")})
        return data

    @cachedproperty
    def processed_sources(self):
        sources = []
        prefix = _("notice in %s")
        for field, vocab in (
            ("sourceDataBnf", "DataBnF"),
            ("sourceWikiData", "Wikidata"),
        ):
            url = self.data.get(field, "").strip()
            source_re = DATABNF_ARK_RE if vocab == "data.bnf" else WIKIDATA_RE
            notice_id = url
            match = source_re.search(url)
            if match:
                notice_id = match.group(1)
            label = self._cw._(prefix) % vocab
            if url:
                sources.append(
                    {
                        "label": label,
                        "url": url,
                        "id": notice_id,
                        "vocab": vocab,
                        "html": vocab,
                    }
                )
        notices = self.data.get("sourceAuthorityRecords", [])
        if notices:
            # retrieve data from sources
            if isinstance(notices[0], str):
                # REMOVE ME
                records = {url.strip("/").split("/")[-1]: url for url in notices}
            else:
                records = {
                    value["url"].strip("/").split("/")[-1]: value["url"] for value in notices
                }
            rset = self._cw.execute(
                """Any X, N, N2, L, R WHERE X is AuthorityRecord,
                   X record_id IN (%(rids)s), X record_id R,
                   X maintainer S, S name N, S name2 N2, S level L
                """
                % {"rids": ", ".join([f'"{s}"' for s in records.keys()])}
            )
            sources.extend(self.build_data_from_authorityrecords(rset, records, with_link=False))
            # TODO: if no source found ?
        sources.extend(self.processed_sourceid)
        return sources

    def build_data_from_authorityrecords(self, rset, records, with_link=True):
        sources = []
        for record, name, name2, level, record_id in rset.iter_rows_with_entities():
            service_label = compute_service_title(self._cw, name, name2, level)
            record_title = record.dc_title()
            label = self._cw._("notice_edited_by %s") % service_label
            html = (
                f"{exturl_link(self._cw, record.absolute_url(), label=record_title)} {label}"
                if with_link
                else f"{record_title} {label}"
            )
            sources.append(
                {
                    "label": f"{record_title} {label}",
                    "url": records[record_id],
                    "id": record_id,
                    "vocab": "XXX",
                    "html": html,
                }
            )
        return sources

    @cachedproperty
    def processed_sourceid(self):
        sources = []
        prefix = _("notice in %s")
        for entry in self.data.get("sourceIds", []):
            source = entry["source"]
            title = entry.get("linkTitle")
            label = f"{title} {source}" if title else self._cw._(prefix) % source
            url = entry["url"]
            html = f"{exturl_link(self._cw, url, label=label)}"
            if entry.get("id"):
                html = f"{html} / {source}%s{entry['id']}" % self._cw._(":")
            label = source
            sources.append(
                {
                    "label": source,
                    "url": url,
                    "id": entry.get("id"),
                    "vocab": "XXX",
                    "html": html,
                }
            )
        return sources

    def get_related_agent_info(self, identifier, relation):
        agent_type = relation.get("agentType")
        if agent_type != "agent_extern":
            query = "Any X WHERE X is AgentRecord, X record_id %(record_id)s"
            etype = "AgentRecord"
        else:
            if relation["targetRole"]["value"] == "period_of_activity":
                query = "Any X WHERE X is Concept, X cwuri %(cwuri)s"
                etype = "Concept"
            else:
                query = "Any X WHERE X eid %(eid)s"
                etype = "AgentReferenceVocabulary"
        try:
            entity = self._cw.execute(
                query, {"record_id": identifier, "eid": identifier, "cwuri": identifier}
            ).one()
        except NoResultError:
            self.error(f"No {etype} with identifier '{identifier}' was found")
            return {}
        base_url = self._cw.vreg.config.get("base-url")
        base_url = f"{base_url.rstrip('/')}/" if base_url else self._cw.base_url()
        agent_type = (
            entity.entity_type if entity.cw_etype == "AgentRecord" else relation.get("targetType")
        )
        return {
            "entity": entity,
            "url": f"{base_url}agentrecord/identifier",
            "type": agent_type,
        }

    def get_related_authority_info(self, etype, eid):
        try:
            entity = self._cw.execute(
                f"Any X WHERE X is {etype}, X eid %(eid)s", {"eid": eid}
            ).one()
        except NoResultError:
            self.error(f"No entity {etype}/{eid} was found")
            return {}
        base_url = self._cw.vreg.config.get("consultation-base-url")
        base_url = f"{base_url.rstrip('/')}/" if base_url else self._cw.base_url()
        return {
            "entity": entity,
            "url": f"{base_url}{INDEX_ETYPE_2_URLSEGMENT[etype]}/{eid}",
        }

    def clone(self):
        cnx = self._cw
        json_data = self.json_data.copy()
        json_data["nameEntry"] = json_data["nameEntry"] + "-copie"
        agent_clone = cnx.create_entity("AgentRecord", json_data=json_data)
        cnx.commit()
        return agent_clone


def format_eac_dates_as_string(entries):
    """see issues/685 for dates display"""
    if not entries:
        return
    formatted_dates = []
    if not isinstance(entries, (list, tuple)):
        entries = [entries]
    for entry in entries:
        from_date = entry.get("fromDate")
        to_date = entry.get("toDate")
        dates = {"fromDate": "", "toDate": ""}
        if from_date:
            date = from_date.get("date")
            if date:
                dates["fromDate"] = str(date)
        if to_date:
            date = to_date.get("date")
            if date:
                dates["toDate"] = str(date)
            else:
                if to_date.get("status") == "ongoing":
                    dates["toDate"] = "..."
        if dates["fromDate"] or dates["toDate"]:
            formatted_dates.append("-".join([d for d in [dates["fromDate"], dates["toDate"]]]))
    return ", ".join(formatted_dates)


def format_live_info(cnx, entry):
    parts = []
    uncertain = ""
    if entry.get("certainty"):
        if entry["certainty"] == "approximate":
            parts.append("environ")
        elif entry["certainty"] == "uncertain":
            uncertain = "?"
    if entry.get("date"):
        parts.append(f"{entry['date']}{uncertain}")
    if entry.get("place"):
        parts.append("à %s" % entry["place"])
    return f"<p>{' '.join(parts)}</p>" if parts else ""


def format_date_with_uncertainty(date_descr):
    date = date_descr.get("date")
    if date:
        if date_descr.get("certainty"):
            if date_descr["certainty"] == "approximate":
                date = f"environ {date}"
            elif date_descr["certainty"] == "uncertain":
                date = f"{date}?"
    else:
        if date_descr.get("status") == "ongoing":
            date = "en cours"
        else:
            date = "?"
    return date


def format_dates_for_activity(dates):
    if not dates:
        return ""
    from_date = format_date_with_uncertainty(dates.get("fromDate", {}))
    to_date = format_date_with_uncertainty(dates.get("toDate", {}))
    if from_date != "?" or to_date != "?":
        return f"dates : {from_date}-{to_date}"
    return ""


def format_activity(cnx, term, place=None, dates=None, institution=None):
    if not isinstance(term, str):
        return ""
    activities_data = [term]
    if place:
        activities_data.append(format_place(cnx, place))
    if institution:
        activities_data.append(institution.get("label", ""))
    if dates:
        activities_data.append(format_dates_for_activity(dates))
    return " ; ".join(activities_data)


def format_place(cnx, place):
    authority_info = place.get("authority")
    if authority_info:
        value = authority_info["entity"].view("outofcontext")
    else:
        value = place.get("placeName")
    dates = place.get("dates")
    if dates:
        value = f"{value} {format_eac_dates_as_string(dates)}"
    address = place.get("address")
    if address:
        value = f"<div><p>{value}</p><p>{address}</p></div>"
    return value or ""


def format_as_list(data):
    if data:
        html = [f"<li>{value[0]} {value[1]}</li>" for value in data]
        return f'<ul class="fr-list">{"".join(html)}</ul>'
    return ""


def format_relation(cnx, relation):
    _ = cnx._
    data = [
        (cnx._("Relation type:"), relation["relationType"].get("label")),
        (cnx._("Role:"), relation["targetRole"].get("label")),
        (cnx._("Dates:"), format_eac_dates_as_string(relation["dates"])),
    ]
    place = relation.get("place")
    if place:
        data.append((cnx._("Place:"), format_place(cnx, place)))
    data = [value for value in data if value[1]]
    target_entity = relation["targetEntity"].get("entity")
    target = relation["targetEntity"]["entity"].view("outofcontext") if target_entity else "???"
    return f"""
    <li><p>{target}</p>{format_as_list(data)}</li>"""


class AgentRecordMainPropsAdapter(EntityMainPropsAdapter):
    __select__ = EntityMainPropsAdapter.__select__ & is_instance("AgentRecord")
    """see issues/685 for dates display"""

    places_vocabulary = {
        "birthPlace": _("birthplace_label"),
        "deathPlace": _("deathplace_label"),
        "activityPlaces": _("activityplace_label"),
    }

    def notice_metadata(self):
        _ = self._cw._
        data = [
            (_("Last updated"), self.last_modified),
            (_("State"), self.state),
        ]
        return [d for d in data if d[1]]

    def metadata(self):
        _ = self._cw._
        data = [
            (_("Identifier"), self.entity.record_id),
            (
                _("Creation date"),
                format_date(self.entity.creation_date, self._cw, fmt="d MMMM y"),
            ),
            (_("Last update date"), self.last_modification_date()),
            (_("permalink_label"), self.entity.ark or "TODO ark"),
        ]
        if self.entity.same_as:
            data.append(
                (
                    _("all_archives_fa_label"),
                    self.entity.same_as[0].view("outofcontext"),
                )
            )
        return [d for d in data if d[1]]

    def main_props(self, export=False, vid="incontext", text_format="text/html"):
        _ = self._cw._
        data = {
            # _("exist_dates_label"): self.exist_dates,
            _("name_entries_label"): self.format_other_names(),
            _("gender_label"): self.entity.gender,
            _("legal_status_label"): self.entity.legal_status,
        }
        if self.entity.entity_type == "person":
            data.update(self.format_person_infos())
        elif self.entity.entity_type == "corporateBody":
            data.update(self.format_corporate_body_infos())
        data.update(
            {
                _("history_label"): self.entity.bioghist,
                _("relations_label"): self.format_relations(),
                _("identityid_label"): [
                    s["html"]
                    for s in self.entity.processed_identityids
                    + self.entity.processed_authority_records
                ],
                _("source_entry_label"): [s["html"] for s in self.entity.processed_sources],
            }
        )
        if self.entity.same_as:
            data[_("all_archives_fa_label")] = self.entity.same_as[0].view("outofcontext")
        return data

    def format_activities(self, label, activities):
        data = []
        for activity in activities:
            term = activity.get("term")
            if not term:
                continue
            if term["value"]:
                rset = self._cw.execute(
                    "Any X, L WHERE X eid %(eid)s, X label L", {"eid": term["value"]}
                )
                if rset:
                    term = rset.one().view("outofcontext")
                else:
                    self.error(f"No entity {term['label']} with eid {term['value']}  was found")
                    # skip the activity
                    continue
            data.append(
                format_activity(
                    self._cw,
                    term,
                    activity.get("place"),
                    activity.get("dates"),
                    activity.get("institution"),
                )
            )
        return {label: data}

    def format_person_infos(self):
        data = self.build_personal_info()
        activities = self.entity.processed_occupations
        if activities:
            data.update(self.format_activities(self._cw._("occupations_label"), activities))
        if self.entity.processed_functions:
            data.update(
                self.format_activities(
                    self._cw._("functions_label"), self.entity.processed_functions
                )
            )
        return data

    def build_personal_info(self):
        data = {}
        birth_info, death_info = self.entity.processed_person_exist_infos()
        if birth_info:
            data[self._cw._("birth_info_label")] = format_live_info(self._cw, birth_info)
        if death_info:
            data[self._cw._("death_info_label")] = format_live_info(self._cw, death_info)
        return data

    def format_corporate_body_infos(self):
        data = self.build_corporate_body_info()
        if self.entity.processed_occupations:
            data.update(
                self.format_activities(
                    self._cw._("functions_label"), self.entity.processed_occupations
                )
            )
        return data

    def build_corporate_body_info(self):
        data = {}
        start_info, stop_info, activity_info = self.entity.processed_corporate_body_exist_infos()
        if start_info:
            data[self._cw._("start_date_label")] = format_live_info(self._cw, start_info)
        if stop_info:
            data[self._cw._("stop_date_label")] = format_live_info(self._cw, stop_info)
        if activity_info:
            data["Lieux"] = "; ".join(activity_info)
        return data

    def build_family_info(self):
        data = {"info": "TODO"}
        return data

    def build_places(self):
        data = {}
        for name, place in self.entity.processed_exist_places.items():
            label = self.places_vocabulary[name]
            if name == "activityPlaces":
                value = [format_place(self._cw, p) for p in place]
            else:
                value = format_place(self._cw, place)
            data[self._cw._(label)] = value
        return data

    def format_relations(self):
        html = []
        for label, rels in self.entity.processed_relations.items():
            html_group = []
            for rel in sorted(rels, key=sort_relations):
                term = rel["targetEntity"]["entity"].view("outofcontext")
                html_group.append(
                    format_activity(
                        self._cw,
                        term,
                        rel.get("place"),
                        rel.get("dates"),
                        rel.get("targetRole"),
                    )
                )
            if html_group:
                html_group = [f"<li>{value}</li>" for value in html_group]
                data = f"<ul class='fr-list eac-relations'>{''.join(html_group)}</ul>"  # noqa
                html.extend((f'<h3 class="fr-text--lead fr-my-2w">{label}</h3>', data))
        return "".join(html)

    @property
    def exist_dates(self):
        exist_dates = self.entity.exist_dates
        if exist_dates:
            return format_eac_dates_as_string([exist_dates])

    def last_modification_date(self, fmt="short"):
        l_date = self.entity.last_modification_date
        if l_date:
            return format_date(datetime.fromisoformat(l_date), self._cw, fmt)

    @property
    def last_modified(self):
        return self._cw._("By %s on %s") % (
            self.last_modified_by,
            self.last_modification_date(fmt="dd/MM/yyyy HH:mm"),
        )

    @property
    def last_modified_by(self):
        login = self.entity.last_modified_by
        if login:
            rset = self._cw.execute(
                """Any F, L WHERE X is CWUser,
                   X login %(login)s, X firstname F, X surname L""",
                {"login": login},
            )
            if rset:
                name = " ".join([r for r in (rset[0][0], rset[0][1]) if r])
                return f"{name} ({login})" if name else login
            self.error(f"No CWUser with login {login} found in the database")
            return login

    def format_other_names(self):
        other_names = self.entity.other_names_entries
        if not other_names:
            return []
        data = []
        for name in other_names:
            data.append(
                format_activity(
                    self._cw,
                    name.get("part", ""),
                    dates=name.get("useDates"),
                )
            )
        return data

    @property
    def state(self):
        adapted = self.entity.cw_adapt_to("IWorkflowable")
        if adapted:
            return self._cw._(adapted.state) if adapted.state else ""


class IAgentsReferenceIndexSerializable(IFullTextIndexSerializable):
    """Adapter to serialize AgentRecord."""

    __regid__ = "IAgentsReferenceIndexSerializable"
    __select__ = is_instance("AgentRecord")

    @property
    def es_id(self):
        return self.entity.record_id

    def _extract_term_label(self, term_data):
        """Extract label from term data (dict or string)"""
        if isinstance(term_data, dict):
            return term_data.get("label", "")
        return str(term_data)

    def process_all_text(self):
        """compute all text from json_data"""
        entity = self.entity
        content = [entity.dc_title(), *entity.other_names_parts]

        if entity.bioghist:
            content.append(entity.bioghist)

        for occ in entity.processed_occupations:
            content.append(self._extract_term_label(occ.get("term", {})))
            if occ.get("note"):
                content.append(occ["note"])

        for func in entity.processed_functions:
            content.append(self._extract_term_label(func.get("term", {})))

        exist_places = entity.processed_exist_places
        for place_key in ["birth_place", "death_place"]:
            place_data = exist_places.get(place_key)
            if place_data and isinstance(place_data, dict):
                content.append(place_data.get("placeName", ""))

        for place_data in exist_places.get("activity_places", []):
            if isinstance(place_data, dict):
                content.append(place_data.get("placeName", ""))

        content.extend(entity.legal_status)
        content.append(entity.gender)

        for rel_list in entity.processed_relations.values():
            for rel in rel_list:
                target = rel.get("targetEntity", {})
                if isinstance(target, dict):
                    content.append(target.get("label", ""))

        return " ".join(filter(None, content))

    def process_all_metadata(self):
        """compute all metadata from json_data"""
        entity = self.entity
        creation_date = entity.creation_date.strftime("%d/%m/%Y")
        content = [entity.creator or "", creation_date]
        l_date = entity.last_modification_date
        if l_date:
            content.append(datetime.fromisoformat(l_date).strftime("%d/%m/%Y"))
        return " ".join(filter(None, content))

    def _extract_date_value(self, date_info):
        """Extract date string from date_info dict"""
        if not date_info:
            return None
        return date_info.get("date")

    def _extract_date_range(self, date_info):
        """Extract integer range from date_info for filtering"""
        if not date_info:
            return None
        date = date_info.get("date")
        if date and isinstance(date, int):
            return {"gt": date - 1, "lt": date + 1}
        return None

    def _serialize_relations(self, relations):
        """Serialize all relations to searchable text"""
        content = []
        for rel_type, rel_list in relations.items():
            for rel in rel_list:
                term = rel.get("term", {})
                if isinstance(term, dict):
                    content.append(term.get("label", ""))
                if rel.get("note"):
                    content.append(rel["note"])
                target = rel.get("targetEntity", {})
                if isinstance(target, dict):
                    content.append(target.get("label", ""))
        return " ".join(filter(None, content))

    def _serialize_relations_by_type(self, relations):
        """
        Serialize relations grouped by type with counts.
        Returns list of dicts for nested ES field.
        """
        result = []
        for rel_type, rel_list in relations.items():
            terms = []
            for rel in rel_list:
                target_role = rel.get("targetRole", {})
                if isinstance(target_role, dict):
                    terms.append(target_role.get("label", ""))

            result.append(
                {
                    "type": rel_type,
                    "count": len(rel_list),
                    "role": " ".join(filter(None, terms)),
                }
            )

        return result

    def _serialize_authority_records(self, authority_records):
        return [
            {
                "record_id": r.get("id"),
                "label": r.get("label"),
                "service": r.get("vocab"),
                "url": r.get("url"),
            }
            for r in authority_records
        ]

    def _serialize_sources(self, sources):
        content = []
        for source in sources:
            if isinstance(source, dict):
                content.extend([source.get(k) for k in ("label", "vocab", "id") if source.get(k)])
            elif isinstance(source, str):
                content.append(source)
        return " ".join(filter(None, content))

    def _serialize_sources_from_json(self):
        """
        Extract external sources from json_data.
        Priority: sourceWikiData → sourceDataBnf → identityIds
        → sourceIds (no duplicates, no empty URIs)
        """
        entity = self.entity
        sources_data = []
        seen_uris = set()

        # 1. sourceWikiData (prioritaire)
        wikidata_url = entity.json_data.get("sourceWikiData", "").strip()
        if wikidata_url:
            sources_data.append(
                {
                    "label": "Wikidata",
                    "uri": wikidata_url,
                    "source": "wikidata",
                }
            )
            seen_uris.add(wikidata_url)

        # 2. sourceDataBnf (prioritaire)
        databnf_url = entity.json_data.get("sourceDataBnf", "").strip()
        if databnf_url:
            sources_data.append(
                {
                    "label": "DataBnF",
                    "uri": databnf_url,
                    "source": "data.bnf",
                }
            )
            seen_uris.add(databnf_url)

        # 3. identityIds (sans doublons, uniquement avec URI)
        for entry in entity.json_data.get("identityIds", []):
            url = entry.get("url", "").strip()
            if url and url not in seen_uris:
                sources_data.append(
                    {
                        "label": entry.get("linkTitle") or entry["source"],
                        "uri": url,
                        "source": entry["source"].lower(),
                    }
                )
                seen_uris.add(url)

        # 4. sourceIds (sans doublons, uniquement avec URI)
        for entry in entity.json_data.get("sourceIds", []):
            url = entry.get("url", "").strip()
            if url and url not in seen_uris:
                sources_data.append(
                    {
                        "label": entry.get("linkTitle") or entry["source"],
                        "uri": url,
                        "source": entry["source"].lower(),
                    }
                )

        return sources_data

    def _get_reverse_same_as(self):
        rset = self._cw.execute(
            """Any X WHERE X is AgentAuthority, X same_as Y, Y eid %(eid)s""",
            {"eid": self.entity.eid},
        )

        def serialize_auth(auth):
            auth.complete()
            return {
                "eid": auth.eid,
                "label": auth.label or auth.dc_title(),
                "ark": getattr(auth, "ark", None),
            }

        return [serialize_auth(auth) for auth in rset.entities()]

    def get_functions(self):
        return [
            f.get("term", {}).get("label")
            for f in self.entity.processed_functions
            if f.get("term", {}).get("label")
        ]

    def get_occupations(self):
        return [
            f.get("term", {}).get("label")
            for f in self.entity.processed_occupations
            if f.get("term", {}).get("label")
        ]

    def serialize(self, complete=True):
        entity = self.entity
        exist_places = entity.processed_exist_places

        if entity.entity_type == "person":
            birth_info, death_info = entity.processed_person_exist_infos()
            start_info = stop_info = {}
        else:
            start_info, stop_info, _ = entity.processed_corporate_body_exist_infos()
            birth_info = death_info = {}

        date_val = lambda info: info.get("date") if info else None
        date_range = lambda info: (
            {"gt": info["date"] - 1, "lt": info["date"] + 1}
            if info and isinstance(info.get("date"), int)
            else None
        )

        place_name = lambda key: (
            exist_places.get(key, {}).get("placeName")
            if isinstance(exist_places.get(key), dict)
            else None
        )

        return {
            "alltext": self.process_all_text(),
            "allmetadata": self.process_all_metadata(),
            "creation_date": entity.creation_date,
            "created_by": entity.creator,
            "eid": entity.eid,
            "is_published": entity.publication_status == "published",
            "modified_by": entity.last_modified_by,
            "modification_date": entity.modification_date,
            "name": entity.dc_title(),
            "other_names": entity.other_names_parts,
            "record_id": entity.record_id,
            "text": [entity.dc_title()] + entity.other_names_parts,
            "type": entity.entity_type,
            "ark": entity.ark,
            "gender": entity.gender,
            "legal_status": " ".join(entity.legal_status),
            "birth_date": date_val(birth_info),
            "birth_dates": date_range(birth_info),
            "death_date": date_val(death_info),
            "death_dates": date_range(death_info),
            "start_date": date_val(start_info),
            "start_dates": date_range(start_info),
            "stop_date": date_val(stop_info),
            "stop_dates": date_range(stop_info),
            "birth_place": place_name("birthPlace"),
            "death_place": place_name("deathPlace"),
            "activity_places": " ".join(filter(None, exist_places.get("activity_places", []))),
            "occupations": " ".join(
                self._extract_term_label(o.get("term", "")) for o in entity.processed_occupations
            ),
            "occupations_index": [
                self._extract_term_label(o.get("term", "")) for o in entity.processed_occupations
            ],
            "functions": " ".join(
                self._extract_term_label(f.get("term", "")) for f in entity.processed_functions
            ),
            "relations": self._serialize_relations(entity.processed_relations),
            "relations_by_type": self._serialize_relations_by_type(entity.processed_relations),
            "relations_count": sum(len(v) for v in entity.processed_relations.values()),
            "bioghist": entity.bioghist,
            "sources": self._serialize_sources_from_json(),
            "sources_count": len(self._serialize_sources_from_json()),
            "source_authority_records": entity.json_data.get("sourceAuthorityRecords", []),
            "authority_records_links": self._serialize_authority_records(
                entity.processed_authority_records
            ),
            "same_as_authorities": self._get_reverse_same_as(),
            "creation_mode": entity.creation_mode,
            "publication_status": entity.publication_status,
            "maintenance_status": entity.maintenance_status,
        }
