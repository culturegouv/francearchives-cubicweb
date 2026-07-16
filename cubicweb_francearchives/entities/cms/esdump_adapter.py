from itertools import chain

from cubicweb.predicates import is_instance

from cubicweb_elasticsearch.entities import IFullTextIndexSerializable
from cubicweb_francearchives import IIIF_MANIFEST_ROLE
from cubicweb_francearchives.dataimport import (
    strip_html,
    pdf,
    unique_indices,
    normalize_entry,
    INDEX_AUTHORITY_TYPE_MAP,
)
from cubicweb_francearchives.dataimport.ead import dates_for_es_doc
from cubicweb_francearchives.entities import ETYPE_CATEGORIES
from cubicweb_francearchives.entities.es import DZFacetValues


def clean_html(data):
    if data:
        return strip_html(data).replace("\n", "")
    return data


class IDumpFTIAdapterMixin(IFullTextIndexSerializable):
    __abstract__ = True

    @property
    def es_id(self):
        return self.entity.stable_id

    @property
    def get_digitized(self):
        return self._cw.execute(
            "Any V, R WHERE X eid %(eid)s, X digitized_versions V, V role R",
            {"eid": self.entity.eid},
        )

    @property
    def index_entries(self):
        indexes = unique_indices(
            [
                {
                    "authority": e.autheid,
                    "label": e.label,
                    "authfilenumber": e.authfilenumber,
                    "type": e.type,
                    "normalized": normalize_entry(e.label),
                    "authtype": INDEX_AUTHORITY_TYPE_MAP[e.type][1],
                }
                for e in chain(
                    self.entity.esdump_agents,
                    self.entity.esdump_locations,
                    self.entity.esdump_subjects,
                )
            ]
        )
        for index in indexes:
            index.pop("normalized")
        return indexes

    def serialize(self, complete=True):
        """Build data from the existing EsDocument. Following data are to be reindexed:
        - Since the last index redesign, should be in esdoc: alltext, dates must
        - Since the last index redesign, should not be in esdoc
          - author, digitized_versions, fatype, name, publisher, year
          - did.note, did.abstract, description, faheader.titleproper must not be in esdoc
            but in alltext
        """
        es_doc = None
        if self.entity.esdump_esdoc:
            es_doc = self.entity.esdump_esdoc.doc
        if not es_doc:
            return self.entity.cw_adapt_to("IFullTextIndexSerializable").serialize()
        if "stable_id" not in es_doc or "did" not in es_doc:
            # something is wrong with ESDocument
            return self.entity.cw_adapt_to("IFullTextIndexSerializable")
        es_doc["creation_date"] = self.entity.creation_date.isoformat()
        # replace did
        did = es_doc.pop("did")
        es_doc["did"] = {"unittitle": did["unittitle"], "unitid": did["unitid"]}
        # replace service
        service = self.entity.esdump_service
        if service:
            es_doc["service"] = {
                "eid": service.eid,
                "level": service.level,
                "code": service.code.upper() if service.code else None,
                "title": service.short_name or service.name2 or service.name or service.code,
            }
        if "dates" not in es_doc:
            # all dates should be in es_doc by now
            did = self.entity.esdump_did
            es_doc.update(dates_for_es_doc({"startyear": did.startyear, "stopyear": did.stopyear}))
        if "digitized_all" not in es_doc:
            digitized = self.get_digitized
            iiif = (
                bool([d for d, role in digitized if role == IIIF_MANIFEST_ROLE])
                if digitized
                else False
            )
            es_doc["digitized_all"] = DZFacetValues.index_values(
                digitized=bool(digitized), iiif=iiif
            )
        # replace indexes
        es_doc["index_entries"] = self.index_entries or None
        es_doc = {key: value for key, value in es_doc.items() if value is not None}
        return es_doc

    def serialize_from_db(self, complete=True):
        """Build data from PostgreSQL
        WARNING: This function has not yet been tested because of budget issues
        It is not used anywhere for now.
        We left because it might be useful in the future to reindex IR data
        from the database fields and not from the ESDocument which is created
        at import.
        """
        es_doc = {}
        entity = self.entity
        if self.entity.cw_etype == "FindingAid":
            es_doc = {
                "eadid": entity.eadid,
                "fa_stable_id": entity.stable_id,
            }
            pdf_file = self.entity.esdump_pdf
            if pdf_file:
                try:
                    # write a test
                    infos = pdf.pdf_infos(pdf_file.data.getvalue())
                    es_doc["text"] = infos["text"] or None
                except Exception:
                    self.error("Could not retrieve data from %s:", pdf_file)
        else:
            findingaid = self.entity.esdump_findingaid
            es_doc = {
                "fa_stable_id": findingaid.stable_id,
            }
        did = self.entity.esdump_did
        alltext = [entity.description, entity.esdump_faheader.titleproper, did.abstract, did.note]
        digitized = bool(self.entity.esdump_digitized_versions)
        iiif = bool(self.entity.esdump_iiif_manifest) if digitized else False
        es_doc.update(
            {
                "acquisition_info": clean_html(entity.acquisition_info) or None,
                "alltext": " ".join(clean_html(e) for e in alltext if e) or None,
                "eid": entity.eid,
                "cw_etype": entity.cw_etype,
                "creation_date": entity.creation_date.isoformat(),
                "escategory": self.escategory,
                "did": {"unitid": did.unitid, "unittitle": did.unittitle},
                "digitized": bool(self.entity.esdump_digitized_versions),
                "digitized_all": DZFacetValues.index_values(digitized=digitized, iiif=iiif),
                "index_entries": self.index_entries or None,
                "originators": [e.label for e in self.entity.esdump_originators] or None,
                "scopecontent": clean_html(entity.scopecontent) or None,
                "stable_id": entity.stable_id,
            }
        )
        es_doc.update(dates_for_es_doc({"startyear": did.startyear, "stopyear": did.stopyear}))
        # add service
        service = self.entity.esdump_service
        if service:
            es_doc["service"] = {
                "eid": service.eid,
                "level": service.level,
                "code": service.code.upper() if service.code else None,
                "title": service.short_name or service.name2 or service.name or service.code,
            }
        # replace indexes
        return {key: value for key, value in es_doc.items() if value is not None}


class FindingAidIDmupFTIAdapter(IDumpFTIAdapterMixin):
    __regid__ = "IDumpFullTextIndexSerializable"
    __select__ = IDumpFTIAdapterMixin.__select__ & is_instance("FindingAid")
    escategory = ETYPE_CATEGORIES["FindingAid"]


class FAComponentIDumpFTIAdapter(IDumpFTIAdapterMixin):
    __regid__ = "IDumpFullTextIndexSerializable"
    __select__ = IDumpFTIAdapterMixin.__select__ & is_instance("FAComponent")
    escategory = ETYPE_CATEGORIES["FAComponent"]


def registration_callback(vreg):
    vreg.register_all(list(globals().values()), __name__)
