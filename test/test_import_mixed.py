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
from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.testutils import (
    OaiImportMixin,
    EADImportMixin,
    PostgresTextMixin,
)

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.dataimport import (
    sqlutil,
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport.oai_dc import OAIDCHarvestedReader
from cubicweb_francearchives.dataimport.oai_ead import OAIEADHarvestedReader
from cubicweb_francearchives.dataimport.ead import Reader
from cubicweb_francearchives.dataimport.importer import import_filepaths
from pgfixtures import setup_module, teardown_module  # noqa


class MixedImportTC(OaiImportMixin, PostgresTextMixin, WebCWTC):
    readerconfig = merge_dicts(
        {},
        EADImportMixin.readerconfig,
        {"reimport": True, "nodrop": False, "noes": True, "force_delete": True},
    )

    @classmethod
    def init_config(cls, config):
        super(MixedImportTC, cls).init_config(config)
        config.set_option(
            "consultation-base-url",
            "https://francearchives.gouv.fr",
        )
        config.set_option("ead-services-dir", "/tmp")
        config.set_option("instance-type", "consultation")

    def init_reader(self, settings, store, *args):
        reader = settings.get("readercls", Reader)
        return reader(settings, store, *args)

    def path(self, service_infos=None):
        service_infos = service_infos or self.service_infos
        try:
            prefix = self.data_directory.split("_")[1]
        except IndexError:
            prefix = ""
        return "{ead_services_dir}/{code}/oaipmh/{prefix}".format(
            ead_services_dir=self.config["ead-services-dir"],
            prefix=prefix,
            code=service_infos["code"],
        )

    def filepath(self, filename=None):
        filename = filename or self.filename
        assert filename is not None
        return self.datapath("{}/{}".format(self.data_directory, filename))

    def setup_database(self):
        super(MixedImportTC, self).setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Service", name="Indre-et-Loire", code="FRAD037", category="foo")
            cnx.create_entity("Service", name="Marne", code="FRAD051", category="foo")
            cnx.create_entity("Service", name="Meuse", code="FRAD055", category="foo")
            cnx.create_entity("Service", name="FRAN", code="FRAN", category="foo")
            cnx.commit()
            self.services_map = load_services_map(cnx)

    def test_reimport_oaiead_over_ead(self):
        """import an IR by oai over en existing ead-imported IR.
        Only one IR must be created.
        """
        with self.admin_access.cnx() as cnx:
            # import ead
            self.readerconfig["readercls"] = Reader
            self.import_filepath(cnx, "FRAD037_1Q_2Q.xml")
            fa_ead = cnx.find("FindingAid").one()
            fa_ead_attrs = {"stable_id": fa_ead.stable_id, "name": fa_ead.name}
            # import oai
            self.assertEqual(fa_ead.dc_title(), "Domaines nationaux")
            self.filename = "FRAD037_1Q_2Q.xml"
            self.data_directory = "oai_ead"
            self.readerconfig["readercls"] = OAIEADHarvestedReader
            service_infos = service_infos_from_service_code("FRAD037", self.services_map)
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, url, service_infos)
            fa_oai = cnx.find("FindingAid").one()
            self.assertEqual(fa_oai.dc_title(), "Domaines nationaux oai")
            self.assertEqual(fa_oai.stable_id, fa_ead_attrs["stable_id"])
            self.assertEqual(fa_oai.name, fa_ead_attrs["name"])

    def test_reimport_ead_over_oaiead(self):
        """import an IR by ead over en existing oai-imported IR.
        Only one IR must be created.
        """
        with self.admin_access.cnx() as cnx:
            # import ead
            self.filename = "FRAD037_1Q_2Q.xml"
            self.data_directory = "oai_ead"
            self.readerconfig["readercls"] = OAIEADHarvestedReader
            service_infos = service_infos_from_service_code("FRAD037", self.services_map)
            path = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            self.import_oai(cnx, path, service_infos)
            fa_oai = cnx.find("FindingAid").one()
            fa_oai_attrs = {"stable_id": fa_oai.stable_id, "name": fa_oai.name}
            self.assertEqual(fa_oai.dc_title(), "Domaines nationaux oai")
            # import ead
            self.readerconfig["readercls"] = Reader
            self.import_filepath(cnx, "FRAD037_1Q_2Q.xml")
            fa_ead = cnx.find("FindingAid").one()
            self.assertEqual(fa_ead.dc_title(), "Domaines nationaux")
            self.assertEqual(fa_ead.stable_id, fa_oai_attrs["stable_id"])
            self.assertEqual(fa_ead.name, fa_oai_attrs["name"])

    def test_mixed_reimport_from_file(self):
        """Test OAI DC and EAD import from file.

        Trying: import OAI_EAD and OAI_DC harvested files and a regular EAD XML file
        Expecting: three FindingAid are created
        """
        readerconfig = {
            "esonly": False,
            "index-name": "dummy",
            "appid": "data",
            "appfiles-dir": self.datapath(),
            "nodrop": False,
            "noes": True,
        }
        with self.admin_access.cnx() as cnx:
            # import oai_dc harvested file
            self.filename = "oai_dc_sample.xml"
            self.data_directory = "oai_dc"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=oai_dc"
            service_infos = service_infos_from_service_code("FRAD055", self.services_map)
            self.readerconfig = readerconfig.copy()
            self.readerconfig["readercls"] = OAIDCHarvestedReader
            self.import_oai(cnx, url, service_infos)
            # import oai_ead harvested file
            self.filename = "oai_ead_sample.xml"
            self.data_directory = "oai_ead"
            url = f"file://{self.filepath()}?verb=ListRecords&metadataPrefix=ead"
            service_infos = service_infos_from_service_code("FRAD051", self.services_map)
            self.readerconfig["readercls"] = OAIEADHarvestedReader
            self.import_oai(cnx, url, service_infos)
            rql = "Any FSPATH(D) WHERE X findingaid_support F, F data D"
            filenames = [result[0].read() for result in cnx.execute(rql)]
            for filename in filenames:
                sqlutil.delete_from_filename(cnx, filename, interactive=False, esonly=False)
            cnx.commit()
            self.assertFalse(cnx.find("FindingAid"))
            # add a regular EAD XML filepath
            filenames.append(self.get_or_create_imported_filepath("FRAN_IR_000224.xml"))
            self.assertEqual(4, len(filenames))
            for filepath in filenames:
                self.assertTrue(self.fileExists(filepath))
                self.assertTrue(self.fileExists(filepath))
            import_filepaths(cnx, filenames, readerconfig)
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            self.assertEqual(4, cnx.find("FindingAid").rowcount)
            actual = [row[0] for row in cnx.execute("Any E WHERE X is FindingAid, X eadid E")]
            expected = ["FRAN_IR_000224", "FRAD055_REC", "FRAD051_000000028_203M ", "FRAD051_204M"]
            self.assertCountEqual(actual, expected)
