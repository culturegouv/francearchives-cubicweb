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

from functools import wraps

from cubicweb_web.devtools.testlib import PyramidWebCWTC
from lxml import etree
import unittest

from cubicweb import Binary


from cubicweb_francearchives.dataimport import usha1
from cubicweb_francearchives.testutils import (
    PostgresTextMixin,
    XMLCompMixin,
    S3BfssStorageTestMixin,
)

from pgfixtures import setup_module, teardown_module  # noqa


class OAITestMixin(object):
    def oai_component(self, cnx):
        """Return the "oai" component"""
        return self.vreg["components"].select("oai", cnx)


def no_validate_xml(method):
    """Disable XML schema validation, often because the underlying metadata
    part of the response (RDF, XSD) is not validable (or we don't know how to
    do it).
    """

    @wraps(method)
    def wrapper(self):
        self._validate_xml = False
        self._debug_xml = True
        return method(self)

    return wrapper


class OAIPMHViewsTC(PostgresTextMixin, PyramidWebCWTC, OAITestMixin):
    _validate_xml = True
    _debug_xml = True
    settings = {
        # to get clean traceback in tests (instead of in an html error page)
        "cubicweb.bwcompat": False,
        # avoid noise in test output (UserWarning: !! WARNING WARNING !! you
        # should stop this instance)
        "cubicweb.session.secret": "x",
        "cubicweb.auth.authtkt.session.secret": "x",
        "cubicweb.auth.authtkt.persistent.secret": "x",
    }

    def assertXmlValid(self, xml_data, xsd_filename, debug=False):
        """Validate an XML file (.xml) according to an XML schema (.xsd)."""
        with open(xsd_filename) as xsd:
            xmlschema = etree.XMLSchema(etree.parse(xsd))
        # Pretty-print xml_data to get meaningfull line information.
        xml_data = etree.tostring(etree.fromstring(xml_data), pretty_print=True)
        root = etree.fromstring(xml_data)
        if debug and not xmlschema.validate(root):
            print(xml_data)
        xmlschema.assertValid(root)

    def oai_request(self, req, **formparams):
        response = self.webapp.get("/oai", formparams)
        self.assertEqual(response.headers["Content-Type"], "text/xml; charset=UTF-8")
        if self._validate_xml:
            self.assertXmlValid(response.body, self.datapath("OAI-PMH.xsd"), debug=self._debug_xml)
        return response.body

    def create_index(self, cnx, authority):
        ce = cnx.create_entity
        args = {}
        if authority.cw_etype == "AgentAuthority":
            etype = "AgentName"
            args["type"] = authority.label.split("_")[1]
        elif authority.cw_etype == "SubjectAuthority":
            etype = "Subject"
        else:
            etype = "Geogname"
        return ce(etype, authority=authority, label=authority.label, **args)

    def create_pnia_agent(self, cnx, label):
        ce = cnx.create_entity
        return ce("AgentAuthority", label=label)

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            # create indexes
            self.fa_loc = ce("LocationAuthority", label="location")
            fa_loc_index = self.create_index(cnx, authority=self.fa_loc)
            self.fa_subj = ce("SubjectAuthority", label="subject")
            fa_subj_index = self.create_index(cnx, authority=self.fa_subj)
            # findingaid contributors
            self.fa_corpname = self.create_pnia_agent(cnx, "fa_corpname")
            fa_corpname_index = self.create_index(cnx, authority=self.fa_corpname)
            self.fa_famname = self.create_pnia_agent(cnx, "fa_famname")
            fa_famname_index = self.create_index(cnx, authority=self.fa_famname)
            self.fa_persname = self.create_pnia_agent(cnx, "fa_persname")
            fa_persname_index = self.create_index(cnx, authority=self.fa_persname)
            # facomponent contributors
            self.facomp_corpname = self.create_pnia_agent(cnx, "facomp_corpname")
            facomp_corpname_index = self.create_index(cnx, authority=self.facomp_corpname)
            self.facomp_famname = self.create_pnia_agent(cnx, "facomp_famname")
            facomp_famname_index = self.create_index(cnx, authority=self.facomp_famname)
            self.facomp_persname = self.create_pnia_agent(cnx, "facomp_persname")
            facomp_persname_index = self.create_index(cnx, authority=self.facomp_persname)

            #
            service = ce("Service", code="FRAD084", name="fc_service", category="test")
            fadid = ce(
                "Did",
                unitid="maindid",
                extptr="http://www.fa-url",
                unitdate="1701-02-13",
                startyear=1234,
                stopyear=1245,
                origination="fa-origination",
                unittitle="maindid-title",
            )
            fcdid = ce(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                unitdate="1701-03-13",
                extptr="http://www.fc-url",
                origination="fc-origination",
                repository="fc-repo",
            )
            fa_header = ce(
                "FAHeader",
                titlestmt="<div>titlestmt</div>",
                titleproper="titleproper",
                author="<div>fa_author</div>",
            )
            fa = ce(
                "FindingAid",
                name="FRAD084_xxx",
                stable_id=usha1("FRAD084_xxx"),
                eadid="FRAD084_xxx",
                publisher="FRAD084",
                did=fadid,
                fa_header=fa_header,
                service=service,
                scopecontent="<div>fa-scoppecontent</div>",
                reverse_index=[
                    fa_loc_index,
                    fa_subj_index,
                    fa_corpname_index,
                    fa_famname_index,
                    fa_persname_index,
                ],
                acquisition_info="acquisition_info",
            )
            facomp = ce(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent="<div>fc-scoppecontent</div>",
                description="<div>fc-descr</div>",
                digitized_versions=ce(
                    "DigitizedVersion", url="http://doa.fr", illustration_url="http://doa_image.fr"
                ),
                reverse_index=[facomp_corpname_index, facomp_famname_index, facomp_persname_index],
            )
            savanol = ce("SubjectAuthority", label="Jérôme Savonarole")
            ce("Subject", label="Jérôme Savonarole", authority=savanol, index=facomp)
            cnx.commit()
            self.fa_eid = fa.eid
            self.facomp_eid = facomp.eid


class OAIEADViewsTC(S3BfssStorageTestMixin, XMLCompMixin, OAIPMHViewsTC):
    def setup_database(self):
        super(OAIEADViewsTC, self).setup_database()
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
                titleproper="titleproper",
                author="<div>fa_author</div>",
            )
            filepath = self.datapath("ir_data/v1/FRAD095_00374.xml")
            with open(filepath, "rb") as f:
                fa_content = f.read()
            fa = ce(
                "FindingAid",
                name="AD05_1563",
                stable_id=usha1("AD05_1563"),
                eadid="AD05_1563",
                publisher="AD05",
                did=fadid,
                findingaid_support=ce(
                    "File",
                    data_format="application/xml",
                    data_name="FRAD095_00374.xml",
                    data=Binary(fa_content),
                ),
                ape_ead_file=ce(
                    "File",
                    data_format="application/xml",
                    data_name="FRAD095_00374.xml",
                    data=Binary(fa_content),
                ),
                fa_header=fa_header,
            )
            cnx.commit()
            self.fa_xml_eid = fa.eid

    @no_validate_xml
    def test_identify(self):
        with self.admin_access.web_request() as req:
            result = self.oai_request(req, verb="Identify")
            self.assertIn(b"<repositoryName>FranceArchives</repositoryName>", result)

    @no_validate_xml
    def test_listmetadaformats_by_identifier(self):
        with self.admin_access.web_request() as req:
            fa = req.find("FindingAid", eid=self.fa_xml_eid).one()
            result = self.oai_request(req, verb="ListMetadataFormats", identifier=fa.stable_id)
            self.assertIn(b"<metadataPrefix>ape_ead</metadataPrefix>", result)

    @no_validate_xml
    def test_fa_listrecords(self):
        with self.admin_access.web_request() as req:
            result = self.oai_request(
                req, verb="ListRecords", set="findingaid", metadataPrefix="ape_ead"
            )
            for data in (
                b'<unitdate type="date_affinee">1791 (8 juillet)-1792 (11 mai) </unitdate>',
                b'<unitid countrycode="fr">c11</unitid>',
            ):
                self.assertIn(data, result)

    @no_validate_xml
    def test_fa_ead_oai_ead(self):
        with self.admin_access.web_request() as req:
            fa = req.find("FindingAid", eid=self.fa_eid).one()
            result = etree.ElementTree(etree.XML(fa.cw_adapt_to("OAI_EAD").dump())).getroot()
            with open(
                self.datapath(osp.join("ape_ead_data"), "fa_ead_adapted.xml"), "r"
            ) as expected:
                self.assertXMLEqual(etree.parse(expected).getroot(), result)

    @no_validate_xml
    def test_fa_from_xml_export_oai_ead(self):
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
                titleproper="titleproper",
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
                    data_name=f"{filepath}",
                    data=Binary(fa_content),
                ),
                fa_header=fa_header,
            )
            cnx.commit()
        with self.admin_access.web_request() as req:
            fa = req.find("FindingAid", eid=fa.eid).one()
            result = fa.cw_adapt_to("OAI_EAD").dump()
            filepath = self.datapath(osp.join("ape_ead_data"), "ape-FRAN_IR_050236_oai_ead.xml")
            with open(filepath, "rb") as expected:
                expected = etree.parse(expected).getroot()
                result = etree.fromstring(result)
                self.assertXMLEqual(expected, result)


if __name__ == "__main__":
    unittest.main()
