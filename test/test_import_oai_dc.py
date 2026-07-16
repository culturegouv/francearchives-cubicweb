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
# The fact that you are presently reading this means that you have had
# knowledge of the CeCILL-C license and that you accept its terms.
#
from datetime import datetime
import glob

import logging
from mock import patch
from os import path as osp

import os
import unittest

from cubicweb_web.devtools.testlib import WebCWTC
from lxml import etree

from cubicweb_francearchives.testutils import (
    EADImportMixin,
    PostgresTextMixin,
    OaiImportMixin,
    XMLCompMixin,
)

from cubicweb_francearchives.dataimport import (
    get_year,
    oai,
    oai_dc,
    oai_utils,
    usha1,
    sqlutil,
    load_services_map,
    service_infos_from_service_code,
)

from cubicweb_francearchives.dataimport.oai_dc import OAIDCHarvestedReader

from cubicweb_francearchives.dataimport.importer import import_filepaths
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_other_sources_from_eids,
    generate_ape_ead_from_other_sources,
)
from cubicweb_francearchives.entities.es import DZFacetValues

from cubicweb_francearchives.utils import merge_dicts

from pgfixtures import setup_module, teardown_module  # noqa


def parse_metadata_dates(date):
    date = [date] if date else []
    res = oai_utils.build_metadata({"date": date})
    return {"start": res["date1"], "stop": res["date2"]}


def find_component(cnx, unittitle):
    rset = cnx.execute(
        "Any X WHERE X is FAComponent, X did D, " "D unittitle %(unittitle)s",
        {"unittitle": unittitle},
    )
    if rset:
        return rset.one()
    return None


class OaiDcImportTC(OaiImportMixin, PostgresTextMixin, XMLCompMixin, WebCWTC):

    readerconfig = merge_dicts(
        {}, EADImportMixin.readerconfig, {"reimport": True, "nodrop": False, "force_delete": True}
    )

    def tearDown(self):
        """Tear down test cases."""
        super().tearDown()
        directories = [self.path({"code": code}) for code in ("FRAD034", "FRAD055")]
        for directory in directories:
            if osp.exists(directory):
                for filename in glob.glob(osp.join(directory, "*")):
                    os.remove(filename)
                os.removedirs(directory)

    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service",
                code="FRAD055",
                level="level-D",
                name="Service",
                category="test",
                iiif_extptr=True,
            )
            cnx.commit()
            services_map = load_services_map(cnx)
            self.service_infos = service_infos_from_service_code(self.service.code, services_map)
            self.service_eid = self.service.eid
            self.filename = "oai_dc_sample.xml"
            repo, oaitask = self.create_repo(
                cnx,
                url="file://{path}?verb=ListRecords&metadataPrefix=ead".format(
                    path=self.filepath()
                ),
            )
            self.repo_eid = repo.eid
            self.oaitask_eid = oaitask.eid

    def init_reader(self, settings, store, *args):
        return OAIDCHarvestedReader(settings, store)

    def filepath(self, filename=None):
        filename = filename or self.filename
        assert filename is not None
        return self.datapath(osp.join("oai_dc", filename))

    def path(self, service_infos=None):
        service_infos = service_infos or self.service_infos
        return "{ead_services_dir}/{code}/oaipmh/dc".format(
            ead_services_dir=self.config["ead-services-dir"], **service_infos
        )

    def test_parse_metadata_dates(self):
        drange = parse_metadata_dates
        self.assertEqual(drange(None), {"start": "", "stop": ""})
        self.assertEqual(drange(" "), {"start": "", "stop": ""})
        self.assertEqual(drange("foo"), {"start": "", "stop": ""})
        self.assertEqual(drange("82"), {"start": "82", "stop": "82"})
        self.assertEqual(drange("823"), {"start": "823", "stop": "823"})
        self.assertEqual(drange("823 - 1022"), {"start": "823", "stop": "1022"})
        self.assertEqual(drange("823-1022"), {"start": "823", "stop": "1022"})
        self.assertEqual(drange("  823 -1022  "), {"start": "823", "stop": "1022"})
        self.assertEqual(drange("823 - 102"), {"start": "823", "stop": "823"})
        self.assertEqual(drange("823/1922"), {"start": "823", "stop": "1922"})
        self.assertEqual(drange("823 / 1922"), {"start": "823", "stop": "1922"})
        self.assertEqual(drange("1817-01-01"), {"start": "1817", "stop": "1817"})
        self.assertEqual(drange("1817/03/01"), {"start": "1817", "stop": "1817"})
        self.assertEqual(drange("02/02/1865"), {"start": "", "stop": ""})
        self.assertEqual(drange("1234/01/02 - 1235/02/03"), {"start": "1234", "stop": "1235"})
        self.assertEqual(drange("1234/01/02-1235/02/03"), {"start": "1234", "stop": "1235"})
        self.assertEqual(drange("1234-01-02 / 1235-02-03"), {"start": "1234", "stop": "1235"})
        self.assertEqual(drange("1234-01-02/1235-02-03"), {"start": "1234", "stop": "1235"})
        self.assertEqual(drange("1801-01-01/2000-12-31"), {"start": "1801", "stop": "2000"})

    def test_parse_year(self):
        drange = get_year
        self.assertEqual(drange(None), None)
        self.assertEqual(drange(" "), None)
        self.assertEqual(drange("foo"), None)
        self.assertEqual(drange("82"), "82")
        self.assertEqual(drange("823"), "823")
        self.assertEqual(drange("1022"), "1022")
        self.assertEqual(drange("  1022  "), "1022")
        self.assertEqual(drange("17-01-01"), "17")
        self.assertEqual(drange("917-01-01"), "917")
        self.assertEqual(drange("1917/03/01"), "1917")

    def test_harvest(self):
        """Test harvest OAI-PMH records

        Trying: importing records
        Expecting: corresponding XML files are harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(["FRAD055_REC.xml"], zf.namelist())

    def test_harvest_deleted(self):
        """Test OAI DC harvest a deleted record

        Trying: import an deleted record
        Expecting: XML file with the deleted record is  harvested
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample_deleted.xml"
            url = f"file://{self.filename}?verb=ListRecords&metadataPrefix=oai_dc"
            repo, oaitask = self.create_repo(cnx, url)
            oai.harvest_oai(cnx, url, oaitask.eid, self.service_infos)
            zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
            self.assertEqual(1, len(zipfiles))
            zf = self.get_zipfile(cnx, zipfiles[0])
            self.assertEqual(["FRAD055_REC.xml"], zf.namelist())

    def test_import_oai_dc_records(self):
        """Test OAI DC import

        Trying: importing records
        Expecting: corresponding XML files are harvested and imported
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, url, self.service_infos)
                self.assertEqual(1, cnx.execute("Any COUNT(X) WHERE X is FindingAid")[0][0])
                self.assertEqual(3, cnx.execute("Any COUNT(X) WHERE X is FAComponent")[0][0])
                fac_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
                unittitle = "62J1 Ordre et syndicat des architectes"
                fac = cnx.execute(fac_rql, {"u": unittitle}).one()
                self.assertEqual("a02bfbc73e5e6c97cda10abea6cb989f8bd9625e", fac.stable_id)

    @unittest.skip("Delete is not implemented on OAI_DC")
    def test_import_oai_dc_deleted(self):
        """Test OAI DC reimport with a deleted record

        Trying: reimport a file with a deleted record
        Expecting: a FinadingAid is deleted
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://portail.cg51.mnesys.fr/oai_pmh.cgi"
            self.import_oai(cnx, path, service_infos)
            self.assertEqual(1, cnx.execute("Any X WHERE X is FindingAid").rowcount)
            self.assertEqual(2, cnx.execute("Any X WHERE X is FAComponent").rowcount)
            # reimport a file with the sames record (one deleted)
            self.filename = "oai_dc_sample_deleted.xml"
            url = f"file://{self.filename}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, url, service_infos)
            self.assertFalse(
                cnx.execute("Any X WHERE X eadid %(e)s", {"e": "FRAD051_000000028_203M"})
            )
            self.assertEqual(0, cnx.execute("Any X WHERE X is FindingAid").rowcount)
            self.assertEqual(0, cnx.execute("Any X WHERE X is FAComponent").rowcount)

    def test_import_no_service_eid(self):
        """Test import OAI-PMH with a service without eid .

        Trying: importing records
        Expecting: import aborted
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            service_infos = {"code": "FRAD055", "eid": None}
            self.import_oai(cnx, url, service_infos)
            self.assertEqual(cnx.find("FindingAid").rowcount, 0)

    def test_reimport_findingaid_support(self):
        """Test re-import of OAI-PMH records from backup file.

        Trying: re-import based on backup file created during import
        Expecting: the same data
        """
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            # import
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fi_rql = "Any X, E, FSPATH(D) WHERE X findingaid_support F, F data D," " X eadid E"
            fi_eid, fi_eadid, fs_path = [
                (eid, eadid, fpath.getvalue()) for eid, eadid, fpath in cnx.execute(fi_rql)
            ][0]
            # import the findingaid_support file
            url = url_str.format(fs_path.decode("utf-8"))
            self.import_oai(cnx, url, self.service_infos)
            self.assertEqual(cnx.find("FindingAid").rowcount, 1)
            nfi_eid, nfi_eadid, nfs_path = [
                (eid, eadid, fpath.getvalue()) for eid, eadid, fpath in cnx.execute(fi_rql)
            ][0]
            self.assertNotEqual(fi_eid, nfi_eid)
            self.assertEqual(fi_eadid, nfi_eadid)
            self.assertEqual(fs_path, nfs_path)

    def test_eadid_legacy_compliance(self):
        """Test Findinding (and thus FAComponent) of harvested files are always based on
        <name> value which value is the same as the filename
        and stored on FindingAid.name
        """
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fi = cnx.find("FindingAid").one()
            self.assertEqual("{}.xml".format(fi.eadid), fi.name)
            self.assertEqual(fi.stable_id, usha1(fi.name))
            fs_path = cnx.execute("Any FSPATH(D) WHERE X findingaid_support F, " "F data D")[0][
                0
            ].getvalue()
            # import the findingaid_support file
            url = url_str.format(fs_path.decode("utf-8"))
            self.import_oai(cnx, url, self.service_infos)
            fi = cnx.find("FindingAid").one()
            self.assertEqual(fi.stable_id, usha1(fi.name))

    def test_name_stable_id_oai_dc(self):
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fi = cnx.find("FindingAid").one()
            self.assertEqual("FRAD055_REC.xml", fi.name)
            self.assertEqual("FRAD055_REC", fi.eadid)
            self.assertEqual(fi.stable_id, usha1(fi.name))
            self.assertTrue(fi.oai_id)

    def test_facomponent_stable_id(self):
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                self.assertEqual(1, cnx.execute("Any COUNT(X) WHERE X is FindingAid")[0][0])
                self.assertEqual(20, cnx.execute("Any COUNT(X) WHERE X is FAComponent")[0][0])
                fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
                fac = cnx.execute(fc_rql, {"u": "Naissances  (1813-1832)"}).one()
                self.assertEqual("700cef882045b97dfacec5850aa58721fc394cd9", fac.stable_id)

    def test_findingaid_esdocument(self):
        """Test imported FindingAid has an EsDocument.

        Trying: importing records
        Expecting: FindingAid has related EsDocument
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fi = cnx.execute("Any X WHERE X is FindingAid").one()
                autority = cnx.find(
                    "AgentAuthority", label="Archives départementales de la Meuse"
                ).one()
                self.assertFalse(fi.did[0].unitdate)
                self.assertFalse(fi.did[0].period)
                es_doc = fi.reverse_entity[0].doc
                es_doc.pop("creation_date")
                expected = {
                    "alltext": "FRAD055",
                    "escategory": "archives",
                    "cw_etype": "FindingAid",
                    "did": {"unittitle": "FRAD055", "unitid": None},
                    "digitized_all": "non-digitized",
                    "digitized": False,
                    "eadid": "FRAD055_REC",
                    "eid": fi.eid,
                    "stable_id": "c8d28639042d97da67a5362e2560a5a5d7ea9fc5",
                    "index_entries": [
                        {
                            "type": "name",
                            "label": "Archives départementales de la Meuse",
                            "authfilenumber": None,
                            "authtype": "AgentAuthority",
                            "authority": autority.eid,
                        }
                    ],
                    "fa_stable_id": "c8d28639042d97da67a5362e2560a5a5d7ea9fc5",
                    "scopecontent": None,
                    "originators": ["Archives départementales de la Meuse"],
                    "service": {
                        "eid": fi.related_service.eid,
                        "level": "level-D",
                        "code": "FRAD055",
                        "title": "Service",
                    },
                }
                self.assertDictEqual(expected, es_doc)

    def test_facomponent_esdocuments(self):
        """Test FAComponent ESDocuments are well formed.

        Trying: importing records
        Expecting: ESDocument are well formed
        """
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
            fa = cnx.execute(
                "Any X WHERE X is FAComponent, "
                "X stable_id 'a02bfbc73e5e6c97cda10abea6cb989f8bd9625e'"
            ).one()
            self.assertEqual("02/02/1865", fa.did[0].unitdate)
            es_doc = fa.reverse_entity[0].doc
            es_doc.pop("creation_date")
            agent = cnx.find("AgentAuthority", label="Archives départementales de la Meuse").one()
            service = fa.related_service
            expected = {
                "cw_etype": "FAComponent",
                "did": {
                    "unitid": "62J1-205",
                    "unittitle": "62J1 Ordre et syndicat des architectes",
                },
                "digitized_all": "non-digitized",
                "digitized": False,
                "eadid": None,
                "eid": fa.eid,
                "escategory": "archives",
                "fa_stable_id": "c8d28639042d97da67a5362e2560a5a5d7ea9fc5",
                "index_entries": [
                    {
                        "authfilenumber": None,
                        "authority": cnx.find("AgentAuthority", label="Jean Marais").one().eid,
                        "authtype": "AgentAuthority",
                        "label": "Jean Marais",
                        "type": "persname",
                    },
                    {
                        "authfilenumber": None,
                        "authority": cnx.find("LocationAuthority", label="Paris").one().eid,
                        "authtype": "LocationAuthority",
                        "label": "Paris",
                        "type": "geogname",
                    },
                    {
                        "authfilenumber": None,
                        "authority": cnx.find("SubjectAuthority", label="France").one().eid,
                        "authtype": "SubjectAuthority",
                        "label": "France",
                        "type": "subject",
                    },
                    {
                        "authfilenumber": None,
                        "authority": agent.eid,
                        "authtype": "AgentAuthority",
                        "label": "Archives départementales de la Meuse",
                        "type": "name",
                    },
                ],
                "originators": ["Archives départementales de la Meuse"],
                "scopecontent": "description",
                "service": {
                    "code": service.code,
                    "eid": service.eid,
                    "level": service.level,
                    "title": service.name,
                },
                "stable_id": "a02bfbc73e5e6c97cda10abea6cb989f8bd9625e",
            }
            self.assertDictEqual(expected, es_doc)

    def _test_metadata(self, header, metadata):
        self.assertEqual(
            metadata,
            {
                "contributor": ["Jean Valjean", "Victor Hugo"],
                "coverage": ["France"],
                "creator": ["Archives départementales de la Meuse"],
                "date": "1865-1981",
                "date1": "1865",
                "date2": "1981",
                "description": ["description"],
                "format": ["8.0"],
                "identifier": [
                    "https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRM"
                ],
                "language": ["eng"],
                "publisher": ["Archives départementales du Doubs"],
                "relation": ["vignette 1", "vignette 2"],
                "rights": [
                    "Les documents peuvent être reproduits sous réserve de leur bon état de conservation. La reproduction et la réutilisation des documents sont soumises aux dispositions du règlement général de réutilisation des informations publiques des Archives départementales du Doubs. "  # noqa
                ],
                "source": ["62J-105"],
                "subject": ["Architecture", "Livre"],
                "title": ["62J Ordre et syndicat des architectes"],
                "type": ["fonds", "fake type"],
            },
        )

    def test_metadata_with_setname(self):
        """Test writing OAI-PMH import with setName provided in record.

        Trying: harvest records with setName
        Expecting: harvest succeeded, record specName is used as
                   header["name"] (unittitle of findingaid)
        """
        self.filename = "oai_dc_sample.xml"
        path = "file://{path}".format(path=osp.join(self.filepath()))
        client = oai_utils.PniaSickle(path)
        records = client.ListRecords(metadataPrefix="oai_dc")
        record = next(records)
        header = oai_utils.build_header(record.header, {})
        self.assertEqual(
            header,
            {
                "eadid": "FRAD055_REC",
                "identifier": "86869/a011349628476eWWr7u",
                "name": "FRAD055",
            },  # noqa
        )
        metadata = oai_utils.build_metadata(record.metadata)
        self._test_metadata(header, metadata)

    def test_metadata_no_setname(self):
        """Test writing OAI-PMH import with no setName provided in record, but
        setLists values provided

        Trying: harvest records with setSpec
        Expecting: harvest succeeded, setName from setLists is used as
                   header["name"] (unittitle of findingaid)

        """
        self.filename = "oai_dc_sample_no_setname.xml"
        path = "file://{path}".format(path=osp.join(self.filepath()))
        client = oai_utils.PniaSickle(path)
        records = client.ListRecords(metadataPrefix="oai_dc")
        record = next(records)
        # setList provided
        setList = oai_dc.get_sets_dict(client.ListSets())
        header = oai_utils.build_header(record.header, setList)
        self.assertEqual(
            header,
            {"eadid": "FRAD055_REC", "identifier": "86869/a011349628476eWWr7u", "name": "FRAD055"},
        )
        metadata = oai_utils.build_metadata(record.metadata)
        self._test_metadata(header, metadata)

    def test_metadata_no_setdata(self):
        """Test writing OAI-PMH import with nor setName or setLists provided

        Trying: harvest records with setSpec but without setName and listSets empty
        Expecting: harvest aborted
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample_no_setdata.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, url, self.service_infos)
            self.assertEqual(cnx.find("FindingAid").rowcount, 0)

    def test_import_meuse_extentities(self):
        with self.admin_access.cnx() as cnx:
            cnx.commit()
            self.filename = "oai_dc_meuse_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fa_rset = cnx.execute("Any X WHERE X is FindingAid")
                self.assertEqual(len(fa_rset), 1)
                es_fa_rset = cnx.execute("Any ES WHERE X is FindingAid, ES entity X")
                self.assertEqual(len(es_fa_rset), 1)
                fac_rset = cnx.execute("Any X WHERE X is FAComponent")
                self.assertEqual(len(fac_rset), 20)
                es_fac_rset = cnx.execute("Any ES WHERE X is FAComponent, ES entity X")
                self.assertEqual(len(es_fac_rset), 20)

    def test_import_extentities(self):
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                # create ape_ead_files
                generate_ape_ead_from_other_sources(cnx)
                fa_rset = cnx.execute("Any X WHERE X is FindingAid")
                self.assertEqual(len(fa_rset), 1)
                fa = fa_rset.one()
                self.assertEqual(fa.eadid, "FRAD055_REC")
                self.assertEqual(fa.name, "FRAD055_REC.xml")
                self.assertEqual(fa.publisher, "Service")
                self.assertEqual(fa.service[0].eid, self.service_eid)
                self.assertEqual(fa.scopecontent, None)
                self.assertEqual(fa.did[0].unitid, None)
                self.assertEqual(fa.did[0].unittitle, "FRAD055")
                self.assertEqual(fa.did[0].startyear, None)
                self.assertEqual(fa.did[0].stopyear, None)
                self.assertEqual(fa.did[0].unitdate, None)
                self.assertEqual(fa.did[0].origination, "Archives départementales de la Meuse")
                self.assertEqual(fa.did[0].lang_code, None)
                self.assertEqual(fa.fa_header[0].titleproper, "FRAD055")
                # assert there is only one "Archives départementales de la Meuse" authority
                cnx.find("AgentAuthority", label="Archives départementales de la Meuse").one()
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label, ie.role)
                    for ie in fa.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [("AgentAuthority", "Archives départementales de la Meuse", "originator")],
                )
                facs_rset = cnx.execute("Any F WHERE F is FAComponent")
                facs = list(facs_rset.entities())
                facs.sort(key=lambda fac: fac.did[0].unitid)
                fac1, fac2, fac3 = facs
                fac1_did = fac1.did[0]
                self.assertEqual(fac1_did.unittitle, "62J Ordre et syndicat des architectes")
                self.assertEqual(fac1_did.unitid, "62J-105")
                self.assertEqual(fac1_did.origination, "Archives départementales de la Meuse")
                self.assertEqual(fac1_did.unitdate, "1865-1981")
                self.assertEqual(fac1_did.startyear, 1865)
                self.assertEqual(fac1_did.stopyear, 1981)
                self.assertEqual(fac1.did[0].lang_code, "eng")
                self.assertEqual(fac1.did[0].lang_description, None)
                self.assertIn('<div class="ead-p">8.0</div>', fac1_did.physdesc)
                self.assertIn('<div class="ead-p">description</div>', fac1.scopecontent)
                self.assertIn('<div class="ead-p">Les documents peuvent', fac1.userestrict)
                bounce_url = "https://recherche-archives.doubs.fr/ark:/25993/a011369750208WU2TRM"
                self.assertEqual(bounce_url, fac1.did[0].extptr)
                self.assertEqual(bounce_url, fac1.bounce_url)
                self.assertCountEqual(
                    [dao.url for dao in fac1.digitized_versions if dao.url],
                    [
                        "vignette 1",
                        "vignette 2",
                    ],
                )
                self.assertFalse(
                    [
                        dao.illustration_url
                        for dao in fac1.digitized_versions
                        if dao.illustration_url
                    ],
                )
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label, ie.role)
                    for ie in fac1.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "Architecture", "index"),
                        ("SubjectAuthority", "Livre", "index"),
                        ("AgentAuthority", "Jean Valjean", "index"),
                        ("AgentAuthority", "Victor Hugo", "index"),
                        ("LocationAuthority", "France", "index"),
                        ("AgentAuthority", fac1_did.origination, "originator"),
                    ],
                )
                fac2_did = fac2.did[0]
                self.assertEqual(fac2_did.unittitle, "62J1 Ordre et syndicat des architectes")
                self.assertEqual(fac2_did.unitid, "62J1-205")
                self.assertEqual(fac2_did.origination, "Archives départementales de la Meuse")
                self.assertEqual(fac2_did.unitdate, "02/02/1865")
                self.assertEqual(fac2_did.startyear, None)
                self.assertEqual(fac2_did.stopyear, None)
                self.assertEqual(fac2.did[0].lang_code, None)
                self.assertIn('<div class="ead-p">eng ; fra</div>', fac2.did[0].lang_description)
                self.assertIn('<div class="ead-p">12.19 ; text/html</div>', fac2_did.physdesc)
                self.assertIn('<div class="ead-p">description</div>', fac2.scopecontent)
                self.assertIn('<div class="ead-p">Les documents peuvent', fac2.userestrict)
                self.assertEqual(len(fac2.digitized_versions), 0)
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label, ie.role)
                    for ie in fac2.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "France", "index"),
                        ("AgentAuthority", "Jean Marais", "index"),
                        ("LocationAuthority", "Paris", "index"),
                        ("AgentAuthority", fac2_did.origination, "originator"),
                    ],
                )
                # ape_ead_file must be created
                ape_ead_file = fa.ape_ead_file[0]
                content = ape_ead_file.data.read()
                tree = etree.fromstring(content)
                eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
                self.assertEqual(
                    eadid.attrib["url"], "https://francearchives.gouv.fr/{}".format(fa.rest_path())
                )

    def test_unique_indexes(self):
        """Test that no duplicate authorities are created during oai_dc import"""
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("LocationAuthority", label="Paris")
            cnx.create_entity("AgentAuthority", label="Jean Valjean")
            cnx.create_entity("SubjectAuthority", label="Architecture")
            cnx.create_entity("SubjectAuthority", label="Livre")
            cnx.create_entity("AgentAuthority", label="Archives départementales de la Meuse")
            cnx.commit()
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                self.assertEqual(
                    ["Architecture", "France", "Livre"],
                    sorted([e.label for e in cnx.find("SubjectAuthority").entities()]),
                )
                self.assertEqual(
                    [
                        "Archives départementales de la Meuse",
                        "Jean Marais",
                        "Jean Valjean",
                        "Victor Hugo",
                    ],
                    sorted([e.label for e in cnx.find("AgentAuthority").entities()]),
                )
                self.assertEqual(
                    ["France", "Paris"],
                    sorted([e.label for e in cnx.find("LocationAuthority").entities()]),
                )

    def test_generate_ape_ead_utils(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", code="FRAD034", name="Service", category="test")
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                service=service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            cnx.commit()
            generate_ape_ead_other_sources_from_eids(cnx, [str(fa.eid)])
            fa = cnx.entity_from_eid(fa.eid)
            ape_filepath = cnx.execute(
                "Any FSPATH(D) WHERE X ape_ead_file F, F data D, X eid %(x)s", {"x": fa.eid}
            )[0][0].getvalue()
            self.assertTrue(self.fileExists(ape_filepath))
            content = fa.ape_ead_file[0].data.read()
            tree = etree.fromstring(content)
            eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
            self.assertEqual(
                eadid.attrib["url"], f"https://francearchives.gouv.fr/{fa.rest_path()}"
            )

    def test_oai_dc_reimport(self):
        """Test OAI DC re-import
        Trying: reimport the same file
        Expecting: no error is raised and no extra FindingAids created
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_meuse_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, path, self.service_infos)
            fi = cnx.execute("Any X WHERE X is FindingAid").one()
            # reimport the same file
            self.import_oai(cnx, path, self.service_infos)
            new_fi = cnx.execute("Any X WHERE X is FindingAid").one()
            self.assertNotEqual(fi.eid, new_fi.eid)
            self.assertEqual(new_fi.stable_id, new_fi.stable_id)
            fac_rset = cnx.execute("Any X WHERE X is FAComponent")
            self.assertEqual(len(fac_rset), 20)
            self.assertEqual(len(set(f.dc_title() for f in fac_rset.entities())), 18)

    def test_findingaid_support_hash_import_oai_dc(self):
        """
        Trying: OAI DC standard import
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, url, self.service_infos)
            fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
            self.assertTrue(fa_support.data_hash)
            self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
            self.assertTrue(fa_support.check_hash())

    def test_oai_dc_reimport_from_file(self):
        """Test OAI DC re-import from file.

        Trying: re-importing from file after deleting harvested FindingAid
        Expecting: same FindingAid is re-created
        """
        readerconfig = {
            "esonly": False,
            "index-name": "dummy",
            "appid": "data",
            "nodrop": False,
            "noes": True,
            "readercls": OAIDCHarvestedReader,
        }
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, url, self.service_infos)
            rql = "Any E,FSPATH(D) WHERE X findingaid_support F, F data D, X eadid E"
            rset = [(row[0], row[1].read()) for row in cnx.execute(rql)]
            filepaths = [row[1] for row in rset]
            self.assertEqual(len(filepaths), 1)
            eadids = [row[0] for row in rset]
            for filename in [row[1] for row in rset]:
                sqlutil.delete_from_filename(cnx, filename, interactive=False, esonly=False)
            cnx.commit()
            # remove OAIImportTask with CWFile
            cnx.execute("DELETE OAIImportTask X")
            cnx.commit()
            assert not cnx.find("FindingAid"), "at least one FindingAid in database"
            assert not cnx.find("File"), "at least one CWFile in database"
            self.assertFalse(cnx.execute(rql).rows)
            for filepath in filepaths:
                self.assertTrue(self.fileExists(filepath))
            import_filepaths(cnx, filepaths, readerconfig)
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            self.assertCountEqual(actual, eadids)

    def test_creation_date_dc_import(self):
        """Test FindingAid, FAComponent creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid and FAComponent have original creation_date
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_meuse_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, path, self.service_infos)
            fa_old = cnx.execute("Any X WHERE X is FindingAid").one()
            comp_stable_id = "1375ca056f49fec4548296908363d30ac653f2d1"
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
            fa_old = cnx.execute("Any X WHERE X is FindingAid").one()
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
            self.import_oai(cnx, path, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            self.assertNotEqual(fa_old.eid, fa.eid)
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                fa.creation_date.isoformat(),
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

    def test_multiple_setSpec(self):
        """Test the case where several FindingAid are created from the same harvesting
        Trying: import a oai_dc file with 3 different <setSpec>
        Expecting: 2 FindingAid for setSpecs FRAD055_REC and FRAD055_ES are created with one
                   FAComponents each. No FindingAid is created for setSpec FRAD055_EC as there
                   is no setName found for it
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_multiple_set.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, path, self.service_infos)
            self.assertEqual(len(cnx.execute("Any X WHERE X is FindingAid")), 2)
            self.assertEqual(len(cnx.execute("Any X WHERE X is FAComponent")), 2)
            # unittitle comes from the ListSet
            fi_ec = cnx.execute(
                'Any X WHERE X is FindingAid, X did D, D unittitle "FRAD055_SET_ES"'
            ).one()
            self.assertEqual(len(fi_ec.reverse_finding_aid), 1)
            # unittitle comes from the record setName
            fi_rec = cnx.execute(
                'Any X WHERE X is FindingAid,  X did D, D unittitle "FRAD055"'
            ).one()
            self.assertEqual(len(fi_rec.reverse_finding_aid), 1)

    def test_multiple_findingaid_support(self):
        """Test that each FindingAid created from the same harvesting has
        a separate findingaid_support file
        Trying: import a oai_dc file with 2 different <setSpec>
        Expecting: both FindingAid have different findingaid_support files
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_multiple_set.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, path, self.service_infos)
            rset = cnx.execute(
                "DISTINCT Any E, FSPATH(D) WHERE X findingaid_support F, F data D," " X eadid E"
            )
            self.assertEqual(rset.rowcount, 2)
            for eid, fpath in rset:
                fpath = fpath.getvalue()
                expected = "{}/FRAD055/oaipmh/dc/{}.xml".format(
                    self.config["ead-services-dir"], eid
                )
                if self.s3_bucket_name:
                    expected = expected.lstrip("/")
                self.assertEqual(expected.encode("utf-8"), fpath)
                self.assertTrue(self.fileExists(fpath))

    def test_ape_ead_path(self):
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, path, self.service_infos)
            generate_ape_ead_from_other_sources(cnx)
            fa = cnx.find("FindingAid").one()
            self.assertEqual(fa.related_service.code, "FRAD055")
            self.assertEqual(fa.eadid, "FRAD055_REC")
            ape_filepath = cnx.execute(
                "Any FSPATH(D) WHERE X ape_ead_file F, F data D, X eid %(x)s", {"x": fa.eid}
            )[0][0].getvalue()
            expected_filepath = self.get_filepath_by_storage(
                f"{self.config['appfiles-dir']}/ape-ead/FRAD055/ape-FRAD055_REC.xml"
            )
            self.assertEqual(ape_filepath.decode("utf-8"), expected_filepath)

    def test_es_dates_infos(self):
        """Test OAI harvest data

        Trying: harvest some records
        Expecting: dates infos are found in FAComponent but not in FindingAid es indexes
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, path, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            json = fa.cw_adapt_to("IFullTextIndexSerializable").serialize()
            # no dates for FindingAid
            self.assertFalse(fa.did[0].unitdate)
            self.assertFalse(fa.did[0].period)
            for attr in ("sortdate", "stopyear", "startyear"):
                self.assertNotIn(attr, json)
            comp = cnx.execute(
                "Any X WHERE X is FAComponent, "
                "X stable_id 'eab91cb651b570f6e573f87f895b51c73f91cf70'"
            ).one()
            comp_json = comp.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("1865-1981", comp.did[0].unitdate)
            self.assertEqual("1865-01-01", comp_json["sortdate"])
            self.assertEqual(1865, comp_json["startyear"])
            self.assertEqual(1981, comp_json["stopyear"])
            comp = cnx.execute(
                "Any X WHERE X is FAComponent, "
                "X stable_id '7b0927f926b9e90fa720336f332e420c8549b80b'"
            ).one()
            comp_json = comp.cw_adapt_to("IFullTextIndexSerializable").serialize()
            self.assertEqual("1817-01-01", comp.did[0].unitdate)
            self.assertEqual("1817-01-01", comp_json["sortdate"])
            self.assertEqual(1817, comp_json["startyear"])
            self.assertEqual(1817, comp_json.get("stopyear"))
            comp = cnx.execute(
                "Any X WHERE X is FAComponent, "
                "X stable_id 'a02bfbc73e5e6c97cda10abea6cb989f8bd9625e'"
            ).one()
            comp_json = comp.cw_adapt_to("IFullTextIndexSerializable").serialize()
            # this date is not recognized
            self.assertEqual("02/02/1865", comp.did[0].unitdate)
            for attr in ("sortdate", "stopyear", "startyear"):
                self.assertNotIn(attr, comp_json)

    def test_es_service_infos(self):
        """Test OAI harvest es data

        Trying: harvest some records
        Expecting: service infos are found in FAComponent and FindingAid es indexes
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            self.import_oai(cnx, path, self.service_infos)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            expected = {
                "eid": self.service_eid,
                "level": "level-D",
                "code": "FRAD055",
                "title": "Service",
            }
            self.assertEqual(expected, adapted.serialize()["service"])
            comp = cnx.execute("Any X LIMIT 1 WHERE X is FAComponent").one()
            adapted = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize()["service"])

    def test_iiif_manifest_ape_ead(self):
        """
        Trying: harvest a record with IIIF manifest in <dc:hasFormat>
        Expecting: new dao are added for IIIF manifest
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_meuse_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fc = find_component(cnx, "Tables décennales  (1792-1802)")
                manifest = "http://archives.meuse.fr/ark:/52669/a011500569432d712H2/manifest"
                self.assertEqual([manifest], [e.url for e in fc.digitized_versions])
                self.assertFalse(fc.digitized_urls)
                self.assertEqual(manifest, fc.iiif_manifest_url)
                expected_manifests = self.get_iiif_manifests(cnx)
                self.assertEqual(1, len(expected_manifests))
                generate_ape_ead_from_other_sources(cnx)
                self._test_ape_ead_iiif_daos(cnx, expected_manifests)

    def test_bounce_url_with_iiif_manifest(self):
        """
        Trying: harvest a record with IIIF manifest in <dc:hasFormat>
        Expecting: the bounce_url for the FAComponent is the value of <dc:identifier>
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_meuse_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fc = find_component(cnx, "Tables décennales  (1792-1802)")
                self.assertEqual(1, len(fc.digitized_versions))
                bounce_url = "http://archives.meuse.fr/ark:/52669/a011500569432d712H2"
                self.assertEqual(fc.bounce_url, bounce_url)
                manifest = "http://archives.meuse.fr/ark:/52669/a011500569432d712H2/manifest"
                self.assertEqual(manifest, fc.iiif_manifest_url)

    def test_bounce_url_without_iiif_manifest(self):
        """
        Trying: harvest a record without IIIF manifest in <dc:hasFormat>
        Expecting: the bounce_url for the FAComponent is not empty
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_meuse_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
                fc = cnx.execute(fc_rql, {"u": "Décès  (1893-1902)"}).one()
                self.assertFalse(len(fc.digitized_versions))
                self.assertEqual(fc.bounce_url, fc.did[0].extptr)

    def test_dao_grasse(self):
        """Test OAI_DC mapping for digitized versions
        Trying: Import a record whith <dc:relation>vignette :
        Expecting:
          - <dc:relation>url is added as illustration URL (not prefixed by vignette)
          - <dc:indentifier> is added as extptr
        """

        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_meuse_sample.xml"
            path = "file://{path}?verb=ListRecords&metadataPrefix=oai_dc".format(
                path=self.filepath()
            )
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fc_rql = "Any X WHERE X is FAComponent, X did D, D unittitle %(u)s"
                fc = cnx.execute(fc_rql, {"u": "Album photos de Stephane Guiraud"}).one()
                self.assertFalse(fc.illustration_url)
                bounce = "http://archives.ville-grasse.fr/notice/oai/34_01/7064/ILUMP9999"
                self.assertEqual(bounce, fc.bounce_url)
                self.assertEqual(bounce, fc.did[0].extptr)
                self.assertFalse(fc.iiif_manifest_url)
                got = sorted(
                    [
                        (dv.url or "", dv.role or "", dv.illustration_url or "")
                        for dv in fc.digitized_versions
                    ]
                )
                expected = [
                    ("http://archives.ville-grasse.fr/oai/3Fi003.JPG", "", ""),
                ]
                self.assertEqual(expected, got)
                self.assertEqual([v[0] for v in expected], sorted(fc.digitized_urls))

    def test_dieppe_bnf_vignette(self):
        """Test OAI_DC mapping for digitized versions

        Trying: Import a record whith <dc:relation>vignette :
        Expecting:
          - <dc:relation> url is added as thumbnail URL
          - <dc:indentifier> is added as fa_bounce_url URL
          - <dc:hasFormat> is added as IIIF manifest
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_dieppe_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fc = find_component(cnx, "Château (vue du)")
                self.assertEqual(2, len(fc.digitized_versions))
                expected = "https://patrimoine.dieppe.fr/i/?IIIF=/09/88/f2/1d/0988f21d-888a-4c93-9777-42fadef86980/iiif/bm76217_gm0004_000001.tif/full/!256,256/0/default.jpg"  # noqa
                thumbnail = [
                    dv.illustration_url for dv in fc.digitized_versions if dv.role == "thumbnail"
                ][0]
                self.assertEqual(expected, thumbnail)
                self.assertEqual(thumbnail, fc.illustration_url)
                bounce = "https://patrimoine.dieppe.fr/idurl/1/3"
                self.assertEqual(bounce, fc.bounce_url)
                self.assertFalse(fc.digitized_urls)
                iiif = "https://patrimoine.dieppe.fr/iiif/3/manifest"
                self.assertEqual(iiif, fc.iiif_manifest_url)
                got = sorted(
                    [
                        (dv.url or "", dv.role or "", dv.illustration_url or "")
                        for dv in fc.digitized_versions
                    ]
                )
                self.assertEqual(
                    got,
                    [
                        (
                            "",
                            "thumbnail",
                            "https://patrimoine.dieppe.fr/i/?IIIF=/09/88/f2/1d/0988f21d-888a-4c93-9777-42fadef86980/iiif/bm76217_gm0004_000001.tif/full/!256,256/0/default.jpg",  # noqa
                        ),
                        (
                            "https://patrimoine.dieppe.fr/iiif/3/manifest",
                            "iiif_manifest",
                            "",
                        ),
                    ],
                )

    def test_dieppe_bnf_vignette_ape_ead(self):
        """Test APE_EAD mapping for digitized versions

        Trying: Import a record whith <dc:relation>vignette :
        Expecting:
          - <dc:relation> url is added as
                <dao xlink:href="" xlink:type="simple" xlink:role="thumbnail"/>
          - <dc:indentifier> is added as
                <unitid extptr xlink:type="simple" xlink:href="" /></unitid>
          - <dc:hasFormat> is added as
                  <dao xlink:role="MANIFEST" xlink:href="XXX/manifest" xlink:title="manifest"/>
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_dieppe_sample_minimal.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                generate_ape_ead_from_other_sources(cnx)
                fc = cnx.find("FAComponent").one()
                self.assertEqual(2, len(fc.digitized_versions))
                fa = fc.finding_aid[0]
                ape_expected_filepath = self.datapath(
                    osp.join("ape_ead_data"), "ape_ead_dieppe_sample.xml"
                )
                content = fa.ape_ead_file[0].data.read()
                tree = etree.fromstring(content)
                with open(ape_expected_filepath, "r") as expected:
                    self.assertXMLEqual(etree.parse(expected).getroot(), tree)
                # check unitid / extptr
                expected = [
                    "https://patrimoine.dieppe.fr/idurl/1/3",
                ]
                extprts = tree.xpath("//e:extptr", namespaces={"e": tree.nsmap[None]})
                got = sorted(
                    [
                        extprt.attrib.get("{{{}}}href".format(tree.nsmap["xlink"]))
                        for extprt in extprts
                    ]
                )
                self.assertEqual(expected, got)
                got = sorted(
                    [
                        extptr
                        for extptr, in cnx.execute(
                            "Any E ORDERBY E WHERE X is FAComponent, X did D, D extptr E"
                        )
                    ]
                )
                self.assertEqual(expected, got)
                expected_manifests = self.get_iiif_manifests(cnx)
                self.assertEqual(1, len(expected_manifests))
                got_manifests = self.get_iiif_manifests_from_tree(tree)
                self.assertEqual(1, len(got_manifests))

    def test_dieppe_no_bnf_vignette(self):
        """Test OAI_DC mapping for digitized versions

        Trying: Import a record whith <dc:relation>vignette :
        Expecting:
          - <dc:relation>url is added as a viewer URL
          - <dc:indentifier> is added as fa_bounce_url URL
          - <dc:hasFormat> is added as IIIF manifest
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_dieppe_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                fc = find_component(cnx, "Eglise (vue de l')")
                thumbnails = [
                    dv.illustration_url for dv in fc.digitized_versions if dv.role == "thumbnail"
                ]
                self.assertFalse(thumbnails)
                self.assertFalse(fc.illustration_url)
                bounce = "https://patrimoine.dieppe.fr/idurl/1/5"
                self.assertEqual(bounce, fc.bounce_url)
                expected_viewer_url = "https://patrimoine.dieppe.fr/i/?IIIF=/19/d8/34/9e/19d8349e-dbf7-445d-a6fc-9421da917f81/iiif/bm76217_gm0006_000001.tif/full/!256,256/0/default.jpg"  # noqa

                digitized_urls = [expected_viewer_url]
                self.assertIn(fc.digitized_urls[0], digitized_urls)
                iiif = "https://patrimoine.dieppe.fr/iiif/5/manifest"
                self.assertEqual(iiif, fc.iiif_manifest_url)
                got = sorted(
                    [
                        (dv.url or "", dv.role or "", dv.illustration_url or "")
                        for dv in fc.digitized_versions
                    ]
                )
                self.assertEqual(
                    got,
                    [
                        (
                            expected_viewer_url,
                            "",
                            "",
                        ),
                        (
                            "https://patrimoine.dieppe.fr/iiif/5/manifest",
                            "iiif_manifest",
                            "",
                        ),
                    ],
                )

    def test_extptr(self):
        """Test OAI_DC mapping for extpt

        Trying: Import a record:
        Expecting: <dc:indentifier> is added as extptr
        """
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_dieppe_sample.xml"
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            with cnx.allow_all_hooks_but("es"):
                self.import_oai(cnx, path, self.service_infos)
                expected = {
                    "7b746246ec1010b4075e2d4d47ff8917e2c7cbc5": "https://patrimoine.dieppe.fr/idurl/1/3",  # noqa
                    "01e09235242e8b323ee07b4eacd9d3d0c129d64d": "https://patrimoine.dieppe.fr/idurl/1/4",  # noqa
                    "4153ff98cfca90851db6331b27b22c724a3a8f21": "https://patrimoine.dieppe.fr/idurl/1/5",  # noqa
                }
                for e in cnx.execute("Any X WHERE X is FAComponent").entities():
                    bounce_url = expected[e.stable_id]
                    self.assertEqual(bounce_url, e.did[0].extptr)

    @patch("cubicweb_francearchives.dataimport.oai.harvest_oai")
    def test_from_parameter_first_import(self, harvest_oai):
        """check _from parameter is not set on first harvesting pass"""
        with self.admin_access.cnx() as cnx:
            url = "http://oai.frad051.fr?verb=ListRecords&metadataPrefix=oai_dc"
            repo, _ = self.create_repo(cnx, url=url, delta=True)
            oai.harvest_delta(cnx, repo.eid)
            repo.cw_clear_all_caches()
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://oai.frad051.fr"

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
                url="http://oai.frad051.fr?verb=ListRecords&metadataPrefix=oai_dc",
                delta=True,
            )
            repo.cw_set(last_successful_import=datetime(2001, 2, 3))
            cnx.commit()
            oai.harvest_delta(cnx, repo.eid)
            repo.cw_clear_all_caches()
            service_infos = self.service_infos.copy()
            service_infos["oai_url"] = "http://oai.frad051.fr"

            harvest_oai.assert_called_with(
                cnx,
                "http://oai.frad051.fr?verb=ListRecords&metadataPrefix=oai_dc&from=2001-02-03",
                repo.reverse_oai_repository[0].eid,
                records_limit=None,
                dry_run=False,
                log=logging.getLogger("rq.task"),
                service_infos=service_infos,
            )

    def test_findingaid_esdoc(self):
        """Testing FindingAid IFullTextIndexSerializable

        Trying: import a FindingAid
        Expecting: FindingAid ESDocument content is correct
                   and equal to es_json from generated from DB
        """
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fa = cnx.find("FindingAid").one()
            authorities = {
                e[0]: e[1] for e in cnx.execute("Any L, X WHERE X is AgentAuthority, X label L")
            }
            expected = {
                "alltext": "FRAD055",
                "creation_date": fa.creation_date.isoformat(),
                "cw_etype": "FindingAid",
                "did": {"unitid": None, "unittitle": "FRAD055"},
                "digitized": False,
                "digitized_all": DZFacetValues.nondz,
                "eadid": "FRAD055_REC",
                "eid": fa.eid,
                "escategory": "archives",
                "fa_stable_id": "c8d28639042d97da67a5362e2560a5a5d7ea9fc5",
                "index_entries": [
                    {
                        "authfilenumber": None,
                        "authority": authorities["Archives départementales de la Meuse"],
                        "authtype": "AgentAuthority",
                        "label": "Archives départementales de la Meuse",
                        "type": "name",
                    }
                ],
                "originators": ["Archives départementales de la Meuse"],
                "scopecontent": None,
                "service": {
                    "code": "FRAD055",
                    "eid": self.service.eid,
                    "level": "level-D",
                    "title": "Service",
                },
                "stable_id": "c8d28639042d97da67a5362e2560a5a5d7ea9fc5",
            }
            adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize())
            es_from_db = adapted.serialize_from_db()
            es_from_db.update(
                {
                    "scopecontent": None,
                }
            )  # None values are removed by adapter
            self.assertEqual(expected, es_from_db)

    def test_facomponent_esdoc(self):
        """Testing FAComponent IFullTextIndexSerializable

        Trying: import a FindingAid
        Expecting: FAComponent ESDocument content is correct
                   and equal to es_json from generated from DB
        """
        url_str = "file://{}?verb=ListRecords&metadataPrefix=oai_dc"
        with self.admin_access.cnx() as cnx:
            self.filename = "oai_dc_sample.xml"
            url = url_str.format(self.filepath())
            self.import_oai(cnx, url, self.service_infos)
            fc = cnx.execute(
                "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s",
                {"unitid": "62J1-205"},
            ).one()
            authorities = {}
            for etype in ("AgentAuthority", "LocationAuthority", "SubjectAuthority"):
                authorities.update(
                    {e[0]: e[1] for e in cnx.execute(f"Any L, X WHERE X is {etype}, X label L")}
                )
            expected = {
                "creation_date": fc.creation_date.isoformat(),
                "cw_etype": "FAComponent",
                "did": {
                    "unitid": "62J1-205",
                    "unittitle": "62J1 Ordre et syndicat des architectes",
                },
                "digitized": False,
                "digitized_all": DZFacetValues.nondz,
                "eadid": None,
                "eid": fc.eid,
                "escategory": "archives",
                "fa_stable_id": "c8d28639042d97da67a5362e2560a5a5d7ea9fc5",
                "index_entries": [
                    {
                        "authfilenumber": None,
                        "authority": authorities["Jean Marais"],
                        "authtype": "AgentAuthority",
                        "label": "Jean Marais",
                        "type": "persname",
                    },
                    {
                        "authfilenumber": None,
                        "authority": authorities["Paris"],
                        "authtype": "LocationAuthority",
                        "label": "Paris",
                        "type": "geogname",
                    },
                    {
                        "authfilenumber": None,
                        "authority": authorities["France"],
                        "authtype": "SubjectAuthority",
                        "label": "France",
                        "type": "subject",
                    },
                    {
                        "authfilenumber": None,
                        "authority": authorities["Archives départementales de la Meuse"],
                        "authtype": "AgentAuthority",
                        "label": "Archives départementales de la Meuse",
                        "type": "name",
                    },
                ],
                "originators": ["Archives départementales de la Meuse"],
                "scopecontent": "description",
                "service": {
                    "code": "FRAD055",
                    "eid": self.service.eid,
                    "level": "level-D",
                    "title": "Service",
                },
                "stable_id": "a02bfbc73e5e6c97cda10abea6cb989f8bd9625e",
            }
            # no dates, stopyear, startyear, sortdate in es
            self.assertEqual("02/02/1865", fc.did[0].unitdate)
            self.assertIsNone(fc.did[0].startyear)
            self.assertIsNone(fc.did[0].stopyear)
            adapted = fc.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(expected, adapted.serialize())
            es_from_db = adapted.serialize_from_db()
            index_expected = expected.pop("index_entries")
            index_db = es_from_db.pop("index_entries")
            self.assertCountEqual(index_expected, index_db)

            es_from_db.update(
                {
                    "eadid": None,
                }
            )  # None values are removed by adapter
            self.assertEqual(expected, es_from_db)


if __name__ == "__main__":
    unittest.main()
