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

"""elasticsearch customization"""

from cubicweb import _
from cubicweb.predicates import is_instance
from cubicweb.entity import EntityAdapter

from cubicweb_elasticsearch import es
from cubicweb_elasticsearch.entities import Indexer
from cubicweb_elasticsearch.entities import IFullTextIndexSerializable

from cubicweb_francearchives import NOMINA_INDEXABLE_ETYPES
from cubicweb_francearchives.utils import remove_html_tags
from cubicweb_francearchives.entities.nomina import MARIAGE_DOCTYPE

SUGGEST_ETYPES = ("AgentAuthority", "LocationAuthority", "SubjectAuthority")


class DZFacetValues:
    dz = _("digitized")
    nondz = _("non-digitized")
    dz_noniiif = _("digitized-noniiif")
    dz_iiif = _("digitized-iiif")

    @classmethod
    def dzitems(cls):
        return {
            "digitized-iiif": cls.dz_iiif,
            "digitized-noniiif": cls.dz_noniiif,
        }

    @classmethod
    def index_values(cls, digitized, iiif):
        """
        :param Bool digitized: value is digitized or not
        :param Bool align: value is digitized in iiif or not iiif
        """
        if digitized:
            if iiif:
                return [cls.dz, cls.dz_iiif]
            return [cls.dz, cls.dz_noniiif]
        return cls.nondz


class PniaIndexer(Indexer):
    analyser_settings = {
        "analysis": {
            "filter": {
                "elision": {
                    "type": "elision",
                    "articles": ["l", "m", "t", "qu", "n", "s", "j", "d"],
                },
                "my_ascii_folding": {
                    "type": "asciifolding",
                    "preserve_original": True,
                },
                "french_stopwords": {
                    "type": "stop",
                    "stopwords": "_french_",
                },
            },
            "analyzer": {
                "default": {
                    "filter": ["my_ascii_folding", "lowercase", "elision"],
                    "tokenizer": "standard",
                },
                "french_stop_analyzer": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "my_ascii_folding", "elision", "french_stopwords"],
                },
            },
        }
    }

    # TODO - inspect which fields are used in facets to generate not_analyzed
    @property
    def mapping(self):
        mapping = {
            "properties": {
                # Default pnia data
                "creation_date": {"type": "date"},
                "modification_date": {"type": "date"},
                "eid": {"type": "keyword"},
                # implement implicity type behaviour of ES 2.x with
                # an explicit "estype" field
                "estype": {"type": "keyword"},
                # all types
                "cw_etype": {"type": "keyword"},
                "index_entries": {
                    "type": "nested",
                    "include_in_parent": True,
                    "properties": {
                        # Note: the index_entries.label is used in full_text search
                        # in this sense it should be "type":"text", it would enable
                        # authority highlighting in the results
                        # However, we do not know  for sure how it is used in Kibana
                        # therefore we leave it as "type":"keyword" for now
                        "label": {
                            "type": "keyword",
                            "copy_to": ["alltext"],
                            "fields": {"raw": {"type": "text"}},
                        },
                        "type": {"type": "keyword"},
                        "authority": {"type": "keyword"},
                        "authtype": {"type": "keyword"},
                        "authfilenumber": {"type": "keyword"},
                    },
                },
                "title": {"type": "text"},
                "title_en": {"type": "text"},
                "title_es": {"type": "text"},
                "title_de": {"type": "text"},
                "alltext": {"type": "text"},
                "alltext_en": {"type": "text"},
                "alltext_de": {"type": "text"},
                "alltext_es": {"type": "text"},
                "escategory": {"type": "keyword"},
                "dates": {"type": "integer_range"},
                "sortdate": {"type": "date", "format": "yyyy-MM-dd"},
                "service": {
                    "properties": {
                        "eid": {"type": "keyword"},
                        "code": {"type": "keyword"},
                        "level": {"type": "keyword"},
                        "title": {"type": "keyword"},
                    }
                },
                "ancestors": {"type": "keyword"},
                "is_published": {"type": "boolean"},  # 0 draft, 1 published
                # FindingAid, FAComponent
                "publisher": {"type": "keyword", "copy_to": "alltext"},
                "digitized": {"type": "boolean"},  # TODO remove on the next reindexation
                "digitized_all": {"type": "keyword"},
                # e.g DZFacetValues values
                "originators": {
                    "type": "keyword",
                    "copy_to": ["alltext"],
                    "fields": {"text": {"type": "text"}},
                },
                "acquisition_info": {
                    "type": "text",
                    "copy_to": "alltext",
                },
                "eadid": {"type": "text", "copy_to": "alltext"},
                "scopecontent": {
                    "type": "text",
                    "copy_to": "alltext",
                },
                "stable_id": {"type": "keyword"},
                "fa_stable_id": {"type": "keyword"},
                "did": {
                    "properties": {
                        "unitid": {
                            "type": "text",
                        },
                        "unittitle": {
                            "type": "text",
                        },
                    }
                },
                "startyear": {"type": "date", "format": "yyyy"},
                "stopyear": {"type": "date", "format": "yyyy"},
                # Circular
                "status": {"type": "keyword", "copy_to": "alltext"},
                "business_field": {"type": "keyword", "copy_to": "alltext"},
                "archival_field": {"type": "keyword", "copy_to": "alltext"},
                "document_type": {"type": "keyword", "copy_to": "alltext"},
                "historical_context": {"type": "keyword", "copy_to": "alltext"},
                "action": {"type": "keyword", "copy_to": "alltext"},
                # Service
                "level": {"type": "keyword", "copy_to": "alltext"},
                "is_partner": {"type": "boolean"},
                "sort_name": {"type": "keyword"},
                # AuthiorityRecord
                "record_id": {"type": "keyword"},
                # pdf content length may be > then 1000000 maximum allowed to be
                # analyzed for highlighting.
                "text": {  # XXX à ajouter dans la liste des champs de requêtes
                    "type": "text",
                    "term_vector": "with_positions_offsets",
                },
            },
        }
        return mapping

    @property
    def index_name(self):
        return "%s_all" % self._cw.vreg.config["index-name"]

    @property
    def settings(self):
        settings = Indexer.settings.copy()
        settings.update(
            {
                "settings": {"index": self.analyser_settings},
                "mappings": self.mapping,
            }
        )
        return settings

    def es_delete(self, entity):
        es_cnx = self.get_connection()
        if entity.cw_etype not in ("AuthorityRecord",):
            super(PniaIndexer, self).es_delete(entity)
        else:
            if es_cnx is None or not self.index_name:
                self.error("no connection to ES (not configured) skip ES deletion")
                return
            # AuthorityRecord serializable.es_id is based on record_id attribute
            # which is not accessible after entity deletion
            es_cnx.delete_by_query(
                index=self.index_name,
                body={"query": {"match": {"eid": entity.eid}}},
            )


class PniaSuggestIndexer(Indexer):
    """indexer for autocomplete search"""

    __regid__ = "suggest-indexer"
    adapter = "ISuggestIndexSerializable"

    indexable_etypes = SUGGEST_ETYPES
    analyser_settings = {
        "analysis": {
            "filter": {
                "ngram_filter": {"type": "edge_ngram", "min_gram": 1, "max_gram": 20},
                "my_ascii_folding": {"preserve_original": True, "type": "asciifolding"},
                "french_snowball": {"type": "snowball", "language": "French"},
            },
            "analyzer": {
                "search_analyzer": {
                    "tokenizer": "standard",
                    "filter": ["lowercase", "asciifolding"],
                },
                "autocomplete": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "my_ascii_folding", "ngram_filter"],
                },
            },
            "normalizer": {
                "my_normalizer": {
                    "type": "custom",
                    "char_filter": [],
                    "filter": ["lowercase", "asciifolding"],
                },
                "uppercase_norm": {
                    "type": "custom",
                    "char_filter": [],
                    "filter": ["uppercase", "asciifolding"],
                },
            },
        },
    }

    mapping_properties = {
        "properties": {
            "text": {
                "search_analyzer": "search_analyzer",
                "analyzer": "autocomplete",
                "type": "text",
                "fields": {"raw": {"type": "keyword", "normalizer": "my_normalizer"}},
            },
            "label": {"type": "search_as_you_type", "max_shingle_size": 3},
            "quality": {"type": "boolean"},
            "letter": {"type": "keyword", "normalizer": "uppercase_norm"},
            "same_as": {
                "type": "nested",
                "properties": {
                    "label": {"type": "text"},
                    "uri": {"type": "keyword"},
                    "source": {"type": "keyword"},
                },
            },
            "same_as_count": {"type": "integer"},
        }
    }

    @property
    def index_name(self):
        return "{}_suggest".format(self._cw.vreg.config["index-name"])

    @property
    def settings(self):
        return {
            "mappings": self.mapping_properties.copy(),
            "settings": {"index": self.analyser_settings},
        }


class PniaIFullTextIndexSerializable(IFullTextIndexSerializable):
    main_attributes = ("cw_etype", "eid")

    def process_attributes(self):
        data = {}
        eschema = self.entity.e_schema
        for attr in self.fulltext_indexable_attributes:
            value = getattr(self.entity, attr)
            if value and eschema.has_metadata(attr, "format"):
                value = remove_html_tags(value)
            data[attr] = value
        data["estype"] = self.entity.cw_etype
        return data


class TranslatableIndexSerializableMixin(object):
    def add_translations(self, complete=True, **kwargs):
        data = {}
        translations = self.entity.reverse_translation_of
        if not translations:
            return data
        eschema = translations[0].e_schema
        indexables = [attr.type for attr in eschema.indexable_attributes()]
        for lang, values in self.entity.translations(**kwargs).items():
            content_fields = []
            for attribute, value in values.items():
                if attribute not in indexables:
                    continue
                if not value or not value.strip():
                    continue
                if eschema.has_metadata(attribute, "format"):
                    value = remove_html_tags(value)
                if attribute == "title":
                    data[f"title_{lang}"] = value
                else:
                    content_fields.append(value)
            data[f"alltext_{lang}"] = "\n".join(content_fields)
        return data


class ISuggestIndexSerializable(EntityAdapter):
    __regid__ = "ISuggestIndexSerializable"
    __select__ = is_instance(*SUGGEST_ETYPES)
    etype2type = {
        "LocationAuthority": _("geogname"),
        "SubjectAuthority": _("subject"),
        "AgentAuthority": _("agent"),
    }
    etype2urlsegment = {
        "LocationAuthority": "location",
        "SubjectAuthority": "subject",
        "AgentAuthority": "agent",
    }

    @property
    def es_id(self):
        return self.entity.eid

    def get_related_docs(self, published=False):
        for key, queries in self.related_docs_queries(published=published).items():
            yield self._cw.execute(
                """Any F WITH F BEING ({queries})""".format(queries=" UNION ".join(queries)),
                {"eid": self.entity.eid},
            )

    def related_docs_queries(self, published=False):
        """Get queries to compute the number of related
        documents.

        :param bool published: whether published documents should be included

        :returns: list of queries
        :rtype: list
        """
        if published:
            state = ", F in_state S, S name '{}'".format("wfs_cmsobject_published")
        else:
            state = ""
        fa_queries = [
            """(DISTINCT Any F WHERE EXISTS(A authority X, A index F),
            X eid %(eid)s, F is FindingAid{state})""",
            """(DISTINCT Any FA WHERE EXISTS(A authority X, A index FA, X eid %(eid)s),
            FA finding_aid F{state})""",
        ]
        docs_queries = [
            """(DISTINCT Any F WHERE EXISTS(F? related_authority X),
            X eid %(eid)s{state})""",
        ]
        if self.entity.cw_etype == "SubjectAuthority":
            docs_queries.append(
                """(DISTINCT Any F WHERE
                              EXISTS (F business_field B, X same_as B)
                              OR EXISTS(F historical_context H, X same_as H)
                              OR EXISTS(F document_type D, X same_as D)
                              OR EXISTS(F action A, X same_as A),
                              X eid %(eid)s{state})"""
            )
        return {
            "archives": [query.format(state=state) for query in fa_queries],
            "siteref": [query.format(state=state) for query in docs_queries],
        }

    def related_docs_counts(self, published=False):
        """compute the number of related FindingAids and FAComponents:
        - total number if published == False
        - number of published entities if published == True
        flag groupped auhtorities

        compute the number of all related :
        - FindingAids
        - FAComponents
        - Circulars
        - Entities related by `related_authority`
        """
        res = {}
        for key, queries in self.related_docs_queries(published=published).items():
            res[key] = self._cw.execute(
                """Any COUNT(F) WITH F BEING ({queries})""".format(queries=" UNION ".join(queries)),
                {"eid": self.entity.eid},
            )[0][0]
        return res

    def related_docs(self, published=False):
        counts = self.related_docs_counts(published=published)
        return sum(counts.values())

    @property
    def grouped(self):
        query = """
            Any COUNT(X1) WHERE X eid {eid}, X grouped_with X1"""
        return bool(self._cw.execute(query.format(eid=self.entity.eid))[0][0])

    def serialize(self, complete=True, published=False):
        entity = self.entity
        if complete:
            entity.complete()
        etype = entity.cw_etype
        counts = self.related_docs_counts(published=published)
        same_as_links = entity.same_as_links
        external_uris = same_as_links.get("ExternalUri", [])
        same_as_data = [
            {
                "label": ext_uri.label,
                "uri": ext_uri.uri,
                "source": ext_uri.source,
            }
            for ext_uri in external_uris
        ]
        return {
            "cw_etype": etype,
            "eid": entity.eid,
            "text": entity.label,
            # do not use type from Geogname, Subject, AgentName
            # because user could have group authorities so
            # one authority could have 2 AgentName with two different
            # type
            "type": self.etype2type[etype],
            "label": entity.label,
            "urlpath": "{}/{}".format(self.etype2urlsegment[etype], entity.eid),
            "count": sum(counts.values()),
            "archives": counts["archives"],
            "siteres": counts["siteref"],
            "grouped": self.grouped,
            "quality": entity.quality,
            "letter": entity.es_start_letter,
            "same_as": same_as_data,
            "same_as_count": len(same_as_data),
        }


class PniaNominaIndexer(Indexer):
    """indexer for search in Nomina"""

    __regid__ = "nomina-indexer"
    adapter = "INominaIndexSerializable"

    indexable_etypes = NOMINA_INDEXABLE_ETYPES
    analyser_settings = {
        "analysis": {
            "filter": {
                "elision": {
                    "type": "elision",
                    "articles": ["l", "m", "t", "qu", "n", "s", "j", "d"],
                },
                "my_ascii_folding": {
                    "type": "asciifolding",
                    "preserve_original": True,
                },
            },
            "analyzer": {
                "default": {
                    "filter": ["my_ascii_folding", "lowercase", "elision"],
                    "tokenizer": "standard",
                }
            },
            "normalizer": {
                "my_normalizer": {
                    "type": "custom",
                    "char_filter": [],
                    "filter": ["lowercase", "my_ascii_folding"],
                },
            },
        }
    }

    mapping_properties = {
        "properties": {
            "act_date": {"type": "text"},
            "act_number": {"type": "keyword"},
            "act_type": {"type": "keyword"},
            "alltext": {"type": "text"},
            "additional_info": {"type": "text", "copy_to": "alltext"},
            "age": {"type": "text"},
            "agent": {"type": "keyword"},  # related agent eid
            "birth_date": {"type": "text"},
            "birth_dates": {"type": "integer_range"},
            "birth_place": {"type": "text", "copy_to": "alltext"},  # socface
            "birth_commune": {"type": "text"},
            "birth_department": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "birth_country": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "civil_status": {"type": "keyword", "copy_to": "alltext"},
            "cote": {"type": "keyword", "copy_to": "alltext"},
            # "creation_date": {"type": "date"},
            "death_date": {"type": "text"},
            "death_dates": {"type": "integer_range"},
            "death_commune": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "death_department": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "death_country": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "doc_page_line_id": {"type": "keyword"},  # socface
            "event_date": {"type": "text"},
            "event_dates": {"type": "integer_range"},
            "event_commune": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "event_department": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "event_country": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "event_year": {"type": "integer"},  # todo : remove it
            "id_arkindex": {"type": "keyword"},  # socface
            "instruction": {"type": "keyword"},
            "forenames": {
                "type": "text",
                "copy_to": "alltext",
            },
            "gender": {"type": "keyword"},
            "employer": {"type": "text", "copy_to": "alltext"},  # socface
            "historial_index": {
                "type": "text",
                "copy_to": "alltext",
                "fields": {"text": {"type": "text"}},
            },  # a list of keywords
            "household_role": {"type": "text", "copy_to": "alltext"},  # or keyword ?
            "household_id": {"type": "keyword"},  # socface
            "mention_mpf": {"type": "keyword", "copy_to": "alltext"},
            "modification_date": {"type": "date"},
            "names": {
                "type": "text",
                "copy_to": "alltext",
            },
            "nationality": {"type": "keyword", "copy_to": "alltext"},
            "notice_id": {
                "type": "keyword"
            },  # only exists for csv imported data - + socface arkindex (?)
            "oai_id": {
                "type": "keyword"
            },  # only exists for csv imported data - + socface arkindex (?)
            "occupations": {"type": "text", "copy_to": "alltext"},
            "occupations_index": {
                "type": "keyword",
                "copy_to": "alltext",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "recruitment_date": {"type": "text"},
            "recruitment_dates": {"type": "integer_range"},
            "recruitment_commune": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},
            },  # transorm in other place ?
            "recruitment_department": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},
            },
            "recruitment_country": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "residence_commune": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "residence_department": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "residence_country": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "service": {"type": "keyword"},
            "source_url": {"type": "keyword"},
            "stable_id": {"type": "keyword"},
            "subject": {
                "type": "keyword",
                "copy_to": "alltext",
                "fields": {"text": {"type": "text"}},  # todo keep only text for autocomplete ?
            },
            "teklia_url": {"type": "keyword"},  # socface
            "title": {"type": "text"},
        }
    }

    @property
    def index_name(self):
        return self._cw.vreg.config["nomina-index-name"]

    @property
    def settings(self):
        return {
            "mappings": self.mapping_properties.copy(),
            "settings": {"index": self.analyser_settings},
        }

    def es_delete(self, entity):
        es_cnx = self.get_connection()
        if es_cnx is None or not self.index_name:
            self.error("no connection to ES (not configured) skip ES deletion")
            return
        if entity.act_type not in MARIAGE_DOCTYPE:
            es_cnx.delete_by_query(
                index=self.index_name,
                body={"query": {"match": {"stable_id": entity.stable_id}}},
            )
        else:
            # in case of marge a notice with a proper stable_id is generated for each member
            es_cnx.delete_by_query(
                index=self.index_name,
                body={"query": {"match": {"household_id": entity.household_id}}},
            )

    @property
    def es_id(self):
        return self.entity.stable_id

    def es_index(self, entity, params=None):
        """Override to handle list of documents returned by serialize()

        For marriage acts with multiple spouses, serialize() returns multiple documents.
        Each document is indexed separately with its own stable_id.
        """
        es_cnx = self.get_connection()
        if es_cnx is None or not self.index_name:
            self.error("no connection to ES (not configured) skip ES indexing")
            return
        serializable = entity.cw_adapt_to(self.adapter)
        json_data = serializable.serialize()
        if not json_data:
            return
        # Handle list of documents (for marriage acts with multiple spouses)
        for doc in json_data:
            es_cnx.index(
                index=self.index_name,
                id=doc["stable_id"],
                body=doc,
                params=params,
            )


def registration_callback(vreg):
    global ALL_INDEXABLE_ETYPES
    vreg.register_all(list(globals().values()), __name__)
    vreg.unregister(Indexer)
    vreg.unregister(IFullTextIndexSerializable)
    ALL_INDEXABLE_ETYPES = es.indexable_types(vreg.schema) + ["FindingAid", "FAComponent"]
