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

"""cubicweb-pnia-ead entity's classes"""
import os.path as osp
import json
from collections import defaultdict
from urllib.parse import urlparse

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance
from cubicweb.entity import EntityAdapter
from cubicweb.entities.adapters import ITreeAdapter
from cubicweb.entities import AnyEntity, fetch_config

from cubicweb_elasticsearch.entities import IFullTextIndexSerializable

from cubicweb_francearchives import IIIF_MANIFEST_ROLE

from cubicweb_francearchives.utils import is_absolute_url
from cubicweb_francearchives.entities import ETYPE_CATEGORIES, systemsource_entity
from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.dataimport import strip_html, pdf, unique_indices, normalize_entry
from cubicweb_francearchives.dataimport.ead import dates_for_es_doc, service_infos_for_es_doc


def clean_html(data):
    if data:
        return strip_html(data).replace("\n", "")
    return data


class AbstractIRIFTIAdapter(IFullTextIndexSerializable):
    __abstract__ = True

    @property
    def es_id(self):
        return self.entity.stable_id

    @property
    def get_did(self):
        return self._cw.execute(
            "Any E, T, U, S, P, O, A, N  WHERE X did E, E is Did, "
            "E unitid U, E unittitle T, E startyear S, E stopyear P, "
            "E origination O, E abstract A, E note N, X eid %(eid)s",
            {"eid": self.entity.eid},
        ).one()

    @property
    def get_digitized(self):
        return self._cw.execute(
            "Any V, R WHERE X eid %(eid)s, X digitized_versions V, V role R",
            {"eid": self.entity.eid},
        )

    @property
    def get_digitized_all(self):
        digitized = self.get_digitized
        iiif = (
            bool([d for d, role in digitized if role == IIIF_MANIFEST_ROLE]) if digitized else False
        )
        return DZFacetValues.index_values(digitized=bool(digitized), iiif=iiif)

    def get_service_dates_info(self, es_doc):
        cu = self._cw.system_sql(self.service_and_dates_sql, {"eid": self.entity.eid})
        rset = cu.fetchall()

        def service_title(code, name, name2, short_name):
            publisher = short_name or name2 or name
            if not publisher and code:
                return code.upper() if code else None
            return publisher

        infos = [
            {
                "startyear": startyear,
                "stopyear": stopyear,
                "service": {
                    "eid": s_eid,
                    "code": s_code.upper() if s_code else None,
                    "level": self._cw._(s_level),
                    "title": service_title(s_code, s_name, s_name2, s_short_name),
                },
            }
            for (
                s_eid,
                s_code,
                s_level,
                s_name,
                s_name2,
                s_short_name,
                startyear,
                stopyear,
            ) in rset
        ][0]
        es_doc.update(service_infos_for_es_doc(self._cw, infos["service"]))
        es_doc.update(dates_for_es_doc(infos))
        return es_doc

    def serialize(self, complete=True, es_doc=None):
        entity = self.entity
        if es_doc is None:
            if "EsDocument" in entity.cw_rset.description[entity.cw_row]:
                # if an EsDocument is on the same row we assume it is the related es document
                doc_col = entity.cw_rset.description[entity.cw_row].index("EsDocument")
                esdoc = entity.cw_rset.get_entity(entity.cw_row, doc_col)
                es_doc = esdoc.doc
            else:
                doc = entity.reverse_entity
                if doc and doc[0].doc:
                    es_doc = doc[0].doc
            if es_doc is None:
                return self.serialize_from_db()
        # adapt es_doc
        es_doc.update(
            {
                "eid": entity.eid,
                "creation_date": entity.creation_date.isoformat(),
            }
        )
        if "digitized_all" not in es_doc:
            # introduced in 4.5.0, wait for whole ES indexation to add them in ESDocuments
            es_doc["digitized_all"] = self.get_digitized_all
        if isinstance(es_doc, str):
            # sqlite return unicode instead of dict
            es_doc = json.loads(es_doc)
        return es_doc

    def build_indexes(self):
        rset = self._cw.execute(
            "Any I, A, AN, IL, AL, R, T, N ORDERBY I WHERE X eid %(eid)s, "
            "I index X, I authority A, A is ET, ET name AN, "
            "A label AL, I label IL, I role R, I type T, I authfilenumber N",
            {"eid": self.entity.eid},
        )
        indexes, originators = [], set()
        for (
            index_eid,
            autheid,
            auth_type,
            index_label,
            auth_label,
            role,
            itype,
            authfilenumber,
        ) in rset:
            # the can have several couples index_eid/autheid with different type
            # for now just keep one of them to be iso with the export
            # we still neead the normalized form to indentify unqiue indexes
            indexes.append(
                {
                    "authority": autheid,
                    "label": index_label,
                    "normalized": normalize_entry(index_label),
                    "authfilenumber": authfilenumber,
                    "type": itype,
                    "authtype": auth_type,
                }
            )
            if role != "index":
                originators.add(auth_label)
        indexes, originators = unique_indices(indexes), list(originators)
        # remove normalized data
        [index.pop("normalized") for index in indexes]
        return indexes, originators

    def serialize_from_db(self, complete=True):
        entity = self.entity
        if complete:
            entity.complete()
        indexes, originators = self.build_indexes()
        did = self.get_did
        custom_attrs = self.custom_attributes()
        titleproper = custom_attrs.pop("titleproper", None)
        alltext = [titleproper, entity.description, did.abstract, did.note]
        digitized = self.get_digitized
        iiif = (
            bool([d for d, role in digitized if role == IIIF_MANIFEST_ROLE]) if digitized else False
        )
        es_doc = {
            "acquisition_info": clean_html(entity.acquisition_info),
            "alltext": " ".join(clean_html(e) for e in alltext if e) or None,
            "creation_date": entity.creation_date.isoformat(),
            "eid": entity.eid,
            "cw_etype": entity.cw_etype,
            "escategory": self.escategory,
            "did": {"unitid": did.unitid, "unittitle": did.unittitle},
            "digitized": bool(digitized),
            "digitized_all": DZFacetValues.index_values(digitized=bool(digitized), iiif=iiif),
            "fa_stable_id": self.fa_stable_id,
            "index_entries": indexes or None,
            "originators": originators or None,
            "scopecontent": clean_html(entity.scopecontent),
            "stable_id": entity.stable_id,
        }
        # update services, dates
        self.get_service_dates_info(es_doc)
        es_doc.update(custom_attrs)
        es_doc = {key: value for key, value in es_doc.items() if value is not None}
        return es_doc

    def custom_attributes(self):
        return {}


class FindingAidIFTIAdapter(AbstractIRIFTIAdapter):
    __select__ = AbstractIRIFTIAdapter.__select__ & is_instance("FindingAid")
    escategory = ETYPE_CATEGORIES["FindingAid"]

    @property
    def fa_stable_id(self):
        return self.entity.stable_id

    def custom_attributes(self):
        data = {"eadid": self.entity.eadid}
        titleproper = self._cw.execute(
            "Any T WHERE X eid %(eid)s, X fa_header F, F titleproper T", {"eid": self.entity.eid}
        )[0][0]
        if titleproper:
            data["titleproper"] = titleproper
        # if pdf
        rset = self._cw.execute(
            "Any FSPATH(D) LIMIT 1 WHERE F eid %(eid)s, "
            "F findingaid_support A, A data D, "
            "A data_format 'application/pdf'",
            {"eid": self.entity.eid},
        )
        if rset:
            filepath = rset[0][0].getvalue()
            try:
                infos = pdf.pdf_infos(filepath)
                data["text"] = infos["text"] or None
            except Exception:
                self.error("%s: Could not retrieve data from %s:", self.entity.eid, filepath)
        return data

    @property
    def service_and_dates_sql(self):
        """Do a single request for optimisation"""
        return """
            SELECT _S.cw_eid,_S.cw_code, _S.cw_level, _S.cw_name, _S.cw_name2,
                   _S.cw_short_name,
                   _D.cw_startyear, _D.cw_stopyear
            FROM cw_Did AS _D, cw_FindingAid AS _X
            LEFT OUTER JOIN cw_Service AS _S ON (_X.cw_service=_S.cw_eid)
            WHERE _X.cw_did=_D.cw_eid AND _X.cw_eid=%(eid)s"""


class FAComponentIFTIAdapter(AbstractIRIFTIAdapter):
    __select__ = AbstractIRIFTIAdapter.__select__ & is_instance("FAComponent")
    escategory = ETYPE_CATEGORIES["FAComponent"]

    @property
    def fa_stable_id(self):
        return self.findingaid.stable_id

    @property
    def findingaid(self):
        return self._cw.execute(
            "Any F, ST WHERE X finding_aid F, F stable_id ST, X eid %(eid)s",
            {"eid": self.entity.eid},
        ).one()

    @property
    def service_and_dates_sql(self):
        """Do a single request for optimistaion"""
        return """
            SELECT _S.cw_eid,_S.cw_code, _S.cw_level, _S.cw_name, _S.cw_name2,
                  _S.cw_short_name,
                   _D.cw_startyear, _D.cw_stopyear
            FROM cw_Did AS _D, cw_FAComponent AS _X, cw_FindingAid AS _F
                LEFT OUTER JOIN cw_Service AS _S ON (_F.cw_service=_S.cw_eid)
                WHERE _X.cw_finding_aid=_F.cw_eid AND
                      _X.cw_did=_D.cw_eid AND
                      _X.cw_eid=%(eid)s
        """


class RecordITreeAdapter(ITreeAdapter):
    __regid__ = "ITree"
    __select__ = ITreeAdapter.__select__ & is_instance("FAComponent")
    tree_relation = "parent_component"


class IndexableMixin(object):
    def index_by_types(self):
        by_types = defaultdict(list)
        for index in self.index_entries:
            by_types[index.type].append(index)
        return by_types

    @cachedproperty
    def indices(self):
        return {
            "agents": self.agent_indexes().entities(),
            "subjects": self.subject_indexes().entities(),
            "locations": self.geo_indexes().entities(),
        }

    def main_indexes(self, itype):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, "
            "X is AgentName, X index E, "
            "X label XP, X type %(t)s",
            {"t": itype, "e": self.eid},
        )

    def agent_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP, XT ORDERBY XP WHERE E eid %(e)s, "
            "X is AgentName, X index E, "
            "X label XP, X type XT",
            {"e": self.eid},
        )

    def subject_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP, XT ORDERBY XP WHERE E eid %(e)s, "
            "X is Subject, X index E, "
            "X label XP, X type XT",
            {"e": self.eid},
        )

    def subject_authority_indexes(self):
        return self._cw.execute(
            "DISTINCT Any A, AP WHERE E eid %(e)s, "
            "X is Subject, X index E, "
            "A label AP, X authority A",
            {"e": self.eid},
        )

    def geo_indexes(self):
        return self._cw.execute(
            "DISTINCT Any X, XP WHERE E eid %(e)s, X is Geogname, X index E, X label XP",
            {"e": self.eid},
        )


class FindingAidBaseMixin(object):
    lang = "fr"

    def get_extptr_for_bounce_url(self, eadid, did):
        if did.extptr:
            # special handling for ANOM arks, we have to rebuild the full URL
            if did.extptr.startswith("ark:/"):
                if eadid.startswith("FRANOM"):
                    return "http://anom.archivesnationales.culture.gouv.fr/" + did.extptr
            else:
                return did.extptr

    @cachedproperty
    def is_iiif_active(self):
        # so far in cms we try all services
        service = self.related_service
        if not service:
            self.error("No service found for %s (stable_id %s)", self, self.stable_id)
            return False
        return service.iiif_extptr or self._cw.vreg.config.get("instance-type") == "cms"

    @property
    def bounce_url(self):
        """URL of the website the FindingAid originates from
        (cf. https://extranet.logilab.fr/ticket/64667749)
        """
        eadid = self.finding_aid[0].eadid
        did = self.did[0]
        extptr = self.get_extptr_for_bounce_url(eadid, did)
        if extptr:
            return extptr
        if self.cw_etype == "FindingAid" and self.website_url:
            return self.website_url
        if self.cw_etype == "FAComponent":
            fa = self.finding_aid[0]
            extptr = self.get_extptr_for_bounce_url(eadid, fa.did[0])
            if extptr:
                return extptr
            if fa.website_url:
                return fa.website_url
        if self.related_service:
            attrs = {"unittitle": did.unittitle, "unitid": did.unitid, "eadid": eadid}
            return self.related_service.bounce_url(attrs)

    @property
    def unprocessed_digitized_urls(self):
        """List of (url, role) related dao tags with url not null (
         whose role should be is neither 'image' or 'thumbnail'):
        - viewer URLs
        - IIIF manifest URLs
        """
        urls = []
        for dv in self.digitized_versions:
            if dv.url:
                has_scheme = urlparse(dv.url).scheme
                if has_scheme:
                    urls.append((dv.url, dv.role or ""))
        # try to sort urls especially for the case of viewer links such as
        # http://www.archinoe.fr/ark:/77293/c2mzpfn3jmb4ootg/1,
        # http://www.archinoe.fr/ark:/77293/c2mzpfn3jmb4ootg/N
        return sorted(urls)

    @property
    def digitized_urls(self):
        """List of (url, role) related dao tags whose role is neither 'image' or 'thumbnail'
        or 'iiif_manifest'.
          - only viewer URLs
        """
        return [
            url
            for url, role in self.unprocessed_digitized_urls
            if role not in (IIIF_MANIFEST_ROLE,)
        ]

    def unprocessed_illustration_url(self):
        """List of one (illustration_url, role) of related dao tags with no
        empty illustration_url - 1 thumbnail URL

        """

        def compare_thumbnails(url1):
            ext = osp.splitext(url1)[-1].lower()
            return bool(ext in {".jpg", ".jpeg", ".png", ".jp2"})

        dvs = self._cw.execute(
            """Any U, R ORDERBY U WHERE D is DigitizedVersion,
               NOT D illustration_url NULL, D illustration_url U, D role R,
               X digitized_versions D, X eid %(eid)s""",
            {"eid": self.eid},
        )
        if not dvs:
            return None
        # take the first url with role 'thumbnail' or 'image',
        # sorted by not ending by {".jpg", ".jpeg", ".png", ".jp2"})
        # to be complient with the old imports.
        # Otherwise, take any non null illustration url
        images, others = [], []
        for illustration_url, role in dvs:
            if illustration_url:
                if role in ("thumbnail", "images"):
                    images.append(illustration_url)
                else:
                    others.append(illustration_url)
        if images:
            if len(images) > 1:
                images.sort(key=compare_thumbnails)
            return images[0]
        if others:
            return others[0]

    @property
    def thumbnail_dest(self):
        """Thumbnail target URL.

        The URI the user will be redirected to when clicking on the thumbnail.
        """
        illustration_url = self.unprocessed_illustration_url()
        if not illustration_url:
            return self.bounce_url
        if is_absolute_url(illustration_url):
            return illustration_url
        thumbnail_dest = self.related_service.thumbnail_dest if self.related_service else ""
        if thumbnail_dest:
            return thumbnail_dest.format(url=illustration_url)
        return self.bounce_url

    @property
    def illustration_url(self):
        """Illustration URL.

        The URL shown as the illustration's source. If there are related dao tags whose role
        is either 'image' or 'thumbnail', one of these tags URL will be used. If no such dao
        tag exists, either one of the other associated dao tags URL is returned (BnF) if there
        is any, or illustration_url is not set.
        If thumbnail_url is defined on the service, the URL will be formatted
        accordingly.
        """
        url = self.unprocessed_illustration_url()
        if url and is_absolute_url(url):
            return url
        service_code = self.related_service.code if self.related_service else None
        if not url:
            if service_code == "FRBNF":
                # special case for BnF
                urls = [d.url for d in self.digitized_versions if d.url]
                url = urls[0] if urls else None
                if not url or not is_absolute_url(url):
                    return None
            else:
                return None
        if not service_code:
            return None
        if url.startswith("/"):
            url = url[1:]
        if service_code == "FRAD085" and not url.isdigit():
            url = url.replace("\\", "/")
        if self.related_service and self.related_service.thumbnail_url:
            url = self.related_service.thumbnail_url.format(url=url)
        # relative URL (root or path unknown)
        if not is_absolute_url(url):
            return None
        return url

    @property
    def iiif_manifest_url(self):
        if not self.is_iiif_active:
            return None
        iiif_manfests = [
            url for url, role in self.unprocessed_digitized_urls if role == IIIF_MANIFEST_ROLE
        ]
        return iiif_manfests[0] if iiif_manfests else None

    @cachedproperty
    def iiif_manifest(self):
        return self.iiif_manifest_url

    @property
    def qualified_index_authorities(self):
        """indexes with role other than "index" come from tags other than <origination>"""
        return self._cw.execute(
            """Any A,T WHERE I authority A, I index F, I type T,
                F eid %(eid)s, I role "index", A quality True""",
            {"eid": self.eid},
        )

    def originators(self, qualified=None):
        """indexes with role other than "index" come from <origination>"""
        query = "DISTINCT Any A WHERE F eid %(e)s, I index F, NOT I role 'index', I authority A"
        if qualified is True:
            query += ", A quality True"
        if qualified is False:
            query += ", A quality False"
        return self._cw.execute(query, {"e": self.eid}).entities()

    @property
    def qualified_originators(self):
        """qualified indexes with role other than "index" come from <origination>"""
        return self.originators(qualified=True)

    @cachedproperty
    def top_children_count(self):
        raise NotImplementedError


@systemsource_entity
class Did(AnyEntity):
    __regid__ = "Did"
    fetch_attrs, cw_fetch_order = fetch_config(["unitid", "unittitle", "startyear", "stopyear"])

    def dc_title(self):
        return self.unittitle or self.unitid or "???"

    @property
    def period(self):
        period = []
        if self.startyear:
            period.append(str(self.startyear))
        if self.stopyear:
            period.append(str(self.stopyear))
        return " - ".join(period)


@systemsource_entity
class FAComponent(IndexableMixin, FindingAidBaseMixin, AnyEntity):
    __regid__ = "FAComponent"
    fetch_attrs, cw_fetch_order = fetch_config(["component_order", "stable_id"], pclass=None)
    rest_attr = "stable_id"

    def dc_title(self):
        return self.did[0].dc_title()

    @property
    def publisher(self):
        rset = self._cw.execute(
            "Any P WHERE X finding_aid FA, FA publisher P, X eid %(x)s", {"x": self.eid}
        )
        return rset[0][0]

    @property
    def related_service(self):
        return self.finding_aid[0].related_service

    @property
    def publisher_title(self):
        service = self.related_service
        if service:
            return self.related_service.dc_title()
        return self.publisher

    def children_components_stable_ids_and_labels(self):
        query = """Any FC, SI, LA WHERE
                X is FAComponent, X eid %(eid)s,
                FC parent_component X, FC stable_id SI,
                FC did D, D unittitle LA"""
        return self._cw.execute(query, {"eid": self.eid})

    @cachedproperty
    def top_children_count(self):
        return self._cw.execute(
            "Any COUNT(F) WHERE EXISTS(F parent_component X), X eid %(eid)s",
            {"eid": self.eid},
        )[0][0]


class FAHeader(AnyEntity):
    __regid__ = "FAHeader"

    def dc_title(self):
        if self.titlestmt:
            return self.titlestmt
        return "FAHeader #{}".format(self.eid)


@systemsource_entity
class FindingAid(IndexableMixin, FindingAidBaseMixin, AnyEntity):
    __regid__ = "FindingAid"
    fetch_attrs, cw_fetch_order = fetch_config(["stable_id", "did"])

    rest_attr = "stable_id"

    def dc_title(self):
        return self.fa_header[0].titleproper or self.did[0].dc_title()

    @property
    def finding_aid(self):
        """implement finding_aid to mimic FAComponent interface"""
        return [self]

    @property
    def service_code(self):
        if self.service and self.service[0].code:
            return self.service[0].code
        else:
            return self.eadid.split("_")[0]

    @property
    def related_service(self):
        if hasattr(self, "service") and self.service:
            return self.service[0]

    @property
    def services(self):
        return self.service

    @property
    def publisher_title(self):
        service = self.related_service
        if service:
            return self.related_service.dc_title()
        return self.publisher

    def all_authorities_eids(
        self,
    ):
        """
        all distinct authorities eids for FindingAid and related FAComponent
        """
        query = """DISTINCT Any A WITH A BEING (
            (DISTINCT Any A WHERE I authority A, I index F,
                F eid %(eid)s, F is FindingAid)
            UNION
            (DISTINCT Any A WHERE I authority A, I index FA,
                F eid %(eid)s, FA finding_aid F)
            )"""
        return {eid[0] for eid in self._cw.execute(query, {"eid": self.eid})}

    def top_components_stable_ids_and_labels(self):
        query = """Any FC, SI, LA WHERE
                F is FindingAid, F eid %(eid)s,
                F top_components FC, FC stable_id SI,
                FC did D, D unittitle LA"""
        return self._cw.execute(query, {"eid": self.eid})

    @cachedproperty
    def top_children_count(self):
        return self._cw.execute(
            "Any COUNT(F) WHERE EXISTS(X top_components F), X eid %(eid)s",
            {"eid": self.eid},
        )[0][0]


class DigitizedVersion(AnyEntity):
    __regid__ = "DigitizedVersion"
    fetch_attrs, cw_fetch_order = fetch_config(["url", "illustration_url", "role"])


class AbstractFAContextTreeAdapter(EntityAdapter):
    __abstract = True
    __regid__ = "IFAContextTree"

    def get_tree(self):
        raise NotImplementedError

    def build_parent(self, entity, children):
        return {
            "type": entity.cw_etype,
            "stableId": entity.stable_id,
            "title": entity.dc_title(),
            "children": children,
        }


class FindingAidFAContenxtTreeAdapter(AbstractFAContextTreeAdapter):
    __select__ = is_instance("FindingAid")

    def get_tree(self, limit=5):
        rset = self._cw.execute(
            "Any SI, DT ORDERBY CO "
            "WHERE X top_components C, X eid %(x)s, "
            "C stable_id SI, C did D, D unittitle DT, "
            "D unitid DI, C component_order CO",
            {"x": self.entity.eid, "l": f"LIMIT {limit}" if limit else ""},
        )
        children = [
            {"type": "FAComponent", "stableId": row[0], "title": row[1], "children": []}
            for row in rset
        ]

        return self.build_parent(self.entity, children)


class FAComponentFAContenxtTreeAdapter(AbstractFAContextTreeAdapter):
    __select__ = is_instance("FAComponent")

    def build_facomponent_tree_item(self, entity):
        rset = self._cw.execute(
            "Any SI, DT ORDERBY CO "
            "WHERE C parent_component X, X eid %(x)s, "
            "C stable_id SI, C did D, D unittitle DT, "
            "D unitid DI, C component_order CO",
            {"x": entity.eid},
        )
        children = [
            {"type": "FAComponent", "stableId": row[0], "title": row[1], "children": []}
            for row in rset
        ]
        return self.build_parent(entity, children)

    def get_tree(self):
        entity = self.entity
        children = [self.build_facomponent_tree_item(entity)]
        parent = entity.parent_component
        while parent:
            children = [self.build_parent(parent[0], children)]
            parent = parent[0].parent_component
        finding_aid = entity.finding_aid[0]
        finding_aid.complete()
        return self.build_parent(finding_aid, children)
