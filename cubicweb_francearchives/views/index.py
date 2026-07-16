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

from collections import defaultdict

from urllib.parse import urlparse

from cwtags import tag as T

from logilab.common.decorators import cachedproperty
from logilab.mtconverter import xml_escape

from cubicweb import _
from cubicweb.predicates import is_instance, rql_condition
from cubicweb_web.view import EntityView
from cubicweb.entity import EntityAdapter
from cubicweb.uilib import cut

from cubicweb_web.views.baseviews import InContextView
from cubicweb_web.views.primary import PrimaryView
from cubicweb_francearchives.entities.rdf import RDF_FORMAT_EXTENSIONS
from cubicweb_francearchives.views.search.nomina import PniaNominaElasticSearchView
from cubicweb_francearchives.views.search import PniaElasticSearchView
from cubicweb_francearchives.views import get_template, blank_link_title


class IndexElasticSearchView(PniaElasticSearchView):
    __regid__ = "indexes-esearch"
    title_count_templates = (
        _("No linked content"),
        _("1 linked content"),
        _("{count} linked content"),
    )

    def call(self, entity, **kwargs):
        self.entity = entity
        super().call(**kwargs)

    def get_header_attrs(self):
        adapter = self.entity.cw_adapt_to("ISearchContextAbstract")
        if adapter:
            return adapter.get_properties()

    def get_rdf_formats(self):
        if self.entity.quality:
            return [
                (f"{self.entity.absolute_url()}/rdf.{extension}", extension, name)
                for extension, name in RDF_FORMAT_EXTENSIONS.items()
            ]
        return None

    @property
    def eulerian_actions(self):
        return self.entity.cw_adapt_to("IEulerian").actions


class AgentAuthorityElasticSearchView(IndexElasticSearchView):
    __select__ = IndexElasticSearchView.__select__ & is_instance("AgentAuthority")
    template = get_template("searchlist-agent.jinja2")


class LocationAuthorityElasticSearchView(IndexElasticSearchView):
    __select__ = IndexElasticSearchView.__select__ & is_instance("LocationAuthority")
    template = get_template("searchlist-location.jinja2")


class SubjectAuthorityElasticSearchView(IndexElasticSearchView):
    __select__ = IndexElasticSearchView.__select__ & is_instance("SubjectAuthority")
    template = get_template("searchlist-subject.jinja2")

    def compute_augmented_search_options(self, response, query_string):
        """augmented_search is active only in SubjectAuhtorities"""
        is_augmented = "aug" in self._cw.form
        url_params = self._cw.form.copy()
        _ = self._cw._
        if is_augmented:
            del url_params["aug"]
            search_text = _("augmented_search_link_text_true")
            href = self._cw.build_url(**url_params)
            link = f'<a href="{href}">{search_text}</a>'
            text = _("augmented_search_text_true {}").format(link)
        else:
            url_params["aug"] = True
            href = self._cw.build_url(**url_params)
            search_text = _("augmented_search_link_text_false")
            link = f'<a href="{href}">{search_text}</a>'
            text = _("augmented_search_text_false {}").format(link)
        return {"extra_link": text, "search_is_augmented": is_augmented}


class AgentAuthorityNominaView(PniaNominaElasticSearchView):
    __select__ = is_instance("AgentAuthority")
    __regid__ = "agents-nomina"

    @cachedproperty
    def entity(self):
        return self.cw_rset.get_entity(0, 0)

    def search_title(self):
        title = [self.entity.dc_title()]
        title.append("({})".format(self._cw.property_value("ui.site-title")))
        return xml_escape(" ".join(title))

    def get_header_attrs(self):
        return {"title": self.entity.view("outofcontext")}

    def call(self, context=None, **kwargs):
        self.entity = self.cw_rset.get_entity(0, 0)
        super().call(context=context, **kwargs)


class AuthorityPrimaryView(PrimaryView):
    __select__ = PrimaryView.__select__ & is_instance(
        "SubjectAuthority", "AgentAuthority", "LocationAuthority"
    )

    def entity_call(self, entity, **kw):
        self._cw.form.pop("rql", None)  # remove rql form param which comes from url_rewriter
        self._cw.form["indexentry"] = entity.eid
        self._cw.form["restrict_to_single_etype"] = False
        self.wview("indexes-esearch", entity=entity)


class IndexInContextView(InContextView):
    __select__ = InContextView.__select__ & is_instance("AgentName", "Subject", "Geogname")

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        kwargs = {"href": xml_escape(entity.authority_url())}
        if self._cw.lang == entity.lang:
            self.w(T.a(xml_escape(entity.dc_title()), **kwargs))
        else:
            with T.a(self.w, **kwargs):
                self.w(T.span(xml_escape(entity.dc_title()), lang=entity.lang))


class AbstractExternalInContextView(InContextView):
    __abstract__ = True
    uri_attr = None

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        self.w(entity.view("urlattr", rtype=self.uri_attr))


class ExternalUriInContextView(InContextView):
    __select__ = InContextView.__select__ & is_instance("ExternalUri")

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        url = entity.uri
        netloc = urlparse(url).netloc
        kwargs = {
            "href": xml_escape(url),
            "klass": "fr-link",
            "target": "_blank",
            "rel": "nofollow noopener noreferrer external",
            "title": xml_escape(f"{netloc} {self._cw._('- New window')}"),
        }
        title = entity.in_context_label() or entity.uri
        with T.a(self.w, **kwargs):
            entity_lang = getattr(entity, "lang", "fr")
            if self._cw.lang == entity_lang:
                self.w(xml_escape(title))
            else:
                self.w(T.span(xml_escape(title), lang="fr"))


class NominaUriInContextView(InContextView):
    __select__ = (
        InContextView.__select__ & is_instance("ExternalUri") & rql_condition('X source "nomina"')
    )

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        url = f"{self._cw.base_url()}/basedenoms/{entity.extid}"
        title = entity.in_context_label() or entity.uri
        kwargs = {
            "href": xml_escape(url),
            "klass": "fr-link fr-icon-arrow-right-line fr-link--icon-right",
            "title": xml_escape(title),
        }
        with T.a(self.w, **kwargs):
            entity_lang = getattr(entity, "lang", "fr")
            if self._cw.lang == entity_lang:
                self.w(xml_escape(title))
            else:
                self.w(T.span(xml_escape(title), lang="fr"))


class GeonameMultipleExternalUriInContextView(ExternalUriInContextView):
    __regid__ = "incontext-geonames-multiple-links"

    def cell_call(self, row, col):
        super().cell_call(row, col)
        fclass = self.cw_rset.get_entity(row, col).get_geonames_fclass()
        if fclass:
            self.w(f"- {self._cw._(fclass)}")


class ConceptInContextView(AbstractExternalInContextView):
    __select__ = AbstractExternalInContextView.__select__ & is_instance("Concept")
    uri_attr = "cwuri"

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        link = self._cw._("link to %s") % entity.schema_label
        label = entity.dc_title()
        url = entity.printable_value("cwuri")
        if url:
            # for now we only have data.culture.fr thesaurus
            kwargs = {
                "href": xml_escape(url),
                "title": blank_link_title(self._cw, f"{entity.dc_title()} - {link}"),
                "klass": "fr-link",
                "target": "_blank",
                "rel": "nofollow noopener noreferrer external",
            }
            if self._cw.lang == "fr":
                self.w(T.a(xml_escape(label), **kwargs))
            else:
                with T.a(self.w, **kwargs):
                    self.w(T.span(xml_escape(label), lang=entity.lang))


class NominaAgentInContextView(InContextView):
    __regid__ = "nomina_agent"
    __select__ = InContextView.__select__ & is_instance("AgentAuthority")

    max_title_size = 140

    def cell_call(self, row, col, **kwargs):
        entity = self.cw_rset.get_entity(row, col)
        full_title = entity.dc_title()
        kwargs = {
            "klass": "fr-link",
            "href": xml_escape(entity.absolute_url()),
            "target": "_blank",
        }
        if self._cw.lang == entity.lang:
            self.w(T.a(xml_escape(full_title), **kwargs))
        else:
            with T.a(self.w, **kwargs):
                self.w(T.span(xml_escape(full_title), lang=entity.lang))


class AbstractAuthorityAdapter(EntityAdapter):
    __abstract__ = True
    __regid__ = "ISearchContextAbstract"
    editable = False

    def get_properties(self):
        properties = self.main_properties()
        sources = self.sources()
        return {
            "entity": self.entity,
            "metadata": self.metadata_properties(),
            "display_tab": any((self.entity.quality, sources, properties)),
            "authority_properties": properties,
            "sources": self.sources(),
            "quality": self.entity.quality,
            "lang": self._cw.lang,
            "editable": self.editable,
        }

    def sources(self):
        raise NotImplementedError()

    def main_properties(self):
        raise NotImplementedError()

    def metadata_properties(self):
        if self.editable:
            return [
                (self._cw._("Creation date"), self.entity.fmt_creation_date),
                (self._cw._("Modification date"), self.entity.fmt_modification_date),
            ]
        return []


class AgentAuthorityAbstractAdapter(AbstractAuthorityAdapter):
    __select__ = AbstractAuthorityAdapter.__select__ & is_instance("AgentAuthority")

    def get_properties(self):
        adapter = self.entity.cw_adapt_to("entity.main_props")
        properties = adapter.properties()
        sources = adapter.sources()
        wikidata_props = self.wikidata_properties()
        data = {
            "entity": self.entity,
            "metadata": self.metadata_properties(),
            "display_tab": any((properties, self.entity.quality, sources, wikidata_props)),
            "authority_properties": properties,
            "sources": sources,
            "wikirelations": wikidata_props,
            "quality": self.entity.quality,
            "lang": self._cw.lang,
            "editable": self.editable,
        }
        return data

    def wikidata_properties(self):
        _ = self._cw._
        data = [
            (
                _("Parent(s)"),
                [e.view("incontext") for e in self.entity.parents],
            ),
            (
                _("Sibling(s)"),
                [e.view("incontext") for e in self.entity.siblings],
            ),
            (
                _("Spouse(s)"),
                [e.view("incontext") for e in self.entity.spouses],
            ),
            (
                _("Child/Children"),
                [e.view("incontext") for e in self.entity.children],
            ),
            (
                _("Member of"),
                [e.view("incontext") for e in self.entity.organizations],
            ),
            (
                _("Member(s)"),
                [e.view("incontext") for e in self.entity.members],
            ),
        ]
        data = [entry for entry in data if entry[1]]
        return data


def get_similar_subjects(cnx, concept, subject):
    subjects = defaultdict(list, {})
    for eid, label in cnx.execute(
        """Any S, NORMALIZE_ENTRY(L) WHERE X eid %(e)s,
           S same_as X, S label L,
           NOT S grouped_with S1,
                   NOT S eid %(s)s
                   """,
        {"e": concept.eid, "s": subject.eid},
    ):
        subjects[label].append(cnx.entity_from_eid(eid))
    labels = [
        r[0]
        for r in cnx.execute(
            """Any NORMALIZE_ENTRY(L) ORDERBY L WHERE O label_of X,
                O label L, X eid %(e)s""",
            {"e": concept.eid},
        )
    ]
    html = []
    for label in labels:
        entities = subjects.get(label, [])
        for entity in entities:
            serializable = entity.cw_adapt_to("ISuggestIndexSerializable")
            doc_count = serializable.related_docs()
            if doc_count:
                desc = cut(entity.dc_description(), 50)
                label = f"{xml_escape(entity.dc_title())} [{doc_count}]"
                if cnx.lang == entity.lang:
                    html.append(
                        f'<a class="fr-link" href="{xml_escape(entity.absolute_url())}" '
                        f'title="{xml_escape(desc)}">{label}</a>'
                    )
                else:
                    html.append(
                        f'<a class="fr-link" href="{xml_escape(entity.absolute_url())}" '
                        f'title="{xml_escape(desc)}"><span lang="{{ enity.lang }}">'
                        f"{label}</span></a>"
                    )
    return html


class SubjectAuthorityAbstractAdapter(AbstractAuthorityAdapter):
    __select__ = AbstractAuthorityAdapter.__select__ & is_instance("SubjectAuthority")

    def main_properties(self):
        return []

    def get_properties(self):
        properties = self.main_properties()
        sources, similar_themes = self.sources()
        return {
            "entity": self.entity,
            "metadata": self.metadata_properties(),
            "display_tab": any((self.entity.quality, sources, similar_themes, properties)),
            "authority_properties": properties,
            "sources": sources,
            "similarthemes": similar_themes,
            "quality": self.entity.quality,
            "lang": self._cw.lang,
            "editable": self.editable,
        }

    def sources(self):
        _ = self._cw._
        sources, external_sources, fa_sources = [], [], []
        same_as = self.entity.same_as_links
        concepts = same_as.get("Concept")
        subjects = []
        if concepts:
            dc_label = _("data.culture.fr")
            data = defaultdict(list, [])
            for concept in concepts:
                data[f"{concept.schema_label} ({dc_label})"].append(concept.view("incontext"))
                subjects.extend(get_similar_subjects(self._cw, concept, self.entity))
            if data:
                external_sources.extend([(label, links) for label, links in data.items()])
        external_uris = sorted(
            [(_(e.source), e.view("incontext")) for e in same_as.get("ExternalUri", [])],
            key=lambda x: getattr(x, "source", "z") or "z",
            reverse=True,
        )
        if external_uris:
            external_sources.extend(external_uris)
        authority_records = same_as.get("AuthorityRecord")
        if authority_records:
            fa_sources.append(
                (
                    self._cw._("AuthorityRecords"),
                    [e.view("maintainer.incontext") for e in authority_records],
                ),
            )
        if fa_sources:
            sources.append((self._cw._("fa_sources_label"), fa_sources))
        if external_sources:
            sources.append((self._cw._("external_sources_label"), external_sources))
        return sources, subjects


class LocationAuthorityAbstractAdapter(AbstractAuthorityAdapter):
    __select__ = AbstractAuthorityAdapter.__select__ & is_instance("LocationAuthority")

    def main_properties(self):
        return []

    def sources(self):
        links = self.entity.same_as_links.get("ExternalUri")
        if not links:
            return []
        links_by_source = {}
        for link in links:
            if link.source not in links_by_source:
                links_by_source[link.source] = []
            links_by_source[link.source].append(link)
        sources = []
        for source, same_as in links_by_source.items():
            if len(same_as) > 1:
                links = [s.view("incontext-geonames-multiple-links") for s in same_as]
            else:
                links = same_as[0].view("incontext")
            sources.append((self._cw._(source), links))
        sources = ((self._cw._("external_sources_label"), sources),)
        return sources


class AuthorityRecordView(EntityView):
    __regid__ = "maintainer.incontext"
    __select__ = EntityView.__select__ & is_instance("AuthorityRecord")

    def entity_call(self, entity, **kwargs):
        title = entity.dc_title()
        if entity.maintainer:
            title = f"{entity.maintainer[0].dc_title()}{self._cw._(':')}{title}"
        kwargs = {
            "href": xml_escape(entity.absolute_url()),
            "klass": "fr-link fr-icon-arrow-right-line fr-link--icon-right",
        }
        if self._cw.lang == entity.lang:
            self.w(T.a(xml_escape(title), **kwargs))
        else:
            with T.a(self.w, **kwargs):
                self.w(T.span(xml_escape(title), lang=entity.lang))
