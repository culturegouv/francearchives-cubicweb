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

import datetime
from collections import OrderedDict, defaultdict
import logging

from logilab.common.decorators import cachedproperty

from cubicweb import _
from cubicweb.predicates import is_instance
from cubicweb.entities import AnyEntity, fetch_config
from cubicweb_francearchives.views import format_agent_date, STRING_SEP
from cubicweb_francearchives.entities.adapters import EntityMainPropsAdapter
from cubicweb_francearchives.utils import es_start_letter, format_date
from cubicweb_francearchives.entities.nomina import (
    initialize_nominarecord_entity,
    NominaActCodeTypes,
)


class GroupAuthorityError(Exception):
    """raised when an entity can not be grouped"""


def iter_entities(cnx, eid, rql, nb_entities, chunksize=100000):
    for offset in range(0, nb_entities, chunksize):
        for index_eid in cnx.execute(rql.format(offset=offset, limit=chunksize, eid=eid)):
            yield cnx.entity_from_eid(index_eid[0])


class ExternalUri(AnyEntity):
    __regid__ = "ExternalUri"
    fetch_attrs, cw_fetch_order = fetch_config(["label", "uri", "source", "extid"])

    def get_geonames_fclass(self):
        if self.source != "geoname":
            return None

        res = self._cw.cnx.system_sql(
            """
            SELECT fclass FROM geonames WHERE geonameid = %(gid)s
            """,
            {"gid": self.extid},
        ).fetchall()
        if res:
            return f"geonames_{res[0][0]}"
        return None

    def in_context_label(self):
        if self.source == "nomina":
            nomina_record = initialize_nominarecord_entity(self._cw.cnx, self.extid)
            act_type = NominaActCodeTypes.get(nomina_record.json_data["entity"]["act_type"], "?")
            act_year = nomina_record.json_data["entity"].get("event_year", "?")
            return f"{nomina_record.dc_title()} ({act_type} - {act_year})"
        return self.label


class ExternalId(AnyEntity):
    __regid__ = "ExternalId"
    fetch_attrs, cw_fetch_order = fetch_config(["extid", "label", "source"])


class AbstractIndex(AnyEntity):
    __abstract__ = True
    fetch_attrs, cw_fetch_order = fetch_config(["label", "role", "type"])
    lang = "fr"

    def dc_title(self):
        return self.label or self.authority[0].dc_title()

    @cachedproperty
    def findingaid(self):
        return self._cw.execute(
            "(DISTINCT Any FA WHERE X index FAC, FAC finding_aid FA, X eid %(e)s)"
            " UNION "
            "(DISTINCT Any FA WHERE X index FA, FA is FindingAid, X eid %(e)s)",
            {"e": self.eid},
        ).one()

    @property
    def authority_url(self):
        return self.authority[0].absolute_url()

    @property
    def authority_label(self):
        return self.authority[0].label

    def new_authority(self):
        req = self._cw
        auth = req.create_entity(self.authority_type, label=self.label)
        prevauthority = self.authority[0].eid
        logger = logging.getLogger("cubicweb_francearchives.dedupe_authorities")
        self.update_es_docs(prevauthority, auth.eid, logger=logger)
        self.cw_set(authority=auth)
        return auth

    def update_es_docs(self, oldauth, newauth, logger=None):
        # update FAComponent and FindingAid related ESDocuments for the current index
        # first update postgres db
        # TODO : this probabl- must go to the cubicweb_frarchives_edition
        if logger:
            logger.info("start updating esdocuments for index %s", self.eid)

        self._cw.system_sql(
            """
UPDATE
  cw_esdocument es
SET
  cw_doc = jsonb_set(
    es.cw_doc::jsonb,
    '{index_entries}',
    update_index_entries(
      es.cw_doc -> 'index_entries',
      %(oldauth)s,
      %(newauth)s
    )
  )
FROM
  ((
     SELECT fac.cw_eid
     FROM
       cw_facomponent fac
       JOIN index_relation ir ON ir.eid_to = fac.cw_eid
     WHERE ir.eid_from = %(indexeid)s
  ) UNION (
     SELECT fa.cw_eid
     FROM
       cw_findingaid fa
       JOIN index_relation ir ON ir.eid_to = fa.cw_eid
       WHERE ir.eid_from = %(indexeid)s
  )) fa
WHERE
  fa.cw_eid = es.cw_entity
        """,
            {"indexeid": self.eid, "oldauth": oldauth, "newauth": newauth},
        )
        self._cw.commit()
        if logger:
            logger.info("stop updating esdocuments, launch ES indexation for index %s", self.eid)
        data = [{"op_type": "index-related-documents", "entity": self, "logger": logger}]
        queue = self._cw.vreg["es"].select("es.opqueue", req=self._cw)
        # then update elasticsearch
        queue.process_operations(data)

    def remove_from_es_docs(self, autheid):
        # remove authority and index data from  esdocument related to FAComponent,FindingAid
        # linked to current index
        # first update postgres db
        self._cw.system_sql(
            """
UPDATE
  cw_esdocument es
SET
  cw_doc = jsonb_set(es.cw_doc::jsonb, '{"index_entries"}',
                   jsonb_path_query_array(es.cw_doc::jsonb->'index_entries',
                                          '$[*] ? (@."authority" <> %(auth)s)'))
FROM
  ((
     SELECT fac.cw_eid
     FROM
       cw_facomponent fac
       JOIN index_relation ir ON ir.eid_to = fac.cw_eid
     WHERE ir.eid_from = %(indexeid)s
  ) UNION (
     SELECT fa.cw_eid
     FROM
       cw_findingaid fa
       JOIN index_relation ir ON ir.eid_to = fa.cw_eid
       WHERE ir.eid_from = %(indexeid)s
  )) fa
WHERE
  fa.cw_eid = es.cw_entity
        """,
            {"indexeid": self.eid, "auth": autheid},
        )
        self._cw.commit()


class AgentName(AbstractIndex):
    __regid__ = "AgentName"
    authority_type = "AgentAuthority"
    fetch_attrs, cw_fetch_order = fetch_config(["label", "type", "role"])


class Geogname(AbstractIndex):
    __regid__ = "Geogname"
    authority_type = "LocationAuthority"


class Subject(AbstractIndex):
    __regid__ = "Subject"
    authority_type = "SubjectAuthority"

    def rest_path(self):
        return "subjectname/{}".format(self.eid)


class AbstractAuthority(AnyEntity):
    __abstract__ = True
    fetch_attrs, cw_fetch_order = fetch_config(["label", "quality"])
    _same_as_links = None
    lang = "fr"

    @property
    def same_as_links(self):
        if self._same_as_links:
            return self._same_as_links
        self._same_as_links = defaultdict(list)
        for e in self.same_as:
            #  same_as object may be of several cw_etypes as ExternaUri,
            #  NominaRecord, AuthorityRecord, etc
            e.complete()
            self._same_as_links[e.cw_etype].append(e)
        return self._same_as_links

    @classmethod
    def orphan_query(cls):
        """
        dont check NOT EXISTS(I authority X, I index F) as
        unpublished IR do not exist in published schema
        """
        return """Any X WHERE
                  X is {etype},
                  X quality False,
                  NOT EXISTS(I authority X),
                  NOT EXISTS(E related_authority X),
                  NOT EXISTS(X grouped_with X1),
                  NOT EXISTS(X2 grouped_with X)""".format(
            etype=cls.cw_etype
        )

    def dc_title(self):
        return self.label or self._cw._("no label")

    def rest_path(self):
        type = self.cw_etype[:-9].lower()  # remove `Authority`
        return "{}/{}".format(type, self.eid)

    @cachedproperty
    def fmt_creation_date(self):
        return format_date(self.creation_date, self._cw, fmt="d MMMM y")

    @property
    def fmt_modification_date(self):
        return format_date(self.modification_date, self._cw, fmt="d MMMM y")

    @property
    def es_start_letter(self):
        return es_start_letter(self.label)

    @property
    def itypes(self):
        return [
            t[0]
            for t in self._cw.execute(
                """DISTINCT Any T WHERE
            I authority X, I type T, X eid {eid}""".format(
                    eid=self.eid
                )
            ).rows
        ]

    def services_rset(self):
        return self._cw.execute(
            """
            DISTINCT Any S WITH S BEING  (
            (DISTINCT Any S WHERE EXISTS(A authority X, A index F, X eid %(e)s,
             F is FindingAid, F service S))
            UNION
            (DISTINCT Any S WHERE EXISTS(A authority X, A index FF, X eid %(e)s,
            FF is FAComponent, FF finding_aid F, F service S))
            )
            """,
            {"e": self.eid},
        )

    @property
    def nb_indexes(self):
        return self._cw.execute(
            """
        Any COUNT(I) WHERE I authority E, E eid %(e)s
        """,
            {"e": self.eid},
        )[0][0]

    def iter_indexes(self):
        rql = """Any I WHERE I authority E, E eid {eid}"""
        for entity in iter_entities(self._cw, self.eid, rql, self.nb_indexes):
            yield entity

    def group(self, other_auth_eids, logger=None):
        """Group an authority with some other authority
        :param list other_auth_eid: a list of authorities eid to group
        :param Logger logger: logger

        :returns: list for authorities eids: [grouping.eid, grouped_1.eid, ..., grouped_n.eid]
        :rtype: list
        """
        if logger is None:
            logger = logging.getLogger("cubicweb_francearchives.group_authorities")
            logger.setLevel(logging.INFO)
        req = self._cw
        if self.grouped_with:
            raise GroupAuthorityError(
                req._("Can not group authorities with an already grouped authority.")
            )
        grouped_with = [e.eid for e in self.reverse_grouped_with]
        grouped_auths = []
        for autheid in other_auth_eids:
            logger.info("start grouping %r into %r (%r)", autheid, self.eid, self.cw_etype)
            try:
                auth = req.entity_from_eid(autheid)
            except Exception:
                logger.error("skip grouping: %r is not an entity", autheid)
                continue
            if autheid == self.eid:
                # do not group with itself
                logger.error("skip grouping: %r with itsef", autheid, self.eid)
                continue
            if autheid in grouped_with:
                # already grouped with
                logger.info(
                    "skip grouping: %s is already grouped with %s ",
                    autheid,
                    self.eid,
                )
                continue
            grouped_auths.append(autheid)
            if auth.cw_etype != self.cw_etype:
                logger.error("could not group: %r with %r", auth.cw_etype, self.cw_etype)
                continue
            # rewrite `index_entries` in related es docs
            for index in auth.iter_indexes():
                index.update_es_docs(oldauth=auth.eid, newauth=self.eid, logger=logger)
                logger.info("done updating index %s of authority %s", index.eid, auth.eid)
                index.cw_clear_all_caches()
            logger.info(
                "start switching grouped authority %s relations to authority %s",
                autheid,
                self.eid,
            )
            kwargs = {"new": self.eid, "old": autheid}
            # redirect index entities from the old authority to the new authority
            req.execute(
                "SET I authority NEW WHERE NEW eid %(new)s, I authority OLD, OLD eid %(old)s",
                kwargs,
            )
            # redirect related ExternRefs, BaseContentand CommemorationItems
            # from the old authority to the new authority
            req.execute(
                """SET E related_authority NEW WHERE NEW eid %(new)s,
                   E related_authority OLD, OLD eid %(old)s, NOT EXISTS(E related_authority NEW)""",
                kwargs,
            )
            # delete related ExternRefs, BaseContent and CommemorationItems from the old authority
            req.execute("""DELETE E related_authority OLD WHERE OLD eid %(old)s""", kwargs)
            # set the grouped_with relation from the old authority to the new
            # delete same_as from the old authority
            req.execute("""DELETE S same_as OLD WHERE OLD eid %(old)s""", kwargs)
            req.execute("""DELETE OLD same_as S WHERE OLD eid %(old)s""", kwargs)
            # authority
            res = req.execute(
                "SET OLD grouped_with NEW WHERE OLD eid %(old)s, NEW eid %(new)s",
                kwargs,
            )
            if res:
                grouped_auths.extend([row[0] for row in res])
            # unqualify the grouped authority
            req.execute("SET OLD quality FALSE WHERE OLD eid %(old)s", kwargs)
            # remove the possible grouped_with relation from the new authority
            # to the old
            req.execute(
                "DELETE NEW grouped_with OLD WHERE OLD eid %(old)s, NEW eid %(new)s",
                kwargs,
            )
            # update all possible grouped_with subjects of the old authority
            # to the new authority
            req.execute(
                "SET O grouped_with NEW WHERE "
                "O grouped_with OLD, OLD eid %(old)s, NEW eid %(new)s",
                kwargs,
            )
            self._cw.commit()
            logger.info("done grouping %s into %s", autheid, self.eid)
            auth.cw_clear_all_caches()
        if grouped_auths:
            grouped_auths.insert(0, self.eid)
        return grouped_auths

    def unindex(self):
        """Make the entity orphan"""
        # remove all indexes from es and postgres
        for index in self.iter_indexes():
            index.remove_from_es_docs(self.eid)
        # DELETE all indexes
        req = self._cw
        req.execute(
            "DELETE {index_type} I WHERE I authority E, E eid %(eid)s".format(
                index_type=self.index_etype
            ),
            {"eid": self.eid},
        )
        # then update elasticsearch
        data = [{"op_type": "index-related-documents", "entity": self}]
        queue = self._cw.vreg["es"].select("es.opqueue", req=self._cw)
        queue.process_operations(data)

    def degroup(self):
        """Degroup an grouped authority"""
        if self.grouped_with:
            self._cw.execute(
                "DELETE X grouped_with Y WHERE X eid %(eid)s",
                {"eid": self.eid},
            )

    def delete_blacklisted(self):
        """Delete an authority to be blacklisted and all its relations.
        Do not use this method in other context than blacklisting.
        """
        self.unindex()
        # Delete `related_authority` relations
        req = self._cw
        req.execute(
            "DELETE A related_authority E WHERE E eid %(eid)s",
            {"eid": self.eid},
        )
        # Delete all `same_as` relations
        req.execute("""DELETE S same_as E WHERE E eid %(eid)s""", {"eid": self.eid})
        req.execute("""DELETE E same_as S WHERE E eid %(eid)s""", {"eid": self.eid})
        # Delete all `grouped_in` authorities and their relations
        # XXX SHOULD WE LET THEM BE?
        all_grouped = self.reverse_grouped_with
        req.execute("DELETE G grouped_with E WHERE E eid %(eid)s", {"eid": self.eid})
        for grouped in all_grouped:
            grouped.delete_blacklisted()
        # Delete all possible entries from authority_history
        self.remove_from_auth_history()
        # Delete the authority itself
        req.transaction_data["blacklist"] = True
        self.cw_delete()
        req.commit()
        self.cw_clear_all_caches()
        # clean as much as possible to avoid memory exhaustion
        req.drop_entity_cache()

    @cachedproperty
    def same_as_refs(self):
        urls = []
        for ref in self.same_as:
            if ref.cw_etype == "ExternalUri":
                urls.append(ref.uri)
            elif ref.cw_etype == "Concept":
                urls.append(ref.cwuri)
            else:
                urls.append(ref.absolute_url())
        return urls

    def add_to_auth_history(self):
        """
        add information of authority indexes and linked FindingAids to the `authority_history`
        table.
        TODO: update esdocument of FAComponents and FindingAids linked to the authority
        """
        indexes = self.reverse_authority
        if not indexes:
            return
        query = """
        INSERT INTO authority_history (fa_stable_id, type, label, indexrole, autheid)
        (
            SELECT DISTINCT fa.cw_stable_id, index.cw_type,
                            index.cw_label, index.cw_role, auth.cw_eid
            FROM cw_{authtable} auth
            JOIN cw_{indextable} as index ON index.cw_authority=auth.cw_eid
            JOIN index_relation i ON i.eid_from = index.cw_eid
            JOIN cw_findingaid fa ON fa.cw_eid = i.eid_to
            WHERE auth.cw_eid = {autheid}
                  AND auth.cw_label != index.cw_label
            UNION
            SELECT DISTINCT fa.cw_stable_id, index.cw_type,
                            index.cw_label, index.cw_role, auth.cw_eid
            FROM cw_{authtable} auth
            JOIN cw_{indextable} as index ON index.cw_authority=auth.cw_eid
            JOIN index_relation i ON i.eid_from = index.cw_eid
            JOIN cw_facomponent fac ON fac.cw_eid = i.eid_to
            JOIN cw_findingaid fa ON fa.cw_eid = fac.cw_finding_aid
            WHERE auth.cw_eid = {autheid}
                AND auth.cw_label != index.cw_label
                AND i.eid_from = index.cw_eid
        )
        ON CONFLICT (fa_stable_id, type, label, indexrole)
        DO UPDATE SET autheid = EXCLUDED.autheid
        ;"""
        self._cw.system_sql(
            query.format(
                autheid=self.eid,
                authtable=self.cw_etype.lower(),
                indextable=indexes[0].cw_etype.lower(),
            )
        )

    def remove_from_auth_history(self):
        """
        remove all lines for a given Authority
        """
        self._cw.system_sql(
            "DELETE FROM authority_history WHERE autheid=%(autheid)s",
            {"autheid": self.eid},
        )

    @property
    def is_orphan(self):
        query = self.orphan_query() + """, X eid %(eid)s"""
        return bool(self._cw.execute(query, {"eid": self.eid}))


class LocationAuthority(AbstractAuthority):
    __regid__ = "LocationAuthority"
    fetch_attrs, cw_fetch_order = fetch_config(["label", "quality", "longitude", "latitude"])
    index_etype = "Geogname"

    @property
    def itypes(self):
        return ()


class AgentAuthority(AbstractAuthority):
    __regid__ = "AgentAuthority"
    index_etype = "AgentName"
    _index_type = None

    @classmethod
    def orphan_query(cls):
        return (
            super(AgentAuthority, cls).orphan_query()
            + """,
            NOT EXISTS(X same_as S1, S1 is AuthorityRecord),
            NOT EXISTS(S2 same_as X, S2 is AuthorityRecord)
            """
        )

    @property
    def index_type(self):
        if not self._index_type:
            self._index_type = "persname" if "persname" in self.itypes else "other"
        return self._index_type

    @property
    def index_types(self):
        return [
            t
            for t in self._cw.execute(
                """DISTINCT Any TYPE WHERE X eid %(e)s,
               I is AgentName, I authority X, I type TYPE""",
                {"e": self.eid},
            ).rows
        ]

    @property
    def parents(self):
        return self.wikidata_child_of

    @property
    def siblings(self):
        return self.wikidata_sibling_of + self.reverse_wikidata_sibling_of

    @property
    def spouses(self):
        return self.wikidata_spouse_of + self.reverse_wikidata_spouse_of

    @property
    def children(self):
        return self.reverse_wikidata_child_of

    @property
    def organizations(self):
        return self.reverse_wikidata_member_of

    @property
    def members(self):
        return self.wikidata_member_of


class AgentAuthorityMainPropsAdapter(EntityMainPropsAdapter):
    __select__ = is_instance("AgentAuthority")
    _eac_info = None
    _agent_info = None
    date_labels = {
        "birthdate": {
            "persname": _("birth_date_label"),
            "other": _("start_date_label"),
        },
        "deathdate": {"persname": _("death_date_label"), "other": _("stop_date_label")},
    }

    def properties(self, export=False, vid="incontext", text_format="text/html"):
        eac_info = self.eac_info(vid=vid, text_format=text_format)
        if eac_info:
            return [entry for entry in eac_info["properties"].items() if entry[-1]]
        else:
            agent_info = self.agent_info(vid=vid, text_format=text_format)
        if agent_info:
            return [entry for entry in agent_info["properties"].items() if entry[-1]]
        return []

    def sources(self, vid="incontext"):
        sources = []
        same_as = self.entity.same_as_links
        fa_sources = []
        basename_sources = []
        authority_records = same_as.get("AuthorityRecord")
        if authority_records:
            fa_sources.append(
                (
                    self._cw._("AuthorityRecords"),
                    [e.view("maintainer.incontext") for e in authority_records],
                ),
            )
        external_sources = []
        for _source, _view in sorted(
            [(e.source, e.view(vid)) for e in same_as.get("ExternalUri", [])],
            key=lambda x: getattr(x, "source", "z") or "z",
            reverse=True,
        ):
            if _source == "nomina":
                basename_sources.append(_view)
            else:
                external_sources.append((_source, _view))
        if basename_sources:
            fa_sources.append((self._cw._("Names database"), basename_sources))
        if fa_sources:
            sources.append((self._cw._("fa_sources_label"), fa_sources))
        if external_sources:
            sources.append((self._cw._("external_sources_label"), external_sources))
        return sources

    def eac_info(self, vid="incontext", text_format="text/html"):
        """EAC notice to be displayed."""
        if self._eac_info is None:
            self._eac_info = {}
            rset = self._cw.execute(
                """Any X, H, AF, OC, HA, HT, AFN, OCT, SD, ED ORDERBY SD LIMIT 1
                WHERE X is AuthorityRecord,
                X start_date SD, X end_date ED,
                H? history_agent X,
                H abstract HA, H text HT,
                AF? function_agent X, AF name AFN,
                OC? occupation_agent X, OC term OCT,
                A same_as X, A eid {eid}""".format(
                    eid=self.entity.eid
                )
            )
            if rset:
                _ = self._cw._
                eac = rset.one()
                dates = {}
                properties = OrderedDict()
                a11y_keys = []
                for dtype, dateobj in (
                    ("birthdate", eac.start_date),
                    ("deathdate", eac.end_date),
                ):
                    if not dateobj:
                        continue
                    dates[dtype] = {
                        "timestamp": dateobj.strftime("%4Y-%m-%d"),
                        "precision": "d",
                        "isdate": True,
                        "isbc": False,
                    }
                    label = _(self.date_labels[dtype][self.entity.index_type])
                    a11y_keys.append(label)
                    properties[label] = format_agent_date(self._cw, dateobj)
                self._eac_info["dates"] = dates
                lang_attr = "fr" if self._cw.lang != "fr" else ""
                properties[_("eac_biogist_label")] = eac.abstract_text
                properties[_("eac_occupation_label")] = " ; ".join(
                    f.dc_title() for f in eac.reverse_occupation_agent
                )
                properties[_("eac_function_label")] = " ; ".join(
                    f.dc_title() for f in eac.reverse_function_agent
                )
                properties["source_info"] = eac.maintainer[0].dc_title()
                if lang_attr:
                    for key, value in properties.items():
                        if value and key not in a11y_keys:
                            properties[key] = f'<p lang="fr">{value}</p>'
                self._eac_info["properties"] = properties
        return self._eac_info

    def agent_info(self, vid="incontext", text_format="text/html"):
        """External agent information to be displayed."""
        if self._agent_info is None:
            self._agent_info = {}
            # ORDERBY S DESC if both Wikidata and data.bnf.fr exist use Wikidata
            rset = self._cw.execute(
                """Any E, S, U, A, DT, D ORDERBY S DESC LIMIT 1
                WHERE X same_as E, E is ExternalUri,
                E source in ('wikidata', 'databnf'), E source S, E uri U,
                A? agent_info_of E, A dates DT, A description D, X eid {eid}
                """.format(
                    eid=self.entity.eid
                )
            )
            if rset:
                _ = self._cw._
                properties = OrderedDict()
                exturi_eid, source, uri, agent, dates, description = rset.rows[0]
                dates = dates if dates else {}
                # why add self._agent_info["dates"]: it is only used in RDF
                self._agent_info["dates"] = dates
                for dtype in ("birthdate", "deathdate"):
                    if not dates.get(dtype):
                        continue
                    # do not display malformatted Wikidata dates
                    if not dates[dtype]["isdate"] and source == "wikidata":
                        continue
                    label = self.date_labels[dtype][self.entity.index_type]
                    if dates[dtype]["isdate"]:
                        datestr = format_agent_date(
                            self._cw,
                            datetime.datetime.strptime(dates[dtype]["timestamp"], "%Y-%m-%d"),
                            precision=dates[dtype]["precision"],
                            isbc=dates[dtype]["isbc"],
                            iso=dates[dtype]["isiso"],
                        )
                    else:
                        datestr = dates[dtype]["timestamp"]
                    properties[_(label)] = datestr
                # why add self._agent_info["description"] it is only used in RDF
                self._agent_info["description"] = description if description else ""
                properties[_("eac_biogist_label")] = "<br>".join(
                    self._agent_info["description"].split(STRING_SEP)
                )
                exturi = self._cw.entity_from_eid(exturi_eid)
                properties["source_info"] = self._cw._(exturi.source)
                self._agent_info["properties"] = properties
        return self._agent_info


class SubjectAuthority(AbstractAuthority):
    __regid__ = "SubjectAuthority"
    index_etype = "Subject"

    @classmethod
    def orphan_query(cls):
        return (
            super(SubjectAuthority, cls).orphan_query()
            + """,
        NOT EXISTS(C1 business_field B, X same_as B),
        NOT EXISTS(C2 historical_context H, X same_as H),
        NOT EXISTS(C3 document_type D, X same_as D),
        NOT EXISTS(C4 action A, X same_as A)"""
        )

    @property
    def itypes(self):
        return ()

    @property
    def index_types(self):
        return [
            t
            for t in self._cw.execute(
                """DISTINCT Any TYPE WHERE X eid %(e)s,
               I is Subject, I authority X, I type TYPE""",
                {"e": self.eid},
            ).rows
        ]
