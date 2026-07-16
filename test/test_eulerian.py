# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2023
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

from datetime import date

from unittest.mock import patch

from cubicweb import Binary

from cubicweb_web.devtools.testlib import WebCWTC
from cubicweb_francearchives import FIRST_LEVEL_SECTIONS
from cubicweb_francearchives.entities import ead
from cubicweb_francearchives.testutils import S3BfssStorageTestMixin, PostgresTextMixin
from elasticsearch_dsl.search import Search
from elasticsearch_dsl.response import Response as ESResponse

from pgfixtures import setup_module, teardown_module  # noqa


class PniaWebCWTC(WebCWTC):
    def setup_database(self):
        with self.admin_access.cnx() as cnx:
            for name in FIRST_LEVEL_SECTIONS:
                cnx.create_entity("Section", name=name, title=name)
            cnx.commit()


class FakeResponse(ESResponse):
    def __init__(self):
        response = {"hits": {"hits": [], "total": {"value": 0, "relation": ""}}, "facets": {}}
        super().__init__(Search(), response)


def _template_context(req, vid):
    viewsreg = req.vreg["views"]
    view = viewsreg.select(vid, req, rset=None)
    tmpl = viewsreg.select("main-template", req, rset=None, view=view)
    return tmpl.template_context(view)


class EntityEulerianTests(S3BfssStorageTestMixin, PniaWebCWTC):
    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", category="cat", code="FRAD084")
            cnx.commit()
            self.service_eid = service.eid

    def create_findingaid(self, cnx, service=None):
        fadid = cnx.create_entity("Did", unitid="maindid", unittitle="maindid-title")
        if service:
            service = self.service_eid
        return cnx.create_entity(
            "FindingAid",
            name="the-fa",
            stable_id="FRAD084_xxx",
            eadid="FRAD084_xxx",
            publisher="FRAD084",
            service=service,
            did=fadid,
            fa_header=cnx.create_entity("FAHeader"),
        )

    def create_facomponent(self, cnx, service=None):
        fcdid = cnx.create_entity(
            "Did",
            unitid="fcdid",
            unittitle="fcdid-title",
            startyear=1234,
            stopyear=1245,
            origination="fc-origination",
            repository="fc-repo",
        )
        return cnx.create_entity(
            "FAComponent",
            finding_aid=self.create_findingaid(cnx, service=service),
            stable_id="fc-stable-id",
            did=fcdid,
            scopecontent="fc-scoppecontent",
            description="fc-descr",
        )

    def test_findingaid_noservice(self):
        with self.admin_access.cnx() as cnx:
            fa = self.create_findingaid(cnx)
            adapter = fa.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/findingaid/unknown-service/frad084_xxx")
            self.assertEqual(adapter.pagegroup, "archives")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.additional, {"iiif": "0"})
            self.assertEqual(adapter.pagelabel, "no-iiif,unknown-service,findingaid")
            actions = {
                "document_title": "findingaid_frad084_xxx",
                "page_type": "archives",
                "service_code": "",
                "type_doc": "findingaid",
            }
            self.assertEqual(actions, adapter.actions)

    def test_findingaid_service(self):
        with self.admin_access.cnx() as cnx:
            fa = self.create_findingaid(cnx, service=True)
            adapter = fa.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/findingaid/frad084/frad084_xxx")
            self.assertEqual(adapter.pagegroup, "archives")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.additional, {"iiif": "0"})
            self.assertEqual(adapter.pagelabel, "no-iiif,frad084,findingaid")
            actions = {
                "document_title": "findingaid_frad084_xxx",
                "page_type": "archives",
                "service_code": "frad084",
                "type_doc": "findingaid",
            }
            self.assertEqual(actions, adapter.actions)

    def test_facomponent_noservice(self):
        with self.admin_access.cnx() as cnx:
            facomp = self.create_facomponent(cnx)
            adapter = facomp.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/facomponent/unknown-service/fc-stable-id")
            self.assertEqual(adapter.pagegroup, "archives")
            self.assertEqual(adapter.pagelabel, "no-iiif,unknown-service,facomponent")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.additional, {"iiif": "0"})
            actions = {
                "document_title": "facomponent_fc-stable-id",
                "page_type": "archives",
                "service_code": "",
                "type_doc": "facomponent",
            }
            self.assertEqual(actions, adapter.actions)

    def test_facomponent_service(self):
        with self.admin_access.cnx() as cnx:
            facomp = self.create_facomponent(cnx, service=True)
            adapter = facomp.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/facomponent/frad084/fc-stable-id")
            self.assertEqual(adapter.pagelabel, "no-iiif,frad084,facomponent")
            self.assertEqual(adapter.pagegroup, "archives")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.additional, {"iiif": "0"})
            actions = {
                "document_title": "facomponent_fc-stable-id",
                "page_type": "archives",
                "service_code": "frad084",
                "type_doc": "facomponent",
            }
            self.assertEqual(actions, adapter.actions)

    def test_findingaid_iiif(self):
        with self.admin_access.cnx() as cnx:
            fc = self.create_findingaid(cnx, service=True)
            adapter = fc.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/findingaid/frad084/frad084_xxx")
            self.assertEqual(adapter.pagegroup, "archives")
            self.assertEqual(adapter.events, [])
            with patch.object(ead.FindingAidBaseMixin, "iiif_manifest", return_value=True):
                self.assertEqual(adapter.additional, {"iiif": "1"})
                self.assertEqual(adapter.pagelabel, "iiif,frad084,findingaid")

    def test_basecontent(self):
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity("BaseContent", title="t'he-titl’e")
            adapter = bc.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/basecontent/{bc.eid}/the-title")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",unknown-service,basecontent")

    def test_basecontent_publication(self):
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity(
                "BaseContent",
                content_type="Publication",
                title="the-title",
                reverse_children=cnx.create_entity("Section", title="Publication", name="Section"),
            )
            adapter = bc.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/publication/{bc.eid}/the-title")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",unknown-service,publication")

    def test_basecontent_publication_translation(self):
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity(
                "BaseContent",
                content_type="Publication",
                title="Un titre long",
                reverse_children=cnx.create_entity("Section", title="Publication", name="Section"),
            )
            lang = "en"
            bct = cnx.create_entity(
                "BaseContentTranslation",
                language=lang,
                title="{}_{}".format(bc.title, lang),
                content="{}_{}".format(bc.content, lang),
                translation_of=bc,
            )
            adapter = bct.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/publication/{bc.eid}/en/un_titre_long_en")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            ["no-iiif", "unknown-service", "publication"]

    def test_basecontent_search_help(self):
        with self.admin_access.cnx() as cnx:
            bc = cnx.create_entity("BaseContent", title="the-title", content_type="SearchHelp")
            adapter = bc.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/searchhelp/{bc.eid}/the-title")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",unknown-service,searchhelp")

    def test_newscontent(self):
        with self.admin_access.cnx() as cnx:
            news = cnx.create_entity("NewsContent", start_date="2017/01/01", title="the-title")
            adapter = news.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/newscontent/{news.eid}/the-title")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,newscontent")

    def test_externref(self):
        with self.admin_access.cnx() as cnx:
            extref = cnx.create_entity(
                "ExternRef",
                reftype="Virtual_exhibit",
                title="externref-title",
                url="http://toto",
                start_year=1982,
                exref_service=self.service_eid,
            )
            adapter = extref.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/virtual_exhibit/{extref.eid}/externref-title")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",frad084,virtual_exhibit")

    def test_commemoration_item(self):
        with self.admin_access.cnx() as cnx:
            item = cnx.create_entity(
                "CommemorationItem",
                commemoration_year=2017,
                title="sortie francearchives",
            )
            adapter = item.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/commemo/2017/sortie_francearchives")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,commemorationitem")

    def test_commemoration_item_translation(self):
        with self.admin_access.cnx() as cnx:
            item = cnx.create_entity(
                "CommemorationItem",
                commemoration_year=2017,
                alphatitle="foo",
                title="sortie francearchives",
            )
            lang = "en"
            translation = cnx.create_entity(
                "CommemorationItemTranslation",
                language=lang,
                title="{}_{}".format(item.title, lang),
                subtitle="{}_{}".format(item.subtitle, lang),
                content="{}_{}".format(item.content, lang),
                translation_of=item,
            )
            adapter = translation.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/commemo/2017/en/sortie_francearchives_en")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,commemorationitem")

    def test_map(self):
        with self.admin_access.cnx() as cnx:
            map = cnx.create_entity("Map", map_file=Binary(b""), title="éleveurs de poules")
            adapter = map.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/map/{map.eid}/eleveurs_de_poules")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,map")

    def test_section(self):
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity("Section", title="Publication", name="Section")
            adapter = section.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/section/{section.eid}/publication")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,section")

    def test_section_translation(self):
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity("Section", title="Publication", name="Section")
            lang = "en"
            translation = cnx.create_entity(
                "SectionTranslation",
                language=lang,
                title="{}_{}".format(section.title, lang),
                translation_of=section,
            )
            adapter = translation.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/section/{section.eid}/en/publication_en")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.pagelabel, ",,section")

    def test_service_without_code(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity("Service", category="cat", name="Archives de Vendée")
            adapter = service.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/service/{service.eid}")
            self.assertEqual(adapter.pagegroup, "service")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,service")

    def test_service_with_code(self):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="cat", code="FRAD085", name="Archives de Vendée"
            )
            adapter = service.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/service/frad085")
            self.assertEqual(adapter.pagegroup, "service")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,service")

    def test_card(self):
        with self.admin_access.cnx() as cnx:
            card = cnx.find("Card", wikiid="cgu-fr").one()
            adapter = card.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/card/cgu-fr")
            self.assertEqual(adapter.pagegroup, "editorial")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,card")

    def test_circular(self):
        with self.admin_access.cnx() as cnx:
            circular = cnx.create_entity(
                "Circular", circ_id="circ1", status="revoked", title="circ1"
            )
            adapter = circular.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/circular/circ1")
            self.assertEqual(adapter.pagegroup, "circular")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,circular")

    def test_nominarecord_service(self):
        with self.admin_access.cnx() as cnx:
            record = cnx.create_entity(
                "NominaRecord",
                stable_id="FRAD084_42",
                json_data={"p": [{"n": "Valjean"}], "t": "RM"},
                service=self.service_eid,
            )
            cnx.commit()
            adapter = record.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/nominarecord/frad084/frad084_42")
            self.assertEqual(adapter.pagegroup, "nomina")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",frad084,nominarecord")

    def test_authority_record(self):
        with self.admin_access.repo_cnx() as cnx:
            kind_eid = cnx.find("AgentKind", name="person")[0][0]
            name = "Jean toto"
            record = cnx.create_entity(
                "AuthorityRecord",
                record_id="FRAN_NP_006883",
                agent_kind=kind_eid,
                maintainer=self.service_eid,
                reverse_name_entry_for=cnx.create_entity(
                    "NameEntry", parts=name, form_variant="authorized"
                ),
                xml_support="foo",
                start_date=date(1940, 1, 1),
                end_date=date(2000, 5, 1),
                reverse_occupation_agent=cnx.create_entity("Occupation", term="éleveur de poules"),
                reverse_history_agent=cnx.create_entity(
                    "History", text="<p>Il aimait les poules</p>"
                ),
            )
            adapter = record.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, "/authorityrecord/fran_np_006883/jean_toto")
            self.assertEqual(adapter.pagegroup, "eac")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,authorityrecord")
            actions = {
                "document_title": "authorityrecord_fran_np_006883",
                "page_type": "eac",
                "service_code": "frad084",
                "type_doc": "authorityrecord",
            }
            self.assertEqual(actions, adapter.actions)

    def test_agent_authority(self):
        with self.admin_access.repo_cnx() as cnx:
            agent = cnx.create_entity("AgentAuthority", label="Grüner Veltliner")
            adapter = agent.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/agentauthority/{agent.eid}/gruner_veltliner")
            self.assertEqual(adapter.pagegroup, "authorities")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,agentauthority")

    def test_subject_authority(self):
        with self.admin_access.repo_cnx() as cnx:
            agent = cnx.create_entity("SubjectAuthority", label="Wein")
            adapter = agent.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/subjectauthority/{agent.eid}/wein")
            self.assertEqual(adapter.pagegroup, "authorities")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,subjectauthority")

    def test_location_authority(self):
        with self.admin_access.repo_cnx() as cnx:
            agent = cnx.create_entity("LocationAuthority", label="Niederösterreich")
            adapter = agent.cw_adapt_to("IEulerian")
            self.assertEqual(adapter.path, f"/locationauthority/{agent.eid}/niederosterreich")
            self.assertEqual(adapter.events, [])
            self.assertEqual(adapter.pagelabel, ",,locationauthority")


class ViewsEulerianTests(S3BfssStorageTestMixin, PostgresTextMixin, PniaWebCWTC):

    def setUp(self):
        super().setUp()
        # add the eulerian configuration parameters required by the test suite
        self.config.global_set_option("eulerian_domain", "sr.fa")

    def setup_database(self):
        super().setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("Service", category="cat", short_name="AD Vaucluse", code="FRAD084")
            cnx.create_entity("BaseContent", title="title")
            cnx.create_entity("BaseContent", title="title")
            cnx.commit()

    def test_home(self):
        with self.admin_access.web_request("") as req:
            ctx = _template_context(req, "index")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": [],
                    "page": {"pagegroup": "home", "path": "/"},
                },
            )

    def test_faq(self):
        with self.admin_access.web_request("faq") as req:
            ctx = _template_context(req, "faq")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": [],
                    "page": {"pagegroup": "faq", "path": "/faq"},
                },
            )

    def test_sitemap(self):
        with self.admin_access.web_request("sitemap") as req:
            ctx = _template_context(req, "sitemap")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": [],
                    "page": {"pagegroup": "sitemap", "path": "/sitemap"},
                },
            )

    def test_sparql_yasgui(self):
        with self.admin_access.web_request("sparql") as req:
            ctx = _template_context(req, "sparql-yasgui")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": [],
                    "page": {"pagegroup": "sparql", "path": "/sparql"},
                },
            )

    def test_sparnatural(self):
        with self.admin_access.web_request("requeteurnaturel") as req:
            ctx = _template_context(req, "sparnatural")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": [],
                    "page": {"pagegroup": "sparnatural", "path": "/sparnatural"},
                },
            )

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_advanced_search(self, feature):
        path = 'earch?q=&advanced=true&searches=[30303793]&searches_op=[]&searches_t=["l"]&services=[34633%2C33366]&services_op="OU"&producers=["Ministère%20de%20la%20Défense%20nationale.%20Dépôt%20des%20Archives%20de%20l%27Intendance%20à%20Crouelle%20(Puy-de-Dôme)"]&producers_op=[]&producers_t=["k"]&es_date_min=12345&es_date_max=12345'  # noqa
        with self.admin_access.web_request(path) as req:
            req.form = {
                "advanced": "true",
                "es_date_max": "12345",
                "es_date_min": "12345",
                "producers": (
                    '["Ministère de la Défense nationale. Dépôt des Archives de '
                    "l'Intendance à Crouelle (Puy-de-Dôme)\"]"
                ),
                "producers_op": "[]",
                "producers_t": '["k"]',
                "q": "",
                "searches": "[30303793]",
                "searches_op": "[]",
                "searches_t": '["l"]',
                "services": "[34633,33366]",
                "services_op": '"OU"',
            }
            ctx = _template_context(req, "esearch")
            events = (
                ("isearchengine", "advanced_search"),
                ("isearchresults", "0"),
                ("isearchkey", "es_date_max"),
                ("isearchdata", "12345"),
                ("isearchkey", "es_date_min"),
                ("isearchdata", "12345"),
                ("isearchkey", "producers"),
                (
                    "isearchdata",
                    "ministere_de_la_defense_nationale._depot_des_archives_de_lintendance_a_crouelle_puy-de-dome",  # noqa
                ),
                ("isearchkey", "producers_t"),
                ("isearchdata", "k"),
                ("isearchkey", "search_term"),
                ("isearchdata", "30303793"),
                ("isearchkey", "searches_t"),
                ("isearchdata", "l"),
                ("isearchkey", "services"),
                ("isearchdata", "3463333366"),
                ("isearchkey", "services_op"),
                ("isearchdata", "ou"),
            )
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": events,
                    "page": {"pagegroup": "advanced_search", "path": "/advanced_search"},
                },
            )

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_global_search_no_params(self, _search):
        with self.admin_access.web_request("search") as req:
            ctx = _template_context(req, "esearch")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": (
                        ("isearchengine", "main_search"),
                        ("isearchresults", "0"),
                    ),
                    "page": {"pagegroup": "search", "path": "/search"},
                },
            )

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_global_search_archives(self, _search):
        path = "search?q=&es_escategory=archives"
        with self.admin_access.web_request(path) as req:
            req.form = {
                "es_escategory": "archives",
            }
            ctx = _template_context(req, "esearch")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": (
                        ("isearchengine", "main_search"),
                        ("isearchresults", "0"),
                        ("isearchkey", "category"),
                        ("isearchdata", "archives"),
                    ),
                    "page": {"pagegroup": "search", "path": "/search"},
                },
            )

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_global_search_with_params(self, _search):
        path = "search?es_cw_etype=Article&es_cw_etype=Service&es_date_max=2344&es_date_min=123&es_escategory=archives&es_escategory=siteres&q=test&es_publisher=33359"  # noqa
        with self.admin_access.web_request(path) as req:
            req.form = {
                "es_cw_etype": ["Article", "Service"],
                "es_date_max": "2344",
                "es_date_min": "123",
                "es_publisher": "33359",
                "es_escategory": ["archives", "siteres"],
                "q": "test",
            }
            ctx = _template_context(req, "esearch")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "events": (
                    ("isearchengine", "main_search"),
                    ("isearchresults", "0"),
                    ("isearchkey", "search_term"),
                    ("isearchdata", "test"),
                    ("isearchkey", "category"),
                    ("isearchdata", "archives,siteres"),
                    ("isearchkey", "document_type_facet"),
                    ("isearchdata", "article,service"),
                    ("isearchkey", "date-max-facet"),
                    ("isearchdata", "2344"),
                    ("isearchkey", "date-min-facet"),
                    ("isearchdata", "123"),
                    ("isearchkey", "publishers_facet"),
                    ("isearchdata", "33359"),
                ),
                "page": {"pagegroup": "search", "path": "/search"},
            }
            self.assertDictEqual(ctx["tracking"], expected)

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_global_search_inventaires(self, _search):
        with self.admin_access.web_request("inventaires") as req:
            req.form = {"vid": "esearch", "es_escategory": "archives"}
            ctx = _template_context(req, "esearch")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "events": (
                    ("isearchengine", "main_search"),
                    ("isearchresults", "0"),
                    ("isearchkey", "category"),
                    ("isearchdata", "archives"),
                ),
                "page": {"pagegroup": "search", "path": "/search/inventaires"},
            }
            self.assertDictEqual(ctx["tracking"], expected)

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_global_search_service(self, _search):
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="cat", short_name="AD Vaucluse", code="FRAD084"
            )
            cnx.commit()
        path = f"inventaires/{service.code}"
        with self.admin_access.web_request(path) as req:
            req.form = {
                "vid": "esearch",
                "es_escategory": "archives",
                "es_publisher": service.eid,
                "inventory": True,
            }
            ctx = _template_context(req, "esearch")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "events": (
                    ("isearchengine", "main_search"),
                    ("isearchresults", "0"),
                    ("isearchkey", "category"),
                    ("isearchdata", "archives"),
                    ("isearchkey", "service"),
                    ("isearchdata", "frad084"),
                ),
                "page": {"pagegroup": "search", "path": "/search/inventaires/frad084"},
            }
            from pprint import pprint

            pprint(ctx["tracking"])
            self.assertDictEqual(ctx["tracking"], expected)

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_gloabal_search_publisher_eid(self, _search):
        """Search AD Vaucluse IR

        Trying: use service eid as `es_publisher` param value (new style)

        Expecting: service short name is found
        """
        with self.admin_access.cnx() as cnx:
            service = cnx.create_entity(
                "Service", category="cat", short_name="AD Vaucluse", code="FRAD084"
            )
            cnx.commit()
        path = f"search?es_escategory=archives&es_escategory=siteres&es_publisher={service.eid}"
        with self.admin_access.web_request(path) as req:
            req.form = {"es_escategory": ["archives", "siteres"], "es_publisher": f"{service.eid}"}
            ctx = _template_context(req, "esearch")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "events": (
                    ("isearchengine", "main_search"),
                    ("isearchresults", "0"),
                    ("isearchkey", "category"),
                    ("isearchdata", "archives,siteres"),
                    ("isearchkey", "publishers_facet"),
                    ("isearchdata", "ad_vaucluse"),
                ),
                "page": {"pagegroup": "search", "path": "/search"},
            }
            from pprint import pprint

            pprint(ctx["tracking"])
            self.assertDictEqual(ctx["tracking"], expected)

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_nomina_search_no_params(self, _search):
        with self.admin_access.web_request("basedenoms") as req:
            ctx = _template_context(req, "nominarecords")
            self.assertDictEqual(
                ctx["tracking"],
                {
                    "additional": {},
                    "domain": "sr.fa",
                    "events": (
                        ("isearchengine", "namebase_search"),
                        ("isearchresults", "0"),
                    ),
                    "page": {"pagegroup": "search", "path": "/nominarecords/search"},
                },
            )

    @patch(
        "cubicweb_francearchives.views.search.PniaElasticSearchView.do_search",
        return_value=FakeResponse(),
    )
    def test_nomina_search_with_params(self, _search):
        path = "basedenoms?es_names=AMIOT&es_forenames=&es_locations=Paris&fulltext_facet="
        with self.admin_access.web_request(path) as req:
            req.form = {
                "es_forenames": "",
                "es_locations": "Paris",
                "es_names": "AMIOT",
                "fulltext_facet": "",
            }
            ctx = _template_context(req, "nominarecords")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "page": {"pagegroup": "search", "path": "/nominarecords/search"},
                "events": (
                    ("isearchengine", "namebase_search"),
                    ("isearchresults", "0"),
                    ("isearchkey", "locations"),
                    ("isearchdata", "paris"),
                    ("isearchkey", "names"),
                    ("isearchdata", "amiot"),
                ),
            }
            self.assertDictEqual(ctx["tracking"], expected)

    @patch(
        "cubicweb_francearchives.views.search.authorities.PniaAuthoritiesElasticSearchView.do_search",  # noqa
        return_value=FakeResponse(),
    )
    def test_qualified_agent_authorities_search(self, _search):
        path = "/agents?let=a"
        with self.admin_access.web_request(path) as req:
            req.form = {"let": "a"}
            ctx = _template_context(req, "agents")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "page": {"pagegroup": "search", "path": "/authorities/search/agents"},
                "events": (
                    ("isearchengine", "agents_search"),
                    ("isearchresults", "0"),
                    ("isearchkey", "starts_with"),
                    ("isearchdata", "a"),
                ),
            }
            self.assertDictEqual(ctx["tracking"], expected)

    @patch(
        "cubicweb_francearchives.views.search.authorities.PniaAuthoritiesElasticSearchView.do_search",  # noqa
        return_value=FakeResponse(),
    )
    def test_qualified_location_authorities_search(self, _search):
        path = "/locations?let=d&fulltext_facet=dachau#/"
        with self.admin_access.web_request(path) as req:
            req.form = {"let": "d", "fulltext_facet": "dachau"}
            ctx = _template_context(req, "locations")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "page": {"pagegroup": "search", "path": "/authorities/search/locations"},
                "events": (
                    ("isearchengine", "locations_search"),
                    ("isearchresults", "0"),
                    ("isearchkey", "starts_with"),
                    ("isearchdata", "d"),
                    ("isearchkey", "contains"),
                    ("isearchdata", "dachau"),
                ),
            }
            self.assertDictEqual(ctx["tracking"], expected)

    @patch(
        "cubicweb_francearchives.views.search.authorities.PniaAuthoritiesElasticSearchView.do_search",  # noqa
        return_value=FakeResponse(),
    )
    def test_qualified_subject_authorities_search(self, _search):
        path = "/subjects"
        with self.admin_access.web_request(path) as req:
            ctx = _template_context(req, "subjects")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "page": {"pagegroup": "search", "path": "/authorities/search/subjects"},
                "events": (
                    ("isearchengine", "subjects_search"),
                    ("isearchresults", "0"),
                ),
            }
            self.assertDictEqual(ctx["tracking"], expected)

    def test_no_department_map_chapters(self):
        with self.admin_access.web_request() as req:
            ctx = _template_context(req, "dpt-service-map")
            expected = {
                "additional": {},
                "domain": "sr.fa",
                "page": {"pagegroup": "department_map", "path": "/department_map"},
                "events": [],
            }
            self.assertDictEqual(ctx["tracking"], expected)


class ViewsNoEulerianTests(S3BfssStorageTestMixin, PniaWebCWTC):
    """test suite to make sure no eulerian markup is added when not configured"""

    def test_404(self):
        with self.admin_access.web_request() as req:
            ctx = _template_context(req, "404")
            self.assertNotIn("tracking", ctx)


if __name__ == "__main__":
    unittest.main()
