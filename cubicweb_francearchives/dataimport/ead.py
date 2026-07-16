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

from datetime import datetime
import logging
import os
import os.path as osp
import re
from itertools import chain
from uuid import uuid4
import mimetypes
from copy import deepcopy

from glamconv.cli.commands import ead2_to_ape

import json

import pytz

from logilab.mtconverter import xml_escape

from cubicweb.utils import json_dumps
from cubicweb_francearchives import IIIF_MANIFEST_ROLE
from cubicweb_francearchives.utils import merge_dicts, pick
from cubicweb_francearchives.entities import ETYPE_CATEGORIES
from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.dataimport import (
    IndexImporterMixin,
    pdf,
    load_metadata_file,
    default_csv_metadata,
    strip_html,
    strip_nones,
    get_year,
    get_date,
    clean_values,
    normalize_entry,
    remove_extension,
    usha1,
    decode_filepath,
    RELFILES_DIR,
    capture_exception,
    service_infos_from_filepath,
    default_service_name,
    load_services_map,
    compute_ape_relpath,
    unique_indices,
    INDEX_AUTHORITY_TYPE_MAP,
    InvalidFindingAid,
)
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename
from cubicweb_francearchives.dataimport.eadreader import (
    EADXMLReader,
    preprocess_ead,
)
from cubicweb_francearchives.dataimport.ape_ead import register_ead_actions
from cubicweb_francearchives.storage import S3BfssStorageMixIn


LOGGER = logging.getLogger()

IGNORED_NODES = frozenset(
    ["altformavail", "arc", "archdescgrp", "bibseries", "blockquote", "chronitem", "chronlist"]
)


IN_RELFILES_RE = re.compile(r"(.*)/{}/(.*)".format(RELFILES_DIR))


def ead2_to_ape_settings():
    """load default ead2 -> ape transformation settings"""
    settings_filepath = osp.join(osp.dirname(__file__), "francearchives-ead2-to-ape-settings.json")
    with open(settings_filepath) as inputf:
        return json.load(inputf)


def transform_ape_ead_file(fa_url, tree, ape_filepath):
    register_ead_actions()
    settings = ead2_to_ape_settings()
    for step in settings["steps"]:
        if step["id"] == "francearchives-eadid-transformer":
            step["params"]["eadid_url"] = fa_url
    ead2_to_ape(deepcopy(tree), ape_filepath, settings=settings)


def generate_ape_ead_file_from_xml(cnx, tree, service_infos, fa_stable_id, ape_filepath):
    fa_url = "{}/findingaid/{}".format(cnx.vreg.config.get("consultation-base-url"), fa_stable_id)
    transform_ape_ead_file(fa_url, tree, ape_filepath)


ES_INDICES_LIMIT = 10000


def year_value(year, ignore_3_digits=False):
    if year is None:
        return None
    if not isinstance(year, int):
        if not year:
            return None
        year = int(year)
    if ignore_3_digits and year < 1000:
        # hack to avoid noise from AN
        return None
    if year >= 10000:  # bad formatted date / date range in the finding aid
        return int(str(year)[:4])
    if year < 2050:
        return year
    return None  # very suspcious date, ignore it


def dates_for_es_doc(did_attrs, logger=None, docid=None):
    attrs = {}
    startyear = year_value(did_attrs.get("startyear"), True)
    stopyear = year_value(did_attrs.get("stopyear"), True)
    if startyear and stopyear:
        if startyear > stopyear:
            if logger:
                logger.error(
                    f"""Stable_id {docid}: Start year {startyear} is greater than """
                    """the stop year {stopyear}"""
                )
            return attrs
    year = startyear or stopyear
    if year:
        attrs["sortdate"] = "{}-01-01".format(year)
    fa_dates = {}
    if startyear:
        attrs["startyear"] = startyear
    if stopyear:
        attrs["stopyear"] = stopyear
    if startyear or stopyear:
        fa_dates["gte"] = startyear or stopyear
        fa_dates["lte"] = stopyear or startyear
    if fa_dates:
        attrs["dates"] = fa_dates
    return attrs


def service_infos_for_es_doc(cnx, service_infos):
    return {
        "service": {
            "eid": service_infos["eid"],
            "level": cnx._(service_infos["level"]),
            "code": service_infos["code"],
            "title": service_infos["name"] if "name" in service_infos else service_infos["title"],
        }
    }


def old_component_stable_id(fa_id, comp_path):
    return usha1("{}{}".format(fa_id, "-".join(str(i) for i in comp_path)))


def component_stable_id(fa_id, comp_id, comp_path):
    if comp_id:
        return usha1("{}{}".format(fa_id, comp_id))
    return old_component_stable_id(fa_id, comp_path)


def readerconfig(cwconfig, appid, esonly, nodrop=False, **kwargs):
    config = {
        "base-url": cwconfig["base-url"],
        "index-name": cwconfig["index-name"],
        "sentry-dsn": cwconfig.get("sentry-dsn"),
        "appid": appid,
        "elasticsearch-locations": cwconfig["elasticsearch-locations"],
        "esonly": esonly,
        "appfiles-dir": cwconfig["appfiles-dir"],
        "nodrop": nodrop,
        "force_delete": False,
        # compare authorities grouped by service without calling normalize_entry
        "autodedupe_authorities": "service/normalize",
        # should we push es documents into elasticsearch index
        "noes": False,
    }
    config.update(kwargs)
    return config


def findingaid_eids(cnx, fa_stable_id):
    return dict(
        cnx.execute(
            "(Any S,X WHERE X is FindingAid, X stable_id %(id)s, X stable_id S)"
            " UNION "
            "(Any S,X WHERE F stable_id %(id)s, X finding_aid F, X stable_id S)",
            {"id": fa_stable_id},
        )
    )


def generate_ape_ead_xml(cnx, config, tree, ir_name, stable_id, service_infos):
    """
    Compute ape_ead_xml file and write it in the ape_filepath
    """
    ape_filepath = osp.join(
        config["appfiles-dir"],
        compute_ape_relpath(cnx, "ape-ead", ir_name, service_infos),
    )
    generate_ape_ead_file_from_xml(cnx, tree, service_infos, stable_id, ape_filepath)
    return ape_filepath


class MetadataReaderMixIn(object):
    """a collection of methods used in csv, pdf and oai_dc import"""

    richstring_template = """
<div class="ead-section ead-{attr}">
  <div class="ead-wrapper">
    <div class="ead-p">{data}</div>
  </div>
</div>"""

    def richstring_html(self, data, attr):
        if data:
            data = xml_escape(data).replace("\n", "<br />")
            return self.richstring_template.format(data=data, attr=attr)
        return None

    def index_entries(self, entry, target_eid, fa_attrs):
        index_entries = {}  # create a map to keep unique index entries only
        for index_name, index_type, role in (
            ("index_personne", "persname", "index"),
            ("index_collectivite", "corpname", "index"),
            ("index_lieu", "geogname", "index"),
            ("index_matiere", "subject", "index"),
            ("type", "genreform", "index"),
            ("origine", "name", "originator"),
        ):
            index_labels = entry.get(index_name) or ()
            if not isinstance(index_labels, (list, tuple)):
                index_labels = [s.strip() for s in index_labels.split(";")]
            for index_label in index_labels:
                if not index_label:
                    # ignore empty string
                    continue
                index_label = index_label[:256].strip()
                index_infos = {
                    "type": index_type,
                    "label": index_label,
                    "normalized": normalize_entry(index_label),
                    "role": role,
                    "authfilenumber": None,
                    "authtype": INDEX_AUTHORITY_TYPE_MAP[index_type][1],
                }
                self.create_index(index_infos, target_eid, fa_attrs)
                index_entries[(index_type, index_infos["normalized"])] = index_infos
        return index_entries

    def import_findingaid(self, service_infos, metadata, fa_support, **fa_es_attrs):
        filepath = fa_support["data"]
        file_identifier = metadata["identifiant_fichier"]
        stable_id = usha1(file_identifier)
        eadid = remove_extension(file_identifier)
        if self.config.get("force_delete"):
            file_identifier, stable_id = self.process_existing_findingaids(eadid, fa_support)
        unittitle = metadata["titre"]
        unitdate = get_date(metadata.get("date1"), metadata.get("date2"))
        extptr = metadata.get("identifiant_uri")
        originator = metadata.get("origine")
        did_attrs = {
            "unitdate": unitdate,
            "unittitle": unittitle,
            "startyear": get_year(metadata.get("date1")),
            "stopyear": get_year(metadata.get("date2")),
            "physdesc": self.richstring_html(metadata.get("format"), "physdesc"),
            "physdesc_format": "text/html",
            "lang_description": metadata.get("langue"),
            "origination": originator,
            "extptr": extptr,
        }
        if extptr and not extptr.startswith("http"):
            raise Exception('`identifiant_uri` "{0}" is not a valid URL'.format(extptr))
        did_data = self.create_entity("Did", clean_values(did_attrs))
        header_attrs = self.create_entity("FAHeader", {"titleproper": unittitle})
        # cwuri = unicode(did_data['eid'])
        basepath = self.storage.storage_get_basepath(filepath)
        if file_identifier and file_identifier != basepath:
            self.log.warning(
                '`file_identifier` "{0}" is different from the imported file name "{1}"'.format(
                    file_identifier, basepath
                )
            )
        publisher = service_infos.get("name") or default_service_name(basepath)
        fa_attrs = {
            "name": file_identifier,
            "eadid": eadid,
            "did": did_data["eid"],
            "scopecontent": self.richstring_html(metadata.get("description"), "scopecontent"),
            "scopecontent_format": "text/html",
            "additional_resources": self.richstring_html(
                metadata.get("source_complementaire"), "additional_resources"
            ),
            "additional_resources_format": "text/html",
            "accessrestrict": self.richstring_html(
                metadata.get("conditions_acces"), "accessrestrict"
            ),
            "accessrestrict_format": "text/html",
            "userestrict": self.richstring_html(
                metadata.get("conditions_utilisation"), "userestrict"
            ),
            "userestrict_format": "text/html",
            "stable_id": stable_id,
            "publisher": str(publisher),
            "service": service_infos.get("eid"),
            "fa_header": header_attrs["eid"],
        }
        fa_attrs["creation_date"] = metadata["creation_date"]
        fa_attrs["findingaid_support"] = fa_support["eid"]
        fa_data = self.create_entity("FindingAid", clean_values(fa_attrs))
        illustration_url = metadata.get("source_image")
        daos = []
        if illustration_url:
            daos = [{"role": "thumbnail", "illustration_url": illustration_url, "url": None}]
            self.create_daos(daos, fa_data["eid"])
        iiif = bool([d for d in daos if d.get("role") == IIIF_MANIFEST_ROLE])
        fa_es_attrs.update(
            {
                "fa_stable_id": fa_data["stable_id"],
                "scopecontent": strip_html(fa_attrs.get("scopecontent")),
                "creation_date": fa_data["creation_date"],
                "originators": [originator] if originator else None,
                "digitized": bool(daos),
                "digitized_all": DZFacetValues.index_values(digitized=bool(daos), iiif=iiif),
            }
        )
        titleproper = header_attrs.get("titleproper")
        if titleproper:
            fa_es_attrs["alltext"] = titleproper
        fa_es_attrs.update(service_infos_for_es_doc(self.store._cnx, service_infos))
        es_doc = self.build_complete_es_doc(
            "FindingAid",
            fa_data,
            did_data,
            self.index_entries(metadata, fa_data["eid"], fa_data),
            **fa_es_attrs,
        )
        self.create_entity(
            "EsDocument", {"doc": json_dumps(es_doc["_source"]), "entity": fa_data["eid"]}
        )
        return es_doc

    def build_complete_es_doc(self, etype, attrs, did_attrs, index_entries, **kwargs):
        es_did_attrs = es_dict(did_attrs, ["unittitle", "unitid"], add_eid=False)
        es_doc = {
            "escategory": ETYPE_CATEGORIES[etype],
            "cw_etype": etype,
            "did": es_did_attrs,
            "eadid": attrs.get("eadid"),
            "eid": attrs["eid"],
            "stable_id": attrs["stable_id"],
            "index_entries": unique_indices(list(index_entries.values())),
            "creation_date": attrs["creation_date"],
        }
        es_doc.update(dates_for_es_doc(did_attrs, logger=self.log, docid=attrs["stable_id"]))
        es_doc.update(kwargs)
        return self.build_es_doc(
            attrs["stable_id"], es_doc, index_name=self.config["index-name"] + "_all"
        )


class Reader(MetadataReaderMixIn, IndexImporterMixin):
    def __init__(self, config, store):
        super(Reader, self).__init__()
        self.config = config
        self.index_policy = {
            "autodedupe_authorities": self.config.get(
                "autodedupe_authorities", "service/normalize"
            ),
        }
        self.log = config.get("log")
        if self.log is None:
            self.log = LOGGER
        self.store = store
        self.storage = S3BfssStorageMixIn(log=self.log)
        # "mixed_c_stable_id" variable indicate whether to apply the mixed
        # stable_id calculation method or the old one based on the composant
        # path
        self.mixed_c_stable_ids = None
        if self.config["esonly"]:
            self.add_rel = lambda *a, **k: None
            self.authority_records = {}
            self.known_fa_ids = {}
            for rqlpath in ("I index FA", "I index FAC, FAC finding_aid FA"):
                for typevar, rqlpath2 in (
                    ("T", "I is AgentName, I type T"),
                    ("'geogname'", "I is Geogname"),
                    ("T", "I is Subject, I type T"),
                ):
                    self.indices.update(
                        {
                            (s, t, l, r): (i, a)
                            for t, l, r, i, a, s in store.rql(
                                "Any {}, L, R, I, A, S WHERE "
                                "FA is FindingAid, FA stable_id S, {}, "
                                "I label L, I authority A, I role R, "
                                "{}".format(typevar, rqlpath, rqlpath2)
                            )
                        }
                    )
        else:
            self.add_rel = self.store.prepare_insert_relation
            self.authority_records = {
                r: x
                for x, r in store.rql("Any X, R WHERE " "X is AuthorityRecord, " "X record_id R")
            }
            self.known_fa_ids = {
                eadid.lower(): stable_id
                for eadid, stable_id in store.rql(
                    "Any E, S WHERE X is FindingAid, X stable_id S, X eadid E"
                )
            }
        self.delete_existing_findingaid = False
        self.deferred = {}
        self._pdf_metadata_cache = {}
        self._files = {}
        self._stable_id_map = None
        self._richstring_cache = {}
        self.imported_findingaids = {}
        self._init_authorities()
        self._init_blacklisted_authorities()
        self._init_unnormalized_authorities()
        self._init_auth_history()

    def etype_richstring_attrs(self, etype):
        if etype in self._richstring_cache:
            return self._richstring_cache[etype]
        # NOTE: RQLObjectStore doesn't have a ``schema`` attribute
        # unlike MassiveObjectStore
        eschema = self.store._cnx.vreg.schema.entity_schema_for(etype)
        meta_attributes = eschema.meta_attributes()
        rich_attrs = [
            (attr, rschema.type)
            for rschema, (meta, attr) in list(meta_attributes.items())
            if meta == "format"
        ]
        self._richstring_cache[etype] = rich_attrs
        return rich_attrs

    @property
    def files(self):
        if not self._files:
            rset = self.store.rql(
                "Any FSPATH(D), X, S WHERE X is File, X data D, X data_hash S, "
                "FA findingaid_support X"
            )
            self._files = {osp.basename(d.read().decode("utf-8")): (x, s) for d, x, s in rset}
        return self._files

    def build_url(self, *restpath):
        base_url = self.config["base-url"].rstrip("/")
        return "%s/%s" % (base_url, "/".join(str(r) for r in restpath))

    def stable_id_to_eid(self, stable_id):
        if self._stable_id_map is None:
            # safety belt, should not happen: we should always have created the
            # FindingAid before trying to create the FAComponent
            self._stable_id_map = findingaid_eids(self.store._cnx, stable_id)
        return self._stable_id_map.get(stable_id)

    def create_entity(self, etype, attrs):
        attrs = strip_nones(attrs)
        for attr, fmt_attr in self.etype_richstring_attrs(etype):
            if attr in attrs and fmt_attr not in attrs:
                attrs[fmt_attr] = "text/html"
        if self.config["esonly"]:
            eid = None
            # try to get FindingAid / FAComponent eid in esonly mode
            if "stable_id" in attrs:
                eid = self.stable_id_to_eid(attrs["stable_id"])
        else:
            eid = self.store.prepare_insert_entity(etype, **attrs)
        attrs["eid"] = eid
        if etype == "FindingAid":
            self.imported_findingaids[attrs["stable_id"]] = eid
        return attrs

    def create_findingaid(self, attrs):
        return self.create_entity("FindingAid", strip_nones(attrs))

    def create_did(self, attrs):
        return self.create_entity("Did", strip_nones(attrs))

    def create_file(self, filepath, title=None, sha1=None):
        if sha1 is None:
            sha1 = self.storage.get_file_sha1(filepath)
            if sha1 is None:
                raise Exception('Could not find file "%r". Please, reimport it.', filepath)
        if not self.config["esonly"] and self.ignore_filepath(filepath, sha1):
            return None
        f = self.create_cwfile(filepath, title, sha1)
        basepath = osp.basename(osp.abspath(decode_filepath(filepath)))
        self._files[basepath] = (f["eid"], sha1)
        return f

    def create_cwfile(self, filepath, title=None, sha1=None):
        ufilepath = self.storage.storage_ufilepath(filepath)
        _, basepath = os.path.split(ufilepath)
        return self.create_entity(
            "File",
            {
                "title": title or basepath,
                "data": ufilepath,
                "data_format": str(mimetypes.guess_type(filepath)[0]),
                "data_name": basepath,
                "data_hash": sha1,
                "uuid": str(uuid4().hex),
            },
        )

    def is_dao_url_valid(self, url):
        if url and len(url) > 512:
            return False
        return True

    def create_daos(self, daos, eid):
        urls = []
        for daodef in daos:
            unvalid_url = False
            for uri in (daodef.get("url"), daodef.get("illustration_url")):
                if not self.is_dao_url_valid(uri):
                    self.log.error("do not import import dao with url length %s: %r", len(uri), uri)
                    unvalid_url = True
                    continue
            if unvalid_url:
                continue
            role = daodef.get("role")
            if role and len(role) > 128:
                self.log.warning("truncating dao role of length %s: %r", len(role), role)
                daodef["role"] = role[:128].strip()
            urls.append(dict(daodef))
            digit_ver_attrs = self.create_entity("DigitizedVersion", strip_nones(daodef))
            self.add_rel(eid, "digitized_versions", digit_ver_attrs["eid"])
        return urls

    def import_component(self, comp_props, findingaid_attrs, service_infos, parent_component):
        did_attrs = self.create_did(comp_props["did"])
        referenced_files = comp_props.pop("referenced_files")
        if self.mixed_c_stable_ids:
            stable_id = component_stable_id(
                findingaid_attrs["stable_id"], comp_props["c_id"], comp_props["path"]
            )
        else:
            stable_id = old_component_stable_id(findingaid_attrs["stable_id"], comp_props["path"])
        comp_attrs = merge_dicts(
            {
                "did": did_attrs["eid"],
                "finding_aid": findingaid_attrs["eid"],
                "stable_id": stable_id,
                "parent_component": parent_component,
                "component_order": comp_props["path"][-1],
            },
            pick(
                comp_props,
                *chain(
                    *(
                        (p, p + "_format")
                        for p in (
                            "description",
                            "bibliography",
                            "bioghist",
                            "notes",
                            "acquisition_info",
                            "scopecontent",
                            "accessrestrict",
                            "userestrict",
                            "additional_resources",
                        )
                    )
                ),
            ),
        )
        comp_attrs["creation_date"] = findingaid_attrs["creation_date"]
        comp_attrs = self.create_entity("FAComponent", strip_nones(comp_attrs))
        self.create_referenced_files(comp_attrs["eid"], referenced_files)
        # uniquify index entries but only on labels (instead of normalized)
        # to keep variants
        index_entries = unique_indices(
            chain(comp_props["origination"], comp_props["index_entries"]), keys=("type", "label")
        )
        for infos in index_entries:
            self.create_index(infos, target=comp_attrs["eid"], fa_attrs=findingaid_attrs)
        # create DigitizedVersions
        self.create_daos(comp_props["daos"], comp_attrs["eid"])
        did_es = es_dict(did_attrs, ["unittitle", "unitid", "abstract", "note"], add_eid=False)
        alltext_values = [x for x in [did_es["abstract"], did_es["note"]] if x is not None]
        del did_es["abstract"]
        del did_es["note"]
        iiif = bool([d for d in comp_props["daos"] if d.get("role") == IIIF_MANIFEST_ROLE])
        es_doc = es_dict(
            comp_attrs,
            [
                "eadid",
                "stable_id",
                "description",
                "acquisition_info",
                "scopecontent",
            ],
            did=did_es,
            digitized=bool(comp_props["daos"]),
            digitized_all=DZFacetValues.index_values(digitized=bool(comp_props["daos"]), iiif=iiif),
            index_entries=unique_indices(index_entries),
            originators=findingaid_attrs["originators"],
            fa_stable_id=findingaid_attrs["stable_id"],
            creation_date=comp_attrs["creation_date"],
            cw_etype="FAComponent",
        )
        es_doc.update(dates_for_es_doc(did_attrs, logger=self.log, docid=comp_attrs["stable_id"]))
        es_doc.update(service_infos_for_es_doc(self.store._cnx, service_infos))
        if es_doc["description"]:
            alltext_values.append(es_doc["description"])
        del es_doc["description"]
        if alltext_values:
            es_doc.update({"alltext": "\n".join(alltext_values)})
        complete_es_doc = self.build_es_doc(
            comp_attrs["stable_id"], es_doc, index_name=self.config["index-name"] + "_all"
        )
        self.create_entity(
            "EsDocument",
            {"doc": json_dumps(complete_es_doc["_source"]), "entity": comp_attrs["eid"]},
        )
        return complete_es_doc

    def ignore_filepath(self, filepath, sha1):
        basepath = osp.basename(filepath)
        if basepath in self.files:
            # a file with same filepath (i.e. same stable_id) was already imported
            if self.config.get("update_imported"):
                return False
            if not self.config.get("reimport"):
                self.log.debug("Ignore already imported file %s", basepath)
                return True
            prevsha1 = self.files[basepath][1]
            if prevsha1 == sha1 and not self.config.get("force_delete"):
                self.log.debug(
                    "Ignore already imported file %s (because of identical sha1)", basepath
                )
                return True
            self.log.debug("Entities related to  %s will be deleted", basepath)
            self.delete_existing_findingaid = True
        return False

    def delete_from_filename(self, filepath):
        if self.delete_existing_findingaid:
            delete_from_filename(
                self.store._cnx,
                filepath,
                interactive=False,
                esonly=self.config["esonly"],
                logger=self.log,
            )

    def creation_date_from_filepath(self, filepath):
        rset = self.store.rql(
            """
            Any D WHERE F is File, F data_name %(e)s,
            FA findingaid_support F, FA creation_date D
            """,
            {"e": osp.basename(filepath)},
        )
        return rset[0][0] if rset else datetime.now(pytz.utc)

    def ensure_service(self, filepath, service_infos=None):
        if service_infos is None:
            service_map = load_services_map(self.store._cnx)
            service_infos = service_infos_from_filepath(filepath, service_map)
        return service_infos

    def import_filepath(self, filepath, service_infos=None, **kwargs):
        entities = []
        if isinstance(filepath, bytes):
            filepath = filepath.decode("utf-8")
        if IN_RELFILES_RE.match(filepath):
            return entities
        self._stable_id_map = None
        file_ext = osp.splitext(filepath)[1].lower()
        service_infos = self.ensure_service(filepath, service_infos)
        if file_ext in (".xml", ".pdf"):
            sha1 = self.storage.get_file_sha1(filepath)
            if sha1 is None:
                self.log.error('Could not find file "%r". Please, reimport it.', filepath)
                return entities
            fa_support = self.create_file(filepath, sha1=sha1)
            if fa_support is None:
                return entities
            self.update_authorities_cache(service_infos.get("eid"))
            if file_ext == ".xml":
                relfiles = self.storage.storage_handle_pdf_relfiles(filepath)
                entities = self.import_ead_xml(service_infos, fa_support, relfiles=relfiles)
            elif file_ext == ".pdf":
                entities = self.import_pdf(service_infos, fa_support)
                # add the symlink after all previous data deletions
                if not self.config["esonly"]:
                    # FIXME s3 why publish imported pdf ?
                    self.storage.storage_make_symlink_to_publish(
                        filepath, sha1, self.config.get("appfiles-dir")
                    )
        else:
            self.log.debug(f"""Do not process "{filepath}" as it's not a .xml or .pdf file""")
            return []
        return entities

    def import_ead_xml(self, service_infos, fa_support, relfiles=None, **fa_attrs):
        """
        Parameters:
        -----------

        service_infos : a map of properties {name, code, eid}
        fa_support    : CW File object hosting the finding aid content (XXX attr_cache)
        relfiles      : files to link to the FindingAid
        fa_attrs      : attributes to add to FindingAid
        """
        filepath = fa_support["data"]
        binary = self.storage.storage_get_file_content(filepath)
        if not binary:
            self.log.error('Could not find file "%r". Please reimport it.', filepath)
            return []
        try:
            tree = preprocess_ead(binary)
        except Exception as exc:
            self.log.exception("Import aborted: invalid xml %r", filepath)
            capture_exception(exc, filepath)
            return []
        return self.import_ead_xmltree(tree, service_infos, fa_support, relfiles, **fa_attrs)

    def update_fa_redirects(self, old_stable_id, new_stable_id, eadid):
        data = {
            "old_stable_id": old_stable_id,
            "new_stable_id": new_stable_id,
            "eadid": eadid,
            "date": datetime.now().strftime("%Y-%m-%d"),
        }
        sql = self.store._cnx.system_sql
        res = sql(
            """SELECT to_stable_id from fa_redirects
                     WHERE from_stable_id = %(old_stable_id)s""",
            data,
        ).fetchall()
        if res:
            existing = res[0][0]
            if existing != new_stable_id:
                self.log.warning(
                    "update_fa_redirects: set new stable_id %r" " instead of existing %r",
                    new_stable_id,
                    existing,
                )
        query = """
        INSERT INTO fa_redirects (eadid, from_stable_id, to_stable_id, date)
        VALUES (%(eadid)s, %(old_stable_id)s, %(new_stable_id)s, %(date)s)
        ON CONFLICT (from_stable_id) DO UPDATE SET to_stable_id = EXCLUDED.to_stable_id;
        """
        sql(query, data)

    def process_existing_findingaids(self, eadid, fa_support):
        """This method is used by now only for xml imported zip files and
        harvested FindingAids.

        The ir_name (and thus stable_id) is now computed from
        fa_support['data_name'] with extension '.xml'.

         - The existing FindingAid with the same stable_id is deleted.

         - If any old version of harvested exist, it well be deleted as well.

        If, by any chance, a FindingAid has no filename, which normaly should
        not happen, the value of <eadid> is still be used to compute the stable_id.

        XXX TODO In the future this method must be used for all imports to
        solve the issue bellow.

        Issue:

        A FindingAid may be imported in two different ways: by oai harvesting or
        by zip import (with '.xml', '.pdf' or '.csv' files). The stable_ids are
        generated as below:

          - from fa_support['data_name'] with extention (
            for xml, pdf and csv with metadata);

          - from fa_support['data_name'] without extension (
            for pdf and csv without metadata);

          - from <eadid> value: legacy code.

        Thus several versions of a same FindingAid may be generated.

        Solution :

        To avoid having several versions of a same FindingAid all these
        different versions must be identified as the same FindingAid.

        To do so, the stable_id of all FindingAids will be computed as:

            base_name, ext = osp.splitext(fa_support['data_name'])
            ir_name = '{}.xml'.format(base_name)

        """
        if fa_support:
            ir_name = fa_support["data_name"]
            stable_id = usha1(ir_name)
            # in future extend it to all files as below:
            # base_name, ext = osp.splitext(fa_support['data_name'])
            # for old_ir_name in (eadid, base_name)
            for old_ir_name in (eadid,):
                # for now only ensure oai/xml compliency
                old_stable_id = usha1(old_ir_name)
                if stable_id == old_stable_id:
                    continue
                if old_stable_id in list(self.known_fa_ids.values()) and self.config.get(
                    "reimport"
                ):
                    delete_from_filename(
                        self.store._cnx,
                        old_stable_id,
                        interactive=False,
                        esonly=self.config["esonly"],
                        is_filename=False,
                        logger=self.log,
                    )
                    self.update_fa_redirects(old_stable_id, stable_id, old_ir_name)
                    self.log.warning(
                        "found and deleted an old file" " with stable_id based on %s", old_ir_name
                    )
        else:
            # must not happen
            self.log.warning("no fa_support found, use <eadid> as stable_id")
            ir_name = eadid
            stable_id = usha1(ir_name)
        if self.config.get("reimport"):
            # What is the difference between reimport and force_delete options ?
            if (
                stable_id not in list(self.known_fa_ids.values())
                and eadid.lower() in self.known_fa_ids
            ):
                # the filename had been changed, but not the eadid
                # stable_id is no more an usha1 on the filename
                # (see https://extranet.logilab.fr/ticket/74031756)
                new_stable_id = self.known_fa_ids[eadid.lower()]
                # keep track of the modification
                self.update_fa_redirects(stable_id, new_stable_id, eadid)
                stable_id = new_stable_id
            if stable_id in list(self.known_fa_ids.values()):
                delete_from_filename(
                    self.store._cnx,
                    stable_id,
                    interactive=False,
                    esonly=self.config["esonly"],
                    is_filename=False,
                    logger=self.log,
                )
        return ir_name, stable_id

    def create_ape_ead_xml(self, tree, fa_eid, ir_name, stable_id, service_infos):
        """
        Create the ape_ead_xml file for the imported IR. Since the XML tree can
        be modified by adding IIIF DAOs to the FindingAid or its FComponents,
        the ape_ead_xml file must be created after the original XML is
        processed.

        """
        ape_filepath = generate_ape_ead_xml(
            self.store._cnx, self.config, tree, ir_name, stable_id, service_infos
        )
        ape_filepath = self.storage.storage_handle_ape_ead_filepath(ape_filepath)
        ape_file = self.create_file(ape_filepath)
        if ape_file:
            # add the ape_ead_file inlined relation to the already created FindingAid."
            for data in self.store._data_entities["FindingAid"]:
                if data["eid"] == fa_eid:
                    data["ape_ead_file"] = ape_file["eid"]
                    break
        return ape_file

    def process_eadid(self, eadid, fa_support):
        # check a FindingAid with the same stable_id hasn't already been imported in this import
        if not eadid:
            if not fa_support["data_name"]:
                raise Exception("findingaid with neither file nor eadid")
            eadid = osp.splitext(fa_support["data_name"])[0]
        return eadid

    def import_ead_xmltree(self, tree, service_infos, fa_support, relfiles=None):
        """

        Parameters:
        -----------

        tree          : the lxml ead tree object to process
        service_infos : a map of properties {name, code, eid}
        fa_support    : CW File object hosting the finding aid content (XXX attr_cache)
        relfiles      : files to link to FindingAid
        fa_attrs      : attributes to add to FindingAid
        """

        self.log.info("Start processing XML")
        ead_reader = EADXMLReader(
            tree,
            self.storage.get_file_sha1,
            iiif_ead_policy=service_infos.get("iiif_ead_policy") if service_infos else None,
            relfiles=relfiles,
            log=self.log,
        )
        ead_reader.check_document_validity(service_infos)
        filepath = fa_support["data"]
        creation_date = self.creation_date_from_filepath(filepath)
        header_props = ead_reader.fa_headerprops()
        eadid = self.process_eadid(header_props.pop("eadid", None), fa_support)
        if not eadid:
            raise InvalidFindingAid("Could not process eadid value.")
        ir_name, stable_id = self.process_existing_findingaids(eadid, fa_support)
        if stable_id in self.imported_findingaids:
            self.log.error(
                "Do not import %s with stable_id %s as a document with the same "
                "stable_id has already been imported" % (filepath, stable_id)
            )
            return []
        self.log.debug("Start deleting from file")
        self.delete_from_filename(filepath)
        self.log.debug("Finish deleting from file")

        self.mixed_c_stable_ids = ead_reader.check_c_id_uniformity()
        fa_properties = ead_reader.fa_properties
        self.log.debug("Start creating entities")
        header_attrs = self.create_entity("FAHeader", strip_nones(header_props))
        did_props = fa_properties["did"]
        did_attrs = self.create_did(did_props)
        # XXX if stable_id in already_imported and not self.config.get('reimport'): continue
        referenced_files = fa_properties.pop("referenced_files")
        publisher = service_infos.get("name") or default_service_name(eadid)
        findingaid_attrs = merge_dicts(
            {
                "stable_id": stable_id,
                "eadid": eadid,
                "name": ir_name,
                "fa_header": header_attrs["eid"],
                "did": did_attrs["eid"],
                "findingaid_support": fa_support["eid"],
                "service": service_infos.get("eid"),
                "publisher": publisher,
            },
            pick(
                fa_properties,
                *chain(
                    *(
                        (p, p + "_format")
                        for p in (
                            "description",
                            "bibliography",
                            "bioghist",
                            "acquisition_info",
                            "scopecontent",
                            "accessrestrict",
                            "userestrict",
                            "additional_resources",
                            "notes",
                            "website_url",
                        )
                    )
                ),
            ),
        )
        findingaid_attrs["creation_date"] = creation_date
        findingaid_attrs = self.create_findingaid(findingaid_attrs)
        self.create_referenced_files(findingaid_attrs["eid"], referenced_files)
        index_entries = unique_indices(
            chain(fa_properties["origination"], fa_properties["index_entries"])
        )
        for infos in index_entries:
            self.create_index(infos, target=findingaid_attrs["eid"], fa_attrs=findingaid_attrs)
        # create DigitizedVersions
        self.create_daos(fa_properties["daos"], findingaid_attrs["eid"])
        did_es = es_dict(did_attrs, ["unittitle", "unitid", "abstract", "note"], add_eid=False)
        alltext_values = [
            x
            for x in [did_es["abstract"], did_es["note"], header_attrs.get("titleproper")]
            if x is not None
        ]
        del did_es["abstract"]
        del did_es["note"]
        iiif = bool([d for d in fa_properties["daos"] if d.get("role") == IIIF_MANIFEST_ROLE])
        fa_es_doc = es_dict(
            findingaid_attrs,
            [
                "eadid",
                "description",
                "acquisition_info",
                "index_entries",
                "stable_id",
                "scopecontent",
                "originators",
            ],
            cw_etype="FindingAid",
            fa_stable_id=findingaid_attrs["stable_id"],
            did=did_es,
            digitized=bool(fa_properties["daos"]),
            digitized_all=DZFacetValues.index_values(
                digitized=bool(fa_properties["daos"]), iiif=iiif
            ),
            index_entries=index_entries,
            originators=ead_reader.originators(),
            creation_date=findingaid_attrs["creation_date"],
        )
        # process dates
        fa_es_doc.update(
            dates_for_es_doc(did_attrs, logger=self.log, docid=findingaid_attrs["stable_id"])
        )
        fa_es_doc.update(service_infos_for_es_doc(self.store._cnx, service_infos))
        if fa_es_doc["description"]:
            alltext_values.append(fa_es_doc["description"])
        del fa_es_doc["description"]
        if alltext_values:
            fa_es_doc.update({"alltext": "\n".join(alltext_values)})
        es_documents = [
            self.build_es_doc(
                findingaid_attrs["stable_id"],
                fa_es_doc,
                index_name=self.config["index-name"] + "_all",
            )
        ]
        self.create_entity(
            "EsDocument",
            {"doc": json_dumps(es_documents[0]["_source"]), "entity": findingaid_attrs["eid"]},
        )
        path2eid = {(): None}
        # update findingaid_attrs['originators'] from es_doc
        # we do not use findingaid_attrs further
        findingaid_attrs["originators"] = fa_es_doc["originators"]
        for comp_node, comp_attrs in ead_reader.walk():
            parent_component = path2eid[comp_attrs["path"][:-1]]
            es_doc = self.import_component(
                comp_attrs, findingaid_attrs, service_infos, parent_component=parent_component
            )
            path2eid[comp_attrs["path"]] = es_doc["_source"]["eid"]
            es_documents.append(es_doc)
        self.log.info("Finish processing XML")
        # generate the ape_file with possibly modified IIIF DAOs
        self.create_ape_ead_xml(tree, findingaid_attrs["eid"], ir_name, stable_id, service_infos)
        return es_documents

    def create_referenced_files(self, fa_eid, referenced_files):
        """always create a new file"""
        for file_info in referenced_files:
            feid = self.create_cwfile(**file_info)["eid"]
            self.add_rel(fa_eid, "fa_referenced_files", feid)
            # we should not create a symlink here but the referenced_files paths
            # are hard coded in FindingAid/FAComponent component_additional attribut
            self.storage.storage_make_symlink_to_publish(
                file_info["filepath"], file_info["sha1"], self.config.get("appfiles-dir")
            )

    def import_pdf(self, service_infos, fa_support, metadata=None):
        filepath = fa_support["data"]
        creation_date = self.creation_date_from_filepath(filepath)
        if not self.config["esonly"]:
            self.delete_from_filename(filepath)
        infos = pdf.pdf_infos(filepath)
        if metadata is None:
            metadata = self.pdf_metadata(filepath)
        metadata["creation_date"] = creation_date
        fa_es_attrs = {"text": infos["text"]}
        return [self.import_findingaid(service_infos, metadata, fa_support, **fa_es_attrs)]

    def pdf_metadata(self, filepath):
        directory = osp.dirname(filepath)
        metadata_file = osp.join(directory, "metadata.csv")
        metadata_file = self.storage.storage_get_metadata_file(metadata_file)
        if metadata_file is None:
            all_metadata = {}
        elif metadata_file not in self._pdf_metadata_cache:
            all_metadata = load_metadata_file(self.storage.storage_read_file, metadata_file)
            self._pdf_metadata_cache[metadata_file] = all_metadata
        else:
            all_metadata = self._pdf_metadata_cache[metadata_file]
        filename = osp.basename(filepath)
        if filename not in all_metadata:
            self.log.info("Using dummy metadata for %s", filename)
            filename = osp.basename(filepath)
            return default_csv_metadata(remove_extension(filename))
        return all_metadata[filename]

    def build_es_doc(self, _id, _source, index_name=None):
        """don't change index_entries directly in _source as FindingAid index_entries
        are used later for FAComponents and needs the 'role' and 'normalized' values
        """
        _source["escategory"] = ETYPE_CATEGORIES[_source["cw_etype"]]
        data = deepcopy(_source)
        if "index_entries" in data:
            for index in data["index_entries"]:
                index.pop("role")
                index.pop("normalized")
        doc = {
            "_op_type": "index",
            "_index": self.config["index-name"],
            "_id": _id,
            "_source": data,
        }
        if index_name:
            doc["_index"] = index_name
        return doc


def es_dict(entity_attrs, props, add_eid=True, **kwargs):
    d = {}
    for propname in props:
        value = entity_attrs.get(propname)
        fmt = entity_attrs.get("%s_format" % propname)
        if fmt == "text/html" and value:
            value = strip_html(value)
        d[propname] = value
    for k, v in list(kwargs.items()):
        d[k] = v
    if add_eid:
        d["eid"] = entity_attrs["eid"]
    return d
