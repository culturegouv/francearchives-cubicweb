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
from itertools import chain

from glamconv.utils import NS, split_qname
from glamconv.ead.utils import log_element
from glamconv.transformer.actions import TransformAction
from glamconv.ead.formats import EAD_2002
from glamconv.transformer.parameters import SingleParameter

from glamconv.transformer.libraries import register_action

from cubicweb_francearchives.utils import is_absolute_url


class EADIDTransformer(TransformAction):
    applicable_for = (EAD_2002,)
    uid = "francearchives-eadid-transformer"
    name = "Transform eadid tag"
    category = "Header"
    desc = "Set a new <eadid> url attribute value is no exists" ""
    params_def = (
        SingleParameter(
            "eadid_url",
            "Eadid Url",
            "Url inserted as <eadid> element url attribute value if no exists " "content.",
            "Text",
            str,
            "",
        ),
    )

    def _execute(self, xml_root, logger, log_details, eadid_url):
        for eadid in xml_root.xpath(".//eadid"):
            if not eadid.attrib.get("url"):
                eadid.set("url", eadid_url)
        return xml_root


class XLinkAttribSetter(TransformAction):
    applicable_for = (EAD_2002,)
    uid = "francearchives-xlink-setter"
    name = "Using xlink attributes in links"
    category = "Links & Refs"
    desc = (
        "This action transforms the attributes of <bibref>, <extprt>, "
        "<extref> and <dao> elements that describe the links into the "
        "corresponding xlink attributes."
    )

    def _execute(self, xml_root, logger, log_details):
        count = 0
        if log_details:
            log_data = []
        names = (
            "bibref",
            "extptr",
            "extref",
            "dao",
        )
        xpath_req = " | ".join([".//{0}".format(eltname) for eltname in names])
        attrs = ("actuate", "arcrole", "href", "role", "show", "title")
        actuate_conv = {
            "onload": "onLoad",
            "onrequest": "onRequest",
            "actuatenone": "none",
            "actuateother": "other",
        }
        show_conv = {
            "new": "new",
            "embed": "embed",
            "showother": "other",
            "shownone": "none",
            "replace": "replace",
        }
        for elt in xml_root.xpath(xpath_req):
            # Link is always a simple link in Ape-EAD
            elt.attrib.pop("type", None)
            elt.set("{{{xlink}}}type".format(**NS), "simple")
            # Collect the links in href and xlink:href and only keep the
            # absolute link (starting with "http"). If both are absolute,
            # keep the xlink:href one
            links = []
            for nspace in (NS["xlink"], ""):
                attname = "{{{}}}href".format(nspace)
                lnk = elt.attrib.get(attname)
                if lnk is not None and lnk.startswith("http"):
                    links.append(lnk)
            if len(links) > 1:
                num = 1
                if "href" in elt.attrib:
                    elt.attrib.pop("href")
                elt.set("{{{}}}href".format(NS["xlink"]), links[0])
            num = 0
            # Process all the attributes but href and set the xlink attributes
            for attname in elt.attrib:
                namespace, name = split_qname(attname)
                if namespace == NS["xlink"] or name not in attrs:
                    continue
                num = 1
                xlink_name = "{{{0}}}{1}".format(NS["xlink"], name)
                # Delete attribute but keep its value
                attvalue = elt.attrib.pop(attname)
                if namespace != NS["xlink"] and xlink_name in elt.attrib:
                    # If already have a xlink attribute with the same local
                    # name, keep this xlink attribute and forget the current
                    # one
                    continue
                if name == "actuate":
                    attvalue = actuate_conv.get(attvalue)
                elif name == "show":
                    attvalue = show_conv.get(attvalue)
                if attvalue is not None:
                    elt.set(xlink_name, attvalue)
            count += num
            if log_details and num > 0:
                log_data.append(log_element(elt, attributes=("xlink:href",)))
        if count > 0:
            logger.warning(
                "{0:d} elements describing a link have had their attributes "
                "transformed into xlink attributes.".format(count)
            )
            if log_details:
                logger.warning("The following elements have been modified:", "\n".join(log_data))
        return xml_root


class XLinkAdjuster(TransformAction):
    applicable_for = (EAD_2002,)
    uid = "francearchives-xlink-adjuster"
    name = "Remove <extptr>, <dao>, <daoloc> with relative href"
    category = "Links & Refs"
    desc = "Remove <extptr>, <dao>, <daoloc> with relative href"

    def _execute(self, xml_root, logger, log_details):
        to_remove = set()
        tags = (
            "archref",
            "bibref",
            "dao",
            "daoloc",
            "extptr",
            "extptrloc",
            "extref",
            "extrefloc",
            "ptrloc",
            "refloc",
            "title",
        )
        elts = chain(xml_root.xpath(".//{}".format(tag)) for tag in tags)
        for elts_list in elts:
            for elt in elts_list:
                _, name = split_qname(elt.tag)
                url = elt.get("{{{xlink}}}href".format(**NS), None)
                if url and not is_absolute_url(url):
                    to_remove.add(elt)
        if len(to_remove) > 0:
            for elt in to_remove:
                elt.getparent().remove(elt)
            logger.warning(
                "Remove relative internal links. {0:d} elements "
                "have been removed.".format(len(to_remove))
            )
            if log_details:
                logger.warning("The following elements have been removed:", "\n".join(to_remove))
        return xml_root


def register_ead_actions():
    register_action(EADIDTransformer, EAD_2002.uid)
    register_action(XLinkAdjuster, EAD_2002.uid)
    register_action(XLinkAttribSetter, EAD_2002.uid)
