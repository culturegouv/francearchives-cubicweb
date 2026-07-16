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
import unittest

from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives import IIIF_MANIFEST_ROLE

from cubicweb_francearchives.testutils import PostgresTextMixin, EADImportMixin, find_component

from pgfixtures import setup_module, teardown_module  # noqa


class EADImporterTC(EADImportMixin, PostgresTextMixin, WebCWTC):
    @classmethod
    def init_config(cls, config):
        super(EADImporterTC, cls).init_config(config)
        config.set_option("instance-type", "consultation")

    def setup_database(self):
        super(EADImporterTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                category="?",
                name="FRCND",
                short_name="FRCND",
                code="FRCND",
            )
            cnx.commit()

    def test_no_iiif_extprt(self):
        """
        Trying: import IR from LIGEO with <c><dig><uniid><extptr> with no ark
        Expecting: iiif dao are not created
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAN",
                category="L",
                name="Archives nationales",
                iiif_extptr=True,
                iiif_ead_policy="iiif_ligeo_extptr",
            )
            cnx.commit()
            filepath = "ir_data/FRAN_IR_053754.xml"
            self.import_filepath(cnx, filepath)
            for fc in cnx.execute("Any X WHERE X is FAComponent").entities():
                if fc.digitized_urls and fc.did[0].extptr:
                    pass
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(s)s"
            fc = cnx.execute(fc_rql, {"s": "Portraits de dames"}).one()
            # no manifest as extptr is not an ark
            extptr = "https://www.siv.archives-nationales.culture.gouv.fr/siv/rechercheconsultation/consultation/ir/consultationIR.action?udId=c-4c79w78y4-1al5dxbf1q4be&irId=FRAN_IR_053754"  # noqa
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            self.assertTrue(fc.digitized_urls)
            iiif_dv = [dv for dv in fc.digitized_versions if dv.role == IIIF_MANIFEST_ROLE]
            self.assertFalse(iiif_dv)
            self.assertIsNone(fc.iiif_manifest)
            # no manifest as there is no digitized_urls
            for fc in cnx.execute(fc_rql, {"s": "Mou - My"}).entities():
                self.assertTrue(fc.did[0].extptr)
                self.assertFalse(fc.digitized_urls)
                self.assertIsNoe(fc.iiif_manifest)
            self.assertFalse(self.get_iiif_manifests(cnx))

    def test_iiif_ligeo_extptr(self):
        """
        Trying: import IR from LIGEO with <c><dig><uniid><extptr> with arks
        Expecting: iiif dao are created
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD034",
                category="L",
                name="Hérault",
                iiif_extptr=True,
                iiif_ead_policy="iiif_ligeo_extptr",
            )
            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRAD034_194EDT.xml")
            fc = find_component(cnx, "194 EDT 25")
            extptr = "https://archives-pierresvives.herault.fr/ark:/37279/vtacd9a36865ad5e5d3"
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            self.assertTrue(fc.digitized_urls)
            self.assertEqual(3, len(fc.digitized_versions))
            iiif_manifest = [
                dv.url for dv in fc.digitized_versions if dv.role == IIIF_MANIFEST_ROLE
            ][0]
            self.assertEqual(iiif_manifest, f"{extptr}/manifest")
            self.assertEqual(fc.iiif_manifest_url, f"{extptr}/manifest")
            expected = self.get_iiif_manifests(cnx)
            self.assertEqual(21, len(expected))
            self._test_ape_ead_iiif_daos(cnx, expected)

    def test_no_iiif_ligeo_extptr_with_viewer(self):
        """
        Trying: import IR from LIGEO with <c><dig><uniid><extptr> with arks
        and a viewer dao
        Expecting: iiif dao is created
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD034",
                category="L",
                name="Hérault",
                iiif_extptr=True,
                iiif_ead_policy="iiif_ligeo_extptr",
            )
            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRAD034_194EDT.xml")
            fc = find_component(cnx, "194 EDT 9")
            extptr = "https://archives-pierresvives.herault.fr/ark:/37279/vta19b1548ac10ced00"
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            # there is no digitized_urls
            self.assertTrue(fc.digitized_urls)
            iiif_manifest = [
                dv.url for dv in fc.digitized_versions if dv.role == IIIF_MANIFEST_ROLE
            ][0]
            self.assertEqual(iiif_manifest, f"{extptr}/manifest")
            self.assertEqual(fc.iiif_manifest_url, f"{extptr}/manifest")

    def test_no_iiif_ligeo_extptr(self):
        """
        Trying: import IR from LIGEO with <c><dig><uniid><extptr> with arks but no digitized dao
        Expecting: iiif dao is not created
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD034",
                category="L",
                name="Hérault",
                iiif_extptr=True,
                iiif_ead_policy="iiif_ligeo_extptr",
            )
            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRAD034_194EDT.xml")
            fc = find_component(cnx, "194 EDT 3")
            extptr = "https://archives-pierresvives.herault.fr/ark:/37279/vta87ef415b69ff7467"
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            # there is no digitized_urls
            self.assertFalse(fc.digitized_urls)
            self.assertFalse(fc.digitized_versions)
            self.assertFalse(fc.iiif_manifest)

    def test_no_iiif_ligeo_extptr_with_thumbnail(self):
        """
        Trying: import IR from LIGEO with <c><dig><uniid><extptr> with arks
        but no digitized dao except thumbnail
        Expecting: iiif dao is not created
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD034",
                category="L",
                name="Hérault",
                iiif_extptr=True,
                iiif_ead_policy="iiif_ligeo_extptr",
            )
            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRAD034_194EDT.xml")
            fc = find_component(cnx, "194 EDT 8")
            extptr = "https://archives-pierresvives.herault.fr/ark:/37279/vtafdaa272402b05d6c"
            self.assertEqual(extptr, fc.did[0].extptr)
            self.assertTrue(fc.did[0].extptr)
            self.assertEqual(0, len(fc.digitized_urls))
            self.assertEqual("thumbnail", fc.digitized_versions[0].role)
            self.assertFalse(fc.iiif_manifest)

    def test_iiif_FRBNF(self):
        """
        Trying: import IR for FRBNF
        Expecting: iiif dao are created
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRBNF",
                category="L",
                iiif_extptr=True,
                iiif_ead_policy="iiif_bnf",
            )

            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRBNF_EAD000096744.xml")
            fc = find_component(cnx, "2011/001/0227")
            self.assertEqual(1, len(fc.digitized_urls))
            self.assertEqual(
                "https://gallica.bnf.fr/ark:/12148/btv1b530312939", fc.digitized_urls[0]
            )
            iiif_manifest = [
                dv.url for dv in fc.digitized_versions if dv.role == IIIF_MANIFEST_ROLE
            ][0]
            expected = "https://gallica.bnf.fr/iiif/ark:/12148/btv1b530312939/manifest.json"  # noqa
            self.assertEqual(expected, iiif_manifest)
            self.assertEqual(expected, fc.iiif_manifest_url)
            expected = self.get_iiif_manifests(cnx)
            self.assertEqual(816, len(expected))
            self._test_ape_ead_iiif_daos(cnx, expected)

    def test_iiif_ajlsm_FRAD053(self):
        """FRBNF service with manifests"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD053",
                category="L",
                iiif_extptr=True,
                iiif_ead_policy="iiif_ajlsm",
            )

            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRAD053_L-Z_EF.xml")
            fc = find_component(cnx, "1516 W 7")
            expected = "https://archives.lamayenne.fr/archives-en-ligne/ark:/37963/r693006zzv2rnk/f1?context=ead::FRAD053_1516W_BV_de-7"  # noqa
            self.assertEqual(expected, fc.digitized_urls[0])
            iiif_manifest = [
                dv.url for dv in fc.digitized_versions if dv.role == IIIF_MANIFEST_ROLE
            ][0]
            expected = "https://archives.lamayenne.fr/archives-en-ligne/iiif/ark:/37963/r693006zzv2rnk/manifest.json"  # noqa
            self.assertEqual(expected, iiif_manifest)
            self.assertEqual(expected, fc.iiif_manifest_url)
            expected = self.get_iiif_manifests(cnx)
            self.assertEqual(2, len(expected))
            self._test_ape_ead_iiif_daos(cnx, expected)

    def test_dao(self):
        """
        Trying : Import a FindingAid with a dao that has
          a role over 128 chars
        Expecting: the dao role is truncated
        """
        url = "https://www.siv.archives-nationales.culture.gouv.fr/mm/media/download/FRDAFAN85_OF9v173541_L-min.jpg"  # noqa
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAN_IR_051016_excerpt.xml")
            fc = cnx.find("FAComponent", component_order=0).one()
            self.assertEqual(len(fc.digitized_versions), 2)
            self.assertEqual(fc.illustration_url, url)
            for dao in fc.digitized_versions:
                if dao.url and dao.url.endswith("_N-min"):
                    # truncated dao role
                    self.assertEqual(
                        dao.role,
                        "Chaque département concerné, au sein du versement 19860711, a fait l'objet d'un répertoire numérique. Des renseignements complém",  # noqa
                    )
                if dao.illustration_url and dao.illustration_url.endswith("_L-min.jpg"):
                    self.assertEqual(dao.role, "thumbnail")
                if dao.url and dao.url.endswith("_M-min"):
                    self.assertFalse(dao.role)

    def test_daogrp(self):
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD095_00374.xml")
            comp = find_component(cnx, "3Q7 1 - 752")
            self.assertEqual(len(comp.digitized_versions), 0)
            comp = find_component(cnx, "3Q7 1 - 7")
            self.assertEqual(len(comp.digitized_versions), 0)
            comp = find_component(cnx, "3Q7 753")
            for i in (3, 4, 5):
                comp = find_component(cnx, f"3Q7 75{i}")
                expected = [(d.role, d.url, d.illustration_url) for d in comp.digitized_versions]
                self.assertEqual(
                    expected,
                    [
                        (
                            "thumbnail",
                            None,
                            f"/FRAD095_00374/FRAD095_3Q7_75{i}/FRAD095_3Q7_75{i}_0001.jpg",
                        )
                    ],
                )
                self.assertFalse(comp.digitized_urls)
                self.assertFalse(comp.illustration_url)

    def test_daogrp_GREFA(self):
        """Test Digitized Versions

        Trying: do not specify iiif_ead_policy
        Expecting: iiif_manifest is correctly retrieved

        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                code="GREFA",
                category="L",
                name="Ecole française d’Athènes",
                iiif_extptr=True,
            )
            cnx.commit()
            self.assertIsNone(service.iiif_ead_policy)
            self.import_filepath(cnx, "ir_data/GREFA_IM_Delphes.xml")
            comp = find_component(cnx, "Photothèque : E905")
            expected = [
                (
                    "",
                    "https://archimage.efa.gr/image_request_iiif/1907/full/200,/0/default.jpg",
                    "thumbnail",
                ),
                ("https://archimage.efa.gr//?r=visionneuse_iiif&id=1907", "", "viewer"),
                (
                    "https://archimage.efa.gr//action.php?r=iiif_json_manifest&id=1907",
                    "",
                    "iiif_manifest",
                ),
            ]
            self.assertEqual(
                expected,
                sorted(
                    [
                        (dv.url or "", dv.illustration_url or "", dv.role)
                        for dv in comp.digitized_versions
                    ]
                ),
            )
            self.assertEqual(
                "https://archimage.efa.gr//action.php?r=iiif_json_manifest&id=1907",
                comp.iiif_manifest,
            )
            self.assertEqual(
                "https://archimage.efa.gr/image_request_iiif/1907/full/200,/0/default.jpg",
                comp.illustration_url,
            )
            self.assertEqual(
                "https://archimage.efa.gr//?r=visionneuse_iiif&id=1907", comp.digitized_urls[0]
            )

            expected = self.get_iiif_manifests(cnx)
            self.assertEqual(3, len(expected))
            self._test_ape_ead_iiif_daos(cnx, expected)

    def test_daogrp_GREFA_iiif_not_digitized(self):
        """Test Digitized Versions

        Trying: add a dao without iii-role and no digitized dao
        Expecting: iiif_manifest is correctly retrieved

        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                code="GREFA",
                category="L",
                name="Ecole française d’Athènes",
                iiif_extptr=True,
            )
            cnx.commit()
            self.assertIsNone(service.iiif_ead_policy)
            self.import_filepath(cnx, "ir_data/GREFA_IM_Delphes.xml")
            comp = find_component(cnx, "Photothèque : E906")
            self.assertEqual(
                "https://archimage.efa.gr/vtae0897032ffb2bd0b.manifest.json", comp.iiif_manifest
            )

            expected = self.get_iiif_manifests(cnx)
            self.assertEqual(3, len(expected))
            self._test_ape_ead_iiif_daos(cnx, expected)

    def test_iiif_bnf_with_existing_manifest(self):
        """
        Trying: import with URL already containing /manifest or .json
        Expecting: manifest URL is preserved as-is
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                code="FRAD080",
                category="L",
                iiif_extptr=True,
                iiif_ead_policy="iiif_bnf",
            )
            cnx.commit()
            self.import_filepath(cnx, "ir_data/FRAD080_test_manifest.xml")

            # Test component 1 with /manifest
            fc1 = find_component(cnx, "TEST_001")
            expected1 = "https://archives.somme.fr/ark:/58483/hvmz5n1jx9sc/manifest"
            iiif_manifest1 = [
                dv.url for dv in fc1.digitized_versions if dv.role == IIIF_MANIFEST_ROLE
            ][0]
            self.assertEqual(expected1, iiif_manifest1)
            self.assertEqual(expected1, fc1.iiif_manifest_url)

            # Test component 2 with .json
            fc2 = find_component(cnx, "TEST_002")
            expected2 = "https://archives.somme.fr/ark:/58483/hvmz5n1jx9sc/manifest.json"
            iiif_manifest2 = [
                dv.url for dv in fc2.digitized_versions if dv.role == IIIF_MANIFEST_ROLE
            ][0]
            self.assertEqual(expected2, iiif_manifest2)
            self.assertEqual(expected2, fc2.iiif_manifest_url)

            # Test component 3 with UUID (archives.somme.fr specific pattern)
            fc3 = find_component(cnx, "TEST_003")
            expected3 = (
                "https://archives.somme.fr/iiif/ark:/58483/3kf1z6rt07pb/group/0/manifest.json"
            )
            iiif_manifest3 = [
                dv.url for dv in fc3.digitized_versions if dv.role == IIIF_MANIFEST_ROLE
            ][0]
            self.assertEqual(expected3, iiif_manifest3)
            self.assertEqual(expected3, fc3.iiif_manifest_url)

    def test_illustration_url(self):
        """Test illustration_url

        Trying : Import a Facomponent with two dao,
                 one without role and one with xlink:role == "thumbnail"
        Expecting: both dao are illustration_url
        """
        url = "https://v-earchives.vaucluse.fr/ajax/img/p/3p_w_cadastre/84-001/AD84_3P2_001_003_H.jpg/format/thumb"  # noqa
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD084_cadastre_min.xml")
            fc = find_component(cnx, "3 P 2-001/3")
            self.assertEqual(len(fc.digitized_versions), 2)
            self.assertEqual(fc.illustration_url, url)
            for dz in fc.digitized_versions:
                self.assertIn(dz.role, ("thumbnail", None))

    def test_illustration_url_daogrp(self):
        """Test illustration_url

        Trying : Import a Facomponent with two dao in daogrp,
                 one without role and one with  xlink:role == "thumbnail"
        """
        url = "https://v-earchives.vaucluse.fr/ajax/representative/p/3p_w_cadastre/84-105/format/thumb"  # noqa
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD084_cadastre_min.xml")
            fc = find_component(cnx, "3 P 2-001/2")
            self.assertEqual(len(fc.digitized_versions), 2)
            self.assertEqual(fc.illustration_url, url)

    def test_illustration_url_role(self):
        """Test illustration_url

        Trying : Import a Facomponent with four dao,
                 two without role and two with xlink:role == "thumbnail"
        Expecting: all dao are illustration_url
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD084_cadastre_min.xml")
            fc = find_component(cnx, "3 P 2-001/1")
            got = [(dz.url, dz.illustration_url, dz.role) for dz in fc.digitized_versions]
            expected = [
                (
                    "https://v-earchives.vaucluse.fr/viewer/e/2e09_caderousse/AD084CAD2E9_0007_03.jpg",  # noqa
                    None,
                    None,
                ),
                (
                    None,
                    "https://v-earchives.vaucluse.fr/ajax/img/e/2e09_caderousse/AD084CAD2E9_0007_03.jpg/format/thumb",  # noqa
                    "thumbnail",
                ),
            ]
            self.assertCountEqual(expected, got)

    def test_facomponent_relative_dao_jpg_old_FRAD085(self):
        """
        Trying: import dao with relative URLS
                [("1", None, "nombre"),
                 ("Fr\\Ad85\\2Num8\\2Num8_126\\2Num8_126_001.jpg", None, "répertoire")]
        Expecting: No dao are created
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD085_6Fi.xml")
            fc = find_component(cnx, "6 Fi 1130")
            got = [(d.url, d.illustration_url, d.role) for d in fc.digitized_versions]
            self.assertFalse(got)

    def test_facomponent_relative_daos_old_FRAD085(self):
        """
        Trying: import dao with relative URLS
                [("52", None, "nombre"),
                 ("FR\\Ad85\\2Num286\\018\\2C2", None, "répertoire")]
        Expected: No dao are created
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD085_2C.xml")
            fc = find_component(cnx, "2 C 2")
            got = [(d.url, d.illustration_url, d.role) for d in fc.digitized_versions]
            self.assertFalse(got)

    def test_facomponent_relative_daos_ligeo_FRAD085(self):
        """
        Trying: import new formated <c> (LIGEO)
        Expected: two dao are created
        """
        fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "FRAD085_SHD.xml")
            fc = cnx.execute(fc_rql, {"u": "29 mai 1793."}).one()
            got = [(d.url, d.illustration_url, d.role) for d in fc.digitized_versions]
            expected = [
                (
                    "https://etatcivil-archives.vendee.fr/c/visionneuse/visu_serie.php?serie=&dossier=1num263/SHD_B_5_4/lot92&page=1&pagefin=9&cote=SHD B 5/4-92&size=BIG",  # noqa
                    None,
                    "UNKNOWN",
                ),
                (
                    None,
                    "https://etatcivil-archives.vendee.fr/c/visionneuse/visu_serie_vign.php?serie=&dossier=1num263/SHD_B_5_4/lot92&page=1&pagefin=9&cote=SHD B 5/4-92&size=BIG",  # noqa
                    "thumbnail",
                ),
            ]
            self.assertCountEqual(got, expected)
            self.assertTrue(fc.illustration_url, expected[0][1])
            self.assertTrue(fc.digitized_versions, [expected[0][0]])

    def test_facomponent_digitized_urls_FRAD084(self):
        """Test digitized_urls.

        Trying: all DAO tags contain absolute URL.
                Two of them have the role "thumbnail" and the other two an empty role
        Expecting: dao without roles are digitized_urls
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD084_IR0000412.xml")
            fc = find_component(cnx, "74 J 2")
            self.assertEqual(2, len(fc.digitized_versions))
            self.assertEqual(1, len(fc.digitized_urls))
            expected_urls = [
                "http://v-earchives.vaucluse.fr/viewer/instrument_recherche/74J_Eysseric/FRAD084_74J02_01.jpg",  # noqa
                "http://v-earchives.vaucluse.fr/viewer/instrument_recherche/74J_Eysseric/FRAD084_74J02_02.jpg",  # noqa
            ]
            expected_illustration_urls = [
                "http://cdn-earchives.vaucluse.fr/prepared_images/thumb/destination/instrument_recherche/74J_Eysseric/FRAD084_74J02_01.jpg",  # noqa
                "http://cdn-earchives.vaucluse.fr/prepared_images/thumb/destination/instrument_recherche/74J_Eysseric/FRAD084_74J02_02.jpg",  # noqa
            ]
            self.assertIn(fc.digitized_urls[0], expected_urls)
            self.assertIn(fc.thumbnail_dest, expected_illustration_urls)

    def test_findingaid_digitized_urls(self):
        """Test digitized_urls.

        Trying: import a FindingAid with daogroup
        Expecting: 1 digitized_versions is created for the FindingAid
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD066_1B.xml")
            fa = cnx.find("FindingAid").one()
            got = [(d.url, d.illustration_url, d.role) for d in fa.digitized_versions]
            expected = [
                ("https://archive.org/details/inventairesommai13arch/page/n6/mode/2up", None, None),
            ]
            self.assertCountEqual(got, expected)

    def test_findingaid_digitized_urls_not_in_es_doc(self):
        """Test digitized_urls.

        Trying: import a FindingAid with daogroup
        Expecting: 1 digitized_versions is created for the FindingAid and present in es
        """
        with self.admin_access.cnx() as cnx:
            self.import_filepath(cnx, "ir_data/FRAD066_1B.xml")
            fa = cnx.find("FindingAid").one()
            dvs = fa.digitized_versions
            self.assertEqual(1, len(dvs))
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertNotIn("digitized_versions", adapter.serialize())

    def test_facomponent_dao_FRAD062(self):
        """Pas de Calais"""
        with self.admin_access.cnx() as cnx:
            fpath = "FRAD062_ir_9fi_02_permaliens.xml"
            self.import_filepath(cnx, fpath)
            fc = find_component(cnx, "9 Fi 1")
            # role image
            url = "http://archivesenligne.pasdecalais.fr/ark:/64297/5e7c97997adc45bcdafd11b170ae7b11"  # noqa
            self.assertTrue(fc.illustration_url, url)
            fc = find_component(cnx, "9 Fi 2")
            # role thumbnail
            url = "http://archivesenligne.pasdecalais.fr/ark:/64297/1a9927cc6cbbe29139031df77d2be48"  # noqa
            self.assertTrue(fc.illustration_url, url)

    def test_facomponent_dao_FRAD030(self):
        """
        Trying: import an IR with DAO
        Expected: DAO with  {".jpg", ".jpeg", ".png", ".jp2"} extention and without role
        are viewers url
        """
        with self.admin_access.cnx() as cnx:
            fpath = "ir_data/FRAD030_DAO.xml"
            self.import_filepath(cnx, fpath)
            fc = find_component(cnx, "7 Q 13/1")
            # viewer URL
            url = "https://v-earchives.gard.fr/series/FRAD030_ENREGISTREMENT/BAGNOLS_SUR_CEZE/FRAD030_07Q13_001?s=FRAD030_07Q13_001_002.jpg&amp;e=FRAD030_07Q13_001_048.jpg"  # noqa
            adapter = fc.cw_adapt_to("entity.main_props")
            self.assertTrue(adapter.digitized_urls()[0], url)
            # thumbnail URL
            url = "https://earchives.gard.fr/api/image/FRAD030_ENREGISTREMENT/BAGNOLS_SUR_CEZE/FRAD030_07Q13_001/FRAD030_07Q13_001_002.jpg"  # noqa
            self.assertTrue(fc.illustration_url, url)


if __name__ == "__main__":
    unittest.main()
