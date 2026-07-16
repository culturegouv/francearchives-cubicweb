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
from lxml import etree

from logilab.mtconverter import xml_escape

from cubicweb.predicates import is_instance

from cubicweb.entity import EntityAdapter

from cubicweb_file.entities import FileIDownloadableAdapter

from cubicweb_francearchives.xmlutils import (
    process_html,
)


class FAFileAdapter(FileIDownloadableAdapter):
    def ape_service_code(self):
        rset = self._cw.execute(
            "Any C WHERE FA ape_ead_file X, X eid %(e)s, " "FA service S, S code C",
            {"e": self.entity.eid},
        )
        if rset:
            return rset[0][0]

    def download_url(self, **kwargs):
        service_code = self.ape_service_code()
        name = self._cw.url_quote(self.download_file_name())
        rest_path = self.entity.rest_path()
        if service_code:
            path = "%s/ape-ead/%s/%s" % (rest_path, service_code, name)
        else:
            path = "%s/%s" % (rest_path, name)
        return self._cw.build_url(path, **kwargs)

    def download_file_name(self):
        return self.entity.data_name


class IPublisherInfoAdapter(EntityAdapter):
    __regid__ = "IPublisherInfo"
    __abstract__ = True

    @property
    def service(self):
        return self.entity.related_service

    @property
    def publisher_title(self):
        return self.entity.publisher_title

    @property
    def bounce_url(self):
        return False

    @property
    def publisher_label(self):
        return self._cw._("Conservation institutions: ")

    def serialize(self):
        _ = self._cw._
        service = self.service
        publisher_params = {}
        if service:
            publisher_params = {
                "contact_url": xml_escape(service.absolute_url()),
                "contact_label": _("Contact_label"),
            }
        publisher_params["title"] = self.publisher_title
        publisher_params["title_label"] = self.publisher_label
        if self.bounce_url:
            publisher_params.update(
                {"site_label": _("Access to the site"), "site_url": xml_escape(self.bounce_url)}
            )
        return publisher_params


class IRIPublisherInfoAdapter(IPublisherInfoAdapter):
    __select__ = IPublisherInfoAdapter.__select__ & is_instance("FindingAid", "FAComponent")

    @property
    def bounce_url(self):
        return self.entity.bounce_url


class AuthorityRecordIPublisherInfoAdapter(IPublisherInfoAdapter):
    __select__ = IPublisherInfoAdapter.__select__ & is_instance("AuthorityRecord", "NominaRecord")

    @property
    def publisher_label(self):
        return self._cw._("Notice author :")

    @property
    def publisher_title(self):
        return self.service.dc_title()


class EntityMainPropsAdapter(EntityAdapter):
    __regid__ = "entity.main_props"
    __abstract__ = True

    def properties(self, export=False, vid="incontext", text_format="text/html"):
        raise NotImplementedError()

    def clean_value(self, entity, attr):
        """skip data containing html tags without actual value"""
        return process_html(self._cw, entity.printable_value(attr), text_format=self.text_format)


def substitute_xml_prefix(prefix_name, namespaces):
    """Given an XML prefixed name in the form `'ns:name'`, return the string `'{<ns_uri>}name'`
    where `<ns_uri>` is the URI for the namespace prefix found in `namespaces`.

    This new string is then suitable to build an LXML etree.Element object.

    Example::

        >>> substitude_xml_prefix('xlink:href', {'xlink': 'http://wwww.w3.org/1999/xlink'})
        '{http://www.w3.org/1999/xlink}href'

    """
    try:
        prefix, name = prefix_name.split(":", 1)
    except ValueError:
        return prefix_name
    assert prefix in namespaces, f"Unknown namespace prefix: {prefix}"
    return f"{{{namespaces[prefix]}}}" + name


class AbstractXmlAdapter(EntityAdapter):
    """Abstract adapter to produce XML documents."""

    content_type = "text/xml"
    encoding = "utf-8"
    namespaces = {}

    @property
    def file_name(self):
        """Return a file name for the dump."""
        raise NotImplementedError

    def dump(self):
        """Return an XML string for the adapted entity."""
        raise NotImplementedError

    def element(self, tag, parent=None, attributes=None, text=None):
        """Generic function to build a XSD element tag.

        Params:

        * `name`, value for the 'name' attribute of the xsd:element

        * `parent`, the parent etree node

        * `attributes`, dictionary of attributes
        """
        attributes = attributes or {}
        tag = substitute_xml_prefix(tag, self.namespaces)
        for attr, value in list(attributes.items()):
            if value is None:
                attributes.pop(attr)
                continue
            newattr = substitute_xml_prefix(attr, self.namespaces)
            attributes[newattr] = value
            if newattr != attr:
                attributes.pop(attr)
        if parent is None:
            elt = etree.Element(tag, attributes, nsmap=self.namespaces)
        else:
            elt = etree.SubElement(parent, tag, attributes)
        if text is not None:
            elt.text = text
        return elt

    @staticmethod
    def cwuri_url(entity):
        """Return an absolute URL for entity's cwuri, necessary for one head ahead application
        handling relative path in cwuri.
        """
        return entity.cwuri


def registration_callback(vreg):
    for adapter in (
        IRIPublisherInfoAdapter,
        AuthorityRecordIPublisherInfoAdapter,
    ):
        vreg.register(adapter)
    vreg.register_and_replace(FAFileAdapter, FileIDownloadableAdapter)
