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

from datetime import datetime
from lxml import etree, html

from logilab.common.date import ustrftime
from cubicweb.predicates import is_instance
from cubicweb_francearchives import SIAF_CODE
from cubicweb_francearchives.entities.adapters import AbstractXmlAdapter


def transform_bioghist_with_lxml(value):
    tree = html.fromstring(value)
    for ul in tree.xpath("//ul"):
        ul.tag = "list"
    for li in tree.xpath("//li"):
        li.tag = "item"
    for p in tree.xpath("//p"):
        if "abstract" in p.attrib.get("class", ""):
            p.tag = "abstract"
        p.attrib.clear()
    return tree


class AuthorityRecordEACAdapter(AbstractXmlAdapter):
    __regid__ = "EAC-CPF-v2"
    __select__ = is_instance("AgentRecord")

    namespaces = {
        None: "https://archivists.org/ns/eac/v2",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xlink": "http://www.w3.org/1999/xlink",
    }

    standard_datetime_fmt = "%Y-%m-%dT%H:%M:%S"
    standard_date_fmt = "%Y-%m-%d"
    fr_datetime_fmt = "%d/%m/%Y %H:%M"

    places_vocabulary = {
        "birthPlace": "Lieu de naissance",
        "deathPlace": "Lieu de sépulture",
        "activityPlaces": "Lieu d'activité",
    }

    @property
    def file_name(self):
        """Return a file name for the dump."""
        return f"{self.entity.record_id}.xml"

    def dump(self):
        """Return an XML string representing the given agent using the EAC-CPF schema."""
        # Root element
        eac_elt = self.element(
            "eac",
            attributes={
                "xsi:schemaLocation": (
                    "https://archivists.org/ns/eac/v2  "
                    "https://eac.staatsbibliothek-berlin.de/schema/v2/eac.xsd"
                ),
                "audience": "external",
            },
        )
        # Top elements: control & cpfDescription
        self.control_element(eac_elt)
        self.cpfdescription_element(eac_elt)
        tree = etree.ElementTree(eac_elt)
        return etree.tostring(tree, xml_declaration=True, encoding=self.encoding, pretty_print=True)

    def control_element(self, eac_elt):
        control_attributes = {
            "audience": "external",
            "maintenanceStatus": self.maintenance_status,
            "publicationStatus": self.publication_status,
            "languageOfElement": "fr",
            "languageEncoding": "iso639-1",
            "scriptEncoding": "iso15924",
            "scriptOfElement": "Latn",
            "id": "control",
            "dateEncoding": "iso8601",  # AAAA-MM-JJTHH:MM:SS,ss-/+FF:ff
        }
        control_elt = self.element("control", parent=eac_elt, attributes=control_attributes)
        self.recordid_element(control_elt)
        self.maintenance_agency_element(control_elt)
        self.maintenance_history_element(control_elt)
        self.sources_element(control_elt)
        self.convention_declaration_elements(control_elt)
        self.language_declaration_element(control_elt)  # optional
        self.local_type_declaration_element(control_elt)
        self.representation_element(control_elt)
        self.rights_declaration_element(control_elt)

    @property
    def publication_status(self):
        """Depending on the entity state return one of following values:
        approved, published, inProcess"""
        return self.entity.publication_status

    @property
    def maintenance_status(self):
        """return one of following values : derived, new, revised"""
        return self.entity.maintenance_status

    def recordid_element(self, control_elt):
        self.element("recordId", parent=control_elt, text=self.entity.record_id)

    def maintenance_agency_element(self, control_elt):
        agency_elt = self.element("maintenanceAgency", parent=control_elt)
        self.element("agencyCode", parent=agency_elt, text=SIAF_CODE)
        self.element(
            "agencyName", parent=agency_elt, text="Service interministériel des Archives de France"
        )

    def language_declaration_element(self, control_elt):
        self.element(
            "languageDeclaration",
            parent=control_elt,
            attributes={"languageCode": "fre", "scriptCode": "Latn"},
        )

    def maintenance_history_element(self, control_elt):
        history = self.entity.maintenance_history
        if history:
            history_elt = self.element("maintenanceHistory", parent=control_elt)
            for event in history:
                self.maintenance_event_element(event, history_elt)

    def maintenance_event_element(self, event, history_elt):
        """<maintenanceEvent maintenanceEventType="revised">
          <agent agentType="unknown">1400</agent>
          <eventDateTime standardDateTime="2015-10-15"></eventDateTime>
        </maintenanceEvent>
        """
        event_elt = self.element(
            "maintenanceEvent",
            parent=history_elt,
            attributes={
                "maintenanceEventType": event["maintenanceEventType"]
            },  # created, derived, revised
        )
        self.element("agent", event_elt, attributes={"agentType": "human"}, text=event["agent"])
        event_date = event["eventDateTime"]
        if event_date:
            try:
                event_date = datetime.fromisoformat(event_date)
            except Exception as error:
                self.error(
                    f"[eac-cpf]: Agent {self.entity.record_id} -could not parse event_date:"
                    f" {event_date} : {error}"
                )
                return
            self.element(
                "eventDateTime",
                parent=event_elt,
                attributes={
                    "standardDateTime": ustrftime(event_date, fmt=self.standard_datetime_fmt)
                },
                text=ustrftime(event_date, fmt=self.fr_datetime_fmt),
            )

    def sources_element(self, control_elt):
        sources = self.entity.processed_sources
        if sources:
            sources_elt = self.element("sources", parent=control_elt)
            for source in sources:
                sources_elt.append(self.source_element(source["url"], source["label"]))

    def source_element(self, source_url, source_title):
        """<source>
         <reference href="https://de.wikipedia.org/wiki/Gustav_IV._Adolf_(Schweden)">
             Wikipedia</reference>
        </source>"""
        source_elt = self.element("source")
        self.element(
            "reference", parent=source_elt, attributes={"href": source_url}, text=source_title
        )
        return source_elt

    def convention_declaration_elements(self, control_elt):
        declaration_elt_1 = self.element("conventionDeclaration", parent=control_elt)
        self.element(
            "reference",
            parent=declaration_elt_1,
            attributes={"href": "https://eac.staatsbibliothek-berlin.de/schema/v2/eac.xsd"},
        )
        self.element(
            "p",
            parent=self.element(
                "descriptiveNote",
                parent=declaration_elt_1,
                attributes={"languageOfElement": "fre", "scriptOfElement": "Ltn"},
            ),
            text="Notice établie conformément à la norme ICA-ISAAR (CPF) 2004, aux normes ISO 8601 pour le système de normalisation des dates utilisé.",  # noqa
        )
        declaration_elt_2 = self.element("conventionDeclaration", parent=control_elt)
        self.element(
            "reference",
            parent=declaration_elt_2,
            attributes={"href": "https://code.rdafr.fr/"},
            text="Code RDA-FR/Agent",
        )

    def local_type_declaration_element(self, control_elt):
        vocabularies = []
        if not vocabularies:
            return
        local_type_elt = self.element("localTypeDeclaration", parent=control_elt)
        for vocabulary in vocabularies:  # TODO
            self.element(
                "reference",
                parent=local_type_elt,
                text=vocabulary,
            )

    def rights_declaration_element(self, control_elt):
        rights = self.element("rightsDeclaration", parent=control_elt)
        self.element(
            "reference",
            parent=rights,
            attributes={
                "href": "https://www.etalab.gouv.fr/wp-content/uploads/2017/04/ETALAB-Licence-Ouverte-v2.0.pdf"  # noqa
            },
            text="Licence etalab-2.0",
        )

    def representation_element(self, control_elt):
        self.element(
            "representation",
            parent=control_elt,
            attributes={"href": self.entity.absolute_url()},
            text=self.entity.dc_title(),
        )

    def cpfdescription_element(self, eac_elt):
        cpfdescription_elt = self.element("cpfDescription", parent=eac_elt)
        self.identity_element(cpfdescription_elt)
        self.description_element(cpfdescription_elt)
        self.alternatives_set_element(cpfdescription_elt)
        self.relations_element(cpfdescription_elt)

    def identity_element(self, cpfdescription_elt):
        identity_elt = self.element("identity", parent=cpfdescription_elt)
        self.element(
            "entityType", parent=identity_elt, attributes={"value": self.entity.entity_type}
        )
        self.names_elements(identity_elt)
        self.identityid_elements(identity_elt)

    def names_elements(self, identity_elt):
        other_names = self.entity.other_names_entries
        namset_elt = self.element("nameEntrySet", parent=identity_elt)
        self.element(
            "part",
            text=self.entity.data["nameEntry"],
            parent=self.element(
                "nameEntry",
                parent=namset_elt if other_names else identity_elt,
                attributes={
                    "languageOfElement": "fre",
                    "scriptOfElement": "Latn",
                    "preferredForm": "true",
                    "status": "authorized",
                },
            ),
        )
        for other_name in other_names:
            if not other_name.get("part"):
                continue
            lang = other_name.get("language")
            #  scriptOfElement="Latn"  ? preferredForm ? status ?
            attribs = (
                {"languageOfElement": lang, "preferredForm": "false", "status": "alternative"}
                if lang
                else {}
            )
            name_entry_elt = self.element("nameEntry", parent=namset_elt, attributes=attribs)
            self.element("part", parent=name_entry_elt, text=other_name["part"])
            self.dates_elements(other_name.get("useDates"), "useDates", name_entry_elt)

    def dates_elements(self, dates, eac_name, parent_elt):
        if dates:
            dates_elt = self.element(eac_name)
            if dates:
                self._eac_dates_xml_elt(dates, parent=dates_elt)
            if len(dates_elt):
                parent_elt.append(dates_elt)

    def identityid_elements(self, identity_elt):
        sources = self.entity.processed_identityids
        for source in sources:
            attributes = {"vocabularySource": source["vocab"]}
            url = source.get("url")
            if url:
                attributes["valueURI"] = url
            self.element(
                "identityId",
                parent=identity_elt,
                attributes=attributes,
                text=source["id"],
            )

    def description_element(self, cpfdescription_elt):
        description_elt = self.element("description")
        self.demographics_element(description_elt)
        self.occupations_element(description_elt)
        self.functions_element(description_elt)
        self.places_element(description_elt)
        self.exist_dates_element(description_elt)
        self.bioghist_element(description_elt)
        if len(description_elt):
            cpfdescription_elt.append(description_elt)

    def alternatives_set_element(self, cpfdescription_elt):
        sources = self.entity.processed_identityids
        if sources:
            set_elt = self.element("alternativeSet")
            for source in sources:
                attributes = {"href": source["url"]}
                if "id" in source:
                    attributes["id"] = source["id"]
                self.element(
                    "componentEntry",
                    parent=self.element(
                        "setComponent",
                        parent=set_elt,
                        attributes=attributes,
                    ),
                    text=source["label"],
                )

    def demographics_element(self, description_elt):
        if self.entity.gender:
            self.element(
                "term",
                parent=self.element(
                    "demographicDescription",
                    parent=self.element("demographicDescriptions", parent=description_elt),
                    attributes={"localType": "sexe"},
                ),
                text=self.entity.gender,
            )

    def occupations_element(self, description_elt):
        occupations_elt = self.element("occupations")
        for occupation in self.entity.processed_occupations:
            occupation_elt = self.element("occupation", parent=occupations_elt)
            self.element("term", parent=occupation_elt, text=occupation["term"]["label"])
            self._eac_dates_xml_elt(occupation.get("dates"), parent=occupation_elt)
            place = occupation.get("place")
            if place:
                self._eac_place_name_xml_elt(place, parent=occupation_elt)
            if len(occupations_elt):
                description_elt.append(occupations_elt)

    def functions_element(self, description_elt):
        for function in self.entity.processed_functions:
            functions_elt = self.element("functions")
            function_elt = self.element("function", parent=functions_elt)
            self.element("term", parent=function_elt, text=function["term"]["label"])
            self._eac_dates_xml_elt(function.get("dates"), parent=function_elt)
            place = function.get("place")
            if place:
                self._eac_place_name_xml_elt(place, parent=function_elt)
            if len(functions_elt):
                description_elt.append(functions_elt)

    def places_element(self, description_elt):
        places_elt = self.element("places")
        for eac_name, data in self.entity.processed_exist_places.items():
            role = self.places_vocabulary[eac_name]
            if eac_name == "activityPlaces":
                for _place in data:
                    self._eac_place_xml_elt(_place, role, parent=places_elt)
            else:
                self._eac_place_xml_elt(data, role, parent=places_elt)
        if len(places_elt):
            description_elt.append(places_elt)

    def exist_dates_element(self, description_elt):
        dates_elt = self._eac_dates_xml_elt(self.entity.exist_dates)
        if dates_elt is not None:
            self.element("existDates", parent=description_elt).append(dates_elt)

    def bioghist_element(self, description_elt):
        bioghist = self.entity.bioghist
        if bioghist:
            bioghist_elt = self.element("biogHist", parent=description_elt)
            bioghist_elt.extend(self._eac_bioghist_elements(bioghist))

    def relations_element(self, cpfdescription_elt):
        relations_elt = self.element("relations")
        for key, relations in self.entity.processed_relations.items():
            self.relation_element(relations_elt, relations)
        if len(relations_elt):
            cpfdescription_elt.append(relations_elt)

    def relation_element(self, relations_elt, relations):
        for relation in relations:
            target_entity = relation["targetEntity"]
            related_agent = target_entity.get("entity")
            if not related_agent:
                self.error(
                    f"[eac-cpf]: Agent {self.entity.record_id} - could not found "
                    f" the related agent {target_entity['label']}/{target_entity['value']}"
                )
                continue
            relation_elt = self.element("relation", parent=relations_elt)
            target_entity_elt = self.element(
                "targetEntity",
                attributes={
                    "targetType": target_entity["type"],
                    "vocabularySourceURI": target_entity["url"],
                },
                parent=relation_elt,
            )
            self.element("part", parent=target_entity_elt, text=related_agent.dc_title())
            dates = relation.get("dates")
            if dates:
                self._eac_dates_xml_elt(dates, parent=relation_elt)
            place = relation.get("place")
            if place:
                self._eac_place_xml_elt(place, parent=relation_elt)
            relation_type = relation.get("relationType")
            if relation_type:  # FIXME
                attributes = {}
                source = relation_type.get("source")
                if source:
                    attributes["vocabularySource"] = source
                self.element(
                    "relationType",
                    attributes=attributes,
                    parent=relation_elt,
                    text=relation_type["label"],
                )
            target_role = relation.get("targetRole")
            if target_role:
                attributes = {}
                source = target_role.get("source")
                if source:
                    attributes["vocabularySource"] = source
                self.element("targetRole", parent=relation_elt, text=target_role["label"])

    def _eac_place_xml_elt(self, place, role=None, parent=None):
        place_name_elt = self._eac_place_name_xml_elt(place)
        if place_name_elt is None:
            return
        place_elt = self.element("place", parent=parent)
        place_elt.append(place_name_elt)
        role = role or place.get("placeRole")
        if role:
            self.element("placeRole", parent=place_elt, text=role)
        if place.get("geographicCoordinates"):
            self.element(
                "geographicCoordinates",
                parent=place_elt,
                attributes={"coordinateSystem": "WGS84"},
                text=place["geographicCoordinates"],
            )
        address = place.get("address")
        if address:
            self.element(
                "addressLine", parent=self.element("address", parent=place_elt), text=address
            )
        self._eac_dates_xml_elt(place.get("dates"), place_elt)
        return place_elt

    def _eac_place_name_xml_elt(self, place, parent=None):
        attributes = {}
        authority_info = place.get("authority")
        if authority_info:
            attributes = {"vocabularySourceURI": authority_info["url"]}
            text = authority_info["entity"].label
        else:
            text = place["placeName"]
        if text:
            return self.element("placeName", parent=parent, attributes=attributes, text=text)

    def _eac_dates_xml_elt(self, dates, parent=None):
        if not dates:
            return
        from_date = self._clean_date(dates.get("fromDate"))
        to_date = self._clean_date(dates.get("toDate"))
        if not (from_date or to_date):
            return
        if not to_date and not from_date.get("date"):
            return
        if from_date == to_date:
            return self._eac_date_xml_elt(from_date, "date", parent=parent)
        else:
            return self._eac_date_range_xml_elt(to_date, from_date, parent=parent)

    def _eac_date_range_xml_elt(self, to_date, from_date, parent=None):
        """Return an EAC lxml ``'dateRange'`` ``Element`` with the given boundaries."""
        if not (from_date or to_date):
            return
        # FIXME (cf https://forge.extranet.logilab.fr/francearchives/cubicweb-francearchives/-/issues/851)  # noqa
        date_range_elt = self.element("dateRange", parent=parent)
        for dt, eac_name in [(from_date, "fromDate"), (to_date, "toDate")]:
            self._eac_date_xml_elt(dt, eac_name, date_range_elt)
        return date_range_elt

    def _eac_date_xml_elt(self, dt, eac_name, parent=None):
        """dt is a dict {"date": 1927, "certainty": "certain}"""
        _date = dt and dt.get("date")
        if _date:
            attributes = {}
            _date_iso = self._eac_year_to_isformat(_date)
            if _date_iso:
                attributes = {"standardDate": _date_iso}
            for attr in ("certainty", "status"):
                value = dt.get(attr)
                if value:
                    attributes[attr] = value
            return self.element(
                eac_name,
                parent=parent,
                attributes=attributes,
                text=str(_date),
            )
        elif dt and dt.get("status"):
            return self.element(
                eac_name,
                parent=parent,
                attributes={"status": dt.get("status")},
            )

    def _eac_year_to_isformat(self, year):
        try:
            date = datetime(int(year), 1, 1)
        except Exception:
            return
        if date:
            return ustrftime(date, fmt=self.standard_date_fmt)

    def _clean_date(self, date):
        if date:
            return {k: v for k, v in date.items() if v}

    def _eac_bioghist_elements(self, value):
        if not value:
            return []
        return list(transform_bioghist_with_lxml(f"<root>{value}</root>"))
