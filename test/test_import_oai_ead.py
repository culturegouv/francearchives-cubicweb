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
from datetime import datetime
import glob
from io import BytesIO

import logging
from lxml import etree
from mock import patch

import os
from os import path as osp
import unittest

from cubicweb_web.devtools.testlib import WebCWTC


from cubicweb_francearchives.dataimport import (
    sqlutil,
    usha1,
    load_services_map,
    service_infos_from_service_code,
    normalize_for_filepath,
)
from cubicweb_francearchives.dataimport import oai
from cubicweb_francearchives.dataimport.oai_utils import compute_oai_id
from cubicweb_francearchives.entities.es import DZFacetValues

from cubicweb_francearchives.testutils import (
    EADImportMixin,
    PostgresTextMixin,
    OaiImportMixin,
    sort_authorities,
)
from cubicweb_francearchives.utils import merge_dicts

from pgfixtures import setup_module, teardown_module  # noqa


class OaiEadImportTC(OaiImportMixin, PostgresTextMixin, WebCWTC):

    readerconfig = merge_dicts(
        {}, EADImportMixin.readerconfig, {"reimport": True, "nodrop": False, "force_delete": True}
    )

    def setup_database(self):
        super(OaiEadImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", name="Marne", code="FRAD051", category="foo")
            cnx.commit()
            self.service_eid = service.eid
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(service.code, services_map)
            self.filename = "oai_ead_sample_listrecords.xml"
            cnx.commit()

    def tearDown(self):
        """Tear down test cases."""
        super(OaiEadImportTC, self).tearDown()
        if osp.exists(self.path()):
            for filename in glob.glob(osp.join(self.path(), "*")):
                os.remove(filename)
            os.removedirs(self.path())

    @classmethod
    def init_config(cls, config):
        super(OaiEadImportTC, cls).init_config(config)
        config.set_option(
            "consultation-base-url",
            "https://francearchives.gouv.fr",
        )
        config.set_option("ead-services-dir", "/tmp")

    def path(self, service_infos=None):
        service_infos = service_infos or self.service_infos
        return "{ead_services_dir}/{code}/oaipmh/ead".format(
            ead_services_dir=self.config["ead-services-dir"], **service_infos
        )

    def filepath(self, filename=None):
        filename = filename or self.filename
        assert filename is not None
        return self.datapath(osp.join("oai_ead", filename))

    def test_service_infos(self):
        self.assertEqual(
            set(self.service_infos.keys()),
            {"code", "name", "eid", "level", "title", "iiif_ead_policy"},
        )

    def test_dump(self):
        """Test OAI EAD standard harvesting.

        Trying: valid OAI-PMH
        Expecting: corresponding XML files are harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["FRAD051_000000028_203M.xml", "FRAD051_204M.xml", "identifiers.csv"]),
                sorted(zf.namelist()),
            )

    def test_harvest_no_header(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 3 records one of which has no header tag
        Expecting: 2 FindingAids are harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_header_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["FRAD051_205M.xml", "FRAD051_204M.xml", "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            oai_url = f"file://{self.filepath()}"
            expected = sorted(
                [
                    [
                        "FRAD051_205M",
                        compute_oai_id(oai_url, "86870/a0114666730443PYpcW"),
                    ],
                    [
                        "FRAD051_204M",
                        compute_oai_id(oai_url, "86869/a0114666730443PYpcW"),
                    ],
                    ["oai_url", f"{oai_url}?metadataPrefix=ead"],
                ]
            )

            self.assertEqual(expected, sorted(self.read_csv_zipfile(zf, "identifiers.csv")))

    def test_harvest_no_metadata(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 3 records one of which has no metadata tag
        Expecting: 2 FindingAids are created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_metadata_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            oai_ead_xml_names = ("FRAD051_205M.xml", "FRAD051_204M.xml")
            self.assertEqual(
                sorted([*oai_ead_xml_names, "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            self.assertEqual(
                sorted([n.split(".xml")[0] for n in oai_ead_xml_names]),
                sorted([normalize_for_filepath(e) for e in eadids]),
            )

    def test_harvest_https(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest a file with a OAI namespace starting with https.
        Expecting: 1 FindingAid is harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_namespace_with_https_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            oai_ead_xml_name = "SHDGR_INV_GRF_Seconde_Republique.xml"
            self.assertEqual(
                sorted([oai_ead_xml_name, "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            self.assertEqual(
                [oai_ead_xml_name.split(".xml")[0]], [normalize_for_filepath(e) for e in eadids]
            )

    def test_harvest_duplicate_c_id(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 2 records one of which has a duplicate c@id
        Expecting: 2 FindingAid are harvested but only 1 is created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "duplicate_c_id_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            zf = self.get_zipfile(cnx, zipfiles[0])
            oai_ead_xml_names = ["FRAD051_000000028_203M.xml", "FRAD051_204M.xml"]
            self.assertEqual(
                sorted([*oai_ead_xml_names, "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            self.assertEqual(2, len(element_tree.findall(".//{*}c[@id='the-id']")))
            # ADD test import TODO

    def test_harvest_no_archdesc(self):
        """Test OAI EAD standard harvesting.

        Trying: impoharvestrt 2 records one of which has no archdesc tag
        Expecting: 1 FindingAid is harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_archdesc_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["FRAD051_204M.xml", "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            self.assertEqual(1, len(element_tree.findall(".//{*}archdesc")))

    def test_harvest_no_did(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 2 records one of which has no archdesc/did tag
        Expecting: 1 FindingAid is harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "no_did_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["FRAD051_204M.xml", "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            self.assertEqual(1, len(element_tree.findall(".//{*}archdesc/{*}did")))

    def test_harvest_wrong_eadid(self):
        """Test OAI EAD standard harvesting.
            For now we accept records with not well formed eadid

        Trying: harvest 2 records one of which <eadid> value is not well formed
        Expecting: 2 FindingAids are nevertheless harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "wrong_eadid_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["000000028_203M.xml", "FRAD051_204M.xml", "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            for filename in ("000000028_203M.xml", "FRAD051_204M.xml"):
                tree = etree.parse(BytesIO(zf.open(filename).read()))
                eadid = [eadid.text for eadid in tree.findall(".//{*}eadid")][0]
                self.assertEqual(filename.split(".xml")[0], eadid)

    def test_harvest_empty_header(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 3 records one of which has an empty header tag
        Expecting: 2 FindingAids are harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "empty_header_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["FRAD051_204M.xml", "FRAD051_205M.xml", "identifiers.csv"]),
                sorted(zf.namelist()),
            )

    def test_harvest_empty_metadata(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 3 records one of which has an empty metadata tag
        Expecting: 2 FindingAids are harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "empty_metadata.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["FRAD051_204M.xml", "FRAD051_205M.xml", "identifiers.csv"]),
                sorted(zf.namelist()),
            )

    def test_harvest_empty_eadid(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 3 records one of which has empty <eadid> tag
        Expecting: 2 FindingAids are harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "empty_eadid.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            oai_ead_xml_names = ["FRAD051_204M.xml", "FRAD051_205M.xml"]
            self.assertEqual(
                sorted([*oai_ead_xml_names, "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid") if eadid.text]
            self.assertEqual(
                sorted([n.split(".xml")[0] for n in oai_ead_xml_names]),
                sorted([normalize_for_filepath(e) for e in eadids]),
            )

    def test_harvest_repeated_eadid(self):
        """Test OAI EAD standard harvesting.

        Trying: harvest 3 records two of which have the same <eadid> value
        Expecting: only one FindingAid is harvested for each unique <eadid> value
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "repeated_eadid_listrecords.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            eadids = [eadid.text for eadid in element_tree.findall(".//{*}eadid")]
            self.assertCountEqual(
                ["FRAD051_000000028_203M", "FRAD051_204M", "FRAD051_000000028_203M"], eadids
            )
            zf = self.get_zipfile(cnx, zipfiles[0])
            oai_ead_xml_names = ["FRAD051_000000028_203M.xml", "FRAD051_204M.xml"]
            self.assertEqual(
                sorted([*oai_ead_xml_names, "identifiers.csv"]),
                sorted(zf.namelist()),
            )

    def test_harvest_deleted_record(self):
        """Test OAI EAD standard harvesting.

        Trying: havest one valid and one deleted recored
        Expecting: 1 deleted record oai identifier is found in "deleted.csv" file
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample_deleted.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["FRAD051_204M.xml", "deleted.csv", "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            oai_url = f"file://{self.filepath()}"
            self.assertEqual(
                [
                    [
                        "FRAD051_204M",
                        compute_oai_id(oai_url, "86869/a0114666730443PYpcW"),
                    ],
                    ["oai_url", f"{oai_url}?metadataPrefix=ead"],
                ],
                self.read_csv_zipfile(zf, "identifiers.csv"),
            )
            self.assertEqual(
                [[compute_oai_id(oai_url, "86869/a011349628476eWWr7u")]],
                self.read_csv_zipfile(zf, "deleted.csv"),
            )

    def test_harvest_only_deleted_record(self):
        """Test OAI EAD standard harvesting.

        Trying: havest two deleted recored
        Expecting: two deleted records oai identifiers are found in "deleted.csv" file
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample_only_deleted.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(
                sorted(["deleted.csv", "identifiers.csv"]),
                sorted(zf.namelist()),
            )
            oai_url = f"file://{self.filepath()}"
            self.assertEqual(
                sorted(
                    [
                        [compute_oai_id(oai_url, "86869/a011349628476eWWr7u")],
                        [compute_oai_id(oai_url, "86869/a011349628476eWWr7b")],
                    ]
                ),
                sorted(self.read_csv_zipfile(zf, "deleted.csv")),
            )

    def test_import_deleted_record(self):
        """Test OAI EAD standard importing.

        Trying: import a recordList with one deleted record
        Expecting: nothing is created
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "deleted_record.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, self.service_infos)
            self.assertFalse(cnx.find("FindingAid"))

    def test_reimport_oai_ead(self):
        """Test OAI EAD re-importing

        Trying: Import once and reimport the same harvested file
        Expecting: no error is raised and no extra FindingAids created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, self.service_infos)
            expected_fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            self.assertEqual(expected_fi_count, 2)
            # reimport the same file
            self.import_oai(cnx, url, self.service_infos)
            new_fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            self.assertEqual(expected_fi_count, new_fi_count)

    @unittest.skip("DELETE")
    def test_import_oai_ead_deleted_ko(self):
        """Test OAI EAD reimport with a deleted record

        Trying: reimport a file with a deleted record
        Expecting: a FinadingAid is deleted
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_ead_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://portail.cg51.mnesys.fr/oai_pmh.cgi"
            self.import_oai(cnx, url, service_infos)
            cnx.execute("Any X WHERE X eadid %(e)s", {"e": "FRAD051_000000028_203M"}).one()
            fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            # reimport a file with the sames record (one deleted)
            self.filename = "oai_ead_sample_deleted.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filename)
            self.import_oai(cnx, url, service_infos)
            new_fi_count = cnx.execute("Any X WHERE X is FindingAid").rowcount
            self.assertEqual(new_fi_count, fi_count - 1)
            self.assertFalse(
                cnx.execute("Any X WHERE X eadid %(e)s", {"e": "FRAD051_000000028_203M"})
            )

    def test_import_fa_audience_internal(self):
        """The content of tags with audience="internal" attribute is not imported

        Trying: import FRAD051_12Fi.xml

        Expecting: FAComponent with unitid='12 Fi 15' from <c audience="internal"> is not created

        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fc_rql = "Any X WHERE X is FAComponent, X did D, D unitid %(u)s"
            rset = cnx.execute(fc_rql, {"u": "12 Fi 15"})
            self.assertFalse(rset)
            # check we still have some FAComponent
            self.assertEqual(15, cnx.find("FAComponent").rowcount)

    def test_import_findingaid_support(self):
        """Test OAI EAD standard importing.

        Trying: OAI EAD standard import
        Expecting: findingaid_support attributes correspond to XML file paths
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            self.assertEqual(2, cnx.find("FindingAid").rowcount)
            if self.s3_bucket_name:
                expected_fpaths = [
                    b"tmp/FRAD051/oaipmh/ead/FRAD051_000000028_203M.xml",
                    b"tmp/FRAD051/oaipmh/ead/FRAD051_204M.xml",
                ]
            else:
                expected_fpaths = [
                    f.encode("utf-8") for f in glob.glob(osp.join(self.path(), "*.xml"))
                ]
            fpaths = [
                row[0].getvalue()
                for row in cnx.execute("Any FSPATH(D) WHERE X findingaid_support F, F data D")
            ]
            self.assertCountEqual(expected_fpaths, fpaths)
            for fpath in fpaths:
                self.assertTrue(self.fileExists(fpath))

    def test_import_findingaid_support_hash_import_oai(self):
        """
        Trying: OAI EAD standard import
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fa_supports = list(cnx.execute("Any X WHERE F findingaid_support X").entities())
            self.assertEqual(2, len(fa_supports))
            for fa_support in fa_supports:
                self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
                self.assertTrue(fa_support.check_hash())

    def test_reimport_findingaid_support(self):
        """Test EAD re-import based on XML files.

        Trying: re-import based on XML files created during OAI EAD import
        Expecting: the same data
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            rql = "Any E, FSPATH(D) WHERE X findingaid_support F, F data D, X eadid E"
            result_set = [(result[0], result[1].read()) for result in cnx.execute(rql)]
            filepaths = [result[1] for result in result_set]
            eadids = [result[0] for result in result_set]
            for filepath in filepaths:
                sqlutil.delete_from_filename(cnx, filepath, interactive=False, esonly=False)
            cnx.commit()
            self.assertFalse(cnx.find("FindingAid"))
            self.assertFalse(cnx.execute("Any X WHERE EXISTS(X findingaid_support F)"))
            rql = "Any E WHERE X is FindingAid, X eadid E"
            for filepath in filepaths:
                self.assertTrue(self.fileExists(filepath))
                self.import_filepath(cnx, filepath.decode("utf-8"))
            actual = [row[0] for row in cnx.execute(rql)]
            self.assertEqual(actual, eadids)

    def test_import_FR_920509801_service_code(self):
        """Test EAD re-import based on XML files.

        Trying: import a stored OAI EAD file from `FR_920509801` service
        Expecting: the created FindingAid is related to right `FR_920509801` service
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FR_920509801", category="foo")
            cnx.commit()
            self.filename = "FR_920509801_3000_3_listrecords.xml"
            fpath = self.get_filepath_by_storage(osp.join("oai_ead", self.filename))
            self.import_filepath(cnx, fpath)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.related_service, service)
            self.assertNotIn("publisher", fa.reverse_entity[0].doc.keys())

    def test_import_eadid_legacy_compliance(self):
        """Test Findinding harvested files `name`attrubute (and thus `stable_id`)
        is computed as <eadid>.xml
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, self.service_infos)
            rql = """Any E, FSPATH(D) WHERE X findingaid_support F,
                     F data D, X eadid E"""
            for fi in cnx.find("FindingAid").entities():
                self.assertEqual(fi.stable_id, usha1(fi.name))
            rset = cnx.execute(rql).rows
            fs_paths = [row[1].read() for row in rset]
            eadids = [row[0] for row in rset]
            # import the findingaid_support file
            for fs_path in fs_paths:
                sqlutil.delete_from_filename(cnx, fs_path, interactive=False, esonly=False)
            cnx.commit()
            for fs_path in fs_paths:
                self.import_filepath(cnx, fs_path.decode("utf-8"))
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            self.assertEqual(actual, eadids)

    def test_import_name_stable_id_oai_ead(self):
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fi1 = cnx.find("FindingAid", eadid="FRAD051_000000028_203M ").one()
            self.assertEqual(fi1.name, "FRAD051_000000028_203M.xml")
            self.assertEqual(fi1.stable_id, usha1(fi1.name))
            fi2 = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            self.assertEqual(fi2.name, "FRAD051_204M.xml")
            self.assertEqual(fi2.stable_id, usha1(fi2.name))

    def test_import_creation_date_ead(self):
        """Test FindingAid, FAComponent creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid and FAComponent have original creation_date
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            url = "file://{}?verb=ListRecords&metadataPrefix=ead".format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fa_stable_id = "060b7c36d487ba217d46f8fdfe3e7e40084f90d2"
            fa_old = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": fa_stable_id}).one()
            comp_stable_id = "2696ef61cfafde6fab2e8ca4df9da094015fa444"
            comp_old = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": comp_stable_id}).one()
            # FindingAid
            adapter = fa_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                fa_old.creation_date.isoformat(),
            )
            creation_date = datetime(1914, 4, 5)
            fmt = "%a %b %d %H:%M:%S %Y"
            fa_old.cw_set(creation_date=creation_date)
            comp_old.cw_set(creation_date=creation_date)
            cnx.commit()
            fa_old = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": fa_stable_id}).one()
            fa_old_date = fa_old.creation_date
            comp_old_date = comp_old.creation_date
            self.assertEqual(
                creation_date.strftime(fmt),
                fa_old_date.strftime(fmt),
            )
            adapter = fa_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                fa_old.creation_date.isoformat(),
            )
            # reimport the same file
            self.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": fa_stable_id}).one()
            self.assertNotEqual(fa_old.eid, fa.eid)
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                fa.creation_date.isoformat(),
                adapter.serialize()["creation_date"],
            )
            self.assertEqual(fa_old_date, fa.creation_date)
            # FAComponent
            comp = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": comp_stable_id}).one()
            adapter = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                comp.creation_date.isoformat(),
            )
            self.assertEqual(comp.creation_date, comp_old_date)

    def test_import_extentities(self):
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=ead".format(path=self.filepath())
            self.import_oai(cnx, path, self.service_infos)
            fas = cnx.find("FindingAid")
            self.assertEqual(2, len(fas))
            fa = cnx.find("FindingAid", eadid="FRAD051_000000028_203M ").one()
            self.assertEqual(4, len(fa.reverse_finding_aid))
            comp_rset = cnx.execute(
                "Any X WHERE X is FAComponent, X did D, D unittitle %(id)s",
                {"id": "Administration générale"},
            )
            self.assertEqual(1, len(comp_rset))
            comp = comp_rset.one()
            self.assertEqual(
                comp.digitized_versions[0].illustration_url,
                "http://portail.cg51.mnesys.fr/ark:/86869/a011401093704slpxLP/5/5.thumbnail",
            )  # noqa

    def test_import_new_findingaids_only(self):
        """Test OAI EAD delta import

        Trying: first import 2 records and reimport two slightly different records
                to simulate changes
        Expecting: one new FindingAid is created, one FindingAid is changed
                   and FindingAid remains unchanged
        """
        with self.admin_access.cnx() as cnx:
            self.assertFalse(cnx.find("OAIRepository"))
            self.filename = "oai_ead_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, delta=True)
            self.assertEqual(
                {fa.eadid for fa in cnx.find("FindingAid").entities()},
                {"FRAD051_000000028_203M ", "FRAD051_204M"},
            )
            fa = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            self.assertCountEqual(
                {"GUERRE 1939-1945", "Recherche détaillée", "Document d'archives"},
                {subject.label for subject in fa.subject_indexes().entities()},
            )
            self.assertIn("BAUDIN", fa.bibliography)
            self.assertEqual(
                fa.dc_title(), "204 M - Organisation économique pendant la guerre 1939-1945"
            )
            # now reimport a slightly different file to simulate changes
            # and check updates
            self.filename = "oai_ead_sample_updated.xml"
            repo = cnx.find("OAIRepository").one()
            repo.cw_set(
                url=repo.url.replace(
                    "oai_ead/oai_ead_sample.xml", "oai_ead/oai_ead_sample_updated.xml"
                )
            )
            self.import_oai(cnx, url, delta=True, repo=repo)
            # we should have :
            # FRAD051_000000028_203M untouched
            # FRAD051_204M updated (title changed, bibliography removed and
            #                       indexation changed)
            # FRAD051_205M created
            self.assertEqual(
                {fa.eadid for fa in cnx.find("FindingAid").entities()},
                {"FRAD051_000000028_203M ", "FRAD051_204M", "FRAD051_205M"},
            )
            fa = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            self.assertEqual(
                fa.dc_title(), "MAJ - 204 M - Organisation économique pendant la guerre 1939-1945"
            )
            self.assertEqual(fa.bibliography, None)
            self.assertCountEqual(
                {subject.label for subject in fa.subject_indexes().entities()},
                {
                    "GUERRE 1939-1945",
                    "La guerre de 39",
                    "Recherche détaillée",
                    "Document d'archives",
                },
            )

    def test_create_ape_ead_file(self):
        """test specific francearchive ape_ead transformations"""
        with self.admin_access.cnx() as cnx:
            service = cnx.find("Service", code="FRAD051").one()
            service.cw_set(iiif_extptr=True, iiif_ead_policy="iiif_ligeo_extptr")
            cnx.commit()
            self.filename = "oai_ead_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            service_infos = self.service_infos.copy()
            service_infos["iiif_ead_policy"] = "iiif_ligeo_extptr"
            self.import_oai(cnx, url, service_infos=service_infos, delta=True)
            fa = cnx.find("FindingAid", eadid="FRAD051_204M").one()
            ape_ead_filepath = fa.ape_ead_file[0]
            content = ape_ead_filepath.data.read()
            tree = etree.fromstring(content)
            eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
            self.assertEqual(
                eadid.attrib["url"], "https://francearchives.gouv.fr/{}".format(fa.rest_path())
            )
            extptrs = tree.xpath("//e:extptr", namespaces={"e": tree.nsmap[None]})
            self.assertEqual(len(extptrs), 5)
            for xlink in extptrs:
                self.assertTrue(
                    xlink.attrib["{{{e}}}href".format(e=tree.nsmap["xlink"])].startswith("http")
                )
                self.assertEqual(eadid.attrib["countrycode"], "FR")
            expected_manifests = self.get_iiif_manifests(cnx)
            self.assertEqual(2, len(expected_manifests))
            got_manifests = self.get_iiif_manifests_from_tree(tree)
            self.assertEqual(1, len(got_manifests))

    def test_unique_indexes(self):
        """Test that no duplicate authorities are created during oai_ead import"""
        with self.admin_access.cnx() as cnx:
            location_label = "Paris (Île-de-France, Paris)"
            cnx.create_entity("LocationAuthority", label=location_label)
            cnx.create_entity("AgentAuthority", label="Préfecture de la Marne")
            cnx.commit()
            self.filename = "oai_ead_sample_listrecords.xml"
            with open(self.filepath()) as fp:
                element_tree = etree.parse(fp)
            geognames = [geogname.text for geogname in element_tree.findall(".//{*}geogname")]
            self.assertEqual([location_label], geognames)
            cnx.commit()
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, delta=True)
            self.assertCountEqual(
                [
                    "Préfecture de la Marne",
                    (
                        "Préfecture régionale de Châlons-sur-Marne, "
                        "devenue Commissariat de la République française "
                        "pour la Région de Châlons-sur-Marne."
                    ),
                ],
                [e.label for e in cnx.find("AgentAuthority").entities()],
            )
            self.assertEqual(1, len(cnx.find("LocationAuthority")))

    def create_findingaid(self, cnx, eadid, service):
        return cnx.create_entity(
            "FindingAid",
            name=eadid,
            stable_id=f"stable_id{eadid}",
            eadid=eadid,
            publisher="publisher",
            did=cnx.create_entity("Did", unitid=f"unitid{eadid}", unittitle=f"title{eadid}"),
            fa_header=cnx.create_entity("FAHeader"),
            service=service,
        )

    def test_unique_grouped_indexes(self):
        """Test that no duplicate authorities are created
        during oai_ead import"""
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_ead_sample.xml"
            service = cnx.find("Service", code="FRAD051").one()
            agent_label = "Préfecture de la Marne"
            loc1 = cnx.create_entity("AgentAuthority", label=agent_label)
            loc2 = cnx.create_entity("AgentAuthority", label=agent_label)
            fa1 = self.create_findingaid(cnx, "eadid1", service)
            cnx.create_entity("AgentName", label="index agent 1", index=fa1, authority=loc1)
            fa2 = self.create_findingaid(cnx, "eadid2", service)
            cnx.create_entity("AgentName", label="index agent 2", index=fa2, authority=loc2)
            cnx.commit()
            loc1.group([loc2.eid])
            cnx.commit()
            self.assertEqual(2, cnx.find("AgentAuthority", label=agent_label).rowcount)
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, delta=True)
            self.assertEqual(2, cnx.find("AgentAuthority", label=agent_label).rowcount)
            fa = cnx.find("FindingAid", eadid="FRAD051_000000028_203M ").one()
            agents = [ie.authority[0] for ie in fa.reverse_index if ie.cw_etype == "AgentName"]
            self.assertEqual(1, len(agents))
            self.assertEqual(loc1.eid, agents[0].eid)

    @patch("cubicweb_francearchives.dataimport.oai.harvest_oai")
    def test_from_parameter_first_import(self, harvest_oai):
        """check _from parameter is not set on first harvesting pass"""
        with self.admin_access.cnx() as cnx:
            url = "http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead"
            repo, _ = self.create_repo(cnx, url=url, delta=True)
            oai.harvest_delta(cnx, repo.eid)
            repo.cw_clear_all_caches()
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://oai.frad051.fr/"

            harvest_oai.assert_called_with(
                cnx,
                url,
                repo.reverse_oai_repository[0].eid,
                records_limit=None,
                dry_run=False,
                log=logging.getLogger("rq.task"),
                service_infos=service_infos,
            )
            self.assertEqual(len(repo.tasks), 1, "we should have exactly one import task")
            twf = repo.tasks[0].cw_adapt_to("IWorkflowable")
            twf.entity.cw_clear_all_caches()
            self.assertEqual(twf.state, "wfs_oaiimport_completed")

    @patch("cubicweb_francearchives.dataimport.oai.harvest_oai")
    def test_from_parameter_last_succcessful_import(self, harvest_oai):
        """check _from parameter is inserted when re-harvesting"""
        with self.admin_access.cnx() as cnx:
            # the last successful import date is set in the frarchives-edition
            # oai import scripts
            repo, _ = self.create_repo(
                cnx,
                url="http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead",
                delta=True,
            )
            repo.cw_set(last_successful_import=datetime(2001, 2, 3))
            cnx.commit()
            oai.harvest_delta(cnx, repo.eid)
            repo.cw_clear_all_caches()
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://oai.frad051.fr/"

            harvest_oai.assert_called_with(
                cnx,
                "http://oai.frad051.fr/?verb=ListRecords&metadataPrefix=ape_ead&from=2001-02-03",
                repo.reverse_oai_repository[0].eid,
                records_limit=None,
                dry_run=False,
                log=logging.getLogger("rq.task"),
                service_infos=service_infos,
            )

    def test_import_facomponents_es_document(self):
        """Test FAComponent EsDocument
        Trying: import FRAD051_12Fi.xml

        Expecting: ESDocument is well formed

        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            es_doc = fa.reverse_entity[0].doc
            for attr in ("_id", "_type", "_index", "publisher"):
                self.assertNotIn(attr, es_doc)
            for attr in ("stable_id", "index_entries", "escategory", "fa_stable_id"):
                self.assertIn(attr, es_doc)

    def test_import_es_dates_infos(self):
        """Test OAI harvest es data

        Trying: harvest some records
        Expecting: dates infos are found in FAComponent but not in FindingAid es indexes
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            json = fa.cw_adapt_to("IFullTextIndexSerializable").serialize()
            # no dates for FindingAid
            self.assertFalse(fa.did[0].unitdate)
            self.assertFalse(fa.did[0].period)
            for attr in ("sortdate", "stopyear", "startyear"):
                self.assertNotIn(attr, json)
            comp = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            comp_json = comp.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("[vers 1918]", comp.did[0].unitdate)
            self.assertEqual("1918-01-01", comp_json["sortdate"])
            self.assertEqual(1918, comp_json["startyear"])
            self.assertEqual(1918, comp_json["stopyear"])

    def test_import_es_service_infos(self):
        """Test OAI harvest es data

        Trying: harvest some records
        Expecting: service infos are found in FAComponent and FindingAid es indexes
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "FRAD051_12Fi.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            expected = {
                "eid": self.service_infos["eid"],
                "level": "None",
                "code": "FRAD051",
                "title": "Marne",
            }
            self.assertEqual(expected, adapted.serialize()["service"])
            comp = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            adapted = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize()["service"])

    def test_findingaid_esdoc(self):
        """Testing FindingAid IFullTextIndexSerializable

        Trying: import a FindingAid
        Expecting: FindingAid ESDocument content is correct
                   and equal to es_json from generated from DB
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FR_920509801", category="foo")
            cnx.commit()
            self.filename = "FR_920509801_3000_3_listrecords.xml"
            fpath = self.get_filepath_by_storage(osp.join("oai_ead", self.filename))
            self.import_filepath(cnx, fpath)
            fa = cnx.find("FindingAid").one()
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            expected = {
                "acquisition_info": None,
                "alltext": "Etats des inventaires des collections de du Fichier national et "
                "continental de la BDIC",
                "creation_date": fa.creation_date.isoformat(),
                "cw_etype": "FindingAid",
                "did": {"unitid": "COTES/MULTIPLES", "unittitle": "Pays et continents"},
                "digitized": False,
                "digitized_all": DZFacetValues.nondz,
                "eadid": "FR_920509801_3000/3",
                "eid": fa.eid,
                "escategory": "archives",
                "fa_stable_id": "88d62c25f73ab94ab87bd28d876af3be3cde10b4",
                "index_entries": [],
                "originators": [],
                "scopecontent": None,
                "service": {
                    "code": "FR_920509801",
                    "eid": service.eid,
                    "level": "None",
                    "title": "FR_920509801",
                },
                "stable_id": "88d62c25f73ab94ab87bd28d876af3be3cde10b4",
            }
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize())
            es_from_db = adapted.serialize_from_db()
            es_from_db.update(
                {
                    "originators": [],
                    "index_entries": [],
                    "scopecontent": None,
                    "acquisition_info": None,
                }
            )  # None values are removed by adapter
            self.assertEqual(expected, es_from_db)

    def test_facomponent_esdoc(self):
        """Testing FAComponent IFullTextIndexSerializable

        Trying: import a FindingAid
        Expecting: FAComponent ESDocument content is correct
                   and equal to es_json from generated from DB
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FR_920509801", category="foo")
            cnx.commit()
            self.filename = "FR_920509801_3000_3_listrecords.xml"
            fpath = self.get_filepath_by_storage(osp.join("oai_ead", self.filename))
            self.import_filepath(cnx, fpath)
            fc = cnx.execute(
                "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s",
                {"unitid": "4/DELTA/RES/0205"},
            ).one()
            authorities = {}
            for etype in ("AgentAuthority", "LocationAuthority", "SubjectAuthority"):
                authorities.update(
                    {e[0]: e[1] for e in cnx.execute(f"Any L, X WHERE X is {etype}, X label L")}
                )
            expected = {
                "acquisition_info": None,
                "creation_date": fc.creation_date.isoformat(),
                "cw_etype": "FAComponent",
                "dates": {"gte": 1969, "lte": 1970},
                "did": {
                    "unitid": "4/DELTA/RES/0205",
                    "unittitle": "Mouvement d'Actions et de Réflexions Critiques",
                },
                "digitized": False,
                "digitized_all": DZFacetValues.nondz,
                "eadid": None,
                "eid": fc.eid,
                "escategory": "archives",
                "fa_stable_id": "88d62c25f73ab94ab87bd28d876af3be3cde10b4",
                "index_entries": [
                    {
                        "authfilenumber": "026403587",
                        "authority": authorities["Université de Paris-Nanterre"],
                        "authtype": "AgentAuthority",
                        "label": "Université de Paris-Nanterre",
                        "type": "corpname",
                    },
                    {
                        "authfilenumber": "150678622",
                        "authority": authorities[
                            "Mouvement d'Action et de Recherche Critique (France)"
                        ],
                        "authtype": "AgentAuthority",
                        "label": "Mouvement d'Action et de Recherche Critique " "(France)",
                        "type": "corpname",
                    },
                    {
                        "authfilenumber": "027380920",
                        "authority": authorities["France -- 1969-1974 (G. Pompidou)"],
                        "authtype": "LocationAuthority",
                        "label": "France -- 1969-1974 (G. Pompidou)",
                        "type": "geogname",
                    },
                    {
                        "authfilenumber": "027519457",
                        "authority": authorities["Mouvements étudiants"],
                        "authtype": "SubjectAuthority",
                        "label": "Mouvements étudiants",
                        "type": "subject",
                    },
                ],
                "originators": [],
                "scopecontent": None,
                "service": {
                    "code": "FR_920509801",
                    "eid": service.eid,
                    "level": "None",
                    "title": "FR_920509801",
                },
                "sortdate": "1969-01-01",
                "stable_id": "b0ea268aced0f6612c12318feb647cd7df187c28",
                "startyear": 1969,
                "stopyear": 1970,
            }
            adapted = fc.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize())
            es_from_db = adapted.serialize_from_db()
            es_from_db.update(
                {
                    "eadid": None,
                    "originators": [],
                    "scopecontent": None,
                    "acquisition_info": None,
                }
            )  # None values are removed by adapter
            esdoc_indexes = sort_authorities(expected.pop("index_entries"))
            from_db_indexes = sort_authorities(es_from_db.pop("index_entries"))
            self.assertEqual(esdoc_indexes, from_db_indexes)
            self.assertEqual(expected, es_from_db)


if __name__ == "__main__":
    unittest.main()
