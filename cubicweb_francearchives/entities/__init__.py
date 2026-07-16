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

"""cubicweb-francearchives entity's classes"""

from collections import defaultdict

import hashlib

from logilab.common.decorators import cachedproperty

from cubicweb import _

from cubicweb_card.entities import Card as BaseCard
from cubicweb_file.entities import File as BaseFile


from cubicweb_skos.entities import Concept as BaseConcept
from rdflib.graph import ConjunctiveGraph

from cubicweb.entity import _marker
from cubicweb.entities import fetch_config

from cubicweb_francearchives import SUPPORTED_LANGS
from cubicweb_francearchives.utils import format_date, formatted_size, is_external_link
from cubicweb_francearchives.xmlutils import (
    process_html_as_xml,
    add_title_on_external_link,
    add_title_on_internal_link,
)
from cubicweb_francearchives.xy import add_statements_to_graph


ETYPE_CATEGORIES = {
    "Circular": _("siteres"),
    "Service": _("siteres"),
    "NewsContent": _("siteres"),
    "BaseContent": _("siteres"),
    "ExternRef": _("siteres"),
    "Section": _("siteres"),
    "Map": _("siteres"),
    "Card": _("siteres"),
    "CommemorationItem": _("siteres"),
    "FindingAid": _("archives"),
    "FAComponent": _("archives"),
    # "AuthorityRecord": _("archives"),
    # for the moment don't show AuthorityRecord in global search
}

DOC_CATEGORY_ETYPES = defaultdict(list)
for etype, category in list(ETYPE_CATEGORIES.items()):
    DOC_CATEGORY_ETYPES[category].append(etype)


@process_html_as_xml
def enhance_rgaa(root, cnx, labels=None):
    """take html as first argument `root`. This argument is then transformed
    in etree root by process_html_as_xml
    """
    for node in root.xpath("//*[@href]"):
        if is_external_link(node.attrib["href"], cnx.base_url()):
            add_title_on_external_link(cnx, node)
        else:
            add_title_on_internal_link(cnx, node)


class HTMLMixIn(object):
    @cachedproperty
    def richstring_attrs(self):
        attrs = []
        subjrels = self._cw.vreg.schema.entity_schema_for(self.cw_etype).subject_relations
        for rel in subjrels:
            if rel.type.endswith("_format"):
                attr = rel.type.split("_format")[0]
                if attr in subjrels:
                    attrs.append(attr)
        return attrs

    def printable_value(
        self, attr, value=_marker, attrtype=None, format="text/html", displaytime=True
    ):
        """return a displayable value (i.e. unicode string) which may contains
        html tags. ̀enhance_rgaa`  may retrun None
        """
        value = super(HTMLMixIn, self).printable_value(attr, value, attrtype, format, displaytime)
        if value and attr in self.richstring_attrs:
            return enhance_rgaa(value, self._cw) or ""
        return value


class Concept(BaseConcept):
    uuid_attr = "cwuri"

    @property
    def uuid_value(self):
        return self.cwuri

    @property
    def lang(self):
        return "fr"

    @property
    def schema_label(self):
        rset = self._cw.execute(
            "Any ST, LL, URI WHERE X eid %(eid)s, X in_scheme S, S title ST, "
            "X cwuri URI, X preferred_label L, L label LL, L language_code LC",
            {"eid": self.eid},
        )
        if rset:
            return rset[0][0]
        return self.scheme.dc_title()


class Card(HTMLMixIn, BaseCard):
    uuid_attr = "wikiid"

    def rest_path(self):
        if "-" in self.wikiid:
            return self.wikiid.split("-")[0]
        return self.wikiid

    def dc_title(self):
        """override default implementation to never consider wikiid in title"""
        return self.title

    @property
    def uuid_value(self):
        return self.wikiid

    @cachedproperty
    def fmt_creation_date(self):
        return format_date(self.creation_date, self._cw, fmt="d MMMM y")

    @property
    def fmt_modification_date(self):
        return format_date(self.modification_date, self._cw, fmt="d MMMM y")

    @property
    def lang(self):
        """try to retrive the card's language from its wikiid"""
        try:
            lang = self.wikiid.split("-")[-1]
        except ValueError:
            return "fr"
        if lang in SUPPORTED_LANGS:
            return lang
        return "fr"


def system_source_absolute_url(self, *args, **kwargs):
    """override default absolute_url to avoid calling cw_metainformation"""
    # use *args since we don't want first argument to be "anonymous" to
    # avoid potential clash with kwargs
    if args:
        assert len(args) == 1, "only 0 or 1 non-named-argument expected"
        method = args[0]
    else:
        method = None
    if method in (None, "view"):
        kwargs["_restpath"] = self.rest_path()
    else:
        kwargs["rql"] = "Any X WHERE X eid %s" % self.eid
    return self._cw.build_url(method, **kwargs)


def systemsource_entity(cls):
    setattr(cls, "absolute_url", system_source_absolute_url)
    return cls


def compute_file_data_hash(value):
    return str(hashlib.sha1(value).hexdigest())


class FAFile(BaseFile):
    fetch_attrs, cw_fetch_order = fetch_config(["data_name", "title", "data_hash"])
    rest_attr = "data_hash"

    def dc_title(self):
        return self.title or self.data_name

    def bfss_storage_relpath(self, attr):
        content_hash = self.cw_attr_metadata(attr, "hash")
        if content_hash is None:
            content_hash = self.compute_hash()
        name = self.cw_attr_metadata(attr, "name")
        return "{}_{}".format(content_hash, name)

    def absolute_url(self):
        idownloadable = self.cw_adapt_to("IDownloadable")
        return idownloadable.download_url()

    def rest_path(self):
        etype = str(self.e_schema)
        path = etype.lower()
        hash = self.data_hash or self.compute_hash()
        return "%s/%s" % (path, self._cw.url_quote(hash))

    def compute_hash(self, value=None):
        """this is the copy of the cubicweb_file.entity.compute_sha1hex method from
        v. 2.0.1.

        We keep this code in order to continue to generate the ̀data_hash` as
        previously whithout '{sha1}' prefix to avoid generating
        `download_url` and filepath whith '{sha1}' prefix.

        Exemple:

        1/ cubicweb_file < 2.1.0:
             url: ../file/OaOaOaOa/data_name
             filepath: applfile/OaOaOaOa/data_name

        2/ cubicweb_file >= 2.1.0:
             url: ../file/{sha1}OaOaOaOa/data_name
             filepath: applfile/{sha1}OaOaOaOa/data_name

        """
        if value is None and self.data is not None:
            value = self.data.getvalue()
        # we assume self._cw.vreg.config['hash-algorithm'] must be "sha1", thus
        # we dont check it
        if value is not None:
            return compute_file_data_hash(value)

    def check_hash(self):
        """rewrite v.2.0.1 cubicweb_file.entity.check_hash method to
        be complient with the `compute_hash` method implementatio
        """
        if self.data_hash:
            value = self.data and self.data.getvalue()
            return self.data_hash == self.compute_hash(value)
        return True

    def formatted_size(self):
        """
        Convert file size in a human read
        """
        try:
            data_size = self.size()
        except Exception as err:
            self.error("Could not retrieve the file %s: %s", self, err)
            return ""
        return formatted_size(self._cw, data_size)

    def get_filepath(self, attr):
        """
        return filepath key for s3 or filepath for BFSS
        """
        rset = self._cw.execute("Any FSPATH(D) WHERE X eid %s, X %s D" % (self.eid, attr))
        key = rset.rows[0][0].getvalue()
        if isinstance(key, bytes):
            key = key.decode("utf-8")
        return key

    @property
    def lang(self):
        return "fr"


def entity2schemaorg(entity):
    sorg = entity.cw_adapt_to("rdf.schemaorg")
    if sorg is not None:
        graph = ConjunctiveGraph()
        add_statements_to_graph(graph, sorg)
        context = {prefix: str(ns) for prefix, ns in sorg.used_namespaces.items()}
        return graph.serialize(format="json-ld", context=context, indent=2)
    return None


def entity2meta(entity):
    meta = entity.cw_adapt_to("IMeta")
    if meta is not None:
        return meta.meta_data()
    return ()


def entity2opengraph(entity):
    og = entity.cw_adapt_to("IOpenGraph")
    if og is not None:
        return og.og_data()
    return ()
