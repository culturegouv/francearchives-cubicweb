# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2026
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
from datetime import datetime
from itertools import islice

import pytz
import re

from cubicweb_francearchives.dataimport.csv_nomina import (
    AbstractCSVNominaReader,
    CSVNominaFieldnames,
    clean_value,
    invalid_doc_type,
)
from cubicweb_francearchives.entities.nomina import GENDER_MAPPING, nomina_translate_codetype
from cubicweb_francearchives.dataimport.oai_nomina import compute_nomina_stable_id


LOCATION_REG = re.compile(
    r"^(?P<commune>[^()]+)\s*\(\s*(?P<department>[^,]+),\s*(?P<country>[^)]+)\s*\)$"
)

SOCFACE_DOCTYPE = "RP"


def is_year(value):
    if value.isdigit():
        year = int(value)
        return 1000 <= year <= 9999
    return False


def clean_key(key):
    return key.replace("’", "'")


class CSVNominaSocfaceReader(AbstractCSVNominaReader):
    optional_fields = ["notice_id", "delete"]

    def get_doctype_fieldnames(self, doctype=SOCFACE_DOCTYPE):
        return CSVNominaFieldnames.fieldnames[doctype]

    def get_doctype_required_columns(self, doctype):
        return (
            "id_arkindex",
            "names",
        )

    def get_record_identifier(self, values):
        """get identifier by document type / format"""
        column = "id_arkindex"  # notice from the initial import by socface
        identifier = values[column]
        if not identifier:
            column = "notice_id"  # notice added later by the service
            identifier = values[column]
        return identifier, column

    def compute_title(self, row):
        return (", ").join([row["names"] or "?", row["forenames"] or "?"])

    def compute_stable_id(self, identifier):
        return compute_nomina_stable_id(self.service.code, identifier)

    def index_alltext(self, values):
        old_lang = self.cnx.lang
        # ensure the language (we only index in french)
        self.cnx.set_language("fr")
        content = []
        content.extend(
            (
                GENDER_MAPPING.get(values.get("gender", ""), ""),
                nomina_translate_codetype(values["act_type"]),
            )
        )
        all_locations = []
        # avoid to add  several times the same value in alltext
        # try to preserve the order for tests
        for key, value in values.items():
            for postfix in ("_country", "_department", "_commune"):
                if key.endswith(postfix) and value and value not in all_locations:
                    # strip () (?)
                    all_locations.append(value)
        content.extend(list(all_locations))
        content = " ".join(content)
        values["alltext"] = content
        self.cnx.set_language(old_lang)
        return values

    def index_birth_locations(self, value):
        if value:
            self.log.warning(f"index_birth_locations : {value}")
            return {"birth_commune": value}
        return {"birth_commune": None}

    def index_dates(self, row, year, attr, with_year=False):
        if year:
            names = f"{row['names']} {row['forenames']}, {row['id_arkindex']}"
            if is_year(year):
                dates = {f"{attr}_date": year, f"{attr}_dates": {"gte": year, "lte": year}}
                if with_year:
                    dates[f"{attr}_year"] = year
                return dates
            else:
                self.log.warning(
                    f'{names} "Date de naissance (traité)" value: {year} is not an year.'
                )
                return {f"{attr}_date": year}
        return {f"{attr}_date": None}

    def index_event_locations(self, value):
        data = {
            "event_commune": None,
            "event_department": None,
            "event_country": None,
        }
        if value:
            match = LOCATION_REG.match(value)
            if match:
                return {
                    "event_commune": match.group("commune"),
                    "event_department": match.group("department"),
                    "event_country": match.group("country"),
                }
            else:
                # XXX keep a litteral value (?)
                self.log.error(f"index_event_locations: could not parse {value}")
                data["event_commune"] = value
                data["event_country"] = "France"
        return data

    def index_gender(self, value):
        if value and value.lower() not in GENDER_MAPPING:
            self.log.error(f""""Genre (traité)" value n'est pas une valeur valide : {value}""")
        return {"gender": value.lower() if value else ""}

    def index_teklia_url(self, row):
        source = row.get("source_url")
        if not source:
            return {"teklia_url": row["teklia_url"]}
        return {"teklia_url": ""}

    def index_missing_fields(self, row, indenfifier):
        return {
            "act_type": SOCFACE_DOCTYPE,
            "creation_date": datetime.now(pytz.utc),
            "modification_date": datetime.now(pytz.utc),
            "service": self.service.eid,
            "stable_id": self.compute_stable_id(indenfifier),
            "title": self.compute_title(row),
        }

    def import_records(
        self, storage, filepath, doctype=SOCFACE_DOCTYPE, delimiter="\t", chunksize=1000
    ):
        if invalid_doc_type(doctype):
            self.log.error("Abort import for unknown document type %s", doctype)
            return
        fieldnames = self.get_doctype_fieldnames(doctype)
        with storage.storage_read_file(filepath) as stream:
            reader = csv.DictReader(
                stream,
                delimiter=delimiter,
            )
            docs, idx = 0, 0
            while True:
                batch = list(islice(reader, chunksize))
                if not batch:
                    break
                for line in batch:
                    idx += 1
                    row = {
                        fieldnames[clean_key(key)]: clean_value(value)
                        for key, value in line.items()
                    }
                    if self.check_missing_required_columns(doctype, row, idx):
                        continue
                    identifier, column = self.get_record_identifier(row)
                    if not identifier:
                        self.log.error(
                            "line %s: could not find identifier for deletion in column '%s': %s",
                            idx,
                            column,
                            row,
                        )
                        continue
                    if row.get("delete") in ("y", "yes"):
                        self.add_records_to_delete(idx, row, SOCFACE_DOCTYPE)
                        continue
                    if self.check_duplicated_records(idx, row):
                        continue
                    values = {}
                    for key in row.keys():
                        if key is None or key in ("service_code", ""):
                            continue
                        elif key == "birth_date":
                            values.update(self.index_dates(row, row[key], "birth"))
                        elif key == "gender":
                            values.update(self.index_gender(row[key]))
                        elif key == "event_date":
                            values.update(self.index_dates(row, row[key], "event", with_year=True))
                        elif key == "event_place":
                            values.update(self.index_event_locations(row[key]))
                        elif key in (
                            "names",
                            "forenames",
                            "occupations",
                            "occupations_index",
                        ):
                            values[key] = [row[key]]
                        elif key == "teklia_url":
                            values.update(self.index_teklia_url(row))
                        else:
                            values[key] = row[key]
                    values.update(self.index_missing_fields(row, identifier))
                    self.index_alltext(values)
                    docs += 1
                    yield self.build_es_doc(values)
                self.log.info(f"Processed {docs} documents from {filepath}")

    def build_es_doc(self, values):
        return {
            "_op_type": "index",
            "_index": self.config["nomina-index-name"],
            "_id": values["stable_id"],
            "_source": values,
        }
