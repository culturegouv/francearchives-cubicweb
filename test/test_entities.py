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

import datetime
import os.path as osp

import unittest

from cubicweb import Binary
from cubicweb.devtools import BASE_URL
from cubicweb_web.devtools.testlib import WebCWTC, WebPostgresApptestConfiguration

from cubicweb_francearchives import SECTIONS
from cubicweb_francearchives.dataimport.pdf import pdf_infos
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id
from cubicweb_francearchives.testutils import S3BfssStorageTestMixin

from pgfixtures import setup_module, teardown_module  # noqa


class EntitiesTC(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def test_map(self):
        with self.admin_access.cnx() as cnx:
            title = "Etat civil et registres " "paroissiaux numérisés et mis en ligne"
            with open(self.datapath("maps", "Carte_Etat-civil.csv"), "rb") as f:
                data = Binary(f.read())
                cw_map = cnx.create_entity(
                    "Map", title=title, map_file=data, top_content="<h1>Top</h1>"
                )
                cnx.commit()
            data = cw_map.data()
            expected = {
                "url": "http://www.archives-numerisees.ain.fr/archives/recherche/etatcivil/n:88",
                "color": "#044694",
                "code": "01",
                "legend": (
                    "Archives ayant mis en ligne l'\xe9tat civil, "
                    "int\xe9gralement ou partiellement "
                ),
            }

            self.assertCountEqual(data[0], expected)

    def test_html_integrity(self):
        with self.admin_access.cnx() as cnx:
            content = """<div style="background: red"
            javascript="onclick('alert')">style</div>"""
            article = cnx.execute(
                "INSERT BaseContent X : X title %(t)s, " "X content %(c)s ",
                {"t": "title", "c": content},
            ).one()
            cnx.commit()
            self.assertEqual(article.content, """<div style="background: red">style</div>""")
            content = """<div style="color: red"
            javascript="onclick('alert')">style</div>"""
            cnx.execute("SET X content %(c)s WHERE X eid %(e)s", {"e": article.eid, "c": content})
            cnx.commit()
            article = cnx.find("BaseContent", eid=article.eid).one()
            self.assertEqual(article.content, """<div style="color: red">style</div>""")

    def test_html_iframe_kept(self):
        """ensure <iframe> tags are kept"""
        with self.admin_access.cnx() as cnx:
            content = (
                "<h1>Hello</h1>"
                '<iframe width="560" height="315" '
                'src="https://www.youtube.com/embed/T3nEhn4g1iU"'
                ' frameborder="0" allowfullscreen></iframe>'
            )
            article = cnx.execute(
                "INSERT BaseContent X : X title %(t)s, " "X content %(c)s ",
                {"t": "title", "c": content},
            ).one()
            cnx.commit()
            self.assertEqual(article.content, content)

    def test_anom_bounce_url(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fcdid = cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
                extptr="ark:/61561/bo755dxx3y5z",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRANOM_xxx",
                eadid="FRANOM_xxx",
                publisher="FRAMP<",
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            facomp = cnx.create_entity(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent="fc-scoppecontent",
                description="fc-descr",
            )
            self.assertEqual(
                facomp.bounce_url,
                "http://anom.archivesnationales.culture.gouv.fr/ark:/61561/bo755dxx3y5z",
            )

    def test_bounce_url_unitid(self):
        with self.admin_access.cnx() as cnx:
            search_form_url = (
                "http://archives.lille.fr/search?preset=6&query=&quot;"
                "%(unitid)s&quot&search-query=&view=classification&search-query=1"
            )
            serviceid = cnx.create_entity(
                "Service",
                category="s1",
                short_name="Commune de Lille",
                code="FRAM059350",
                search_form_url=search_form_url,
            ).eid
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRANOM_xxx",
                eadid="FRANOM_xxx",
                publisher="FRAMP<",
                did=fadid,
                service=serviceid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            self.assertEqual(fa.bounce_url, search_form_url.format(unitid=fadid.unitid))

    def test_bounce_url_eadid(self):
        with self.admin_access.cnx() as cnx:
            search_form_url = (
                "https://www.archives71.fr/arkotheque/inventaires/" "ead_ir_consult.php?ref={eadid}"
            )
            serviceid = cnx.create_entity(
                "Service",
                category="s1",
                short_name="CHALON-SUR-SAÔNE",
                code="FRAD071",
                search_form_url=search_form_url,
            ).eid
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD071_2098W",
                eadid="FRAD071 1F 1-168_2F 1-568",
                publisher="FRAD071<",
                did=fadid,
                service=serviceid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            self.assertEqual(
                fa.bounce_url, search_form_url.format(eadid=fa.eadid.replace(" ", "+"))
            )

    def test_section(self):
        """
        Add Section with Image in File
        """
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            image = cnx.create_entity(
                "Image",
                caption="image-caption",
                description="alt",
                image_file=ce(
                    "File",
                    data=Binary(b"some-image-data"),
                    data_name="image-name.png",
                    data_format="image/png",
                ),
            )
            section = ce("Section", title="sect-1", name="sect-1", section_image=image)
            cnx.commit()
            self.assertEqual(section.image.eid, image.eid)
            image_url = image.image_file[0].cw_adapt_to("IDownloadable").download_url()
            self.assertEqual(section.illustration_url, image_url)
            self.assertEqual(section.illustration_alt, "alt")

    def test_mixed_string_attrs(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            section = ce(
                "Section",
                title="""<p>sect</p>"<scriPt>alert('toto')</script>""",
                name="""sect-1<scriPt>alert('toto')</scriPT>""",
                content='<a href="www.toto.fr" title="toto">toto</a><script>alert("toto")</script>',
            )
            cnx.commit()
            self.assertEqual(section.title, """<p>sect</p>"alert('toto')""")
            self.assertEqual(section.name, """sect-1alert('toto')""")
            self.assertEqual(section.richstring_attrs, ["content"])
            self.assertEqual(
                section.content,
                '<a href="www.toto.fr" rel="nofollow noopener '
                'noreferrer external" target="_blank">toto</a>',
            )
            self.assertEqual(
                section.printable_value("content"),
                '<a href="www.toto.fr" rel="nofollow noopener '
                'noreferrer external" target="_blank" title="toto - new window">toto</a>',
            )


class FileTests(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def _create_similar_files(self, cnx):
        """create two cwFiles with the same filepath"""
        for i in range(2):
            for data, name in ((Binary(b"some-file-data"), "file.pdf"),):
                cnx.create_entity("File", data=data, data_name=name, data_format="application/pdf")
        cnx.commit()

    def test_delete_one_similar_file(self):
        """
        Trying: create two cwFiles with the same filepath and then
                delete one of the file
        Expecting: file is still present on the FS
        """
        with self.admin_access.cnx() as cnx:
            self._create_similar_files(cnx)
            fpaths = [
                f[0].getvalue() for f in cnx.execute("Any fspath(D) WHERE X data D, X is File")
            ]
            self.assertEqual(1, len(set(fpaths)))
            fobj = cnx.execute("Any X LIMIT 1 WHERE X is File").one()
            fobj.cw_delete()
            cnx.commit()
            cnx.find("File").one()
            fpath = cnx.execute("Any fspath(D) WHERE X data D, X is File")[0][0].getvalue()
            self.assertTrue(self.fileExists(fpath))

    def test_delete_all_similar_files(self):
        """
        Trying: create tow cwFiles with the same filepath and then
                delete them both
        Expecting: file no longer exists on FS
        """
        with self.admin_access.cnx() as cnx:
            self._create_similar_files(cnx)
            fpaths = [
                f[0].getvalue() for f in cnx.execute("Any fspath(D) WHERE X data D, X is File")
            ]
            self.assertEqual(1, len(set(fpaths)))
            cnx.execute("DELETE File X WHERE X is File")
            cnx.commit()
            self.assertFalse(cnx.find("File"))
            self.assertFalse(osp.exists(fpaths[0]))

    def test_delete_file_with_apostrophe(self):
        """
        Trying: create a cwFile with apostrophe in filepath
        Expecting: file no longer exists on FS
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "File",
                data=Binary(b"data"),
                data_name="FRSHD_INV_GR28P1_COMMISSARIAT_NATIONAL_A_L'INTERIEUR.xml",
                data_format="application/pdf",
            )
            cnx.commit()
            fpaths = [
                f[0].getvalue() for f in cnx.execute("Any fspath(D) WHERE X data D, X is File")
            ]
            self.assertEqual(1, len(set(fpaths)))
            cnx.execute("DELETE File X WHERE X is File")
            cnx.commit()
            self.assertFalse(cnx.find("File"))
            self.assertFalse(osp.exists(fpaths[0]))

    def test_s3_file_upload_content_type(self):
        """
        Trying: create a PDF file
        Expecting: the file is uploaded with the right mimetype
        """
        if self.s3_bucket_name:
            mime_type = "application/pdf"
            with self.admin_access.client_cnx() as cnx:
                pdf = cnx.create_entity(
                    "File",
                    data_name="pdf",
                    data_format="application/pdf",
                    data=Binary(b"pdf content"),
                )
                cnx.commit()
                s3storage = self.repo.system_source.storage("File", "data")
                s3_key = s3storage.get_s3_key(pdf, "data")
                head = s3storage.s3cnx.head_object(Bucket=s3storage.bucket, Key=s3_key)
                self.assertEqual(head["ContentType"], mime_type)

    def test_update_file_content(self):
        """
        Trying: create a Circular with attachment and update the attachment content
        Expecting: attachment file references a new file and the old no more exists
        """
        with self.admin_access.cnx() as cnx:
            signing_date = datetime.date(2001, 6, 6)
            pdffile = self.get_or_create_imported_filepath("pdf.pdf")
            pdf_content = self.getFileContent(pdffile)
            circular = cnx.create_entity(
                "Circular",
                circ_id="circ01",
                title="Circular",
                signing_date=signing_date,
                status="in-effect",
            )
            attachment = cnx.create_entity(
                "File",
                data_name="pdf",
                data_format="application/pdf",
                data=Binary(pdf_content),
                reverse_attachment=circular,
            )
            cnx.commit()
            fpath = cnx.execute(f"""Any FSPATH(D) WHERE X eid {attachment.eid}, F data D""")[0][
                0
            ].getvalue()
            self.assertTrue(self.fileExists(fpath))
            pdf_text = "Test\nCirculaire chat\n\n\x0c"
            self.assertEqual(pdf_text, pdf_infos(fpath).get("text"))
            # update pdf
            with open(osp.join(self.datadir, "pdf1.pdf"), "rb") as f:
                pdf_content = f.read()
                attachment.cw_set(data=Binary(pdf_content))
            cnx.commit()
            new_pdf_text = "Circulaire sérieux\n\n\x0c"
            new_fpath = cnx.execute(f"""Any FSPATH(D) WHERE X eid {attachment.eid}, F data D""")[0][
                0
            ].getvalue()
            self.assertFalse(self.fileExists(fpath))
            self.assertTrue(self.fileExists(new_fpath))
            self.assertNotEqual(new_fpath, fpath)
            self.assertEqual(new_pdf_text, pdf_infos(new_fpath).get("text"))


class NominaRecordTests(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        super(NominaRecordTests, self).setup_database()
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service",
                name="Département des Landes",
                code="FRAD040",
                category="DS",
                short_name="Landes",
            )
            cnx.commit()

    def test_nomina_mpf1418_dates(self):
        """Test MPF1418 NominaRecord dates

        Trying: add a MPF1418 NominaRecord

        Expecting: act_year is d date
        """

        with self.admin_access.cnx() as cnx:
            stable_id = compute_nomina_stable_id(self.service.code, "1")
            nomina_record = cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id,
                json_data={
                    "e": {
                        "N": {
                            "d": [{"d": "1894-06-24", "y": "1894"}],
                            "l": [{"c": "France", "d": "Yvelines (ex Seine et Oise)", "dc": "78"}],
                        },
                        "D": {
                            "d": [{"d": "1914-06-24", "y": "1914"}],
                            "l": [{"c": "France", "d": "Yvelines (ex Seine et Oise)", "dc": "78"}],
                        },
                    },
                    "p": [{"f": "Georges René", "n": "BIEUVILLE"}],
                    "t": "MPF14-18",
                    "u": "https://www.memoiredeshommes.sga.defense.gouv.fr/fr/ark:/40699/m005239d4b17b33e",  # noqa
                },
                service=self.service,
            )
            self.assertEqual(nomina_record.act_year, "1914")

    def test_nomina_dates(self):
        """Test NominaRecord other then MPF1418 dates

        Trying: add a NominaRecord

        Expecting: act_year is the date of doctype_code
        """

        with self.admin_access.cnx() as cnx:
            stable_id = compute_nomina_stable_id(self.service.code, "10")
            nomina_record = cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id,
                json_data={
                    "c": {"c": "R P 392", "e": "0", "n": "22", "o": ["laboureur"]},
                    "e": {
                        "N": [
                            {
                                "d": {"y": "1867"},
                            }
                        ],
                        "R": [
                            {
                                "l": {
                                    "c": "France",
                                    "cc": "FR",
                                    "d": "Landes",
                                    "dc": "40",
                                    "p": "Cère",
                                }
                            }
                        ],
                        "RM": [
                            {
                                "d": {"y": "1887"},
                            }
                        ],
                    },
                    "p": [{"f": "Barthélémy", "n": "Duprat"}],
                    "t": "RM",
                    "u": "http://www.archives.landes.fr/ark:/35227/s0052cbf404e1290/52cc0a4a27570",
                },
                service=self.service,
            )
            self.assertEqual(nomina_record.act_year, "1887")


class BreadcrumbTests(WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            self.service = cnx.create_entity(
                "Service", category="s1", short_name="AD de la Marne", code="FRAD051"
            )
            cnx.commit()

    def test_nomina_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            stable_id = compute_nomina_stable_id(self.service.code, "42")
            nomina_record = cnx.create_entity(
                "NominaRecord",
                stable_id=stable_id,
                json_data={"p": [{"f": "Jean", "n": "Durand"}], "t": "AA"},
                service=self.service,
            )
            ibc = nomina_record.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [
                    (BASE_URL, "Home"),
                    (f"{BASE_URL}basedenoms", "Search in the name base"),
                    (f"{BASE_URL}basedenoms/service/FRAD051", "AD de la Marne"),
                    (None, "Durand, Jean"),
                ],
            )

    def test_inventory_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                service=self.service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            ibc = fa.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [
                    (BASE_URL, "Home"),
                    (f"{BASE_URL}inventaires/FRAD051", "AD de la Marne"),
                    (None, "Inventory - maindid"),
                ],
            )

    def test_inventory_breadcrumbs_noservice(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            ibc = fa.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [(BASE_URL, "Home"), (None, "Inventory - maindid")],
            )

    def test_facomponent_breadcrumbs(self):
        with self.admin_access.cnx() as cnx:
            fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
            fcdid = cnx.create_entity(
                "Did",
                unitid="fcdid",
                unittitle="fcdid-title",
                startyear=1234,
                stopyear=1245,
                origination="fc-origination",
                repository="fc-repo",
                extptr="ark:/61561/bo755dxx3y5z",
            )
            fa = cnx.create_entity(
                "FindingAid",
                name="the-fa",
                stable_id="FRAD051_xxx",
                eadid="FRAD051_xxx",
                publisher="FRAD051",
                service=self.service,
                did=fadid,
                fa_header=cnx.create_entity("FAHeader"),
            )
            facomp = cnx.create_entity(
                "FAComponent",
                finding_aid=fa,
                stable_id="fc-stable-id",
                did=fcdid,
                scopecontent="fc-scoppecontent",
                description="fc-descr",
            )
            ibc = facomp.cw_adapt_to("IBreadCrumbs")
            self.assertEqual(
                ibc.breadcrumbs(),
                [
                    (BASE_URL, "Home"),
                    (f"{BASE_URL}inventaires/FRAD051", "AD de la Marne"),
                    (f"{BASE_URL}findingaid/FRAD051_xxx", "Inventory - maindid"),
                    "fcdid-title",
                ],
            )


class AdapterTests(WebCWTC):
    def test_service_vcard(self):
        """
        Trying: adapt a Service to Service2VcardAdapater
        Expecting: the adaption is correct
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service",
                category="Département de la Savoie",
                name="Communauté d'agglomération du Grand Chambéry",
                name2="Service des archives",
                short_name="AD de la Marne",
                phone_number="04.79.68.30.75",
                contact_name="Lise Paulus-Levet",
                address="106 allée des Blachères",
                city="73000 Chambéry",
                opening_period="Sur rendez-vous",
                email="archives@grandchambery.fr",
            )
            cnx.commit()
            card = service.cw_adapt_to("vcard").vcard()
            got = card.serialize()
            for data in (
                f"UID:{service.eid}",
                f"N:{service.dc_title()}",
                "ADR:;;106 allée des Blachères;73000 Chambéry;;;FR",
                "AGENT:Lise Paulus-Levet\r\nEMAIL:archives@grandchambery.fr",
                (
                    "FN:Communauté d'agglomération du Grand Chambéry - "
                    "Service des archives\r\nN:;Communauté d'agglomération "
                    "du Grand Chambéry - Service des archives"
                ),
                "NOTE:Sur rendez-vous\r\nTEL:04.79.68.30.75\r\n",
            ):
                self.assertIn(data, got)

    def test_card_no_esindex(self):
        """Test serializing Card which should not be indexed in ElasticSearch (do_index is False).

        Trying: adapting Card to IFullTextIndexSerializable and calling serialize() method
        Expecting: empty dict
        """
        with self.admin_access.cnx() as cnx:
            card = cnx.create_entity("Card", title="foo", wikiid="bar", do_index=False)
            cnx.commit()
            card = cnx.find("Card", eid=card.eid).one()
            adapter = card.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(adapter.serialize(), {})


class BaseContentAideTC(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Section", name="gerer", title="Gérer")
            cnx.create_entity("Section", name="comprendre", title="Comprendre")
            cnx.commit()
            rset = cnx.execute("Any X WHERE X is Section, X name 'gerer'")
            SECTIONS["gerer"] = rset[0][0]

    def test_basecontent_pro(self):
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity(
                "BaseContent",
                title="title",
                reverse_children=cnx.find("Section", name="gerer").one(),
            )
            cnx.commit()
            basecontent.cw_clear_all_caches()
            self.assertEqual("05_faq_basecontent_pro", basecontent.cw_adapt_to("IFaq").faq_category)

    def test_basecontent_public(self):
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity(
                "BaseContent",
                title="title",
                reverse_children=cnx.find("Section", name="comprendre").one(),
            )
            cnx.commit()
            basecontent.cw_clear_all_caches()
            self.assertEqual(
                "01_faq_basecontent_public", basecontent.cw_adapt_to("IFaq").faq_category
            )


if __name__ == "__main__":
    unittest.main()
