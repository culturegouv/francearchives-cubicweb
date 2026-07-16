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

from logilab.mtconverter import xml_escape

from cwtags import tag as T

from cubicweb import _
from cubicweb_web.view import EntityView
from cubicweb.predicates import is_instance
from cubicweb.schema import display_name

from cubicweb_francearchives.views import get_template, blank_link_title
from cubicweb_francearchives.utils import format_date, title_for_link, remove_html_tags


def clean_properties(properties, entity, req):
    cleaned = []
    for label, value in properties:
        if label is None:
            cleaned.append((label, value))
        else:
            cleaned.append((display_name(req, label, context=entity.cw_etype), value))
    return cleaned


class PniaTextSearchResultView(EntityView):
    __regid__ = "pniasearch-item"
    template = get_template("searchitem.jinja2")

    def get_illustration(self, entity):
        url = getattr(entity, "illustration_url", None)
        if url:
            return {
                "url": url,
                "alt": getattr(entity, "illustration_alt", None)
                or remove_html_tags(entity.dc_title()),
            }

    def get_service(self, entity):
        return None

    def default_picto_src(self, entity):
        return None

    def get_logo(self, entity, service=None):
        if service:
            logo = service.illustration_url
            if logo:
                return {
                    "src": logo,
                }

    def get_default_picto_srcs(self, entity, illustration, doc_image):
        default_srcs = self.default_picto_src(entity)
        if illustration == default_srcs:
            default_srcs = doc_image
        else:
            if default_srcs:
                default_srcs = ";".join((default_srcs, doc_image))
            else:
                default_srcs = doc_image
        return default_srcs

    def get_highlights(self, entity, es_response, max_highlights=3):
        highlights = defaultdict(list)
        highlights_label = None
        if "highlight" in es_response.meta:
            highlights_dict = es_response.meta.highlight.to_dict()
            for key, values in list(highlights_dict.items()):
                if key not in ("index_entries.label", "text"):
                    if len(highlights["notice"]) > max_highlights:
                        continue
                    highlights["notice"].extend(values)
                else:
                    # there is no point to show the same index string several times
                    if len(highlights[key]) > 1:
                        continue
                    highlights[key].extend(values)
                if len(highlights["notice"]) > max_highlights:
                    break

        highlights_values = []
        if highlights["notice"]:
            # only display index or text if no excerpts from other fields are found
            highlights_values = highlights["notice"][:max_highlights]
            highlights_label = self._cw._("Notice excerpt:")
        elif "index_entries.label" in highlights:
            highlights_values = highlights["index_entries.label"][:max_highlights]
            highlights_label = self._cw._("Indexed authorities:")
        elif "text" in highlights:
            highlights_values = highlights["text"][:max_highlights]
            highlights_label = self._cw._("Excerpt from attachment:")
        if highlights_values:
            return {"values": highlights_values, "label": highlights_label}

    def template_context(self, entity, es_response, max_highlights=3):
        properties = self.properties(entity)
        doc_image = self._cw.uiprops["DOCUMENT_IMG"]
        illustration = self.get_illustration(entity)
        if illustration:
            illustration = {
                "src": illustration["url"],
                "srcs": self.get_default_picto_srcs(entity, illustration["url"], doc_image),
            }
        logo = None
        service = self.get_service(entity)
        if service:
            logo_src = service.illustration_url
            if logo_src:
                logo = {
                    "src": logo_src,
                    "srcs": (
                        self.get_default_picto_srcs(entity, logo_src, doc_image) if logo_src else ""
                    ),
                }
        entity_title = entity.dc_title()
        return {
            "_": self._cw._,
            "entity": {
                "url": xml_escape(entity.absolute_url()),
                "link_title": (title_for_link(xml_escape(entity_title)) if entity_title else ""),
                "alink": entity.view("incontext"),
                "cw_etype": self.entity_type(entity),
                "service": service,
            },
            "illustration": illustration,
            "logo": logo,
            "highlights": self.get_highlights(entity, es_response, max_highlights),
            "item_properties": properties,
        }

    def entity_type(self, entity):
        return entity.cw_etype

    def cell_call(self, row, col, es_response=None):
        entity = self.cw_rset.get_entity(row, col)
        entity = entity.cw_adapt_to("ITemplatable").entity_param()
        self.w(self.template.render(self.template_context(entity, es_response)))

    def properties(self, entity):
        bottom = clean_properties(self.properties_bottom(entity), entity, self._cw)
        service_link = self.service_link(entity)
        if service_link:
            bottom.append(service_link)
        return {
            "top": clean_properties(self.properties_top(entity), entity, self._cw),
            "bottom": bottom,
        }

    def service_link(self, entity):
        service = self.get_service(entity)
        if service:
            return (self._cw._("publisher"), service.view("incontext"))

    def properties_top(self, entity):
        yield (None, None)

    def properties_bottom(self, entity):
        meta = entity.cw_adapt_to("IMeta")
        if meta:
            authors = meta.author()
            label = _("Author") if len(authors) < 2 else _("Authors")
            yield (label, self._cw._("###list_separator###").join(meta.author()))
        else:
            yield (None, None)


class CircularSearchResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("Circular")

    def template_context(self, entity, es_response):
        ctx = super(CircularSearchResultView, self).template_context(entity, es_response)
        ctx["circular_css_class"] = entity.status
        ctx["circular_status"] = self._cw._(entity.printable_value("status"))
        return ctx

    def properties_top(self, entity):
        return [
            (
                _("code"),
                entity.printable_value("nor")
                or entity.printable_value("siaf_daf_code")
                or entity.printable_value("code"),
            ),
            (_("siaf_daf_kind"), entity.printable_value("siaf_daf_kind")),
            # TODO - removed because duplicate with visual indication
            (_("status"), self._cw._(entity.printable_value("status"))),
            (
                _("signing_date"),
                (
                    None
                    if entity.signing_date is None
                    else format_date(entity.signing_date, self._cw)
                ),
            ),
            (
                _("siaf_daf_signing_date"),
                (
                    None
                    if entity.siaf_daf_signing_date is None
                    else format_date(entity.siaf_daf_signing_date, self._cw)
                ),
            ),
            (
                _("link"),
                (
                    '<a href="{link}">{link}</a>'.format(link=xml_escape(entity.link))
                    if entity.link
                    else None
                ),
            ),
        ]


class ServiceSearchResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("Service")

    def eulerian(self, entity):
        if not hasattr(self, "_eulerian"):
            self._eulerian = entity.cw_adapt_to("IEulerian").actions
        return self._eulerian

    def template_context(self, entity, es_response, max_highlights=3):
        eulerian = self.eulerian(entity)
        template_context = super().template_context(
            entity, es_response, max_highlights=max_highlights
        )
        template_context["entity"]["url"] = xml_escape(entity.absolute_url())
        document_title = f"{eulerian['document_title']}"
        heading_hierarchy = f"recherche_>_{document_title}"
        eulerian_link = f"voir_{document_title}"
        title = entity.dc_title()
        template_context["entity"]["alink"] = str(
            T.a(
                xml_escape(title) if title else "",
                href=xml_escape(entity.absolute_url()),
                klass="eulerian-button",
                data_eulerian_actionname=f"site_record_{heading_hierarchy}",
                data_eulerian_actionlabel=f"site_record,content,service,{eulerian_link},{entity.code}",  # noqa
                data_eulerian_headinghierarchy=heading_hierarchy,
                data_eulerian_componenthierarchy="main_>_section_>_list",
                data_eulerian_componentlabel=eulerian_link,
                data_eulerian_componentvalue=xml_escape(entity.absolute_url()),
            )
        )
        return template_context

    def properties_top(self, entity):
        website_link, email_link = None, None
        website_url = entity.printable_value("website_url")
        email = entity.printable_value("email")
        if website_url or email:
            eulerian = self.eulerian(entity)
            heading_hierarchy = f"recherche_>_{eulerian['document_title']}"
        if website_url:
            website_link = str(
                T.a(
                    website_url,
                    href=website_url,
                    target="_blank",
                    title=blank_link_title(self._cw, website_url),
                    rel="nofollow noopener noreferrer external",
                    klass="eulerian-button",
                    data_eulerian_actionname=f"external_link_{heading_hierarchy}",
                    data_eulerian_actionlabel="external_link,service,link,site_web,clic_lien",
                    data_eulerian_headinghierarchy=heading_hierarchy,
                    data_eulerian_componenthierarchy="main_>_section_>_list_>_link",
                    data_eulerian_componentlabel="site_web",
                    data_eulerian_componentvalue=xml_escape(website_url),
                )
            )
        if email:
            email_link = str(
                T.a(
                    email,
                    href="mailto:%s" % email,
                    klass="eulerian-button",
                    data_eulerian_actionname=f"external_link_{heading_hierarchy}",
                    data_eulerian_actionlabel="external_link,service,link,email,clic_mail",
                    data_eulerian_headinghierarchy=heading_hierarchy,
                    data_eulerian_componenthierarchy="main_>_section_>_list_>_link",
                    data_eulerian_componentlabel="email",
                    data_eulerian_componentvalue=xml_escape(email),
                )
            )
        return [
            (
                _("Name"),
                entity.printable_value("name") or entity.printable_value("name2"),
            ),
            (_("Phone number"), entity.printable_value("phone_number")),
            (_("Address"), xml_escape(entity.physical_address())),
            (_("Write to us"), entity.printable_value("mailing_address")),
            (_("Email"), email_link),
            (_("Website"), website_link),
        ]

    def get_logo(self, entity, service=None):
        logo = entity.illustration_url
        if logo:
            return {
                "src": logo,
            }

    def get_illustration(self, entity):
        return None


class FAComponentSearchResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("FindingAid", "FAComponent")

    def template_context(self, entity, es_response, max_highlights=3):
        template_context = super().template_context(
            entity, es_response, max_highlights=max_highlights
        )
        if entity.iiif_manifest:
            iiif_logo = {
                "alt": self._cw._(
                    "IIIF logo - this image will be displayd in IIIF-compatible viewer"
                ),
                "src": xml_escape(self._cw.uiprops["IIIF_LOGO"]),
            }
            template_context["iiif_logo"] = iiif_logo
        return template_context

    def get_service(self, entity):
        return entity.related_service

    def properties_top(self, entity):
        _ = self._cw._
        props = [
            (_("Cote"), entity.did[0].printable_value("unitid")),
            (_("Period"), entity.did[0].period),
        ]
        if entity.cw_etype == "FAComponent":
            props.append(
                (_("Fonds"), entity.finding_aid[0].view("incontext")),
            )
        return props


class CommemorationItemSearchResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("CommemorationItem")

    def properties_top(self, entity):
        dates = entity.dates
        if dates:
            yield (_("Period"), dates)
        else:
            yield (
                _("Modification date"),
                format_date(entity.modification_date, self._cw, fmt="d MMMM y"),
            )


class NewsSearchResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("NewsContent")

    def properties_top(self, entity):
        dates = entity.dates
        if dates:
            yield (_("Dates"), dates)
        else:
            yield (
                _("Modification date"),
                format_date(entity.modification_date, self._cw, fmt="d MMMM y"),
            )


class ExternRefSearchResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("ExternRef")

    def get_service(self, entity):
        return entity.service

    def entity_type(self, entity):
        return entity.etype

    def properties_top(self, entity):
        dates = entity.dates
        if dates:
            yield (_("Period"), dates)
        else:
            yield (
                _("Modification date"),
                format_date(entity.modification_date, self._cw, fmt="d MMMM y"),
            )


class BaseContentResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("BaseContent")

    def get_service(self, entity):
        return entity.service

    def entity_type(self, entity):
        return entity.etype

    def properties_top(self, entity):
        yield (_("Modification date"), entity.fmt_modification_date)

    def service_link(self, entity):
        services = entity.basecontent_service
        if services:
            return (
                self._cw._("publisher"),
                (" ;").join([service.view("incontext") for service in services]),
            )


class CardResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("Card")

    def properties_top(self, entity):
        yield (_("Modification date"), entity.fmt_modification_date)


class AuthoritiesResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance(
        "SubjectAuthority", "AgentAuthority", "LocationAuthority"
    )
    template = get_template("searchitem-authorities.jinja2")


class AuthorityRecordResultView(PniaTextSearchResultView):
    __select__ = PniaTextSearchResultView.__select__ & is_instance("AuthorityRecord")

    def get_service(self, entity):
        return entity.related_service

    def properties_top(self, entity):
        dates = entity.dates
        _ = self._cw._
        if dates:
            yield (_("Dates"), dates)
        if entity.abstract_text:
            yield (_("Description"), entity.abstract_text)
