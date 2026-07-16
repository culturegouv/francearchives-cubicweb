# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2024
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
from jinja2 import Environment, FileSystemLoader
from json import loads as json_loads

import logging
import unittest

from cubicweb_web.devtools.testlib import WebCWTC, WebPostgresApptestConfiguration

from cubicweb_francearchives import IIIF_MANIFEST_ROLE
from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.es.esdump import CACHER_CLASSES, ETYPES_ADAPTERS
from cubicweb_francearchives.testutils import sort_authorities


from cubicweb_eac import testutils as eac_testutils

from pgfixtures import setup_module, teardown_module  # noqa

LOGGER = logging.getLogger("testing.francearchives.esdump")
# LOGGER.setLevel(logging.INFO)

env = Environment(
    loader=FileSystemLoader("test/data/esdump"),
)


# Because of the _unbind_orm_relation, no other test can be executed after
# test_esdump, same attributes/relations of the entities are unbound and
# therefore unaccessible


def get_findingaid_es_doc(entity):
    service = entity.related_service
    return {
        "acquisition_info": "acquisition_info",
        "alltext": "description titleproper abstract note",
        "cw_etype": "FindingAid",
        "dates": {"gte": 1234, "lte": 1245},
        "did": {
            "unitid": "unitid",
            "unittitle": "unittitle",
        },
        "digitized": True,
        "eid": entity.eid,
        "eadid": "FRAD084_xxx",
        "escategory": "archives",
        "fa_stable_id": "FA1",
        "originators": ["Originators"],
        "scopecontent": "scopecontent",
        "service": {
            "code": service.code,
            "eid": service.eid,
            "level": service.level,
            "title": service.short_name,
        },
        "sortdate": "1234-01-01",
        "stable_id": "FA1",
        "startyear": 1234,
        "stopyear": 1245,
    }


def get_facomponent_es_doc(entity):
    service = entity.related_service
    return {
        "acquisition_info": f"{entity.stable_id}-fc-acquisition_info",
        "alltext": f"{entity.stable_id}-fc-description",
        "cw_etype": "FAComponent",
        "dates": {"gte": 2001, "lte": 2011},
        "did": {
            "unitid": f"{entity.stable_id}-fc-unitid",
            "unittitle": f"{entity.stable_id}-fc-unittitle",
        },
        "digitized": True,
        "digitized_all": [DZFacetValues.dz, DZFacetValues.dz_noniiif],
        "eid": entity.eid,
        "escategory": "archives",
        "fa_stable_id": entity.finding_aid[0].stable_id,
        "originators": ["Originators"],
        "scopecontent": f"{entity.stable_id}-fc-scopecontent",
        "service": {
            "code": service.code,
            "eid": service.eid,
            "level": service.level,
            "title": service.short_name,
        },
        "sortdate": "2001-01-01",
        "stable_id": entity.stable_id,
        "startyear": 2001,
        "stopyear": 2011,
    }


class RDFDumpTC(WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def create_findingaid(self, cnx, service, stable_id, **kwargs):
        fa = cnx.create_entity(
            "FindingAid",
            name="name",
            stable_id=stable_id,
            eadid="FRAD084_xxx",
            did=cnx.create_entity(
                "Did",
                unitid="unitid",
                unittitle="unittitle",
                physdesc="un beau rouleau",
                startyear=1234,
                stopyear=1245,
                note="note",
                abstract="abstract",
                origination="originators",
            ),
            fa_header=cnx.create_entity("FAHeader", titleproper="titleproper"),
            publisher="FRAD084",
            description="<div>description</div>",
            accessrestrict="<div>accessrestrict</div>",
            userestrict="<div>userestrict</div>",
            acquisition_info="<div>acquisition_info</div>",
            additional_resources="<div>additional_resources</div>",
            bibliography="<div>bibliography</div>",
            bioghist="<div>bioghist</div>",
            notes="<div>notes</div>",
            scopecontent="<div>scopecontent</div>",
            website_url="website_url",
            digitized_versions=[
                cnx.create_entity(
                    "DigitizedVersion",
                    illustration_url="dv-illustration_ur",
                    role="image",
                ),
                cnx.create_entity(
                    "DigitizedVersion",
                    url="dv-iiif_url",
                    role=IIIF_MANIFEST_ROLE,
                ),
            ],
            service=service,
            **kwargs,
        )
        esdoc = get_findingaid_es_doc(fa)
        cnx.create_entity("EsDocument", doc=esdoc, entity=fa)
        return fa

    def create_facomponent(self, cnx, finding_aid, stable_id, **kwargs):
        entity = cnx.create_entity(
            "FAComponent",
            finding_aid=finding_aid,
            stable_id=stable_id,
            did=cnx.create_entity(
                "Did",
                unitid=f"{stable_id}-fc-unitid",
                unittitle=f"{stable_id}-fc-unittitle",
                startyear=2001,
                stopyear=2011,
                origination=f"{stable_id}-fc-originators",
                repository="fc-repo",
            ),
            description=f"<div>{stable_id}-fc-description</div>",
            bibliography=f"<div>{stable_id}-fc-bibliography</div>",
            accessrestrict=f"<div>{stable_id}-fc-accessrestrict</div>",
            userestrict=f"<div>{stable_id}-fc-userestrict</div>",
            acquisition_info=f"<div>{stable_id}-fc-acquisition_info</div>",
            additional_resources=f"<div>{stable_id}-fc-additional_resources</div>",
            digitized_versions=cnx.create_entity(
                "DigitizedVersion",
                url="fr-dv-url",
                illustration_url="fc-dv-illustration_ur",
                role="image",
            ),
            bioghist=f"<div>{stable_id}-fc-bioghist</div>",
            notes=f"<div>{stable_id}-fc-notes</div>",
            scopecontent=f"<div>{stable_id}-fc-scopecontent</div>",
            component_order=kwargs["order"],
        )
        es_doc = get_facomponent_es_doc(entity)
        cnx.create_entity("EsDocument", doc=es_doc, entity=entity)
        return entity

    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            """
            In the data, description expected in B: base only (non quality), Q: quality:
            - F FindingAid: ir
              |_P FAComponent: facomp_parent
              | |_C FAComponent: facomp_child

            - F AuthorityRecord: QUALIFIED_AR -reverse_same_as- quality_auth_agent

            - F Service: FRAD084
            """
            service = cnx.create_entity(
                "Service",
                code="FRAD084",
                category="foo",
                name="Archives Vaucluse",
                short_name="AD Vaucluse",
                level="level-D",
            )
            self.service_eid = service.eid
            ir = self.create_findingaid(cnx, service, stable_id="FA1")
            cursor = cnx.cnxset.cu
            sql = """
            CREATE TABLE tmp_findingaid_es (cw_eid int, cw_name varchar(50));
            INSERT INTO tmp_findingaid_es (cw_eid, cw_name) VALUES (%s,%s)"""
            data = [(ir.eid, "wfs_cmsobject_draft")]
            cursor.executemany(sql, data)
            cnx.commit()

            facomp_parent = self.create_facomponent(cnx, ir, "FC1", order=1)
            facomp_child = self.create_facomponent(
                cnx, ir, "FC11", order=2, parent_component=facomp_parent
            )
            quality_authority_record = eac_testutils.authority_record(
                cnx, "QUALIFIED_AR", "Toto", xml_support="foo"
            )
            cnx.create_entity(
                "AgentAuthority",
                label="Jeanne Poulet",
                quality=True,
                same_as=quality_authority_record,
            )
            loutre_location_auth = cnx.create_entity("LocationAuthority", label="Loutre")
            loutre_subj_auth = cnx.create_entity("SubjectAuthority", label="Loutre")
            loutre_agent_auth = cnx.create_entity("AgentAuthority", label="Loutre", quality=True)
            originator_auth = cnx.create_entity("AgentAuthority", label="Originators", quality=True)
            cnx.create_entity(
                "AgentName",
                label="originators",
                authority=originator_auth,
                role="originator",
                index=(ir, facomp_parent, facomp_child),
                type="corpname",
            )
            cnx.create_entity(
                "AgentName",
                label="loutre",
                authority=loutre_agent_auth,
                index=facomp_parent,
                type="occupation",
                role="index",
            )
            cnx.create_entity(
                "Subject",
                label="loutre",
                authority=loutre_subj_auth,
                index=(ir, facomp_parent, facomp_child),
                type="subject",
                role="index",
            )
            cnx.create_entity(
                "Geogname",
                label="loutre",
                authority=loutre_location_auth,
                index=facomp_child,
                role="index",
                type="geogname",
            )
            cnx.commit()
        self.loutre_agent_auth_eid = loutre_agent_auth.eid
        self.loutre_subj_auth_eid = loutre_subj_auth.eid
        self.loutre_location_auth_eid = loutre_location_auth.eid
        self.originator_auth_eid = originator_auth.eid
        self.ir_eid = ir.eid
        self.fa_parent_eid = facomp_parent.eid
        self.fa_child_eid = facomp_child.eid

    def _test_public_findingaid_dump_from_esdoc(self, cnx):
        """Build data from an existing ESDocument
        and compare with FindingAid IDumpFullTextIndexSerializable
        """
        res = cnx.system_sql("SELECT * from tmp_findingaid_es").fetchall()
        self.assertEqual(res, [(self.ir_eid, "wfs_cmsobject_draft")])
        service = cnx.entity_from_eid(self.service_eid)
        cacher = CACHER_CLASSES["findingaid"](LOGGER)
        rset = cacher.build_rset(cnx, 1, 0, None)
        schema = "public"
        cacher.setup_iteration_cache(cnx, rset, schema)
        for idx, entity in enumerate(rset.entities(), 1):
            serializer = entity.cw_adapt_to(ETYPES_ADAPTERS.get(entity.cw_etype))
            json_doc = serializer.serialize(complete=False)
            entity.reverse_entity[0].cw_clear_all_caches()
            service = entity.related_service
            expected = env.get_template(f"{entity.stable_id.lower()}.json").render(
                service_eid=self.service_eid,
                service_level=service.level,
                eid=entity.eid,
                loutre=self.loutre_subj_auth_eid,
                originator=self.originator_auth_eid,
            )
            self.maxDiff = None
            expected = json_loads(expected)
            expected["creation_date"] = entity.creation_date.isoformat()
            self.assertDictEqual(expected, json_doc)
            # clear ESDocument cache
            entity.reverse_entity[0].cw_clear_all_caches()
            expected.pop("index_entries")  # not in tested ESDocument
            json_doc = entity.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertDictEqual(expected, json_doc)

    def _test_public_findingaid_dump_from_db(self, cnx):
        """Build data from PostgreSQL  and compare with FindingAid IDumpFullTextIndexSerializable"""
        res = cnx.system_sql("SELECT * from tmp_findingaid_es").fetchall()
        self.assertEqual(res, [(self.ir_eid, "wfs_cmsobject_draft")])
        service = cnx.entity_from_eid(self.service_eid)
        cacher = CACHER_CLASSES["findingaid"](LOGGER)
        rset = cacher.build_rset(cnx, 1, 0, None)
        schema = "public"
        cacher.setup_iteration_cache(cnx, rset, schema, from_db=True)
        for idx, entity in enumerate(rset.entities(), 1):
            serializer = entity.cw_adapt_to(ETYPES_ADAPTERS.get(entity.__regid__))
            json_doc = serializer.serialize_from_db(complete=False)
            expected = env.get_template(f"{entity.stable_id.lower()}.json").render(
                service_eid=self.service_eid,
                service_level=service.level,
                eid=entity.eid,
                loutre=self.loutre_subj_auth_eid,
                originator=self.originator_auth_eid,
            )
            expected = json_loads(expected)
            expected["creation_date"] = entity.creation_date.isoformat()
            self.assertDictEqual(expected, json_doc)

    def _test_public_findingaid_from_db(self, cnx):
        """Test Build data from PostgreSQL with IFullTextIndexSerializable.
        This test suite is not complete to rely on PostgreSQL data to create
        EsDocuments. In particular to index pdf data in the "text" field
        """

        fa = cnx.entity_from_eid(self.ir_eid)
        json_doc = fa.cw_adapt_to("IFullTextIndexSerializable").serialize_from_db()
        service = cnx.entity_from_eid(self.service_eid)
        expected = env.get_template(f"{fa.stable_id.lower()}.json").render(
            service_eid=self.service_eid,
            service_level=service.level,
            eid=fa.eid,
            loutre=self.loutre_subj_auth_eid,
            originator=self.originator_auth_eid,
        )
        expected = json_loads(expected)
        expected["creation_date"] = fa.creation_date.isoformat()
        self.assertCountEqual(
            json_doc.pop("alltext").split(" "), expected.pop("alltext").split(" ")
        )
        index_entries = sort_authorities(json_doc.pop("index_entries"))
        expected_entries = sort_authorities(expected.pop("index_entries"))
        for index, auth in enumerate(index_entries):
            self.assertEqual(auth, expected_entries[index])
        self.assertDictEqual(expected, json_doc)

    def _test_published_findingaid_dump(self, cnx):
        service = cnx.entity_from_eid(self.service_eid)
        cacher = CACHER_CLASSES["findingaid"](LOGGER)
        rset = cacher.build_rset(cnx, 1, 0, None)
        schema = "published"
        cacher.setup_iteration_cache(cnx, rset, schema)
        for idx, entity in enumerate(rset.entities(), 1):
            serializer = entity.cw_adapt_to(ETYPES_ADAPTERS.get(entity.__regid__))
            json_doc = serializer.serialize(complete=False)
            expected = env.get_template(f"{entity.stable_id.lower()}.json").render(
                service_eid=self.service_eid,
                service_level=service.level,
                creation_date=entity.creation_date,
                eid=entity.eid,
                loutre=self.loutre_subj_auth_eid,
                originator=self.originator_auth_eid,
            )
            expected = json_loads(expected)
            expected["creation_date"] = entity.creation_date.isoformat()
            self.assertDictEqual(expected, json_doc)

    def _test_public_facomponents_dump_from_esdoc(self, cnx):
        """Test facomponent IDumpFullTextIndexSerializable adapter"""
        service = cnx.entity_from_eid(self.service_eid)
        cacher = CACHER_CLASSES["facomponent"](LOGGER)
        rset = cacher.build_rset(cnx, 2, 0, None)
        schema = "public"
        cacher.setup_iteration_cache(cnx, rset, schema)
        for idx, entity in enumerate(rset.entities(), 1):
            serializer = entity.cw_adapt_to(ETYPES_ADAPTERS.get(entity.__regid__))
            json_doc = serializer.serialize(complete=False)
            template = f"{entity.stable_id.lower()}.json"
            expected = env.get_template(template).render(
                service_eid=self.service_eid,
                service_level=service.level,
                eid=entity.eid,
                loutre_subj=self.loutre_subj_auth_eid,
                loutre_agent=self.loutre_agent_auth_eid,
                loutre_loc=self.loutre_location_auth_eid,
                originator=self.originator_auth_eid,
            )
            expected = json_loads(expected)
            expected["creation_date"] = entity.creation_date.isoformat()
            index_entries = sort_authorities(json_doc.pop("index_entries"))
            expected_entries = sort_authorities(expected.pop("index_entries"))
            for index, auth in enumerate(index_entries):
                self.assertEqual(auth, expected_entries[index])
            self.assertEqual(entity.reverse_entity[0].doc["stable_id"], entity.stable_id)
            self.assertDictEqual(expected, json_doc)
            # clear ESDocument cache
            entity.reverse_entity[0].cw_clear_all_caches()
            json_doc = entity.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertDictEqual(expected, json_doc)

    def _test_public_facomponents_dump_from_db(self, cnx):
        """Build data from PostgreSQL and compare with
        FAComponent IDumpFullTextIndexSerializable"""
        service = cnx.entity_from_eid(self.service_eid)
        cacher = CACHER_CLASSES["facomponent"](LOGGER)
        rset = cacher.build_rset(cnx, 2, 0, None)
        schema = "public"
        cacher.setup_iteration_cache(cnx, rset, schema)
        for idx, entity in enumerate(rset.entities(), 1):
            serializer = entity.cw_adapt_to(ETYPES_ADAPTERS.get(entity.__regid__))
            json_doc = serializer.serialize(complete=False)
            template = f"{entity.stable_id.lower()}.json"
            expected = env.get_template(template).render(
                service_eid=self.service_eid,
                service_level=service.level,
                eid=entity.eid,
                loutre_subj=self.loutre_subj_auth_eid,
                loutre_agent=self.loutre_agent_auth_eid,
                loutre_loc=self.loutre_location_auth_eid,
                originator=self.originator_auth_eid,
            )
            expected = json_loads(expected)
            json_doc.pop("creation_date")
            index_entries = sort_authorities(json_doc.pop("index_entries"))
            expected_entries = sort_authorities(expected.pop("index_entries"))
            for index, auth in enumerate(index_entries):
                self.assertEqual(auth, expected_entries[index])
            self.assertEqual(entity.reverse_entity[0].doc["stable_id"], entity.stable_id)
            self.assertDictEqual(expected, json_doc)

    def test_esdump(self):
        with self.admin_access.cnx() as cnx:
            self._test_public_findingaid_dump_from_esdoc(cnx)
            self._test_public_findingaid_dump_from_db(cnx)
            self._test_public_findingaid_from_db(cnx)
            self._test_published_findingaid_dump(cnx)
            self._test_public_facomponents_dump_from_esdoc(cnx)
            self._test_public_facomponents_dump_from_db(cnx)


if __name__ == "__main__":
    unittest.main()
