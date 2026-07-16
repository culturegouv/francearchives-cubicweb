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
import mimetypes
from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.dataimport.maps import import_maps

from cubicweb_francearchives.testutils import S3BfssStorageTestMixin


class ImporMapsTC(S3BfssStorageTestMixin, WebCWTC):
    def test_import_maps(self):
        """
        This test tests the inital import. It was not adapted to s3
        """
        directory = self.datapath("maps")
        with self.admin_access.cnx() as cnx:
            sec = cnx.create_entity("Section", title="Mes ancêtres")
            cnx.commit()
            with cnx.allow_all_hooks_but("es"):
                import_maps(cnx, directory)
                cnx.commit()
                cw_map = cnx.find("Map").one()
                title = "Etat civil en ligne"
                self.assertEqual(cw_map.title, title)
                self.assertEqual(cw_map.metadata[0].title, title)
                map_title = "Numérisation et mise en ligne des registres paroissiaux et d'état civil dans les services d'archives publics au 26 avril 2016"  # noqa
                self.assertEqual(cw_map.map_title, map_title)
                self.assertTrue(cw_map.map_file)
                self.assertEqual(cw_map.reverse_children[0].eid, sec.eid)
                thumbnail = cw_map.map_image[0]
                self.assertEqual(thumbnail.caption, "Vignette")
                fspath = cnx.execute(
                    "Any fspath(D) WHERE X data D, X eid %(e)s", {"e": thumbnail.image_file[0].eid}
                )
                mmtype = mimetypes.guess_type(fspath[0][0].getvalue().decode("utf-8"))
                self.assertEqual(mmtype, ("image/png", None))


if __name__ == "__main__":
    unittest.main()
