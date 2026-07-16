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

"""cubicweb-pnia-content entity's classes"""
import re
from collections import OrderedDict
import csv
import urllib.request
import urllib.parse
import urllib.error

import json
from io import StringIO

from logilab.common.decorators import cachedproperty

from rql import TypeResolverException

from cubicweb import NoResultError, MultipleResultsError
from cubicweb.predicates import is_instance, score_entity, has_related_entities
from cubicweb.entities import AnyEntity, fetch_config

from cubicweb_francearchives import CMS_I18N_OBJECTS
from cubicweb_francearchives.dataimport import strip_html, unique_indices
from cubicweb_francearchives.dataimport.pdf import pdf_infos
from cubicweb_francearchives.entities import ETYPE_CATEGORIES, HTMLMixIn
from cubicweb_francearchives.entities.es import (
    PniaIFullTextIndexSerializable,
    TranslatableIndexSerializableMixin,
)
from cubicweb_francearchives.entities.ead import IndexableMixin
from cubicweb_francearchives.esutils import (
    nominarecords_number_for_service,
)
from cubicweb_francearchives.utils import safe_cut, remove_html_tags, format_date


class RelatedAutorityIndexableMixin(IndexableMixin):
    def indexes(self):
        return self._cw.execute(
            """DISTINCT Any X, XP WHERE E eid %(e)s, E related_authority X, X label XP""",
            {"e": self.eid},
        )

    def agent_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, "
            "E related_authority X, X is AgentAuthority, "
            "X label XP",
            {"e": self.eid},
        )

    def subject_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP ORDERBY XP WHERE E eid %(e)s, "
            "E related_authority X, X is SubjectAuthority, "
            "X label XP",
            {"e": self.eid},
        )

    def geo_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP ORDERBY XP  WHERE E eid %(e)s, "
            "E related_authority X, X is LocationAuthority, "
            "X label XP",
            {"e": self.eid},
        )

    def es_indexes(self):
        """method used in AbstractCMSIFTIAdapter"""
        return self._cw.execute(
            """Any L, A, T ORDERBY L
            WHERE X related_authority A, A label L, X eid %(e)s, A is Y, Y name T""",
            {"e": self.eid},
        )

    def main_indexes(self, itype):
        # itype is only here for compatibility with IndexableMixin
        return self._cw.execute(
            "DISTINCT Any X, XP ORDERBY XP WHERE E eid %(e)s, "
            "E related_authority X, X is AgentAuthority, "
            "X label XP",
            {"e": self.eid},
        )


class ImageMixIn(object):
    image_rel_name = None

    @cachedproperty
    def image(self):
        if self.image_rel_name:
            images = self.related(self.image_rel_name)
            if images:
                return images.get_entity(0, 0)

    @property
    def illustration_url(self):
        if self.image:
            return self.image.image_file[0].cw_adapt_to("IDownloadable").download_url()

    @cachedproperty
    def illustration_alt(self):
        if self.image:
            return self.image.alt
        return ""


class CmsObject(ImageMixIn, HTMLMixIn, AnyEntity):
    __abstract__ = True
    rest_attr = "eid"

    @cachedproperty
    def img(self):
        pass

    @cachedproperty
    def fmt_creation_date(self):
        return format_date(self.creation_date, self._cw, fmt="d MMMM y")

    @property
    def fmt_modification_date(self):
        return format_date(self.modification_date, self._cw, fmt="d MMMM y")

    def dc_authors(self):
        authors = self.cw_adapt_to("IMeta").author()
        if authors:
            return "; ".join(authors)

    @property
    def abstract(self):
        if hasattr(self, "header") and self.header:
            return self.header
        else:
            return safe_cut(self.content, 500, remove_html=True)

    @property
    def printable_content(self):
        return self.printable_value("content")

    @property
    def etype(self):
        return self.cw_etype

    def dc_subjects(self):
        if self.metadata:
            return self.metadata[0].keywords

    @property
    def lang(self):
        return "fr"


class TranslatableCmsObject(CmsObject):
    def i18n_query(self, *args, **kwargs):
        attrs, fvars = [], []
        for i, field in enumerate(self.i18nfields):
            attrs.append("X {field} F{i}".format(i=i, field=field))
            fvars.append("F{i}".format(i=i))
        query = """Any X, {fvars}, L ORDERBY L WHERE X translation_of E,
          {attrs}, X language L, E eid %(e)s""".format(
            fvars=", ".join(fvars), attrs=", ".join(attrs)
        )
        return query

    def i18n_rset(self, *args, **kwargs):
        query = self.i18n_query(*args, **kwargs)
        return self._cw.execute(query, {"e": self.eid})

    def i18n_links(self):
        query = """Any L ORDERBY L WHERE X translation_of E,
                  X language L, E eid %(e)s"""
        langs = [lang for lang, in self._cw.execute(query, {"e": self.eid})]
        langs.append("fr")
        langs = sorted(langs, key=lambda x: x != self.lang)
        if len(langs) == 1:
            return []
        return [
            (
                self._cw._(f"{lang_code}_lang"),
                lang_code,
                f"{self._cw.base_url()}{lang_code}/{self.rest_path()}",
                f"Translate in {lang_code}",
            )
            for lang_code in langs
        ]

    def translations(self, *args, **kwargs):
        values = {}
        for res in self.i18n_rset(*args, **kwargs).iter_rows_with_entities():
            entity = res[0]
            values[entity.language] = {attr: getattr(entity, attr) for attr in self.i18nfields}
        return values

    def translations_in_lang(self, lang=None):
        lang = lang or self._cw.lang
        if lang == "fr":
            return {}
        attrs, fvars = [], []
        for i, field in enumerate(self.i18nfields):
            attrs.append("X {field} F{i}".format(i=i, field=field))
            fvars.append("F{i}".format(i=i))
        query = """Any X, {fvars} WHERE X translation_of E,
        {attrs},
        X language %(lang)s, E eid %(e)s""".format(
            fvars=", ".join(fvars), attrs=", ".join(attrs)
        )
        rset = self._cw.execute(query, {"lang": lang, "e": self.eid})
        if rset:
            entity = rset.one()
            return {attr: getattr(entity, attr) for attr in self.i18nfields}
        return {}

    @property
    def lang(self):
        return self.cw_attr_cache.get("lang", "fr")


class BaseContent(RelatedAutorityIndexableMixin, TranslatableCmsObject):
    __regid__ = "BaseContent"
    image_rel_name = "basecontent_image"
    i18nfields = ("title", "header", "content", "summary")

    def dc_title(self):
        if self._cw.lang == "fr":
            return self.title
        return self.cw_adapt_to("ITemplatable").entity_param().title

    def rest_path(self):
        return "article/{}".format(self.eid)

    @property
    def service(self):
        if self.basecontent_service:
            return self.basecontent_service[0]

    @property
    def services(self):
        return self.basecontent_service

    @property
    def dates(self):
        return self.fmt_modification_date

    @property
    def etype(self):
        return self.content_type


class TranslationMixin(object):
    rest_attr = "eid"

    def rest_path(self):
        return "{}/{}".format(self.cw_etype.lower(), self.eid)

    @cachedproperty
    def original_entity(self):
        if self.translation_of:
            return self.translation_of[0]


class BaseContentTranslation(TranslationMixin, CmsObject):
    __regid__ = "BaseContentTranslation"

    @property
    def summary_policy(self):
        return self.original_entity.summary_policy


class NewsContent(CmsObject):
    __regid__ = "NewsContent"
    image_rel_name = "news_image"

    def rest_path(self):
        return "actualite/{}".format(self.eid)

    @property
    def keywords(self):
        pass

    @property
    def dates(self):
        if self.start_date and self.stop_date:
            if self.start_date == self.stop_date:
                return format_date(self.start_date, self._cw, fmt="d MMMM y")
            start_date = format_date(self.start_date, self._cw, fmt="d MMMM y")
            stop_date = format_date(self.stop_date, self._cw, fmt="d MMMM y")
            return "-".join([start_date, stop_date])
        date = self.start_date or self.stop_date
        return format_date(date, self._cw, fmt="d MMMM y")


class Circular(AnyEntity):
    __regid__ = "Circular"
    rest_attr = "circ_id"
    lang = "fr"

    def rest_path(self):
        return "circulaire/{}".format(self.circ_id)

    def dc_title(self):
        return self.title

    def sortdate(self):
        return self.siaf_daf_signing_date or self.signing_date

    @property
    def values_as_json(self):
        old_lang = self._cw.lang
        if old_lang != "fr":
            # export Concepts in french
            self._cw.set_lang("fr")
        # install i18n configuration for `lang` translation.
        # as self._cw._ is an unicode string
        self._cw.set_language(self._cw.lang)
        values = self.cw_adapt_to("csv-props").csv_row()
        if old_lang != "fr":
            self._cw.set_lang(old_lang)
            self._cw.set_language(old_lang)
        return values

    @property
    def values_from_json(self):
        return json.loads(self.json_values)


def compute_service_title(req, name, name2, level):
    if level == "level-D":
        return name2 or name or req._("Unknown")
    else:
        terms = [name, name2]
        return " - ".join(t for t in terms if t) or req._("Unknown")


class Service(ImageMixIn, HTMLMixIn, AnyEntity):
    fetch_attrs, cw_fetch_order = fetch_config(
        [
            "category",
            "name",
            "name2",
            "city",
            "address",
            "short_name",
            "dpt_code",
            "zip_code",
            "code_insee_commune",
            "thumbnail_url",
            "thumbnail_dest",
            "level",
        ]
    )
    __regid__ = "Service"
    image_rel_name = "service_image"
    rest_attr = "eid"
    lang = "fr"

    def dc_title(self):
        return compute_service_title(self._cw, self.name, self.name2, self.level)

    def rest_path(self):
        rset = self.annex_of
        if rset:
            return f"service/{rset[0].eid}#service-{self.eid}"
        else:
            return f"service/{self.eid}"

    @cachedproperty
    def fmt_creation_date(self):
        return format_date(self.creation_date, self._cw, fmt="d MMMM y")

    @property
    def fmt_modification_date(self):
        return format_date(self.modification_date, self._cw, fmt="d MMMM y")

    @staticmethod
    def from_code(req, code):
        try:
            if code.startswith("c-"):
                if not code[2:].isdigit():
                    return None
                return req.find("Service", eid=(int(code[2:]))).one()
            return req.find("Service", code=code).one()
        except (TypeResolverException, NoResultError, MultipleResultsError):
            return None

    @property
    def has_documents(self):
        return bool(
            self._cw.execute(
                """Any 1 WHERE EXISTS(F service X, NOT X code NULL,
                F is FindingAid, X eid %(e)s)""",
                {"e": self.eid},
            )
        )

    @property
    def has_nominarecords(self):
        return bool(nominarecords_number_for_service(self._cw, self.eid))

    def is_partner(self, published=False):
        if self.has_nominarecords:
            return True
        if not published:
            query = """
            Any 1 WHERE EXISTS(N service X, NOT X code NULL,
            N is IN (NominaRecord, FindingAid),
            X eid %(e)s)"""
        else:
            query = """
            Any 1 WHERE EXISTS(F service X, F is FindingAid,
            F in_state ST, ST name 'wfs_cmsobject_published'),
            NOT X code NULL, X eid %(e)s"""
        return bool(self._cw.execute(query, {"e": self.eid}))

    def documents_url(self):
        code = self.code if self.code else f"c-{self.eid}"
        return self._cw.build_url("inventaires/{}".format(code))

    def nominarecords_url(self):
        code = self.code if self.code else f"c-{self.eid}"
        return self._cw.build_url("basedenoms/service/{}".format(code))

    def bounce_url(self, attrs):
        if self.search_form_url:
            terms = re.search(r"\{(\w+)\}", self.search_form_url)
            if terms:
                attrs = {
                    k: urllib.parse.quote_plus(v.encode("utf-8"))
                    for k, v in list(attrs.items())
                    if v
                }
                try:
                    return self.search_form_url.format(**attrs)
                except Exception:
                    # could not replace placeholder
                    # see https://extranet.logilab.fr/ticket/69111700
                    return self.website_url
        return self.search_form_url or self.website_url

    def printable_physical_address(self, sep=", "):
        terms = [
            self.printable_value("address"),
            self.printable_value("zip_code"),
            self.printable_value("city"),
        ]
        return sep.join(str(t) for t in terms if t)

    def physical_address(self, sep=", "):
        terms = [self.address, self.zip_code, self.city]
        return sep.join(str(t) for t in terms if t)

    def publisher(self):
        publisher = self.short_name or self.name2 or self.name
        if not publisher and self.code:
            return self.code.upper()
        return publisher

    @property
    def save_iiif_ead_policy(self):
        if self.iiif_extptr:
            return self.iiif_ead_policy or "iiif_role"


# XXX duplicated from cubes.frarchives_edition.views.primary
def get_ancestors(entity, result=None):
    if result is None:
        result = []
    if not hasattr(entity, "reverse_children"):
        return []
    parent = entity.reverse_children
    while parent:
        result.append(parent[0].eid)
        parent = parent[0].reverse_children
    result.reverse()
    return result


class ExternRef(RelatedAutorityIndexableMixin, CmsObject):
    __regid__ = "ExternRef"
    fetch_attrs, cw_fetch_order = fetch_config(
        ["title", "reftype", "content", "start_year", "stop_year"]
    )
    image_rel_name = "externref_image"

    @property
    def dates(self):
        dates = [self.start_year, self.stop_year]
        return " - ".join(str(e) for e in dates if e is not None)

    @property
    def service(self):
        if self.exref_service:
            return self.exref_service[0]

    @property
    def services(self):
        return self.exref_service

    @property
    def etype(self):
        return self.reftype


class MapCSVReader(object):
    fieldnames = OrderedDict(
        [("Code_insee", "code"), ("URL", "url"), ("Couleur", "color"), ("Legende", "legend")]
    )
    delimiter = ","
    # required_fiels is used in cubicweb_frarchives_edition hooks to build error message
    required_fields = ("Code_insee", "Couleur", "Legende")

    def csv_reader(self, csvfile):
        return csv.DictReader(
            csvfile, delimiter=self.delimiter, fieldnames=list(self.fieldnames.keys())
        )

    def csv_headers(self, csvfile):
        return next(csv.reader(csvfile, delimiter=self.delimiter))


class Map(MapCSVReader, ImageMixIn, HTMLMixIn, AnyEntity):
    __regid__ = "Map"
    fetch_attrs = ("title", "map_title", "top_content", "bottom_content")
    image_rel_name = "map_image"
    rest_attr = "eid"
    lang = "fr"

    def dc_title(self):
        return self.title

    def data(self):
        data = []
        fp = StringIO(self.map_file.getvalue().decode("utf-8"))
        reader = self.csv_reader(fp)
        for line in reader:
            entry = {self.fieldnames[key]: value if value else "" for key, value in line.items()}
            if "code" in entry:
                entry["code"] = entry["code"].lower()
            data.append(entry)
        return data


class OfficialText(AnyEntity):
    __regid__ = "OfficialText"
    fetch_attrs, cw_fetch_order = fetch_config(["code", "name"])
    lang = "fr"

    def dc_title(self):
        return self.code

    def dc_description(self):
        return self.name


class CMSI18NIFTIAdapter(PniaIFullTextIndexSerializable):
    __select__ = is_instance(*CMS_I18N_OBJECTS) & has_related_entities("translation_of")

    @cachedproperty
    def original_entity(self):
        return self.entity.original_entity

    @cachedproperty
    def ift_original(self):
        if self.original_entity:
            return self.original_entity.cw_adapt_to("IFullTextIndexSerializable")

    @property
    def es_id(self):
        if self.entity.original_entity:
            return self.ift_original.es_id

    def serialize(self, complete=True):
        if self.entity.original_entity:
            return self.ift_original.serialize(complete)


class AlltextIFTIAdapterMixin:
    alltext_fields = ["synopsis", "content"]

    def alltext_values(self, data):
        alltext_values = []
        for field_name in self.alltext_fields:
            field_value = data.pop(field_name, None)
            if field_value:
                alltext_values.append(strip_html(field_value))
        return "\n".join(alltext_values)


class AbstractCMSIFTIAdapter(PniaIFullTextIndexSerializable, AlltextIFTIAdapterMixin):
    __abstract__ = True
    numeric_indexable = False

    def serialize(self, complete=True):
        data = super(AbstractCMSIFTIAdapter, self).serialize(complete)

        data.update(
            {
                "escategory": ETYPE_CATEGORIES[self.entity.cw_etype],
                "ancestors": get_ancestors(self.entity),
                "dates": {
                    "gte": self.entity.modification_date.year,
                    "lte": self.entity.modification_date.year,
                },
                "sortdate": self.entity.modification_date.strftime("%Y-%m-%d"),
                "alltext": self.alltext_values(data),
            }
        )
        return data


class CMSIFTIAdapterMixin:
    custom_indexable_attributes = ("order",)


class CardIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Card")

    def serialize(self, complete=True):
        if not self.entity.do_index:
            return {}
        data = super().serialize(complete=complete)
        data.update({"cw_etype": "Article", "estype": self.entity.cw_etype})
        return data

    @property
    def fmt_modification_date(self):
        return format_date(self.modification_date, self._cw, fmt="d MMMM y")


class NewsContentIFTIAdapter(CMSIFTIAdapterMixin, AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("NewsContent")

    def serialize(self, complete=True):
        data = super(NewsContentIFTIAdapter, self).serialize(complete)
        # if start date or stop date are defined, use these dates for facet
        # search and for date sorting
        # otherwise, use modification date (default behaviour cf AbstractCMSIFTIAdapter)
        start_date = self.entity.start_date or self.entity.stop_date
        stop_date = self.entity.stop_date or start_date
        if start_date or stop_date:
            data["dates"] = {"gte": start_date.year, "lte": stop_date.year}
            data["sortdate"] = start_date.strftime("%Y-%m-%d")
        return data


class MapIFTIAdapter(CMSIFTIAdapterMixin, AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Map")

    alltext_fields = ["top_content", "bottom_content", "map_title"]

    def serialize(self, complete=True):
        data = super(MapIFTIAdapter, self).serialize(complete)
        data.pop("map_file", None)

        return data


class BaseContentMixIn(TranslatableIndexSerializableMixin):
    def serialize(self, complete=True, **kwargs):
        data = super(BaseContentMixIn, self).serialize(complete)
        services = self.entity.basecontent_service
        if services:
            data["service"] = [
                {"eid": s.eid, "code": s.code, "level": s.level, "title": s.publisher()}
                for s in services
            ]
        if self.entity.content_type:
            data["cw_etype"] = self.entity.content_type
        data["index_entries"] = [
            {"label": label, "authtype": cw_etype, "authority": auth}
            for label, auth, cw_etype in self.entity.es_indexes()
        ]
        data.update(self.add_translations(complete=complete, **kwargs))
        return data


class BaseContentIFTIAdapter(CMSIFTIAdapterMixin, BaseContentMixIn, AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("BaseContent")


class FileAttachmentIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = (
        AbstractCMSIFTIAdapter.__select__
        & is_instance("File")
        & score_entity(lambda f: f.reverse_attachment or f.reverse_additional_attachment)
    )

    @cachedproperty
    def ift_circular(self):
        if self.entity.reverse_attachment:
            circular = self.entity.reverse_attachment[0]
        else:
            # predicates guarantees that we either have and attachment or an additional attachment
            circular = self.entity.reverse_additional_attachment[0]
        return circular.cw_adapt_to("IFullTextIndexSerializable")

    @property
    def es_id(self):
        return self.ift_circular.es_id

    def serialize(self, complete=True):
        return self.ift_circular.serialize(complete)


class CommemorationItemIFTIAdapter(
    CMSIFTIAdapterMixin, TranslatableIndexSerializableMixin, AbstractCMSIFTIAdapter
):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("CommemorationItem")
    i18nfields = ("title", "header", "subtitle", "content")
    custom_indexable_attributes = ("order",)
    alltext_fields = ["subtitle", "content", "header"]

    def serialize(self, complete=True, **kwargs):
        data = super(CommemorationItemIFTIAdapter, self).serialize(complete)
        data.pop("dates", None)
        data.pop("sortdate", None)
        if self.entity.start_year is not None or self.entity.stop_year is not None:
            start_year = self.entity.start_year or self.entity.stop_year
            stop_year = self.entity.stop_year or start_year
            data["dates"] = {"gte": start_year, "lte": stop_year}
            if self.entity.start_year < 0:
                # TODO f"BC {abs(start_year):04d}-01-01"
                # "sortdate": {"type": "date", "format": "yyyy-MM-dd||G yyy-MM-dd" }
                # BC dates are not taken into account of for the moment. Just set them to 0
                data["sortdate"] = "0000-01-01"
            else:
                data["sortdate"] = f"{self.entity.start_year:04}-01-01"
        data["index_entries"] = [
            {"label": label, "authtype": cw_etype, "authority": auth}
            for label, auth, cw_etype in self.entity.es_indexes()
        ]
        data.update(self.add_translations(complete=complete, **kwargs))
        return data


def get_preflabel(concept):
    for preflabel in concept.preferred_label:
        if preflabel.language_code and preflabel.language_code.lower()[:2] == "fr":
            return preflabel.label
    if concept.preferred_label:
        return concept.preferred_label[0].label


class CircularIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Circular")
    custom_indexable_attributes = ("order",)
    alltext_fields = ["kind", "siaf_daf_code", "code", "attachment", "siaf_daf_kind"]

    def _index_subjects_authorities(self, concept):
        """Add Subject entities to ElasticSearch index Concept entity
        is related to.

        :param Concept concept: Concept entity
        """
        # find related SubjectAuthority entities
        subject_authorities = self._cw.execute(
            "Any X WHERE X is SubjectAuthority, X same_as %(eid)s", {"eid": concept.eid}
        )
        return [{"authority": r[0], "authtype": "SubjectAuthority"} for r in subject_authorities]

    def serialize(self, complete=True):
        data = super(CircularIFTIAdapter, self).serialize(complete)
        signing_date = self.entity.sortdate()
        index_entries = []
        data.pop("dates", None)
        data.pop("sortdate", None)
        if signing_date:
            data["sortdate"] = signing_date.strftime("%Y-%m-%d")
            data["siaf_daf_signing_year"] = signing_date.year
            data["dates"] = {"gte": signing_date.year, "lte": signing_date.year}
        if self.entity.business_field:
            data["business_field"] = bfields = []
            for field in self.entity.business_field:
                bfield = get_preflabel(field)
                if bfield:
                    bfields.append(bfield)
                index_entries += self._index_subjects_authorities(field)
        if self.entity.archival_field:
            data["archival_field"] = self.entity.archival_field
        if self.entity.historical_context:
            data["historical_context"] = get_preflabel(self.entity.historical_context[0])
            index_entries += self._index_subjects_authorities(self.entity.historical_context[0])
        if self.entity.document_type:
            data["document_type"] = get_preflabel(self.entity.document_type[0])
            index_entries += self._index_subjects_authorities(self.entity.document_type[0])
        if self.entity.action:
            data["action"] = get_preflabel(self.entity.action[0])
            index_entries += self._index_subjects_authorities(self.entity.action[0])
        attachments = list(self.entity.attachment) + list(self.entity.additional_attachment)
        if attachments:
            afields = []
            for a in attachments:
                if a.data_format == "application/pdf":
                    # XXX else: try a.printable_value('data',
                    # format='text/plain')
                    fpath = self._cw.execute(
                        "Any fspath(D) WHERE F eid %(e)s, F data D", {"e": a.eid}
                    )[0][0].getvalue()
                    try:
                        text = pdf_infos(fpath).get("text")
                        if text:
                            afields.append(text)
                    except Exception:
                        continue
            data["alltext"] += "\n" + " ".join(afields)
        if index_entries:
            data["index_entries"] = unique_indices(index_entries, keys=("authority",))
        return data


class ExternRefIFTIAdapter(CMSIFTIAdapterMixin, AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("ExternRef")

    def serialize(self, complete=True):
        data = super(ExternRefIFTIAdapter, self).serialize(complete)

        # if start year or stop year, use start/stop year for facet and sort
        # otherwise, fallback to default (modification date) behaviour
        # cf AbstractCMSIFTIAdapter
        if self.entity.start_year is not None or self.entity.stop_year is not None:
            start_year = self.entity.start_year or self.entity.stop_year
            stop_year = self.entity.stop_year or start_year
            data["dates"] = {"gte": start_year, "lte": stop_year}
            if start_year < 0:
                # TODO f"BC {abs(start_year):04d}-01-01"
                # "sortdate": {"type": "date", "format": "yyyy-MM-dd||G yyy-MM-dd" }
                # BC dates are not taken into account of for the moment. Just set them to 0
                data["sortdate"] = "0000-01-01"
            else:
                data["sortdate"] = f"{start_year:04d}-01-01"
        data["cw_etype"] = self.entity.reftype.capitalize()
        data["index_entries"] = [
            {"label": label, "authtype": cw_etype, "authority": auth}
            for label, auth, cw_etype in self.entity.es_indexes()
        ]
        services = self.entity.exref_service
        if services:
            data["service"] = [
                {"eid": s.eid, "code": s.code, "level": s.level, "title": s.publisher()}
                for s in services
            ]
        return data


class ServiceIFTIAdapter(AbstractCMSIFTIAdapter):
    __select__ = AbstractCMSIFTIAdapter.__select__ & is_instance("Service")
    alltext_fields = [
        "code",
        "other",
        "address",
        "mailing_address",
        "city",
        "name",
        "category",
        "name2",
        "contact_name",
        "short_name",
    ]

    def serialize(self, complete=True, published=False):
        data = super(ServiceIFTIAdapter, self).serialize(complete)
        data.update(
            {
                "sort_name": self.entity.name,
                "is_partner": self.entity.is_partner(published=published),
            }
        )
        return data


class ImageMixIn(object):
    @cachedproperty
    def alt(self):
        """use as value of alt attribute in <img>"""
        return safe_cut(self.description, 77, remove_html=True)


class Image(ImageMixIn, HTMLMixIn, AnyEntity):
    __regid__ = "Image"
    fetch_attrs, cw_fetch_order = fetch_config(["description", "caption", "uri"])
    lang = "fr"

    @cachedproperty
    def legend(self):
        legend = []
        if self.caption:
            legend.append(remove_html_tags(self.caption))
        if self.copyright:
            legend.append(self.copyright)
        return " / ".join(legend)

    def dc_title(self):
        return self.image_file[0].dc_title() if self.image_file else self._cw._("Image")


class CssImage(ImageMixIn, HTMLMixIn, AnyEntity):
    __regid__ = "CssImage"
    fetch_attrs, cw_fetch_order = fetch_config(["cssid", "description", "caption"])


class GlossaryTerm(AnyEntity):
    __regid__ = "GlossaryTerm"
    fetch_attrs, cw_fetch_order = fetch_config(
        ["term", "term_plural", "short_description", "description"]
    )
    rest_attr = "eid"
    lang = "fr"

    @cachedproperty
    def fmt_creation_date(self):
        return format_date(self.creation_date, self._cw, fmt="d MMMM y")

    @cachedproperty
    def fmt_modification_date(self):
        return format_date(self.modification_date, self._cw, fmt="d MMMM y")


class FaqItem(TranslatableCmsObject):
    __regid__ = "FaqItem"
    fetch_attrs, cw_fetch_order = fetch_config(["order", "answer", "question", "category"])
    i18nfields = ("question", "answer")

    def dc_title(self):
        if self._cw.lang == "fr":
            return remove_html_tags(self.question)
        return self.cw_adapt_to("ITemplatable").entity_param().question


class FaqItemTranslation(TranslationMixin, AnyEntity):
    __regid__ = "FaqItemTranslation"
    fetch_attrs, cw_fetch_order = fetch_config(["answer", "question"])


class SiteLink(AnyEntity):
    __regid__ = "SiteLink"
    fetch_attrs, cw_fetch_order = fetch_config(
        ["url", "context", "label_fr", "label_en", "label_es", "label_de", "order"]
    )

    def dc_title(self):
        label = self.label_fr
        return getattr(self, "label_{}".format(self._cw.lang)) or label

    def url(self):
        link = self.link
        return link if link.startswith("http") else self._cw.build_url(link)

    @cachedproperty
    def fmt_modification_date(self):
        return format_date(self.modification_date, self._cw, fmt="d MMMM y")


class Metadata(AnyEntity):
    __regid__ = "Metadata"
    rest_attr = "uuid"
    lang = "fr"
