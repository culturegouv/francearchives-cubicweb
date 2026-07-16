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

from collections import defaultdict, OrderedDict
from os import path as osp
from sys import getsizeof

from cubicweb_elasticsearch.es import get_connection

from cwtags import tag as T
from elasticsearch_dsl.query import Q, Bool
from elasticsearch_dsl.search import Search

from urllib.parse import urlsplit

from logilab.mtconverter import xml_escape
from logilab.common.decorators import cachedproperty
from logilab.common.registry import objectify_predicate

from cubicweb import _
from cubicweb.predicates import is_instance, score_entity, relation_possible

from cubicweb.schema import display_name

from cubicweb_web import NotFound
from cubicweb_web.views.primary import PrimaryView, URLAttributeView
from cubicweb_web.view import View, EntityView, StartupView
from cubicweb_web.views.baseviews import InContextView
from cubicweb_web.views.idownloadable import DownloadView, BINARY_ENCODINGS
from cubicweb.uilib import cut, remove_html_tags


from cubicweb_francearchives import SUPPORTED_LANGS, FEATURE_CHATBOT_SECTIONS
from cubicweb_card.views import CardPrimaryView
from cubicweb_francearchives.entities.nomina import initialize_nominarecord_entity
from cubicweb_francearchives.entities.rdf import RDF_FORMAT_EXTENSIONS
from cubicweb_francearchives.views import (
    JinjaViewMixin,
    add_js_translations,
    get_template,
    exturl_link,
    blank_link_title,
)

from cubicweb_francearchives.views.service import DeptMapForm, all_services
from cubicweb_francearchives.entities.cms import section
from cubicweb_francearchives.views import FaqMixin
from cubicweb_francearchives.utils import (
    find_card,
    format_date,
    format_number,
    formatted_size,
    is_external_link,
    number_of_archives,
    get_hp_articles,
    get_key_figures,
    get_key_figures_card,
    title_for_link,
)
from cubicweb_francearchives.xmlutils import get_broken_editorial_links


class UtilsMixin:
    @property
    def editable(self):
        return not self._cw.session.anonymous_session

    def check_content(self, entity):
        data = None
        if self.editable:
            uri = self._cw.url()
            schema, netloc, path, query, fragment = urlsplit(uri)
            if not query.startswith("check_links"):
                return data
            data = {self._cw._("Broken links"): self.check_broken_links(entity)}
        return data

    def check_broken_links(self, entity):
        data = []
        subjrels = self._cw.vreg.schema.entity_schema_for(entity.cw_etype).subject_relations
        for rel in subjrels:
            if "_format" not in rel.type:
                continue
            attr = rel.type.split("_format")[0]
            text_format = getattr(entity, str(rel.type))
            if text_format == "text/html":
                get_broken_editorial_links(getattr(entity, attr), self._cw, data=data)
        if data:
            msg = self._cw._("Some links bellow seem to be broken. Please check them.")
        else:
            msg = self._cw._("No broken links where detected.")
        return {"msg": msg, "errors": data}


class WebChatShareLinksMixin:
    def display_chatbot(self, entity):
        return str(entity.eid) in (FEATURE_CHATBOT_SECTIONS)

    def add_webchat_js(self, entity):
        if self.display_chatbot(entity):
            self._cw.add_js("bundle-pnia-webchat.js")
            self._cw.add_js("https://webchat.wikit.ai/webchat-embed.js", localfile=False)


class ShareLinksMixin:
    def sharelinks(self, url):
        return {
            "mail": f"mailto:?subject=&body={url}",
            "title": _("Share the page"),
            "copyurl": url,
            "_": self._cw._,
        }


class SitemapView(View, JinjaViewMixin):
    __regid__ = "sitemap"
    title = _("Plan du site")
    template = get_template("sitemap.jinja2")
    eulerian_tag = True
    eulerian_pagegroup = "sitemap"
    display_documents = False

    @property
    def breadcrumbs(self):
        return [
            (self._cw.build_url(""), self._cw._("Home")),
            (self._cw.build_url("glossary"), self._cw._(self.title)),
        ]

    def get_roots_rset(self):
        cnx = self._cw
        return cnx.execute(
            "Any S, T ORDERBY O WHERE S is Section, NOT EXISTS(X children S), S title T, S order O"
        )

    def global_links(self):
        req = self._cw
        sections = []
        for label, url in (
            (_("All the referenced archives"), "inventaires"),
            (_("All site contents"), "search?q=&es_escategory=siteres"),
            (_("Names database"), "basedenoms"),
            (_("Quality locations"), "locations"),
            (_("Quality persons/organizations"), "agents"),
            (_("Quality themes"), "subjects"),
            (_("Service Directory"), "services"),
            (_("Circulars"), "circulaires"),
            (_("Record creators"), "authorityrecord"),
        ):
            sections.append(
                {
                    "title": req._(label),
                    "etype": "Link",
                    "url": req.build_url(url),
                    "children": None,
                }
            )
        return sections

    def call(self, **kw):
        req = self._cw
        # add direct links
        _ = req._
        sections = self.global_links()
        roots = self.get_roots_rset()
        for idx, sect in enumerate(roots.entities()):
            sections.append(
                dict(
                    url=xml_escape(sect.absolute_url()),
                    etype="Section",
                    title=sect.title,
                    children=section.get_children(
                        req, sect.eid, only_sections=not self.display_documents
                    ),
                    lang=self._cw.lang,
                )
            )
        self.call_template(title=req._(self.title), sections=sections, _=_)


class SectionMixin:

    def get_section_info(self, entity):
        images = entity.section_image
        return {
            "entity": entity.cw_adapt_to("ITemplatable").entity_param(),
            "image": images[0] if images else None,
            "errors": self.check_content(entity),
            "_": self._cw._,
        }


def get_subsections(data):
    return [
        {
            "eid": s["eid"],
            "url": s["url"],
            "title": s["title"],
            "description": s["short_description"],
        }
        for s in data
        if s["etype"] == "Section"
    ]


class SectionTreeView(EntityView, UtilsMixin, SectionMixin, WebChatShareLinksMixin, JinjaViewMixin):
    __regid__ = "section-tree"
    template = get_template("section-tree.jinja2")

    def get_content_for_tree(self, entity):
        tree = entity.cw_adapt_to("ISectionTree")
        if tree:
            return tree.retrieve_subsections(section_mode="mode_tree")
        return []

    def cell_call(self, row, col):

        entity = self.cw_rset.get_entity(row, col)
        self.add_webchat_js(entity)
        data = self.get_content_for_tree(entity) if entity.display_tree else None
        ctx = self.get_section_info(entity)
        ctx.update(
            {
                "sections": data,
                "subsections": get_subsections(data),
                "lang": self._cw.lang,
            }
        )
        return self.call_template(**ctx)


class SectionThemesView(EntityView, WebChatShareLinksMixin, JinjaViewMixin):
    __regid__ = "section-themes"
    template = get_template("section-themes.jinja2")

    def cell_call(self, row, col, themes):
        entity = self.cw_rset.get_entity(row, col)
        self.add_webchat_js(entity)
        return self.call_template(
            entities=themes,
            _=self._cw._,
        )


class SectionInfoView(UtilsMixin, WebChatShareLinksMixin, EntityView, JinjaViewMixin):
    __regid__ = "section-info"
    template = get_template("section-info.jinja2")
    __select__ = EntityView.__select__ & is_instance("Section")

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        self.add_webchat_js(entity)
        errors = self.check_content(entity)
        return self.call_template(
            self.w,
            entity=entity.cw_adapt_to("ITemplatable").entity_param(),
            img_src=entity.illustration_url,
            img_alt=entity.illustration_alt,
            errors=errors,
            _=self._cw._,
        )


class SectionPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Section")

    def entity_call(self, entity, **kw):
        display_mode = entity.display_mode
        self.w(entity.view("section-tranlsations"))
        if display_mode != "mode_tree":
            self.w(entity.view("section-info"))
            # display results results for default and themes mode
            self._cw.form["ancestors"] = str(entity.eid)
            self._cw.form.pop("rql", None)  # remove rql form param which comes from url_rewriter
            path = [entity.eid]
            parents = entity.reverse_children
            while parents:
                parent = parents[0]
                path.append(parent.eid)
                parents = parent.reverse_children
            self.wview(
                "esearch",
                context={
                    "section": entity,
                    "path": list(reversed(path)),
                },
            )
        else:
            self.w(entity.view("section-tree"))


class SectionTranslationToolView(EntityView, JinjaViewMixin):
    __regid__ = "section-tranlsations"
    template = get_template("section-translations.jinja2")
    __select__ = EntityView.__select__ & is_instance("Section")

    def call_template(self, w, **ctx):
        w(self.template.render(**ctx))

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        return self.call_template(
            self.w,
            i18n_links=entity.i18n_links(),
            _=self._cw._,
        )


class IIIFViewersMixin(StartupView, JinjaViewMixin):
    bundle_js = None

    def call(self, **kwargs):
        if self.bundle_js:
            self._cw.add_js(self.bundle_js)
        return self.call_template(**self.template_context())

    def template_context(self):
        return {
            "_": self._cw._,
            "data_url": self._cw.datadir_url,
            "lang": self._cw.lang,
            "pagetitle": self._cw._(self.title),
            "iiif_manifest": self._cw.form.get("manifest", ""),
        }


class MiradorEmbedPageView(IIIFViewersMixin):
    __regid__ = "mirador"
    template = get_template("mirador.jinja2")
    title = _("Mirador Viewer")


class UniversalViewerEmbedPageView(IIIFViewersMixin):
    __regid__ = "universalviewer"
    template = get_template("universalviewer.jinja2")
    bundle_js = "bundle-pnia-universalviewer.js"
    title = _("Universal Viewer")


@objectify_predicate
def is_gerer_section(cls, req, rset, row=0, col=0, **kwargs):
    return rset.get_entity(0, 0).name == "gerer"


class GererPrimaryView(SectionPrimaryView, JinjaViewMixin):
    __select__ = SectionPrimaryView.__select__ & is_gerer_section()
    template = get_template("homepage_archivists.jinja2")

    def page_title(self):
        entity = self._cw.execute("Any X WHERE X is Section, X name 'gerer'").one()
        entity = entity.cw_adapt_to("ITemplatable").entity_param()
        return f'{entity.title} ({self._cw.property_value("ui.site-title")})'

    def retrieve_quick_access(self):
        """TODO add Picto in link definition"""
        pictos = {
            "circulaires": "SIGN_DOC_PICTO",
            "services": "CITY_PICTO",
            "authorityrecord": "DOC_PICTO",
        }
        links = []
        for link, title in self._cw.execute(
            """ Any L, T ORDERBY O WHERE
                X is SiteLink, X context "archiviste_hp_links",
                X order O, X link L,
                X label_{lang} T""".format(
                lang=self._cw.lang
            )
        ):
            url = link if link.startswith("http") else self._cw.build_url(link)
            picto = self._cw.uiprops[pictos.get(link, "SEARCH_PICTO")]
            links.append((url, title, picto, is_external_link(url, self._cw.base_url())))
        return links

    def template_context(self):
        return {"display_professional_access": False}

    def entity_call(self, entity, **kw):
        self._cw.add_js("bundle-pnia-archivists.js")
        self._cw.form["ancestors"] = str(entity.eid)
        self._cw.form.pop("rql", None)  # remove rql form param which comes from url_rewriter
        _ = self._cw._
        news_url = self._cw.build_url(
            "search", **{"ancestors": entity.eid, "es_cw_etype": "NewsContent"}
        )
        archives = format_number(number_of_archives(self._cw), self._cw)
        tree = entity.cw_adapt_to("ISectionTree")
        sections = tree.retrieve_subsections()
        attrs = {
            "_": _,
            "req": self._cw,
            "sections": sections,
            "subsections": get_subsections(sections),
            "quick_links": self.retrieve_quick_access(),
            "news_url": news_url,
            "archives_url": self._cw.build_url("inventaires"),
            "archives_number_label": _("See {} archives").format(archives),
            "related_entities": get_hp_articles(self._cw, "onhp_arch"),
            "data_url": self._cw.datadir_url,
            "figures": get_key_figures(self._cw),
        }
        attrs.update(get_key_figures_card(self._cw))
        self.call_template(**attrs)


class ContentPrimaryView(UtilsMixin, PrimaryView, JinjaViewMixin):
    __abstract__ = True
    template = None
    needs_css = ()
    needs_js = ("bundle-glossary.js",)

    def add_css(self):
        for css in self.needs_css:
            self._cw.add_css(css)

    def add_js(self):
        for js in self.needs_js:
            self._cw.add_js(js)

    def template_attrs(self, entity):
        errors = self.check_content(entity)
        return {
            "entity": entity.cw_adapt_to("ITemplatable").entity_param(),
            "errors": errors,
            "lang": self._cw.lang,
            "_": self._cw._,
        }

    def entity_call(self, entity, **kw):
        self.add_css()
        self.add_js()
        self.render_content(entity)

    def render_content(self, entity):
        self.call_template(**self.template_attrs(entity))


class RecentDataPrimaryView(ShareLinksMixin, ContentPrimaryView):
    __abstract__ = True
    needs_js = ("bundle-glossary.js",)
    template = get_template("article.jinja2")
    recent_label = _("Similar documents")

    def indexes_props(self, entity):
        return []

    def template_attrs(self, entity):
        attrs = super(RecentDataPrimaryView, self).template_attrs(entity)
        attrs["data_url"] = self._cw.data_url("/").rstrip("/")
        main_attrs = self.main_attrs(entity)
        recents = []
        for related in self.related_content(entity):
            related = related.cw_adapt_to("ITemplatable").entity_param()
            title = related.title
            recents.append(
                {
                    "url": related.absolute_url(),
                    "header": related.abstract,
                    "link_title": title_for_link(title),
                    "etype": self._cw._(getattr(related, "etype", related.cw_etype)),
                    "dates": self.entity_date(related),
                    "image": related.image,
                    "default_picto_srcs": self._cw.uiprops["DOCUMENT_IMG"],
                    "lang_attr": f'lang="{related.lang}"' if related.lang != self._cw.lang else "",
                }
            )
        if recents:
            attrs["related_entities"] = recents
        attrs.update(main_attrs)
        attrs.update(
            {
                "sharelinks_data": self.sharelinks(entity.absolute_url()),
                "metadata": self.metadata(entity),
                "indexes": self.indexes_props(entity),
            }
        )
        return attrs

    def entity_date(self, entity):
        return format_date(entity.modification_date, self._cw, fmt="d MMMM y")

    def metadata(self, entity):
        metadata = ((_("Last update on"), self.entity_date(entity)),)
        return [entry for entry in metadata if entry[-1]]

    def main_attrs(self, entity):
        _ = self._cw._
        images = self.entity_images(entity)
        return {
            "_": _,
            "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
            "image": images[0] if images else None,
            "recent_label": _(self.recent_label),
            "all_links": {
                "url": self._cw.build_url(self.all_link_url),
                "label": _(self.all_link_label),
            },
            "eulerian": entity.cw_adapt_to("IEulerian").actions,
        }

    def related_content(self, entity):
        # if entity has an explicit relation towards related_content_suggestion
        # send the objects of this relation
        if entity.related_content_suggestion:
            related_content = entity.related_content_suggestion
            if len(related_content) >= 3:
                return related_content[0:3]
            else:
                return related_content

        # else if this entity is the object of a relation_content_suggestion
        # send the subjects of these relations
        if entity.reverse_related_content_suggestion:
            related_content = entity.reverse_related_content_suggestion
            if len(related_content) >= 3:
                return related_content[0:3]
            else:
                return related_content

        related_subjects = self._cw.execute(
            "Any A WHERE X eid %(eid)s, X related_authority A, A is SubjectAuthority",
            {"eid": entity.eid},
        ).rows
        # else if this entity has no subject, return no related content
        if len(related_subjects) == 0:
            return []

        # else, retrieve automatic suggestions only if entity has subjects
        # Query more like this based on authority eid
        es = get_connection(self._cw.vreg.config)
        if not es:
            self._cw.error("[related_content]: no elastisearch connection available")
            return []
        index_name = self._cw.vreg.config["index-name"]
        search = Search(index="{}_all".format(index_name))

        # "must" condition to ensure that related content are of the right types
        related_content_etypes = [
            "BaseContent",
            "ExternRef",
            "CommemorationItem",
        ]
        etypes_clauses = []
        for etype in related_content_etypes:
            etypes_clauses.append(Q("term", estype=etype))
        must_etypes = Bool(should=etypes_clauses, minimum_should_match=1)

        # "should" condition to select similar entities based on subjects indexes
        should = []
        for subject in related_subjects:
            should.append(Q({"term": {"index_entries.authority": subject[0]}}))
        # do not include same document in results
        same_document = [Q("term", eid=entity.eid)]
        search.query = Bool(should=should, minimum_should_match=1)
        search = search.filter(Bool(must=must_etypes, must_not=same_document))
        search = search[0:3]
        search = search.source(["eid"])  # only return eids

        response = search.execute()
        related_content = []
        for hit in response:
            try:
                related = self._cw.entity_from_eid(hit["eid"])
            except Exception:
                self._cw.error(f'[related_content]: entity {hit["eid"]} not found')
                continue
            related_content.append(related)

        return related_content


class RelatedAutorityIndexablePrimaryMixIn:
    def authority_props(self, entity):
        _ = self._cw._
        main_props = []
        # indexes
        main_props.append(
            (
                _("persname_index_label"),
                ", ".join(e.view("incontext") for e in entity.main_indexes(None).entities()),
            )
        )
        main_props.append(
            (
                _("subject_indexes_label"),
                ", ".join(e.view("incontext") for e in entity.subject_indexes().entities()),
            )
        )
        main_props.append(
            (
                _("geo_indexes_label"),
                ", ".join(e.view("incontext") for e in entity.geo_indexes().entities()),
            )
        )
        return [entry for entry in main_props if entry[-1]]

    def indexes_props(self, entity):
        _ = self._cw._
        indexes_props = []
        # indexes
        for label, itype, rset in (
            (_("Persons/organizations"), "agent", entity.main_indexes(None)),
            (_("Themes"), "subject", entity.subject_indexes()),
            (_("Locations"), "location", entity.geo_indexes()),
        ):
            if rset:
                indexes_props.append(
                    (label, [(self._cw.build_url(f"{itype}/{row[0]}"), row[1]) for row in rset])
                )
        return indexes_props


class BaseContentPrimaryView(
    FaqMixin, RelatedAutorityIndexablePrimaryMixIn, WebChatShareLinksMixin, RecentDataPrimaryView
):
    __select__ = RecentDataPrimaryView.__select__ & is_instance("BaseContent")
    all_link_url = "articles"
    all_link_label = _("See all articles")

    def main_props(self, entity):
        main_props = self.authority_props(entity)
        service = entity.basecontent_service
        if service:
            main_props.insert(
                0, (self._cw._("service_label"), ", ".join(e.view("incontext") for e in service))
            )
        return main_props

    def display_chatbot(self, entity):
        parents = set([str(e.eid) for e in entity.reverse_children])
        return parents.intersection(FEATURE_CHATBOT_SECTIONS)

    def entity_call(self, entity):
        self._cw.add_js("bundle-pnia-articles.js")
        self.add_webchat_js(entity)
        super(BaseContentPrimaryView, self).entity_call(entity)

    @cachedproperty
    def faq_category(self):
        entity = self.cw_rset.complete_entity(self.cw_row or 0, self.cw_col or 0)
        return entity.cw_adapt_to("IFaq").faq_category

    def template_attrs(self, entity):
        """Build the dictionary for the jinja template by
        merging all required data from the BaseContent entity"""
        attrs = super(BaseContentPrimaryView, self).template_attrs(entity)
        attrs.update(
            {
                "faqs": self.faqs_attrs(),
                "main_props": self.main_props(entity),
                "i18n_links": entity.i18n_links(),
            }
        )
        services = entity.basecontent_service
        if services:
            _ = self._cw._
            label = _("Service_plural") if len(services) > 1 else _("Service")
            attrs["services"] = [label, [(e.absolute_url(), e.dc_title()) for e in services]]
        return attrs

    def entity_images(self, entity):
        return entity.basecontent_image


class NewsContentPrimaryView(RecentDataPrimaryView):
    __select__ = RecentDataPrimaryView.__select__ & is_instance("NewsContent")
    all_link_url = "actualites"
    all_link_label = _("See all news")
    recent_label = _("###Recent News###")

    def related_content(self, entity):
        return self._cw.execute(
            """Any X ORDERBY X DESC LIMIT 3
               WHERE X is NewsContent,
               NOT X identity S, S eid %(e)s""",
            {"e": entity.eid},
        ).entities()

    def entity_images(self, entity):
        return entity.news_image


class CommemorationItemPrimaryView(RelatedAutorityIndexablePrimaryMixIn, RecentDataPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("CommemorationItem")
    all_link_url = "pages_histoire"
    all_link_label = _("See all commemorations")

    def main_props(self, entity):
        main_props = self.authority_props(entity)
        return main_props

    def template_attrs(self, entity):
        attrs = super(CommemorationItemPrimaryView, self).template_attrs(entity)
        attrs.update(
            {
                "main_props": self.main_props(entity),
                "default_picto_src": self._cw.uiprops["DOCUMENT_IMG"],
                "i18n_links": entity.i18n_links(),
            }
        )
        return attrs

    def metadata(self, entity):
        metadata = super(CommemorationItemPrimaryView, self).metadata(entity)
        authors = self.authors(entity)
        if authors:
            metadata.append(authors)
        return metadata

    def authors(self, entity):
        _ = self._cw._
        authors = entity.cw_adapt_to("IMeta").author()
        if authors:
            title = _("Text author") if len(authors) == 1 else _("Text authors")
            data = _("###list_separator###").join(authors)
            return (f"{title}{_(':')}", data)

    def entity_images(self, entity):
        return entity.commemoration_image


class AuthorityRecordPrimaryView(FaqMixin, ShareLinksMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("AuthorityRecord")
    template = get_template("authorityrecord.jinja2")
    faq_category = "06_faq_eac"

    def template_attrs(self, entity):
        """Build the dictionary for the jinja template by
        merging all required data from the AuthorithyRecord entity"""
        attrs = super(AuthorityRecordPrimaryView, self).template_attrs(entity)
        adapter = entity.cw_adapt_to("entity.main_props")
        export_props = adapter.properties(export=True, vid="text", text_format="text/plain")
        csv_props = adapter.csv_export_props()
        csv_size = getsizeof("\t".join(e + i for i, e in export_props))
        csv_props["size"] = formatted_size(self._cw, csv_size)
        attrs.update(
            {
                "_": self._cw._,
                "lang": self._cw.lang,
                "faqs": self.faqs_attrs(),
                "main_props": adapter.properties(),
                "metadata": adapter.metadata(),
                "rdf_formats": [
                    (f"{entity.absolute_url()}/rdf.{extension}", extension, name)
                    for extension, name in RDF_FORMAT_EXTENSIONS.items()
                ],
                "eulerian": entity.cw_adapt_to("IEulerian").actions,
                "csv_props": csv_props,
                "sharelinks_data": self.sharelinks(entity.absolute_url()),
            }
        )
        if entity.related_service:
            publisher = entity.cw_adapt_to("IPublisherInfo").serialize()
            attrs.update({"publisher": publisher})
        return attrs


class FindingAidPrimaryView(FaqMixin, ShareLinksMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("FindingAid", "FAComponent")
    template = get_template("findingaid.jinja2")
    faq_category = "03_faq_ir"
    noreact = False

    @cachedproperty
    def iiif_manifest(self):
        return self.entity.iiif_manifest

    def entity_call(self, entity):
        self.entity = entity
        if self.iiif_manifest:
            self._cw.html_headers.define_var("DATA_URL", self._cw.datadir_url)
            add_js_translations(self._cw)
            self._cw.add_js("bundle-pnia-iiif-viewers.js")
        super().entity_call(entity)

    @cachedproperty
    def eulerian(self):
        return self.entity.cw_adapt_to("IEulerian").actions

    def render_content(self, entity):
        context = self.template_attrs(entity)
        self.call_template(**context)
        if context["display_context"]:
            self.content_navigation_components("fa-inventory-context")
        attrs = {
            "sharelinks": self.sharelinks(entity.absolute_url()),
            "css_class": "fi",
            "_": self._cw._,
            "heading_hierarchy": self.eulerian["document_title"],
            "component_hierarchy": "main_>_links",
        }
        self.w('<section class="fr-container fr-mt-16v">')
        self.w(get_template("sharelinks.jinja2").render(attrs))
        self.w("</section>")

    def template_attrs(self, entity):
        attrs = super(FindingAidPrimaryView, self).template_attrs(entity)
        adapter = entity.cw_adapt_to("entity.main_props")
        service = entity.related_service
        default_picto_src = [self._cw.uiprops["DIGITIZED_IMG"]]
        if service:
            illustration_url = service.illustration_url
            if illustration_url:
                default_picto_src.append(illustration_url)
        digitized_urls = adapter.digitized_urls()
        illustation_src = entity.illustration_url
        if not illustation_src and digitized_urls:
            illustation_src = self._cw.uiprops["DIGITIZED_IMG"]
        iiif_viewer = self._cw.form.get("viewer", "m")
        main_props = adapter.properties()
        export_props = adapter.properties(export=True, vid="text", text_format="text/plain")
        csv_size = getsizeof("\t".join(e + " " + i for i, e in export_props))
        csv_props = adapter.csv_export_props()
        csv_props["size"] = formatted_size(self._cw, csv_size)
        attrs.update(
            {
                "_": self._cw._,
                "publisher": entity.cw_adapt_to("IPublisherInfo").serialize(),
                "title": adapter.shortened_title(),
                "main_props": main_props,
                "indexes_props": adapter.indexes(),
                "illustation_src": illustation_src,
                "default_picto_src": ";".join(default_picto_src),
                "faqs": self.faqs_attrs(),
                "cms": self._cw.vreg.config.get("instance-type") == "cms",
                "csv_props": csv_props,
                "site_tour_url": self._cw.build_url(f"{entity.cw_etype.lower()}-tour.json"),
                "iiif_manifest": self.iiif_manifest,
                "iiif_viewer": iiif_viewer,
                "display_context": adapter.display_fa_context,
                "data_url": self._cw.datadir_url,
                "lang": self._cw.lang,
                "eulerian": self.eulerian,
                "a11y_alert": self._cw._("a11y_alert_iiif"),
                "rdf_formats": [
                    (f"{entity.absolute_url()}/rdf.{extension}", extension, name)
                    for extension, name in RDF_FORMAT_EXTENSIONS.items()
                ],
            }
        )
        inventory_source = adapter.inventory_source()
        if inventory_source:
            url = inventory_source.get("url")
            if url:
                inventory_source["url"] = xml_escape(url)
            attrs["inventory_source"] = inventory_source
        if digitized_urls:
            attrs["digitized_urls"] = [xml_escape(url) for url in digitized_urls]
        return attrs


class MapPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("Map")
    template = get_template("map-page.jinja2")
    needs_js = ("bundle-glossary.js",)

    def entity_call(self, entity):
        legends, options = {}, {"urls": {}, "colors": {}}
        items = defaultdict(list)
        services = list(all_services(self._cw))
        services_map = OrderedDict([(s.dpt_code.lower(), s.name) for s in services])
        for v in entity.data():
            url = v.get("url")
            if not url:
                continue
            if v["legend"]:
                legend = v["legend"]
                if legend.lower() == "legende":
                    continue
                items[v["color"]].append((services_map.get(v["code"], url), url))
                legends[v["color"]] = legend
            if v["url"]:
                options["urls"][v["code"]] = v["url"]
            if v["color"]:
                options["colors"][v["code"]] = v["color"].lower()
        dept_map_form = DeptMapForm(options)
        legends = [(c, l, items.get(c, [])) for c, l in legends.items()]
        self.w(
            self.template.render(
                _=self._cw._,
                map=entity,
                map_form=dept_map_form.render(self._cw, services),
                legends=legends,
            )
        )


class PniaDownloadView(DownloadView):
    def set_request_content_type(self):
        """don not set disposition='attachment' in content_type"""
        entity = self.cw_rset.complete_entity(self.cw_row or 0, self.cw_col or 0)
        adapter = entity.cw_adapt_to("IDownloadable")
        encoding = adapter.download_encoding()
        if encoding in BINARY_ENCODINGS:
            contenttype = "application/%s" % encoding
            encoding = None
        else:
            contenttype = adapter.download_content_type()
        self._cw.set_content_type(
            contenttype or self.content_type,
            filename=adapter.download_file_name(),
            encoding=encoding,
        )

    def entity_call(self, entity):
        adapter = entity.cw_adapt_to("IDownloadable")
        self.w(adapter.download_data())


class FilePrimaryView(PniaDownloadView):
    __regid__ = "primary"
    __select__ = PrimaryView.__select__ & is_instance("File")


class CircularPrimaryView(FaqMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("Circular")
    template = get_template("circular.jinja2")
    faq_category = "04_faq_circular"

    def get_related_cirular(self, circ_id):
        if circ_id:
            rset = self._cw.execute("Any X WHERE X is Circular, X circ_id %(c)s", {"c": circ_id})
            if rset:
                return rset.one().view("incontext")
        return xml_escape(circ_id) if circ_id else ""

    def metadata(self, entity):
        if entity.signing_date:
            return (("Date", format_date(entity.signing_date, self._cw)),)
        return ()

    def template_attrs(self, entity):
        attrs = super(CircularPrimaryView, self).template_attrs(entity)
        _ = self._cw._
        attrs.update({"_": _, "faqs": self.faqs_attrs(), "metadata": self.metadata(entity)})
        main_props = []
        circular_link = exturl_link(self._cw, entity.link) if entity.link else None
        for attr, value in (
            (_("circular_kind_label"), entity.printable_value("kind")),
            (_("circular_code_label"), entity.printable_value("code")),
            (_("circular_nor_label"), entity.printable_value("nor")),
            (_("circular_status_label"), _(entity.printable_value("status"))),
            (_("circular_link_label"), circular_link),
            (
                _("circular_additional_link_label"),
                [e.view("urlattr", rtype="url") for e in entity.additional_link],
            ),
            (
                _("circular_attachment_label"),
                [e.view("fa.circular.pdf", circular=entity) for e in entity.attachment],
            ),
            (
                _("circular_additional_attachment_label"),
                [e.view("fa.circular.pdf", circular=entity) for e in entity.additional_attachment],
            ),
            (_("circular_signing_date_label"), format_date(entity.signing_date, self._cw)),
            (_("circular_siaf_daf_kind_label"), entity.printable_value("siaf_daf_kind")),
            (_("circular_siaf_daf_code_label"), entity.printable_value("siaf_daf_code")),
            (
                _("circular_siaf_daf_signing_date_label"),
                format_date(entity.siaf_daf_signing_date, self._cw),
            ),
            (_("circular_producer_label"), entity.printable_value("producer")),
            (_("circular_producer_acronym_label"), entity.printable_value("producer_acronym")),
            (
                _("circular_modification_date_label"),
                format_date(entity.circular_modification_date, self._cw),
            ),
            (_("circular_abrogation_date_label"), format_date(entity.abrogation_date, self._cw)),
            (_("circular_abrogation_text_label"), self.get_related_cirular(entity.abrogation_text)),
            (_("circular_archival_field_label"), entity.printable_value("archival_field")),
            (
                _("circular_historical_context_label"),
                ", ".join(e.view("incontext") for e in entity.historical_context),
            ),
            (
                _("circular_business_field_label"),
                ", ".join(e.view("incontext") for e in entity.business_field),
            ),
            (
                _("circular_document_type_label"),
                ", ".join(e.view("incontext") for e in entity.document_type),
            ),
            (_("circular_action_label"), ", ".join(e.view("incontext") for e in entity.action)),
            (
                _("circular_modified_text_label"),
                ", ".join(e.view("incontext") for e in entity.modified_text),
            ),
            (
                _("circular_modifying_text_label"),
                ", ".join(e.view("incontext") for e in entity.modifying_text),
            ),
            (
                _("circular_revoked_text_label"),
                ", ".join(e.view("incontext") for e in entity.revoked_text),
            ),
        ):
            if value:
                label = display_name(self._cw, attr, context="Circular")
                main_props.append((label, value))
        attrs["main_props"] = main_props
        return attrs


class CircularPDFtInContext(InContextView):
    __regid__ = "fa.circular.pdf"

    def cell_call(self, row, col, circular):
        entity = self.cw_rset.get_entity(row, col)
        heading_hierarchy = circular.cw_adapt_to("IEulerian").actions["document_title"]
        desc = xml_escape(cut(entity.dc_description(), 50))
        title = xml_escape(entity.dc_title())
        detail = []
        if entity.data_name:
            filename, extension = osp.splitext(entity.data_name)
            detail.append(extension[1:].upper())
        size = entity.formatted_size()
        if size:
            detail.append(size)
        if detail:
            size = f'<span class="fa-link__detail">{" - ".join(detail)}</span>'
        self.w(
            f"""<a class="fr-link fr-link--download"
                   href="{xml_escape(entity.absolute_url())}" title="{desc}"
                   data-eulerian-actionname="download_pdf_{heading_hierarchy}"
                   data-eulerian-actionlabel="download_pdf,editorial,Circular,{title},"
                   data-eulerian-headinghierarchy="{heading_hierarchy}"
                   data-eulerian-componenthierarchy="main_>_section_>_h2"
                   data-eulerian-componentlabel="{title}"
                >{title}</a>{size}
            """,
            escape=False,
        )


class OfficialTextInContext(InContextView):
    __select__ = InContextView.__select__ & is_instance("OfficialText")

    max_title_size = 140

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        title = entity.dc_title()
        circular = entity.circular[0] if entity.circular else None
        if not circular:
            self.w(xml_escape(title))
            return
        date = circular.sortdate()
        if date:
            title = "{cid} {date}".format(
                date=self._cw._("on %s ") % format_date(date, self._cw), cid=title
            )
        kwargs = {"href": xml_escape(circular.absolute_url()), "klass": "fr-link"}
        desc = cut(entity.dc_description(), 50)
        if desc:
            kwargs["title"] = xml_escape(f"{title} - {desc}")
        self.w(T.a(xml_escape(title), **kwargs))


class UrLBasedAttributeView(URLAttributeView):
    """open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance("ExternRef", "Link", "ExternalUri")

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            self.w(exturl_link(self._cw, url, klass="fr-link"))


class IndexURLAttributeView(URLAttributeView):
    """open the url in a new tab"""

    __select__ = URLAttributeView.__select__ & is_instance(
        "Concept",
    )

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            title = blank_link_title(self._cw, url)
            self.w(
                T.a(
                    xml_escape(entity.dc_title()),
                    href=xml_escape(url),
                    title=xml_escape(title),
                    klass="fr-link",
                    target="_blank",
                    rel="nofollow noopener noreferrer external",
                )
            )


class DigitizedVersionUrLAttributeView(EntityView):
    __regid__ = "urlattr"
    __select__ = EntityView.__select__ & is_instance("DigitizedVersion")

    def entity_call(self, entity, rtype="subject", **kwargs):
        url = entity.printable_value(rtype)
        if url:
            self.w(exturl_link(self._cw, url, icon="file-archive-o"))


def is_virtual_exhibit(entity):
    return entity.reftype == "Virtual_exhibit"


class ExternRefPrimaryMixIn(RelatedAutorityIndexablePrimaryMixIn):
    def main_props(self, entity):
        main_props = self.authority_props(entity)
        _ = self._cw._
        service = entity.exref_service
        if service:
            main_props.append((_("service_label"), ", ".join(e.view("incontext") for e in service)))
        return main_props

    def template_attrs(self, entity):
        """Build the dictionary for the jinja template by
        merging all required data from the BaseContent entity"""
        attrs = super().template_attrs(entity)
        services = entity.exref_service
        if services:
            _ = self._cw._
            label = _("Service_plural") if len(services) > 1 else _("Service")
            attrs["services"] = [(label, [(e.absolute_url(), e.dc_title()) for e in services])]
        return attrs


class ExternRefPrimaryView(ShareLinksMixin, ExternRefPrimaryMixIn, ContentPrimaryView):
    __select__ = (
        PrimaryView.__select__
        & is_instance("ExternRef")
        & ~score_entity(lambda e: is_virtual_exhibit(e))
    )
    template = get_template("externref.jinja2")

    def template_attrs(self, entity):
        attrs = super(ExternRefPrimaryView, self).template_attrs(entity)
        attrs["years"] = entity.dates
        attrs.update(
            {
                "main_props": self.main_props(entity),
                "eulerian": entity.cw_adapt_to("IEulerian").actions,
                "sharelinks_data": self.sharelinks(entity.absolute_url()),
            }
        )
        return attrs

    def entity_images(self, entity):
        return entity.externref_image


class VirtualExhibitExternRefPrimaryView(ExternRefPrimaryMixIn, RecentDataPrimaryView):
    __select__ = (
        PrimaryView.__select__
        & is_instance("ExternRef")
        & score_entity(lambda e: is_virtual_exhibit(e))
    )
    template = get_template("virtualexhibit.jinja2")
    all_link_url = "expositions"
    all_link_label = _("See all virtual exhibits")

    def template_attrs(self, entity):
        attrs = super(VirtualExhibitExternRefPrimaryView, self).template_attrs(entity)
        attrs.update(
            {
                "main_props": self.main_props(entity),
                "eulerian": entity.cw_adapt_to("IEulerian").actions,
            }
        )
        # for eulerian tracking
        service = entity.services[0] if entity.services else None
        if service and service.code:
            attrs["service_code"] = service.code.lower()
        else:
            attrs["service_code"] = ""
        return attrs

    def entity_images(self, entity):
        return entity.externref_image


class NominaPrimaryView(FaqMixin, StartupView, UtilsMixin, ShareLinksMixin, JinjaViewMixin):
    __regid__ = "nomina-primary"
    template = get_template("nominarecord.jinja2")
    needs_css = ()
    needs_js = ("bundle-glossary.js",)
    faq_category = "07_faq_nomina"
    is_nomina = True

    def __init__(self, req=None, rset=None, **kwargs):
        super().__init__(req, rset=rset, **kwargs)
        self.entity = None
        self.entity = kwargs["entity"]
        self.init_entity(kwargs["stable_id"])

    def add_css(self):
        for css in self.needs_css:
            self._cw.add_css(css)

    def add_js(self):
        for js in self.needs_js:
            self._cw.add_js(js)

    def call(self, **kwargs):
        self.add_js()
        return self.call_template(**self.template_attrs())

    def init_entity(self, stable_id):
        if self.entity is None:
            try:
                self.entity = initialize_nominarecord_entity(self._cw, stable_id)
            except Exception as ex:
                self.errror(f"NominaRecord with stable_id {stable_id} not found: {ex}")
                raise NotFound
        return self.entity

    def page_title(self):
        return f'{self.entity.dc_title()} ({self._cw.property_value("ui.site-title")})'

    def template_context(self):
        return {
            "nomina": True,
            "display_nomina_search": False,
        }

    def template_attrs(self):
        json_data = self.entity.json_data
        service = self.entity.related_service
        if service:
            json_data["entity"]["publisher_title"] = service.dc_title()
        csv_props = None
        if "csv_export" in json_data:
            export_props = json_data["csv_export"]
            csv_size = getsizeof("\t".join(e + i for i, e in export_props))
            title = self._cw._("Download shelfmark")
            csv_props = {
                "url": self._cw.build_url(f"{self.entity.rest_path()}.csv"),
                "filename": f"{self.entity.rest_path()}.csv".replace("/", "_"),
                "title": title,
                "link": title,
                "size": formatted_size(self._cw, csv_size),
            }
        attrs = {
            "_": self._cw._,
            "lang": self._cw.lang,
            "faqs": self.faqs_attrs(),
            "main_props": [(k, v) for k, v in json_data["main_props"].items() if v],
            "entity": json_data["entity"],
            "publisher": self.entity.cw_adapt_to("IPublisherInfo").serialize(),
            "source_url": json_data["entity"].get("source_url"),
            "warning": json_data.get("warning"),
            "csv_props": csv_props,
            "eulerian": self.entity.cw_adapt_to("IEulerian").actions,
            "sharelinks_data": self.sharelinks(json_data["entity"]["absolute_url"]),
        }
        agents = self.entity.related_agents()
        if agents:
            attrs["see_others"] = (self._cw._("Link with the qualified agent"), agents)
        household_link = json_data.get("household_link")
        if household_link:
            attrs["household_link"] = (
                self._cw._("See all members of the household"),
                household_link,
            )

        return attrs


class PniaCardPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("Card")
    template = get_template("card.jinja2")

    def render_content(self, entity):
        attrs = self.template_attrs(entity)
        attrs.update(
            {"metadata": ((_("Last update on"), entity.fmt_modification_date),), "_": self._cw._}
        )
        self.call_template(**attrs)


class PniaTranslationsPrimaryView(ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & relation_possible("translation_of", role="subject")
    template = get_template("translation.jinja2")

    def get_translation(self, original, entity):
        trads = []
        if self.editable:
            translations = {}
            for res in original.i18n_rset().iter_rows_with_entities():
                trad = res[0]
                translations[trad.language] = trad
            for lang in SUPPORTED_LANGS:
                if lang in ("fr", entity.language):
                    continue
                trad = translations.get(lang)
                if trad:
                    state = self._cw._(trad.cw_adapt_to("IWorkflowable").state)
                    if trad.eid != entity.eid:
                        trad = trad.view("incontext")
                    else:
                        trad = trad.dc_title()
                else:
                    state = ""
                    trad = self._cw._("no translation yet exists")
                trads.append((self._cw._(lang), trad, state))
        return trads

    def metadata(self, entity):
        return [
            (self._cw._("Language"), self._cw._(entity.language)),
        ]

    def main_props(self, entity):
        _ = self._cw._
        main_props = []
        original = entity.original_entity
        for attr in original.i18nfields:
            main_props.append((_(attr), entity.printable_value(attr)))
        return main_props

    def template_attrs(self, entity):
        attrs = super(PniaTranslationsPrimaryView, self).template_attrs(entity)
        original = entity.original_entity
        attrs.update(
            {
                "_": self._cw._,
                "editable": self.editable,
                "original": original.view("incontext"),
                "original_title": xml_escape(original.dc_title()),
                "metadata": self.metadata(entity),
            }
        )
        attrs["translations"] = self.get_translation(original, entity)
        attrs["main_props"] = self.main_props(entity)
        return attrs


class AbstractEditablePrivaryView(ContentPrimaryView):
    template = get_template("editable_entities.jinja2")

    def content_meta_props(self, entity):
        return []

    def main_props(self, entity):
        return []

    def info_links(self, entity):
        return []

    def template_attrs(self, entity):
        attrs = super().template_attrs(entity)
        attrs.update(
            {
                "metadata": self.content_meta_props(entity),
                "main_props": self.main_props(entity),
                "info_links": self.info_links(entity),
                "description": "",
                "_": self._cw._,
            }
        )
        return attrs


class GlossaryTermPrimaryView(AbstractEditablePrivaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("GlossaryTerm")

    def info_links(self, entity):
        return [
            (
                self._cw._("Go to the glossary"),
                self._cw.build_url(
                    "glossaire",
                ),
            ),
        ]


class GlossaryView(View, JinjaViewMixin):
    __regid__ = "glossary"
    template = get_template("glossary.jinja2")
    title = _("Glossary")
    editable = False
    eulerian_tag = True
    eulerian_pagegroup = "faq"

    @property
    def breadcrumbs(self):
        b_url = self._cw.build_url
        breadcrumbs = [(b_url(""), self._cw._("Home"))]
        breadcrumbs.append((b_url("glossary"), self._cw._("Glossary")))
        return breadcrumbs

    def card(self):
        card = find_card(self._cw, "glossary-card", display_empty=True)
        if card is not None:
            return card

    def build_glossary(self):
        rset = self._cw.execute(
            """Any X, L, T, D, A ORDERBY T WHERE X is GlossaryTerm, X term T,
            X description D, X sort_letter L, X anchor A"""
        )
        glossary = defaultdict(list)
        for eid, letter, term, description, sort_term in rset:
            glossary[letter].append((eid, term, title_for_link(term), description, sort_term))
        return glossary

    def add_js(self):
        self._cw.add_js("bundle-pnia-glossary.js")

    def call(self, **kw):
        self.add_js()
        req = self._cw
        letters = [
            e[0]
            for e in req.execute(
                "DISTINCT Any L ORDERBY L WHERE X is GlossaryTerm, X sort_letter L"
            ).rows
        ]
        card = self.card()
        attrs = {
            "glossary": self.build_glossary(),
            "letters": letters,
            "card": card.content if card else None,
            "title": card.title if card else req._(self.title),
            "editable": self.editable,
            "base_url": self._cw.build_url("").rstrip("/"),
            "glossary_url": self._cw.build_url("glossaire"),
            "lang": self._cw.lang,
            "_": req._,
        }
        self.call_template(**attrs)


class FaqStartView(View, JinjaViewMixin):
    __regid__ = "faq"
    template = get_template("faq.jinja2")
    title = _("FAQ")
    editable = False
    eulerian_tag = True
    eulerian_pagegroup = "faq"

    @property
    def breadcrumbs(self):
        b_url = self._cw.build_url
        breadcrumbs = [(b_url(""), self._cw._("Home"))]
        breadcrumbs.append((b_url("glossary"), self._cw._("FAQ")))
        return breadcrumbs

    def call(self, **kw):
        req = self._cw
        sql_query = """
        SELECT faq.cw_eid eid,
               TRANSLATE_ENTITY('FaqItem', faq.cw_eid, 'question', %(lang)s) AS question,
               TRANSLATE_ENTITY('FaqItem', faq.cw_eid, 'answer', %(lang)s) AS answer,
               faq.cw_category as category,
               faq.cw_order as order,
               faq.cw_question as fr_question,
               faq.cw_answer as fr_answer
        FROM cw_FaqItem AS faq ORDER BY 4"""
        # TODO rewrite the TRANSLATE_ENTITY to return the actual entity language
        # and avoid comparing values
        rset = req.cnx.system_sql(sql_query, {"lang": req.lang}).fetchall()
        faqs = defaultdict(list)
        fr_lang = self._cw.lang == "fr"
        for eid, question, answer, category, order, fr_question, fr_answer in rset:
            qlang_attr = 'lang="fr"' if not fr_lang and question == fr_question else ""
            alang_attr = 'lang="fr"' if not fr_lang and answer == fr_answer else ""
            faq_url = self._cw.build_url("faqitem/{}".format(eid))
            faqs[category].append(
                (eid, faq_url, remove_html_tags(question), answer, qlang_attr, alang_attr)
            )
        faqs = sorted(faqs.items(), key=lambda e: e[0])
        attrs = {
            "editable": self.editable,
            "faqs": faqs,
            "title": req._(self.title),
            "lang": self._cw.lang,
            "_": req._,
        }
        self.call_template(**attrs)


class FaqItemPrimaryView(AbstractEditablePrivaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("FaqItem")

    def info_links(self, entity):
        return [
            (
                self._cw._("Go to the Faq"),
                self._cw.build_url(
                    "faq",
                ),
            ),
        ]


class SiteLinkPrimaryView(AbstractEditablePrivaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("SiteLink")


class AgentRecordVocabularyPrimaryView(AbstractEditablePrivaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance(
        "AgentRecordFunction", "AgentRecordOccupation", "AgentRecordLegalStatus"
    )

    template = get_template("agentrecord_vocabulary.jinja2")

    def entity_call(self, entity, **kw):
        self.call_template(**self.template_attrs(entity))

    def content_meta_props(self, entity):
        return []

    def template_attrs(self, entity):
        adapter = entity.cw_adapt_to("ITemplatable")
        return {
            "metadata": self.content_meta_props(entity),
            "entity": adapter.entity_param(),
            "main_props": adapter.main_props(),
            "lang": self._cw.lang,
            "_": self._cw._,
        }


class ServicePrimaryView(ShareLinksMixin, ContentPrimaryView):
    __select__ = ContentPrimaryView.__select__ & is_instance("Service")
    template = get_template("service.jinja2")

    def template_attrs(self, entity):
        attrs = super().template_attrs(entity)
        attrs.update(
            {
                "lang_attr": f'lang="{entity.lang}"' if entity.lang != self._cw.lang else "",
                "sharelinks_data": self.sharelinks(entity.absolute_url()),
            }
        )
        return attrs

    def call(self, **kwargs):
        for css in ("leaflet.css", "LeafletStyleSheet.css"):
            self._cw.add_css(css)
        for js in ("leaflet.js", "PruneCluster.js", "bundle-pnia-entity-map.js"):
            self._cw.add_js(js)
        super().call(**kwargs)


class ServiceDptContent(EntityView, JinjaViewMixin):
    __regid__ = "service-dpt-content"
    __select__ = EntityView.__select__ & is_instance("Service")
    template = get_template("services-maininfo.jinja2")

    def entity_call(self, entity):
        rset = self._cw.execute(
            """Any X, N, N2, L WHERE X dpt_code C, Y dpt_code C,
               X name N, X name N2, Y eid %(e)s, X level L""",
            {"e": entity.eid},
        )
        if rset:
            entities = sorted(rset.entities(), key=lambda x: x.level != "level-D")
            self.w(
                self.template.render(
                    {
                        "services": [
                            e.cw_adapt_to("ITemplatable").entity_param() for e in entities
                        ],
                        "lang_attr": 'lang="fr"' if self._cw.lang != "fr" else "",
                        "_": self._cw._,
                    }
                )
            )


class AuthorityIndexPrimaryView(PrimaryView, JinjaViewMixin):
    __select__ = PrimaryView.__select__ & is_instance("AgentName", "Geogname", "Subject")
    template = get_template("index.jinja2")

    def entity_call(self, entity, **kw):
        self.call_template(**self.template_attrs(entity))

    def content_meta_props(self, entity):
        return []

    def template_attrs(self, entity):
        adapter = entity.cw_adapt_to("ITemplatable")
        return {
            "metadata": self.content_meta_props(entity),
            "entity": adapter.entity_param(),
            "main_props": adapter.main_props(),
            "indexes": adapter.documents(),
            "lang": self._cw.lang,
            "_": self._cw._,
        }


class AgentRecordPrimaryView(ShareLinksMixin, ContentPrimaryView):
    __select__ = PrimaryView.__select__ & is_instance("AgentRecord")
    template = get_template("agentrecord.jinja2")

    def csv_props(self, entity):
        title = self._cw._("Download shelfmark")
        return {
            "url": self._cw.build_url(f"{entity.rest_path()}.csv"),
            "link": title,
            "filename": f"{entity.record_id}.csv",
            "size": "",
        }

    def eaccpf_props(self, entity):
        title = self._cw._("Download the record in EAC-CPF (v2)")
        return {
            "url": self._cw.build_url(f"{entity.rest_path()}.xml"),
            "link": title,
            "filename": f"{entity.record_id}.xml",
            "size": "",
        }

    def template_attrs(self, entity):
        props = super(AgentRecordPrimaryView, self).template_attrs(entity)
        adapter = entity.cw_adapt_to("entity.main_props")
        csv_props = self.csv_props(entity)
        eaccpf_props = self.eaccpf_props(entity)
        publisher = {"title": "SIAF"}
        props.update(
            {
                "_": self._cw._,
                "main_props": [(k, v) for k, v in adapter.main_props().items() if v],
                "metadata": adapter.metadata(),
                "csv_props": csv_props,
                "eaccpf_props": eaccpf_props,
                "publisher": publisher,
                "eulerian": entity.cw_adapt_to("IEulerian").actions,
                "sharelinks_data": self.sharelinks(entity),
                "editable": self.editable,
                "notice_metadata": adapter.notice_metadata(),
            }
        )
        return props


def registration_callback(vreg):
    vreg.register_all(list(globals().values()), __name__, (PniaDownloadView, PniaCardPrimaryView))
    vreg.register_and_replace(PniaDownloadView, DownloadView)
    vreg.register_and_replace(PniaCardPrimaryView, CardPrimaryView)
