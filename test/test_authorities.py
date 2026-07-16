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

from mock import patch
import unittest

from cubicweb.devtools.testlib import CubicWebTC
from cubicweb_francearchives import Authkey
from cubicweb_francearchives.testutils import PostgresTextMixin, EADImportMixin, create_findingaid
from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename

from pgfixtures import setup_module, teardown_module  # noqa


def get_authority_history(cnx):
    query = """
    SELECT fa_stable_id, type, label, indexrole, autheid
    FROM authority_history"""
    return cnx.system_sql(query).fetchall()


def get_indexed(authority):
    return [f.eid for aut in authority.reverse_authority for f in aut.index]


class GroupAuthoritiesTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {"nodrop": False})

    def setUp(self):
        super(GroupAuthoritiesTests, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity("Service", code="FRAD054", category="foo")
            self.service = cnx.create_entity("Service", code="FRAD0541", category="foo")
            cnx.commit()
            self.location_label = "Nancy (Meurthe-et-Moselle, France)"

    def test_tested_geongnames(self):
        with self.admin_access.cnx() as cnx:
            # assure Nancy (Meurthe-et-Moselle, France) is present in FRAD054_0000000407.xml
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            self.import_filepath(cnx, "ir_data/FRAD054_0000000407.xml")
            fc = cnx.execute(fc_rql, {"u": "31 Fi 47-185"}).one()
            locations = [
                ie.authority[0].label for ie in fc.reverse_index if ie.cw_etype == "Geogname"
            ]
            self.assertEqual(locations[0], self.location_label)

    def test_ungroup_geongname(self):
        """
        Triyng: Ungroup an index
        Expecting: authority_history table is updated
        """
        with self.admin_access.cnx() as cnx:
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            self.import_filepath(cnx, "ir_data/FRAD054_0000000407.xml")
            fc = cnx.execute(fc_rql, {"u": "31 Fi 47-185"}).one()
            location = [ie.authority[0] for ie in fc.reverse_index if ie.cw_etype == "Geogname"][0]
            self.assertEqual(location.label, self.location_label)
            self.assertCountEqual([], get_authority_history(cnx))
            geogname = location.reverse_authority[0]
            locs = set([eid for eid, in cnx.find("LocationAuthority")])
            # ungroup the Geogname
            geogname.new_authority()
            cnx.commit()
            # the newly created LocationAuthority
            loc_eid = list(set([eid for eid, in cnx.find("LocationAuthority")]) - locs)[0]
            self.assertCountEqual(
                [
                    (fc.finding_aid[0].stable_id, "geogname", geogname.label, "index", loc_eid),
                ],
                get_authority_history(cnx),
            )

    def group_locations(self, cnx, loc1, loc2):
        expected_count = len(loc1.reverse_authority) + len(loc2.reverse_authority)
        loc1.group([loc2.eid])
        cnx.commit()
        loc1 = cnx.find("LocationAuthority", eid=loc1.eid).one()
        loc2 = cnx.find("LocationAuthority", eid=loc2.eid).one()
        self.assertFalse(loc2.reverse_authority)
        self.assertEqual(len(loc1.reverse_authority), expected_count)
        self.assertEqual((loc1,), loc2.grouped_with)

    def import_findingaid(self, cnx, loc1, service_infos=None, **custom_settings):
        """
        import a findindaid with geogname Nancy (Meurthe-et-Moselle, France)
        """
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        self.import_filepath(
            cnx, "ir_data/FRAD054_0000000407.xml", service_infos=service_infos, **custom_settings
        )
        fc = cnx.execute(fc_rql, {"u": "31 Fi 47-185"}).one()
        locations = [ie.authority[0] for ie in fc.reverse_index if ie.cw_etype == "Geogname"]
        self.assertEqual(1, len(locations))
        self.assertEqual(loc1.eid, locations[0].eid)
        return locations[0]

    def test_grouped_with_chain(self):
        """
        Create three LocationAuthorities
        Triyng: group loc3 with loc2 and loc2 with loc1
        Expecting: loc2 and loc3 are grouped with loc1
        """
        with self.admin_access.cnx() as cnx:
            loc1 = cnx.create_entity(
                "LocationAuthority",
                label="loc1",
                reverse_authority=cnx.create_entity("Geogname", role="index", label="index loc1"),
            )
            loc2 = cnx.create_entity(
                "LocationAuthority",
                label="loc2",
                reverse_authority=cnx.create_entity("Geogname", role="index", label="index loc2"),
            )
            loc3 = cnx.create_entity(
                "LocationAuthority",
                label="loc3",
                reverse_authority=cnx.create_entity("Geogname", role="index", label="index loc3"),
            )
            cnx.commit()
            loc2.group([loc3.eid])
            cnx.commit()
            loc1.group([loc2.eid])
            cnx.commit()
            loc1 = cnx.find("LocationAuthority", eid=loc1.eid).one()
            loc2 = cnx.find("LocationAuthority", eid=loc2.eid).one()
            loc3 = cnx.find("LocationAuthority", eid=loc3.eid).one()
            self.assertFalse(loc3.reverse_authority)
            self.assertFalse(loc2.reverse_authority)
            self.assertEqual(3, len(loc1.reverse_authority))
            self.assertCountEqual(loc1.reverse_grouped_with, [loc2, loc3])
            self.assertFalse(loc2.reverse_grouped_with)
            self.assertFalse(loc3.reverse_grouped_with)

    def test_service_strict_grouped_authorities(self):
        """
        Triyng: create two orphan LocationAuthority with the same label,
                group them and import an IR containing a geogname with the same label
                under index_policy == 'service/strict'
        Expecting: the newly created Gegoname must not be attached to the grouped
                   LocationAuthority
        """
        with self.admin_access.cnx() as cnx:
            loc2 = cnx.create_entity("LocationAuthority", label=self.location_label)
            loc1 = cnx.create_entity("LocationAuthority", label=self.location_label)
            cnx.commit()
            self.assertEqual(2, cnx.find("LocationAuthority", label=self.location_label).rowcount)
            self.group_locations(cnx, loc1, loc2)
            linked_authority = self.import_findingaid(
                cnx, loc1, autodedupe_authorities="service/strict"
            )
            # the newly created Gegoname must not be attached to the grouped LocationAuthority
            self.assertEqual(loc1.eid, linked_authority.eid)
            # no new LocationAuthority has been created
            self.assertCountEqual(
                [loc1.eid, loc2.eid],
                [e[0] for e in cnx.find("LocationAuthority", label=self.location_label)],
            )

    def test_service_strict_new_authorities(self):
        """Trying: import a FindingAid with index_policy == 'service/strict'
                and 3 similar subjects
        Expecting: 3 new SubjectAuthorities are created
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(
                cnx,
                "ir_data/FRAD092_subject.xml",
                autodedupe_authorities="service/strict",
            )
            expected = ["Léningrad", "leningrad", "LeninGrad?"]
            self.assertCountEqual(
                expected,
                [label[0] for label in cnx.execute("Any L WHERE X is SubjectAuthority, X label L")],
            )
            fc = cnx.find("FindingAid").one()
            #  main_auth = the fist authority found in XML
            main_auth = cnx.find("SubjectAuthority", label="Léningrad").one()
            # XXX Why the FindingAid and FAC component only indexes the main authority
            self.assertEqual(
                fc.reverse_entity[0].doc["index_entries"],
                [
                    {
                        "authfilenumber": None,
                        "authority": main_auth.eid,
                        "authtype": "SubjectAuthority",
                        "label": "Léningrad",
                        "type": "subject",
                    }
                ],
            )
            fa = cnx.find("FAComponent").one()
            self.assertEqual(
                fa.reverse_entity[0].doc["index_entries"],
                [
                    {
                        "authfilenumber": None,
                        "authority": main_auth.eid,
                        "label": "Léningrad",
                        "authtype": "SubjectAuthority",
                        "type": "subject",
                    }
                ],
            )
            for e in cnx.execute("Any X WHERE X is SubjectAuthority").entities():
                index = e.reverse_authority
                self.assertEqual(len(index), 1)
                # XXX Why the main authority  indexes the FindingAid, but not the
                # other indexes?
                if e.eid == main_auth.eid:
                    self.assertCountEqual([fc, fa], index[0].index)
                else:
                    self.assertCountEqual([fa], index[0].index)

    def test_service_normalize_new_authorities(self):
        """Trying: import a FindingAid with index_policy == 'service/normalize'
                and 3 similar subjects (Léningrad, leningrad, LeninGrad (1924-1991))
        Expecting: 1 new SubjectAuthority is created
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(
                cnx,
                "ir_data/FRAD092_subject.xml",
                autodedupe_authorities="service/normalize",
            )
            main_auth = cnx.find("SubjectAuthority").one()
            self.assertEqual(main_auth.label, "Léningrad")  # the first found in xml
            fc = cnx.find("FindingAid").one()
            self.assertEqual(
                fc.reverse_entity[0].doc["index_entries"],
                [
                    {
                        "authfilenumber": None,
                        "authority": main_auth.eid,
                        "label": "Léningrad",
                        "authtype": "SubjectAuthority",
                        "type": "subject",
                    }
                ],
            )
            fa = cnx.find("FAComponent").one()
            self.assertEqual(
                fa.reverse_entity[0].doc["index_entries"],
                [
                    {
                        "authfilenumber": None,
                        "authority": main_auth.eid,
                        "authtype": "SubjectAuthority",
                        "label": "Léningrad",
                        "type": "subject",
                    }
                ],
            )
            indexes = main_auth.reverse_authority
            self.assertEqual(len(indexes), 3)
            for index in indexes:
                if index.label == main_auth.label:
                    self.assertCountEqual([fc, fa], index.index)
                else:
                    self.assertCountEqual([fa], index.index)

    def test_service_strict_orphan_authorities_different_labels(self):
        """
        Triyng: create two orphan LocationAuthority with the different labels,
                group them and import an IR containing a geogname with the same label
                as the LocationAuthority we group in
                under index_policy == 'service/strict'
        Expecting: the newly created Gegoname must not be attached to the grouped
                   LocationAuthority
        """
        with self.admin_access.cnx() as cnx:
            loc1 = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-Moselle, France) regrouped"
            )
            loc2 = cnx.create_entity("LocationAuthority", label=self.location_label)
            cnx.commit()
            self.assertEqual(1, cnx.find("LocationAuthority", label=loc2.label).rowcount)
            self.group_locations(cnx, loc1, loc2)
            linked_authority = self.import_findingaid(
                cnx, loc1, autodedupe_authorities="service/strict"
            )
            # the newly created Gegoname must not be attached to the grouped LocationAuthority
            self.assertEqual(loc1.eid, linked_authority.eid)
            # geogname label is different from the linked_authority label
            self.assertNotEqual(loc1.label, linked_authority.reverse_authority[0].label)
            self.assertEqual(1, cnx.find("LocationAuthority", label=self.location_label).rowcount)

    def test_global_strict_orphan_authorities_different_labels(self):
        """
        Triyng: create two orphan LocationAuthority with different labels,
                group them and import an IR containing a geogname with the same label
                under index_policy == 'global/strict'
        Expecting: the newly created Gegoname must not be attached to the grouped
                   LocationAuthority
        """
        with self.admin_access.cnx() as cnx:
            loc1 = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-Moselle, France) regrouped"
            )
            loc2 = cnx.create_entity("LocationAuthority", label=self.location_label)
            cnx.commit()
            self.group_locations(cnx, loc1, loc2)
            linked_authority = self.import_findingaid(
                cnx, loc1, autodedupe_authorities="global/strict"
            )
            # the newly created Gegoname must not be attached to the grouped LocationAuthority
            self.assertEqual(loc1.eid, linked_authority.eid)
            # geogname label is different from the linked_authority label
            self.assertNotEqual(loc1.label, linked_authority.reverse_authority[0].label)
            self.assertEqual(1, cnx.find("LocationAuthority", label=self.location_label).rowcount)

    def test_authorities_order_service_strict(self):
        """
        Trying: create 4 LocationAuthorities with similar labels and group two of them.
        Expecting: only the authority with grouped in authorities is present in
                   self.reader.all_authorities.values
        """
        with self.admin_access.cnx() as cnx:
            loc2 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            loc3 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            cnx.commit()
            loc4 = cnx.create_entity("LocationAuthority", label="paris (France)")
            loc1 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            cnx.commit()
            loc2.group([loc3.eid, loc4.eid])
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/strict",
            )
            all_authorities = self.reader.all_authorities
            for data in (
                ("LocationAuthority", "paris (France)", 0),
                ("LocationAuthority", "Paris (France)", 0),
            ):
                self.assertEqual(all_authorities[hash(data)], loc2.eid)
            for eid in (loc1.eid, loc3.eid, loc4.eid):
                self.assertNotIn(eid, list(all_authorities.values()))

    def test_authorities_order_global_strict(self):
        """
        Trying: create 4 LocationAuthorities with similar labels and group two of them.
        Expecting: only the authority with grouped in authorities is present in
                   self.reader.all_authorities.values
        """
        with self.admin_access.cnx() as cnx:
            loc2 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            loc3 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            cnx.commit()
            loc4 = cnx.create_entity("LocationAuthority", label="paris (France)")
            loc1 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            cnx.commit()
            loc2.group([loc3.eid, loc4.eid])
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="global/strict",
            )
            all_authorities = self.reader.all_authorities
            for data in (
                ("LocationAuthority", "paris (France)", 0),
                ("LocationAuthority", "Paris (France)", 0),
            ):
                self.assertEqual(all_authorities[hash(data)], loc2.eid)
            for eid in (loc1.eid, loc3.eid, loc4.eid):
                self.assertNotIn(eid, list(all_authorities.values()))

    def test_authorities_order_global_normalize(self):
        """
        Trying: create 4 LocationAuthorities with similar labels and group two of them.
        Expecting: only the authority with grouped in authorities is present in
                   self.reader.all_authorities.values
        """
        with self.admin_access.cnx() as cnx:
            loc2 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            loc3 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            cnx.commit()
            loc4 = cnx.create_entity("LocationAuthority", label="paris (France)")
            loc1 = cnx.create_entity("LocationAuthority", label="Paris (France)")
            cnx.commit()
            loc2.group([loc3.eid, loc4.eid])
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="global/normalize",
            )
            all_authorities = self.reader.all_authorities
            for data in (("LocationAuthority", "paris france", 0),):
                self.assertEqual(all_authorities[hash(data)], loc2.eid)
            for eid in (loc1.eid, loc3.eid, loc4.eid):
                self.assertNotIn(eid, list(all_authorities.values()))

    def test_subject_global_normalize(self):
        """
        Trying: import 2 identical IR for 2 different services with 20 SubjectAuthorities each
                under index_policy == 'global/normalize'
        Expecting: SubjectAuthorities are not duplcated
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="global/normalize",
            )
            subjects = cnx.find("SubjectAuthority")
            self.assertEqual(20, subjects.rowcount)
            self.import_filepath(
                cnx,
                "ir_data/FRAD0541_0000000407.xml",
                autodedupe_authorities="global/normalize",
            )
            subjects = cnx.find("SubjectAuthority")
            self.assertEqual(20, subjects.rowcount)
            for subject in subjects.entities():
                self.assertEqual(2, len(subject.reverse_authority))

    def test_subject_service_normalize(self):
        """
        Trying: import 2 identical IR for 2 different services with 20 SubjectAuthorities each
        Expecting: SubjectAuthorities are not duplicated
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            subjects = cnx.find("SubjectAuthority")
            self.assertEqual(20, subjects.rowcount)
            self.import_filepath(
                cnx,
                "ir_data/FRAD0541_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            subjects = cnx.find("SubjectAuthority")
            self.assertEqual(20, subjects.rowcount)
            for subject in subjects.entities():
                self.assertEqual(2, len(subject.reverse_authority))

    def test_subject_orphan_service_normalize(self):
        """
        Trying: create two SubjectAuthorities and import an IR with
                20 SubjectAuthorities including those
        Expecting: there are still 20 SubjectAuthorities
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("SubjectAuthority", label="Fête")
            cnx.create_entity("SubjectAuthority", label="Fête nationale")
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            subjects = cnx.find("SubjectAuthority")
            self.assertEqual(20, subjects.rowcount)

    def test_grouped_location_history(self):
        """In case locations authorities are grouped,
        only the target autheid must be kept in authority_history
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            loc_label = "Nancy (Meurthe-et-Moselle, France)"
            loc1 = cnx.create_entity("LocationAuthority", label=loc_label)
            loc2 = cnx.create_entity("LocationAuthority", label=loc_label)
            fa1 = create_findingaid(cnx, "eadid1", self.service)
            geog1 = ce(
                "Geogname", role="index", label="index location 1", index=fa1, authority=loc1
            )
            fa2 = create_findingaid(cnx, "eadid2", self.service)
            geog2 = ce(
                "Geogname", role="index", label="index location 2", index=fa2, authority=loc2
            )
            cnx.commit()
            self.assertCountEqual(
                [
                    (fa1.stable_id, "geogname", geog1.label, "index", loc1.eid),
                    (fa2.stable_id, "geogname", geog2.label, "index", loc2.eid),
                ],
                get_authority_history(cnx),
            )
            loc1.group([loc2.eid])
            cnx.commit()
            self.assertCountEqual(
                [
                    (fa1.stable_id, "geogname", geog1.label, "index", loc1.eid),
                    (fa2.stable_id, "geogname", geog2.label, "index", loc1.eid),
                ],
                get_authority_history(cnx),
            )

    def test_grouped_agent_with_fa_commemo_and_extref(self):
        """
        Trying: group an AgentAuthority having linked IRs,CommemorationItem and ExternRef
        Expecting: grouped agent have 0 related entities:
                   IRs, CommemorationItem or ExternRef
        """
        with self.admin_access.cnx() as cnx:
            fa1 = create_findingaid(cnx, "chirac ministre", service=self.service)
            label = "Chirac, Jacques (homme politique, président de la République)"
            index = cnx.create_entity("AgentName", label=label, index=fa1)
            agent = cnx.create_entity("AgentAuthority", label=label, reverse_authority=index)
            cnx.commit()
            fa2 = create_findingaid(cnx, "Jacques Chirac", service=self.service)
            index = cnx.create_entity("AgentName", label="Chirac, Jacques", index=fa2)
            commemo_item = cnx.create_entity(
                "CommemorationItem",
                title="Commemoration",
                alphatitle="commemoration",
                content="content",
                commemoration_year=2019,
            )
            extref = cnx.create_entity(
                "ExternRef", reftype="Virtual_exhibit", title="externref-title"
            )
            grouped_agent = cnx.create_entity(
                "AgentAuthority",
                label="Chirac, Jacques",
                reverse_authority=index,
                reverse_related_authority=[commemo_item, extref],
            )
            cnx.commit()
            agent.group([grouped_agent.eid])
            cnx.commit()
            grouped_agent = cnx.find("AgentAuthority", eid=grouped_agent.eid).one()
            self.assertEqual((), grouped_agent.reverse_related_authority)
            self.assertEqual((), grouped_agent.reverse_authority)
            agent = cnx.find("AgentAuthority", eid=agent.eid).one()
            self.assertCountEqual([commemo_item, extref], agent.reverse_related_authority)
            self.assertCountEqual(
                [fa1.eid, fa2.eid], [fa.eid for i in agent.reverse_authority for fa in i.index]
            )

    def test_orphan_locations(self):
        """
        Trying: create two LocationAuthorities and import an IR with
                9 LocationAuthorities including thoses under `service/normalize` policy
        Expecting: there are still 9 LocationAuthorities
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("LocationAuthority", label="Épinal (Vosges, France)")
            cnx.create_entity("LocationAuthority", label="Londres")
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            locations = cnx.find("LocationAuthority")
            self.assertEqual(9, locations.rowcount)

    def test_subjects_of_basecontent(self):
        """
        Trying: create a ServiceAuthority for a particular BaseContent
                and import an IR with
                20 SubjectAuthorities including it under `service/normalize` policy
        Expecting: there are still 20 SubjectAuthorities
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.find("Service", code="FRAD054").one()
            fete = cnx.create_entity("SubjectAuthority", label="Fête")
            cnx.create_entity(
                "BaseContent", title="title", related_authority=fete, basecontent_service=service
            )
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            subjects = cnx.find("SubjectAuthority")
            self.assertEqual(20, subjects.rowcount)

    def test_locations_of_basecontent(self):
        """
        Trying: create a LocationAuthority for a particular BaseContent
                and import an IR with
                9 LocationAuthorities including it under `service/normalize` policy
        Expecting: there are still 9 LocationAuthorities
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.find("Service", code="FRAD054").one()
            epinal = cnx.create_entity("LocationAuthority", label="Épinal (Vosges, France)")
            cnx.create_entity(
                "BaseContent", title="title", related_authority=epinal, basecontent_service=service
            )
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            locations = cnx.find("LocationAuthority")
            self.assertEqual(9, locations.rowcount)

    def test_quality_authority_order_service_normalized(self):
        """
        Trying: create LocationAuthorities with similar labels one of which is a
                qualified authority.
        Expecting: the newly imported IR is indexed on the qualified authority
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD054", category="foo")
            other_service = cnx.create_entity("Service", code="FRAD051", category="foo")
            loc_orphan = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-Moselle, France)"
            )  # orphan
            loc_qualified = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-MOSELLE, France)", quality=True
            )
            loc_grouped = cnx.create_entity(
                "LocationAuthority", label="Nancy (MEurthe-et-Moselle, France)'"
            )  # grouped with loc_orphan
            ir_FRAD051 = create_findingaid(cnx, "ir_FRAD051", other_service)
            loc_ir_FRAD051 = cnx.create_entity(
                "LocationAuthority",
                label="Nancy (Meurthe-et-Moselle, France)",
                reverse_authority=cnx.create_entity(
                    "Geogname", label="Nancy (Meurthe-et-Moselle, France)", index=ir_FRAD051
                ),
            )
            ir_FRAD054 = create_findingaid(cnx, "ir_FRAD054", service)
            loc_ir_FRAD054 = cnx.create_entity(
                "LocationAuthority",
                label="Nancy (Meurthe-et-Moselle, France)",
                reverse_authority=cnx.create_entity(
                    "Geogname", label="Nancy (Meurthe-et-Moselle, France)", index=ir_FRAD054
                ),
            )
            cnx.commit()
            loc_orphan.group([loc_grouped.eid])
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            all_authorities = self.reader.all_authorities
            # Check that grouped and other service authorities are not
            # considered globally by the reader
            for eid in (loc_grouped.eid, loc_ir_FRAD051.eid):
                self.assertNotIn(eid, list(all_authorities.values()))
            # Check that the qualifed, orphan and FRAD054 service authority are
            # considered globally by the reader
            for eid in (loc_orphan.eid, loc_qualified.eid, loc_ir_FRAD054.eid):
                self.assertIn(eid, list(all_authorities.values()))
            for entity in (loc_orphan, loc_qualified, loc_grouped, loc_ir_FRAD054, loc_ir_FRAD051):
                entity.cw_clear_all_caches()
            new_ir = cnx.execute("Any X WHERE X is FindingAid, X eadid 'FRAD054_0000000407'").one()

            self.assertIn(ir_FRAD054.eid, get_indexed(loc_ir_FRAD054))
            self.assertEqual([ir_FRAD051.eid], get_indexed(loc_ir_FRAD051))
            # Check that only the qualified authority was used to index the imported FA
            indexed_fa = [
                f
                for aut in loc_qualified.reverse_authority
                for f in aut.index
                if f.cw_etype == "FAComponent"
            ]
            self.assertEqual(144, len(indexed_fa))
            for fa in indexed_fa:
                self.assertEqual(new_ir.eid, fa.finding_aid[0].eid)
            # Check that (loc_orphan and loc_grouped) authorities are not used to index the
            #  the imported FA
            for loc in (loc_orphan, loc_grouped):
                self.assertFalse(loc.reverse_authority)

    def test_same_service_authority_order_service_normalized(self):
        """
        Trying: create LocationAuthorities with similar label one of which already indexes
                an IR with the same Service
        Expecting: the newly imported IR is indexed on the authority which already indexes
                an IR with the same Service
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD054", category="foo")
            other_service = cnx.create_entity("Service", code="FRAD051", category="foo")
            loc_orphan = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-Moselle, France)"
            )  # orphan
            loc_grouped = cnx.create_entity(
                "LocationAuthority", label="Nancy (MEurthe-et-Moselle, France)'"
            )  # grouped with loc_orphan
            ir_FRAD051 = create_findingaid(cnx, "ir_FRAD051", other_service)
            loc_ir_FRAD051 = cnx.create_entity(
                "LocationAuthority",
                label="Nancy (Meurthe-et-Moselle, France)",
                reverse_authority=cnx.create_entity(
                    "Geogname", label="Nancy (Meurthe-et-Moselle, France)", index=ir_FRAD051
                ),
            )
            ir_FRAD054 = create_findingaid(cnx, "ir_FRAD054", service)
            loc_ir_FRAD054 = cnx.create_entity(
                "LocationAuthority",
                label="Nancy (Meurthe-et-Moselle, France)",
                reverse_authority=cnx.create_entity(
                    "Geogname", label="Nancy (Meurthe-et-Moselle, France)", index=ir_FRAD054
                ),
            )
            cnx.commit()
            loc_orphan.group([loc_grouped.eid])
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            all_authorities = self.reader.all_authorities
            # Check that grouped and other service authorities are not
            # considered globally by the reader
            for eid in (loc_grouped.eid, loc_ir_FRAD051.eid):
                self.assertNotIn(eid, list(all_authorities.values()))
            # Check that the orphan and FRAD054 service authority are
            # considered globally by the reader
            for eid in (loc_orphan.eid, loc_ir_FRAD054.eid):
                self.assertIn(eid, list(all_authorities.values()))
            for entity in (loc_orphan, loc_grouped, loc_ir_FRAD054, loc_ir_FRAD051):
                entity.cw_clear_all_caches()
            new_ir = cnx.execute("Any X WHERE X is FindingAid, X eadid 'FRAD054_0000000407'").one()

            self.assertIn(ir_FRAD054.eid, get_indexed(loc_ir_FRAD054))
            self.assertEqual([ir_FRAD051.eid], get_indexed(loc_ir_FRAD051))
            # Check that only the FRAD054 authority was used to index the imported FA
            indexed_fa = [
                f
                for aut in loc_ir_FRAD054.reverse_authority
                for f in aut.index
                if f.cw_etype == "FAComponent"
            ]
            self.assertEqual(144, len(indexed_fa))
            for fa in indexed_fa:
                self.assertEqual(new_ir.eid, fa.finding_aid[0].eid)
            # Check that (loc_orphan and loc_grouped) authorities are not used to index the
            #  the imported FA
            for loc in (loc_orphan, loc_grouped):
                self.assertFalse(loc.reverse_authority)

    def test_other_service_authority_order_service_normalized(self):
        """
        Trying: create LocationAuthorities with similar label and no authority which already indexes
                an IR with the same Service
        Expecting: the newly imported IR is indexed on the orphan authority
        """
        with self.admin_access.cnx() as cnx:
            other_service = cnx.create_entity("Service", code="FRAD051", category="foo")
            loc_orphan = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-Moselle, France)"
            )  # orphan
            loc_grouped = cnx.create_entity(
                "LocationAuthority", label="Nancy (MEurthe-et-Moselle, France)'"
            )  # grouped with loc_orphan
            ir_FRAD051 = create_findingaid(cnx, "ir_FRAD051", other_service)
            loc_ir_FRAD051 = cnx.create_entity(
                "LocationAuthority",
                label="Nancy (Meurthe-et-Moselle, France)",
                reverse_authority=cnx.create_entity(
                    "Geogname", label="Nancy (Meurthe-et-Moselle, France)", index=ir_FRAD051
                ),
            )
            cnx.commit()
            loc_orphan.group([loc_grouped.eid])
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            all_authorities = self.reader.all_authorities
            # Check that grouped and other service authorities are not
            # considered globally by the reader
            for eid in (loc_grouped.eid, loc_ir_FRAD051.eid):
                self.assertNotIn(eid, list(all_authorities.values()))
            # Check that the orphan and FRAD054 service authority are
            # considered globally by the reader
            for eid in (loc_orphan.eid,):
                self.assertIn(eid, list(all_authorities.values()))
            for entity in (loc_orphan, loc_grouped, loc_ir_FRAD051):
                entity.cw_clear_all_caches()
            new_ir = cnx.execute("Any X WHERE X is FindingAid, X eadid 'FRAD054_0000000407'").one()

            self.assertEqual([ir_FRAD051.eid], get_indexed(loc_ir_FRAD051))
            # Check that only the orphan authority was used to index the imported FA
            indexed_fa = [
                f
                for aut in loc_orphan.reverse_authority
                for f in aut.index
                if f.cw_etype == "FAComponent"
            ]
            self.assertEqual(144, len(indexed_fa))
            for fa in indexed_fa:
                self.assertEqual(new_ir.eid, fa.finding_aid[0].eid)
            # Check that loc_grouped authority is notxs used to index the
            #  the imported FA
            for loc in (loc_grouped,):
                self.assertFalse(loc.reverse_authority)

    def test_quality_orphan_authority_service_normalized(self):
        """
        Trying: create LocationAuthorities with a similar labels one of which is a
                qualified authority and the other is orphan.
        Expecting: the newly imported IR is indexed on the qualified authority
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Service", code="FRAD054", category="foo")
            loc_orphan = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-Moselle, France)"
            )  # orphan
            loc_qualified = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-MOSELLE, France)", quality=True
            )
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            all_authorities = self.reader.all_authorities
            # Check that the qualifed, orphan  service authority are
            # considered globally by the reader
            for eid in (loc_orphan.eid, loc_qualified.eid):
                self.assertIn(eid, list(all_authorities.values()))
            for entity in (loc_orphan, loc_qualified):
                entity.cw_clear_all_caches()
            new_ir = cnx.execute("Any X WHERE X is FindingAid, X eadid 'FRAD054_0000000407'").one()
            # Check that only the qualified authority was used to index the imported FA
            indexed_fa = [
                f
                for aut in loc_qualified.reverse_authority
                for f in aut.index
                if f.cw_etype == "FAComponent"
            ]
            self.assertEqual(144, len(indexed_fa))
            for fa in indexed_fa:
                self.assertEqual(new_ir.eid, fa.finding_aid[0].eid)
            # Check that (loc_orphan and loc_grouped) authorities are not used to index the
            #  the imported FA
            for loc in (loc_orphan,):
                self.assertFalse(loc.reverse_authority)

    def test_grouping_authority_order_service_normalized(self):
        """
        Trying: create 4 LocationAuthorities with similar labels and group two of them.
        Expecting: the grouping authority is indexed
        """
        with self.admin_access.cnx() as cnx:
            loc_grouping = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-Moselle, France)"
            )
            loc2 = cnx.create_entity(
                "LocationAuthority", label="Nancy (Meurthe-et-MOSELLE, France)"
            )
            loc3 = cnx.create_entity(
                "LocationAuthority", label="Nancy (MEurthe-et-Moselle, France)"
            )
            loc4 = cnx.create_entity(
                "LocationAuthority", label="nancy (Meurthe-et-Moselle, France)"
            )
            cnx.commit()
            loc_grouping.group([loc3.eid, loc4.eid])
            cnx.commit()
            for loc in (loc_grouping, loc2, loc3, loc4):
                loc.cw_clear_all_caches()
            self.assertCountEqual(
                (loc3.eid, loc4.eid), [a.eid for a in loc_grouping.reverse_grouped_with]
            )
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000407.xml",
                autodedupe_authorities="service/normalize",
            )
            all_authorities = self.reader.all_authorities
            # Check that the grouping authority is considered globally by
            # the reader
            for eid in (loc_grouping.eid,):
                self.assertIn(eid, list(all_authorities.values()))
            # Check that grouped authorities are not considered globally by
            # the reader
            for eid in (loc2.eid, loc3.eid, loc4.eid):
                self.assertNotIn(eid, list(all_authorities.values()))
            # Check that only the grouping authority was used to index the FA"
            self.assertTrue(loc_grouping.reverse_authority)
            # "Check that the grouped authorities were not used to index the
            for loc in (loc2, loc3, loc4):
                self.assertFalse(loc.reverse_authority)

    def test_unqualify_grouped_authorities(self):
        """Triyng: create two qualified SubjectAuthority and group them.

        Expecting: the grouped authority is unqualified.
        """
        with self.admin_access.cnx() as cnx:
            label = "Jean Valjean (1769-1833)"
            loc2 = cnx.create_entity("SubjectAuthority", label=label, quality=True)
            loc_grouping = cnx.create_entity("SubjectAuthority", label=label, quality=True)
            cnx.commit()
            self.assertTrue(loc_grouping.quality)
            self.assertTrue(loc2.quality)
            loc_grouping.group([loc2.eid])
            cnx.commit()
            loc_grouping.cw_clear_all_caches()
            loc2.cw_clear_all_caches()
            self.assertEqual((loc_grouping,), loc2.grouped_with)
            self.assertTrue(loc_grouping.quality)
            self.assertFalse(loc2.quality)


class AuthoritiesHistoryTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {"nodrop": False})

    def test_rename_authority_history(self):
        """
        Trying: import an IR and rename one of related AgentAuthority
        Expecting: renamed authority with all indexed IR are present in authority_history table
        """
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRAN_IR_053754.xml"
            self.import_filepath(cnx, filepath)
            old_label = "Mac-mahon (Patrice de), duc de Magenta, maréchal de France"
            main_mac = cnx.find("AgentAuthority", label=old_label).one()
            cnx.commit()
            fa = cnx.find("FindingAid").one()
            indexes = cnx.execute(
                """
                    Any I, IT, IR, IL WHERE I authority X,
                    I type IT, I role IR, I label IL,
                    X eid %(eid)s""",
                {"eid": main_mac.eid},
            )
            related_fa = [
                (
                    Authkey(fa.stable_id, index.type, index.label, index.role).as_tuple(),
                    main_mac.eid,
                )
                for index in indexes.entities()
            ]
            # rename the authority
            new_label = "Mac-Mahon, Patrice de (1808-1893 ; " "duc de Magenta, maréchal de France)"
            main_mac.cw_set(label=new_label)
            cnx.commit()
            cu = cnx.system_sql(
                """
            SELECT fa_stable_id, type, label, indexrole, autheid
            FROM authority_history ORDER BY fa_stable_id"""
            )
            auth_history = []
            for fa_stable_id, type, label, indexrole, auth in cu.fetchall():
                key = Authkey(fa_stable_id, type, label, indexrole)
                auth_history.append((key.as_tuple(), auth))
            self.assertEqual(related_fa, auth_history)

    def test_grouped_authority_history(self):
        """
        Trying: import an IR and group two AgentAuthorities
        Expecting: the grouped authority with the indexed IRs
                   is present in `authority_history` table
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAN_IR_053754.xml")
            main_mac = cnx.find(
                "AgentAuthority",
                label=("Mac-mahon (Patrice de), " "duc de Magenta, maréchal de France"),
            ).one()
            # group the main Mac-Mahon authority with another one
            grouped_mac = cnx.find("AgentAuthority", label="Mac-mahon, duchesse de Magenta").one()
            grouped_index = grouped_mac.reverse_authority[0]
            main_mac.group([grouped_mac.eid])
            cnx.commit()
            # main Mac-Mahon authority is now linked to 2 AgentNames
            self.assertEqual(2, len(main_mac.reverse_authority))
            fa = cnx.find("FindingAid").one()
            related_fa = [
                (
                    Authkey(
                        fa.stable_id, grouped_index.type, grouped_mac.label, grouped_index.role
                    ).as_tuple(),
                    main_mac.eid,
                )
            ]
            cu = cnx.system_sql(
                """
            SELECT fa_stable_id, type, label, indexrole, autheid
            FROM authority_history ORDER BY fa_stable_id"""
            )
            auth_history = []
            for fa_stable_id, type, label, indexrole, auth in cu.fetchall():
                key = Authkey(fa_stable_id, type, label, indexrole)
                auth_history.append((key.as_tuple(), auth))
            self.assertEqual(related_fa, auth_history)

    def filtered_authorities_eids(self, rset):
        """
        PostgresSQL execution of NORMALIZE_ENTRY function do not match with python
        cubicweb_francearchives.dataimport.normalize_entry results
        for punctuations (' ',  '…', '’') and probably for others not ascii characters
         1 u'Deboraüde ?'
            PostgresSQL -> 'deboraude\xa0'
            Python -> 'deboraude'
         2. u'Tavel… (de)'
            PostgresSQL  -> 'de tavel...''
            Python       -> 'de tavel.'
         3. 'Gauthier de rougemont, chef d’escadron'
            PostgresSQL  -> "chef de d'escadron gauthier rougemont"
            Python       -> "chef d'escadron de gauthier rougemont"

        """
        labels = []
        for e in rset.entities():
            if all((" " not in e.label, "…" not in e.label, "’" not in e.label)):
                labels.append(e.eid)
        return labels

    def test_reimport_global_normalize(self):
        """
        Trying: import an IR and rename a related AgentAuthority.
                Delete and reimport the IR under `global/normalize` policy.
        Expecting: no new AgentAutority is created as the renamed authority
               is kept in authority_history
        """
        with self.admin_access.cnx() as cnx:
            filepath = "ir_data/FRAN_IR_053754.xml"
            self.import_filepath(cnx, filepath)
            old_agents = self.filtered_authorities_eids(cnx.find("AgentAuthority"))
            old_label = "Mac-mahon (Patrice de), duc de Magenta, maréchal de France"
            main_mac = cnx.find("AgentAuthority", label=old_label).one()
            main_mac.cw_set(
                label=("Mac-Mahon, Patrice de (1808-1893 ; " "duc de Magenta, maréchal de France)")
            )
            cnx.commit()
            indexed_irs = [
                e[0]
                for e in cnx.execute(
                    """Any SI ORDERBY SI WHERE I authority X, I index F, I label L,
                   F stable_id SI, X eid %(eid)s""",
                    {"eid": main_mac.eid},
                )
            ]
            # delete the imported IR
            delete_from_filename(cnx, "FRAN_IR_053754.xml", interactive=False, esonly=False)
            cnx.commit()
            # check entities are deleted
            self.assertFalse(
                cnx.execute("Any X WHERE X is IN (FindingAid, FAComponent, AgentName)")
            )
            self.import_filepath(cnx, filepath, autodedupe_authorities="global/normalize")
            # assert no new AgentAuthority with old_label has been created
            new_agents = self.filtered_authorities_eids(cnx.find("AgentAuthority"))
            self.assertCountEqual(old_agents, new_agents)
            self.assertFalse(cnx.find("AgentAuthority", label=old_label))
            # test FAComponents are correctly attached to the main_mac authority
            new_indexed_irs = [
                e[0]
                for e in cnx.execute(
                    """Any SI ORDERBY SI  WHERE I authority X, I index F, I label L,
                F stable_id SI, X eid %(eid)s""",
                    {"eid": main_mac.eid},
                )
            ]
            self.assertEqual(indexed_irs, new_indexed_irs)
            cu = cnx.system_sql(
                """
                SELECT fa_stable_id, type, label, indexrole, autheid
                FROM authority_history ORDER BY fa_stable_id"""
            )
            auth_history = []
            for fa_stable_id, type, label, indexrole, auth in cu.fetchall():
                key = Authkey(fa_stable_id, type, label, indexrole)
                auth_history.append((key.as_tuple(), auth))
            expected = [
                (
                    ("01c7b52c477ca45a3589858bc25203e0011a660c", "persname", old_label, "index"),
                    main_mac.eid,
                )
            ]
            self.assertEqual(expected, auth_history)

    def create_bergbieten(self, cnx, link_fa=True):
        """
        Create a FindingAid with service TEST01 service different from the
        imported in tests IRs
        """
        kwargs = {}
        if link_fa:
            service = cnx.create_entity("Service", code="TEST01", category="L")
            fa = create_findingaid(cnx, "test", service)
            kwargs = {"index": fa}
        index = cnx.create_entity("Geogname", label="BERGBIETEN", **kwargs)
        return cnx.create_entity("LocationAuthority", label="BERGBIETEN", reverse_authority=index)

    def test_orphan_location_bergbieten_global_normalize(self):
        """
        Trying: Create an orphan LocationAutority with BERGBIETEN geogname.
                Import 2 IRs with BERGBIETEN geognames from an other service
                under `global/normalize` policy
        Expecting: only one LocationAuthority BERGBIETEN is created with 3 linkend geognames
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            bergbieten = self.create_bergbieten(cnx, link_fa=False)
            cnx.commit()
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="global/normalize",
                )
            loc = cnx.find("LocationAuthority", label="BERGBIETEN").one()
            self.assertEqual(loc.eid, bergbieten.eid)
            self.assertEqual(3, len(loc.reverse_authority))

    def test_different_service_location_bergbieten_global_normalize(self):
        """
        Create an IR with BERGBIETEN geogname from TEST01 service.

        Trying: Import 2 IRs with BERGBIETEN geognames from FRAD067 service
                under `global/normalize` policy
        Expecting: only one LocationAuthority BERGBIETEN is found
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            bergbieten = self.create_bergbieten(cnx)
            cnx.commit()
            self.assertEqual(1, len(bergbieten.reverse_authority))
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="global/normalize",
                )
            loc = cnx.find("LocationAuthority", label="BERGBIETEN").one()
            self.assertEqual(loc.eid, bergbieten.eid)
            self.assertEqual(3, len(loc.reverse_authority))

    def test_orphan_location_bergbieten_service_strict(self):
        """
        Create an orphan LocationAutority with BERGBIETEN geogname.

        Trying: Import 2 IRs with BERGBIETEN geognames from another service
                under `service/strict` policy
        Expecting: two LocationAuthorities BERGBIETEN, one per service, are created
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            bergbieten = self.create_bergbieten(cnx, link_fa=False)
            cnx.commit()
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="service/strict",
                )
            bergbietens = list(cnx.find("LocationAuthority", label="BERGBIETEN").entities())
            self.assertEqual(2, len(bergbietens))
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            self.assertEqual(1, len(bergbieten.reverse_authority))
            new_bergbieten = [e for e in bergbietens if e.eid != bergbieten.eid][0]
            self.assertEqual(2, len(new_bergbieten.reverse_authority))

    def test_location_different_service_bergbieten_service_strict(self):
        """
        Create an IR with BERGBIETEN geogname from TEST01 service.

        Trying: Import 2 IRs with BERGBIETEN geognames from FRAD067 service
                under 'service/strict' policy
        Expecting: two LocationAuthorities BERGBIETEN for each service are created
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            bergbieten = self.create_bergbieten(cnx)
            cnx.commit()
            self.assertEqual(1, len(bergbieten.reverse_authority))
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="service/strict",
                )
            bergbietens = list(cnx.find("LocationAuthority", label="BERGBIETEN").entities())
            self.assertEqual(2, len(bergbietens))
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            new_bergbieten = [e for e in bergbietens if e.eid != bergbieten.eid][0]
            self.assertEqual(2, len(new_bergbieten.reverse_authority))

    def test_location_same_service_bergbieten_service_strict(self):
        """
        Trying: Create an IR with BERGBIETEN geogname from FRAD067 service.
                Then import 2 IRs with BERGBIETEN geognames from FRAD067 service
                under `service/strict` policy
        Expecting: one LocationAuthority BERGBIETEN
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            fa = create_findingaid(cnx, "test", service=service)
            index = cnx.create_entity("Geogname", label="BERGBIETEN", index=fa)
            bergbieten = cnx.create_entity(
                "LocationAuthority", label="BERGBIETEN", reverse_authority=index
            )
            cnx.commit()
            self.assertEqual(1, len(bergbieten.reverse_authority))
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="service/strict",
                )
            loc = cnx.find("LocationAuthority", label="BERGBIETEN").one()
            self.assertEqual(bergbieten.eid, loc.eid)
            self.assertEqual(3, len(loc.reverse_authority))

    def test_renamed_location_global_normalize(self):
        """
        Create a LocationAuthority with an indexed IR and rename it into BERGBIETEN.

        Trying: Import 2 IR with BERGBIETEN geognames under `global/normalize` policy.
        Expecting: only one LocationAuthority BERGBIETEN is found
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            fa = create_findingaid(cnx, "test", service)
            index = cnx.create_entity("Geogname", label="BERGBIETEN", index=fa)
            bergbieten = cnx.create_entity(
                "LocationAuthority", label="Bergbieten (Bas-Rhin, France)", reverse_authority=index
            )
            cnx.commit()
            bergbieten.cw_set(label="BERGBIETEN")
            cnx.commit()
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="global/normalize",
                )
            loc = cnx.find("LocationAuthority", label="BERGBIETEN").one()
            self.assertEqual(bergbieten.eid, loc.eid)
            self.assertEqual(3, len(loc.reverse_authority))

    def test_renamed_same_service_location_service_strict_orphan(self):
        """
        Create an orphan LocationAuthority with an indexed IR from FRAD067 service
                and rename it into BERGBIETEN.
        Trying: Import 2 IR with BERGBIETEN geognames from FRAD067 service
                under `service/strict` policy
        Expecting: only one LocationAuthority BERGBIETEN is created
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            fa = create_findingaid(cnx, "test", service)
            index = cnx.create_entity("Geogname", label="BERGBIETEN", index=fa)
            bergbieten = cnx.create_entity(
                "LocationAuthority", label="Bergbieten (Bas-Rhin, France)", reverse_authority=index
            )
            cnx.commit()
            bergbieten.cw_set(label="BERGBIETEN")
            cnx.commit()
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="service/strict",
                )
            bergbieten = cnx.find("LocationAuthority", label="BERGBIETEN").one()
            self.assertEqual(3, len(bergbieten.reverse_authority))

    def _renamed_location_reimport(self, autodedupe_authorities):
        """
        Create import 2 IR with BERGBIETEN geognames from FRAD067 service,
                and rename it into Bergbieten (Bas-Rhin, France) .
        Trying: re-import same IRs
        Expecting: no new BERGBIETEN authority is created
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            cnx.commit()
            filenames = (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archivses_paroissiales.xml",
            )
            for filename in filenames:
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities=autodedupe_authorities,
                )
            bergbieten = cnx.find("LocationAuthority", label="BERGBIETEN").one()
            self.assertEqual(2, len(bergbieten.reverse_authority))
            bergbieten.cw_set(label="Bergbieten (Bas-Rhin, France)")
            cnx.commit()
            self.assertCountEqual(
                [
                    (
                        "105e079883af01b25a11a29cce861bf6d42739b9",
                        "geogname",
                        "BERGBIETEN",
                        "index",
                        bergbieten.eid,
                    ),
                    (
                        "1c25ab836c01ee06986f7946a2bf98c8dd569f4d",
                        "geogname",
                        "BERGBIETEN",
                        "index",
                        bergbieten.eid,
                    ),
                ],
                get_authority_history(cnx),
            )
            # delete the imported IR
            for filename in filenames:
                delete_from_filename(cnx, filename, interactive=False, esonly=False)
            cnx.commit()
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            self.assertEqual(0, len(bergbieten.reverse_authority))
            for filename in filenames:
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities=autodedupe_authorities,
                )
            self.assertFalse(cnx.find("LocationAuthority", label="BERGBIETEN"))
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            self.assertEqual(2, len(bergbieten.reverse_authority))

    def test_renamed_same_service_location_service_strict_reimport(self):
        """
        Create import 2 IR with BERGBIETEN geognames from FRAD067 service,
                and rename it into Bergbieten (Bas-Rhin, France) .
        Trying: re-import same IRs under `service/strict` policy
        Expecting: no new BERGBIETEN authority is created
        """
        self._renamed_location_reimport("service/strict")

    def test_renamed_same_service_location_global_normalize_reimport(self):
        """
        Create import 2 IR with BERGBIETEN geognames from FRAD067 service,
                and rename it into Bergbieten (Bas-Rhin, France) .
        Trying: re-import same IRs under `global/normalize` policy
        Expecting: no new BERGBIETEN authority is created
        """
        self._renamed_location_reimport("global/normalize")

    def _renamed_location_same_normalized_label_reimport(self, autodedupe_authorities):
        """
        Create import an IR with 'Aïn Touta, Commune mixte (Algérie)'
                geognames from FRANOM service,
                and rename it into 'Aïn Touta (Algérie, Commune mixte)'
                witch is the same as
                NORMALIZED_ENTRY('Aïn Touta, Commune mixte (Algérie))'.
        Trying: re-import the same IR
        Expecting: no new 'Aïn Touta, Commune mixte (Algérie)' is created
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRANOM", category="L")
            cnx.commit()
            filename = "FRANOM_93202_11.xml"
            self.import_filepath(
                cnx,
                f"ir_data/{filename}",
                service_info={"code": service.code, "eid": service.eid},
                autodedupe_authorities=autodedupe_authorities,
            )
            ain_touta = cnx.find(
                "LocationAuthority", label="Aïn Touta, Commune mixte (Algérie)"
            ).one()
            self.assertEqual(1, len(ain_touta.reverse_authority))
            ain_touta.cw_set(label="Aïn Touta (Algérie, Commune mixte)")
            cnx.commit()
            # delete the imported IR
            delete_from_filename(cnx, filename, interactive=False, esonly=False)
            cnx.commit()
            ain_touta = cnx.find("LocationAuthority", eid=ain_touta.eid).one()
            self.assertEqual(0, len(ain_touta.reverse_authority))
            self.import_filepath(
                cnx,
                f"ir_data/{filename}",
                service_info={"code": service.code, "eid": service.eid},
                autodedupe_authorities=autodedupe_authorities,
            )
            self.assertFalse(
                cnx.find("LocationAuthority", label="Aïn Touta, Commune mixte (Algérie)")
            )
            ain_touta = cnx.find("LocationAuthority", eid=ain_touta.eid).one()
            self.assertEqual(1, len(ain_touta.reverse_authority))

    def test_renamed_normalized_location_service_strict_reimport(self):
        """
        Create import an IR with 'Aïn Touta, Commune mixte (Algérie)'
                geognames from FRANOM service
                and rename it into 'Aïn Touta (Algérie, Commune mixte)'
                with is the same as
                NORMALIZED_ENTRY('Aïn Touta, Commune mixte (Algérie))'.
        Trying: re-import the same IR under `service/strict` policy
        Expecting: no new 'Aïn Touta, Commune mixte (Algérie)' is created
        """
        self._renamed_location_same_normalized_label_reimport("service/strict")

    def test_renamed_normalized_location_global_normalize_reimport(self):
        """
        Create import an IR with 'Aïn Touta, Commune mixte (Algérie)'
                geognames from FRANOM service
                and rename it into 'Aïn Touta (Algérie, Commune mixte)'
                with is the same as
                NORMALIZED_ENTRY('Aïn Touta, Commune mixte (Algérie))'.
        Trying: re-import the same IR under `global/normalize` policy
        Expecting: no new 'Aïn Touta, Commune mixte (Algérie)' is created
        """
        self._renamed_location_same_normalized_label_reimport("global/normalize")

    def test_renamed_grouped_location_global_normalize(self):
        """
        Trying: Create a LocationAuthority BERGBIETEN with an indexed IR from TEST01 service.
                Create a LocationAuthority with an indexed IR from FRAD067 service
                and rename it into BERGBIETEN.
                Group the first BERGBIETEN into the second.
                Import 2 IR with BERGBIETEN geognames under `global/normalize` policy.
        Expecting: two LocationAuthority BERGBIETEN exist, but only the second have indexes
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            bergbieten = self.create_bergbieten(cnx)
            cnx.commit()
            self.assertEqual(1, len(bergbieten.reverse_authority))
            fa = create_findingaid(cnx, "test2", service)
            index = cnx.create_entity("Geogname", label="BERGBIETEN", index=fa)
            renamed_bergbieten = cnx.create_entity(
                "LocationAuthority", label="Bergbieten (Bas-Rhin, France)", reverse_authority=index
            )
            cnx.commit()
            renamed_bergbieten.cw_set(label="BERGBIETEN")
            cnx.commit()
            renamed_bergbieten = cnx.find("LocationAuthority", eid=renamed_bergbieten.eid).one()
            self.assertEqual(1, len(renamed_bergbieten.reverse_authority))
            renamed_bergbieten.group([bergbieten.eid])
            cnx.commit()
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            self.assertEqual(0, len(bergbieten.reverse_authority))
            renamed_bergbieten = cnx.find("LocationAuthority", eid=renamed_bergbieten.eid).one()
            self.assertEqual(2, len(renamed_bergbieten.reverse_authority))
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="global/normalize",
                )
            self.assertCountEqual(
                [renamed_bergbieten.eid, bergbieten.eid],
                [e[0] for e in cnx.find("LocationAuthority", label="BERGBIETEN")],
            )
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            self.assertEqual(0, len(bergbieten.reverse_authority))
            renamed_bergbieten = cnx.find("LocationAuthority", eid=renamed_bergbieten.eid).one()
            self.assertEqual(4, len(renamed_bergbieten.reverse_authority))

    def test_renamed_grouped_same_service_location_service_strict(self):
        """
        Trying: Create a LocationAuthority BERGBIETEN with an indexed IR from TEST01 service.
                Create a LocationAuthority with an indexed IR from FRAD067 service
                and rename it into BERGBIETEN.
                Group the first BERGBIETEN into the second.
                Import 2 IR with BERGBIETEN geognames under `service/strict` policy.
        Expecting: two LocationAuthority BERGBIETEN exist, but only the second have indexes
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            bergbieten = self.create_bergbieten(cnx)
            cnx.commit()
            self.assertEqual(1, len(bergbieten.reverse_authority))
            fa = create_findingaid(cnx, "test2", service)
            index = cnx.create_entity("Geogname", label="BERGBIETEN", index=fa)
            renamed_bergbieten = cnx.create_entity(
                "LocationAuthority", label="Bergbieten (Bas-Rhin, France)", reverse_authority=index
            )
            cnx.commit()
            renamed_bergbieten.cw_set(label="BERGBIETEN")
            cnx.commit()
            renamed_bergbieten = cnx.find("LocationAuthority", eid=renamed_bergbieten.eid).one()
            self.assertEqual(1, len(renamed_bergbieten.reverse_authority))
            renamed_bergbieten.group([bergbieten.eid])
            cnx.commit()
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            self.assertEqual(0, len(bergbieten.reverse_authority))
            renamed_bergbieten = cnx.find("LocationAuthority", eid=renamed_bergbieten.eid).one()
            self.assertEqual(2, len(renamed_bergbieten.reverse_authority))
            for filename in (
                "FRAD067_EDF1_archives_communales_deposees.xml",
                "FRAD067_EDF1_archives_paroissiales.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filename}",
                    service_info={"code": service.code, "eid": service.eid},
                    autodedupe_authorities="service/strict",
                )
            self.assertCountEqual(
                [renamed_bergbieten.eid, bergbieten.eid],
                [e[0] for e in cnx.find("LocationAuthority", label="BERGBIETEN")],
            )
            bergbieten = cnx.find("LocationAuthority", eid=bergbieten.eid).one()
            self.assertEqual(0, len(bergbieten.reverse_authority))
            renamed_bergbieten = cnx.find("LocationAuthority", eid=renamed_bergbieten.eid).one()
            self.assertEqual(4, len(renamed_bergbieten.reverse_authority))

    def test_group_locations_with_same_as(self):
        """
        Trying: Create two LocationAuthority BERGBIETEN with the same same_as reference
                Group the second BERGBIETEN into the first.
        Expecting: the grouped BERGBIETEN has no more same_as.
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD067", category="L")
            bergbieten1 = self.create_bergbieten(cnx)
            cnx.commit()
            fa = create_findingaid(cnx, "test2", service)
            index = cnx.create_entity("Geogname", label="BERGBIETEN", index=fa)
            bergbieten2 = cnx.create_entity(
                "LocationAuthority", label="Bergbieten (Bas-Rhin, France)", reverse_authority=index
            )
            cnx.create_entity(
                "ExternalUri",
                uri="https://fr.wikipedia.org/wiki/BERGBIETEN1",
                label="BERGBIETEN1",
                same_as=bergbieten1.eid,
            )
            cnx.create_entity(
                "ExternalUri",
                uri="https://fr.wikipedia.org/wiki/BERGBIETEN2",
                label="BERGBIETEN2",
                same_as=bergbieten2.eid,
            )
            cnx.commit()
            bergbieten1 = cnx.find("LocationAuthority", eid=bergbieten1.eid).one()
            bergbieten2 = cnx.find("LocationAuthority", eid=bergbieten2.eid).one()
            self.assertEqual(["BERGBIETEN1"], [same.label for same in bergbieten1.same_as])
            self.assertEqual(["BERGBIETEN2"], [same.label for same in bergbieten2.same_as])
            bergbieten1.group([bergbieten2.eid])
            cnx.commit()
            bergbieten1 = cnx.find("LocationAuthority", eid=bergbieten1.eid).one()
            bergbieten2 = cnx.find("LocationAuthority", eid=bergbieten2.eid).one()
            self.assertEqual(["BERGBIETEN1"], [same.label for same in bergbieten1.same_as])
            self.assertEqual([], [same.label for same in bergbieten2.same_as])


class AuthoritiesTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {"nodrop": False})

    def setUp(self):
        super(AuthoritiesTests, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity("Service", code="FRAD017", category="foo")
            cnx.commit()

    def test_normalized_labels_normalize(self):
        """
        Trying: import a IR with spelling writing of Oléron, île d'(Charente-Maritime ; France
                under `service/normalize` policy.
        Expecting: Only one Oléron authority is created
        """
        with self.admin_access.cnx() as cnx:
            for filepath in (
                "frad017_258j.xml",
                "frad017_12fi_rome_stdenis.xml",
                "frad017_cartespostales1418-v2.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filepath}",
                    service_info={"code": self.service.code, "eid": self.service.eid},
                    autodedupe_authorities="service/normalize",
                )
            oleron = cnx.execute(
                """Any X, L WHERE X is LocationAuthority,
                       X label L, X label ILIKE 'oléron%'"""
            ).one()
            expected = [
                "Oléron, île d' (Charente-Maritime, France )",
                "Oléron, île d' (Charente-Maritime, France)",
                "Oléron, île d'(Charente-Maritime ; France)",
            ]
            for index in oleron.reverse_authority:
                self.assertIn(index.label, expected)
            self.assertEqual(3, len(oleron.reverse_authority))

    def test_normalized_labels_strict(self):
        """
        Trying: import a IR with different spelling of Oléron, île d'(Charente-Maritime ; France
                under `service/strict` policy.
        Expecting: 3 Oléron authorites are created
        """
        with self.admin_access.cnx() as cnx:
            for filepath in (
                "frad017_258j.xml",
                "frad017_12fi_rome_stdenis.xml",
                "frad017_cartespostales1418-v2.xml",
            ):
                self.import_filepath(
                    cnx,
                    f"ir_data/{filepath}",
                    service_info={"code": self.service.code, "eid": self.service.eid},
                    autodedupe_authorities="service/strict",
                )
            rset = cnx.execute(
                """Any X, L WHERE X is LocationAuthority,
                       X label L, X label ILIKE 'oléron%'"""
            )
            expected = [
                "Oléron, île d' (Charente-Maritime, France )",
                "Oléron, île d' (Charente-Maritime, France)",
                "Oléron, île d'(Charente-Maritime ; France)",
            ]
            for eid, label in rset:
                self.assertIn(label, expected)
            self.assertEqual(3, rset.rowcount)

    def test_duplicated_subjects(self):
        """
        Trying: import an IR services with 20 SubjectAuthorities each
                under index_policy == 'global/normalize'
        Expecting: SubjectAuthority arm��e is duplicated because
                python normalize_entry("arm��e") == "arm__e"
                sql NORMALIZE_ENTRY("arm��e") == "arm��e"
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("SubjectAuthority", label="arm��e")
            cnx.create_entity("SubjectAuthority", label="armée de terre")
            cnx.commit()
            self.import_filepath(
                cnx,
                "ir_data/FRAD054_0000000405.xml",
                autodedupe_authorities="global/normalize",
            )
            subjects = cnx.find("SubjectAuthority")
            self.assertEqual(3, subjects.rowcount)
            rset = cnx.find("SubjectAuthority", label="arm��e")
            self.assertEqual(2, rset.rowcount)


def mock_unindex(authority):
    # skip the reindex in es part of unindex method
    authority._cw.execute(
        "DELETE {index_type} I WHERE I authority E, E eid %(eid)s".format(
            index_type=authority.index_etype
        ),
        {"eid": authority.eid},
    )


class DeleteAuthoritiesTests(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts({}, EADImportMixin.readerconfig, {"nodrop": False})

    def setUp(self):
        super(DeleteAuthoritiesTests, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity("Service", code="FRAD054", category="foo")
            self.service = cnx.create_entity("Service", code="FRAD0541", category="foo")
            cnx.commit()
            self.location_label = "Nancy (Meurthe-et-Moselle, France)"

    @patch("cubicweb_francearchives.entities.indexes.AbstractAuthority.unindex", new=mock_unindex)
    def test_delete_blacklisted_authority(self):
        """
        Trying: import an IR, group 'SUCCESSION' with SubjectAuthority "TABLE ALPHABETIQUE"
                and delete SubjectAuthority "TABLE ALPHABETIQUE"

        Expecting: the SubjectAuthority and its grouped Authorities are deleted.
        """
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
        with self.admin_access.cnx() as cnx:
            filepath = "FRAD095_00374.xml"
            self.import_filepath(cnx, filepath)
            fc = cnx.execute(fc_rql, {"u": "3Q7 753 - 773"}).one()
            subjects = [(i.label, i.type) for i in fc.subject_indexes().entities()]
            expected = [
                ("ENREGISTREMENT", "subject"),
                ("SUCCESSION", "subject"),
                ("TABLE ALPHABETIQUE", "genreform"),
            ]
            self.assertCountEqual(expected, subjects)
            subject = cnx.find("SubjectAuthority", label="TABLE ALPHABETIQUE").one()
            cnx.create_entity(
                "ExternalUri",
                uri="https://fr.wikipedia.org/wiki/TABLE ALPHABETIQUE",
                label="TABLE ALPHABETIQUE",
                same_as=subject.eid,
            )
            cnx.commit()
            grouped = cnx.find("SubjectAuthority", label="SUCCESSION").one()
            grouped.cw_set(label="test")
            cnx.commit()
            self.assertEqual(
                [
                    (
                        "f5051f99c331da3e2da1464b6374dd4917c00b8e",
                        "subject",
                        "SUCCESSION",
                        "index",
                        grouped.eid,
                    )
                ],
                get_authority_history(cnx),
            )
            grouped.cw_set(grouped_with=subject)
            cnx.commit()
            fc.cw_clear_all_caches()
            mock_unindex(subject)
            subject.delete_blacklisted()
            self.assertFalse(cnx.find("SubjectAuthority", eid=subject.eid))
            self.assertFalse(cnx.find("SubjectAuthority", eid=grouped.eid))
            self.assertEqual([], get_authority_history(cnx))
            self.assertCountEqual(
                [("ENREGISTREMENT", "subject")],
                [(i.label, i.type) for i in fc.subject_indexes().entities()],
            )


if __name__ == "__main__":
    unittest.main()
