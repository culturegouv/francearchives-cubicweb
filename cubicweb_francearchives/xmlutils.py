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

"""xml utility functions"""
import hashlib
from jinja2 import Environment, PackageLoader

import logging

from lxml import etree
from lxml import html as lxml_html
from lxml.builder import E
import re

import requests
from urllib.parse import urljoin, urlsplit
from .utils import is_external_link

from cubicweb_francearchives import get_user_agent
from cubicweb_francearchives.utils import remove_html_tags

env = Environment(loader=PackageLoader("cubicweb_francearchives.views"))

XMLParser = etree.XMLParser(load_dtd=False, resolve_entities=False)


def to_unicode(el):
    return lxml_html.tostring(el, encoding="unicode")


def log(msg, eid=None):
    try:
        if eid:
            msg = "Entity {}: {}".format(eid, msg)
        logging.getLogger("xmltulils").warn(msg)
    except Exception:
        pass


def process_html_as_xml(func):
    def wrapper(html, *args, **kwargs):
        if not html:
            return None
        # security belt
        stripped = html.strip()
        if not stripped:
            return html
        if not stripped.startswith("<"):
            return html
        if stripped.startswith("<body"):
            return html
        # add a wrap to ensure a parent for top elements
        html = f"<div>{stripped}</div>"
        try:
            fragments = lxml_html.fragments_fromstring(html)
        except Exception as err:
            eid = kwargs.get("eid")
            log("Invalid html: {}".format(err), eid)
            return html
        if fragments:
            func(fragments[0], *args, **kwargs)
        snippet = "".join(to_unicode(fragment) for fragment in fragments)
        if snippet.startswith("<div>") and snippet.endswith("</div>"):
            snippet = snippet[5:-6]
        return snippet

    return wrapper


FRFILE = re.compile(r"../file/(\w+)/(.*)")


def is_francearchive_relatif_link(href):
    match = FRFILE.match(href)
    if match:
        return True
    return False


def clean_external_link(cnx, node):
    node.set("rel", "nofollow noopener noreferrer external")
    node.set("target", "_blank")


def add_title_on_external_link(cnx, node):
    title = node.text_content()
    if not title:
        return
    attr_title = node.attrib.get("title")
    new_window = cnx._("new window")
    if attr_title is None:
        node.set("title", " - ".join([title, new_window]))
    else:
        titles = []
        if title.lower() not in attr_title.lower():
            titles.append(title)
        if attr_title:
            titles.append(attr_title)
        if new_window.lower() not in attr_title.lower():
            titles.append(new_window)
        if len(titles) > 1:
            node.set("title", " - ".join(titles))


def clean_internal_link(cnx, node):
    """remove target and rel if exists"""
    for attr in ("rel",):
        if node.attrib.get(attr):
            node.attrib.pop(attr)


def add_title_on_internal_link(cnx, node):
    """add the link title in title attribute is exists"""
    title = node.text_content()
    if not title:
        return
    attr_title = node.attrib.get("title") or ""
    if attr_title:
        if title.lower() not in attr_title.lower():
            node.set("title", " - ".join(t for t in [title, attr_title] if t))


def clean_fa_link(node, href):
    """
    clean wrong internal urls,
    remove trailing # et "edit" added by users

    cf. https://extranet.logilab.fr/ticket/74004621
    """
    for end in ("#/edit", "/", "#"):
        href = re.sub(f"{end}$", "", href)
        if node.attrib.get("href") != href:
            node.set("href", href)


def fix_links(root, cnx, *args, **kwargs):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml

    also clean wrong internal urls

    """
    base_url = cnx.base_url()
    for node in root.xpath("//a"):
        attribs = node.attrib
        # remove empty title
        title = attribs.get("title", None)
        if title is not None and not title.strip():
            attribs.pop("title")
        # remove title identical to the link's label
        content = node.text_content()
        if title is not None and title == content:
            attribs.pop("title")
        href = attribs.get("href")
        if href is None:
            if attribs.get("name") is None:
                log(
                    ("Invalid link tag with missing href: " 'content "{}", attrs"{}"').format(
                        repr(node.text_content()), repr(attribs)
                    ),
                    kwargs.get("eid"),
                )
        else:
            if is_external_link(href, base_url):
                clean_external_link(cnx, node)
            else:
                clean_fa_link(node, href)
                clean_internal_link(cnx, node)
        # change the image alt
        images = node.xpath(".//child::img")
        for image in images:
            image.set("alt", content)
        if images:
            css_class = attribs.get("class", "")
            if "image-link" not in css_class:
                if css_class:
                    css_class = "{} image-link".format(css_class)
                else:
                    css_class = "image-link"
                node.set("class", css_class)


def fix_images(root, *args, **kwargs):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml
    """
    for i, node in enumerate(root.xpath("//img")):
        # add data on figure
        parent = node.getparent()
        if parent.tag == "figure":
            parent.set("role", "figure")
            caption = parent.find("figcaption")
            if caption is not None:
                caption.set("id", f"caption_{i + 1}")
                parent.set("aria-labelledby", caption.attrib.get("id"))
        # node.set("class", "fr-responsive-img")
        attribs = node.attrib
        # add an empty alt rgaa 3.1
        alt = ""
        if "alt" not in attribs:
            attribs["alt"] = alt
            # rgaa 3.2
            if "title" in attribs:
                attribs.pop("title")
        else:
            # 3.3 alt must be relevent
            filename = attribs["src"].rsplit("/", 1)[-1]
            alt = attribs["alt"].strip()
            if alt == filename.strip():
                attribs["alt"] = ""
        # 3.3 alt and title must be identical is title exists
        if "title" in attribs:
            title = attribs["title"].strip()
            if not title:
                attribs.pop("title")
            elif title != alt:
                attribs["title"] = alt


@process_html_as_xml
def enhance_accessibility(html, cnx, *args, **kwargs):
    fix_links(html, cnx, *args, **kwargs)
    fix_images(html, *args, **kwargs)


def add_subtitles_html(root, cnx, **kwargs):
    transcripts = root.xpath("//div[@class='media-subtitles' or @class='media-subtitles hidden']")
    if len(transcripts) == 0:
        return
    #  load the jija_template for transcripts
    template = env.get_template("transcript.jinja2")
    lang = kwargs.get("lang", None)
    # change the language for translations
    if lang:
        old_lang = cnx.lang
        cnx.set_language(lang)
    transcription_label = cnx._("Transcript")
    close_label = cnx._("Close")
    enlarge_label = cnx._("Enlarge")
    enlarge_transcription_label = cnx._("Enlarge the transcript")
    for node in root.xpath('//div[@class="media-subtitles-button"]'):
        # remove old code
        node.getparent().remove(node)
    for idx, node in enumerate(transcripts):
        node_id = f"{hashlib.sha1(etree.tostring(node, encoding='utf8')).hexdigest()}"
        node.attrib.pop("class")
        node.set("class", "fa-transcript")
        data = {
            "id": node_id,
            "transcription_label": transcription_label,
            "close_label": close_label,
            "enlarge_label": enlarge_label,
            "enlarge_transcription_label": enlarge_transcription_label,
            "data": to_unicode(node),
        }
        html = template.render(data)
        try:
            fragments = lxml_html.fragments_fromstring(html)
        except Exception as err:
            log("add_subtitles_html: Invalid html: {}".format(err))
            continue
        if len(fragments) == 0:
            log("add_subtitles_html: no html has been generated")
            continue
        elem = fragments[0]
        # add class class="fr-modal__title" to title
        title = elem.xpath("//h1")
        if len(title) > 0:
            title[0].set("class", "fr-modal__title")
        node.getparent().replace(node, elem)
    if lang:
        cnx.set_language(old_lang)


@process_html_as_xml
def handle_subtitles(root, cnx, **kwargs):
    add_subtitles_html(root, cnx, **kwargs)


def remove_all_styles(node):
    """remove somes attributes from a node and all its descendents"""
    # node.attrib.pop("style", None)
    node.attrib.pop("border", None)
    for child in node.getchildren():
        remove_all_styles(child)


def tables_to_dsfr_html(root, cnx, **kwargs):
    """add DSFR tags and css classes to tables"""
    tables = root.xpath("//table")
    for table in tables:
        remove_all_styles(table)
        parent = table.getparent()
        if "fr-table__content" in parent.attrib.get("class", ""):
            continue
        table.attrib.pop("style", None)
        new_parent = E.div({"class": "fr-table__content"})
        new_table = E.div(
            E.div(
                E.div(new_parent, {"class": "fr-table__container"}),
                {"class": "fr-table__wrapper"},
            ),
            {"class": "fr-table fr-table--bordered fr-table--no-scroll"},
        )
        parent.replace(table, new_table)
        new_parent.append(table)


@process_html_as_xml
def handle_tables(root, cnx, **kwargs):
    tables_to_dsfr_html(root, cnx, **kwargs)


def insert_labels(cnx, root, labels):
    for label in labels:
        _class = "ead-section ead-%s" % label

        for parent in root.xpath("//div[@class='%s']" % _class):
            # test the empty parent
            if not any(r.strip() for r in parent.xpath(".//child::*/text()")):
                continue
            if not parent.xpath(".//div[@class='ead-label']"):
                div = '<p class="ead-label">%s</p>' % cnx._("%s_label" % label)
                parent.insert(0, etree.XML(div))


def translate_labels(cnx, root):
    for node in root.xpath("//div[@class='ead-label']"):
        node.text = cnx._(node.text)


@process_html_as_xml
def fix_fa_external_links(root, cnx, labels=None):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml.

    This method is used to modify links on the fly in views"""
    nodes = root.xpath("//*[@href]")
    tobe_removed = []
    for node in nodes:
        href = node.attrib["href"]
        if href.startswith("//"):
            node.set("href", "http:{}".format(href))
            href = node.attrib["href"]
        if is_external_link(href, cnx.base_url()):
            # add _blank target and new window
            clean_external_link(cnx, node)
            add_title_on_external_link(cnx, node)
        elif is_francearchive_relatif_link(href):
            rel = node.attrib.get("rel")
            if rel == "nofollow noopener noreferrer":
                del node.attrib["rel"]
            if "target" in node.attrib:
                del node.attrib["target"]
        else:
            # remove links with relative path
            # (cf. https://extranet.logilab.fr/ticket/54134093)
            tobe_removed.append(node)
    for node in tobe_removed:
        try:
            node.getparent().remove(node)
        except Exception:
            pass
    if labels:
        insert_labels(cnx, root, labels)
    else:
        translate_labels(cnx, root)


def a11y_rewrite_divs(node):
    """acessibility: transform <div class="ead-p ead-wrapper"> into <p> or <ul>"""
    children = node.getchildren()
    if not len(children) or not [s for s in children if s.tag in ("p", "div")]:
        if node.tag == "br":
            node.set("aria-hidden", "true")
            return
        if node.tag in ("i, b"):
            node.set("class", f"ead-{node.tag}")
        node.tag = "p"
        if children and children[0].tag == "li":
            node.tag = "ul"
            node.set("class", "fr-list")
    else:
        transform = True
        for sub_node in children:
            if sub_node.tag not in ("span", "i", "b", "br"):
                transform = False
            else:
                if sub_node.tag != "br":
                    sub_node.tag = "p"
                else:
                    sub_node.set("aria-hidden", "true")
                continue
            if sub_node.tag == "p":
                continue
            if sub_node.tag == "div":
                sub_children = sub_node.getchildren()
                if not sub_children or not [s for s in sub_children if s.tag in ("p", "div")]:
                    sub_node.tag = "p"
                    transform = False
                for child in sub_children:
                    if child.tag == "div":
                        a11y_rewrite_divs(child)
                    if child.tag == "br":
                        child.set("aria-hidden", "true")

        if transform:
            node.tag = "p"


@process_html_as_xml
def fix_ead_divs(root, cnx):
    # for node in root.xpath('//div[@class="ead-p"]'):
    #     a11y_rewrite_divs(node)
    for node in root.xpath('//div[@class="ead-wrapper"]'):
        a11y_rewrite_divs(node)


def ping_uri(uri):
    headers = {
        "user-agent": get_user_agent(),
    }
    response = requests.head(uri, headers=headers, allow_redirects=True, timeout=4)
    if response.status_code >= 400:
        return f"{response.status_code} {response.reason}"
    return None


def detect_wrong_editorial_links(root, cnx, data, *args, **kwargs):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml

    also clean wrong internal urls

    """
    for node in root.xpath("//a"):
        attribs = node.attrib
        href = attribs.get("href")
        if href is None:
            continue
        if href.startswith("mailto"):
            continue
        base_url = cnx.base_url()
        schema, netloc, path, query, fragment = urlsplit(href)
        # francearchives.gouv.fr is considered as a wrong link
        try:
            rebuilt_url = urljoin(base_url, href) if not schema else href
            ping_result = ping_uri(rebuilt_url)
            if ping_result is not None:
                data.append((node.text, href, ping_result))
                continue

        except Exception as exc:
            data.append((node.text, href, exc.__class__.__name__))
            pass


@process_html_as_xml
def get_broken_editorial_links(html, cnx, data, *args, **kwargs):
    detect_wrong_editorial_links(html, cnx, data, *args, **kwargs)


def format_html(cnx, html, text_format="text/html"):
    if html and remove_html_tags(html).strip():
        if text_format != "text/html":
            # XXX use mtc_transform
            return remove_html_tags(html).strip()
        return html
    return None


def process_html(cnx, html, text_format="text/html", labels=None):
    if html:
        processed = fix_fa_external_links(html, cnx, labels)
        processed = fix_ead_divs(processed, cnx)
        if processed:
            return format_html(cnx, processed, text_format)
    return html


XSS_CLEAN_RE = re.compile(
    r"<\s*/?\s*(script|a|javascript|img|body|input|style|svg|bgsound|br|xss|marqee|audio|button|form)\s*>",  # noqA
    re.IGNORECASE,
)


def clean_xss(value, cnx, **kwargs):
    """remove same dangerous tags from plain text string to avoid XSS vulnerabilities"""
    if value is None:
        return value
    value = value.strip()
    if not value:
        return value
    return XSS_CLEAN_RE.sub("", value)


def insert_link_to_text(root, cnx, *args, **kwargs):
    """Insert a@href before the a text

    :param string html: html to be transformed in etree root by process_html_as_xml
    :param Connection cnx: connection
    """
    nodes = root.xpath("//*[@href]")
    for node in nodes:
        href = node.attrib["href"]
        node.text = f"({href}) {node.text}"


def process_html_for_csv(html, cnx):
    """Remove html tags. Extract and keep same information from html tags

    :param Element root: html transformed in etree Element by process_html_as_xml
    :param Connection cnx: connection
    """
    if html is None:
        return None
    try:
        # Etree does not like HTML without a single root element
        # so we need to wrap it inside a div.
        tree = etree.fromstring("<div>{}</div>".format(html))
    except etree.XMLSyntaxError:
        return remove_html_tags(html.strip())
    insert_link_to_text(tree, cnx)
    return " ".join(tree.xpath("//text()")).strip()
