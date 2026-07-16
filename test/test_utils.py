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


# flake8: noqa

import datetime
import hashlib
from jinja2 import Environment, PackageLoader

import unittest

from cubicweb.devtools import BASE_URL
from cubicweb_web.devtools.testlib import WebCWTC
from mock import Mock
import string

from cubicweb.uilib import remove_html_tags

from cubicweb_francearchives import GLOSSARY_CACHE
from cubicweb_francearchives.dataimport import (
    normalize_for_filepath,
    PUNCTUATION,
    pdf,
    normalize_entry,
    clean,
)
from cubicweb_francearchives.entities import enhance_rgaa
from cubicweb_francearchives.htmlutils import soup2xhtml

from cubicweb_francearchives.testutils import S3BfssStorageTestMixin
from cubicweb_francearchives.views.forms import EMAIL_REGEX
from cubicweb_francearchives.views.search import PniaElasticSearchView
from cubicweb_francearchives.utils import (
    is_absolute_url,
    reveal_glossary,
    find_card,
    id_for_anchor,
    merge_dicts,
    format_date,
)
from cubicweb_francearchives.xmlutils import (
    enhance_accessibility,
    process_html_for_csv,
    handle_subtitles,
    handle_tables,
    clean_xss,
    process_html,
    fix_fa_external_links as fa_fix_links,
    fix_ead_divs,
)

env = Environment(loader=PackageLoader("cubicweb_francearchives.views"))


class UtilsTest(S3BfssStorageTestMixin, WebCWTC):
    def test_fa_fix_links_1(self):
        html = '<div class="ead-p"> <a href="www.archives.valdoise.fr">Archives <b>départementales</b> du Val</a></div>'
        expected = '<div class="ead-p"> <a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer external" target="_blank" title="Archives départementales du Val - new window">Archives <b>départementales</b> du Val</a></div>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fa_fix_links(html, cnx), expected)

    def test_fa_fix_links_2(self):
        html = """<div class="ead-p"><a href="www.archives.valdoise.fr" title="site">Archives départementales du Val-d'Oise</a></div>"""
        expected = """<div class="ead-p"><a href="www.archives.valdoise.fr" title="Archives départementales du Val-d'Oise - site - new window" rel="nofollow noopener noreferrer external" target="_blank">Archives départementales du Val-d'Oise</a></div>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fa_fix_links(html, cnx), expected)

    def test_fa_fix_links_3(self):
        html = '<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p">Inventaire, CADN, 1991.<br>\n<a href="medias/Intruments%20de%20recherche%20bureautiques/CADN/POI/Otase_B_1955-1971_26POI.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de recherche</a>&#160;</div></div></div>'
        expected = (
            '<div class="ead-section ead-otherfindaid"><div class="ead-wrapper">'
            '<div class="ead-p">Inventaire, CADN, 1991.<br>\n</div></div></div>'
        )
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fa_fix_links(html, cnx), expected)

    def test_fa_fix_ead_divs_1(self):
        html = """<div class="fr-mb-10v"><h2 class="fr-h4 fr-mb-4v">Publication:</h2><div class="ead-section ead-publisher"><div class="ead-wrapper">Archives nationales</div></div>
<div class="ead-section ead-date"><div class="ead-wrapper">18 juin 2013</div></div>
<div class="ead-section ead-address"><div class="ead-wrapper"><div>
<div>Paris</div></div></div></div></div>"""
        expected = """<div class="fr-mb-10v"><h2 class="fr-h4 fr-mb-4v">Publication:</h2><div class="ead-section ead-publisher"><p class="ead-wrapper">Archives nationales</p></div>
<div class="ead-section ead-date"><p class="ead-wrapper">18 juin 2013</p></div>
<div class="ead-section ead-address"><div class="ead-wrapper"><div>
<p>Paris</p></div></div></div></div>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fix_ead_divs(html, cnx), expected)

    def test_fa_fix_ead_divs_2(self):
        html = """<div class="ead-wrapper"><div class="ead-p"><div>Etude VI</div>
<div>Boucot, Claude</div></div></div>"""
        expected = """<div class="ead-wrapper"><div class="ead-p"><p>Etude VI</p>
<p>Boucot, Claude</p></div></div>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fix_ead_divs(html, cnx), expected)

    def test_fa_fix_ead_divs_3(self):
        html = """<div class="ead-wrapper"><div class="ead-p"><span class="ead-bold">Minutes et répertoires :</span>la loi 2008-696 du 15 juillet 2008 relative</div><div class="ead-p"><span class="ead-bold">Autres documents</span>s'agissant</div><div class="ead-p">Certains documents ne sont pas accessibles en raison de leur mauvais état de conservation.</div></div>"""
        expected = """<div class="ead-wrapper"><p class="ead-p"><span class="ead-bold">Minutes et répertoires :</span>la loi 2008-696 du 15 juillet 2008 relative</p><p class="ead-p"><span class="ead-bold">Autres documents</span>s'agissant</p><p class="ead-p">Certains documents ne sont pas accessibles en raison de leur mauvais état de conservation.</p></div>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fix_ead_divs(html, cnx), expected)

    def test_fa_fix_ead_divs_4(self):
        html = """<div class="ead-wrapper"><div class="ead-p"><p class="ead-i">Aulus-les-Bains : portrait de cinq femmes (les soeurs Mauran et leurs amies)</p></div></div>"""
        expected = """<div class="ead-wrapper"><div class="ead-p"><p class="ead-i">Aulus-les-Bains : portrait de cinq femmes (les soeurs Mauran et leurs amies)</p></div></div>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fix_ead_divs(html, cnx), expected)

    def test_fa_fix_ead_divs_5(self):
        html = """<div class="ead-section ead-physdesc"><div class="ead-wrapper"><div class="ead-p"><b class="ead-autolabel">Description physique:</b> Document iconographique<br></div></div>
</div>"""
        expected = """<div class="ead-section ead-physdesc"><div class="ead-wrapper"><p class="ead-p"><b class="ead-autolabel">Description physique:</b> Document iconographique<br aria-hidden="true"></p></div>
</div>"""

        with self.admin_access.cnx() as cnx:
            self.assertEqual(fix_ead_divs(html, cnx), expected)

    def test_fa_fix_ead_divs_6(self):
        html = """<div class="ead-wrapper"><span class="ead-title">Notes ISBD</span><div class="ead-p">Corr;, adr., timbre (1911).</div></div>"""
        expected = """<div class="ead-wrapper"><p class="ead-title">Notes ISBD</p><p class="ead-p">Corr;, adr., timbre (1911).</p></div>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fix_ead_divs(html, cnx), expected)

    def test_fa_fix_ead_divs_7(self):
        html = (
            """<div class="ead-wrapper"><li>Converted_apeEAD_version_2015-06-SNAPSHOT</li></div>"""
        )
        expected = """<ul class="fr-list"><li>Converted_apeEAD_version_2015-06-SNAPSHOT</li></ul>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(fix_ead_divs(html, cnx), expected)

    def test_insert_biblio_labels(self):
        html = """<div class="ead-section ead-bibliography"><div class="ead-label">bibliography_label</div><div class="ead-wrapper"><div>
<div class="ead-p">text-bibliography</div>
</div></div></div>
<div class="ead-section ead-bioghist"><div class="ead-wrapper">
<div class="ead-p">text-bioghist</div>
</div></div>"""

        expected = """<div class="ead-section ead-bibliography"><div class="ead-label">bibliography_label</div><div class="ead-wrapper"><div>
<p class="ead-p">text-bibliography</p>
</div></div></div>
<div class="ead-section ead-bioghist"><p class="ead-label">bioghist_label</p><div class="ead-wrapper">
<p class="ead-p">text-bioghist</p>
</div></div>"""
        labels = ["bibliography", "bibref", "bioghist"]
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.assertEqual(got, expected)

    def test_skip_empty_biblio_labels(self):
        html = """<div class="ead-section ead-bibliography"><p class="ead-wrapper"></p></div><div class="ead-section ead-arrangement"><div class="ead-wrapper"><p class="ead-p">Classement chronologique</p></div></div>"""
        labels = ["bibliography", "bibref", "bioghist"]
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.assertEqual(got, html)

    def test_insert_description_labels(self):
        html = """<div class="ead-section ead-accruals"><div class="ead-wrapper"><div class="ead-p">Fonds ouvert susceptible d'accroissement</div></div></div>
<div class="ead-section ead-appraisal"><div class="ead-wrapper"><div class="ead-p">Aucun</div></div></div>
<div class="ead-section ead-arrangement"><div class="ead-wrapper"><div class="ead-p">Classement chronologique</div></div></div>"""

        expected = """<div class="ead-section ead-accruals"><p class="ead-label">accruals_label</p><div class="ead-wrapper"><p class="ead-p">Fonds ouvert susceptible d'accroissement</p></div></div>
<div class="ead-section ead-appraisal"><p class="ead-label">appraisal_label</p><div class="ead-wrapper"><p class="ead-p">Aucun</p></div></div>
<div class="ead-section ead-arrangement"><p class="ead-label">arrangement_label</p><div class="ead-wrapper"><p class="ead-p">Classement chronologique</p></div></div>"""

        labels = ["accruals", "appraisal", "arrangement"]
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.assertEqual(got, expected)

    def test_additional_resources(self):
        html = '<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>\n<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>\n<div class="ead-section ead-relatedmaterial"><div class="ead-wrapper"><div class="ead-p"><a href="../file/06419493742584d8873722d6b1b3732cfc7d8532/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>\n<div class="ead-section ead-separatedmaterial"><div class="ead-wrapper"><div class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf" rel="nofollow noopener noreferrer" target="_blank">Voir l\'instrument de\n    recherche</a>&#160;</div></div></div>'
        expected = """<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><p class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l'instrument de
    recherche</a> </p></div></div>
<div class="ead-section ead-otherfindaid"><div class="ead-wrapper"><p class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l'instrument de
    recherche</a> </p></div></div>
<div class="ead-section ead-relatedmaterial"><div class="ead-wrapper"><p class="ead-p"><a href="../file/06419493742584d8873722d6b1b3732cfc7d8532/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l'instrument de
    recherche</a> </p></div></div>
<div class="ead-section ead-separatedmaterial"><div class="ead-wrapper"><p class="ead-p"><a href="../file/dd5464631894040fed175ea8db7bd843d3fc2f48/FRMAEE_MN_179CPCOM_Maroc.pdf">Voir l'instrument de
    recherche</a> </p></div></div>"""  # noqa
        labels = ["custodhist"]
        with self.admin_access.cnx() as cnx:
            got = process_html(cnx, html, labels=labels)
            self.maxDiff = None
            self.assertEqual(got, expected)

    def test_process_links_for_csv_ok(self):
        html = """<div class="related-productors"><a href="http://localhost:9998/fr/authorityrecord/FRAN_NP_003944" title="">France. Ministère des Universités (1974-1981)</a><div class="related-productors__dates"><span class="eac-sub-label">dates :</span> 5/07/1974-31/12/1975</div></div>"""
        expected = """(http://localhost:9998/fr/authorityrecord/FRAN_NP_003944) France. Ministère des Universités (1974-1981) dates :  5/07/1974-31/12/1975"""
        with self.admin_access.cnx() as cnx:
            got = process_html_for_csv(html, cnx)
            self.assertEqual(got, expected)

    def test_process_links_for_csv_ko(self):
        html = """<a href="http://localhost:9998/fr/authorityrecord/FRAN_NP_003944" title="">France. Ministère des Universités (1974-1981)</a><div class="related-productors__dates"><span class="eac-sub-label">dates :</span> 5/07/1974-31/12/1975</div></div>"""
        expected = """France. Ministère des Universités (1974-1981)dates : 5/07/1974-31/12/1975"""
        with self.admin_access.cnx() as cnx:
            got = process_html_for_csv(html, cnx)
            self.assertEqual(got, expected)

    def test_table_dsfr(self):
        """check that tables HTML is DSFR compliant"""
        with open(self.datapath("html/table_no_dsfr.html"), "r") as f:
            html = f.read()
        with open(self.datapath("html/table_dsfr.html"), "r") as f:
            expected = f.read()
        with self.admin_access.cnx() as cnx:
            self.maxDiff = None
            generated = handle_tables(html, cnx)
            self.assertEqual(generated, expected)

    def test_merge_dicts(self):
        def old_merge_dicts(dict1, *dicts):
            for dct in dicts:
                dict1.update(dct)
            return dict1

        test_cases = [[{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}], [{}, {"a": 1}, {"b": 2}, {"c": 3}]]
        for args in test_cases:
            self.assertEqual(old_merge_dicts(*args), merge_dicts(*args))

    def test_find_card_nocard(self):
        with self.admin_access.cnx() as cnx:
            self.assertIsNone(find_card(cnx, "no-such-wikiid"))

    def test_find_card_nolang(self):
        with self.admin_access.cnx() as cnx:
            c1 = cnx.create_entity("Card", title="c1", wikiid="c1", content="foo")
            self.assertEqual(find_card(cnx, "c1").eid, c1.eid)
            cnx.set_language("fr")
            self.assertEqual(find_card(cnx, "c1").eid, c1.eid)

    def test_find_card_fr(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Card", title="c1", wikiid="c1", content="foo")
            c1fr = cnx.create_entity("Card", title="c1", wikiid="c1-fr", content="foo")
            cnx.set_language("fr")
            self.assertEqual(find_card(cnx, "c1").eid, c1fr.eid)

    def test_find_card_en_match(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Card", title="c1", wikiid="c1", content="foo")
            c1en = cnx.create_entity("Card", title="c1", wikiid="c1-en", content="foo")
            cnx.create_entity("Card", title="c1", wikiid="c1-fr", content="foo")
            cnx.set_language("en")
            self.assertEqual(find_card(cnx, "c1").eid, c1en.eid)

    def test_find_card_en_fallback(self):
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Card", title="c1", wikiid="c1", content="foo")
            c1fr = cnx.create_entity("Card", title="c1", wikiid="c1-fr", content="foo")
            cnx.set_language("en")
            self.assertEqual(find_card(cnx, "c1").eid, c1fr.eid)

    def test_find_card_en_fallback_when_nocontent(self):
        with self.admin_access.cnx() as cnx:
            c1fr = cnx.create_entity("Card", title="c1", wikiid="c1-fr", content="foo")
            # create an english card but with no content. Behaviour should
            # be the same as if there was no card
            cnx.create_entity("Card", title="c1", wikiid="c1-en")
            cnx.set_language("en")
            self.assertEqual(find_card(cnx, "c1").eid, c1fr.eid)

    def test_email_checker(self):
        email = "test@toto.fr"
        self.assertTrue(EMAIL_REGEX.match(email))
        email = "testtoto.fr"
        self.assertFalse(EMAIL_REGEX.match(email))
        email = "test@totofr"
        self.assertFalse(EMAIL_REGEX.match(email))
        email = "@test@toto.fr"
        self.assertFalse(EMAIL_REGEX.match(email))

    def test_normalize_entry_iso(self):
        # labels whose normalization is the same in Python and PostgreSQL"""
        norm = normalize_entry
        self.assertEqual(norm("Charles de Gaulle"), "charles de gaulle")
        self.assertEqual(norm("Charles   de Gaulle"), "charles de gaulle")
        self.assertEqual(norm("Charles, Gaulle (de)"), "charles gaulle de")
        self.assertEqual(norm("Gaulle de, Charles"), "gaulle de charles")
        self.assertEqual(norm("Charles (de)   Gaulle"), "charles de gaulle")
        self.assertEqual(norm("Charles de Gaulle (1890-1970)"), "charles de gaulle 1890 1970")
        self.assertEqual(norm("Charles de Gaulle (1890 - 1970)"), "charles de gaulle 1890 1970")
        self.assertEqual(norm("Charles de Gaulle (1890 - 1970)"), "charles de gaulle 1890 1970")
        self.assertEqual(norm("Liszt, Franz (1811-1886)"), "liszt franz 1811 1886")
        self.assertEqual(norm("Liszt (Franz)"), "liszt franz")
        self.assertEqual(norm("debré, jean-louis (1944-....)"), "debre jean louis 1944")
        self.assertEqual(norm("DEBRE, Jean-Louis"), "debre jean louis")
        self.assertEqual(norm("Debré, Jean-Louis"), "debre jean louis")
        self.assertEqual(norm("Tavel... (de)"), "tavel de")
        self.assertEqual(norm("Bonaparte, Élisa (1777-1820)"), "bonaparte elisa 1777 1820")
        self.assertEqual(
            norm("Bureau international du Travail (BIT) (1919-…)"),
            "bureau international du travail bit 1919 .",
        )
        self.assertEqual(
            norm("Bureau international du Travail (BIT) (1919-...)"),
            "bureau international du travail bit 1919",
        )
        self.assertEqual(
            norm("Bureau International du Travail (BIT) (1919-)"),
            "bureau international du travail bit 1919",
        )

        # labels whose normalization is not the same in Python and PostgreSQL
        norm = normalize_entry
        self.assertEqual(norm("Deboraüde ?"), "deboraude")
        self.assertEqual(norm("Tavel… (de)"), "tavel. de")
        self.assertEqual(
            norm("Blein (Ange François Alexandre) , général"),
            "blein ange francois alexandre general",
        )
        self.assertEqual(
            norm("Gauthier de rougemont, chef d’escadron"), "gauthier de rougemont chef d'escadron"
        )
        self.assertEqual(
            norm("Route nationale (n° 120) -- Cantal (France)"),
            "route nationale n_ 120 cantal france",
        )
        self.assertEqual(
            norm(
                (
                    """Comité d'attribution des fonds recueillis à l'occasion """
                    """de la journée nationale des orphelins de guerre (France)"""
                )
            ),
            (
                """comite_ d attribution des fonds recueillis a_ l occasion """
                """de la journe_e nationale des orphelins de guerre france"""
            ),
        )

    def test_pagination(self):
        # params: number_of_items (items_per_page, max_pages, max_pagination_links)
        results_per_page = 10

        # No need to paginate
        req = Mock()
        req.form = {"page": 1}
        pesv = PniaElasticSearchView(req=req)
        pagination = pesv.pagination(results_per_page)
        self.assertFalse(pagination)

        #  Page 1 out of 2 > >> (only 1 item on the second page)
        req = Mock()
        req.form = {"page": 1}
        pesv = PniaElasticSearchView(req=req)
        pagination = pesv.pagination(results_per_page + 1)
        self.assertEqual(
            [1, 2], sorted([d["name"] for d in pagination if d["class"] == "fr-pagination__link"])
        )
        self.assertEqual(
            sorted(
                [
                    "fr-pagination__link",
                    "fr-pagination__link",
                    "fr-pagination__link fr-pagination__link--next",
                ]
            ),
            sorted([d["class"] for d in pagination]),
        )
        # << < Page 2 out of 5 > >>
        req = Mock()
        req.form = {"page": 2}
        pesv = PniaElasticSearchView(req=req)
        pagination = pesv.pagination(results_per_page * 5)
        self.assertEqual(
            [1, 2, 3, 5],
            sorted([d["name"] for d in pagination if d["class"] == "fr-pagination__link"]),
        )
        self.assertEqual(
            sorted(
                [
                    "fr-pagination__item fr-ellipsis",
                    "fr-pagination__link",
                    "fr-pagination__link",
                    "fr-pagination__link",
                    "fr-pagination__link",
                    "fr-pagination__link fr-pagination__link--next",
                    "fr-pagination__link fr-pagination__link--prev",
                ]
            ),
            sorted([d["class"] for d in pagination]),
        )
        # << < Page [7] out of 7
        req = Mock()
        req.form = {"page": 7}
        pesv = PniaElasticSearchView(req=req)
        pagination = pesv.pagination(results_per_page * 7)
        self.assertEqual(
            [1, 6, 7],
            sorted([d["name"] for d in pagination if d["class"] == "fr-pagination__link"]),
        )
        self.assertEqual(
            sorted(
                [
                    "fr-pagination__item fr-ellipsis",
                    "fr-pagination__link",
                    "fr-pagination__link",
                    "fr-pagination__link",
                    "fr-pagination__link fr-pagination__link--prev",
                ]
            ),
            sorted([d["class"] for d in pagination]),
        )

    def test_clean_up_punctuation(self):
        """Test filename clean-up.

        Trying: filename contains punctuation
        Expecting: punctuation replaced with "_"
        """
        filename = "foo" + PUNCTUATION + "bar"
        cleaned_up = "foo" + len(PUNCTUATION) * "_" + "bar"
        self.assertEqual(cleaned_up, normalize_for_filepath(filename))

    def test_clean_up_whitespace(self):
        """Test filename clean-up.

        Trying: filename contains whitespaces
        Expecting: whitespaces replaced with "_"
        """
        filename = "foo" + string.whitespace + "bar"
        cleaned_up = "foo" + len(string.whitespace) * "_" + "bar"
        self.assertEqual(cleaned_up, normalize_for_filepath(filename))

    def test_clean_up_common_french(self):
        """Test filename clean-up.

        Trying: filename contains any of "ÀàÇçÉéÈè"
        Expecting: replaced with "AaEe"
        """
        filename = "ÀàÇçÉéÈè"
        cleaned_up = "AaCcEeEe"
        self.assertEqual(cleaned_up, normalize_for_filepath(filename))

    def test_clean_up_not_ascii(self):
        """Test filename clean-up.

        Trying: filename contains any of not ascii caracters
        Expecting: "°" is replaced with "_"
        """
        filename = "FRAC N° insee_1E_Etat_civil"
        cleaned_up = "FRAC_N__insee_1E_Etat_civil"
        self.assertEqual(cleaned_up, normalize_for_filepath(filename))

    def test_absolute_url(self):
        """Test absolute URL check.

        Trying: https://foo.com/bar
        Expecting: is True
        """
        self.assertTrue(is_absolute_url("https://foo.com/bar"))

    def test_relative_url(self):
        """Test absolute URL check.

        Trying: /foo/bar
        Expecting: is False
        """
        self.assertFalse(is_absolute_url("/foo/bar"))

    def test_www(self):
        """Test absolute URL check.

        Trying: www.foo.com/bar
        Expecting: is True
        """
        self.assertTrue(is_absolute_url("www.foo.com/bar"))

    def test_clean(self):
        """Test cleaning labels.

        Trying: cleaning labels
        Expecting: cleaned labels
        """
        labels = ("foo\t\tbar\n\nbaz", "foo  bar foobar", "foo\u0090bar")
        expected = ["foo bar baz", "foo bar foobar", "foobar"]
        actual = list(clean(*labels))
        self.assertCountEqual(actual, expected)

    def test_format_dates_short(self):
        with self.admin_access.repo_cnx() as cnx:
            date = datetime.date(2021, 3, 11)
            for lang, expected in (
                ("fr", "11/03/2021"),
                ("en", "2021/03/11"),
                ("es", "11/03/2021"),
                ("de", "11.03.2021"),
            ):
                cnx.set_language(lang)
                formatted = format_date(date, fmt="short", req=cnx)
                self.assertEqual(expected, formatted)

    def test_format_dates_from_str(self):
        with self.admin_access.repo_cnx() as cnx:
            for date, expected in (("2025-08-20T14:52:03.600247+00:00", "20/08/2025 14:52"),):
                date = datetime.datetime.fromisoformat(date)
                formatted = format_date(date, req=cnx, fmt="dd/MM/yyyy HH:mm")


class XMlUtilsTest(S3BfssStorageTestMixin, WebCWTC):

    def test_link_remove_empty_title(self):
        html = """<div><a href="www.archives.valdoise.fr" title="">Archives départementales du Val-d'Oise</a></div>"""  # noqa
        target = 'rel="nofollow noopener noreferrer external" target="_blank"'
        with self.admin_access.cnx() as cnx:
            expected = f"""<div><a href="www.archives.valdoise.fr" {target}>Archives départementales du Val-d'Oise</a></div>"""  # noqa
            self.assertEqual(enhance_accessibility(html, cnx), expected)
            title = '''title="Archives départementales du Val-d'Oise - new window"'''
            expected = f"""<div><a href="www.archives.valdoise.fr" {title}>Archives départementales du Val-d'Oise</a></div>"""  # noqa
            self.assertEqual(enhance_rgaa(html, cnx), expected)

    def test_link_invalid_html(self):
        html = """href="www.archives.valdoise.fr" title="{0}"> Archives départementales du Val-d'Oise</a></div>"""  # noqa
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_link_remove_identical_link_title(self):
        title = "Archives départementales du Val-d'Oise"
        label = "Archives départementales du <i>Val-d'Oise</i>"
        html = f'<div><a href="./article" title="{title}">{label}</a></div>'
        with self.admin_access.cnx() as cnx:
            expected = f'<div><a href="./article">{label}</a></div>'
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_add_blank_target(self):
        html = '<div><a href="www.google">google</a></div>'
        expected = (
            '<div><a href="www.google" rel="nofollow noopener noreferrer external" '
            'target="_blank">google</a></div>'
        )
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_do_not_add_blank_target(self):
        with self.admin_access.cnx() as cnx:
            html = '<div><a href="{}google.fr">google</a></div>'.format(cnx.base_url())
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_link_clean_external_link(self):
        html = '<a href="www.archives.valdoise.fr">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = (
                '<a href="www.archives.valdoise.fr" '
                'rel="nofollow noopener noreferrer external" '
                'target="_blank">toto</a>'
            )
            self.maxDiff = None
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_add_title_on_external_link(self):
        html = '<a href="www.archives.valdoise.fr">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = '<a href="www.archives.valdoise.fr" title="toto - new window">toto</a>'
            self.assertEqual(enhance_rgaa(html, cnx), expected)

    def test_link_add_title_on_external_link_1(self):
        html = '<a href="www.archives.valdoise.fr" title="toto">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = '<a href="www.archives.valdoise.fr" title="toto - new window">toto</a>'
            self.assertEqual(enhance_rgaa(html, cnx), expected)

    def test_link_add_title_on_external_link_2(self):
        html = '<a href="//www.archives.valdoise.fr" title="titi">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = (
                '<a href="//www.archives.valdoise.fr" ' 'title="toto - titi - new window">toto</a>'
            )
            self.assertEqual(enhance_rgaa(html, cnx), expected)

    def test_link_add_title_on_external_link_3(self):
        html = '<a href="www.archives.valdoise.fr" title="toto - titi - new window">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = (
                '<a href="www.archives.valdoise.fr" ' 'title="toto - titi - new window">toto</a>'
            )
            self.assertEqual(enhance_rgaa(html, cnx), expected)

    def test_link_clean_internal_link(self):
        html = (
            '<a href="/article" '
            'rel="nofollow noopener noreferrer external" '
            'target="_blank" '
            ">toto</a>"
        )
        with self.admin_access.cnx() as cnx:
            expected = '<a href="/article" target="_blank">toto</a>'
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_link_add_title_on_internal_link_1(self):
        html = '<a href="./article" title="titi">toto</a>'
        with self.admin_access.cnx() as cnx:
            expected = '<a href="./article" title="toto - titi">toto</a>'
            self.assertEqual(enhance_rgaa(html, cnx), expected)

    def test_link_add_title_on_internal_link_2(self):
        html = '<a href="/article">toto</a>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_rgaa(html, cnx), html)

    def test_link_keep_link_title(self):
        title = "Archives départementales du Val-d'Oise - Voir plus"
        label = "Archives départementales du Val-d'Oise"
        html = '<div><a href="www.archives.valdoise.fr" title="{0}">{1}</a></div>'.format(
            title, label
        )
        target = 'rel="nofollow noopener noreferrer external" target="_blank"'
        title = "Archives départementales du Val-d'Oise - Voir plus"
        with self.admin_access.cnx() as cnx:
            expected = (
                f'<div><a href="www.archives.valdoise.fr" '
                f'title="{title}" {target}>{label}</a></div>'
            )
            self.assertEqual(enhance_accessibility(html, cnx), expected)
            title = "Archives départementales du Val-d'Oise - Voir plus - new window"
            expected = (
                f'<div><a href="www.archives.valdoise.fr" ' f'title="{title}">{label}</a></div>'
            )
            self.assertEqual(enhance_rgaa(html, cnx), expected)

    def test_remove_rel(self):
        html = (
            '<a href="../location/18363459" target="_blank" rel="noopener">Saint-Laurent-Blangy</a>'
        )
        expected = '<a href="../location/18363459" target="_blank">Saint-Laurent-Blangy</a>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_add_empty_alt(self):
        """images must have alt attribute"""
        html = '<div><img src="http://advaldoise.fr"/></div>'
        expected = '<div><img src="http://advaldoise.fr" ' 'alt=""></div>'
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_add_link_title_as_alt(self):
        """image's alt inside a link must be equal to the link title"""
        label = "Archives départementales du <i>Val-d'Oise</i>"
        html = (
            '<div><img src="http://google.fr">'
            '<a href="www.archives.valdoise.fr">'
            '<img src="http://advaldoise.fr" '
            'alt="toto" />{}</a></div>'
        ).format(label)
        target = 'rel="nofollow noopener noreferrer external" target="_blank"'
        expected = (
            f'<div><img src="http://google.fr" alt="">'
            f'<a href="www.archives.valdoise.fr" {target} class="image-link">'
            f'<img src="http://advaldoise.fr" alt="{remove_html_tags(label)}"'
            f">{label}</a></div>"
        )
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_remove_alt_content(self):
        """images alt must be relevent"""
        html = (
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="illustration_1.jpg" '
            'width="523" height="371" >'
        )
        expected = (
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="" '
            'width="523" height="371">'
        )
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_alt_and_title(self):
        """images alt and title must be identical is title is present"""
        html = (
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="alt" '
            'title="title" width="523" height="371" />'
        )
        expected = (
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="alt" '
            'title="alt" width="523" height="371">'
        )
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_images_figure_tiny(self):
        """add role="figure" and aria-label= figcaption.text on the figure tag"""
        html = """<figure class="image"><img src="http://advaldoise.fr"/><figcaption>legende</figcaption></figure>"""
        expected = """<figure class="image" role="figure" aria-labelledby="caption_1"><img src="http://advaldoise.fr" alt=""><figcaption id="caption_1">legende</figcaption></figure>"""
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_stripped_html_node(self):
        with self.admin_access.cnx() as cnx:
            html = "\xa0<p>tooo</p>"
            self.assertEqual(enhance_accessibility(html, cnx), "<p>tooo</p>")

    def test_not_html_node(self):
        with self.admin_access.cnx() as cnx:
            html = "test<p>\xa0</p>"
            self.assertEqual(enhance_accessibility(html, cnx), html)

    def test_process_not_body_node(self):
        with self.admin_access.cnx() as cnx:
            html = "<body>\xa0<p>tooo</p></body>"
            self.assertEqual(enhance_accessibility(html, cnx, eid=1111), html)

    def test_image_link_class(self):
        """add a specific css class on image-links"""
        html = (
            '<a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer" '
            'target="_blank" class="toto">'
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="alt" /></a>'
        )
        expected = (
            '<a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer external" '
            'target="_blank" class="toto image-link">'
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt=""></a>'
        )
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_image_link_classes(self):
        """add a specific css class on image-links"""
        html = (
            '<a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer" '
            'target="_blank" class="toto image-link">'
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt="alt" /></a>'
        )
        expected = (
            '<a href="www.archives.valdoise.fr" rel="nofollow noopener noreferrer external" '
            'target="_blank" class="toto image-link">'
            '<img src="../file/01c12288z2dsd/illustration_1.jpg" alt=""></a>'
        )
        with self.admin_access.cnx() as cnx:
            self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_id_for_anchor(self):
        title = "Commune de Pierre-Bénite - Archives : communales"
        expected = "commune-de-pierrebenite--archives--communales"
        self.assertEqual(id_for_anchor(title), expected)

    def test_clean_internal_links(self):
        """also see the case of https://extranet.logilab.fr/ticket/73968852"""
        expected = """<div><a href="../article/37704">Article</a></div>"""
        for html in (
            """<div><a href="../article/37704#/">Article</a></div>""",
            """<div><a href="../article/37704/">Article</a></div>""",
            """<div><a href="../article/37704#/edit">Article</a></div>""",
            """<div><a href="../article/37704/#/edit">Article</a></div>""",
        ):
            with self.admin_access.cnx() as cnx:
                self.assertEqual(enhance_accessibility(html, cnx), expected)

    def test_media_subtitles(self):
        transcript = '<div class="media-subtitles hidden"><h1>Title</h1><p>Implémentation des adapteurs RDF pour traduire les entités suivantes en RiC-O</p></div>'  # noqa
        html = '<div class="media-subtitles-button"></div>' + transcript
        with self.admin_access.cnx() as cnx:
            filepath = self.datapath("html/transcription.html")
            with open(filepath, "r") as f:
                expected = f.read()
            generated = soup2xhtml(handle_subtitles(html, cnx), encoding=cnx.encoding)
            self.assertEqual(generated, expected)

    def test_clean_xss(self):
        with self.admin_access.cnx() as cnx:
            for title, expected in (
                (
                    'Fixer la frontière : Alpes-Maritimes <script>alert("toto")</script>',
                    'Fixer la frontière : Alpes-Maritimes alert("toto")',
                ),
                (
                    '<script>alert("titi")</script> Fixer la frontière : Alpes-Maritimes',
                    'alert("titi") Fixer la frontière : Alpes-Maritimes',
                ),
                (
                    'Fix<ScriPt>alert("tata")</scRipT> xer la frontière : Alpes-Maritimes',
                    'Fixalert("tata") xer la frontière : Alpes-Maritimes',
                ),
                (
                    'Fix<javascript>alert("tete") xer la frontière : Alpes-Maritimes',
                    'Fixalert("tete") xer la frontière : Alpes-Maritimes',
                ),
                (
                    "<xss onbeforescriptexecute=alert(1)><script>1</script>",
                    "<xss onbeforescriptexecute=alert(1)>1",
                ),
            ):
                clean_xss(title, cnx)
                self.assertEqual(clean_xss(title, cnx), expected)


class GlossaryUtilsTest(WebCWTC):
    def setUp(self):
        GLOSSARY_CACHE[:] = []
        super(GlossaryUtilsTest, self).setUp()
        with self.admin_access.repo_cnx() as cnx:
            terms = (("Archives", None), ("Inventaire d'archives", "Inventaires d'archives"))
            for term, pl in terms:
                if not cnx.find("GlossaryTerm", term=term):
                    gt = cnx.create_entity(
                        "GlossaryTerm",
                        term=term,
                        term_plural=pl,
                        short_description="%s descritpion" % term,
                        description="%s descritpion" % term,
                        sort_letter=term[0].lower(),
                    )
                    gt.cw_set(anchor=str(gt.eid))
            cnx.commit()

    def test_reveal_glossary(self):
        with self.admin_access.repo_cnx() as cnx:
            text = (
                "<p>Le portail rassemble les inventaires d'archives de toute la France</p>"  # noqa
            )
            term = cnx.find("GlossaryTerm", term="Inventaire d'archives").one()
            got = reveal_glossary(cnx, text).replace("&#39;", "'")
            expected = f"""<p>Le portail rassemble les <a href="{BASE_URL}glossaire#{term.eid}" class="fr-link" rel="noopener external" target="_blank">Inventaires d'archives</a>
        <button type="button" id="button-glossaire-{term.eid}" class="fr-btn--tooltip fr-btn" aria-describedby="tooltip-{term.eid}">
        </button>
        <span class="fr-tooltip fr-placement" id="tooltip-{term.eid}" role="tooltip" aria-hidden="true">Inventaire d'archives descritpion</span> de toute la France</p>"""
            self.assertEqual(got, expected)


class ImportUtiles(S3BfssStorageTestMixin, WebCWTC):
    def test_pdf_info(self):
        """
        Trying: create a pdf file and extract the text
        Expecting: the text is extracted
        """
        pdffile = self.get_or_create_imported_filepath(f"pdf.pdf")
        data = pdf.pdf_infos(pdffile)
        self.assertEqual(data["text"], "Test\nCirculaire chat\n\n\x0c")


if __name__ == "__main__":
    unittest.main()
