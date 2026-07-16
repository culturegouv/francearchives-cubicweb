# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
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
import unittest

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives.testutils import (
    PostgresTextMixin,
    EADImportMixin,
    create_findingaid,
)
from cubicweb_francearchives.entities.indexes import GroupAuthorityError
from cubicweb_francearchives.hooks import AuthorityIntegrityError
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id

from pgfixtures import setup_module, teardown_module  # noqa


class AuthoritiesHookTests(PostgresTextMixin, EADImportMixin, CubicWebTC):
    def setUp(self):
        super(AuthoritiesHookTests, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity("Service", code="FRAD054", category="foo")
            cnx.commit()
            self.location_label = "Nancy (Meurthe-et-Moselle, France)"

    def test_delete_index_target(self):
        """Remove the Index taget"""
        with self.admin_access.repo_cnx() as cnx:
            ce = cnx.create_entity
            agent = ce("AgentAuthority", label="Jean Jean")
            ce(
                "NominaRecord",
                stable_id=compute_nomina_stable_id(self.service.code, "42"),
                json_data={"p": [{"kn": "Valjean"}], "t": "RM"},
                service=self.service.eid,
                same_as=agent,
            )
            externref = ce(
                "ExternRef",
                reftype="Virtual_exhibit",
                url="http://toto",
                title="toto",
                related_authority=agent,
            )
            cnx.commit()
            cnx.execute("DELETE ExternRef X")
            cnx.commit()
            self.assertTrue(cnx.find("AgentAuthority", eid=agent.eid))
            self.assertFalse(cnx.find("ExternRef", eid=externref.eid))

    def test_delete_index_authority(self):
        """
        Triyng: delete the AgentAuthority linked to an ExternRef
        Expecting: AgentAuthority is not deleted
        """

        with self.admin_access.repo_cnx() as cnx:
            ce = cnx.create_entity
            agent = ce("AgentAuthority", label="Jean Jean")
            ce(
                "NominaRecord",
                stable_id=compute_nomina_stable_id(self.service.code, "42"),
                json_data={"p": [{"n": "Valjean"}], "t": "RM"},
                service=self.service.eid,
                same_as=agent,
            )
            externref = ce(
                "ExternRef",
                reftype="Virtual_exhibit",
                url="http://toto",
                title="toto",
                related_authority=agent,
            )
            cnx.commit()
            with self.assertRaises(AuthorityIntegrityError):
                cnx.execute("DELETE AgentAuthority X")
                cnx.commit()
            self.assertTrue(cnx.find("AgentAuthority", eid=agent.eid))
            self.assertTrue(cnx.find("ExternRef", eid=externref.eid))

    def test_grouped_authority_indexes(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce("LocationAuthority", label="location 1")
            loc2 = ce("LocationAuthority", label="location 2")
            loc3 = ce("LocationAuthority", label="location 3")
            fa1 = create_findingaid(cnx, "eadid1", self.service)
            ce("Geogname", label="index location 1", index=fa1, authority=loc1)
            fa2 = create_findingaid(cnx, "eadid2", self.service)
            ce("Geogname", label="index location 2", index=fa2, authority=loc2)
            fa3 = create_findingaid(cnx, "eadid3", self.service)
            ce("Geogname", label="index location 3", index=fa3, authority=loc3)
            cnx.commit()
            loc2.group((loc3.eid,))
            loc1.group((loc2.eid,))
            cnx.commit()
            loc1 = cnx.find("LocationAuthority", eid=loc1).one()
            loc2 = cnx.find("LocationAuthority", eid=loc2).one()
            loc3 = cnx.find("LocationAuthority", eid=loc3).one()
            for fa in (fa1, fa2, fa3):
                fa = cnx.find("FindingAid", eid=fa).one()
                fa_index = fa.reverse_index[0]
                self.assertEqual(fa_index.authority[0].eid, loc1.eid)

    def test_grouped_authority_check_pipeline(self):
        """
        Triyng: group an authority with an existing grouped authority."
        Expecting: authorities cannot be grouped with a grouped authority.
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce("LocationAuthority", label="location 1")
            loc2 = ce("LocationAuthority", label="location 2")
            loc3 = ce("LocationAuthority", label="location 3")
            cnx.commit()
            loc2.group((loc1.eid,))
            cnx.commit()
            loc1 = cnx.find("LocationAuthority", eid=loc1).one()
            loc2 = cnx.find("LocationAuthority", eid=loc2).one()
            loc3 = cnx.find("LocationAuthority", eid=loc3).one()
            self.assertEqual(loc2.eid, loc1.grouped_with[0].eid)
            self.assertEqual((), loc2.grouped_with)
            self.assertEqual((), loc3.grouped_with)
            loc2.group((loc3.eid,))
            cnx.commit()
            loc1 = cnx.find("LocationAuthority", eid=loc1).one()
            loc2 = cnx.find("LocationAuthority", eid=loc2).one()
            loc3 = cnx.find("LocationAuthority", eid=loc3).one()
            self.assertEqual(loc2.eid, loc1.grouped_with[0].eid)
            self.assertEqual((), loc2.grouped_with)
            self.assertEqual(loc2.eid, loc3.grouped_with[0].eid)
            with self.assertRaises(GroupAuthorityError):
                loc1.group((loc2.eid,))
                cnx.commit()

    def test_grouped_authority_check_simple_cycle_ko(self):
        """
        Triyng: group an authority with a grouped authority
        Expecting: authorities can not be grouped with a grouped authority
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc1 = ce("LocationAuthority", label="location 1")
            loc2 = ce("LocationAuthority", label="location 2")
            cnx.commit()
            loc1.group((loc2.eid,))
            cnx.commit()
            loc1 = cnx.find("LocationAuthority", eid=loc1).one()
            loc2 = cnx.find("LocationAuthority", eid=loc2).one()
            self.assertEqual(loc1.eid, loc2.grouped_with[0].eid)
            with self.assertRaises(GroupAuthorityError):
                loc2.group((loc1.eid,))
                cnx.commit()

    def test_delete_non_orphan_authorities(self):
        """
        Create non-orphan Authorities by IR import
        Triyng: delete the Authorities
        Expecting: Authorities are not deleted
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/strict",
            )
            for count, etype in (
                (9, "LocationAuthority"),
                (24, "AgentAuthority"),
                (20, "SubjectAuthority"),
            ):
                authorities = cnx.find(etype)
                self.assertEqual(count, authorities.rowcount)
                for eid in authorities:
                    with self.assertRaises(AuthorityIntegrityError):
                        cnx.execute(
                            "DELETE {etype} X WHERE X eid {eid}".format(etype=etype, eid=eid[0])
                        )
                        cnx.commit()

    def test_delete_non_orphan_subject_authority(self):
        """
        Create a SubjectAuthority related to a Concept linked to the Circular

        Triyng: delete the SubjectAuthority
        Expecting: SubjectAuthority is not deleted
        """
        with self.admin_access.cnx() as cnx:
            subject = cnx.create_entity("SubjectAuthority", label="foo")
            cnx.create_entity("Subject", label="foo", authority=subject)
            scheme = cnx.create_entity("ConceptScheme", title="foo")
            concept = cnx.create_entity("Concept", same_as=(subject,), in_scheme=scheme)
            cnx.create_entity(
                "Label", language_code="fr", kind="preferred", label="foo", label_of=concept
            )
            cnx.commit()
            cnx.create_entity(
                "Circular",
                circ_id="circ01",
                title="Circular",
                status="in-effect",
                business_field=concept,
            )
            with self.assertRaises(AuthorityIntegrityError):
                cnx.execute("DELETE SubjectAuthority X WHERE X eid {eid}".format(eid=subject.eid))
            cnx.commit()

    def test_delete_non_orphan_authorities_with_indexes(self):
        """
        Triyng: create non-orphan Authorities with indexes and try to delete them
        Expecting: Authority are not deleted
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc = ce(
                "LocationAuthority",
                label="LocationAuthority",
                reverse_authority=ce("Geogname", label="LocationAuthority"),
            )
            agent = ce(
                "AgentAuthority",
                label="AgentAuthority",
                reverse_authority=ce("AgentName", label="AgentAuthority"),
            )
            subject = ce(
                "SubjectAuthority",
                label="SubjectAuthority",
                reverse_authority=ce("Subject", label="SubjectAuthority"),
            )
            cnx.commit()
            for authority in (loc, subject, agent):
                with self.assertRaises(AuthorityIntegrityError):
                    cnx.entity_from_eid(authority.eid).cw_delete()
                    cnx.commit()

    def test_delete_orphan_authorities(self):
        """
        Triyng: create orphan Authorities and delete them
        Expecting: Authorities are deleted
        """
        with self.admin_access.cnx() as cnx:
            loc = cnx.create_entity("LocationAuthority", label="LocationAuthority")
            agent = cnx.create_entity("AgentAuthority", label="AgentAuthority")
            subject = cnx.create_entity("SubjectAuthority", label="SubjectAuthority")
            cnx.commit()
            for authority, etype in (
                (loc, "LocationAuthority"),
                (subject, "SubjectAuthority"),
                (agent, "AgentAuthority"),
            ):
                cnx.transaction_data["blacklist"] = True
                cnx.execute(
                    "DELETE {etype} X WHERE X eid {eid}".format(etype=etype, eid=authority.eid)
                )
                cnx.commit()


if __name__ == "__main__":
    unittest.main()
