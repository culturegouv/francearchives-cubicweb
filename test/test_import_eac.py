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
from itertools import count
from os.path import join, dirname
import unittest

from cubicweb import devtools  # noqa

from cubicweb.dataimport.importer import SimpleImportLog
from cubicweb_eac.dataimport import EACCPFImporter
from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.dataimport import eac
from cubicweb_francearchives.testutils import PostgresTextMixin, EACImportMixin

from pgfixtures import setup_module, teardown_module  # noqa


class EACXMLParserTC(unittest.TestCase):
    @classmethod
    def datapath(cls, *fname):
        """joins the object's datadir and `fname`"""
        return join(dirname(__file__), "data", "eac", *fname)

    def file_extentities(self, fname):
        fpath = self.datapath(fname)
        import_log = SimpleImportLog(fpath)
        # Use a predictable extid_generator.
        extid_generator = map(str, count()).__next__
        importer = EACCPFImporter(fpath, import_log, str, extid_generator=extid_generator)
        return importer.external_entities()

    def test_disabled_relations(self):
        etypes = set(
            [
                ext_entity.etype
                for ext_entity in self.file_extentities("FRAD033_EAC_00001_simplified.xml")
            ]
        )
        expected = set(
            (
                "EACResourceRelation",
                "ChronologicalRelation",
                "HierarchicalRelation",
                "AssociationRelation",
                "ExternalUri",
            )
        )
        self.assertFalse(expected.difference(etypes))


class EACImportTC(EACImportMixin, PostgresTextMixin, WebCWTC):

    def test_import_eac_files(self):
        """Test import eac

        Trying: Import 2 eac notices
        Expecting: 2 AuthorityRecords are created
        """
        with self.admin_access.cnx() as cnx:
            fspaths = [
                self.eac_filepath("FRAN_NP_010232.xml"),
                self.eac_filepath("FRAN_NP_010931.xml"),
            ]
            self.massif_import_files(cnx, fspaths)
            record_ids = [
                r[0]
                for r in cnx.execute("Any R ORDERBY R WHERE A record_id R, A is AuthorityRecord")
            ]
            self.assertEqual(["FRAN_NP_010232", "FRAN_NP_010931"], record_ids)
            services_codes = [
                r[0]
                for r in cnx.execute(
                    "Any C ORDERBY C WHERE A is AuthorityRecord, A maintainer S, S code C"
                )
            ]
            self.assertEqual(["FRAN", "FRAN"], services_codes)

    def test_import_invalid_eac(self):
        """Test do not import invalid eac notice

        Trying: Import an eac notice without <control><record_id> tag
        Expecting: no AuthorityRecord created
        """
        with self.admin_access.cnx() as cnx:
            fspaths = [self.eac_filepath("FRAN_NP_150159_bis.xml")]
            self.massif_import_files(cnx, fspaths)
            self.assertFalse(cnx.execute("Any X WHERE X is AuthorityRecord"))

    def test_maintenance_events(self):
        """Test maintenance events import an AuthorityRecord

        Trying: import a Noitce
        Expecting: no AuthorityRecord created
        """
        with self.admin_access.cnx() as cnx:
            fspaths = [self.eac_filepath("FRAN_NP_150159.xml")]
            self.massif_import_files(cnx, fspaths)
            r = cnx.execute("Any X WHERE X is AuthorityRecord").one()
            self.assertEqual(
                [("Creation date", "25 novembre 2015"), ("Identifier", "FRAN_NP_050159")],
                r.cw_adapt_to("entity.main_props").metadata(),
            )

    def test_authority_same_as_authorityrecord(self):
        """Test `same_as` relation between an AgentAuthority and the corresponding
        AuthorityRecord

        Trying: Create an AgentAuthority with a `authfilenumber` and import
        related eac notices
        Expecting: AgentAuthority is linked to the
        corresponding AuthorityRecord through an same_as relation

        """
        with self.admin_access.cnx() as cnx:
            agentname = cnx.create_entity(
                "AgentName", label="Pijeau, Nicolas Charles", authfilenumber="FRAN_NP_010931"
            )
            agent = cnx.create_entity(
                "AgentAuthority", label="Pijeau, Nicolas Charles", reverse_authority=agentname
            )
            cnx.commit()
            fspaths = [
                self.eac_filepath("FRAN_NP_010232.xml"),
                self.eac_filepath("FRAN_NP_010931.xml"),
            ]
            self.massif_import_files(cnx, fspaths)
            cnx.find("AuthorityRecord", record_id="FRAN_NP_010232").one()
            authrec_010931 = cnx.find("AuthorityRecord", record_id="FRAN_NP_010931").one()
            agent = cnx.find("AgentAuthority", eid=agent.eid).one()
            self.assertEqual(agent.same_as[0].eid, authrec_010931.eid)

    def test_authority_filter_related_authorities(self):
        """Test `authorities` method that return the views of
        the related authorities which possess at least
        one related FindingAid, ExternRef or CommemorationItem

        Trying: Create an authority record with related
        authorities

        Expecting: Only the authorities that have related
        elements are returned by the method
        """
        with self.admin_access.cnx() as cnx:
            did = cnx.create_entity("Did", unittitle="qsjkgqhgkqjghqfgkdh")
            faheader = cnx.create_entity("FAHeader")
            findingAid = cnx.create_entity(
                "FindingAid",
                name="FA test",
                fa_header=faheader,
                did=did,
                eadid="TEST",
                publisher="TEST",
                stable_id="sdklhgdifqjhgùqdfjhfdjhdq",
            )
            agent = cnx.create_entity("AgentAuthority", label="Pijeau, Nicolas Charles")
            cnx.create_entity(
                "AgentName",
                label="Pijeau, Nicolas Charles",
                authfilenumber="FRAN_NP_010232",
                index=findingAid,
                authority=agent,
            )
            agent2 = cnx.create_entity("AgentAuthority", label="Pijeau, Nicolas Charles2")
            cnx.create_entity(
                "AgentName",
                label="Pijeau, Nicolas Charles2",
                authfilenumber="FRAN_NP_010232",
                authority=agent2,
            )
            cnx.commit()
            fspaths = [self.eac_filepath("FRAN_NP_010232.xml")]
            self.massif_import_files(cnx, fspaths)
            authrec = cnx.find("AuthorityRecord", record_id="FRAN_NP_010232").one()
            agent = cnx.find("AgentAuthority", eid=agent.eid).one()
            agent2 = cnx.find("AgentAuthority", eid=agent2.eid).one()
            expected = f"""<ul class="fr-list eac-related-productors">
<li>{agent.view("outofcontext")}</li>
</ul>\n"""  # noqa
            self.assertEqual(dict(authrec.authorities)["all_archives_label"], expected)
            cnx.create_entity(
                "CommemorationItem",
                alphatitle="TITLE",
                title="sdkljfghkljsd",
                commemoration_year=42,
                related_authority=agent2,
            )
            cnx.commit()
            authrec = cnx.find("AuthorityRecord", record_id="FRAN_NP_010232").one()
            print(dict(authrec.authorities)["all_archives_label"])
            expected = f"""<ul class="fr-list eac-related-productors">
<li>{agent.view("outofcontext")}</li>
<li>{agent2.view("outofcontext")}</li>
</ul>\n"""  # noqa
            print(repr(expected))
            self.assertEqual(dict(authrec.authorities)["all_archives_label"], expected)

    def test_patch_authorized_name_entries(self):
        """Test on the overloading of `build_name_entry`
        from cubicweb_eac to select the authorized name
        using a convention used by the french archive
        system.

        Trying:
        Three name entries with one authorized.

        Expecting:
        One authorized is detected
        """
        with self.admin_access.cnx() as cnx:
            fspath = self.eac_filepath("FRAF_notice_type_EAC.xml")
            self.massif_import_files(cnx, [fspath])
            record = cnx.execute("Any X WHERE X is AuthorityRecord").one()
            self.assertEqual(record.record_id, "FRAN_0001")
            names = record.reverse_name_entry_for
            self.assertEqual(len(names), 3)
            for name in names:
                if name.parts == (
                    "\xc9l\xe9ment contenant une forme du nom d\u2019une"
                    " collectivit\xe9, d\u2019une personne ou d\u2019une\n"
                    "               famille. L\u2019\xe9l\xe9ment Forme "
                    "dque l\u2019entit\xe9 puisse \xeatre identifi\xe9e "
                    "avec certitude et\n               distingu\xe9e des"
                    " autres qui portent un nom semblable ou similaire."
                ):
                    self.assertEqual(name.form_variant, "authorized")
                else:
                    self.assertNotEqual(name.form_variant, "authorized")

    def test_remove_authority_with_sameas_relations(self):
        """Test on the deletion of the same_as relationships
        which link AuthorityRecords and AgentAuthorities
        """
        with self.admin_access.cnx() as cnx:
            agent = cnx.create_entity(
                "AgentAuthority",
                label="TESTAGENT",
                reverse_authority=cnx.create_entity(
                    "AgentName", label="TESTAGENT", authfilenumber="FRAN_0001"
                ),
            )
            cnx.commit()
            fspath = self.eac_filepath("FRAF_notice_type_EAC.xml")
            self.massif_import_files(cnx, [fspath])
            record = cnx.execute("Any X WHERE X is AuthorityRecord").one()
            self.assertEqual(record.record_id, "FRAN_0001")
            agent = cnx.find("AgentAuthority", eid=agent.eid).one()
            self.assertEqual(record.eid, agent.same_as[0].eid)
            record.cw_delete()
            cnx.commit()

    def test_import_authority_with_existing_sameas(self):
        """Test AuthorityRecord import with existing ExternalUrl"""
        with self.admin_access.cnx() as cnx:
            urls = [
                "https://data.bnf.fr/ark:/12148/cb11865019j",
                "https://www.wikidata.org/wiki/Q1168019",
                "https://catalogue.bnf.fr/ark:/12148/cb11865019j",
                "https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000360157/",
            ]
            for url in urls:
                cnx.create_entity("ExternalUri", uri=url)
            cnx.commit()
            fspath = self.eac_filepath("FRAN_NP_053078.xml")
            self.massif_import_files(cnx, [fspath])
            record = cnx.execute("Any X WHERE X is AuthorityRecord").one()
            self.assertEqual(record.record_id, "FRAN_NP_053078")
            urls.extend(
                [
                    "d5blonb3ky--u69ytier8ih6",
                    "FRAN_IR_059679",
                    "FRAN_IR_060007",
                    "FRAN_NP_005223",
                    "https://www.wikidata.org/wiki/Q11680199",
                ]
            )
            got = [u for u, in cnx.execute("Any U WHERE X is ExternalUri, X uri U")]
            self.assertEqual(sorted(urls), sorted(got))
            cnx.commit()

    def test_patch_date_range_on_name_entries(self):
        """Teston the overloading of `build_name_entry`
        from cubicweb_eac that <dateRange> handling is still correct.

        Trying: Import eac Notes

        Expecting: Date ranges are correctly processed
        """
        with self.admin_access.cnx() as cnx:
            fspath = self.eac_filepath("FRAF_notice_type_EAC.xml")
            self.massif_import_files(cnx, [fspath])
            record = cnx.execute("Any X WHERE X is AuthorityRecord").one()
            self.assertEqual(record.record_id, "FRAN_0001")
            date = cnx.execute(
                """
            Any N WHERE X record_id %(r)s, N name_entry_for X,
            N parts %(p)s, N date_relation D""",
                {"r": "FRAN_0001", "p": "Forme parallèle du nom"},
            ).one()
            self.assertEqual(date.start_date, datetime.date(1981, 1, 1))
            self.assertEqual(date.end_date, datetime.date(1986, 1, 1))

    def test_externaluri_to_related_authority(self):
        """Test ExternalUri are replaced into AuthorityRecords if exists

        Trying: Create 2 eac notices, one by one
        Expecting: ExternalUri has been replaced by the AuthorityRecord and deleted
        corresponding AuthorityRecord through an same_as relation

        """
        with self.admin_access.cnx() as cnx:
            eac.eac_import_files(cnx, [self.eac_filepath("FRAN_NP_010232.xml")])
            cnx.commit()
            exturi = cnx.execute('Any X WHERE X is ExternalUri, X cwuri "FRAN_NP_010931"').one()
            association_rel = exturi.reverse_association_to[0]
            # import the notice with FRAN_NP_010931 record_id
            self.massif_import_files(cnx, [self.eac_filepath("FRAN_NP_010931.xml")])
            authrec_010931 = cnx.find("AuthorityRecord", record_id="FRAN_NP_010931").one()
            association_rel.cw_clear_all_caches()
            # ensure the external uri has been replaced by the authorirty record and deleted
            self.assertEqual(1, len(association_rel.association_to))
            self.assertEqual(association_rel.association_to[0].eid, authrec_010931.eid)
            self.assertFalse(cnx.execute('Any X WHERE X is ExternalUri, X cwuri "FRAN_NP_010931"'))

    def test_import_support(self):
        """Test AuthorityRecord support file exists

        Trying: Create an AuthorityRecord
        Expecting: xml_support is not Null
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.eac_filepath("FRAN_NP_010232.xml")
            eac.eac_import_files(cnx, [filepath])
            cnx.commit()
            ar = cnx.find("AuthorityRecord").one()
            self.assertEqual(ar.xml_support, filepath)

    def test_place_agents(self):
        """Test <cpfDescription><places> of AuthorityRecord

        Trying: Create an AuthorityRecord
        Expecting: <cpfDescription><places> tag is imported
        """
        with self.admin_access.cnx() as cnx:
            filepath = self.eac_filepath("FRAN_NP_004652.xml")
            eac.eac_import_files(cnx, [filepath])
            cnx.commit()
            ar = cnx.find("AuthorityRecord").one()
            places_agent = ar.reverse_place_agent
            nomLieu = []
            for place_agent in places_agent:
                self.assertEqual("Lieu de Paris", place_agent.role)
                for place in place_agent.place_entry_relation:
                    if place.local_type == "nomLieu":
                        nomLieu.append(place.name)
            expected = [
                "Siège social : 32 avenue de la Sibelle, 75014 Paris",
                "Siège social : 23 rue Daviel, 75013 Paris",
                "Siège social : 66 boulevard Haussmann, 75008 Paris",
                "Siège social : 47 avenue de la Chaussée d\u2019Antin, 75009 Paris",
            ]
            self.assertCountEqual(expected, nomLieu)

    def test_import_ape_eac_files(self):
        """Import EAC notices and test ape_eac_files are generated

        Trying: Import 2 EAC notices
        Expecting: 2 AuthorityRecords are created and their ApeEAC files are generated
        """
        with self.admin_access.cnx() as cnx:
            fspaths = [
                self.eac_filepath("FRAN_NP_010232.xml"),
                self.eac_filepath("FRAN_NP_010931.xml"),
            ]
            self.massif_import_files(cnx, fspaths)
            ar1 = cnx.find("AuthorityRecord", record_id="FRAN_NP_010931").one()
            ar2 = cnx.find("AuthorityRecord", record_id="FRAN_NP_010232").one()
            self.assertEqual(len(ar1.ape_eac_file), 1)
            self.assertEqual(len(ar2.ape_eac_file), 1)

    def test_defferrable_constraints_tables(self):
        with self.admin_access.cnx() as cnx:
            expected = {
                "close_match_relation",
                "convention_of_relation",
                "created_by_relation",
                "cw_activity",
                "cw_agentfunction",
                "cw_agentkind",
                "cw_agentplace",
                "cw_associationrelation",
                "cw_authorityrecord",
                "cw_chronologicalrelation",
                "cw_citation",
                "cw_concept",
                "cw_conceptscheme",
                "cw_convention",
                "cw_cwetype",
                "cw_cwsource",
                "cw_cwuser",
                "cw_dateentity",
                "cw_eacfunctionrelation",
                "cw_eacotherrecordid",
                "cw_eacresourcerelation",
                "cw_eacsource",
                "cw_externaluri",
                "cw_familyrelation",
                "cw_generalcontext",
                "cw_hierarchicalrelation",
                "cw_historicalevent",
                "cw_history",
                "cw_identityrelation",
                "cw_legalstatus",
                "cw_mandate",
                "cw_nameentry",
                "cw_occupation",
                "cw_parallelnames",
                "cw_placeentry",
                "cw_postaladdress",
                "cw_source_relation",
                "cw_structure",
                "date_relation_relation",
                "entities",
                "equivalent_concept_relation",
                "exact_match_relation",
                "has_citation_relation",
                "has_event_relation",
                "is_instance_of_relation",
                "is_relation",
                "owned_by_relation",
                "parallel_names_of_relation",
                "place_entry_relation_relation",
                "same_as_relation",
                "simple_name_relation_relation",
                "vocabulary_source_relation",
            }
            self.assertEqual(expected, eac.eac_foreign_key_tables(cnx.vreg.schema))


if __name__ == "__main__":
    unittest.main()
