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


""":synopsis: OAI utils test cases."""


# standard library imports


import os
import glob

# third party imports
# library specific imports
from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.dataimport import oai_utils

from cubicweb_francearchives.testutils import S3BfssStorageTestMixin


class TestOAIPMHWriter(S3BfssStorageTestMixin, WebCWTC):
    """OAIPMHWriter test cases.

    :cvar dict SERVICE_INFOS: service information
    """

    SERVICE_INFOS = {"code": "FRAD123"}

    @classmethod
    def init_config(cls, config):
        super(TestOAIPMHWriter, cls).init_config(config)
        config.set_option("ead-services-dir", "/tmp")

    def get_path(self, subdirectory=()):
        """
        Compute the path
        """
        return os.path.join(
            self.config["ead-services-dir"], self.SERVICE_INFOS["code"], "oaipmh", *subdirectory
        )

    def tearDown(self):
        """Tear down test cases."""
        super(TestOAIPMHWriter, self).tearDown()
        path = self.get_path()
        if os.path.exists(path):
            for filename in glob.glob(os.path.join(path, "*")):
                os.remove(filename)
            os.removedirs(path)

    def test_create_directory_existing(self):
        """Test XML backup files directory creation.

        Trying: already existing directory
        Expecting: existing directory with the same files
        """
        file_path = self.get_filepath_by_storage(os.path.join(self.get_path(), "foo"))
        self.storage_write_file(file_path, "bar")
        oai_writer = oai_utils.OAIPMHWriter(
            self.config["ead-services-dir"], self.SERVICE_INFOS, subdirectories=["oaipmh"]
        )
        oai_writer.makedir(subdirectories=["oaipmh"])
        self.assertTrue(self.fileExists(file_path))

    def test_create_directory_new(self):
        """Test backup XML file directory creation. Bfss only

        Trying: new path
        Expecting: new directory
        """
        oai_writer = oai_utils.OAIPMHWriter(self.config["ead-services-dir"], self.SERVICE_INFOS)
        oai_writer.makedir(subdirectories=["oaipmh"])
        if not self.s3_bucket_name:
            self.assertTrue(self.fileExists(self.get_path()))

    def test_get_file_path(self):
        """Test getting file path.

        Trying: fout-digit EAD ID
        Expecting: file path is {path}/{code_service}_{eadid}.xml
        """
        eadid = "1234"
        file_path = os.path.join(self.get_path(), f"{self.SERVICE_INFOS['code']}_{eadid}.xml")
        oai_writer = oai_utils.OAIPMHWriter(
            self.config["ead-services-dir"], self.SERVICE_INFOS, subdirectories=["oaipmh"]
        )
        self.assertEqual(self.get_filepath_by_storage(file_path), oai_writer.get_file_path(eadid))

    def test_get_file_path_lower(self):
        """Test getting file path.

        Trying: fout-digit EAD ID
        Expecting: file path is {path}/{code_service}_{eadid}.xml
        """
        eadid = "frad123_1234"
        file_path = os.path.join(self.get_path(), f"{self.SERVICE_INFOS['code']}_1234.xml")
        oai_writer = oai_utils.OAIPMHWriter(
            self.config["ead-services-dir"], self.SERVICE_INFOS, subdirectories=["oaipmh"]
        )
        self.assertEqual(self.get_filepath_by_storage(file_path), oai_writer.get_file_path(eadid))

    def test_get_file_whitespace(self):
        """Test getting file path.

        Trying: fout-digit EAD ID
        Expecting: file path is {path}/{code_service}_{eadid}.xml
        """
        eadid = " FRAD123_1234 "
        file_path = self.get_filepath_by_storage(
            os.path.join(self.get_path(), f"{self.SERVICE_INFOS['code']}_1234.xml")
        )
        oai_writer = oai_utils.OAIPMHWriter(
            self.config["ead-services-dir"], self.SERVICE_INFOS, subdirectories=["oaipmh"]
        )
        self.assertEqual(file_path, oai_writer.get_file_path(eadid))

    def test_get_file_path_dasg(self):
        """Test getting file path.

        Trying: EAD ID with dash
        Expecting: file path is {path}/{code_service}_{eadid}.xml
        """
        eadid = "FRAD123 F 1-1423"
        file_path = os.path.join(self.get_path(), f"{self.SERVICE_INFOS['code']}_F_1-1423.xml")
        oai_writer = oai_utils.OAIPMHWriter(
            self.config["ead-services-dir"], self.SERVICE_INFOS, subdirectories=["oaipmh"]
        )
        self.assertEqual(self.get_filepath_by_storage(file_path), oai_writer.get_file_path(eadid))

    def test_get_file_contents(self):
        """Test getting file contents.

        Trying: calling get_file_contents method
        Expecting: raises NotImplementedError
        """
        oai_writer = oai_utils.OAIPMHWriter(self.config["ead-services-dir"], self.SERVICE_INFOS)
        with self.assertRaises(NotImplementedError):
            oai_writer.get_file_contents()

    def test_dump_new_file(self):
        """Test dumping file contents.

        Trying: new file
        Expecting: new file
        """
        eadid = "IR0001383"
        file_path = self.get_filepath_by_storage(
            os.path.join(self.get_path(), f"{self.SERVICE_INFOS['code']}_{eadid}.xml")
        )
        oai_writer = oai_utils.OAIPMHWriter(
            self.config["ead-services-dir"], self.SERVICE_INFOS, subdirectories=["oaipmh"]
        )
        oai_file_path = oai_writer.dump(eadid, b"bar")
        self.assertEqual(file_path, oai_file_path)
        binary = self.getFileContent(file_path)
        self.assertEqual(b"bar", binary)

    def test_dump_existing_file(self):
        """Test dumping file contents.

        Trying: existing file
        Expecting: new file
        """
        eadid = "IR0001383"
        file_path = self.get_filepath_by_storage(
            os.path.join(self.get_path(), f"{self.SERVICE_INFOS['code']}_{eadid}.xml")
        )
        self.storage_write_file(file_path, "bar")
        oai_writer = oai_utils.OAIPMHWriter(
            self.config["ead-services-dir"], self.SERVICE_INFOS, subdirectories=["oaipmh"]
        )
        oai_file_path = oai_writer.dump(eadid, b"baz")
        self.assertEqual(file_path, oai_file_path)
        binary = self.getFileContent(file_path)
        self.assertEqual(b"baz", binary)
