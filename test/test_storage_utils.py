# -*- coding: utf-8 -*-
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2021
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
from io import StringIO
import gzip
import unittest

from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.storage import S3BfssStorageMixIn
from cubicweb_francearchives.testutils import S3BfssStorageTestMixin


class S3BfssStorageTest(S3BfssStorageTestMixin, WebCWTC):
    def setUp(self):
        super().setUp()
        self.storage = S3BfssStorageMixIn()

    def test_write_csv_file(self):
        """
        Trying: create a csv file and delete
        Expecting: the csv file is created with the right content
        """
        rows = [[1, 2, 3], ["1a", "2b", "3c"]]
        filepath = "text_storage.csv"
        filepath = self.storage.storage_write_csv_file(filepath, rows, directory="storage")
        self.assertTrue(self.fileExists(filepath))
        content = self.storage.storage_get_file_content(filepath)
        self.assertEqual(b"1;2;3\r\n1a;2b;3c\r\n", content)
        self.storage.storage_delete_file(filepath)
        self.assertFalse(self.fileExists(filepath))

    def test_write_gzip_file(self):
        """
        Trying: create a gzip file from a buffer
        Expecting: the unziped file is equal to the buffer
        """
        buf = StringIO()
        xml = """<?xml version="1.0" encoding="UTF-8"?><test>test<test>"""
        buf.write(xml)
        filename = "test.xml.gz"
        self.storage.storage_write_gz_file(filename, buf)
        self.assertTrue(self.fileExists(filename))
        content = self.storage.storage_get_file_content(filename)
        got_text = gzip.decompress(content).decode("utf-8")
        self.assertEqual(xml, got_text)


if __name__ == "__main__":
    unittest.main()
