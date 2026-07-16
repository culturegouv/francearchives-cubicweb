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
# professionals having in-depth comezputer knowledge. Users are therefore
# encouraged to load and test the software's suitability as regards their
# requirements in conditions enabling the security of their systemsand/or
# data to be ensured and, more generally, to use and operate it in the
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have hadredis
# knowledge of the CeCILL-C license and that you accept its terms.
#

"""cubicweb-pnia-content adapter's classes"""

import vobject

from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.entity import EntityAdapter
from cubicweb.predicates import is_instance, relation_possible
from cubicweb.entities.adapters import ITreeAdapter

from cubicweb_francearchives import FIRST_LEVEL_SECTIONS, SECTIONS

from cubicweb_francearchives.entities.rdf import RDF_FORMAT_EXTENSIONS
from cubicweb_francearchives.redis_utils import RedisConnector
from cubicweb_francearchives.schema.cms import CMS_OBJECTS
from cubicweb_francearchives.utils import format_date
from cubicweb_francearchives.views import exturl_link


class ITemplatableApdater(EntityAdapter):
    __select__ = is_instance("Any")
    __regid__ = "ITemplatable"

    def entity_param(self):
        return self.entity

    def main_props(self):
        return []


class TranslatableMixIn(object):
    def cache_entity_translations(self):
        """update entity cache with translated value for translatable attributes"""
        if self._cw.lang == "fr":
            return self.entity
        if hasattr(self, "_cached_translation") and self._cached_translation == self._cw.lang:
            return self.entity
        self._cached_translation = {}
        translations = self.entity.translations_in_lang()
        if translations:
            for attr, value in translations.items():
                self.entity.cw_attr_cache[attr] = value
                self.entity.cw_attr_cache["lang"] = self._cw.lang
        self._cached_translation = self._cw.lang
        return self.entity


class ITranslatableAdapter(TranslatableMixIn, EntityAdapter):
    __regid__ = "ITranslatable"
    __select__ = relation_possible("translation_of", role="object")


class ITemplatableTranslatableApdater(TranslatableMixIn, ITemplatableApdater):
    __select__ = ITemplatableApdater.__select__ & relation_possible("translation_of", role="object")

    def entity_param(self):
        return self.cache_entity_translations()


class CommemoITemplatable(ITemplatableTranslatableApdater):
    __select__ = ITemplatableTranslatableApdater.__select__ & is_instance("CommemorationItem")

    def entity_param(self):
        return self.cache_entity_translations()


class IndexITemplatable(ITemplatableApdater):
    __select__ = ITemplatableApdater.__select__ & is_instance("AgentName", "Geogname", "Subject")

    def documents(self, limit=200):
        _ = self._cw._
        index_nb = self._cw.execute(
            "Any COUNT(I) WHERE X eid %(eid)s, X index I", {"eid": self.entity.eid}
        )[0][0]
        label = f"{_('FindingAid_plural')} {_('or')} {_('FAComponent_plural')}"
        if index_nb == 1:
            label = f"{_(self.entity.index[0].cw_etype)}"
        label = _("This index is linked to %s.") % f"{index_nb} {label}"
        data = {}
        if index_nb > limit:
            warning = _("Only display %s links.") % limit
            label = f"{label} {warning}"
        data["label"] = label
        query = f"""
            Any F, N, I ORDERBY N, I LIMIT {limit} WHERE X eid %(eid)s, X index F,
            F did D?, D unittitle N, D unitid I"""
        rset = self._cw.execute(query, {"eid": self.entity.eid})
        data["docs"] = [e.view("incontext") for e in rset.entities()]
        return data

    def main_props(self):
        _ = self._cw._
        entity = self.entity
        properties = [
            (_("type"), entity.type),
            (_("role"), entity.role),
            (_("Authfilenumber"), entity.authfilenumber),
            (_("authority"), ", ".join(e.view("incontext") for e in entity.authority)),
        ]
        return properties


class ServiceITemplatable(ITemplatableApdater):
    __select__ = ITemplatableApdater.__select__ & is_instance("Service")

    def meta_props(self):
        return ((self._cw._("Last update on"), self.entity.fmt_modification_date),)

    def main_props(self):
        _ = self._cw._
        entity = self.entity
        main_props = {}
        n_level = entity.level in ("level-D", "level-N")
        contact_label = _("Service_direction") if n_level else _("Service_manager")
        gps = ", ".join(str(c) for c in (entity.latitude, entity.longitude) if c)
        web_url = entity.printable_value("website_url")
        if web_url:
            web_url = exturl_link(self._cw, web_url)
        properties = [
            (contact_label, entity.printable_value("contact_name")),
            (_("service_level_facet"), entity.printable_value("level")),
            (_("Phone number"), entity.printable_value("phone_number")),
            (_("Address"), entity.printable_physical_address()),  # must be a propery
            (_("Opening period"), entity.printable_value("opening_period")),
            (_("Annual closure"), entity.printable_value("annual_closure")),
            (_("Email"), entity.printable_value("email")),
            (_("Write to us"), entity.printable_value("mailing_address")),
            (_("Website"), web_url),
            (
                _("SocialNetwork_plural"),
                ", ".join(e.view("urlattr", rtype="url") for e in entity.service_social_network),
            ),
            (_("Code INSEE commune"), entity.printable_value("code_insee_commune")),
            (_("GPS coordinates"), gps),
        ]
        if entity.annex_of:
            properties.insert(0, (_("main_service"), entity.annex_of[0].view("incontext")))
        info = [entry for entry in properties if entry[-1]]
        if info:
            main_props["info"] = info
        if entity.annex_of:
            properties.insert(0, (_("main_service"), entity.annex_of[0].view("incontext")))
        if gps:
            main_props["json_map_url"] = self._cw.build_url("services-map.json", srv=entity.eid)
        related_services = list(entity.related("annex_of", "object").entities())
        if related_services:
            main_props["related_services"] = [e.view("incontext") for e in related_services]
            main_props["related_entities"] = [
                e.cw_adapt_to("ITemplatable").entity_param() for e in related_services
            ]
        note = entity.printable_value("other")
        if note:
            main_props["note"] = note
        main_props["lang"] = self._cw.lang
        return main_props

    def documents_links(self):
        entity = self.entity
        documents_links = (
            (
                self._cw._("see service related documents"),
                entity.documents_url() if entity.has_documents else None,
            ),
            (
                self._cw._("see service related nominarecords"),
                (entity.nominarecords_url() if entity.has_nominarecords else None),
            ),
        )
        return [entry for entry in documents_links if entry[-1]]

    def rdf_formats(self):
        uri = self._cw.build_url(f"service/{self.entity.eid}")
        return [
            (f"{uri}/rdf.{extension}", extension, name)
            for extension, name in RDF_FORMAT_EXTENSIONS.items()
        ]

    def entity_param(self):
        self.entity.meta_props = self.meta_props()
        self.entity.properties = self.main_props()
        self.entity.documents_links = self.documents_links()
        self.entity.eulerian = self.entity.cw_adapt_to("IEulerian").actions
        self.entity.rdf_formats = self.rdf_formats()
        return self.entity


class CMSObjectITreeAdapter(ITreeAdapter):
    __regid__ = "ITree"
    __select__ = ITreeAdapter.__select__ & is_instance(*CMS_OBJECTS)
    tree_relation = "children"

    child_role = "object"
    parent_role = "subject"

    @cachedproperty
    def main_section(self):
        section_name = self.root().name
        if section_name in FIRST_LEVEL_SECTIONS:
            return section_name
        return "home"


class Service2VcardAdapater(EntityAdapter):
    __regid__ = "vcard"

    def properties(self):
        entity = self.entity
        title = entity.dc_title() or self._cw._("n/r")  # title is mandatory
        props = {
            "n": vobject.vcard.Name(given=title),
            "fn": title,
            "nickname": entity.code,
            "email": entity.email,
            "agent": entity.contact_name,
            "tel": entity.phone_number,
            "adr": vobject.vcard.Address(
                street=(entity.address or ""),
                city=(entity.city or ""),
                code=(entity.zip_code or ""),
                country="FR",
            ),
            "url": entity.website_url,
            "note": entity.opening_period,
            "uid": str(entity.eid),
        }
        if entity.service_image:
            imgfile = entity.service_image[0].image_file[0]
            props["logo"] = imgfile.cw_adapt_to("IDownloadable").download_url()
        return props

    def vcard(self):
        props = self.properties()
        card = vobject.vCard()
        for key, value in list(props.items()):
            if not value:
                continue
            try:
                key, value_type = key.split(".")
            except ValueError:
                value_type = None
            card.add(key)
            propvalue = getattr(card, key)
            propvalue.value = value
            if value_type is not None:
                propvalue.type_param = value_type
            # XXX uuid
        return card


class Absctract2CSV(EntityAdapter):
    __abstract__ = True
    __regid__ = "csv-props"
    headers = []

    def properties():
        return {}

    def csv_row(self):
        props = self.properties()
        return [(props[h] or "") for h in self.headers]


class Service2CSV(Absctract2CSV):
    __select__ = EntityAdapter.__select__ & is_instance("Service")

    headers = (
        "Id_FranceArchives",
        "Nom_du_service",
        "Identifiant_du_service",
        "Courriel",
        "Telephone",
        "Adresse_postale",
        "Adresse_du_service",
        "Ville",
        "Code_postal",
        "Horaires_d_ouverture",
        "Site_internet",
        "Code_insee_commune",
        "Latitude",
        "Longitude",
        "Lien_FranceArchives",
        "Categorie_de_service",
        "Categorie",
        "Service_de_rattachement",
    )

    def properties(self):
        entity = self.entity
        props = {
            "Id_FranceArchives": entity.eid,
            "Nom_du_service": entity.dc_title(),
            "Identifiant_du_service": entity.code,
            "Courriel": entity.email,
            "Telephone": entity.phone_number,
            "Adresse_postale": entity.mailing_address,
            "Adresse_du_service": entity.address,
            "Ville": entity.city,
            "Code_postal": entity.zip_code,
            "Horaires_d_ouverture": entity.opening_period,
            "Site_internet": entity.website_url,
            "Code_insee_commune": entity.code_insee_commune,
            "Latitude": entity.latitude,
            "Longitude": entity.longitude,
            "Lien_FranceArchives": entity.absolute_url(),
            "Categorie_de_service": entity.level.rsplit("-", 1)[-1] if entity.level else None,
            "Categorie": self._cw._(entity.level) if entity.level else None,
            "Service_de_rattachement": entity.annex_of[0].dc_title() if entity.annex_of else None,
        }
        return props


class Circular2CSV(Absctract2CSV):
    __regid__ = "csv-props"
    __select__ = EntityAdapter.__select__ & is_instance("Circular")

    def file_url(self, cwfile, prod_url):
        url = cwfile.cw_adapt_to("IDownloadable").download_url()
        base_url = self._cw.base_url()
        if url and base_url:
            return url.replace(base_url, prod_url)
        return ""

    def properties(self):
        self.entity.complete()
        entity = self.entity
        translate = self._cw._
        prod_url = "{}/".format(self._cw.vreg.config.get("consultation-base-url"))
        return (
            (_("circular_title_label"), entity.dc_title()),
            (_("circular_url"), "{}{}".format(prod_url, self.entity.rest_path())),
            (_("circular_circ_id_label"), entity.circ_id),
            (_("circular_kind_label"), entity.kind),
            (_("circular_code_label"), entity.code),
            (_("circular_nor_label"), entity.nor),
            (_("circular_status_label"), translate(entity.status)),
            (_("circular_link_label"), entity.link),
            (_("circular_additional_link_label"), "; ".join(e.url for e in entity.additional_link)),
            (
                _("circular_attachment_label"),
                "; ".join(self.file_url(e, prod_url) for e in entity.attachment),
            ),
            (
                _("circular_additional_attachment_label"),
                "; ".join(self.file_url(e, prod_url) for e in entity.additional_attachment),
            ),
            (_("circular_signing_date_label"), format_date(entity.signing_date, self._cw)),
            (_("circular_siaf_daf_kind_label"), entity.siaf_daf_kind),
            (_("circular_siaf_daf_code_label"), entity.siaf_daf_code),
            (
                _("circular_siaf_daf_signing_date_label"),
                format_date(entity.siaf_daf_signing_date, self._cw),
            ),
            (_("circular_producer_label"), entity.producer),
            (_("circular_producer_acronym_label"), entity.producer_acronym),
            (
                _("circular_modification_date_label"),
                format_date(entity.circular_modification_date, self._cw),
            ),
            (_("circular_abrogation_date_label"), format_date(entity.abrogation_date, self._cw)),
            (_("circular_abrogation_text_label"), entity.abrogation_text),
            (_("circular_archival_field_label"), entity.archival_field),
            (
                _("circular_historical_context_label"),
                "; ".join(e.dc_title() for e in entity.historical_context),
            ),
            (
                _("circular_business_field_label"),
                "; ".join(e.dc_title() for e in entity.business_field),
            ),
            (
                _("circular_document_type_label"),
                "; ".join(e.dc_title() for e in entity.document_type),
            ),
            (_("circular_action_label"), "; ".join(e.dc_title() for e in entity.action)),
            (
                _("circular_modified_text_label"),
                "; ".join(e.dc_title() for e in entity.modified_text),
            ),
            (
                _("circular_modifying_text_label"),
                "; ".join(e.dc_title() for e in entity.modifying_text),
            ),
            (
                _("circular_revoked_text_label"),
                "; ".join(e.dc_title() for e in entity.revoked_text),
            ),
        )

    def csv_row(self):
        return self.properties()


class FAQAdapater(EntityAdapter):
    __regid__ = "IFaq"
    __abstract__ = True

    def faq_category(self):
        return None


class BaseContentFAQAdapater(FAQAdapater):
    __select__ = FAQAdapater.__select__ & is_instance("BaseContent")

    @property
    def faq_category(self):
        root = self.entity.cw_adapt_to("ITree").root()
        if not root:
            return None
        if root.eid != SECTIONS["gerer"]:
            return "01_faq_basecontent_public"
        return "05_faq_basecontent_pro"


class FAFAQAdapater(FAQAdapater):
    __select__ = FAQAdapater.__select__ & is_instance("FindingAid", "FAComponent")
    faq_category = "03_faq_ir"


class CircularFAQAdapater(FAQAdapater):
    __select__ = FAQAdapater.__select__ & is_instance("Circular")
    faq_category = "04_faq_circular"


class SectionTreeAdapter(EntityAdapter):
    __select__ = is_instance("Section")
    __regid__ = "ISectionTree"
    possible_document_types = {
        "BaseContent": "article",
        "NewsContent": "actualite",
        "CommemorationItem": "pages_histoire",
        "ExternRef": "externref",
        "Map": "map",
    }

    def query_variables(self, depth, max_depth, attributes, etype):
        variables = []
        for i in range(depth):
            for attribute in attributes:
                _etype = etype if i == depth - 1 else "Section"
                if attribute == "title":
                    variables.append(
                        "translate_entity('%(etype)s', _X%(i)s.cw_eid, '%(attr)s', '%(lang)s')"
                        % {"etype": _etype, "i": i, "lang": self._cw.lang, "attr": attribute}
                    )
                elif attribute in ("display_mode", "short_description") and i == depth - 1:
                    variables.append("null")
                elif attribute == "etype":
                    variables.append(f"'{_etype}'")
                else:
                    variables.append("_X%s.cw_%s" % (i, attribute))
        # Fill variables with null until max_depth is reached
        for i in range((max_depth - depth) * len(attributes)):
            variables.append("null")
        return ", ".join(variables)

    def query_tables(self, depth, etype):
        tables = ["cw_Section AS _G"]
        for i in range(depth):
            tables.append("children_relation as rel_children%s" % i)
        for i in range(depth - 1):
            tables.append("cw_Section AS _X%s" % i)
        tables.append("cw_%s AS _X%s" % (etype, depth - 1))
        return ", ".join(tables)

    def query_triples(self, depth):
        triples = [
            "_G.cw_eid=%(eid)s",
            "rel_children0.eid_from=_G.cw_eid",
            "rel_children0.eid_to=_X0.cw_eid",
        ]
        for i in range(1, depth):
            triples.append("rel_children%s.eid_from=_X%s.cw_eid" % (i, i - 1))
            triples.append("rel_children%s.eid_to=_X%s.cw_eid" % (i, i))
        return " AND ".join(triples)

    def generate_query(self, attributes, max_depth=6):
        queries = []
        for etype in self.possible_document_types.keys():
            # Reversed for types resolution in postgres
            for depth in reversed(range(1, max_depth + 1)):
                query_template = """
                SELECT {variables}
                FROM {tables}
                WHERE {triples}""".format(
                    variables=self.query_variables(depth, max_depth, attributes, etype),
                    tables=self.query_tables(depth, etype),
                    triples=self.query_triples(depth),
                )
                queries.append(query_template)
        return " UNION ALL ".join(queries)

    def parse_results(self, row, attributes, current_dict, section_mode=None):
        subsection = row[: len(attributes)]
        eid = str(subsection[0])
        if eid not in current_dict:
            current_dict[eid] = {}
            for index in range(len(attributes)):
                current_dict[eid][attributes[index]] = subsection[index]
            current_dict[eid]["children"] = {}
            etype = current_dict[eid]["etype"]
            current_dict[eid]["url"] = self._cw.build_url(
                f"{self.possible_document_types.get(etype, etype.lower())}/{eid}"
            )
        new_row = row[len(attributes) :]
        if new_row and new_row[0] is not None:
            if not section_mode or current_dict[eid]["display_mode"] == section_mode:
                self.parse_results(
                    new_row, attributes, current_dict[eid]["children"], section_mode=section_mode
                )

    def section_dict_to_array(self, section_dict):
        if section_dict["children"]:
            section_dict["children"] = sorted(
                section_dict["children"].values(), key=lambda x: x["order"] if x["order"] else 1000
            )
            for child_dict in section_dict["children"]:
                self.section_dict_to_array(child_dict)
        return section_dict

    def retrieve_subsections(self, section_mode=None):
        redis_key = f"submenu_{self.entity.eid}_{section_mode or 'none'}_{self._cw.lang}"
        redis_connection = RedisConnector(self._cw)
        cached_data = redis_connection.get(redis_key)
        if cached_data:
            return cached_data
        # Get all subsections having documents of the following types
        attributes = ["eid", "display_mode", "title", "order", "etype", "short_description"]
        sql_query = self.generate_query(attributes)
        sys_source = self._cw.cnx.repo.system_source
        attrs = {"eid": self.entity.eid, "section_mode": section_mode}
        cu = sys_source.doexec(self._cw.cnx, sql_query, attrs)
        res = cu.fetchall()
        sections_dict = {}
        for row in res:
            self.parse_results(row, attributes, sections_dict, section_mode=section_mode)

        # sort by order and retrieve absolute_urls of documents
        sections = []
        for key, value in sections_dict.items():
            section = self.section_dict_to_array(value)
            if section:
                sections.append(section)

        result = sorted(sections, key=lambda x: x["order"] if x["order"] else 1000)
        redis_connection.set(redis_key, result, expire=86400)
        return result
