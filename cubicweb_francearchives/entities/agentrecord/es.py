# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2026
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
# data to be ensured and, more generally, to use and operate it in
# same conditions as regards security.
#
# The fact that you are presently reading this means that you have hadredis
# knowledge of the CeCILL-C license and that you accept its terms.
#
"""PniaAgentReferenceIndexers classes"""
from elasticsearch_dsl import Search, query as dsl_query, Q
from typing import List, Optional

from cubicweb_elasticsearch.entities import Indexer
from cubicweb_francearchives import AGENTS_REFERENCE_INDEXABLE_ETYPES


class PniaAgentReferenceIndexer(Indexer):
    """indexer for search in Nomina"""

    __regid__ = "agents-reference-indexer"
    adapter = "IAgentsReferenceIndexSerializable"

    indexable_etypes = AGENTS_REFERENCE_INDEXABLE_ETYPES
    analyser_settings = {
        "analysis": {
            "filter": {
                "ngram_filter": {"type": "edge_ngram", "min_gram": 1, "max_gram": 20},
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
            },
        }
    }

    mapping_properties = {
        "properties": {
            # Identity fields
            "alltext": {"type": "text", "analyzer": "default"},
            "allmetadata": {"type": "text"},
            "creation_date": {"type": "date"},
            "created_by": {"type": "keyword"},
            "eid": {"type": "keyword"},
            "is_published": {"type": "boolean"},
            "text": {
                "analyzer": "autocomplete",
                "type": "text",
                "copy_to": "alltext",
                "fields": {"raw": {"type": "keyword", "normalizer": "my_normalizer"}},
            },
            "modified_by": {"type": "keyword"},
            "modification_date": {"type": "date"},
            "name": {
                "type": "text",
                "fields": {"raw": {"type": "keyword", "normalizer": "my_normalizer"}},
                "copy_to": "alltext",
            },
            "other_names": {
                "type": "text",
                "copy_to": "alltext",
            },
            "record_id": {"type": "keyword"},
            "type": {"type": "keyword"},
            # Identifiers
            "ark": {"type": "keyword"},
            # Gender & Legal Status
            "gender": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},
            },
            "legal_status": {
                "type": "text",
                "copy_to": "alltext",
                "fields": {"raw": {"type": "keyword"}},
            },
            # Dates - Person (birth/death)
            "birth_date": {"type": "text"},
            "birth_dates": {"type": "integer_range"},
            "death_date": {"type": "text"},
            "death_dates": {"type": "integer_range"},
            # Dates - Corporate Body (start/stop)
            "start_date": {"type": "text"},
            "start_dates": {"type": "integer_range"},
            "stop_date": {"type": "text"},
            "stop_dates": {"type": "integer_range"},
            # Places - Birth
            "birth_place": {
                "type": "text",
                "copy_to": "alltext",
                "fields": {"raw": {"type": "keyword"}},
            },
            # Places - Death
            "death_place": {
                "type": "text",
                "copy_to": "alltext",
                "fields": {"raw": {"type": "keyword"}},
            },
            # Places - Activity
            "activity_places": {
                "type": "text",
                "copy_to": "alltext",
                "fields": {"raw": {"type": "keyword"}},
            },
            # Occupations & Functions
            "occupations": {
                "type": "text",
                "copy_to": "alltext",
            },
            "occupations_index": {
                "type": "keyword",
                "fields": {"text": {"type": "text"}},
            },
            "functions": {
                "type": "text",
                "copy_to": "alltext",
            },
            # Relations
            "relations": {
                "type": "text",
                "copy_to": "alltext",
            },
            "relations_by_type": {
                "type": "nested",
                "properties": {
                    "type": {"type": "keyword"},
                    "count": {"type": "integer"},
                    "terms": {"type": "text"},
                },
            },
            "relations_count": {"type": "integer"},
            # Biography
            "bioghist": {
                "type": "text",
                "copy_to": "alltext",
            },
            # Sources & External References
            "sources": {
                "type": "nested",
                "properties": {
                    "label": {"type": "text"},
                    "uri": {"type": "keyword"},
                    "source": {"type": "keyword"},
                },
            },
            "sources_count": {"type": "integer"},
            "source_authority_records": {
                "properties": {
                    "label": {"type": "integer"},
                    "uri": {"type": "keyword"},
                },
            },
            # Authority Links
            "authority_records_links": {
                "type": "nested",
                "properties": {
                    "record_id": {"type": "keyword"},
                    "label": {"type": "text"},
                    "service": {"type": "keyword"},
                    "url": {"type": "keyword"},
                },
            },
            "same_as_authorities": {
                "type": "nested",
                "properties": {
                    "eid": {"type": "keyword"},
                    "label": {"type": "text"},
                    "ark": {"type": "keyword"},
                },
            },
            # Administrative Status
            "creation_mode": {"type": "keyword"},
            "publication_status": {"type": "keyword"},
            "maintenance_status": {"type": "keyword"},
        }
    }

    @property
    def index_name(self):
        return self._cw.vreg.config["agents-reference-index-name"]

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
        # AgentRecord serializable.es_id is based on record_id attribute
        # which is not accessible after entity deletion
        es_cnx.delete_by_query(
            index=self.index_name,
            body={"query": {"match": {"eid": entity.eid}}},
        )

    def get_agentrecords_by_query_es(
        self, query: str, search_by_id: bool = False, source_fields: Optional[List[str]] = None
    ) -> dict:
        """Retrieves AgentRecords data based on a query string.

        Parameters:
        req (CubicWebPyramidRequest'): The CW request object
        query (str): The search query used to filter on authorities label or eid.

        Returns:
        result: a list of matching authorities"""
        es_cnx = self.get_connection()
        if not es_cnx:
            self.error("no connection to ES (not configured)")
            return {"hits": [], "total": 0}
        search = Search(index=self.index_name)
        if search_by_id:
            must = [{"match": {"record_id": query}}]
        else:
            must = [{"match": {"text": {"query": query, "operator": "and"}}}]
        search.query = dsl_query.Bool(must=must)
        if source_fields:
            search = search.source(includes=source_fields)
        search = search.sort({"_score": {"order": "desc"}})
        try:
            response = search.execute()
        except Exception as e:
            self.error(f"Error while retrieving agentRecords '{query}': {e}")
            return {"hits": [], "total": 0}
        return {
            "hits": [hit.to_dict() for hit in response.hits],
            "total": (
                response.hits.total.value
                if hasattr(response.hits.total, "value")
                else response.hits.total
            ),
        }

    def count_documents_by_field(
        self, field_name: str, field_value: str, match_phrase: bool = False
    ) -> int:
        """
        Count documents in PniaAgentReferenceIndex having a specific field value.

        :param str field_name: The field name to search
             on (e.g., "functions", "occupations", "type")
        :param str field_value: The value to search for (e.g., "toto")
        :param bool match_phrase: If True, use match_phrase query instead of term query
        :return: Number of documents with this field value
        :rtype: int
        """
        es_cnx = self.get_connection()
        if es_cnx is None or not self.index_name:
            self.error("no connection to ES (not configured)")
            return 0

        search = Search(using=es_cnx, index=self.index_name)
        # Use term query for keyword fields, match_phrase for text fields
        if match_phrase:
            query = Q("match_phrase", **{field_name: field_value})
        else:
            query = Q("term", **{field_name: field_value})
        try:
            search = search.query(query)
        except Exception as e:
            self.error(f"Error counting documents by field '{field_name}': {e}")
            return 0
        return search.count()

    def search_documents_by_field(
        self,
        field_name: str,
        field_value: str,
        source_fields: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0,
        match_phrase: bool = False,
    ) -> dict:
        """
        Search documents in PniaAgentReferenceIndex having a specific field value.
        Single query returns both total count and hits.

        :param str field_name: The field name to search
               on (e.g., "functions", "occupations", "type")
        :param str field_value: The value to search for (e.g., "toto")
        :param list source_fields: List of fields to retrieve (default: all fields)
        :param int limit: Maximum number of results to return
        :param int offset: Results offset for pagination
        :param bool match_phrase: If True, use match_phrase query instead of term query
        :return: Dictionary with hits and total count
        :rtype: dict
        """
        es_cnx = self.get_connection()
        if es_cnx is None or not self.index_name:
            self.error("no connection to ES (not configured)")
            return {"hits": [], "total": 0}

        search = Search(using=es_cnx, index=self.index_name)
        # Use term query for keyword fields, match_phrase for text fields
        if match_phrase:
            query = Q("match_phrase", **{field_name: field_value})
        else:
            query = Q("term", **{field_name: field_value})
        try:
            search = search.query(query)
        except Exception as e:
            self.error(f"Error searching documents by field '{field_name}': {e}")
            return {"hits": [], "total": 0}

        if source_fields:
            search = search.source(includes=source_fields)

        # Pagination
        search = search[offset : offset + limit]

        # Execute search - single query returns both hits and total count
        response = search.execute()

        return {
            "hits": [hit.to_dict() for hit in response.hits],
            "total": (
                response.hits.total.value
                if hasattr(response.hits.total, "value")
                else response.hits.total
            ),
        }

    def count_documents_by_field_terms(
        self, field_name: str, min_count: int = 1, size: int = 100
    ) -> dict:
        """
        Get count of documents grouped by each unique value of a field.
        Uses Elasticsearch terms aggregation.

        :param str field_name: The field name to aggregate
               on (e.g., "functions", "occupations", "type")
        :param int min_count: Minimum count for a term to be included (default: 1)
        :param int size: Maximum number of buckets to return (default: 100)
        :return: Dictionary with field values as keys and document counts as values
        :rtype: dict
        """
        es_cnx = self.get_connection()
        if es_cnx is None or not self.index_name:
            self.error("no connection to ES (not configured)")
            return {}

        search = Search(using=es_cnx, index=self.index_name)
        search = search[:0]
        # Add terms aggregation
        search.aggs.bucket(
            field_name,
            "terms",
            field=field_name,
            min_doc_count=min_count,
            size=size,
        )
        try:
            response = search.execute()
        except Exception as e:
            self.error(f"Error counting documents by field terms '{field_name}': {e}")
            return {}

        result = {}
        if hasattr(response.aggregations, field_name):
            agg = response.aggregations[field_name]
            for bucket in agg.buckets:
                result[bucket.key] = bucket.doc_count

        return result


def registration_callback(vreg):
    vreg.register_all(list(globals().values()), __name__)
    vreg.unregister(Indexer)
