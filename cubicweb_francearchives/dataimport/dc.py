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

import csv
from collections import defaultdict
import os.path as osp

import logging

from cubicweb.utils import json_dumps
from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives import init_bfss, IIIF_MANIFEST_ROLE
from cubicweb_francearchives.dataimport import (
    clean_row_dc_csv,
    strip_html,
    default_csv_metadata,
    get_date,
    get_year,
    clean_values,
    component_stable_id_for_dc,
    load_metadata_file,
    sqlutil,
    es_bulk_index,
    log_in_db,
    service_infos_from_filepath,
    load_services_map,
)
from cubicweb_francearchives.dataimport.ead import (
    Reader,
    capture_exception,
    service_infos_for_es_doc,
)
from cubicweb_francearchives.storage import S3BfssStorageMixIn

from cubicweb_francearchives.dataimport.stores import create_massive_store
from cubicweb_francearchives.dataimport.scripts.generate_ape_ead import (
    generate_ape_ead_from_other_sources,
)
from cubicweb_francearchives.dataimport.sqlutil import ead_foreign_key_tables
from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.utils import is_absolute_url

LOGGER = logging.getLogger()
CSV_METADATA_CACHE = {}


def parse_dc_csv(read_func, fpath, fieldnames, log):
    """Generate a data dict by CSV entry of `fpath`"""
    rows = []
    with read_func(fpath) as csvfile:
        dcreader = csv.DictReader(csvfile)
        # clean file fieldnames
        # remove possible whitespaces in header names
        dcreader.fieldnames = [f.strip() for f in dcreader.fieldnames]
        mandatory_fields = [field for field, mandatory in fieldnames if mandatory]
        if len(dcreader.fieldnames) < len(mandatory_fields):
            log.error(
                f"""Abort importing {fpath}: only found {len(dcreader.fieldnames)} fieldnames {", ".join(['"%s"' % f for f in  dcreader.fieldnames])} while {len(mandatory_fields)} expected. Please, check fields delimiter which must be ','"""  # noqa
            )
            return rows
        for row in dcreader:
            for key in list(row.keys()):
                if key:
                    value = row.pop(key) or ""
                    row[key] = value.strip()
            rows.append(row)
    return rows


def csv_metadata_without_cache(filepath, metadata_filepath=None):
    """if import is done from cms interface:
    - dont look for the metadata in the same direcrtory
    - dont use the cache"""
    filename = osp.basename(filepath)
    if not metadata_filepath:
        return default_csv_metadata(filename)
    st = S3BfssStorageMixIn()
    metadata_filepath = st.storage_get_metadata_file(metadata_filepath)
    return load_metadata_file(st.storage_read_file, metadata_filepath, csv_filename=filename)[
        filename
    ]


def csv_metadata_from_cache(filepath, metadata_filepath=None):
    """if import is done from CWCcommand `import_dc`:
    - look for the metadata in the same direcrtory
    - use the cache
    """
    st = S3BfssStorageMixIn()
    if metadata_filepath:
        return load_metadata_file(st.storage_read_file, metadata_filepath)[osp.basename(filepath)]
    # if metadata_filepath is None, try to find a metadata stored in the same
    # directory as filepath
    directory = osp.dirname(filepath)
    metadata_file = osp.join(directory, "metadata.csv")
    all_metadata = {}
    if metadata_file is None:
        LOGGER.warning(f"{metadata_file} file is missing")
    elif metadata_file not in CSV_METADATA_CACHE:
        all_metadata = load_metadata_file(st.storage_read_file, metadata_file)
        CSV_METADATA_CACHE[metadata_file] = all_metadata
    else:
        all_metadata = CSV_METADATA_CACHE[metadata_file]
    filename = osp.basename(filepath)
    if filename not in all_metadata:
        LOGGER.info("using dummy metadata for %s", filename)
        return default_csv_metadata(filename)
    return all_metadata[filename]


class CSVReader(Reader):
    """expected columns for FAComoponents are:"""

    fieldnames = (
        ("identifiant_cote", True),
        ("titre", True),
        ("origine", True),
        ("date1", True),
        ("date2", True),
        ("description", True),
        ("type", True),
        ("format", True),
        ("index_matiere", True),
        ("index_lieu", True),
        ("index_personne", True),
        ("index_collectivite", True),
        ("langue", True),
        ("conditions_acces", True),
        ("conditions_utilisation", True),
        ("source_complementaire", True),
        ("identifiant_URI", True),
        ("source_image", True),
        ("cote_complete", False),  # optional
    )

    def cleaned_rows(self, filepath):
        """check rows/files integrity"""
        res = []
        data = dict(
            (idx, row)
            for idx, row in enumerate(
                parse_dc_csv(self.storage.storage_read_file, filepath, self.fieldnames, self.log)
            )
        )
        if not data:
            return res
        csv_empty_value = 'Skip row {row}: missing required value for column "{col}" \n'
        csv_missing_col = 'The required column "{col}" is missing \n'
        mandatory_columns = ("titre", "identifiant_cote")
        identifiant_cotes = defaultdict(list)
        # check for duplicated "identifiant_cote"
        for idx, row in data.items():
            identifiant_cotes[row["identifiant_cote"]].append(idx)
        for cote, idx in identifiant_cotes.items():
            if len(idx) > 1:
                for i in idx:
                    data.pop(i)
                self.log.warning(
                    f"""Skip rows {", ".join([str(i) for i in idx])} with duplicated values {cote} for 'identifiant_cotes' \n"""  # noqa
                )
        # check missing / wrong values
        for idx, row in data.items():
            errors = []
            if idx == 0:
                errors.extend(
                    [csv_missing_col.format(col=col) for col in mandatory_columns if col not in row]
                )
                if errors:
                    break
            else:
                errors.extend(
                    [
                        csv_empty_value.format(row=idx, col=col)
                        for col in mandatory_columns
                        if not row[col]
                    ]
                )
            if not errors:
                res.append(clean_row_dc_csv(row))
            else:
                self.log.warning(" ".join(errors))
        return res

    def import_filepath(self, service_infos, filepath, metadata_filepath=None, **kwargs):
        # check csv file data are valid
        cleaned_csv_data = self.cleaned_rows(filepath)
        if not cleaned_csv_data:
            self.log.error(f"{filepath}: no data to import.")
            return []
        self._stable_id_map = None
        fa_support = self.create_file(filepath)
        if fa_support is None:
            return []
        if not self.config.get("dc_no_cache"):
            metadata = csv_metadata_without_cache(filepath, metadata_filepath)
        else:
            metadata = csv_metadata_from_cache(filepath, metadata_filepath)
        self.update_authorities_cache(service_infos.get("eid"))
        creation_date = self.creation_date_from_filepath(filepath)
        metadata["creation_date"] = creation_date
        fa_es_doc = self.import_findingaid(service_infos, metadata, fa_support)
        es_docs = [fa_es_doc]
        # findingaid_attrs should probably not be based on es_documents, but
        # so far it contains all needed values except "service" needed for "index_entries"
        # method
        findingaid_attrs = {k: v for k, v in fa_es_doc["_source"].items()}
        findingaid_attrs.update(
            {"service": service_infos.get("eid"), "creation_date": creation_date}
        )

        for order, row in enumerate(cleaned_csv_data):
            es_docs.append(self.import_facomponent(row, findingaid_attrs, order, service_infos))
        self.delete_from_filename(filepath)
        self.storage.storage_make_symlink_to_publish(
            filepath, fa_support["data_hash"], self.config.get("appfiles-dir")
        )
        return es_docs

    def import_facomponent(self, entry, findingaid_data, order, service_infos):
        fa_stable_id = findingaid_data["stable_id"]
        stable_id_component = entry["identifiant_cote"]
        cote = entry.get("cote_complete", stable_id_component)
        originator = entry.get("origine")
        did_attrs = {
            "unitid": cote,
            "unittitle": entry["titre"],
            "unitdate": get_date(entry.get("date1"), entry.get("date2")),
            "startyear": get_year(entry.get("date1")),
            "stopyear": get_year(entry.get("date2")),
            "physdesc": self.richstring_html(entry.get("format"), "physdesc"),
            "physdesc_format": "text/html",
            "origination": originator,
            "lang_description": self.richstring_html(entry.get("langue"), "language"),
            "lang_description_format": "text/html",
        }
        did_data = self.create_entity("Did", clean_values(did_attrs))
        comp_attrs = {
            "finding_aid": findingaid_data["eid"],
            "stable_id": component_stable_id_for_dc(stable_id_component, fa_stable_id),
            "did": did_data["eid"],
            "scopecontent": self.richstring_html(entry.get("description"), "scopecontent"),
            "scopecontent_format": "text/html",
            "additional_resources": self.richstring_html(
                entry.get("source_complementaire"), "additional_resources"
            ),
            "additional_resources_format": "text/html",
            "accessrestrict": self.richstring_html(entry.get("conditions_acces"), "accessrestrict"),
            "accessrestrict_format": "text/html",
            "userestrict": self.richstring_html(entry.get("conditions_utilisation"), "userestrict"),
            "userestrict_format": "text/html",
            "component_order": order,
        }
        comp_attrs["creation_date"] = findingaid_data["creation_date"]
        comp_data = self.create_entity("FAComponent", clean_values(comp_attrs))
        comp_eid = comp_data["eid"]
        # add daos
        daodefs = self.digitized_versions(entry)
        for daodef in daodefs:
            digit_ver_attrs = self.create_entity("DigitizedVersion", clean_values(daodef))
            self.add_rel(comp_eid, "digitized_versions", digit_ver_attrs["eid"])
        iiif = bool([d for d in daodefs if d.get("role") == IIIF_MANIFEST_ROLE])
        es_doc = self.build_complete_es_doc(
            "FAComponent",
            comp_data,
            did_data,
            fa_stable_id=findingaid_data["stable_id"],
            scopecontent=strip_html(comp_attrs.get("scopecontent")),
            index_entries=self.index_entries(entry, comp_eid, findingaid_data),
            digitized=bool(daodefs),
            digitized_all=DZFacetValues.index_values(digitized=bool(daodefs), iiif=iiif),
            originators=[originator] if originator else None,
            **service_infos_for_es_doc(self.store._cnx, service_infos),
        )
        self.create_entity("EsDocument", {"doc": json_dumps(es_doc["_source"]), "entity": comp_eid})
        return es_doc

    def digitized_versions(self, entry):
        daos = []
        identifiant_uri = entry.get("identifiant_uri")
        if not self.is_dao_url_valid(identifiant_uri):
            LOGGER.error(
                "do not import import dao with url length %s: %r",
                len(identifiant_uri),
                identifiant_uri,
            )
            identifiant_uri = None
        if identifiant_uri and not is_absolute_url(identifiant_uri):
            identifiant_uri = None
        source_image = entry.get("source_image")
        if not self.is_dao_url_valid(source_image):
            LOGGER.error(
                "do not import import dao with url length %s: %r", len(source_image), source_image
            )
            source_image = None
        if source_image:
            daos.append({"illustration_url": source_image, "url": None, "role": "thumbnail"})
        if identifiant_uri:
            daos.append({"url": identifiant_uri, "illustration_url": None, "role": None})
        return daos


def import_filepaths(cnx, config, filepaths, metadata_filepath=None):
    for filepath in filepaths:
        import_filepath(cnx, config, filepath, metadata_filepath=None)


@log_in_db
def import_filepath(cnx, config, filepath, metadata_filepath=None):
    foreign_key_tables = ead_foreign_key_tables(cnx.vreg.schema)
    if not config["esonly"]:
        store = create_massive_store(cnx, nodrop=config["nodrop"])
        store.master_init()
        if config["nodrop"]:
            with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
                sqlutil.disable_triggers(su_cnx, foreign_key_tables)
        cnx.commit()
    csv_import_filepath(cnx, config, filepath, metadata_filepath)
    if not config["esonly"]:
        store.finish()
        store.commit()
    if config["nodrop"]:
        with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
            sqlutil.enable_triggers(su_cnx, foreign_key_tables)
    generate_ape_ead_from_other_sources(cnx)


def csv_import_filepath(cnx, config, filepath, metadata_filepath=None):
    """Import a finding aid from `fpath` CSV file possibly using `metadata_filepath`
    CSV file"""

    services_map = load_services_map(cnx)
    service_infos = service_infos_from_filepath(filepath, services_map)
    # bfss should be initialized to enable `FSPATH` in rql
    init_bfss(cnx.repo)
    if not config["esonly"]:
        store = create_massive_store(cnx, slave_mode=True)
    else:
        store = RQLObjectStore(cnx)
    readercls = config.get("readercls", CSVReader)
    reader = readercls(config, store)
    es_docs = []
    try:
        es_docs = reader.import_filepath(service_infos, filepath, metadata_filepath)
    except Exception as exc:
        import traceback

        traceback.print_exc()
        print("failed to import", repr(filepath))
        LOGGER.exception("failed to import %r", filepath)
        capture_exception(exc, filepath)
        return
    if not config["esonly"]:
        store.flush()
        store.commit()
    if es_docs and not config["noes"]:
        indexer = cnx.vreg["es"].select("indexer", cnx)
        es = indexer.get_connection()
        es_bulk_index(es, es_docs, logger=LOGGER)
