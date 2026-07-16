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

import datetime as dt

from cubicweb_web.devtools.testlib import WebCWTC


class MetaTests(WebCWTC):
    def test_newscontent_default_metadata(self):
        """tests IMeta when no Metadata entity is created"""
        with self.admin_access.cnx() as cnx:
            newscontent = cnx.create_entity(
                "NewsContent",
                title="the-news",
                content="the-content",
                start_date=dt.date(2011, 1, 1),
            )
            meta = newscontent.cw_adapt_to("IMeta")
            self.assertEqual(
                meta.meta_data(),
                [
                    ("title", "the-news"),
                    ("twitter:card", "summary"),
                    ("twitter:site", "@FranceArchives"),
                ],
            )

    def test_newscontent_with_metadata(self):
        """tests IMeta when a Metadata entity is created"""
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity(
                "Metadata",
                title="meta-title",
                description="meta-descr",
                keywords="kw1 kw2",
                subject="the-subject",
                creator="john",
            )
            newscontent = cnx.create_entity(
                "NewsContent",
                title="the-news",
                content="the-content",
                start_date=dt.date(2011, 1, 1),
                metadata=metadata,
            )
            meta = newscontent.cw_adapt_to("IMeta")
            self.assertEqual(
                meta.meta_data(),
                [
                    ("title", "meta-title"),
                    ("description", "meta-descr"),
                    ("keywords", "kw1 kw2"),
                    ("author", "john"),
                    ("subject", "the-subject"),
                    ("twitter:card", "summary"),
                    ("twitter:site", "@FranceArchives"),
                ],
            )

    def test_newscontent_mix_with_metadata(self):
        """tests IMeta when a Metadata entity is created"""
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity("Metadata", description="meta-descr", keywords="kw1 kw2")
            newscontent = cnx.create_entity(
                "NewsContent",
                title="the-news",
                content="the-content",
                start_date=dt.date(2011, 1, 1),
                metadata=metadata,
            )
            meta = newscontent.cw_adapt_to("IMeta")
            self.assertEqual(
                meta.meta_data(),
                [
                    ("title", "the-news"),
                    ("description", "meta-descr"),
                    ("keywords", "kw1 kw2"),
                    ("twitter:card", "summary"),
                    ("twitter:site", "@FranceArchives"),
                ],
            )

    def test_faqitem_default_metadata(self):
        """tests IMeta when for FaqItem"""
        with self.admin_access.cnx() as cnx:
            newscontent = cnx.create_entity(
                "FaqItem",
                question="<p>question</p>",
                answer="answser",
            )
            meta = newscontent.cw_adapt_to("IMeta")
            self.assertEqual(
                meta.meta_data(),
                [
                    ("title", "question"),
                    ("twitter:card", "summary"),
                    ("twitter:site", "@FranceArchives"),
                ],
            )


class OpenGraphTests(WebCWTC):
    def test_news_opengraph(self):
        with self.admin_access.cnx() as cnx:
            metadata = cnx.create_entity(
                "Metadata",
                title="meta-title",
                description="meta-descr",
                keywords="kw1 kw2",
                subject="the-subject",
                creator="john",
            )
            newscontent = cnx.create_entity(
                "NewsContent",
                title="the-news",
                content="the-content",
                start_date=dt.date(2011, 1, 1),
                metadata=metadata,
            )
            ogdata = newscontent.cw_adapt_to("IOpenGraph")
            self.assertEqual(
                ogdata.og_data(),
                [
                    ("locale", "fr_FR"),
                    ("site_name", "FranceArchives"),
                    ("url", newscontent.absolute_url()),
                    ("title", "meta-title"),
                    ("description", "meta-descr"),
                    ("type", "article"),
                ],
            )

    def test_card_locale_opengraph(self):
        """test card locale handling"""
        with self.admin_access.cnx() as cnx:
            card = cnx.create_entity(
                "Card", wikiid="card-de", title="the-card", content="some-content"
            )
            ogdata = card.cw_adapt_to("IOpenGraph")
            self.assertEqual(
                ogdata.og_data(),
                [
                    ("locale", "de_DE"),
                    ("site_name", "FranceArchives"),
                    ("url", card.absolute_url()),
                    ("title", "the-card"),
                    ("type", "article"),
                ],
            )
            card.cw_set(wikiid="some-card")
            ogdata = card.cw_adapt_to("IOpenGraph")
            self.assertEqual(
                ogdata.og_data(),
                [
                    ("locale", "fr_FR"),  # ← lang default to fr
                    ("site_name", "FranceArchives"),
                    ("url", card.absolute_url()),
                    ("title", "the-card"),
                    ("type", "article"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
