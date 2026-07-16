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

"""AgentRecord adapter's classes"""

from cubicweb.predicates import is_instance

from cubicweb_francearchives.entities.cms.adapters import ITemplatableApdater
from cubicweb_francearchives.views import internurl_link

AGENT_VOCABULARY_ES_FIELDS_MAPPING = {
    "AgentRecordFunction": "functions",
    "AgentRecordOccupation": "occupations",
    "AgentRecordLegalStatus": "legal_status",
}


class AbstractAgentRecordVocabularyITemplatableApdater(ITemplatableApdater):
    __abstract__ = True
    __select__ = ITemplatableApdater.__select__ & is_instance(
        "AgentRecordFunction", "AgentRecordOccupation", "AgentRecordLegalStatus"
    )
    es_field = None

    def main_props(self):
        return [
            (self._cw._("note"), self.entity.note),
        ]

    def linked_documents(self, limit=100):
        cnx = self._cw
        indexer = cnx.vreg["es"].select("agents-reference-indexer", cnx)
        try:
            response = indexer.search_documents_by_field(
                self.es_field,
                self.entity.label,
                source_fields=["name", "record_id"],
                limit=limit,
            )
        except Exception as err:
            msg = (
                "[AgentRecordVocabularyITemplatableApdater] cound not "
                f'retrieve documents linked to "{self.entity.label}": {err}'
            )
            self.error(msg)
            return {"error": msg}
        doc_count = response["total"]
        data = {"total": doc_count}
        data["docs"] = [
            internurl_link(cnx, cnx.build_url(f"agentrecord/{hit['record_id']}"), hit["name"])
            for hit in response.get("hits", [])
        ]
        return data


class AgentRecordFunctionTemplatableApdater(AbstractAgentRecordVocabularyITemplatableApdater):
    __select__ = ITemplatableApdater.__select__ & is_instance("AgentRecordFunction")
    es_field = AGENT_VOCABULARY_ES_FIELDS_MAPPING["AgentRecordFunction"]


class AgentRecordOccupationTemplatableApdater(AbstractAgentRecordVocabularyITemplatableApdater):
    __select__ = ITemplatableApdater.__select__ & is_instance("AgentRecordOccupation")
    es_field = AGENT_VOCABULARY_ES_FIELDS_MAPPING["AgentRecordOccupation"]


class AgentRecordLegalStatusTemplatableApdater(AbstractAgentRecordVocabularyITemplatableApdater):
    __select__ = ITemplatableApdater.__select__ & is_instance("AgentRecordLegalStatus")
    es_field = AGENT_VOCABULARY_ES_FIELDS_MAPPING["AgentRecordLegalStatus"]
