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
"""i18nio tests"""

import unittest
import doctest

from cubicweb.devtools.testlib import BaseTestCase

from cubicweb_francearchives import i18n


class PolibTests(BaseTestCase):
    def test_po_catalogs_update(self):
        po_files = i18n.all_pofiles()
        po_dicts = i18n.pofiles_as_dicts(po_files, skip_msgctxt=False)
        po_dicts["en"][("", "NominaRecord")].msgstr = ""
        po_dicts = i18n.update_i18n_catalogs(
            po_files, self.datapath("translations.csv"), autosave=False, skip_msgctxt=False
        )
        self.assertEqual("auteurfr", po_dicts["fr"][("", "NominaRecord")].msgstr)
        self.assertEqual("auteurfr", po_dicts["en"][("", "NominaRecord")].msgstr)
        self.assertEqual("auteurde", po_dicts["de"][("", "NominaRecord")].msgstr)
        self.assertEqual("nameservfr", po_dicts["fr"][("Service", "name")].msgstr)
        self.assertEqual("nameservde", po_dicts["de"][("Service", "name")].msgstr)
        self.assertEqual("Aide à la recherche", po_dicts["fr"][("", "SearchHelp")].msgstr)
        self.assertEqual("SearchHelp", po_dicts["en"][("", "SearchHelp")].msgstr)
        self.assertEqual("Suchhilfe", po_dicts["de"][("", "SearchHelp")].msgstr)
        self.assertEqual("Ayuda para la búsqueda", po_dicts["es"][("", "SearchHelp")].msgstr)
        self.assertEqual("namesecten", po_dicts["en"][("Section", "name")].msgstr)
        self.assertEqual("Article", po_dicts["fr"][("", "BaseContent")].msgstr)
        self.assertEqual("Content", po_dicts["en"][("", "BaseContent")].msgstr)
        self.assertEqual("Artikel", po_dicts["de"][("", "BaseContent")].msgstr)
        self.assertEqual("Artículo", po_dicts["es"][("", "BaseContent")].msgstr)

    def test_schema_msgid_filtered(self):
        po_files = i18n.all_pofiles()
        po_dicts = i18n.pofiles_as_dicts(po_files)
        msgids = {msgid for _, msgid in list(po_dicts["fr"].keys())}
        self.assertNotIn("add a BaseContent", msgids)
        self.assertIn("Circular", msgids)


def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(i18n))
    return tests


if __name__ == "__main__":
    unittest.main()
