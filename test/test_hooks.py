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
import os.path as osp
import unittest

from cubicweb import Unauthorized, Binary
from cubicweb_web.devtools.testlib import WebCWTC
from cubicweb_francearchives.testutils import S3BfssStorageTestMixin


class HookTests(S3BfssStorageTestMixin, WebCWTC):
    def test_delete_card(self):
        with self.admin_access.cnx() as cnx:
            card = cnx.create_entity("Card", title="Test", wikiid="test")
            cnx.commit()
            card.cw_delete()
            cnx.commit()

    def test_undeletable_section(self):
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity("Section", title="Test", name="test")
            cnx.commit()
            with self.assertRaises(Unauthorized):
                section.cw_delete()

    def test_delete_section(self):
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity("Section", title="Test")
            cnx.commit()
            section.cw_delete()
            cnx.commit()

    def test_rgaa_hook_service(self):
        with self.admin_access.cnx() as cnx:
            other = (
                '<img src="../file/01c12288z2dsd/illustration_1.jpg" '
                'alt="illustration_1.jpg"  width="523" height="371" >'
            )
            service = cnx.create_entity(
                "Service",
                category="foo1",
                level="level-R",
                dpt_code="75",
                name="Service de Paris",
                other=other,
            )
            cnx.commit()
            expected = (
                '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="" '
                'width="523" height="371">'
            )
            self.assertEqual(service.other, expected)

    def test_rgaa_hook_map(self):
        with self.admin_access.cnx() as cnx:
            top = '<div><a href="www.google">google</a></div>'
            bottom = '<div><img src="http://advaldoise.fr"/></div>'
            with open(osp.join(self.datadir, "Carte_Cadastres.csv"), "rb") as stream:
                map = cnx.create_entity(
                    "Map",
                    title="map",
                    map_file=Binary(stream.read()),
                    top_content=top,
                    bottom_content=bottom,
                )
            cnx.commit()
            new_top = (
                '<div><a href="www.google" rel="nofollow noopener noreferrer external" '
                'target="_blank">google</a></div>'
            )
            new_bottom = '<div><img src="http://advaldoise.fr" ' 'alt=""></div>'
            self.assertEqual(map.top_content, new_top)
            self.assertEqual(map.bottom_content, new_bottom)


if __name__ == "__main__":
    unittest.main()
