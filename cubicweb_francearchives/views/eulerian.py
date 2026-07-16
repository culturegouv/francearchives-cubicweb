# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2023
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

from cubicweb.entity import Adapter, EntityAdapter

from cubicweb.predicates import is_instance

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.dataimport import TRANSMAP

EULERIAN_FORBIDDEN_PUNCT = "!\"#$%&'()*+,;<=>?@[\\]^`’{|}~"

EULERIAN_TRANSMAP = merge_dicts(
    {},
    TRANSMAP,
    dict.fromkeys(ord(c) for c in EULERIAN_FORBIDDEN_PUNCT),
    {
        ord(" "): ord("_"),
    },
)


def normalize_eulerian_button_id(tags):
    return normalize_eulerian_value("::".join(tags))


def normalize_eulerian_value(value):
    """all values have to be normalized for Eulerian"""
    if isinstance(value, str):
        # safety belt if the "u" prefix was forgotten, we're supposed
        # to have ascii here
        chapter = str(value)
    try:
        return chapter.lower().translate(EULERIAN_TRANSMAP)
    except Exception:
        return "unknown-error-fallback"


class EulerianEntityAdapter(EntityAdapter):
    """default implementation returns 3 chapters: (etype, <main-attr>, title)"""

    __regid__ = "IEulerian"

    append_title = True  # set to False if <main-attr> is self-explanatory
    pagegroup = "editorial"

    @property
    def get_attrname(self):
        return self.entity.cw_rest_attr_info()[0]

    @cachedproperty
    def _service(self):
        has_service = hasattr(self.entity, "related_service")
        if has_service:
            return self.entity.related_service

    @property
    def service(self):
        service = self._service
        if service:
            return normalize_eulerian_value(service.code or service.zip_code or service.dc_title())
        return "unknown-service"

    @property
    def cwetype(self):
        return normalize_eulerian_value(self.entity.cw_etype)

    @property
    def path_chunks(self):
        entity = self.entity
        attrname = self.get_attrname
        chunks = [
            self.cwetype,
            # we might get integers
            str(getattr(entity, attrname)),
        ]
        if self.append_title:
            chunks.append(entity.dc_title())
        return chunks

    @property
    def path(self):
        return f"/{normalize_eulerian_value('/'.join(self.path_chunks))}"

    @property
    def events(self):
        return []

    @property
    def additional(self):
        """additional tag to be pushed to EA_datalayer"""
        return {}

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return ",".join(["", "", self.cwetype])

    @property
    def actions(self):
        """All needed information for actions (buttons clics)"""
        _ = self._cw._
        service = self._service
        if service:
            service_code = normalize_eulerian_value(service.code)
        else:
            service_code = ""
        return {
            "service_code": service_code,
            "type_doc": self.cwetype,
            "page_type": self.pagegroup,
            "document_title": normalize_eulerian_value(self.entity.rest_path().replace("/", "_")),
        }


class FAEulerianAdapater(EulerianEntityAdapter):
    """generate 3 chapters (etype, service_code, stable_id)"""

    __select__ = is_instance("FindingAid", "FAComponent")
    pagegroup = "archives"

    @property
    def path(self):
        paths = [self.cwetype, self.service, self.entity.stable_id]
        return f"/{normalize_eulerian_value('/'.join(paths))}"

    @property
    def additional(self):
        """additional tag to be pushed to EA_datalayer"""
        return {"iiif": str(int(bool(self.entity.iiif_manifest)))}

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        iiif = "iiif" if bool(self.entity.iiif_manifest) else "no-iiif"
        return ",".join([iiif, self.service, self.cwetype])


class ServiceEulerianAdapter(EulerianEntityAdapter):
    __select__ = is_instance("Service")
    pagegroup = "service"

    @property
    def path_chunks(self):
        service_code = self.entity.code or str(self.entity.eid)
        return ["Service", service_code]

    @property
    def actions(self):
        _ = self._cw._
        return {
            "service_code": self.entity.eid,
            "type_doc": self.cwetype,
            "page_type": self.pagegroup,
            "document_title": normalize_eulerian_value(self.entity.rest_path().replace("/", "_")),
        }


class CardEulerianAdapter(EulerianEntityAdapter):
    __select__ = is_instance("Card")
    append_title = False

    @property
    def pagegroup(self):
        return "editorial"


class CircularEulerianAdapter(EulerianEntityAdapter):
    __select__ = is_instance("Circular")
    append_title = False

    @property
    def get_attrname(self):
        """avoid self.entity.cw_rest_attr_info()[0] returning uuid instead of circ_id"""
        return "circ_id"

    @property
    def pagegroup(self):
        return "circular"


class NominaRecordEulerianAdapater(EulerianEntityAdapter):
    """generate 3 chapters (etype, service_code, stable_id)"""

    __select__ = is_instance("NominaRecord")

    @property
    def pagegroup(self):
        return "nomina"

    @property
    def path_chunks(self):
        return [self.cwetype, self.service, self.entity.stable_id]

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return ",".join(["", self.service, self.cwetype])


class AuthorityRecordEulerianAdapter(EulerianEntityAdapter):
    __select__ = is_instance("AuthorityRecord")
    pagegroup = "eac"


class AuthoritiesEulerianAdapter(EulerianEntityAdapter):
    __select__ = is_instance("SubjectAuthority", "AgentAuthority", "LocationAuthority")
    pagegroup = "authorities"


class SectionEulerianAdapter(EulerianEntityAdapter):
    __select__ = is_instance("Section")


class TranslationEntityEulerianAdapter(EulerianEntityAdapter):
    __abstract__ = True

    @property
    def original(self):
        return self.entity.original_entity

    @property
    def path_chunks(self):
        chunks = self.original.cw_adapt_to("IEulerian").path_chunks[:2]
        return chunks + [
            self.entity.language,
            self.entity.dc_title(),
        ]

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return self.original.cw_adapt_to("IEulerian").pagelabel


class SectionTranslationEulerianAdapter(TranslationEntityEulerianAdapter):
    __select__ = is_instance("SectionTranslation")


BASE_CONTENT_MAP = {
    "Article": "BaseContent",
    "Publication": "Publication",
    "SearchHelp": "SearchHelp",
}


class CMSEulerianEntityAdapter(EulerianEntityAdapter):
    __abstract__ = True

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return ",".join(["", "", self.cwetype])

    @cachedproperty
    def _service(self):
        has_service = hasattr(self.entity, "service")
        if has_service:
            return self.entity.service


class BaseContentEulerianAdapter(CMSEulerianEntityAdapter):
    __select__ = is_instance("BaseContent")

    @property
    def cwetype(self):
        cwetype = BASE_CONTENT_MAP.get(self.entity.content_type, "BaseContent")
        return normalize_eulerian_value(cwetype)

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return ",".join(["", self.service, self.cwetype])


class BaseContentTranslationEulerianAdapter(TranslationEntityEulerianAdapter):
    __select__ = is_instance("BaseContentTranslation")

    @property
    def cwetype(self):
        cwetype = BASE_CONTENT_MAP.get(self.original.content_type, "BaseContent")
        return normalize_eulerian_value(cwetype)

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return ",".join(["", self.service, self.cwetype])


class NewContentEulerianAdapter(CMSEulerianEntityAdapter):
    __select__ = is_instance("NewsContent")


class ExternRefEulerianAdapter(CMSEulerianEntityAdapter):
    __select__ = is_instance("ExternRef")

    @property
    def get_attrname(self):
        return "eid"

    @property
    def cwetype(self):
        return normalize_eulerian_value(self.entity.reftype)

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return ",".join(["", self.service, self.cwetype])


class MapEulerianAdapter(CMSEulerianEntityAdapter):
    __select__ = is_instance("Map")


class CommemorationItemEulerianAdapter(EulerianEntityAdapter):
    __select__ = is_instance("CommemorationItem")

    @property
    def path_chunks(self):
        return ["Commemo", str(self.entity.commemoration_year), self.entity.dc_title()]


class CommemorationItemTranslationEulerianAdapter(TranslationEntityEulerianAdapter):
    __select__ = is_instance("CommemorationItemTranslation")


class EulerianViewsAdapter(Adapter):
    """default implementation for Eulerian tags"""

    __regid__ = "IEulerianView"

    def __init__(self, _cw, view, **kwargs):
        super().__init__(_cw, **kwargs)
        self.view = view

    @property
    def path(self):
        chunks = getattr(self.view, "eulerian_path_chunks", None)
        if chunks:
            return f"/{normalize_eulerian_value('/'.join(chunks))}"
        default = normalize_eulerian_value(f"/{self._cw.relative_path(False).rstrip('/')}")
        return getattr(self.view, "eulerian_path", default)

    @property
    def pagegroup(self):
        return getattr(self.view, "eulerian_pagegroup", "")

    @property
    def events(self):
        return getattr(self.view, "eulerian_events", [])

    @property
    def additional(self):
        """additional tag to be pushed to EA_datalayer"""
        return {}

    @property
    def pagelabel(self):
        """List of up to 5 content groupings. The first label"""
        return ""

    @property
    def actions(self):
        return getattr(self.view, "eulerian_actions", {})
