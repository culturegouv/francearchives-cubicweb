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
import os.path as osp
import mimetypes
from glob import glob

import csv
from collections import OrderedDict

from cubicweb import Binary

from cubicweb.dataimport.importer import ExtEntity, ExtEntitiesImporter
from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives import init_bfss, SOCIAL_NETWORK_LIST
from cubicweb_francearchives.dataimport import log_in_db


MAPPING_CSV_SCHEMA = OrderedDict(
    [
        ("Code", "code"),
        ("page", None),
        ("category", "category"),
        ("Annexe de ", "annex_of"),
        ("Nom de la collectivité ou de l’institution", "name"),
        ("niveau régional (R) départemental (D) ou autre ()", "level"),
        ("Nom du service d’archives", "name2"),
        ("Adresse", "address"),
        ("Code postal", "zip_code"),
        ("Ville", "city"),
        ("Adresse postale (si différente de l’adresse physique)", "mailing_address"),
        ("Site web", "website_url"),
        ("Nom du contact", "contact_name"),
        ("Numéro de téléphone", "phone_number"),
        ("fax", "fax"),
        ("Adresse électronique", "email"),
        ("Fermeture annuelle", "annual_closure"),
        ("Horaires d’ouverture", "opening_period"),
        ("Flux rss", "rss"),
        ("Dailymotion", "daylmotion"),
        ("Scoop it", "scoop it"),
        ("Pinterest", "pinterest"),
        ("Vimeo", "vimeo"),
        ("Twitter", "twitter"),
        ("Storify", "storify"),
        ("Foursquare", "foursquare"),
        ("Facebook", "facebook"),
        ("   YouTube", "youtube"),
        ("Wikimédia", "wikimédia"),
        ("Flickr", "flickr"),
        ("Blogs", "blog"),
    ]
)

EXPECTED_CSV_HEADER = list(MAPPING_CSV_SCHEMA.keys())


def get_extid(entry):
    return "%s_%s_%s_%s" % (entry["category"], entry["name"], entry["name2"], entry["address"])


def find_annex_of(entries):
    """find last entry with empty `annex_of` field"""
    idx = len(entries) - 1
    while idx > 0:
        entry = entries[idx]
        if not entry["annex_of"]:
            break
        idx -= 1
    return get_extid(entry)


MAPPING_DEP_SCHEMA = OrderedDict(
    [
        ("concaténation", "code"),
        ("Affichage nom long", "name2"),
        ("Affichage nom court", "short_name"),
        ("texte brut", None),
        ("racine", None),
        ("indicatif", None),
        ("numéro", None),
        ("nom de département", None),
        ("chef-lieu", None),
        (
            "Url vers formulaire de recherche / Arborescence de l’inventaire",
            "search_form_url",
        ),  # noqa
    ]
)

EXPECTED_DEP_HEADER = list(MAPPING_DEP_SCHEMA.keys())


def load_services_logos(directory):
    logos = {}
    for filepath in glob(osp.join(directory, "*")):
        code = osp.splitext(osp.basename(filepath))[0]
        logos[code] = filepath
    return logos


def load_departments_map(departements):
    with open(departements) as f:
        dep_map = {}
        reader = csv.reader(f, delimiter=",")
        header = next(reader)  # noqa
        for idx, entry in enumerate(reader):
            entry = {
                MAPPING_DEP_SCHEMA[key]: value.strip()
                for key, value in zip(EXPECTED_DEP_HEADER, entry)
            }
            dep_map[entry["code"]] = entry
        return dep_map


def get_dpt_code(zipcode):
    if zipcode == "97150":  # Saint-Martin
        return "978"
    dpt_code = int(zipcode[:3])
    if len(zipcode) == 4:
        dpt_code = "0%s" % zipcode[0]
    elif 200 <= dpt_code <= 201:
        dpt_code = "2A"
    elif 201 < dpt_code < 210:
        dpt_code = "2B"
    elif dpt_code >= 970:
        dpt_code = str(dpt_code)
    else:
        dpt_code = zipcode[:2]
    return dpt_code


def create_logo(extentities, logos, code_service, extid):
    logo_path = logos.get(code_service)
    if logo_path:
        file_extid = "File-{}".format(extid)
        extentities.append(
            ExtEntity(
                "File",
                file_extid,
                {
                    "title": {str(osp.basename(logo_path))},
                    "data": [Binary(open(logo_path, "rb").read())],
                    "data_name": {str(osp.basename(logo_path))},
                    "data_format": {str(mimetypes.guess_type(logo_path)[0])},
                },
            )
        )
        img_extid = "Image-{}".format(extid)
        extentities.append(
            ExtEntity("Image", img_extid, {"image_file": {file_extid}, "caption": {"Logo"}})
        )
        return img_extid


def build_extentities(directory, departements, logos_directory, schema_attrs=None):
    extentities = []
    dep_map = load_departments_map(departements)
    logos = load_services_logos(logos_directory)
    entries = []
    processed = set()
    with open(directory) as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)  # noqa
        for idx, entry in enumerate(reader):
            entry = {
                MAPPING_CSV_SCHEMA[key]: value.strip()
                for key, value in zip(EXPECTED_CSV_HEADER, entry)
            }
            if not any(entry.values()):
                continue
            # fax no more exists in Service schema
            entry.pop("fax")
            extid = get_extid(entry)
            social_networks = set()
            values = {}
            for key in entry:
                if key in SOCIAL_NETWORK_LIST and entry[key]:
                    social_extid = "social_%s_%s" % (key, extid)
                    social_networks.add(social_extid)
                    extentities.append(
                        ExtEntity(
                            "SocialNetwork", social_extid, {"url": {entry[key]}, "name": {key}}
                        )
                    )
                if schema_attrs and key not in schema_attrs:
                    continue
                if entry[key]:
                    if key == "level":
                        values[key] = {"level-{}".format(entry[key])}
                    else:
                        values[key] = {entry[key]}
            values["service_social_network"] = social_networks
            if "category" not in values:
                values["category"] = {entry.get("category", entry["name"])}
            if entry["annex_of"]:
                # annex case
                if entries:
                    values["annex_of"] = {find_annex_of(entries)}
            if entry["zip_code"]:
                dpt_code = get_dpt_code(entry["zip_code"])
                values["dpt_code"] = {dpt_code}
            code_service = entry["code"]
            data = dep_map.get(code_service)
            if data:
                processed.add(code_service)
                for attr in ("short_name", "code", "search_form_url"):
                    values[attr] = {data[attr]}
            img_extid = create_logo(extentities, logos, code_service, extid)
            if img_extid:
                values["service_image"] = {img_extid}
            extentities.append(ExtEntity("Service", extid, values))
            entries.append(entry)
        # create missing Services
        missings = set(dep_map).difference(processed)
        for service in missings:
            entry = dep_map[service]
            code_service = entry["code"]
            extid = "%s %s" % (code_service, entry["short_name"])
            values = {"category": {entry["name2"]}}
            entry.pop(None)
            for key in entry:
                value = entry[key]
                if value:
                    values[key] = {value}
            img_extid = create_logo(extentities, logos, code_service, extid)
            if img_extid:
                values["service_image"] = {img_extid}
            extentities.append(ExtEntity("Service", extid, values))
    return extentities


@log_in_db
def import_directory(cnx, directory, departements, logos_directory):
    init_bfss(cnx.repo)
    service_schema = cnx.vreg.schema.entity_schema_for("Service")
    schema_attrs = {
        rschema.type for rschema, _ in service_schema.attribute_definitions() if not rschema.meta
    }
    with cnx.allow_all_hooks_but("es"):
        store = RQLObjectStore(cnx)
        importer = ExtEntitiesImporter(cnx.vreg.schema, store)
        importer.import_entities(
            build_extentities(directory, departements, logos_directory, schema_attrs)
        )
        store.flush()
        store.commit()
        store.finish()


if __name__ == "__main__":
    if not __args__:  # noqa
        print("Missing argument: you must specify the filepath to the directory to import")
    else:
        directory = __args__[0]  # noqa
        print("Importing services directory from CSV file %s..." % directory)
        import_directory(cnx, directory, departements, logos_directory)  # noqa
