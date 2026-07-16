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

"""cubicweb-pnia-content persons's classes"""

from collections import OrderedDict
from datetime import datetime
import json

import logging
import re
from elasticsearch_dsl import Search, query as dsl_query

from logilab.common.decorators import cachedproperty
from logilab.common.textutils import unormalize
from logilab.mtconverter import xml_escape

from cubicweb import _
from cubicweb.entities import AnyEntity, fetch_config
from cubicweb.predicates import is_instance

from cubicweb_web import NotFound

from cubicweb_elasticsearch.entities import IFullTextIndexSerializable
from cubicweb_elasticsearch.es import get_connection

from cubicweb_francearchives.dataimport import get_year
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id

from cubicweb_francearchives.utils import format_date

UnknownNominaActCode = "###"

# these is not really a single unique list of nomina act codes: services can use
# differents codes. We try to normalize them for ES indexation
# and translations. All codes must be present in NominaActCodeTypes with upper cases


log = logging.getLogger("retrieve_nomina_es")

FORBIDDEN_CSV_EXPORT = [
    "FRAD010",
    "FRAD014",
    "FRAD029",
    "FRAD034",
    "FRAD035",
    "FRAD039",
    "FRAD059",
    "FRAD086",
]


def normalized_doctype_code(code):
    return unormalize(code).upper()


def nomina_translate_codetype(code):
    """use this function for translate document code"""
    if not code:
        code = UnknownNominaActCode
    # code = normalized_doctype_code(code)
    return NominaActCodeTypes.get(code, code)


def nomina_translate_gender_code(code):
    """use this function for translate document code"""
    return NominaGenderCodeTypes.get(code, code)


def format_date_location(cnx, hit, attr):
    location = format_event_location(hit, attr)
    return cnx._("; ").join([d for d in (hit.get(f"{attr}_date"), location) if d])


def format_event_location(hit, attr):
    commune = hit[f"{attr}_commune"] if f"{attr}_commune" in hit else None
    department = hit[f"{attr}_department"] if f"{attr}_department" in hit else None
    country = hit[f"{attr}_country"] if f"{attr}_country" in hit else None
    if not any((commune, department, country)):
        return ""
    context = ", ".join([e for e in (department, country) if e])
    if commune:
        if context:
            return f"{commune} ({context})"
        return commune
    if context:
        if department and country:
            return f"{department} ({country})"
        return department or country
    return ""


def build_nomina_faceted_search_kwargs(form_params, text_facets=None):
    """Build standardized kwargs for NominaFacetedSearch instantiation.

    :param dict form_params: search parameters from request form
    :param list text_facets: list of text facet names
        (default: ["es_forenames", "es_names", "es_locations"])
    :return: dict with keys for NominaFacetedSearch constructor
    """
    if text_facets is None:
        text_facets = ["es_forenames", "es_names", "es_locations"]

    kwargs = {
        "fulltext_facet": form_params.get("fulltext_facet"),
        "es_date_max": form_params.get("es_date_max"),
        "es_date_min": form_params.get("es_date_min"),
    }

    # Text facets
    for facet in text_facets:
        kwargs[facet] = form_params.get(facet)

    # Agent and household
    kwargs["agent"] = form_params.get("authority")
    kwargs["household"] = form_params.get("household")

    # Sort with default
    kwargs["script_sort"] = form_params.get("sort", "score")

    return kwargs


CIVIL_STATUS_DOCTYPE = (
    "B",
    "BN",
    "BANS",
    "D",
    "N",
    "NA",
    "M",
    "MA",
    "TD",
    "TN",
    "TM",
    "S",
    "SD",
)

MARIAGE_DOCTYPE = ("M", "MA", "TM")

MPF_DOCTYPE = ("MPF14-18", "MORT 14-18", "MPF")

RM_DOCTYPE = ("RM", "MPF14-18", "MORT 14-18", "MPF")

GENDER_MAPPING = {
    "h": "homme",
    "f": "femme",
    "i": "non renseigné",
    "": "non renseigné",
}


def formatted_same_household(cnx, hit, index_name):
    data = []
    household_id = hit.get("household_id")
    if household_id:
        search = Search(index=index_name)
        must = [{"match": {"household_id": household_id}}]
        same_document = [{"match": {"stable_id": hit["stable_id"]}}]
        search.query = dsl_query.Bool(must=must, must_not=same_document)
        search = search.source(["stable_id", "title", "household_id", "household_role"])
        try:
            response = search.execute()
        except Exception as err:
            cnx.error("[es] no es connection found: %s. abort.", err)
            return
        for hit in response:
            url = cnx.build_url(f"basedenoms/{hit['stable_id']}")
            role = f", {hit['household_role']}" if "household_role" in hit else ""
            data.append(f'<a href="{url}">{hit["title"]}</a>{role}')
    if data:
        return f"<ul>{''.join([f'<li>{link}</li>' for link in data])}</ul>"


def fetch_service(cnx, service_eid):
    if service_eid:
        rset = cnx.execute(
            """Any X, C, N, N2, SN, L WHERE X is Service,
            X code C, X name N, X name2 N2, X short_name SN,
            X level L, X eid %(eid)s""",
            {"eid": service_eid},
        )
        if rset:
            return rset.one()


def hit_to_entity_json(cnx, hit, csv_export=False):
    nomina_index_name = cnx.vreg.config["nomina-index-name"]
    code = normalized_doctype_code(hit["act_type"])
    # For census records (RP), occupations is source, occupations_index is indexed version
    if code == "RP":
        occupations_raw = hit.get("occupations")  # Source
        occupations_index = hit.get("occupations_index")  # Indexed
    else:
        occupations_raw = hit.get("occupations")
        occupations_index = None
    instruction = NominaEducationCodes.get(hit["instruction"]) if "instruction" in hit else None
    mention = hit.get("mention_mpf")
    absolute_url = cnx.build_url(f"basedenoms/{hit['stable_id']}")
    act_number_label = "NMN_C_nro" if code in RM_DOCTYPE else "Deed number"
    service = fetch_service(cnx, hit["service"])
    gender = GENDER_MAPPING.get(hit["gender"], "")
    hit["absolute_url"] = absolute_url
    data = {"entity": hit, "service": service}
    if not (code in RM_DOCTYPE and service.code in FORBIDDEN_CSV_EXPORT):
        data["csv_export"] = [
            (cnx._("FranceArchives link"), absolute_url),
            (cnx._("Name"), ", ".join(hit["names"]) or ""),
            (cnx._("Forenames"), ", ".join(hit["forenames"]) or ""),
            (cnx._("Event date"), hit["event_date"] or ""),
            (cnx._("Event location"), format_event_location(hit, "event")),
            (
                cnx._("NMN_C_occupations"),
                ", ".join(occupations_index) if occupations_index else "",
            ),
            (cnx._("Gender"), gender),
            (cnx._("Doctype_label"), nomina_translate_codetype(code)),
            (cnx._("Cote"), hit["cote"] or ""),
            (cnx._(act_number_label), hit.get("notice_id", "") or ""),
            (cnx._("Partner service name"), service.dc_title() if service else ""),
            (cnx._("thumbnail_dest"), hit["source_url"] or ""),
        ]
    if csv_export:
        return data
    match code:
        case _ if code in RM_DOCTYPE:
            data["main_props"] = OrderedDict(
                [
                    (cnx._("Birth"), format_date_location(cnx, hit, "birth")),
                    (
                        cnx._("NMN_C_occupations"),
                        ", ".join(occupations_raw) if occupations_raw else "",
                    ),
                    (
                        cnx._("NMN_C_education"),
                        cnx._(instruction) if instruction else None,
                    ),
                    (
                        cnx._("Enrolment year and place"),  # RM
                        format_date_location(cnx, hit, "recruitment"),
                    ),
                    (
                        cnx._("Death"),
                        format_date_location(cnx, hit, "death"),
                    ),
                    (cnx._("Gender"), gender),
                    (cnx._("NMN_R"), format_event_location(hit, "residence")),
                    (cnx._("Doctype_label"), nomina_translate_codetype(code)),
                    (cnx._("NMN_C_cote"), hit["cote"]),
                    (cnx._("NMN_C_nro"), hit["act_number"]),
                    (cnx._("Additional information"), hit["additional_info"]),
                    (cnx._("NMN_mention_mpf"), mention),
                    (cnx._("Historical context"), hit.get("historical_context")),
                ]
            )
            return data
        case _ if code in CIVIL_STATUS_DOCTYPE:
            household_id = hit.get("household_id")
            same_household = None
            if code in MARIAGE_DOCTYPE and household_id:
                same_household = formatted_same_household(cnx, hit, nomina_index_name)
            data["main_props"] = OrderedDict(
                [
                    (cnx._("Birth"), format_date_location(cnx, hit, "birth")),
                    (
                        cnx._("NMN_C_occupations"),
                        ", ".join(occupations_raw) if occupations_raw else "",
                    ),
                    (
                        cnx._("NMN_C_education"),
                        cnx._(instruction) if instruction else "",
                    ),
                    (cnx._("Death"), format_date_location(cnx, hit, "death")),
                    (cnx._("Gender"), gender),
                    (cnx._("Doctype_label"), nomina_translate_codetype(code)),
                    (
                        cnx._("Date and place of the event"),
                        format_date_location(cnx, hit, "event"),
                    ),
                    (cnx._("Deed date"), hit["act_date"]),
                    (cnx._("NMN_C_cote"), hit["cote"]),
                    (cnx._("Deed number"), hit["act_number"]),
                    (cnx._("Additional information"), hit["additional_info"]),
                    (cnx._("NMN_mention_mpf"), mention),
                    (cnx._("See other members of the household"), same_household),
                ]
            )
            return data
        case _ if code == "RP":
            same_household = None
            if hit.get("id_arkindex"):  # socface
                data["warning"] = cnx._("socface_warning {link}").format(
                    link=cnx.build_url("article/1118237662")
                )
                birth = cnx._("; ").join([d for d in (hit["birth_date"], hit["birth_place"]) if d])
                household_id = hit.get("household_id")
                if household_id and household_id != "_":
                    same_household = formatted_same_household(cnx, hit, nomina_index_name)
                    data["household_link"] = cnx.build_url(
                        f"basedenoms?household={hit['household_id']}"
                    )
            else:
                birth = format_date_location(cnx, hit, "birth")
            data["main_props"] = OrderedDict(
                [
                    (cnx._("Birth"), birth),
                    (cnx._("Age"), hit["age"]),
                    (cnx._("Gender"), gender),
                    (cnx._("Civil status"), hit["civil_status"]),
                    (
                        cnx._("Relationship to the head of household"),
                        hit["household_role"],
                    ),
                    (
                        cnx._("Ooccupation (source)"),
                        ", ".join(occupations_raw) if occupations_raw else "",
                    ),
                    (
                        cnx._("Ooccupation (index)"),
                        ", ".join(occupations_index if occupations_index else ""),
                    ),
                    (cnx._("Employer"), hit["employer"]),
                    (
                        cnx._("Date and place of the census"),
                        format_date_location(cnx, hit, "event"),
                    ),
                    (cnx._("Doctype_label"), nomina_translate_codetype(code)),
                    (cnx._("Nationality"), hit["nationality"]),
                    (cnx._("Comments_nomina_RP"), hit["additional_info"]),
                    (cnx._("NMN_C_cote"), hit["cote"]),
                    (
                        cnx._("Page and position of the line on the page"),
                        hit.get("doc_page_line_id"),  # socface
                    ),
                    (cnx._("See other members of the household"), same_household),
                ]
            )
            return data
        case _:
            data["main_props"] = OrderedDict(
                [
                    (cnx._("Birth"), format_date_location(cnx, hit, "birth")),
                    (
                        cnx._("NMN_C_occupations"),
                        ", ".join(occupations_raw) if occupations_raw else "",
                    ),
                    (
                        cnx._("NMN_C_education"),
                        cnx._(instruction) if instruction else None,
                    ),
                    (cnx._("Death"), format_date_location(cnx, hit, "death")),
                    (cnx._("Doctype_label"), nomina_translate_codetype(code)),
                    (
                        cnx._("Date and place of the event"),
                        format_date_location(cnx, hit, "event"),
                    ),
                    (cnx._("Deed date"), hit["act_date"]),
                    (cnx._("NMN_C_cote"), hit["cote"]),
                    (cnx._("Deed number"), hit["act_number"]),
                    (cnx._("Additional information"), hit["additional_info"]),
                    (cnx._("NMN_mention_mpf"), mention),
                    (cnx._("Historical context"), hit.get("historical_context")),
                ]
            )

            return data


def nominarecord_from_esdoc(cnx, stable_id, hit, csv_export=False):
    entity = cnx.vreg["etypes"].etype_class("NominaRecord")(cnx)
    entity.cw_attr_cache.update(
        {
            "stable_id": stable_id,
            "json_data": hit_to_entity_json(cnx, hit["_source"], csv_export=csv_export),
        }
    )
    return entity


def initialize_nominarecord_entity(cnx, stable_id, csv_export=False):
    """initialize a NominaRecord record entity from a stable_id"""
    es = get_connection(cnx.vreg.config)
    if not es or not es.ping:
        cnx._cw.error("-> no es connection found: abort.")
        return {}
    index_name = cnx.vreg.config["nomina-index-name"]
    query = {"query": {"match": {"stable_id": stable_id}}}
    response = es.search(index=index_name, body=query)
    number_responses = response["hits"]["total"]["value"]
    if number_responses == 1:
        return nominarecord_from_esdoc(
            cnx, stable_id, response["hits"]["hits"][0], csv_export=csv_export
        )
    cnx.error(f'Found {number_responses} NominaRecord(s) with stable_id "{stable_id}".')
    if number_responses == 0:
        raise NotFound(
            cnx._("NominaRecord with stable_id {stable_id} not found in index {index_name}").format(
                stable_id=stable_id, index_name=index_name
            )
        )
    else:
        raise NotFound(
            cnx._(
                "Found {number_response} NominaRecords with stable_id {stable_id} in index {index_name}"  # noqa
            ).format(stable_id=stable_id, index_name=index_name)
        )


NominaActCodeTypes = OrderedDict(
    {
        "A": "Abjuration",
        "AN": "Acte notarié",
        "B": "Baptême ou naissance",
        "N": "Baptême ou naissance",
        "TN": "Baptême ou naissance",
        "BN": "Baptême ou naissance",
        "NA": "Baptême ou naissance",
        "BANS": "Bans de mariage",
        "CM": "Contrat de mariage",
        "CO": "Congé",
        "DI": "Divorce",
        "F": "Fiançailles",
        "JU": "Jugement",
        "M": "Mariage",
        "MA": "Mariage",
        "TM": "Mariage",
        "MPF": "Mort pour la France",
        "MPF14-18": "Mort pour la France 14-18",
        "MORT 14-18": "Mort 14-18",
        "P": "Permission",
        "PER": "Permission",
        "PR": "Promesse de mariage",
        "PU": "Publication de mariage",
        "R": "Résidence",
        "RE": "Reconnaissance",
        "REA": "Réhabilitation",
        "RM": "Matricule militaire",
        "RP": "Recensement de la population",
        "RT": "Rôle de taille",
        "S": "Sépulture ou décès",
        "D": "Sépulture ou décès",
        "TD": "Sépulture ou décès",
        "SD": "Sépulture ou décès",
        "SV": "Sans vie",
        "T": "Rôle de taille",
        "ZZ": "Autre type",
        "PM": "Autre type",
        # "JU": "Autre type",
        "RC": "Autre type",
        UnknownNominaActCode: "Inconnu",
    }
)

NominaGenderCodeTypes = {
    "h": "homme",
    "f": "femme",
    "i": "non renseigné",
    "": "non renseigné",
}

# Some code refer to the same event and must be merge in ES indexation
# All codes must be present un upper cases in NominaESActCodeTypes

NominaESActCodeTypes = {
    "B": "BN",
    "N": "BN",
    "TN": "BN",
    "NA": "BN",
    "MA": "M",
    "TM": "M",
    "PER": "P",
    "D": "S",
    "TD": "S",
    "SD": "S",
    "T": "RT",
    "ZZ": "AU",
    "PM": "AU",
    "RC": "AU",
}


NominaComplementCodes = OrderedDict(
    {
        "f": _("NMN_C_conflit"),
        "c": _("NMN_C_cote"),
        "e": _("NMN_C_education"),
        "n": _("NMN_C_nro"),
        "m": _("NMN_C_mention"),
        "o": _("NMN_C_occupations"),
        "a": _("NMN_C_autre"),
        "d": _("NMN_C_digitized"),
        "p": _("NMN_C_payant"),
    }
)


NominaEducationCodes = OrderedDict(
    {
        "0": "Ne sait ni lire ni écrire",
        "1": "Sait lire",
        "2": "Sait lire et écrire",
        "3": "Sait lire, écrire et compter",
        "4": "Brevet de l'enseignement primaire",
        "5": "Bachelier",
    }
)


def date_from_str(string):
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(string, fmt)
        except Exception:
            pass


def format_str_date(req, string):
    _date = date_from_str(string)
    if _date:
        return format_date(_date, req)
    return string


def year_from_date(date):
    """
    :param list dict: dictionnaire {"y": year, "d", date}
    """
    if not date:
        return None
    year = date.get("y")
    if year:
        return year
    date = date.get("d")
    if date:
        date = date_from_str(date)
        if date:
            return str(date.year)


class NominaImportAttributesMixIn:
    def dc_title(self):
        """Generic dc_title"""
        return self._cw._("; ").join(self.persons_data) or self._cw._("Unknown")

    @cachedproperty
    def doctype_code(self):
        """
        doctype code should be mandatory
        """
        return self.data.get("t", UnknownNominaActCode)

    @cachedproperty
    def doctype_type(self):
        return nomina_translate_codetype(self.doctype_code)

    @cachedproperty
    def civil_status_doctype(self):
        return normalized_doctype_code(self.doctype_code) in CIVIL_STATUS_DOCTYPE

    @cachedproperty
    def mariage_doctype(self):
        return normalized_doctype_code(self.doctype_code) in MARIAGE_DOCTYPE

    @cachedproperty
    def mpf_doctype(self):
        return normalized_doctype_code(self.doctype_code) in MPF_DOCTYPE

    @cachedproperty
    def rm_doctype(self):
        return normalized_doctype_code(self.doctype_code) in RM_DOCTYPE

    @cachedproperty
    def events(self):
        return self.data.get("e", {})

    def get_events(self, code):
        return self.events.get(code)

    def get_events_types(self, skip=()):
        keys = self.events.keys()
        if not skip:
            return keys
        return set(keys) - set(skip)

    def format_dates(self, dates):
        if not dates:
            return ""
        formatted = []
        sep = self._cw._("; ")
        for _dates in dates:
            complete_date = _dates.get("d")
            if complete_date:
                formatted.append(format_str_date(self._cw, complete_date))
            elif "y" in _dates:
                values = _dates["y"]
                formatted.append(values)
        return sep.join(formatted)

    def get_uncorrelated_dates(self, events):
        """dates issues from nomina oai are not correlated with their locations and are
        list or dictionary in a dictionary
        ex.
        {'d': [{'y': '1851'}], 'l': [{'d': 'Ardennes', 'p': 'Gespunsart'}]}
        :param list events: list of events
        :param boolean year: True
        """
        dates = events.get("d", [])
        if isinstance(dates, dict):
            return [dates]
        return dates

    def get_correlated_dates(self, events):
        """dates issues from csv are be correlated with their locations and are
        dictionary in a list
        ex. [{'d': {'y': '1867'},
              'l': {'p': 'Labrit', 'dc': '40', 'd': 'Landes', 'cc': 'FR', 'c': 'France'}}]

        :param list events: list of events
        return array
        """
        assert isinstance(events, (list, tuple))
        data = []
        for event in events:
            data.extend(self.get_uncorrelated_dates(event))
        return data

    def get_dates(self, code, fmt=True):
        """return "d" for a date, "y" for the exact year
        :param string code: code if the event
        :param boolean fmt: True for string result else array
        """
        dates = []
        events = self.get_events(code)
        if events is None:
            return "" if fmt else dates
        if isinstance(events, dict):
            # events come from nomina oai
            dates = self.get_uncorrelated_dates(events)
        else:
            dates = self.get_correlated_dates(events)
        if fmt:
            return self.format_dates(dates)
        return dates

    def get_uncorrelated_locations(self, events):
        """location issues from nomina oai are not correlated with their dates and are
        list or dictionary in a dictionary
        ex.
        {'d': [{'y': '1851'}], 'l': [{'d': 'Ardennes', 'p': 'Gespunsart'}]}
        :param list events: list of events
        """
        locations = events.get("l", [])
        if isinstance(locations, dict):
            locations = [locations]
        return locations

    def get_correlated_locations(self, events):
        """location issues from csv are correlated with their dates and are a
        dictionary in a list
        ex. [{'d': {'y': '1867'},
              'l': {'p': 'Labrit', 'c': '40', 'd': 'Landes', 'cc': 'FR', 'c': 'France'}}]
        :param list events: list of events
        """
        assert isinstance(events, (list, tuple))
        data = []
        for event in events:
            data.extend(self.get_uncorrelated_locations(event))
        return data

    @cachedproperty
    def info_data(self):
        return self.data.get("c", {})

    def get_infos_data(self, skip="o"):
        data = []
        infos = self.data.get("c")
        if infos:
            for key, values in infos.items():
                if key in skip:
                    continue
                label = self._cw._(NominaComplementCodes[key])
                if key == "e":  # niveau
                    values = NominaEducationCodes.get(values)
                    if values:
                        values = self._cw._(values)
                data.append((label, values))
        return data

    @cachedproperty
    def notice_id(self):
        """only exists for csv imported data"""
        return self.data.get("i") or None

    @cachedproperty
    def persons_data(self):
        return [
            f"{person.get('n', '?') or '?'}, {person.get('f', '?') or '?'}"
            for person in self.data.get("p", [])
        ]

    @cachedproperty
    def processed_acte_type_code(self):
        """normalize doctype code for es indexation"""
        code = normalized_doctype_code(self.doctype_code)
        return NominaESActCodeTypes.get(code, code)

    @cachedproperty
    def source_url(self):
        return self.data.get("u", None)


class NominaRecord(NominaImportAttributesMixIn, AnyEntity):
    __regid__ = "NominaRecord"
    fetch_attrs, cw_fetch_order = fetch_config(["stable_id", "json_data"], pclass=None)
    lang = "fr"

    def dc_title(self):
        if self.is_pg_entity:
            return super().dc_title()
        return self.data["entity"]["title"]

    @cachedproperty
    def is_pg_entity(self):
        """
        Test that the current entity is a PostgreSQL-backed entity.
        ORM entities are used only for data migration and will be removed afterward.
        """
        return "entity" not in self.data

    def rest_path(self, use_ext_eid=False):
        return f"basedenoms/{self.stable_id}"

    @cachedproperty
    def data(self):
        data = self.json_data
        if isinstance(data, str):
            # sqlite return unicode instead of dict : XXX for ES
            return json.loads(data)
        return data

    @cachedproperty
    def processed_acte_type_code(self):
        if "entity" not in self.data:
            return super().processed_acte_type_code
        return self.data["entity"]["act_type"]

    def agent_indexes(self):
        if self.is_pg_entity:
            return self._cw.execute(
                """
                DISTINCT Any A, L ORDERBY L WHERE P eid %(e)s,
                P same_as A, A is AgentAuthority, A label L""",
                {"e": self.eid},
            )

        return self._cw.execute(
            """
            DISTINCT Any A, L WHERE A same_as X, A is AgentAuthority, A label L,
            X is ExternalUri, X extid %(e)s
            """,
            {"e": self.stable_id},
        )

    @property
    def label(self):
        """property to ease compatibility with AgentName entities"""
        raise
        return self.dc_title()

    def related_agents(self):
        return [e.view("nomina_agent") for e in self.agent_indexes().entities()]

    @cachedproperty
    def related_service(self):
        if self.is_pg_entity:
            return self.service[0]
        if "service" in self.data:
            return self.data["service"]
        return fetch_service(self._cw, self.data["entity"]["service"])

    @cachedproperty
    def act_year(self):
        code = "D" if self.mpf_doctype else self.doctype_code
        date = self.get_dates(code, fmt=False)
        if not date:
            date = self.get_dates("acte", fmt=False)
        if isinstance(date, list):
            years = list(filter(None, [year_from_date(d) for d in date]))
            return years[0] if years else ""
        return year_from_date(date)


def xml_escape_props_values(props):
    for label, value in props.items():
        if value:
            if isinstance(value, (tuple, list)):
                value = [xml_escape(v) for v in value]
            else:
                value = xml_escape(value)
        props[label] = value
    return props


def normalized_occupation(occupation):
    return occupation.lower() if occupation else ""


class NominaIndexJsonDataSerializable(NominaImportAttributesMixIn):
    def __init__(self, cnx, json_data):
        self._cw = cnx
        self.data = json_data

    def dates_to_es(self, date):
        # dates can be intervals #74118518
        if date is None:
            return
        start, stop = None, None
        year = re.sub(r"[^0-9/\-]", "", date)
        if year:
            for sep in "-/":
                if sep in year:
                    try:
                        start, stop = [d.strip() for d in year.split(sep)]
                    except ValueError:
                        pass
        if not stop and not start:
            start = year.strip() if year else year
            stop = start

        # try transforming the dates to 4 digit integers
        startyear = get_year(start)
        stopyear = get_year(stop)

        if startyear and stopyear:  # the transformation succeeded (no non-digit characters)
            return {"gte": startyear, "lte": stopyear}
        return  # Do not return anything if the dates could not be properly parsed

    def process_all_text(self, data):
        """compute all text from json_data
        other data are copied to all_text in es mapping
        """

        old_lang = self._cw.lang
        # ensure the language (we only index in french)
        self._cw.set_language("fr")
        _ = self._cw._
        content = []
        for label, value in self.get_infos_data(skip=["e", "n", "o"]):
            # skip:
            # - instruction (add the translation later),
            # - nro
            # - occupation (added in index mappings)
            if type(value) in (list, tuple):
                value = ", ".join(value)
            if value:
                content.append(value)
        if data.get("instruction"):
            content.append(NominaEducationCodes.get(data["instruction"], ""))
        content.extend(
            (
                GENDER_MAPPING.get(data.get("gender", "")),
                nomina_translate_codetype(data["act_type"]),
            )
        )
        all_locations = []
        # avoid to add  several times the same value in alltext
        # try to preserve the order for tests
        for key, value in data.items():
            for postfix in ("_country", "_department", "_commune"):
                if key.endswith(postfix) and value and value not in all_locations:
                    # strip () (?)
                    all_locations.append(value)
        content.extend(list(all_locations))
        self._cw.set_language(old_lang)
        return " ".join(content)

    def process_act_dates(self):
        dates = self.get_dates("acte", fmt=False)
        if dates:
            return self.format_dates(dates)

    def process_act_event_data(self):
        code = "D" if self.mpf_doctype else self.doctype_code
        data = self.process_event_data(code, with_act=True)
        return {f"event_{key}": value for key, value in data.items()}

    def process_birth_data(self):
        data = self.process_event_data("N")
        return {f"birth_{key}": value for key, value in data.items()}

    def process_death_data(self):
        data = self.process_event_data("D")
        return {f"death_{key}": value for key, value in data.items()}

    def process_recruitment_data(self):
        data = self.process_event_data("RM")
        return {f"recruitment_{key}": value for key, value in data.items()}

    def process_event_location(self, code):
        # indexed_data = { "commune": None, "department":None, "country: None}
        indexed_data = {}
        events = self.get_events(code)
        if not events:
            return indexed_data
        locations = []
        if isinstance(events, dict):
            # events comes from nomina oai
            locations = self.get_uncorrelated_locations(events)
        else:
            locations = self.get_correlated_locations(events)
        # Only take the first location
        if not locations:
            return indexed_data
        location = locations[0]
        if isinstance(location, (tuple, list)):
            location = location[0]
        indexed_data.update(
            {
                "commune": location.get("p"),
                "department": location.get("d"),
                "country": location.get("c"),
            }
        )
        return indexed_data

    def process_residence_data(self):
        data = self.process_event_location("R")
        return {f"residence_{key}": value for key, value in data.items()}

    def process_event_data(self, code, with_act=False):
        data = {"dates": None, "date": None}  # date could be a real date
        event = self.get_events(code)
        if with_act:
            data["year"] = None
            if not event:
                event = self.get_events("act")
        if event:
            dates = self.get_dates(code, fmt=False)
            if dates:
                es_dates = self.dates_to_es(year_from_date(dates[0]))
                data.update(
                    {
                        "date": self.format_dates(dates),
                        "dates": es_dates,
                    }
                )
                if with_act and es_dates:
                    data["year"] = es_dates.get("gte")
            data.update(self.process_event_location(code))
        return data

    def process_persons_data(self):
        if self.processed_acte_type_code in MARIAGE_DOCTYPE:
            return self.process_spouses()
        return self.process_persons()

    def process_persons(self):
        data = {"names": [], "forenames": []}
        for p in self.data.get("p", []):
            names = p.get("n")
            if names:
                data["names"].append(names)
            forenames = p.get("f")
            if forenames:
                data["forenames"].append(forenames)
        return data

    def process_spouses(self):
        """Extract spouse data from marriage act as a flat list.

        Supports multiple spouses of the same gender (e.g., polygamous marriages).
        Returns a flat list where each spouse is a separate entry with its index.

        :return: List of person data dictionaries with gender and index
        :rtype: list[dict]

        Example::

            [
                {"names": ["DUPONT"], "forenames": ["Marie"], "gender": "f", "idx": 0,
                          "title": "DUPONT, Marie"},
                {"names": ["DURAND"], "forenames": ["Pierre"], "gender": "m", "idx": 1,
                           "title", "DURAND, Pierre"}
            ]
        """
        persons = self.data.get("p", [])
        if not persons:
            return []

        data = []
        indexes = {}
        for idx, p in enumerate(persons):
            genre = p.get("g", "i")
            person_data = {
                "gender": genre,
                "idx": idx,
                "names": ["?"],
                "forenames": ["?"],
            }
            if names := p.get("n"):
                person_data["names"] = [names]
            if forenames := p.get("f"):
                person_data["forenames"] = [forenames]
            person_data["title"] = (
                f"""{' '.join(person_data["names"])}, {' '.join(person_data["forenames"])}"""
            )
            indexes[genre] = idx
            data.append(person_data)
        return data

    def process_json_data(self, service_code, stable_id, alltext=None):
        """Process NominaRecord data for Elasticsearch indexing.

        Extracts and structures data from a NominaRecord entity including:
        - Act information (date, number, type, event)
        - Person information (names, forenames, birth, death, residence)
        - Historical context and occupations
        - Metadata (creation/modification dates, source URL, cote)

        For marriage acts (MARIAGE_DOCTYPE), includes spouse data grouped by gender.
        For other acts, includes person data.

        :param str service_code: Sevice code
        :param str stable_id: Notice stable_id
        :param str alltext: Additional text to index (used for authorities labels in import)
        :return: List containing indexed data documents
        :rtype: list[dict]
        """
        act = self.processed_acte_type_code
        occupations = self.info_data.get("o")
        occupations = (
            occupations
            if isinstance(occupations, (list, tuple))
            else [occupations] if occupations else None
        )
        data = {
            "act_date": self.process_act_dates(),
            "act_number": self.info_data.get("n"),
            "act_type": act,
            "additional_info": self.info_data.get("a"),
            "cote": self.info_data.get("c"),
            "instruction": self.info_data.get("e"),
            "historical_context": self.info_data.get("f"),  # conflit (c.f. #905#note_186285)
            "gender": "h" if normalized_doctype_code(self.doctype_code) in ("RM",) else "i",
            "notice_id": self.notice_id,  #
            "oai_id": self.data.get("oai_id"),
            "occupations": occupations,
            "occupations_index": (
                [normalized_occupation(o) for o in occupations] if occupations else None
            ),
            "mention_mpf": self.info_data.get("m"),
            "source_url": self.source_url,
            "stable_id": stable_id,
            "title": self.dc_title(),
        }
        for process_method in (
            self.process_act_event_data,
            self.process_birth_data,
            self.process_death_data,
            self.process_recruitment_data,
            self.process_residence_data,
        ):
            data.update(process_method())
        # Build alltext field for full-text search
        text = self.process_all_text(data)
        data["alltext"] = f"{text} {alltext}" if alltext else text
        # Marriage acts: split by spouse gender, otherwise add person data
        if act in MARIAGE_DOCTYPE:
            return self.process_json_data_spouses(service_code, data)
        data.update(self.process_persons_data())
        return [data]

    def generate_spouse_stable_id(self, service_code: str, notice_id: str, index: int) -> str:
        """Generate a deterministic stable_id based on document position.

        The index corresponds to the position in the source document,
        ensuring stability across imports.

        :param str service_code: Service code
        :param str notice: Notice notice_id
        :param int index: Notice position
        :rtype: str

        """
        return compute_nomina_stable_id(service_code, f"{notice_id}_{index}")

    def process_json_data_spouses(self, service_code: str, json_data: dict) -> list[dict]:
        """Generate separate JSON documents for each spouse.

        :param str service_code: Service code
        :param dict json_data: Base JSON data to duplicate for each spouse
        :return: List of JSON documents, one per spouse
        :rtype: list[dict]
        """
        stable_id = json_data.pop("stable_id")
        notice_id = json_data["notice_id"]
        spouses_data = []
        for person in self.process_persons_data():
            idx = person.pop("idx")
            spouse_stable_id = (
                self.generate_spouse_stable_id(service_code, notice_id, idx) if idx else stable_id
            )
            spouses_data.append(
                {
                    **json_data,
                    **person,
                    "stable_id": spouse_stable_id,
                    "household_id": f"m_{stable_id}",
                    # "household_role": "conjoint",
                }
            )
        return spouses_data


class INominaIndexSerializable(IFullTextIndexSerializable):
    """Adapter to serialize Nomina data. It is only used in tests."""

    __regid__ = "INominaIndexSerializable"
    __select__ = is_instance("NominaRecord")
    skip_indexable_attributes = ("cwuri",)

    @property
    def es_id(self):
        return self.entity.stable_id

    def serialize(self, complete=True):
        # In case of mariage there is possible to have more than 1
        # person per original notice
        entity = self.entity
        if complete:
            entity.complete()
        service = entity.related_service
        agents = entity.agent_indexes()
        data = {
            "service": service.eid,
            "agent": [e[0] for e in agents],
        }
        data.update(self.process_attributes())
        adapter = NominaIndexJsonDataSerializable(self.entity._cw, self.entity.json_data)
        result = []
        for idx, notice in enumerate(adapter.process_json_data(service.code, entity.stable_id)):
            if not idx and agents:
                data["alltext"] += " " + " ".join(e[1] for e in agents)
            result.append({**data, **notice})
        return result
