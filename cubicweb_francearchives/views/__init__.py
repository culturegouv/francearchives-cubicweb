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

"""cubicweb-francearchives views/forms/actions/components for web ui"""

import os.path as osp

from urllib.parse import urlparse, parse_qs, urlunsplit, urlsplit

from babel import Locale
from cubicweb_web.bwcompat import CubicWebPyramidRequest

from jinja2 import Environment, PackageLoader

import yaml
from yaml.parser import ParserError

from cwtags import tag as T

from cubicweb.uilib import cut

from logilab.mtconverter import xml_escape
from logilab.common.decorators import monkeypatch

from cubicweb_web.views.basecomponents import RQLInputForm, MetaDataComponent
from cubicweb_web.views.basecontrollers import ViewController
from cubicweb_web.views.bookmark import BookmarksBox
from cubicweb_web.views.boxes import SearchBox, EditBox
from cubicweb_web.views.baseviews import InContextView, OutOfContextView
from cubicweb.uilib import remove_html_tags

from cubicweb_card.hooks import CardAddedView
from cubicweb_file.views import FileOutOfContext
from cubicweb_francearchives.redis_utils import get_data_with_cache
from cubicweb_francearchives.utils import format_number, is_external_link


_ = str

HERE = osp.dirname(__file__)
PORTAL_CONFIG = None

env = Environment(loader=PackageLoader("cubicweb_francearchives.views"))

STRING_SEP = "#####"


def get_template(template_name):
    return env.get_template(template_name)


def format_agent_date(cnx, date, precision="d", isbc=False, iso=True):
    year = date.year
    if isbc:
        template = "{{template}} {bc}".format(bc=cnx._("bc"))
        if iso:
            # https://en.wikipedia.org/wiki/ISO_8601#Years
            # 0000 is 1BC -0001 is 2BC and so on
            year += 1
    else:
        template = "{template}"
    if precision in ("d", "m"):
        lc = cnx.lang
        month = Locale(lc).months["format"]["wide"][date.month]
    else:
        month = ""
    return template.format(
        template={
            "d": "{date.day:2d} {month} {year:04d}",
            "m": "{month} {year:04d}",
            "y": "{year:04d}",
        }[precision].format(date=date, year=year, month=month)
    )


env.filters["format_number"] = format_number


def is_list(value):
    return isinstance(value, list)


env.filters["is_list"] = is_list


def get_subsections_infos(cnx, sections_eid):
    subsections = {eid: [] for eid in sections_eid}
    for parent_eid, subsection_eid, title_fr, title_lang in cnx.execute(
        """Any X, Y, TITLE_FR,  TITLE_LANG ORDERBY O
            WHERE X is Section,
            X eid in ({eids}), X children Y,
            E? translation_of Y, E language "{lang}",
            Y title TITLE_FR, Y short_description DESC_FR,
            E title TITLE_LANG, E short_description DESC_LANG,
            EXISTS (Y children Z), Y order O""".format(
            lang=cnx.lang, eids=",".join(str(x) for x in sections_eid)
        )
    ):
        subsections[parent_eid].append(
            [
                subsection_eid,
                cnx.entity_from_eid(subsection_eid).absolute_url(),
                title_lang or title_fr,
                [],
            ]
        )
    return subsections


def get_top_sections_infos(cnx):
    """retrieve info for the 4 top sections"""
    key = f"mainmenu_{cnx.lang}"
    return get_data_with_cache(cnx, key, _get_top_sections_infos)


def _get_top_sections_infos(cnx):
    top_sections = []
    query = f"""Any X, N, TITLE_FR, TITLE_LANG, DESC_FR, DESC_LANG,
                SUBTITLE_FR, SUBITLE_LANG ORDERBY O WHERE X is Section,
                X name N,
                E? translation_of X, E language "{cnx.lang}",
                X title TITLE_FR, X short_description DESC_FR, X subtitle SUBTITLE_FR,
                E title TITLE_LANG, E short_description DESC_LANG, E subtitle SUBITLE_LANG,
                X name IN (%s), X order O"""
    sections = {
        "rechercher": "search",
        "comprendre": "understand",
        "decouvrir": "discover",
        "gerer": "manage",
    }
    params = ",".join('"%s"' % s for s in sections.keys())
    rset = cnx.execute(query % params)
    if rset:
        infos = {e: (n, tl or tf, dl or df, sl or sf) for e, n, tf, tl, df, dl, sf, sl in rset}

        subsections_infos = get_subsections_infos(cnx, infos.keys())

        for top_section_eid in infos.keys():
            name, title, desc, label = infos.get(top_section_eid, (None, None, None, None))
            cssclass = sections[name]
            if title:
                # may not exist (in tests)
                children = []
                for subsection in subsections_infos[top_section_eid]:
                    subsection_info = subsection
                    children.append(subsection_info)

                top_sections.append(
                    (top_section_eid, title, label, name, cssclass, desc or "", children)
                )
        return top_sections
    return {}


class JinjaViewMixin(object):
    template = None

    def call_template(self, **ctx):
        self.w(self.template.render(**ctx))


@monkeypatch(CubicWebPyramidRequest)
def relative_path(self, includeparams=True):
    path = self._request.path_info[1:]
    if self.lang:
        langprefix = self.lang + "/"
        if path.startswith(langprefix):
            path = path[len(langprefix) :]
    if includeparams and self._request.query_string:
        return "%s?%s" % (path, self._request.query_string)
    return path


def load_portal_config(cwconfig):
    global PORTAL_CONFIG
    if PORTAL_CONFIG is None:
        lookup_paths = [
            osp.join(cwconfig.apphome, "portal_config.yaml"),
            osp.join(HERE, "portal_config.yaml"),
        ]
        for filepath in lookup_paths:
            if osp.isfile(filepath):
                try:
                    with open(filepath, "r") as f:
                        PORTAL_CONFIG = yaml.safe_load(f)
                        cwconfig.info("loaded portal config from file %r", filepath)
                        break
                except ParserError:
                    cwconfig.error("ignoring invalid yaml file %r", filepath)
        else:
            cwconfig.warning("failed to find a valid YAML portal config file")
            PORTAL_CONFIG = {}
    return PORTAL_CONFIG


def twitter_account_name(cwconfig):
    portal_config = load_portal_config(cwconfig)
    twitter_account_url = portal_config.get("sn", {}).get("twitter", {}).get("url", "")
    return "@" + twitter_account_url.rsplit("/", 1)[-1]


def rebuild_url(req, url=None, replace_keys=False, **newparams):
    """Override `cubicweb.req.RequestSessionbase.rebuild_url` implementation.

    This functions handle the multiselection of facets value.
    If a (parameter,value) pair already exists in the current query, the value
    is removed from the query parameter list.
    If replace_keys param is True, replace the key values

    For example, with
        - query={"param":["value"]}
        - newparams={"param":["value"]}
    the final query should be {}
    """
    if url is None:
        path = req.relative_path(includeparams=True)
        if req.lang:
            path = "{}/{}".format(req.lang, path)
        url = req.base_url() + path
    schema, netloc, path, query, fragment = urlsplit(url)
    query = parse_qs(query)
    # sort for testing predictability
    for key, val in sorted(newparams.items()):
        # <cw-patch>: remove query parameter if new value is None
        if val is None:
            query.pop(key, None)
        # </cw-patch>
        else:
            # remove the old values
            if replace_keys:
                query.pop(key, None)
            if not isinstance(val, (list, tuple)):
                val = (val,)
            # if param is already in query
            if key in query:
                # if param value exists in query, remove value from query
                for _val in val:
                    if _val in query[key]:
                        query[key].remove(_val)
                        # else, add param value to the param
                    else:
                        query[key].append(_val)

            # if param is not in query
            else:
                query[key] = val
    query = "&".join(
        "%s=%s" % (param, req.url_quote(value))
        for param, values in sorted(query.items())
        for value in values
    )
    return urlunsplit((schema, netloc, path, query, fragment))


def html_link(cnx, url, label=None, klass=None):
    if is_external_link(url, cnx.base_url()):
        return exturl_link(cnx, url, label=label, klass=klass)
    return internurl_link(cnx, url, label=label, klass=klass)


def internurl_link(cnx, url, label=None, klass=None, title=None):
    url = xml_escape(url)
    if label is None:
        label = url
    else:
        label = xml_escape(label)
    if title:
        return T.a(label, href=url, title=title, klass=klass or "fr-link")
    return T.a(label, href=url, klass=klass or "fr-link")


def exturl_link(cnx, url, label=None, klass=None, title=None, **kwargs):
    url = xml_escape(url)
    title = title or label
    if title:
        title = "{} - {}".format(title, cnx._("new window"))
    if label is None:
        label = url
        if title is None:
            title = blank_link_title(cnx, url)
    return T.a(
        label,
        klass=klass or "fr-link",
        href=url,
        target="_blank",
        rel="nofollow noopener noreferrer external",
        title=title,
        **kwargs,
    )


def blank_link_title(cnx, link=None):
    link = link or urlparse(link).netloc
    return f"{link} - {cnx._('new window')}"


@monkeypatch(InContextView)
def cell_call(self, row, col, **kwargs):
    entity = self.cw_rset.get_entity(row, col)
    entity = entity.cw_adapt_to("ITemplatable").entity_param()
    kwargs["href"] = xml_escape(entity.absolute_url())
    desc = cut(entity.dc_description(), 50)
    title = entity.dc_title()
    if desc and desc != title:
        kwargs["title"] = xml_escape(desc)
    entity_lang = getattr(entity, "lang", "fr")
    if self._cw.lang == entity_lang:
        self.w(T.a(xml_escape(title), **kwargs))
    else:
        with T.a(self.w, **kwargs):
            self.w(T.span(xml_escape(title), lang=entity_lang))


@monkeypatch(OutOfContextView)  # noqa
def cell_call(self, row, col, **kwargs):  # noqa
    entity = self.cw_rset.get_entity(row, col)
    entity = entity.cw_adapt_to("ITemplatable").entity_param()
    kwargs["href"] = xml_escape(entity.absolute_url())
    desc = cut(entity.dc_description(), 50)
    title = entity.dc_long_title()
    if desc and desc != title:
        kwargs["title"] = xml_escape(desc)
    entity_lang = getattr(entity, "lang", "fr")
    if self._cw.lang == entity_lang:
        self.w(T.a(xml_escape(title), **kwargs))
    else:
        with T.a(self.w, **kwargs):
            self.w(T.span(xml_escape(title), lang=entity_lang))


class SiteTourMixin(object):
    site_tour_url = None

    def call(self, **kwargs):
        self._cw.add_js("introjs/intro.min.js")
        self._cw.add_js("bundle-intro-tour.js")
        self._cw.add_css("introjs/introjs.min.css")
        self._cw.add_css("introjs/pnia.introjs.css")
        super(SiteTourMixin, self).call(**kwargs)

    def get_site_tour_url(self):
        if self.site_tour_url:
            return self._cw.build_url(self.site_tour_url)


class FaqMixin(object):
    faq_category = None

    def faqs_attrs(self):
        if not self.faq_category:
            return {}

        sql_query = """
        SELECT faq.cw_eid eid,
               TRANSLATE_ENTITY('FaqItem', faq.cw_eid, 'question', %(lang)s) AS question,
               TRANSLATE_ENTITY('FaqItem', faq.cw_eid, 'answer', %(lang)s) AS answer,
               faq.cw_category as category,
               faq.cw_order as order,
               faq.cw_question as fr_question,
               faq.cw_answer as fr_answer
        FROM cw_FaqItem AS faq WHERE faq.cw_category=%(c)s ORDER BY 4"""
        # TODO rewrite the TRANSLATE_ENTITY to return the actual entity language
        # and avoid comparing values
        rset = self._cw.cnx.system_sql(
            sql_query, {"c": self.faq_category, "lang": self._cw.lang}
        ).fetchall()
        if rset:
            faqs = []
            fr_lang = self._cw.lang == "fr"
            for eid, question, answer, category, order, fr_question, fr_answer in rset:
                qlang_attr = 'lang="fr"' if not fr_lang and question == fr_question else ""
                alang_attr = 'lang="fr"' if not fr_lang and answer == fr_answer else ""
                faq_url = self._cw.build_url("faqitem/{}".format(eid))
                faqs.append(
                    (eid, faq_url, remove_html_tags(question), answer, qlang_attr, alang_attr)
                )
            return {
                "faqs": faqs,
                "category": self.faq_category,
                "faq_url": self._cw.build_url("faq"),
                "faq_label": self._cw._("See all FAQs"),
            }
        return {}


def add_js_translations(req):
    js_i18n_url = req.build_url(
        "appstatic/{}/i18n/{}.js".format(req.vreg.config.instance_md5_version(), req.lang)
    )
    req.html_headers.jsfiles.insert(0, {"src": js_i18n_url})


class ControllerWithCSRFCheckDisabled(ViewController):
    require_csrf = False


class FAFileOutOfContext(FileOutOfContext):

    def cell_call(self, row, col):
        entity = self.cw_rset.get_entity(row, col)
        url = entity.cw_adapt_to("IDownloadable").download_url()
        self.w(
            f'<a class="fr-link fr-link--download" download href="{url}">'
            + entity.dc_title()
            + "</a>"
        )


def registration_callback(vreg):
    vreg.register_all(
        list(globals().values()), __name__, (ControllerWithCSRFCheckDisabled, FAFileOutOfContext)
    )
    vreg.unregister(BookmarksBox)
    vreg.unregister(SearchBox)
    vreg.unregister(RQLInputForm)
    vreg.unregister(EditBox)
    vreg.unregister(MetaDataComponent)
    vreg.unregister(CardAddedView)
    vreg.register_and_replace(ControllerWithCSRFCheckDisabled, ViewController)
    vreg.register_and_replace(FAFileOutOfContext, FileOutOfContext)
