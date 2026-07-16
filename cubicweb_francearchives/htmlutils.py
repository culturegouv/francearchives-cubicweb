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

from lxml import etree, html
from lxml.html import clean

from cubicweb.uilib import REM_ROOT_HTML_TAGS, ALLOWED_TAGS

# allow the style attribute
SAFE_ATTRS = html.defs.safe_attrs | {
    "style",
    "lang",
    "hreflang",
    "frameborder",
    "allowfullscreen",
    "aria-label",
    "aria-labelledby",
    "aria-controls",
    "aria-expanded",
    "data-label-expand",
    "data-label-collapse",
    "data-fr-opened",
    "data-fr-js-collapse-button",
    "data-fr-js-collapse",
    "data-fr-js-modal",
    "data-fr-js-modal-body",
    "data-fr-js-modal-button",
    "role",
}

CLEANER = clean.Cleaner(
    allow_tags=ALLOWED_TAGS | {"iframe", "figure", "figcaption", "button"},
    remove_unknown_tags=False,
    safe_attrs=SAFE_ATTRS,
    add_nofollow=False,
    forms=False,
    embedded=False,
)


def soup2xhtml(data, encoding):
    """tidy html soup by allowing some element tags and return the result"""
    # remove spurious </body> and </html> tags, then normalize line break
    # (see http://www.w3.org/Protocols/rfc2616/rfc2616-sec3.html#sec3.7.1)
    data = REM_ROOT_HTML_TAGS.sub("", "\n".join(data.splitlines()))
    xmltree = etree.HTML(CLEANER.clean_html("<div>%s</div>" % data))
    # NOTE: lxml 2.0 does support encoding='unicode', but last time I (syt)
    # tried I got weird results (lxml 2.2.8)
    body = etree.tostring(xmltree[0], encoding=encoding, method="html")
    # remove <body> and </body> and decode to unicode
    snippet = body[6:-7].decode(encoding)
    # take care to bad xhtml (for instance starting with </div>) which
    # may mess with the <div> we added below. Only remove it if it's
    # still there...
    if snippet.startswith("<div>") and snippet.endswith("</div>"):
        snippet = snippet[5:-6]
    return snippet
