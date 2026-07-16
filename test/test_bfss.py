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
import os
import os.path as osp
import urllib.request
import urllib.parse
import urllib.error

from cubicweb import Binary
from cubicweb.devtools import BASE_URL
from cubicweb.devtools.testlib import CubicWebTC

from cubicweb_francearchives.testutils import HashMixIn


@unittest.skipIf(
    "AWS_S3_BUCKET_NAME" in os.environ, "BFSS specific tests, skipping when S3 activated"
)
class BfssTests(HashMixIn, CubicWebTC):
    def setUp(self):
        super(BfssTests, self).setUp()
        self.bfss_dir = osp.join(self.config.appdatahome, "bfss")
        # at this point, storage is already created, we have to get it
        # to update its default output directory
        ssource = self.repo.sources_by_uri["system"]
        storage = ssource.storage("File", "data")
        storage.default_directory = self.bfss_dir

    def expected_path(self, entity):
        return osp.join(self.bfss_dir, "{}_{}".format(entity.compute_hash(), entity.data_name))

    def expected_download_url(self, entity):
        return urllib.parse.quote(
            "{}file/{}/{}".format(BASE_URL, entity.data_hash, entity.data_name)
        )

    def test_basic_storage_basename(self):
        with self.admin_access.cnx() as cnx:
            f = cnx.create_entity(
                "File", data=Binary(b"foo"), data_format="image/jpeg", data_name="foo.jpg"
            )
            # test the file is saved correctly
            expected_path = self.expected_path(f)
            self.assertTrue(osp.isfile(self.expected_path(f)))
            with open(expected_path) as inputf:
                content = inputf.read()
                self.assertEqual(content, "foo")
            self.assertEqual(
                f.cw_adapt_to("IDownloadable").download_url(), self.expected_download_url(f)
            )
            # test that rollback will remove the file from disk
            cnx.rollback()
            self.assertFalse(osp.isfile(expected_path))

    def test_update_storage(self):
        with self.admin_access.cnx() as cnx:
            f = cnx.create_entity(
                "File", data=Binary(b"foo-foo"), data_format="imag/jpeg", data_name="foo.jpg"
            )

            expected_path = self.expected_path(f)
            self.assertTrue(
                expected_path.endswith("de67f401c7068b01ed85ef5f7247f0d018ffa0f3_foo.jpg")
            )
            # test the file is saved correctly
            self.assertTrue(osp.isfile(expected_path))
            with open(expected_path) as inputf:
                content = inputf.read()
                self.assertEqual(content, "foo-foo")
            self.assertEqual(
                f.cw_adapt_to("IDownloadable").download_url(), self.expected_download_url(f)
            )
            cnx.commit()

            # modify file content and ensure new hash is handled properly
            f.cw_set(data=Binary(b"bar"))
            expected_path2 = self.expected_path(f)
            self.assertTrue(
                expected_path2.endswith("62cdb7020ff920e5aa642c3d4066950dd1f01f4d_foo.jpg")
            )
            with open(expected_path2) as inputf:
                content = inputf.read()
                self.assertEqual(content, "bar")
            self.assertEqual(
                f.cw_adapt_to("IDownloadable").download_url(), self.expected_download_url(f)
            )

            # test that rollback will remove the second file (only) from disk
            cnx.rollback()
            self.assertTrue(osp.isfile(expected_path))
            self.assertFalse(osp.isfile(expected_path2))


if __name__ == "__main__":
    unittest.main()
