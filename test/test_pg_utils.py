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
"""cubicweb-francearcihves tests for postgres utils"""
import string

from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.dataimport import normalize_entry
from cubicweb_francearchives.testutils import PostgresTextMixin

from pgfixtures import setup_module, teardown_module  # noqa


class SQLUtilsBaseTC(PostgresTextMixin, WebCWTC):
    def test_normalize_entry_iso(self):
        """labels whose normalization is the same in Python and PostgreSQL"""
        with self.admin_access.cnx() as cnx:
            query = "SELECT NORMALIZE_ENTRY(%(label)s)"
            for label, expected in (
                ("Charles de Gaulle", "charles de gaulle"),
                ("Charles   de Gaulle", "charles de gaulle"),
                ("Charles, Gaulle (de)", "charles gaulle de"),
                ("Gaulle de, Charles", "gaulle de charles"),
                ("Charles (de)   Gaulle", "charles de gaulle"),
                ("Charles de Gaulle (1890-1970)", "charles de gaulle 1890 1970"),
                ("Charles de Gaulle (1890 - 1970)", "charles de gaulle 1890 1970"),
                ("Charles de Gaulle (1890 - 1970)", "charles de gaulle 1890 1970"),
                ("Liszt, Franz (1811-1886)", "liszt franz 1811 1886"),
                ("Liszt (Franz)", "liszt franz"),
                ("Guerre d'Algérie (1954-1962)", "guerre d algerie 1954 1962"),
                ("debré, jean-louis (1944-....)", "debre jean louis 1944"),
                ("DEBRE, Jean-Louis", "debre jean louis"),
                ("Debré, Jean-Louis", "debre jean louis"),
                ("Tavel... (de)", "tavel de"),
                ("Bonaparte, Élisa (1777-1820)", "bonaparte elisa 1777 1820"),
                ("Deboraüde ?", "deboraude"),
                ("Tavel… (de)", "tavel. de"),
                (
                    "Blein (Ange François Alexandre) , général",
                    "blein ange francois alexandre general",
                ),
                (
                    "Route nationale (n° 120) -- Cantal (France)",
                    "route nationale n_ 120 cantal france",
                ),
                (
                    (
                        """Comité d'attribution des fonds recueillis à l'occasion """
                        """de la journée nationale des orphelins de guerre (France)"""
                    ),
                    (
                        """comite_ d attribution des fonds recueillis a_ l occasion """
                        """de la journe_e nationale des orphelins de guerre france"""
                    ),
                ),
                ("Punctuation {}".format(string.punctuation), "punctuation"),
            ):
                got = cnx.system_sql(query, {"label": label}).fetchall()[0][0]
                self.assertEqual(expected, got)
                self.assertEqual(expected, normalize_entry(label))

    def test_normalize_entry_not_iso(self):
        """labels whose normalization is not the same in Python and PostgreSQL"""
        with self.admin_access.cnx() as cnx:
            query = "SELECT NORMALIZE_ENTRY(%(label)s)"
            for label, expected in (
                # This is a sorting issue between "'" and "e" which is probably not
                # a big deal
                (
                    "Gauthier de rougemont, chef d’escadron",
                    [
                        "gauthier de rougemont chef d'escadron",
                        "gauthier de rougemont chef d escadron",
                    ],
                ),
            ):
                got = cnx.system_sql(query, {"label": label}).fetchall()[0][0]
                self.assertIn(got, expected)

    def test_translations(self):
        """test translate_entity postgres function"""
        with self.admin_access.cnx() as cnx:
            basecontent = cnx.create_entity(
                "BaseContent", title="Programme", content="<h1>31 juin</h1>", header="chapo"
            )
            cnx.commit()
            cnx.create_entity(
                "BaseContentTranslation",
                language="en",
                title="Program",
                content="<h1>31 june</h1>",
                translation_of=basecontent,
            )
            cnx.commit()
            query = "SELECT TRANSLATE_ENTITY(%(etype)s, %(eid)s, %(attr)s, %(lang)s)"
            for expected, attr, lang in (
                ("Programme", "title", "fr"),
                ("Program", "title", "en"),
                ("chapo", "header", "fr"),
                ("chapo", "header", "en"),
            ):
                got = cnx.system_sql(
                    query,
                    {
                        "etype": "BaseContent",
                        "eid": basecontent.eid,
                        "attr": attr,
                        "lang": lang,
                    },
                ).fetchall()[0][0]
                self.assertEqual(expected, got)
