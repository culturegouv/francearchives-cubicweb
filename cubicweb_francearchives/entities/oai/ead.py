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
import html.parser

from collections import defaultdict

from logilab.common.decorators import cachedproperty

from cubicweb.predicates import is_instance
from cubicweb_eac.entities import AbstractXmlAdapter

from cubicweb_francearchives import IIIF_MANIFEST_ROLE

from cubicweb_francearchives.entities.oai import AbstractOAIDownloadView
from cubicweb_francearchives.dataimport import cleanup_ns
from cubicweb_francearchives.utils import is_absolute_url, remove_html_tags

OAI_IDENTIFIER_SCHEMA_LOCATION = "urn:isbn:1-931666-22-9"
OAI_IDENTIFIER_SCHEMA_LOCATION_XSD = "http://www.loc.gov/ead/ead.xsd"


class FindingAidOAIEADXmlAdapter(AbstractXmlAdapter):
    __regid__ = "OAI_EAD"
    __select__ = is_instance("FindingAid")
    namespaces = {
        None: "urn:isbn:1-931666-22-9",
        "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        "xlink": "http://www.w3.org/1999/xlink",
    }

    def __init__(self, *args, **kwargs):
        super(FindingAidOAIEADXmlAdapter, self).__init__(*args, **kwargs)
        self._indexes = None

    @cachedproperty
    def prod_entity_url(self):
        return "{}/{}".format(
            self._cw.vreg.config.get("consultation-base-url"), self.entity.rest_path()
        )

    @cachedproperty
    def findingaid(self):
        query = (
            "Any FA, D, DU, DUT, DUD, DPH, DRP, DLG, "
            "DOR, DEX, FTP, FSP, FAR, FUR, FAD  "
            "WHERE FA stable_id %(st)s, FA did D, D unittitle DUT, D unitid DU, "
            "D unitdate DUD, D physdesc DPH, D repository DRP, "
            "D lang_description DLG, D origination DOR, D extptr DEX, "
            "FA fa_header FH, FH titleproper FTP, FA scopecontent FSP, "
            "FA accessrestrict FAR, FA userestrict FUR, FA description FAD"
        )
        return self._cw.execute(query, {"st": self.entity.stable_id}).get_entity(0, 0)

    @cachedproperty
    def did(self):
        return self.findingaid.did[0]

    @cachedproperty
    def fa_header(self):
        return self.findingaid.fa_header[0]

    def dates(self, did):
        if did.unitdate:
            return did.unitdate
        dates = (did.startyear, did.startyear)
        return "-".join([str(d) for d in dates if d])

    @cachedproperty
    def digitized_versions(self):
        """return all digitized versions urls and roles"""
        query = (
            "(Any FA, IL, VIEW, ROLE WHERE X stable_id %(st)s, "
            "FA finding_aid X, FA digitized_versions DA, "
            "DA illustration_url IL, DA url VIEW, DA role ROLE)"
            " UNION "
            "(Any X, IL, VIEW, ROLE WHERE X stable_id %(st)s, "
            "X digitized_versions DA, "
            "DA illustration_url IL, DA url VIEW, DA role ROLE)"
        )
        rset = self._cw.execute(query, {"st": self.findingaid.stable_id})
        dao = defaultdict(list)
        for eid, illustration_url, viewer_url, role in rset:
            dao[eid].append((illustration_url, viewer_url, role))
        return dao

    @cachedproperty
    def facomponents(self):
        query = (
            "Any FA, FH, D, DU, DUT, DUD, DPH, DRP, DLG, "
            "DOR, DEX, FTP, FSP, FAR, FUR, FAD, XD, XDF ORDERBY FA "
            "WHERE X stable_id %(st)s, FA finding_aid X, FA did D, "
            "D unittitle DUT, D unitid DU, D unitdate DUD, "
            "D physdesc DPH, D repository DRP, D lang_description DLG, "
            "D origination DOR, D extptr DEX, "
            "X fa_header FH, FH titleproper FTP, FA scopecontent FSP, "
            "FA accessrestrict FAR, FA userestrict FUR, FA description FAD, "
            "X description_format XDF, X description XD"
        )
        rset = self._cw.execute(query, {"st": self.findingaid.stable_id})
        return rset.entities()

    @property
    def indexes(self):
        if self._indexes is None:
            self._indexes = self.init_indexes()
        return self._indexes

    def init_indexes(self):
        indexes = defaultdict(list)
        fa_eid = self.findingaid.eid
        # fetch all agent indexes on the FindingAid and its components
        rset = self._cw.execute(
            " (DISTINCT Any L, T, X WHERE A is AgentName, "
            "  A label L, A type T, A index X, X eid %(x)s) "
            " UNION "
            " (DISTINCT Any L, T, FC WHERE A is AgentName, "
            "  A label L, A type T, A index FC, FC finding_aid X, X eid %(x)s) ",
            {"x": fa_eid},
        )
        for label, itype, eid in rset:
            indexes[eid].append((itype, label))
        # fetch all subject indexes on the FindingAid and its components
        rset = self._cw.execute(
            " (DISTINCT Any L, T, X WHERE A is Subject, A label L, A type T, "
            " A index X, X eid %(x)s) "
            " UNION "
            " (DISTINCT Any L, T, FC WHERE A is Subject, A label L, A type T,"
            "  A index FC, FC finding_aid X, X eid %(x)s)",
            {"x": fa_eid},
        )
        for label, itype, eid in rset:
            indexes[eid].append((itype, label))
        # fetch all gegonames indexes on the FindingAid and its components
        rset = self._cw.execute(
            " (DISTINCT Any L, X WHERE A is Geogname, A label L, A index X, X eid %(x)s) "
            " UNION "
            " (DISTINCT Any L, FC WHERE A is Geogname, A label L, "
            "  A index FC, FC finding_aid X, X eid %(x)s)",
            {"x": fa_eid},
        )
        for label, eid in rset:
            indexes[eid].append(("geogname", label))
        return indexes

    def dump(self, as_xml=False):
        """Return an XML string representing the given agent using the OAI_DC schema."""
        # Root element
        root_element = self.ead_from_file()
        oai_identifier = "{0} {1}".format(
            OAI_IDENTIFIER_SCHEMA_LOCATION, OAI_IDENTIFIER_SCHEMA_LOCATION_XSD
        )
        if root_element is not None:
            nsmap = root_element.nsmap
            nsmap["xsi"] = "http://www.w3.org/2001/XMLSchema-instance"
            root_element.set("audience", "external")
            root_element.set(etree.QName(nsmap["xsi"], "schemaLocation"), oai_identifier)
        else:
            root_element = self.element(
                "ead",
                attributes={
                    "xsi:schemaLocation": oai_identifier,
                    "audience": "external",
                },
            )
            self.body_elements(root_element)
        self.findingaid.cw_clear_all_caches()
        if as_xml:
            return root_element
        return etree.tostring(
            root_element,
            xml_declaration=True,
            method="xml",
            encoding=self.encoding,
            pretty_print=True,
        )

    def update_original_xml(self, tree):
        # Some EAD files use the 'urn:isbn:1-931666-22-9' namesapce, some don't.
        for eadid in tree.xpath("..//s:eadid", namespaces={"s": "urn:isbn:1-931666-22-9"}):
            if eadid.attrib.get("url") is None:
                eadid.attrib["url"] = self.prod_entity_url
            if eadid.attrib.get("countrycode") is None:
                eadid.attrib["countrycode"] = "FR"

    def ead_from_file(self):
        ape_file = self.findingaid.ape_ead_file
        if ape_file:
            if not ape_file[0].data:
                self.exception(
                    f"failed to build ead tree for FindingAid {self.findingaid.stable_id}: ape_file not found"  # noqa
                )
                return None
            try:
                xmlcontent = ape_file[0].data.getvalue()
                tree = etree.fromstring(xmlcontent)
                self.update_original_xml(tree)
                return cleanup_ns(tree, "ns0")
            except Exception:
                self.exception(
                    f"failed to build ead tree for FindingAid {self.findingaid.stable_id}"
                )
        return None

    def body_elements(self, root_element):
        self.eadheader_element(root_element)
        self.archdesc_element(root_element)

    def clean_richstring_data(self, entity, attr):
        html_ = getattr(entity, attr)
        if html_:
            html_ = remove_html_tags(html_.replace("\n", "")).strip(" ")
            html_ = html.unescape(html_)
            return html_ if html_ else None

    def eadheader_element(self, parent_element):
        eadheader = self.element("eadheader", parent=parent_element)
        self.element(
            "eadid",
            parent=eadheader,
            text=self.findingaid.eadid,
            attributes={"identifier": self.findingaid.eadid, "url": self.prod_entity_url},
        ),
        self.filedesc_element(eadheader)

    def filedesc_element(self, parent_root):
        filedesc = self.element("filedesc", parent=parent_root)
        titleproper = self.fa_header.titleproper or self.did.unittitle
        titlestmt = self.element("titlestmt", parent=filedesc)
        self.element("titleproper", parent=titlestmt, text=titleproper)
        self.publicationstmt_element(filedesc)

    def publicationstmt_element(self, parent_root):
        publicationstmt = self.element("publicationstmt", parent=parent_root)
        service = self.findingaid.service
        if service:
            publisher = service[0].short_name or service[0].dc_title()
        publisher = self.findingaid.publisher
        if publisher:
            self.element("publisher", parent=publicationstmt, text=publisher)

    def archdesc_element(self, parent_element):
        attrs = {"level": "fonds"}
        archdesc = self.element("archdesc", parent=parent_element, attributes=attrs)
        did = self.did
        self.did_element(archdesc, self.findingaid, did)
        daos = [u for u in self.digitized_versions.get(self.findingaid.eid, []) if u]
        if daos:
            self.dao_elements(archdesc, self.findingaid, daos)
        self.scopecontent(archdesc, self.findingaid)
        self.controlaccess(archdesc, self.findingaid)
        self.relatedmaterial(archdesc, self.findingaid)
        self.accessrestrict(archdesc, self.findingaid)
        self.userestrict(archdesc, self.findingaid)
        self.components(archdesc)

    def did_element(self, parent_element, entity, did):
        did_elt = self.element("did", parent=parent_element)
        # dao
        unitid = self.element("unitid", parent=did_elt)
        extptr = did.extptr
        if extptr:
            if is_absolute_url(extptr):
                attribs = {
                    "{%s}type" % self.namespaces["xlink"]: "simple",
                    "{%s}href" % self.namespaces["xlink"]: extptr,
                }
                extptr = self.element("extptr", parent=unitid)
                extptr.attrib.update(attribs)
        if extptr is not None:
            extptr.tail = did.unitid
        else:
            unitid.text = did.unitid
        titleproper = did.unittitle
        if titleproper:
            self.element("unittitle", parent=did_elt, text=titleproper)
        dates = self.dates(did)
        if dates:
            self.element("unitdate", parent=did_elt, text=dates)
        physdesc = self.clean_richstring_data(did, "physdesc")
        if physdesc:
            self.element("physdesc", parent=did_elt, text=physdesc)
        repository = self.clean_richstring_data(did, "repository")
        if repository:
            self.element("repository", parent=did_elt, text=repository)
        self.origination(did_elt, did)
        lang_description = self.clean_richstring_data(did, "lang_description")
        if lang_description:
            self.element("langmaterial", parent=did_elt, text=lang_description)

    def dao_elements(self, parent_element, entity, daos):
        """Create dao tags:
        - The thumbnail URL : dc:relation preceded by "vignette :"
          becomes <dao xlink:href="" xlink:type="simple" xlink:role="thumbnail"/>
          with the role "thumbnail""
        - The digitized link URL: using the dc:relation tag without the 'thumbnail' prefix becomes
           <dao xlink:href="" xlink:type="simple" xlink:title=""/>
        - Component identifier :
          the dc:identifier element is reserved for the
          link to the component and becomes
          <unitid extptr xlink:type="simple" xlink:href=""/></unitid>
        - IIIF MANIFEST: added as <dao xlink:role="MANIFEST"
             xlink:href="XXX/manifest" xlink:title="manifest"/>
        """
        for illustration_url, viewer_url, role in daos:
            if role == IIIF_MANIFEST_ROLE:
                dao = self.element("dao", parent=parent_element)
                dao.attrib.update(
                    {
                        "{%s}title" % self.namespaces["xlink"]: "manifest",
                        "{%s}role" % self.namespaces["xlink"]: "MANIFEST",
                        "{%s}href" % self.namespaces["xlink"]: viewer_url,
                    }
                )
                continue
            url = illustration_url or viewer_url
            if url:
                attribs = {
                    "{%s}type" % self.namespaces["xlink"]: "simple",
                    "{%s}href" % self.namespaces["xlink"]: url,
                }
                if role:
                    attribs.update({"{%s}role" % self.namespaces["xlink"]: role})
                dao = self.element("dao", parent=parent_element)
                dao.attrib.update(attribs)

    def relatedmaterial(self, parent_element, entity):
        description = self.clean_richstring_data(entity, "additional_resources")
        if description:
            self.element(
                "p", parent=self.element("relatedmaterial", parent=parent_element), text=description
            )

    def scopecontent(self, parent_element, entity):
        description = self.clean_richstring_data(entity, "description")
        if description:
            self.element(
                "p", parent=self.element("scopecontent", parent=parent_element), text=description
            )

    def accessrestrict(self, parent_element, entity):
        accessrestrict = self.clean_richstring_data(entity, "accessrestrict")
        if accessrestrict:
            self.element(
                "p",
                parent=self.element("accessrestrict", parent=parent_element),
                text=accessrestrict,
            )

    def userestrict(self, parent_element, entity):
        userestrict = self.clean_richstring_data(entity, "userestrict")
        if userestrict:
            self.element(
                "p", parent=self.element("userestrict", parent=parent_element), text=userestrict
            )

    def controlaccess(self, parent_element, entity):
        controlaccess = self.element("controlaccess", parent=parent_element)
        for itype, label in sorted(self.indexes[entity.eid]):
            self.element(itype, parent=controlaccess, text=label)

    def origination(self, parent_element, did):
        origination = self.clean_richstring_data(did, "origination")
        if origination:
            self.element("origination", parent=parent_element, text=origination)

    def components(self, parent_element):
        fa_components = self.facomponents
        if fa_components:
            doas = self.digitized_versions
            dsc = self.element("dsc", parent=parent_element)
            for fa_component in fa_components:
                did = fa_component.did[0]
                c = self.element("c", parent=dsc)
                daos = [u for u in doas.get(fa_component.eid, []) if u]
                self.did_element(c, fa_component, did)
                if daos:
                    self.dao_elements(c, fa_component, daos)
                self.scopecontent(c, fa_component)
                self.controlaccess(c, fa_component)
                self.accessrestrict(c, fa_component)
                self.userestrict(c, fa_component)
                fa_component.cw_clear_all_caches()


class OAIEADDownloadView(AbstractOAIDownloadView):
    """oai_ead download view"""

    __regid__ = "oai_ead.export"
    __select__ = AbstractOAIDownloadView.__select__ & is_instance("FindingAid")
    adapter_id = "OAI_EAD"
