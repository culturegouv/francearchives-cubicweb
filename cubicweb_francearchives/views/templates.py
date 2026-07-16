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

"""pnia_content views/templates"""

from collections import defaultdict
import hashlib

from logilab.common.decorators import monkeypatch, cachedproperty
from logilab.mtconverter import xml_escape

from cubicweb.utils import json_dumps
from cubicweb.uilib import remove_html_tags

from cubicweb_web.views import basetemplates
from cubicweb_web.utils import HTMLStream, HTMLHead

from cubicweb_francearchives import (
    FEATURE_ADVANCED_SEARCH,
    FEATURE_SPARQL_ACCESSIBLE,
    SITE_TYPE,
)
from cubicweb_francearchives.redis_utils import get_data_with_cache
from cubicweb_francearchives.utils import build_faq_url, find_card

from cubicweb_francearchives.entities import (
    entity2schemaorg,
    entity2meta,
    entity2opengraph,
)
from cubicweb_francearchives.entities.cms import get_ancestors
from cubicweb_francearchives.views import (
    JinjaViewMixin,
    get_top_sections_infos,
    get_template,
    load_portal_config,
)
from cubicweb_francearchives.views.eulerian import EulerianViewsAdapter

# HACK: bypass HTMLStream doctype / head generation: they're managed
# directly by our jinja templates. We only need the body
HTMLStream.getvalue = lambda self: self.body.getvalue()


@monkeypatch(HTMLHead)
def add_onload(self, jscode):
    """original `add_onload` implementation use `$(cw)`
    but `cw` variable is not available
    in francearchive, use `$` instead"""
    self.add_post_inline_script(
        """$(function() {
  %s
});"""
        % jscode
    )


def picklabel(labels, lang):
    return labels.get(lang) or labels.get("fr")


def get_site_links(cnx):
    query = """ Any X, C, U, LF, LE, LS, LD, O ORDERBY C, O WHERE
    X is SiteLink, X link U, X order O,
    X label_fr LF, X label_en LE,  X label_es LS, X label_de LD,
    X context C
    """
    rset = cnx.execute(query)
    links = defaultdict(list)
    for eid, context, link, lf, le, ls, ld, order in rset:
        hide = True if link in ("annuaire/departements") else False
        link = link if link.startswith("http") else f"%(base_url)s{link}"
        links[context].append(
            {
                "url": link,
                "hide": hide,
                "labels": {"fr": lf, "en": le or lf, "es": ls or lf, "de": ld or lf},
            }
        )
    return links


def get_search_faqs(cnx):
    category = "02_faq_search"
    query = f"""Any X, Q, A ORDERBY O WHERE X is FaqItem,
    X question Q, X answer A,
    X order O, X category '{category}'"""
    rset = cnx.execute(query)
    if rset:
        faqs = [
            (
                eid,
                cnx.build_url(f"faqitem/{eid}"),
                remove_html_tags(question),
                answer,
            )
            for eid, question, answer in rset
        ]
        return {
            "faqs": faqs,
            "category": category,
            "faq_url": cnx.build_url("faq"),
            "faq_label": cnx._("See all FAQs"),
        }
    return {}


class PniaMainTemplate(JinjaViewMixin, basetemplates.TheMainTemplate):
    template = get_template("maintemplate.jinja2")

    def _handle_added_resources(self, tmpl_context):
        """fetch all resources added with add_{js,css}, etc.

        and backport them into ``tmpl_context`` to feed the main jinja template
        """
        # handle define_var() calls
        var_stmts = [
            (var, json_dumps(value)) for var, value, override in self._cw.html_headers.jsvars
        ]
        tmpl_context["js_vars"] = var_stmts
        # handle add_js() calls
        current_jsfiles = tmpl_context["jsfiles"]
        for jsfile in self._cw.html_headers.jsfiles:
            if jsfile["src"] not in current_jsfiles:
                current_jsfiles.append(jsfile["src"])
        # handle add_onload() calls
        tmpl_context["inline_scripts"] = self._cw.html_headers.post_inlined_scripts
        # handle add_css() calls
        current_cssfiles = tmpl_context["cssfiles"]
        for cssfile, media in self._cw.html_headers.cssfiles:
            if cssfile not in current_cssfiles:
                current_cssfiles.append(cssfile)

    def call(self, view):
        self.set_request_content_type()
        self._cw.html_headers.define_var("BASE_URL", self._cw.build_url(""))
        self._cw.html_headers.define_var("DATA_URL", self._cw.datadir_url)
        context = self.template_context(view)
        page_content = view.render()
        context.update(getattr(view, "template_context", lambda: {})())
        self._handle_added_resources(context)
        context["page_content"] = page_content
        self.call_template(**context)

    @cachedproperty
    def portal_config(self):
        return load_portal_config(self._cw.vreg.config)

    @cachedproperty
    def site_links(self):
        return get_site_links(self._cw)

    def sn_data(self):
        sn_data = self.portal_config.get("sn", {})
        if not sn_data:
            self.error('could not find "sn" section in portal config')
        return sn_data

    def footer_sections(self):
        links = []
        section_links = self.site_links.get("footer_ministries", [])
        if section_links:
            links.append(
                {
                    "labels": {"fr": self._cw._("Interministerial portal")},
                    "links": section_links,
                }
            )
        for section in (
            "footer_public_sites",
            "footer_archives_sites",
            "footer_search_notebooks",
            "footer_usefull_links",
            "footer_links_directories",
        ):
            section_links = self.site_links.get(section, [])
            if section_links:
                links.append(
                    {
                        "labels": {"fr": self._cw._(section.split("footer_")[1])},
                        "links": section_links,
                    }
                )
        return links

    def footer_links(self):
        return self.site_links.get("footer_links", [])

    def mission_link(self, is_nomina=False):
        link = self.site_links.get("foundout_link")
        if not link:
            return

        if is_nomina:
            return link[1] if len(link) == 2 else None

        return link[0]

    def display_top_button(self, view):
        if getattr(view, "notop", False):
            return False
        return True

    def view_entity(self, view):
        if self.cw_rset and len(self.cw_rset) == 1:
            return self.cw_rset.one()
        if hasattr(view, "entity"):
            # see NominaPrimaryView
            return view.entity

    @cachedproperty
    def search_faqs(self):
        return get_data_with_cache(self._cw, f"search_faqs_{self._cw.lang}", get_search_faqs)

    def alert(self):
        alert = find_card(self._cw, "alert")
        if alert is not None and alert.content.strip():
            cssclass = alert.synopsis if alert.synopsis else "fr-alert--warning"
            return {
                "content": alert.content,
                "title": alert.title,
                "class": cssclass.strip(),
                "hash": hashlib.sha1(alert.content.encode("utf8")).hexdigest(),
            }

    def get_page_id(self, view):
        if view and view.__regid__ == "index":
            return "homepage"

        if view and view.__regid__ == "nomina-home":
            return "homepage"
        return "page"

    def get_base_search_route(self, view):
        base_search_route = "basedenoms"
        if not view:
            base_search_route = ""
        elif view.__regid__ == "index":
            base_search_route = ""
        elif view.__regid__ == "nominacensusrecord":
            base_search_route = f"{base_search_route}_recensement"
        elif view.__regid__ == "nominamilitaryrecord":
            base_search_route = f"{base_search_route}_militaire"
        elif view.__regid__ == "nominacivilstatusrecord":
            base_search_route = f"{base_search_route}_etat_civil"
        return base_search_route

    def template_context(self, view):
        archives_choice = {
            "label": self._cw._("###in archives###"),
            "info": self._cw._("archives_search_info"),
        }
        siteres_choice = {
            "label": self._cw._("###site resources###"),
            "info": self._cw._("siteres_search_info"),
        }
        lang = self._cw.lang

        entity = self.view_entity(view)
        if entity:
            parents = [entity.eid] + get_ancestors(entity)
        else:
            parents = []
        if getattr(view, "faq_category", None):
            faqs = view.faqs_attrs()
        else:
            faqs = None
        is_nomina = getattr(view, "is_nomina", False)
        ctx = {
            "_": self._cw._,
            "title": view.page_title(),
            "lang": lang,
            "picklabel": picklabel,
            "base_url": self._cw.build_url("").rstrip("/"),
            "data_url": self._cw.datadir_url,
            "page_url": xml_escape(self._cw.url()),
            "parents": parents,
            "search_info_url": build_faq_url(self._cw, "02_faq_search"),
            "archives_choice": archives_choice,
            "siteres_choice": siteres_choice,
            "advanced_search_url": self._cw.build_url("advancedSearch"),
            "cssfiles": self._cw.uiprops["STYLESHEETS"][:],
            "jsfiles": self._cw.uiprops["PNIA_JAVASCRIPTS"][:],
            "mission_link": self.mission_link(is_nomina),
            "page_id": self.get_page_id(view),
            "is_nomina": is_nomina,
            "topsections": get_top_sections_infos(self._cw),
            "sn": self.sn_data(),
            "cms": self._cw.vreg.config.get("instance-type") == "cms",
            "footer": {
                "sections": self.footer_sections(),
                "footer_links": self.footer_links(),
            },
            "query": self._cw.form.get("q", ""),
            "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            "display_sparql_search": FEATURE_SPARQL_ACCESSIBLE,
            "display_professional_access": True,
            "display_search_bar": True,
            "display_advanced_search": FEATURE_ADVANCED_SEARCH,
            "tac_domain": self._cw.vreg.config.get("tac_domain"),
            "tac_uuid": self._cw.vreg.config.get("tac_uuid"),
            "search_faqs": self.search_faqs,
            "faqs": faqs,
            "alert": self.alert(),
            "is_production": 1 if SITE_TYPE == "production" else 0,
            "noreact": getattr(view, "noreact", True),
            "base_search_route": self.get_base_search_route(view),
        }
        # XXX fix breadcrumbs implementation (listview, etc.) later
        breadcrumbs = []
        eulerian_adapter = getattr(view, "eulerian_tag", False)
        if eulerian_adapter:
            eulerian_adapter = EulerianViewsAdapter(self._cw, view)
        if entity:
            ibc = entity.cw_adapt_to("IBreadCrumbs")
            if ibc is not None:
                for bc_element in ibc.breadcrumbs():
                    if isinstance(bc_element, (list, tuple)):
                        breadcrumbs.append(bc_element)
                    elif isinstance(bc_element, str):
                        breadcrumbs.append((None, bc_element))
                    else:
                        if len(ibc.breadcrumbs()) == 1:
                            breadcrumbs.extend(
                                (
                                    (self._cw.build_url(""), self._cw._("Home")),
                                    (bc_element.absolute_url(), bc_element.dc_title()),
                                )
                            )
                        else:
                            breadcrumbs.append((bc_element.absolute_url(), bc_element.dc_title()))
                ctx["breadcrumbs"] = breadcrumbs
            graph = entity2schemaorg(entity)
            if graph is not None:
                ctx["jsonld_graph"] = graph
            ctx["meta"] = entity2meta(entity)
            ctx["open_graph"] = entity2opengraph(entity)
            # if the view explicitly defines some chapters, use them
            # otherwise we would have no way to distinguish chapters for
            # primary and other views for a single entity (e.g. commemo index)
            if not eulerian_adapter:
                eulerian_adapter = entity.cw_adapt_to("IEulerian")
        elif hasattr(view, "breadcrumbs"):
            ctx["breadcrumbs"] = view.breadcrumbs
        eulerian_domain = self._cw.vreg.config.get("eulerian_domain")
        if eulerian_domain and eulerian_adapter:  # cms shouldn't have eulerian config
            page = {
                "path": eulerian_adapter.path,
                "pagegroup": eulerian_adapter.pagegroup,
                "pagelabel": eulerian_adapter.pagelabel,
            }
            ctx["tracking"] = {
                "domain": eulerian_domain,
                "page": {k: v for k, v in page.items() if v},
                "events": eulerian_adapter.events,
                "additional": eulerian_adapter.additional,
            }
        langswitch_comp = self._cw.vreg["components"].select(
            "pnia.langswitch.component", self._cw, rset=self.cw_rset
        )
        ctx["langswitch"] = list(langswitch_comp.lang_urls())
        return ctx


def registration_callback(vreg):
    vreg.register_and_replace(PniaMainTemplate, basetemplates.TheMainTemplate)
