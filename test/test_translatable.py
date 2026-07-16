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

from cubicweb_web.devtools.testlib import WebCWTC, WebPostgresApptestConfiguration

from cubicweb_francearchives import SUPPORTED_LANGS
from cubicweb_francearchives.testutils import S3BfssStorageTestMixin

from pgfixtures import setup_module, teardown_module  # noqa

LANGS = list(SUPPORTED_LANGS[:])
LANGS.remove("fr")


class SectionTranslatableTests(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            self.section = cnx.create_entity(
                "Section",
                title="titre",
                subtitle="sous-titre",
                content="contenu",
                short_description="description",
                name="section",
            )
            cnx.commit()
            self.create_translations(cnx, self.section)

    def create_translations(self, cnx, section):
        """create translations for a Section"""
        for lang in LANGS:
            cnx.create_entity(
                "SectionTranslation",
                language=lang,
                title="{}_{}".format(section.title, lang),
                subtitle="{}_{}".format(section.subtitle, lang),
                content="{}_{}".format(section.content, lang),
                short_description="{}_{}".format(section.short_description, lang),
                translation_of=section,
            )
        cnx.commit()

    def test_section_all_translations(self):
        """
        Trying: create a Section with translations in all supported languages
        Expecting: all translations are present
        """
        with self.admin_access.cnx() as cnx:
            section = cnx.find("Section", eid=self.section.eid).one()
            for lang, values in section.translations().items():
                for attr in section.i18nfields:
                    self.assertEqual("{}_{}".format(getattr(section, attr), lang), values[attr])

    def test_section_translation_in_lang(self):
        """
        Trying: create a Section with translations in all supported languages
        Expecting: check translations in a particular language
        """
        with self.admin_access.cnx() as cnx:
            section = cnx.find("Section", eid=self.section.eid).one()
            self.assertFalse(section.translations_in_lang())

    def test_section_meta_in_lang(self):
        """
        Trying: create a Section with translations in all supported languages
        Expecting: check meta data
        """
        with self.admin_access.cnx() as cnx:
            section = cnx.find("Section", eid=self.section.eid).one()
            self.assertEqual(3, len(section.reverse_translation_of))
            for lang in LANGS:
                cnx.set_language(lang)
                section.cw_adapt_to("ITranslatable").cache_entity_translations()
                self.assertIn(lang, section.dc_title())
                meta = section.cw_adapt_to("IMeta")
                self.assertEqual(section.dc_title(), meta.title())
            cnx.set_language("fr")
            section.cw_clear_all_caches()
            meta = section.cw_adapt_to("IMeta")
            self.assertEqual("titre - sous-titre", meta.title())

    def test_section_dctitles_in_lang(self):
        """
        Trying: create a Section with translations in all supported languages
        Expecting: check dc_title
        """
        with self.admin_access.cnx() as cnx:
            section = cnx.find("Section", eid=self.section.eid).one()
            for lang in LANGS:
                cnx.set_language(lang)
                self.assertEqual(
                    "titre_{lang} - sous-titre_{lang}".format(lang=lang), section.dc_title()
                )
            cnx.set_language("fr")
            section.cw_clear_all_caches()
            self.assertEqual("titre - sous-titre", section.dc_title())


class BaseContentTranslatableTests(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            self.bc = cnx.create_entity(
                "BaseContent",
                title="titre",
                content="contenu",
            )
            cnx.commit()
            self.create_translations(cnx, self.bc)
            bc = cnx.find("BaseContent", eid=self.bc.eid).one()
            self.assertEqual(3, len(bc.reverse_translation_of))

    def create_translations(self, cnx, bc):
        """create translations for a BaseContent"""
        for lang in LANGS:
            cnx.create_entity(
                "BaseContentTranslation",
                language=lang,
                title="{}_{}".format(bc.title, lang),
                content="{}_{}".format(bc.content, lang),
                translation_of=bc,
            )
        cnx.commit()

    def test_basecontent_all_translations(self):
        """
        Trying: create a BaseContent with translations in all supported languages
        Expecting: all translations are present
        """
        with self.admin_access.cnx() as cnx:
            bc = cnx.find("BaseContent", eid=self.bc.eid).one()
            for lang, values in bc.translations().items():
                for attr in bc.i18nfields:
                    if attr in ("summary", "header"):
                        self.assertEqual(None, values[attr])
                    else:
                        self.assertEqual("{}_{}".format(getattr(bc, attr), lang), values[attr])

    def test_basecontent_translation_in_lang(self):
        """
        Trying: create a BaseContent with translations in all supported languages
        Expecting: check translations in a particular language
        """
        with self.admin_access.cnx() as cnx:
            bc = cnx.find("BaseContent", eid=self.bc.eid).one()
            self.assertFalse(bc.translations_in_lang())

    def test_basecontent_meta_in_lang(self):
        """
        Trying: create a BaseContent with translations in all supported languages
        Expecting: check meta data
        """
        with self.admin_access.cnx() as cnx:
            bc = cnx.find("BaseContent", eid=self.bc.eid).one()
            for lang in LANGS:
                cnx.set_language(lang)
                bc.cw_adapt_to("ITranslatable").cache_entity_translations()
                self.assertIn(lang, bc.dc_title())
                meta = bc.cw_adapt_to("IMeta")
                self.assertEqual(bc.dc_title(), meta.title())
            cnx.set_language("fr")
            bc.cw_clear_all_caches()
            meta = bc.cw_adapt_to("IMeta")
            self.assertEqual("titre", meta.title())

    def test_basecontent_dctitles_in_lang(self):
        """
        Trying: create a BaseContent with translations in all supported languages
        Expecting: check dc_title
        """
        with self.admin_access.cnx() as cnx:
            bc = cnx.find("BaseContent", eid=self.bc.eid).one()
            for lang in LANGS:
                cnx.set_language(lang)
                self.assertEqual("titre_{lang}".format(lang=lang), bc.dc_title())
            cnx.set_language("fr")
            bc.cw_clear_all_caches()
            self.assertEqual("titre", bc.dc_title())


class CommemorationItemTranslatableTests(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            self.citem = cnx.create_entity(
                "CommemorationItem",
                title="titre",
                subtitle="subtitre",
                alphatitle="titre",
                content="content",
                commemoration_year=2019,
            )
            cnx.commit()
            self.create_translations(cnx, self.citem)
            citem = cnx.find("CommemorationItem", eid=self.citem.eid).one()
            self.assertEqual(3, len(citem.reverse_translation_of))

    def create_translations(self, cnx, citem):
        """create translations for a CommemorationItem"""
        for lang in LANGS:
            cnx.create_entity(
                "CommemorationItemTranslation",
                language=lang,
                title="{}_{}".format(citem.title, lang),
                subtitle="{}_{}".format(citem.subtitle, lang),
                content="{}_{}".format(citem.content, lang),
                translation_of=citem,
            )
        cnx.commit()

    def test_commemo_item_all_translations(self):
        """
        Trying: create a CommemorationItem with translations in all supported languages
        Expecting: all translations are present
        """
        with self.admin_access.cnx() as cnx:
            citem = cnx.find("CommemorationItem", eid=self.citem.eid).one()
            for lang, values in citem.translations().items():
                for attr in citem.i18nfields:
                    if attr in ("summary",):
                        self.assertEqual(None, values[attr])
                    else:
                        self.assertEqual("{}_{}".format(getattr(citem, attr), lang), values[attr])

    def test_commemo_item_translation_in_lang(self):
        """
        Trying: create a CommemorationItem with translations in all supported languages
        Expecting: check translations in a particular language
        """
        with self.admin_access.cnx() as cnx:
            citem = cnx.find("CommemorationItem", eid=self.citem.eid).one()
            self.assertFalse(citem.translations_in_lang())

    def test_commemo_item_meta_in_lang(self):
        """
        Trying: create a CommemorationItem with translations in all supported languages
        Expecting: check meta data
        """
        with self.admin_access.cnx() as cnx:
            citem = cnx.find("CommemorationItem", eid=self.citem.eid).one()
            for lang in LANGS:
                cnx.set_language(lang)
                citem.cw_adapt_to("ITranslatable").cache_entity_translations()
                self.assertIn(lang, citem.dc_title())
                meta = citem.cw_adapt_to("IMeta")
                self.assertEqual(citem.dc_title(), meta.title())
            cnx.set_language("fr")
            citem.cw_clear_all_caches()
            meta = citem.cw_adapt_to("IMeta")
            self.assertEqual("titre", meta.title())

    def test_commemo_item_dctitles_in_lang(self):
        """
        Trying: create a CommemorationItem with translations in all supported languages
        Expecting: check dc_title
        """
        with self.admin_access.cnx() as cnx:
            citem = cnx.find("CommemorationItem", eid=self.citem.eid).one()
            for lang in LANGS:
                cnx.set_language(lang)
                self.assertEqual("titre_{lang}".format(lang=lang), citem.dc_title())
            cnx.set_language("fr")
            citem.cw_clear_all_caches()
            self.assertEqual("titre", citem.dc_title())


class FaqItemTranslatableTests(S3BfssStorageTestMixin, WebCWTC):
    configcls = WebPostgresApptestConfiguration

    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            self.faqitem = cnx.create_entity(
                "FaqItem", question="Who?", answer="Dr. Who", category="02_faq_search"
            )
            cnx.commit()
            self.create_translations(cnx, self.faqitem)

    def create_translations(self, cnx, faqitem):
        """create translations for a FaqItem"""
        for lang in LANGS:
            cnx.create_entity(
                "FaqItemTranslation",
                language=lang,
                question="{}_{}".format(faqitem.question, lang),
                answer="{}_{}".format(faqitem.answer, lang),
                translation_of=faqitem,
            )
        cnx.commit()

    def test_faq_translations(self):
        with self.admin_access.cnx() as cnx:
            faqitem = cnx.find("FaqItem", eid=self.faqitem.eid).one()
            self.assertEqual(3, len(faqitem.reverse_translation_of))

    def test_faqitem_all_translations(self):
        """
        Trying: create a FaqItem with translations in all supported languages
        Expecting: all translations are present
        """
        with self.admin_access.cnx() as cnx:
            faqitem = cnx.find("FaqItem", eid=self.faqitem.eid).one()
            for lang, values in faqitem.translations().items():
                for attr in faqitem.i18nfields:
                    self.assertEqual("{}_{}".format(getattr(faqitem, attr), lang), values[attr])

    def test_faqitem_translation_in_lang(self):
        """
        Trying: create a FaqItem with translations in all supported languages
        Expecting: check translations in a particular language
        """
        with self.admin_access.cnx() as cnx:
            faqitem = cnx.find("FaqItem", eid=self.faqitem.eid).one()
            self.assertFalse(faqitem.translations_in_lang())

    def test_faqitem_meta_in_lang(self):
        """
        Trying: create a FaqItem with translations in all supported languages
        Expecting: check meta data
        """
        with self.admin_access.cnx() as cnx:
            faqitem = cnx.find("FaqItem", eid=self.faqitem.eid).one()
            for lang in LANGS:
                cnx.set_language(lang)
                faqitem.cw_adapt_to("ITranslatable").cache_entity_translations()
                self.assertIn("Who?_{}".format(lang), faqitem.dc_title())
                meta = faqitem.cw_adapt_to("IMeta")
                self.assertEqual(faqitem.dc_title(), meta.title())
            cnx.set_language("fr")
            faqitem.cw_clear_all_caches()
            meta = faqitem.cw_adapt_to("IMeta")
            self.assertEqual("Who?", meta.title())

    def test_faqitem_dctitles_in_lang(self):
        """
        Trying: create a FaqItem with translations in all supported languages
        Expecting: check dc_title
        """
        with self.admin_access.cnx() as cnx:
            faqitem = cnx.find("FaqItem", eid=self.faqitem.eid).one()
            for lang in LANGS:
                cnx.set_language(lang)
                self.assertEqual("Who?_{lang}".format(lang=lang), faqitem.dc_title())
            cnx.set_language("fr")
            faqitem.cw_clear_all_caches()
            self.assertEqual("Who?", faqitem.dc_title())


if __name__ == "__main__":
    unittest.main()
