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
import shutil
import tempfile

from itertools import chain

import os
import os.path as osp

import unittest

from lxml import etree

from cubicweb.devtools.testlib import CubicWebTC


from cubicweb_francearchives.dataimport.ead import transform_ape_ead_file
from cubicweb_francearchives.dataimport.eadreader import preprocess_ead

from cubicweb_francearchives.testutils import PostgresTextMixin
from pgfixtures import setup_module, teardown_module  # noqa


class ApeEadTransformationTest(PostgresTextMixin, CubicWebTC):
    @classmethod
    def init_config(cls, config):
        super(ApeEadTransformationTest, cls).init_config(config)
        config.set_option("appfiles-dir", cls.datapath("tmp/ape_ead_data"))

    def setUp(self):
        super(ApeEadTransformationTest, self).setUp()
        self.ape_ead_dir = self.datapath("ape_ead_data")

    def ape_ead_filepath(self, filename):
        return os.path.join(self.config["appfiles-dir"], filename)

    def tearDown(self):
        """Tear down test cases."""
        super(ApeEadTransformationTest, self).tearDown()
        appdir = self.config["appfiles-dir"]
        if osp.exists(appdir):
            shutil.rmtree(appdir)

    def get_elements(
        self,
        tree,
        tag,
    ):
        return tree.xpath("//e:{}".format(tag), namespaces={"e": tree.nsmap[None]})

    def test_ape_ead_conversion(self):
        """test an ead file with all major tags"""
        filepath = "ead_complet.xml"
        ape_filepath = self.ape_ead_filepath(filepath)
        fa_url = "https://francearchives.gouv.fr/1234"
        tree = preprocess_ead(self.datapath(self.ape_ead_dir, filepath))
        transform_ape_ead_file(fa_url, tree, ape_filepath)
        # test ead source file
        # test ape_ead resulting  file
        filepath = self.datapath(osp.join("ape_ead_data"), ape_filepath)
        # use etree.parse to let lxml handle file and encoding
        tree = etree.parse(filepath).getroot()  # returns _ElementTree use getroot() to get Element
        eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
        self.assertEqual(eadid.attrib["url"], fa_url)
        # ptr, extptr, bibref, ref are transformed to extref
        tags = (("extref", 10), ("ref", 0), ("extptr", 0), ("ptr", 0))
        for tag, nb in tags:
            elts = self.get_elements(tree, tag)
            self.assertEqual(len(elts), nb)

    def test_ape_ead_conversion_countrycode(self):
        """Test countrycode attributes on <eadid>

        Trying: generate an ape_ead file
        Expecting: countrycode attributes is correctly set
        """
        filepath = "ead_complet.xml"
        ape_filepath = self.ape_ead_filepath(filepath)
        fa_url = "https://francearchives.gouv.fr/1234"
        tree = preprocess_ead(self.datapath(self.ape_ead_dir, filepath))
        transform_ape_ead_file(fa_url, tree, ape_filepath)
        # test ead source file
        # test ape_ead resulting  file
        filepath = self.datapath(osp.join("ape_ead_data"), ape_filepath)
        # use etree.parse to let lxml handle file and encoding
        tree = etree.parse(filepath).getroot()  # returns _ElementTree use getroot() to get Element
        eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
        self.assertEqual(eadid.attrib["countrycode"], "FR")

    def test_ape_full_ead_conversion(self):
        """test the newly generated ape file as exactly the same as the witness
        ape file (ape_ead_complet_expected.xml)
        """
        self.maxDiff = 0
        filepath = "ead_complet.xml"
        ape_filepath = self.ape_ead_filepath(filepath)
        ape_expected_filepath = self.datapath(
            osp.join("ape_ead_data"), "ape_ead_complet_expected.xml"
        )
        fa_url = "https://francearchives.gouv.fr/1234"
        tree = preprocess_ead(self.datapath(osp.join("ape_ead_data"), filepath))
        transform_ape_ead_file(fa_url, tree, ape_filepath)
        ape_stream, ape_expected_stream = None, None
        with open(self.datapath(osp.join("ape_ead_data"), ape_filepath), "r") as f:
            ape_stream = f.read()
        with open(self.datapath(osp.join("ape_ead_data"), ape_expected_filepath), "r") as f:
            ape_expected_stream = f.read()
        self.assertEqual(ape_stream, ape_expected_stream)

    def test_ape_full_ead_conversion_2(self):
        filepath = "FRAD070_115Edepot_rpnum_001.xml"
        ape_filepath = self.ape_ead_filepath(filepath)
        ape_expected_filepath = self.datapath(
            osp.join("ape_ead_data"), "ape_FRAD070_115Edepot_rpnum_001_expected.xml"
        )
        fa_url = "https://francearchives.gouv.fr/findingaid/XXX"
        tree = preprocess_ead(self.datapath(osp.join("ape_ead_data"), filepath))
        transform_ape_ead_file(fa_url, tree, ape_filepath)
        ape_stream, ape_expected_stream = None, None
        with open(self.datapath(osp.join("ape_ead_data"), ape_filepath), "r") as f:
            ape_stream = f.read()
        with open(self.datapath(osp.join("ape_ead_data"), ape_expected_filepath), "r") as f:
            ape_expected_stream = f.read()
        self.assertEqual(ape_stream, ape_expected_stream)

    def test_ape_ead_conversion_xlinks(self):
        """test an ead file with all major tags"""
        filepath = "FRAD005_33FI.xml"
        ape_filepath = self.ape_ead_filepath(filepath)
        fa_url = (
            "https://francearchives.gouv.fr/findingaid/ee81f35ba975a0aceabfff4e2de751df3cccaff3"
        )
        tree = preprocess_ead(self.datapath(osp.join("ape_ead_data"), filepath))
        transform_ape_ead_file(fa_url, tree, ape_filepath)
        # test ead source file
        filepath = self.datapath(osp.join("ape_ead_data"), filepath)
        tree = etree.parse(filepath).getroot()
        tags = (
            "archref",
            "bibref",
            "dao",
            "daoloc",
            "extptr",
            "extptrloc",
            "extref",
            "extrefloc",
            "ref",
            "refloc",
            "title",
        )
        elts = chain(self.get_elements(tree, tag) for tag in tags)
        for elts_list in elts:
            for elt in elts_list:
                xlink = elt.attrib["{{{}}}href".format(tree.nsmap["xlink"])]
                self.assertTrue(elt.tag, xlink.startswith("/"))
        daos = tree.xpath("//e:dao", namespaces={"e": tree.nsmap[None]})
        self.assertEqual(len(daos), 88)
        # test ape_ead resulting file
        ape_filepath = self.datapath(osp.join("ape_ead_data"), ape_filepath)
        tree = etree.parse(ape_filepath).getroot()
        eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
        self.assertEqual(eadid.attrib["url"], fa_url)
        daos = tree.xpath("//e:dao", namespaces={"e": tree.nsmap[None]})
        self.assertEqual(len(daos), 0)

    def test_ape_ead_conversion_dao_xlinks(self):
        """test an dao"""
        filepath = "FRAD051_61Fi.xml"
        ape_filepath = self.ape_ead_filepath(filepath)
        fa_url = (
            "https://francearchives.gouv.fr/findingaid/3d6c85cc8e4fa93d57d4c01c18d232ccc5a0d270"
        )
        tree = preprocess_ead(self.datapath(osp.join("ape_ead_data"), filepath))
        transform_ape_ead_file(fa_url, tree, ape_filepath)
        # test ead source file
        filepath = self.datapath(osp.join("ape_ead_data"), filepath)
        tree = etree.parse(filepath).getroot()
        daos = tree.xpath("//e:daoloc", namespaces={"e": tree.nsmap[None]})
        for dao in daos:
            xlink = dao.attrib["href"]
            self.assertTrue(dao.tag, xlink.startswith("/"))
            if not dao.attrib.get("role") == "last_image":
                xlink = dao.attrib["{{{}}}href".format(tree.nsmap["xlink"])]
                self.assertTrue(dao.tag, xlink.startswith("/"))
        self.assertEqual(len(daos), 3)
        # test ape_ead resulting file
        ape_filepath = self.datapath(osp.join("ape_ead_data"), ape_filepath)
        tree = etree.parse(ape_filepath).getroot()
        daos = tree.xpath("//e:dao", namespaces={"e": tree.nsmap[None]})
        expected = [
            "http://archives.marne.fr/ark:/86869/a011515062574JdMMvc/1/1.thumbnail",
            "http://archives.marne.fr/ark:/86869/a011515062574JdMMvc/1/1",
        ]
        got = [dao.attrib["{{{}}}href".format(tree.nsmap["xlink"])] for dao in daos]
        self.assertEqual(sorted(expected), sorted(got))

    def test_ape_ead_conversion_address(self):
        """<adress> must contains <addressline> if data"""
        filepath = self.datapath("ape_ead_data/FRAD070_115Edepot_rpnum_001.xml")
        tree = etree.parse(filepath).getroot()
        orig_tree = etree.parse(filepath).getroot()
        addresses = orig_tree.findall(".//address")
        self.assertEqual(len(addresses), 2)
        for address in addresses:
            for line in address:
                self.assertEqual(line.tag, "addressline")
        fa_url = "https://francearchives.gouv.fr/findingaid/XXX"
        tree = preprocess_ead(filepath)
        tempdir = tempfile.mkdtemp()
        try:
            ape_filepath = osp.join(tempdir, "ape_FRAD070_115Edepot_rpnum_001.xml")
            transform_ape_ead_file(fa_url, tree, ape_filepath)
            # test ead source file
            tree = etree.parse(ape_filepath).getroot()
            addresses = tree.xpath("//e:address", namespaces={"e": tree.nsmap[None]})
            self.assertEqual(len(addresses), 2)
            for address in addresses:
                self.assertTrue(len(address))
                for line in address:
                    self.assertEqual(line.tag, "{{{}}}addressline".format(tree.nsmap[None]))
        finally:
            shutil.rmtree(tempdir)


if __name__ == "__main__":
    unittest.main()
