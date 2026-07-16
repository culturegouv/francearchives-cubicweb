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

"""small es utility functions"""
import logging

from elasticsearch_dsl import Search, query as dsl_query

from cubicweb_elasticsearch.es import get_connection

from cubicweb_francearchives.dataimport import es_bulk_index

logging.getLogger("elasticsearch").level = logging.ERROR


def documents_number_for_service(req, service_eid, cw_etype, index_name=None):
    es = get_connection(req.vreg.config)
    if not es or not es.ping():
        req.error("no elastisearch connection available")
        return
    if not index_name:
        index_name = f"{req.vreg.config['index-name']}_all"
    must = [{"term": {"service": service_eid}}, {"term": {"cw_etype": cw_etype}}]
    search = Search(index=index_name)
    search.query = dsl_query.Bool(must=must)
    response = search.count()
    if response and response.hits:
        return response.hits.total.value
    return 0


def nominarecords_number_for_service(req, service_eid):
    es = get_connection(req.vreg.config)
    if not es or not es.ping():
        req.error("no elastisearch connection available")
        return
    index_name = req.vreg.config["nomina-index-name"]
    search = Search(index=index_name)
    must = [{"term": {"service": service_eid}}]
    search.query = dsl_query.Bool(must=must)
    response = search.execute()
    if response and response.hits:
        return response.hits.total.value
    return 0


def delete_autority_from_es(cnx, eids, log=None):
    """Delete authorities from all es indexes"""

    def docs_to_delete(es, eids, index_name):
        if log:
            log.info("es [%s]: deleting %s", index_name, eids)
        else:
            print(f"es [{index_name}]: deleting {eids}")
        for eid in eids:
            yield {
                "_op_type": "delete",
                "_index": index_name,
                "_id": eid,
            }

    config = cnx.vreg.config
    indexes = [f"{config['index-name']}_suggest"]
    if config.get("published-index-name"):  # only in cms
        indexes.append(f"{config['published-index-name']}_suggest")
    if config["enable-kibana-indexes"]:
        indexes.append(config["kibana-authorities-index-name"])
    for index_name in indexes:
        es = get_connection(config)
        if not es or not es.ping:
            log.error("-> no es connection found: abort autorities deletion")
            return
        es_docs = docs_to_delete(es, eids, index_name)
        es_bulk_index(es, es_docs, raise_on_error=False)


def update_index_mapping(cnx, index_name, mapping, log=None):
    if not log:
        log = logging.getLogger("update_index_mapping")
    es = get_connection(cnx.vreg.config)
    if not es or not es.ping:
        log.error("-> no es connection found: abort.")
        return
    es.indices.put_mapping(index=index_name, body=mapping, doc_type="_doc", include_type_name=True)
