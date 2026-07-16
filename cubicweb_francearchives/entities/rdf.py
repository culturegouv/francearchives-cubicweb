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
"""francearchives rdf adpaters"""
import logging

from cubicweb_web.bwcompat import CubicWebPyramidRequest
from lxml import etree
import os
from rdflib.term import BNode, Literal, URIRef

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance
from cubicweb.entities.adapters import EntityRDFAdapter as CWEntityRDFAdapter
from cubicweb_eac.entities.rdf import AuthorityRecordRDFAdapter, AuthorityRecordRICORDFAdapter

RDF_FORMAT_EXTENSIONS = {
    "xml": "RDF/XML",
    "ttl": "Turtle",
    "nt": "n-triples",
    "n3": "n3",
    "jsonld": "JSON-LD",
}


# NOTE: do not call absolute_url() or cnx.build_url to avoid including lang prefix
def build_uri(req, restpath):
    if os.environ.get("RDFDUMP_PUBLISHED"):
        base_url = req.vreg.config.get("consultation-base-url")
        base_url = f"{base_url.rstrip('/')}/" if base_url else req.base_url()
    else:
        base_url = req.base_url()
    return URIRef(f"{base_url}{restpath}")


def plaintext(html):
    if html:
        try:
            html = etree.HTML(html)
            return (" ".join(html.xpath("//text()"))).strip()
        except Exception:
            logging.warning("failed to extract text from %r", html)
            return html
    return ""


def check_dataproperty_value(subject, predicate, data):
    if data.value is None or data.value == "":
        return []
    yield (subject, predicate, data)


class EntityRDFAdapter(CWEntityRDFAdapter):
    __abstract__ = True

    @property
    def uri(self):
        req = self._cw
        return build_uri(req, self.entity.rest_path())


class ArchiveComponent2Schemaorg(EntityRDFAdapter):
    __abstract__ = True
    MAX_COMPONENTS_DISPLAY = 500
    MAX_SUBJECTS_DISPLAY = 100

    @cachedproperty
    def subject_indexes(self):
        return self.entity.subject_authority_indexes()

    def schema_org_triples(self):
        entity = self.entity
        did = entity.did[0]
        RDF = self._use_namespace("rdf")
        SCHEMA = self._use_namespace("schema")
        yield (self.uri, RDF.type, SCHEMA.ArchiveComponent)
        yield (self.uri, SCHEMA.name, Literal(entity.dc_title()))
        if did.origination:
            yield (self.uri, SCHEMA.contentLocation, Literal(plaintext(did.origination)))
        if entity.scopecontent:
            yield (self.uri, SCHEMA.mentions, Literal(plaintext(entity.scopecontent)))
        if len(self.subject_indexes) < self.MAX_SUBJECTS_DISPLAY:
            for subject_eid, subject_label in self.subject_indexes:
                subject_uri = build_uri(self._cw, f"subject/{subject_eid}")
                yield (self.uri, SCHEMA.about, subject_uri)
                yield (subject_uri, SCHEMA.name, Literal(subject_label))

    def digitized_versions_triples(self):
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        RDF = self._use_namespace("schema")

        digitized_urls = [
            (url, "DataDownload")
            for url in entity.cw_adapt_to("entity.main_props").digitized_urls()
        ]
        if entity.illustration_url:
            digitized_urls.append((entity.illustration_url, "ImageObject"))

        for digitized_url, digitized_type in digitized_urls:
            encoding = BNode()
            yield (encoding, RDF.type, SCHEMA[digitized_type])
            yield (encoding, SCHEMA.contentUrl, URIRef(digitized_url))
            yield (self.uri, SCHEMA.encoding, encoding)


class FindingAid2SchemaOrg(ArchiveComponent2Schemaorg):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("FindingAid")

    def triples(self):
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        yield from self.schema_org_triples()
        top_components = entity.top_components_stable_ids_and_labels()
        if len(top_components) < self.MAX_COMPONENTS_DISPLAY:  # avoid making pages too heavy
            for _, fc_stable_id, fc_label in top_components:
                facomponent_uri = build_uri(self._cw, f"facomponent/{fc_stable_id}")
                yield (self.uri, SCHEMA.hasPart, facomponent_uri)
                yield (facomponent_uri, SCHEMA.name, Literal(fc_label))
        if entity.service:
            yield (self.uri, SCHEMA.holdingArchive, Literal(entity.service[0].dc_title()))
            yield from self.digitized_versions_triples()


class FAComponent2SchemaOrg(ArchiveComponent2Schemaorg):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("FAComponent")

    def triples(self):
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        yield from self.schema_org_triples()
        if entity.parent_component:
            yield (
                self.uri,
                SCHEMA.isPartOf,
                entity.parent_component[0].cw_adapt_to("rdf.schemaorg").uri,
            )
        else:
            yield (
                self.uri,
                SCHEMA.isPartOf,
                entity.finding_aid[0].cw_adapt_to("rdf.schemaorg").uri,
            )
        children_components = entity.children_components_stable_ids_and_labels()
        if len(children_components) < self.MAX_COMPONENTS_DISPLAY:  # avoid making pages too heavy
            for _, fc_stable_id, fc_label in children_components:
                facomponent_uri = build_uri(self._cw, f"facomponent/{fc_stable_id}")
                yield (self.uri, SCHEMA.hasPart, facomponent_uri)
                yield (facomponent_uri, SCHEMA.name, Literal(fc_label))

        if entity.finding_aid[0].service:
            yield (
                self.uri,
                SCHEMA.holdingArchive,
                Literal(entity.finding_aid[0].service[0].dc_title()),
            )
        yield from self.digitized_versions_triples()


class ServiceRDFAdapter(EntityRDFAdapter):
    __regid__ = "rdf"
    __select__ = is_instance("Service")

    @property
    def uri(self):
        req = self._cw
        return build_uri(req, f"service/{self.entity.eid}")

    @cachedproperty
    def address_uri(self):
        return URIRef(f"{self.uri}#address")

    def contact_triples(self):
        RDF = self._use_namespace("rdf")
        SCHEMA = self._use_namespace("schema")
        yield from check_dataproperty_value(
            self.uri, SCHEMA.employee, Literal(self.entity.contact_name)
        )
        yield from check_dataproperty_value(
            self.uri, SCHEMA.telephone, Literal(self.entity.phone_number)
        )
        yield from check_dataproperty_value(
            self.uri, SCHEMA.openingHours, Literal(self.entity.opening_period)
        )
        yield from check_dataproperty_value(self.uri, SCHEMA.email, Literal(self.entity.email))
        yield from check_dataproperty_value(self.uri, SCHEMA.url, Literal(self.entity.website_url))

        address = self.address_uri
        yield (self.uri, SCHEMA.address, address)
        yield (address, RDF.type, SCHEMA.PostalAddress)
        yield from check_dataproperty_value(
            address, SCHEMA.postalCode, Literal(self.entity.zip_code)
        )
        yield from check_dataproperty_value(
            address, SCHEMA.streetAddress, Literal(self.entity.address)
        )
        yield from check_dataproperty_value(
            address, SCHEMA.addressLocality, Literal(self.entity.city)
        )
        yield (address, SCHEMA.addressCountry, Literal("fr"))

    def hierarchical_triples(self, relation_uri, parent_uri, child_uri):
        RDF = self._use_namespace("rdf")
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        yield (relation_uri, RDF.type, RICO.AgentHierarchicalRelation)
        yield (relation_uri, RICO.agentHierarchicalRelationHasSource, parent_uri)
        yield (relation_uri, RICO.agentHierarchicalRelationHasTarget, child_uri)
        yield (parent_uri, RICO.agentIsSourceOfAgentHierarchicalRelation, relation_uri)
        yield (child_uri, RICO.agentIsTargetOfAgentHierarchicalRelation, relation_uri)
        yield (parent_uri, RICO.hasOrHadSubordinate, child_uri)
        yield (child_uri, RICO.isOrWasSubordinateTo, parent_uri)

    def triples(self):
        RDF = self._use_namespace("rdf")
        RDFS = self._use_namespace("rdfs")
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        GEO = self._use_namespace("geo", base_url="http://www.w3.org/2003/01/geo/wgs84_pos#")
        self.entity.complete()
        yield (self.uri, RDF.type, RICO.Agent)
        yield (self.uri, RDF.type, RICO.CorporateBody)
        yield (self.uri, RDFS.label, Literal(self.entity.dc_title()))
        yield from check_dataproperty_value(self.uri, RICO.identifier, Literal(self.entity.code))
        yield from check_dataproperty_value(self.uri, RICO.name, Literal(self.entity.name))
        yield from check_dataproperty_value(self.uri, RICO.name, Literal(self.entity.name2))
        yield from check_dataproperty_value(self.uri, RICO.name, Literal(self.entity.short_name))
        yield from check_dataproperty_value(self.uri, RICO.name, Literal(self.entity.name2))
        yield from check_dataproperty_value(self.uri, RICO.type, Literal(self.entity.level))

        yield from self.contact_triples()
        if self.entity.annex_of:
            parent_uri = build_uri(self._cw, f"service/{self.entity.annex_of[0].eid}")
            relation_uri = URIRef(f"{parent_uri}#hierarchical_to_{self.entity.eid}")
            yield from self.hierarchical_triples(relation_uri, parent_uri, self.uri)

        for child in self.entity.reverse_annex_of:
            child_uri = build_uri(self._cw, f"service/{child.eid}")
            relation_uri = URIRef(f"{self.uri}#hierarchical_to_{child.eid}")
            yield from self.hierarchical_triples(relation_uri, self.uri, child_uri)

        if self.entity.latitude and self.entity.longitude:
            yield (self.uri, GEO.lat, Literal(self.entity.latitude))
            yield (self.uri, GEO.long, Literal(self.entity.longitude))


class Service2SchemaOrg(ServiceRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("Service")

    @cachedproperty
    def address_uri(self):
        return BNode()

    def triples(self):
        RDF = self._use_namespace("rdf")
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        yield (self.uri, RDF.type, SCHEMA.ArchiveOrganization)
        yield (self.uri, SCHEMA.legalName, Literal(entity.dc_title()))
        if entity.illustration_url:
            yield (self.uri, SCHEMA.logo, Literal(entity.illustration_url))

        if entity.annex_of:
            parent = entity.annex_of[0].cw_adapt_to("rdf.schemaorg")
            if parent:
                yield (self.uri, SCHEMA.parentOrganization, parent.uri)

        for child in entity.reverse_annex_of:
            child = child.cw_adapt_to("rdf.schemaorg")
            if child:
                yield (self.uri, SCHEMA.subOrganization, child.uri)

        if entity.latitude and entity.longitude:
            yield (self.uri, SCHEMA.latitude, Literal(entity.latitude))
            yield (self.uri, SCHEMA.longitude, Literal(entity.longitude))
        yield from self.contact_triples()


class AuthorityRICOAdapter(EntityRDFAdapter):
    __abstract__ = True

    def triples(self):
        OWL = self._use_namespace("owl")
        RDFS = self._use_namespace("rdfs")
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        yield (self.uri, RICO.name, Literal(self.entity.label))
        yield (self.uri, RDFS.label, Literal(self.entity.label))
        for ref in self.entity.same_as:
            if ref.cw_etype == "ExternalUri":
                yield (self.uri, OWL.sameAs, URIRef(ref.uri))
            elif ref.cw_etype == "Concept":
                yield (self.uri, OWL.sameAs, URIRef(ref.cwuri))
            elif ref.cw_etype != "AuthorityRecord":
                yield (self.uri, OWL.sameAs, build_uri(self._cw, ref.rest_path()))


class AgentAuthority(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("AgentAuthority")

    def triples(self):
        RDF = self._use_namespace("rdf")
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        agent_types = self.entity.index_types
        if len(agent_types) > 0:
            if "persname" in agent_types[0]:
                yield (self.uri, RDF.type, SCHEMA.Person)
            else:
                yield (self.uri, RDF.type, SCHEMA.Organization)
        else:
            yield (self.uri, RDF.type, SCHEMA.Thing)
        adapter = entity.cw_adapt_to("entity.main_props")
        info = adapter.eac_info() or adapter.agent_info()
        if info:
            if "dates" in info:
                birthdate = info["dates"].get("birthdate")
                deathdate = info["dates"].get("deathdate")
                for dtype, dateinfo in (("birthDate", birthdate), ("deathDate", deathdate)):
                    if dateinfo and dateinfo["isdate"] and not dateinfo["isbc"]:
                        yield (self.uri, SCHEMA[dtype], Literal(dateinfo["timestamp"]))
            if "description" in info:
                yield (self.uri, SCHEMA.description, Literal(info["description"]))
        yield (self.uri, SCHEMA.name, Literal(entity.label))
        yield (self.uri, SCHEMA.url, Literal(self.uri))

        for url in self.entity.same_as_refs:
            yield (self.uri, SCHEMA.sameAs, Literal(url))


class AgentAuthorityRDFAdapter(AuthorityRICOAdapter):
    __regid__ = "rdf"
    __select__ = is_instance("AgentAuthority")

    def dates_triples(self, beginProperty, endProperty):
        XSD = self._use_namespace("xsd")
        adapter = self.entity.cw_adapt_to("entity.main_props")
        info = adapter.eac_info() or adapter.agent_info()
        if info:
            if "dates" in info:
                birthdate = info["dates"].get("birthdate")
                deathdate = info["dates"].get("deathdate")
                for propUri, dateinfo in ((beginProperty, birthdate), (endProperty, deathdate)):
                    if dateinfo and dateinfo["isdate"] and not dateinfo["isbc"]:
                        yield (
                            self.uri,
                            propUri,
                            Literal(dateinfo["timestamp"], datatype=XSD.date),
                        )

    def relation_uri(self, relation_type, agent_a):
        records = sorted([agent_a, self.entity], key=lambda x: x.eid)
        return URIRef(
            f"{build_uri(self._cw, records[0].rest_path())}#{relation_type}_to_{records[1].eid}"
        )

    def family_relation_triples(self, relation_uri, fam_agent_uri):
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        RDF = self._use_namespace("rdf")
        yield (self.uri, RDF.type, RICO.Person)
        yield from self.relation_triples(
            RICO.FamilyRelation,
            relation_uri,
            self.uri,
            fam_agent_uri,
            RICO.familyRelationConnects,
            RICO.personHasFamilyRelation,
            RICO.familyRelationConnects,
            RICO.personHasFamilyRelation,
            RICO.hasFamilyAssociationWith,
            RICO.hasFamilyAssociationWith,
        )

    def relation_triples(
        self,
        class_uri,
        relation_uri,
        source_uri,
        target_uri,
        prop_source,
        prop_source_inverse,
        prop_target,
        prop_target_inverse,
        reduced_prop,
        reduced_prop_inverse,
    ):
        RDF = self._use_namespace("rdf")
        yield (relation_uri, RDF.type, class_uri)
        yield (relation_uri, prop_source, source_uri)
        yield (relation_uri, prop_target, target_uri)
        yield (source_uri, prop_source_inverse, relation_uri)
        yield (target_uri, prop_target_inverse, relation_uri)
        yield (source_uri, reduced_prop, target_uri)
        yield (target_uri, reduced_prop_inverse, source_uri)

    def triples(self):
        if not self.entity.quality:
            return []
        yield from super().triples()
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        RDF = self._use_namespace("rdf")

        yield (self.uri, RDF.type, RICO.Agent)
        types = self.entity.index_types

        if types:
            if ["name"] in types:
                types.remove(["name"])
        if types:
            if len(types) > 1:  # if the authority is of more than one type
                yield (self.uri, RDF.type, RICO.Agent)
            elif types[0][0] == "persname":
                yield (self.uri, RDF.type, RICO.Person)
                yield from self.dates_triples(RICO.birthDate, RICO.deathDate)

            else:
                yield from self.dates_triples(RICO.beginningDate, RICO.endDate)

                if types[0][0] == "corpname":
                    yield (self.uri, RDF.type, RICO.CorporateBody)
                elif types[0][0] == "famname":
                    yield (self.uri, RDF.type, RICO.Family)

        authority_record_rset = self._cw.execute(
            "DISTINCT Any R WHERE X is AgentAuthority,"
            "X eid %(e)s, X same_as R, R is AuthorityRecord",
            {"e": self.entity.eid},
        )
        if authority_record_rset:
            for record in authority_record_rset.entities():
                yield from record.cw_adapt_to("rdf").agent_triples()

        # Family relations from Wikidata

        # children
        for child in self.entity.reverse_wikidata_child_of:
            if not child.quality:
                continue
            child_uri = build_uri(self._cw, child.rest_path())
            rel_uri = self.relation_uri("child", child)
            yield from self.family_relation_triples(rel_uri, child_uri)

            yield from self.relation_triples(
                RICO.ChildRelation,
                rel_uri,
                self.uri,
                child_uri,
                RICO.childRelationHasSource,
                RICO.personIsSourceOfChildRelation,
                RICO.childRelationHasTarget,
                RICO.personIsTargetOfChildRelation,
                RICO.hasChild,
                RICO.isChildOf,
            )

        # parents
        for parent in self.entity.wikidata_child_of:
            if not parent.quality:
                continue
            parent_uri = build_uri(self._cw, parent.rest_path())
            rel_uri = self.relation_uri("child", parent)
            yield from self.family_relation_triples(rel_uri, parent_uri)

            yield from self.relation_triples(
                RICO.ChildRelation,
                rel_uri,
                parent_uri,
                self.uri,
                RICO.childRelationHasSource,
                RICO.personIsSourceOfChildRelation,
                RICO.childRelationHasTarget,
                RICO.personIsTargetOfChildRelation,
                RICO.hasChild,
                RICO.isChildOf,
            )

        # siblings
        for sibling in self.entity.wikidata_sibling_of + self.entity.reverse_wikidata_sibling_of:
            if not sibling.quality:
                continue
            sibling_uri = build_uri(self._cw, sibling.rest_path())
            rel_uri = self.relation_uri("sibling", sibling)
            yield from self.family_relation_triples(rel_uri, sibling_uri)

            yield from self.relation_triples(
                RICO.SiblingRelation,
                rel_uri,
                sibling_uri,
                self.uri,
                RICO.siblingRelationConnects,
                RICO.personHasSiblingRelation,
                RICO.siblingRelationConnects,
                RICO.personHasSiblingRelation,
                RICO.hasSibling,
                RICO.hasSibling,
            )

        # spouse
        for spouse in self.entity.wikidata_spouse_of + self.entity.reverse_wikidata_spouse_of:
            if not spouse.quality:
                continue
            spouse_uri = build_uri(self._cw, spouse.rest_path())
            rel_uri = self.relation_uri("spouse", spouse)
            yield from self.family_relation_triples(rel_uri, spouse_uri)

            yield from self.relation_triples(
                RICO.SpouseRelation,
                rel_uri,
                spouse_uri,
                self.uri,
                RICO.spouseRelationConnects,
                RICO.personHasSpouseRelation,
                RICO.spouseRelationConnects,
                RICO.personHasSpouseRelation,
                RICO.hasOrHadSpouse,
                RICO.hasOrHadSpouse,
            )

        # organisation
        for organisation in self.entity.wikidata_member_of:
            if not organisation.quality:
                continue
            org_uri = build_uri(self._cw, organisation.rest_path())
            rel_uri = self.relation_uri("member", organisation)
            yield (self.uri, RDF.type, RICO.Person)
            yield (org_uri, RDF.type, RICO.CorporateBody)
            yield from self.relation_triples(
                RICO.MembershipRelation,
                rel_uri,
                org_uri,
                self.uri,
                RICO.membershipRelationHasSource,
                RICO.groupIsSourceOfMembershipRelation,
                RICO.membershipRelationHasTarget,
                RICO.personIsTargetOfMembershipRelation,
                RICO.hasOrHadMember,
                RICO.isOrWasMemberOf,
            )
            yield from self.relation_triples(
                RICO.AgentToAgentRelation,
                rel_uri,
                self.uri,
                org_uri,
                RICO.agentRelationConnects,
                RICO.agentIsConnectedToAgentRelation,
                RICO.agentRelationConnects,
                RICO.agentIsConnectedToAgentRelation,
                RICO.isAgentAssociatedWithAgent,
                RICO.isAgentAssociatedWithAgent,
            )


class LocationAuthority(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("LocationAuthority")

    def triples(self):
        RDF = self._use_namespace("rdf")
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        yield (self.uri, RDF.type, SCHEMA.Place)
        yield (self.uri, SCHEMA.name, Literal(entity.label))
        yield (self.uri, SCHEMA.url, Literal(self.uri))

        if entity.latitude and entity.longitude:
            yield (self.uri, SCHEMA.latitude, Literal(entity.latitude))
            yield (self.uri, SCHEMA.longitude, Literal(entity.longitude))
        for url in self.entity.same_as_refs:
            yield (self.uri, SCHEMA.sameAs, Literal(url))


class LocationAuthorityRDFAdapter(AuthorityRICOAdapter):
    __regid__ = "rdf"
    __select__ = is_instance("LocationAuthority")

    def triples(self):
        if not self.entity.quality:
            return []
        yield from super().triples()
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        RDF = self._use_namespace("rdf")
        GEO = self._use_namespace("geo", base_url="http://www.w3.org/2003/01/geo/wgs84_pos#")
        yield (self.uri, RDF.type, RICO.Place)
        if self.entity.latitude and self.entity.longitude:
            yield (self.uri, GEO.lat, Literal(self.entity.latitude))
            yield (self.uri, GEO.long, Literal(self.entity.longitude))

        parent_levels = {
            "adm4": {"table": "adm4_geonames", "field": "admin4_code"},
            "adm3": {"table": "adm3_geonames", "field": "admin3_code"},
            "adm2": {"table": "adm2_geonames", "field": "admin2_code"},
            "adm1": {"table": "adm1_geonames", "field": "admin1_code"},
            "country": {"table": "country_geonames", "field": "country_code"},
        }

        for key, value in parent_levels.items():
            cnx = self._cw

            # CubicWebPyramidRequest does not have system_sql
            if isinstance(cnx, CubicWebPyramidRequest):
                cnx = self._cw.cnx

            res = cnx.system_sql(
                f"""
                WITH parent AS (SELECT CAST(_P.geonameid AS TEXT) as parent_id
                FROM cw_ExternalUri AS _Y, same_as_relation AS rel_same_as0,
                    geonames AS _Z, {value["table"]} as _P
                WHERE rel_same_as0.eid_from=%(eid)s AND rel_same_as0.eid_to=_Y.cw_eid
                AND _Y.cw_source='geoname'
                AND _Z.geonameid= NULLIF(_Y.cw_extid, '')::int
                AND _P.{value["field"]}=_Z.{value["field"]}
                {"AND _Z.country_code='FR'" if "adm" in key else ""}
                )
                SELECT L.cw_eid
                FROM cw_LocationAuthority as L, same_as_relation AS same_as, cw_ExternalUri as E
                WHERE E.cw_extid IN (SELECT parent_id FROM parent)
                AND E.cw_source='geoname'
                AND same_as.eid_from=L.cw_eid AND same_as.eid_to=E.cw_eid AND L.cw_quality=True
                AND L.cw_eid != %(eid)s;
            """,
                {"eid": self.entity.eid},
            ).fetchall()
            if res:
                for parent_eid in res:
                    parent_uri = (
                        self._cw.entity_from_eid(parent_eid[0], etype="LocationAuthority")
                        .cw_adapt_to("rdf")
                        .uri
                    )
                    yield (parent_uri, RICO.containsOrContained, self.uri)
                    yield (self.uri, RICO.isOrWasContainedBy, parent_uri)


class SubjectAuthority(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("SubjectAuthority")

    def triples(self):
        RDF = self._use_namespace("rdf")
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        yield (self.uri, RDF.type, SCHEMA.Thing)
        yield (self.uri, SCHEMA.url, Literal(self.uri))
        yield (self.uri, SCHEMA.name, Literal(entity.label))
        for url in self.entity.same_as_refs:
            yield (self.uri, SCHEMA.sameAs, Literal(url))


class SubjectAuthorityRDFAdapter(AuthorityRICOAdapter):
    __regid__ = "rdf"
    __select__ = is_instance("SubjectAuthority")

    def triples(self):
        if not self.entity.quality:
            return []
        yield from super().triples()
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        RDF = self._use_namespace("rdf")
        yield (self.uri, RDF.type, RICO.Concept)
        TYPE_TO_RICO = {
            "genreform": [RICO.DocumentaryFormType],
            "subject": [RICO.Concept],
            "function": [RICO.ActivityType],
            "occupation": [RICO.OccupationType, RICO.ActivityType],
        }

        rset = self._cw.execute(
            "DISTINCT Any TYPE WHERE X is SubjectAuthority,"
            "X eid %(e)s, I is Subject, I authority X,"
            "I type TYPE",
            {"e": self.entity.eid},
        )  # no better way to find what kind of subject this is supposed to be
        if rset:
            if len(rset[0]) == 1 and rset[0][0] in TYPE_TO_RICO:
                for subject_type in TYPE_TO_RICO[rset[0][0]]:
                    yield (self.uri, RDF.type, subject_type)


class AuthorityRecord2SchemaOrg(EntityRDFAdapter, AuthorityRecordRDFAdapter):
    __select__ = AuthorityRecordRDFAdapter.__select__ & is_instance("AuthorityRecord")


class AuthorityRecordRDFAdapter(EntityRDFAdapter, AuthorityRecordRICORDFAdapter):
    __regid__ = "rdf"

    @property
    def agent_uri(self):
        agent = self.entity.qualified_authority
        if agent:
            return build_uri(self._cw, agent[0].rest_path())
        return super().agent_uri

    def triples(self):
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        yield from self.record_triples()

        # output agent_triples only if they are not already output by an existing authority
        if self.agent_uri.startswith(self.uri):
            yield from self.agent_triples()

        if self.entity.maintainer:
            service_uri = URIRef(build_uri(self._cw, f"service/{self.entity.maintainer[0].eid}"))
            yield (self.uri, RICO.hasCreator, service_uri)
            yield (self.inst_uri, RICO.hasOrHadHolder, service_uri)


class EntityBNodeAdapter(CWEntityRDFAdapter):
    __abstract__ = True

    @cachedproperty
    def uri(self):
        return BNode()


class EntitySameAsAdapter(CWEntityRDFAdapter):
    __abstract__ = True

    @cachedproperty
    def uri(self):
        equiv = self.entity.equivalent_concept
        if equiv:
            return build_uri(self._cw, equiv[0].rest_path())
        return BNode()


class ActivityRDFAdapter(EntityBNodeAdapter):
    __select__ = is_instance("Activity")


class MandateRDFAdapter(EntitySameAsAdapter):
    __select__ = is_instance("Mandate")


class OccupationRDFAdapter(EntitySameAsAdapter):
    __select__ = is_instance("Occupation")


class AgentFunctionRDFAdapter(EntitySameAsAdapter):
    __select__ = is_instance("AgentFunction")


class LegalStatusRDFAdapter(EntitySameAsAdapter):
    __select__ = is_instance("LegalStatus")


class PlaceEntryRDFAdapter(EntitySameAsAdapter):
    __select__ = is_instance("PlaceEntry")


class NameEntryRDFAdapter(EntityBNodeAdapter):
    __select__ = is_instance("NameEntry")


class AgentPlaceRDFAdapter(EntityBNodeAdapter):
    __select__ = is_instance("AgentPlace")


class ArticleSchemaOrg(EntityRDFAdapter):
    __regid__ = "rdf.schemaorg"
    __abstract__ = True

    article_type = "Article"

    def author_triples(self):
        SCHEMA = self._use_namespace("schema")
        RDF = self._use_namespace("rdf")
        authors = self.entity.cw_adapt_to("IMeta").author()
        if authors:
            for name in authors:
                author = BNode()
                yield (author, RDF.type, SCHEMA.Person)
                yield (author, SCHEMA.name, Literal(name))
                yield (self.uri, SCHEMA.author, author)
        else:
            author = BNode()
            yield (author, RDF.type, SCHEMA.Organization)
            yield (author, SCHEMA.name, Literal("FranceArchives"))
            yield (self.uri, SCHEMA.author, author)

    def dates_triples(self):
        SCHEMA = self._use_namespace("schema")
        yield (
            self.uri,
            SCHEMA.datePublished,
            Literal(self.entity.creation_date.strftime("%Y-%m-%d")),
        )
        yield (
            self.uri,
            SCHEMA.dateCreated,
            Literal(self.entity.creation_date.strftime("%Y-%m-%d")),
        )
        yield (
            self.uri,
            SCHEMA.dateModified,
            Literal(self.entity.modification_date.strftime("%Y-%m-%d")),
        )

    def triples(self):
        RDF = self._use_namespace("rdf")
        SCHEMA = self._use_namespace("schema")
        entity = self.entity
        yield (self.uri, RDF.type, SCHEMA[self.article_type])
        yield (self.uri, SCHEMA.name, Literal(entity.dc_title()))
        yield (self.uri, SCHEMA.headline, Literal(entity.dc_title()))
        yield (self.uri, SCHEMA.inLanguage, Literal(entity.dc_language().upper()))
        yield (self.uri, SCHEMA.mainEntityOfPage, Literal(self.uri))
        if entity.dc_subjects():
            yield (self.uri, SCHEMA.keywords, Literal(entity.dc_subjects()))
        if entity.illustration_url:
            yield (self.uri, SCHEMA.image, Literal(entity.illustration_url))
            # XXX TODO : ideally, each article should have an illustration
        yield (self.uri, SCHEMA.url, Literal(self.uri))

        yield from self.dates_triples()
        yield from self.author_triples()

        francearchives = BNode()
        yield (self.uri, SCHEMA.publisher, francearchives)
        yield (francearchives, SCHEMA.name, Literal("FranceArchives"))
        yield (francearchives, RDF.type, SCHEMA.Organization)
        yield (
            francearchives,
            SCHEMA.logo,
            Literal(self._cw.vreg.config.uiprops["AMP_LOGO"]),
        )
        # XXX TODO : data_url is not found (how to retrieve it ?)

        if entity.header:
            yield (self.uri, SCHEMA.description, Literal(entity.header))

        sections = [s.dc_title() for s in entity.cw_adapt_to("ITree").iterparents()]
        for section in sections:
            yield (self.uri, SCHEMA.articleSection, Literal(section))
        yield (self.uri, SCHEMA.isAccessibleForFree, Literal("True"))


class BaseContent2SchemaOrg(ArticleSchemaOrg):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("BaseContent")


class NewsContent2SchemaOrg(ArticleSchemaOrg):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("NewsContent")

    article_type = "NewsArticle"

    def dates_triples(self):
        SCHEMA = self._use_namespace("schema")
        yield (
            self.uri,
            SCHEMA.dateCreated,
            Literal(self.entity.creation_date.strftime("%Y-%m-%d")),
        )
        yield (
            self.uri,
            SCHEMA.dateModified,
            Literal(self.entity.modification_date.strftime("%Y-%m-%d")),
        )
        if self.entity.start_date:
            yield (
                self.uri,
                SCHEMA.datePublished,
                Literal(self.entity.start_date.strftime("%Y-%m-%d")),
            )
        else:
            yield (
                self.uri,
                SCHEMA.datePublished,
                Literal(self.entity.creation_date.strftime("%Y-%m-%d")),
            )


class CommemorationItem2SchemaOrg(ArticleSchemaOrg):
    __regid__ = "rdf.schemaorg"
    __select__ = is_instance("CommemorationItem")


def set_related_cache(entity, rtype, related, role="subject"):
    cache_key = "{}_{}".format(rtype, role)
    # XXX None means we can't use resultset, only entities
    entity._cw_related_cache[cache_key] = (None, related)


class ArchiveComponentRDFAdapter(EntityRDFAdapter):
    __abstract__ = True

    @property
    def main_instance_uri(self):
        return URIRef(f"{self.uri}#record_resource_inst")

    def main_instance_triples(self):
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        RDF = self._use_namespace("rdf")
        inst_uri = self.main_instance_uri
        yield (inst_uri, RDF.type, RICO.Instantiation)
        yield (inst_uri, RICO.isInstantiationOf, self.uri)
        yield (self.uri, RICO.hasInstantiation, inst_uri)
        entity_service = self.entity.related_service
        if entity_service:
            yield (
                inst_uri,
                RICO.hasOrHadHolder,
                build_uri(self._cw, f"service/{entity_service.eid}"),
            )
        for originator in self.entity.qualified_originators:
            adapted_authority = originator.cw_adapt_to("rdf")
            yield (inst_uri, RICO.hasProvenance, adapted_authority.uri)

    def did_triples(self):
        XSD = self._use_namespace("xsd")
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        did = self.entity.did[0]
        did.complete()
        start_year = did.startyear
        stop_year = did.stopyear
        if start_year and stop_year:
            yield from check_dataproperty_value(
                self.uri, RICO.beginningDate, Literal(start_year, datatype=XSD.gYear)
            )
            yield from check_dataproperty_value(
                self.uri, RICO.endDate, Literal(stop_year, datatype=XSD.gYear)
            )
        else:
            yield from check_dataproperty_value(
                self.uri, RICO.date, Literal(start_year or stop_year, datatype=XSD.gYear)
            )
        yield from check_dataproperty_value(self.uri, RICO.identifier, Literal(did.unitid))

        yield from check_dataproperty_value(
            self.uri, RICO.history, Literal(plaintext(did.origination))
        )

        # Define the RecordResource instance
        if did.physdesc or did.physloc:
            yield from self.main_instance_triples()
            yield from check_dataproperty_value(
                self.main_instance_uri,
                RICO.physicalCharacteristics,
                Literal(plaintext(did.physdesc)),
            )

    def record_resource_triples(self):
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        RICO_FORMTYPES = self._use_namespace(
            "ricoformtypes",
            base_url="https://www.ica.org/standards/RiC/vocabularies/documentaryFormTypes#",
        )
        RDF = self._use_namespace("rdf")
        DCTERMS = self._use_namespace("dcterms")
        DCMITYPE = self._use_namespace("dcmitype", base_url="http://purl.org/dc/dcmitype/")
        RDFS = self._use_namespace("rdfs")
        entity = self.entity
        entity.complete()
        yield (self.uri, RDF.type, RICO.RecordResource)
        yield from check_dataproperty_value(self.uri, RICO.title, Literal(entity.dc_title()))
        yield from check_dataproperty_value(self.uri, RDFS.label, Literal(entity.dc_title()))
        yield from self.did_triples()
        yield from check_dataproperty_value(
            self.uri, RICO.scopeAndContent, Literal(plaintext(entity.scopecontent))
        )
        yield from check_dataproperty_value(
            self.uri, RICO.conditionsOfAccess, Literal(plaintext(entity.accessrestrict))
        )
        yield from check_dataproperty_value(
            self.uri, RICO.conditionsOfUse, Literal(plaintext(entity.userestrict))
        )
        yield from check_dataproperty_value(
            self.uri, RICO.history, Literal(plaintext(entity.acquisition_info))
        )
        # Link to authority
        for authority_eid, authority_type in entity.qualified_index_authorities:
            authority_uri = build_uri(self._cw, self._cw.entity_from_eid(authority_eid).rest_path())
            if authority_type == "genreform":
                yield (self.uri, RICO.hasOrHadSubject, authority_uri)
                yield (authority_uri, RDF.type, RICO.DocumentaryFormType)
            elif authority_type == "function":
                activity = BNode()
                yield (self.uri, RICO.documents, activity)
                yield (activity, RICO.hasActivityType, authority_uri)
            elif authority_type == "occupation":
                yield (self.uri, RICO.hasOrHadSubject, authority_uri)
                yield (authority_uri, RDF.type, RICO.OccupationType)
                yield (authority_uri, RDF.type, RICO.ActivityType)
            else:
                yield (self.uri, RICO.hasOrHadSubject, authority_uri)
        for originator in entity.qualified_originators:
            authority_uri = build_uri(self._cw, originator.rest_path())
            yield (self.uri, RICO.hasProvenance, authority_uri)

        # Define digitized_versions instance
        inst_number = 1
        if entity.related_service:
            service_uri = build_uri(self._cw, f"service/{entity.related_service.eid}")
        else:
            service_uri = None
        digitized_urls = [
            (url, "Dataset") for url in entity.cw_adapt_to("entity.main_props").digitized_urls()
        ]
        if entity.illustration_url:
            digitized_urls.append((entity.illustration_url, "Image"))
        for digitized_url, digitized_type in digitized_urls:
            digitized_version_uri = URIRef(f"{self.uri}#record_resource_inst{inst_number}")
            yield (digitized_version_uri, RDF.type, RICO.Instantiation)
            yield (digitized_version_uri, RICO.isInstantiationOf, self.uri)
            yield (self.uri, RICO.hasInstantiation, digitized_version_uri)
            yield (digitized_version_uri, DCTERMS["type"], DCMITYPE[digitized_type])
            yield (digitized_version_uri, DCTERMS["source"], Literal(digitized_url))
        if entity.iiif_manifest:
            iiif_manifest_uri = URIRef(f"{self.uri}#iiif_manifest")
            yield (iiif_manifest_uri, RDF.type, RICO.Record)
            yield (iiif_manifest_uri, RICO.hasDocumentaryFormType, RICO_FORMTYPES.IIIFManifest)
            yield (iiif_manifest_uri, RICO.describesOrDescribed, self.uri)
            yield (self.uri, RICO.isOrWasDescribedBy, iiif_manifest_uri)
            # add JSON file Instantiation
            iiif_instance_uri = URIRef(f"{entity.iiif_manifest}#iiif_manifest_inst")
            yield (iiif_instance_uri, RDF.type, RICO.Instantiation)
            yield (iiif_instance_uri, RICO.isInstantiationOf, iiif_manifest_uri)
            yield (iiif_manifest_uri, RICO.hasInstantiation, iiif_instance_uri)
            yield (iiif_instance_uri, DCTERMS["format"], Literal("application/json"))
            yield (iiif_instance_uri, DCTERMS["source"], Literal(iiif_manifest_uri))

            if service_uri:
                yield (
                    digitized_version_uri,
                    RICO.hasProvenance,
                    service_uri,
                )
            inst_number += 1

        if service_uri:
            yield (self.uri, RICO.hasOrHadManager, service_uri)


class FindingAidRDFAdapter(ArchiveComponentRDFAdapter):
    __regid__ = "rdf"
    __select__ = is_instance("FindingAid")

    def triples(self):
        RDF = self._use_namespace("rdf")
        RDFS = self._use_namespace("rdfs")
        DCTERMS = self._use_namespace("dcterms")
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        RICO_FORMTYPES = self._use_namespace(
            "ricoformtypes",
            base_url="https://www.ica.org/standards/RiC/vocabularies/documentaryFormTypes#",
        )
        entity = self.entity
        yield from self.record_resource_triples()

        # Define a record for the FA
        record_uri = URIRef(f"{self.uri}#record")
        yield (record_uri, RDF.type, RICO.Record)
        yield (record_uri, RICO.identifier, Literal(entity.eadid))
        yield (record_uri, RICO.hasDocumentaryFormType, RICO_FORMTYPES.FindingAid)
        yield (record_uri, RICO.describesOrDescribed, self.uri)
        yield (self.uri, RICO.isOrWasDescribedBy, record_uri)

        # Define the FA instanciation
        instance_uri = URIRef(f"{self.uri}#record_inst1")
        yield (instance_uri, RDF.type, RICO.Instantiation)
        yield (instance_uri, RICO.isInstantiationOf, record_uri)
        yield (record_uri, RICO.hasInstantiation, instance_uri)
        yield (instance_uri, DCTERMS["format"], Literal("text/csv"))
        yield (instance_uri, RDFS.seeAlso, build_uri(self._cw, "%s.csv" % entity.rest_path()))

        # Include top FAComponent
        for top_component in entity.top_components:
            facomponent_uri = build_uri(self._cw, f"facomponent/{top_component.stable_id}")
            yield (self.uri, RICO.includesOrIncluded, facomponent_uri)

        if entity.fa_header[0].lang_code:
            yield from check_dataproperty_value(
                self.uri, DCTERMS.language, Literal(entity.fa_header[0].lang_code)
            )


class FAComponentRDFAdapter(ArchiveComponentRDFAdapter):
    __regid__ = "rdf"
    __select__ = is_instance("FAComponent")

    def triples(self):
        RICO = self._use_namespace("rico", base_url="https://www.ica.org/standards/RiC/ontology#")
        entity = self.entity
        yield from self.record_resource_triples()
        finding_aid = entity.finding_aid[0]
        findingaid_uri = build_uri(self._cw, f"findingaid/{finding_aid.stable_id}")
        yield (self.uri, RICO.isRecordResourceAssociatedWithRecordResource, findingaid_uri)
        if not entity.parent_component:
            yield (self.uri, RICO.isOrWasIncludedIn, findingaid_uri)
        else:
            parent_component = entity.parent_component[0]
            facomponent_uri = build_uri(self._cw, f"facomponent/{parent_component.stable_id}")

            yield (self.uri, RICO.isOrWasIncludedIn, facomponent_uri)

        for child_component in entity.reverse_parent_component:
            facomponent_uri = build_uri(self._cw, f"facomponent/{child_component.stable_id}")
            yield (self.uri, RICO.includesOrIncluded, facomponent_uri)
        else:
            # if FAComponent is a leaf component, create the main
            # Instantiation
            yield from self.main_instance_triples()
