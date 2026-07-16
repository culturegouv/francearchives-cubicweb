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
from cubicweb_web.devtools.testlib import PyramidWebCWTC
from lxml import etree

import unittest
import os.path as osp

from cubicweb import Binary

from cubicweb_francearchives.testutils import (
    PostgresTextMixin,
    XMLCompMixin,
    S3BfssStorageTestMixin,
)
from cubicweb_francearchives.dataimport import dc

from pgfixtures import setup_module, teardown_module  # noqa


BASE_SETTINGS = {
    "cubicweb.bwcompat": "no",
    "cubicweb.session.secret": "stuff",
    "cubicweb.auth.authtkt.session.secret": "stuff",
    "cubicweb.auth.authtkt.persistent.secret": "stuff",
    "francearchives.autoinclude": "no",
}


class FindingAidExportApeEADTC(
    S3BfssStorageTestMixin, PostgresTextMixin, PyramidWebCWTC, XMLCompMixin
):
    maxDiff = None
    settings = BASE_SETTINGS

    readerconfig = {
        "noes": True,
        "esonly": False,
        "appid": "data",
        "nodrop": False,
        "dc_no_cache": True,
        "index-name": "dummy",
    }

    def includeme(self, config):
        config.include("cubicweb_francearchives.pviews")

    def oai_request(self, req, **formparams):
        params = "&".join("{}={}".format(k, v) for k, v in list(formparams.items()))
        return self.webapp.get(
            "/oai?{}".format(params),
            status=200,
            headers={
                "Accept": (
                    "text/html,application/xhtml+xml," "application/xml;q=0.9,image/webp,*/*;q=0.8"
                )
            },
        )

    def assert_ead_tag(self, result, verb="GetRecord"):
        tree = etree.fromstring(result)
        got_ead = self.get_ead(tree, verb)
        expected_attribs = {
            "{http://www.w3.org/2001/XMLSchema-instance}schemaLocation": (
                "urn:isbn:1-931666-22-9 http://www.loc.gov/ead/ead.xsd"
            ),  # noqa
            "audience": "external",
        }
        expected_nsmap = {
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xlink": "http://www.w3.org/1999/xlink",
            # 'cpf': 'urn:isbn:1-931666-33-4', # not mandatory
            None: "urn:isbn:1-931666-22-9",
        }
        self.assertCountEqual(expected_attribs, got_ead.attrib)
        if "cpf" in got_ead.nsmap:
            got_ead.nsmap.pop("cpf")
        self.assertDictContainsSubset(expected_nsmap, got_ead.nsmap)

    def assert_metadata_equal(self, filepath, result, verb="GetRecord"):
        tree = etree.fromstring(result)
        got_metadata = self.get_metadata(tree, verb)
        tree = etree.parse(self.datapath(osp.join("ape_ead_data"), filepath))
        expected_metadata = self.get_metadata(tree.getroot(), verb)
        # with open(f"/tmp/{filepath}", "w") as fp:
        #     fp.write(
        #         etree.tostring(got_metadata, pretty_print=True, encoding="utf8").decode("utf8")
        #     )
        self.assertXMLEqual(expected_metadata, got_metadata)

    def get_metadata(self, root, verb="GetRecord"):
        ns = {"e": root.nsmap[None]}
        record = root.xpath("//e:{verb}/e:record/e:metadata".format(verb=verb), namespaces=ns)[0]
        return record

    def get_ead(self, root, verb="GetRecord"):
        ns = {"e": root.nsmap[None], "x": "urn:isbn:1-931666-22-9"}
        ead = root.xpath("//e:{verb}/e:record/e:metadata/x:ead".format(verb=verb), namespaces=ns)[0]
        return ead

    def test_ead_export_1(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            )
            cnx.commit()
            with cnx.allow_all_hooks_but("es"):
                fpath = "FRAD092_9FI_cartes-postales.csv"
                fpath = self.get_or_create_imported_filepath(f"csv/{fpath}")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
        with self.admin_access.web_request() as req:
            fa = req.execute("Any X WHERE X is FindingAid, X stable_id S").one()
            fa_stable_id = fa.stable_id
            self.assertIn('<div class="ead-p">5 cartons</div>', fa.did[0].physdesc)
            self.assertEqual(len(fa.reverse_finding_aid), 10)
            result = self.oai_request(
                req, metadataPrefix="ape_ead", verb="GetRecord", identifier=str(fa_stable_id)
            )
            self.assert_ead_tag(result.body)
            self.assert_metadata_equal("FRAD092_9FI_cartes-postales_export_ead.xml", result.body)

    def test_fa_from_xml_ead_export(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            fadid = ce(
                "Did",
                unitid="maindid",
                extptr="http://www.fa-url",
                unitdate="1701-02-13",
                unittitle="maindid-title",
            )
            fa_header = ce(
                "FAHeader",
                titlestmt="<div>titlestmt</div>",
                titleproper="titlepr",
                author="<div>fa_author</div>",
            )
            filepath = "ape-FRAN_IR_050236.xml"
            with open(self.datapath(osp.join("ape_ead_data"), filepath), "rb") as f:
                fa_content = f.read()
            fa = ce(
                "FindingAid",
                name="the-fa",
                stable_id="FR-AN_FRAN_IR_050236",
                eadid="FR-AN_FRAN_IR_050236",
                publisher="AN",
                did=fadid,
                findingaid_support=ce(
                    "File",
                    data_format="application/xml",
                    data_name=filepath,
                    data=Binary(fa_content),
                ),
                ape_ead_file=ce(
                    "File",
                    data_format="application/xml",
                    data_name=filepath,
                    data=Binary(fa_content),
                ),
                fa_header=fa_header,
            )
            cnx.commit()
        with self.admin_access.web_request() as req:
            fa = req.find("FindingAid", eid=fa.eid).one()
            result = self.oai_request(
                req, metadataPrefix="ape_ead", verb="GetRecord", identifier=str(fa.stable_id)
            )
            self.assert_ead_tag(result.body)
            self.assert_metadata_equal("ape-FRAN_IR_050236_ape_ead.xml", result.body)


if __name__ == "__main__":
    unittest.main()
