# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2026
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

from collections import defaultdict
from datetime import datetime
import csv
import json
import os.path as osp

import pytz

from cubicweb_francearchives.dataimport import strip_nones
from cubicweb_francearchives.dataimport.csv_nomina import (
    AbstractCSVNominaReader,
    invalid_doc_type,
    check_document_fieldnames,
    check_socface_update_fieldnames,
    clean_value,
    check_doctype,
    IGNORE_KEY,
    SOCFACE_UPDATE_REQUIRED_COLUMNS,
    SOCFACE_UPDATE_ALLOWED_COLUMNS,
)

from cubicweb_francearchives.dataimport.oai_nomina import (
    str2bool,
    compute_nomina_stable_id,
)
from cubicweb_francearchives.entities.nomina import (
    NominaIndexJsonDataSerializable,
)

# Default country for SOCFACE census records
DEFAULT_EVENT_COUNTRY = "France"

HERE = osp.dirname(__file__)


def load_departments_map():
    csv_path = osp.join(HERE, "data", "departements-france.csv")
    with open(csv_path) as stream:
        dep_map = {}
        reader = csv.DictReader(stream, delimiter=",")
        for idx, entry in enumerate(reader):
            code = entry["code_departement"].strip()
            name = entry["nom_departement"].strip()
            if code and name:
                dep_map[code] = name
        return dep_map


DEPARTMENTES_MAPS = load_departments_map()


class CSVNominaReader(AbstractCSVNominaReader):
    """CSV reader for initial import of Nomina data.

    This import completely replaces existing documents in Elasticsearch.
    """

    def import_records(self, storage, filepath, doctype, delimiter=";", chunksize=1000):
        """Index NominaRecords.

        :param String filepath  : Filepath to process
        :param String doctype   : CSV file data type
        :param String delimiter : CSV delimiter
        """
        if invalid_doc_type(doctype):
            self.log.error("Abort import for unknown document type %s", doctype)
            return
        fieldnames = self.get_doctype_fieldnames(doctype)
        func = self.extract_nomina_data if doctype == "OAI" else self.build_nomina_data
        with storage.storage_read_file(filepath) as stream:
            # check headers
            file_fieldnames = csv.DictReader(stream, delimiter=delimiter).fieldnames
            errors = check_document_fieldnames(self.cnx, doctype, file_fieldnames)
            if errors:
                self.log.error(
                    "Abort import for document type %s: %s" % (doctype, "\n".join(errors))
                )
                return
            stream.seek(0)
            reader = csv.DictReader(
                stream,
                delimiter=delimiter,
                fieldnames=list(fieldnames.keys()),
            )
            next(reader, None)  # skip the headers
            for idx, line in enumerate(reader, start=1):
                try:
                    if not any(line.values()):
                        continue
                    values = {
                        fieldnames[key]: clean_value(value)
                        for key, value in line.items()
                        if key and value
                    }
                    if self.check_missing_required_columns(doctype, values, idx):
                        continue
                    if values.get("delete") in ("y", "yes"):
                        self.add_records_to_delete(idx, values, doctype)
                        continue
                    data = func(values, doctype)
                    if data:
                        if self.check_duplicated_records(idx, values):
                            continue
                        data["creation_date"] = datetime.now(pytz.utc)  # XXX to be corrected
                        self.processed_records += 1
                        yield from self.build_es_docs(strip_nones(data))
                except StopIteration:
                    break
                except csv.Error as exception:
                    self.log.warning(f"line {idx}: skipped line ({exception})")
                    continue

    def build_es_source(self, attrs):
        authorities, labels = [], []
        identifiant = attrs["stable_id"]
        for eid, label in self.linked_authorities.get(identifiant, []):
            authorities.append(eid)
            labels.append(label)
        json_data = json.loads(attrs["json_data"])
        json_data["oai_id"] = attrs.get("oai_id")
        processed_list = NominaIndexJsonDataSerializable(self.cnx, json_data).process_json_data(
            self.service.code, identifiant, alltext=" ".join(labels)
        )
        # stable_id wil be generated in process_json_data: it will be
        # recalculated in case of splites notices
        base_data = {
            "service": self.service.eid,
            "creation_date": attrs["creation_date"],
            "modification_date": attrs["creation_date"],
            "agent": authorities,
        }
        return [{**base_data, **doc} for doc in processed_list]

    def build_es_docs(self, values):
        for source in self.build_es_source(values):
            yield {
                "_op_type": "index",
                "_index": self.config["nomina-index-name"],
                "_id": values["stable_id"],
                "_source": source,
            }

    def extract_nomina_data(self, values, doctype):
        """
        process CSV resulting from OAI-PMH harvest

        :param dict values  : processed CSV row
        """
        # check doctype
        data = json.loads(values["json_data"])
        oai_id = values["oai_id"]
        if not data.get("t"):
            self.log.error("Ignore notice %s without document type" % oai_id)
            return None
        # check persons data
        persons = data.get("p")
        if not persons or not len(persons) or not len(persons[0]):
            self.log.error("Ignore notice %s without personal data" % oai_id)
            return None
        return {
            "stable_id": values["stable_id"],
            "oai_id": oai_id,
            "service": self.service.eid,
            "json_data": values["json_data"],
        }

    def get_record_identifier(self, values):
        """get identifier by document type / format"""

        """get notice identifier

        :param dict data  : processed CSV row
        """
        if "oai_id" in values:
            return values["oai_id"], "oai_id"
        if "notice_id" in values:
            return values["notice_id"], "notice_id"

    def build_nomina_data(self, values, doctype):
        """Build NominaRecord data

        :param dict values  : processed CSV row
        :param dict doctype : document type

        """
        if not check_doctype(values, doctype, self.log):
            return None
        complement_data = {}
        locations = defaultdict(dict)  # one event by record
        dates = defaultdict(dict)  # one event by record
        events = defaultdict(dict)
        # build data from values
        uri = values.pop("U", None)
        persons = []
        persons_data = defaultdict(dict)
        for key, value in values.items():
            if not value:
                continue
            if key == IGNORE_KEY:
                continue
            section, code = key.split("_", 1)
            if section == "P":
                try:
                    code, gender = code.split("_")
                except ValueError:
                    gender = ""
                persons_data[gender].update({code: value})
            elif section in ("C"):
                if code == "o":
                    value = [value]
                if code in ("d", "p"):
                    value = str2bool(value)
                complement_data[code] = value
            elif section in "L":
                event, prec = code.split("_")
                event = doctype if event == "XXX" else event
                locations[event].update({prec: value})
            elif section == "D":
                event, prec = code.split("_")
                event = doctype if event == "XXX" else event
                dates[event].update({prec: value})
        if not persons_data:
            return None
        for key, person in persons_data.items():
            if key:
                person.update({"g": key})
            persons.append(person)
        # build events
        for key, value in dates.items():
            desc = {"d": value}
            loc = locations.pop(key, None)
            if loc:
                desc["l"] = loc
            events[key] = [desc]
        # build locations
        for key, value in locations.items():
            assert key not in events
            events[key] = [{"l": value}]
        for key, _values in events.items():
            for _value in _values:
                location = _value.get("l")
                if location and not location.get("d"):
                    department = DEPARTMENTES_MAPS.get(location.get("dc"))
                    if department:
                        location["d"] = department
        json_data = {
            "t": doctype,
            "e": events,
            "p": persons,
            "c": complement_data,
            "i": values["notice_id"],
        }
        if uri:
            json_data["u"] = uri
        data = {
            "stable_id": compute_nomina_stable_id(self.service.code, values["notice_id"]),
            "service": self.service.eid,
            "json_data": json.dumps(json_data),
        }
        return data


# ============================================================================
# CSV READER FOR SOCFACE PARTIAL UPDATES
# ============================================================================


class CSVNominaUpdateReader(CSVNominaReader):
    """CSV reader specialized for partial census updates (SOCFACE format).

    This class performs partial updates in Elasticsearch:
    - Only provided fields are updated
    - Unmodified fields are preserved
    - Strict validation of allowed columns
    - Document existence check before update

    Required CSV format:
    - Required column: "Identifiant Arkindex"
    - At least one update column from the allowed list
    - No forbidden columns

    :cvar UPDATE_REQUIRED_COLUMNS: Required CSV columns
    :cvar UPDATE_ALLOWED_COLUMNS: Allowed CSV columns for updates
    """

    # Validation constants (references to __init__.py)
    UPDATE_REQUIRED_COLUMNS = SOCFACE_UPDATE_REQUIRED_COLUMNS
    UPDATE_ALLOWED_COLUMNS = SOCFACE_UPDATE_ALLOWED_COLUMNS

    def __init__(self, config, cnx, service_code, log=None):
        """Initialize update reader.

        :param config: Elasticsearch configuration
        :param cnx: CubicWeb connection
        :param service_code: Service code
        :param log: Logger
        """
        super().__init__(config, cnx, service_code, log=log)
        self.not_found_records = 0

    def get_doctype_required_columns(self, doctype):
        """Override to use SOCFACE update required columns.

        For partial updates, only 'id_arkindex' is required.
        This differs from initial SOCFACE import which requires both
        'id_arkindex' and 'names'.

        :param doctype: Document type (should be "SOCFACE")
        :return: Tuple of required column attributes
        """
        if doctype == "SOCFACE":
            return ("id_arkindex",)
        return super().get_doctype_required_columns(doctype)

    def build_nomina_data(self, values, doctype):
        """Build NominaRecord data for SOCFACE partial update.

        Uses id_arkindex as identifier (not notice_id like standard format).
        Builds partial json_data containing only provided update fields.

        :param dict values: processed CSV row
        :param str doctype: document type (must be "SOCFACE")
        :return: Dict with stable_id, service, json_data or None if invalid
        """
        if doctype != "SOCFACE":
            return super().build_nomina_data(values, doctype)

        id_arkindex = values.get("id_arkindex")
        if not id_arkindex:
            self.log.error("Missing id_arkindex for SOCFACE update")
            return None

        json_data = {
            "t": "RP",
            "p": [],
            "e": {},
            "c": {},
            "i": id_arkindex,
        }

        person = {}
        person_field_mapping = {
            "names": "n",
            "forenames": "f",
            "gender": "g",
            "age": "age",
            "birth_date": "birth_date",
            "birth_place": "birth_place",
            "household_role": "household_role",
            "occupations": "occupations",
            "occupations_index": "occupations_index",
            "employer": "employer",
            "nationality": "nationality",
            "civil_status": "civil_status",
            "additional_info": "additional_info",
        }

        for field_name, person_key in person_field_mapping.items():
            if values.get(field_name):
                if field_name in (
                    "names",
                    "forenames",
                    "occupations",
                    "occupations_index",
                ):
                    person[person_key] = [values[field_name]]
                else:
                    person[person_key] = values[field_name]

        if person:
            json_data["p"].append(person)

        event_data = {}
        if values.get("event_date"):
            event_data["d"] = values["event_date"]
            event_data["year"] = values["event_date"]

        event_location = {}
        for field_name, loc_key in [
            ("event_place", "commune"),
            ("event_department", "department"),
            ("event_commune", "commune"),
        ]:
            if values.get(field_name):
                event_location[loc_key] = values[field_name]

        if event_location:
            event_location["country"] = "France"
            event_data["l"] = event_location

        if event_data:
            json_data["e"]["RP"] = [event_data]

        complement_field_mapping = {
            "cote": "cote",
            "doc_page_line_id": "doc_page_line_id",
            "household_id": "household_id",
            "act_type": "act_type",
            "source_url": "source_url",
            "teklia_url": "teklia_url",
        }

        for field_name, complement_key in complement_field_mapping.items():
            if values.get(field_name):
                json_data["c"][complement_key] = values[field_name]

        data = {
            "stable_id": compute_nomina_stable_id(self.service.code, id_arkindex),
            "service": self.service.eid,
            "json_data": json.dumps(json_data),
        }

        return data

    def get_record_identifier(self, values):
        """Get identifier for SOCFACE update records.

        Uses id_arkindex as the primary identifier.

        :param dict values: processed CSV row
        :return: Tuple (identifier, column_name) or None if not found
        """
        if values.get("id_arkindex"):
            return values["id_arkindex"], "id_arkindex"
        return None

    def check_update_fieldnames(self, fieldnames):
        """Validate CSV columns for an update.

        :param fieldnames: List of CSV column names
        :return: List of errors (empty if valid)
        """
        return check_socface_update_fieldnames(self.cnx, fieldnames)

    def import_records(self, storage, filepath, doctype, delimiter=";", chunksize=1000):
        """Import and update SOCFACE census records.

        :param storage: Storage handler
        :param filepath: Path to CSV file
        :param doctype: Document type (must be "SOCFACE")
        :param delimiter: CSV delimiter
        :param chunksize: Batch size for ES operations
        :yield: Elasticsearch documents to update
        """
        # Strict doctype validation
        if doctype != "SOCFACE":
            self.log.error(
                "CSVNominaUpdateReader only supports SOCFACE doctype. Received: %s",
                doctype,
            )
            return

        fieldnames = self.get_doctype_fieldnames(doctype)

        with storage.storage_read_file(filepath) as stream:
            # 1. Check headers with strict update validation
            file_fieldnames = csv.DictReader(stream, delimiter=delimiter).fieldnames

            # SOCFACE update specific validation
            errors = self.check_update_fieldnames(file_fieldnames)
            if errors:
                self.log.error(
                    "Abort import for document type %s (update mode): %s",
                    doctype,
                    "\n".join(errors),
                )
                return

            stream.seek(0)
            reader = csv.DictReader(
                stream,
                delimiter=delimiter,
                fieldnames=list(file_fieldnames),
            )
            next(reader, None)  # skip headers

            # Initialize ES connection for existence check
            indexer = self.cnx.vreg["es"].select("nomina-indexer", self.cnx)
            es = indexer.get_connection()
            if not es or not es.ping():
                self.log.error("Elasticsearch unavailable for document existence check")
                return

            idx = 1
            batch_data = []  # Collect data for bulk existence check

            while True:
                try:
                    line = next(reader)
                except csv.Error as exception:
                    self.log.warning("line %s: skipped line (%s)", idx, exception)
                    idx += 1
                    continue
                except StopIteration:
                    break

                if not any(line.values()):
                    idx += 1
                    continue

                # Clean values - convert empty strings to None
                values = {
                    fieldnames[key]: clean_value(value) if value else None
                    for key, value in line.items()
                    if key
                }

                if self.check_missing_required_columns(doctype, values, idx):
                    idx += 1
                    continue

                if values.get("delete") in ("y", "yes"):
                    self.add_records_to_delete(idx, values)
                    idx += 1
                    continue

                # Build data
                data = self.build_nomina_data(values, doctype)
                if not data:
                    idx += 1
                    continue

                if self.check_duplicated_records(idx, values):
                    idx += 1
                    continue

                # Collect for bulk existence check
                stable_id = data.get("stable_id")
                if stable_id:
                    batch_data.append((idx, stable_id, values, data))

                # Process batch when chunksize reached
                if len(batch_data) >= chunksize:
                    yield from self._process_batch(es, batch_data)
                    batch_data = []

                idx += 1

            # Process remaining documents
            if batch_data:
                yield from self._process_batch(es, batch_data)

    def _process_batch(self, es, batch_data):
        """Process a batch of documents with bulk existence check.

        :param es: Elasticsearch client
        :param batch_data: List of (idx, stable_id, values, data) tuples
        :yield: Elasticsearch documents to update
        """
        if not batch_data:
            return

        # Bulk check which documents exist
        stable_ids = [item[1] for item in batch_data]
        existing_ids = set(self.bulk_check_documents_exist(es, stable_ids))

        # Filter and yield only existing documents
        for idx, stable_id, values, data in batch_data:
            if stable_id not in existing_ids:
                arkindex = values.get("id_arkindex", "unknown")
                self.log.warning(
                    "line %s: document with arkindex '%s' " "not found in Elasticsearch - skipped",
                    idx,
                    arkindex,
                )
                self.not_found_records += 1
                continue

            # Update partial - do not force creation_date
            self.processed_records += 1
            # Merge data (stable_id, service) with values (CSV fields)
            merged_data = {**data, **values}
            yield self.build_es_doc(merged_data)

    def bulk_check_documents_exist(self, es, stable_ids):
        """Check which documents exist in Elasticsearch using bulk mget.

        :param es: Elasticsearch client
        :param stable_ids: List of stable_ids to check
        :return: List of stable_ids that exist
        """
        if not stable_ids:
            return []

        try:
            docs = es.mget(index=self.config["nomina-index-name"], body={"ids": stable_ids})
            return [
                stable_id for stable_id, doc in zip(stable_ids, docs["docs"]) if doc.get("found")
            ]
        except Exception as e:
            self.log.error("Error bulk checking documents existence: %s", e)
            # Fallback: return empty list (all will be skipped)
            return []

    def build_es_doc(self, values):
        """Build Elasticsearch document for partial update.

        Uses _op_type: "update" with "doc" to modify fields.
        Empty values (None, "", []) are set as empty in Elasticsearch.

        :param values: Document data (includes stable_id and CSV fields)
        :return: Dict formatted for ES bulk API
        """
        return {
            "_op_type": "update",
            "_index": self.config["nomina-index-name"],
            "_id": values["stable_id"],
            "doc": self.build_es_source_for_update(values),
        }

    def build_es_source_for_update(self, values):
        """Build source for SOCFACE partial update.

        Uses flat field structure like CSVNominaSocfaceReader (not json_data structure).
        Includes all fields, even empty ones (as [] or None).

        :param dict values: Processed CSV row with field mappings
        :return: Dict for "doc" field in ES with updated fields
        """
        es_doc = {
            "service": self.service.eid,
            "modification_date": datetime.now(pytz.utc),
        }

        # Person fields - include all fields, even empty ones
        if "names" in values:
            es_doc["names"] = [values["names"]] if values["names"] else []
        if "forenames" in values:
            es_doc["forenames"] = [values["forenames"]] if values["forenames"] else []
        if "gender" in values:
            es_doc["gender"] = values["gender"] if values["gender"] else None
        if "age" in values:
            es_doc["age"] = values["age"] if values["age"] else None
        if "birth_date" in values:
            es_doc["birth_date"] = values["birth_date"] if values["birth_date"] else None
        if "birth_place" in values:
            es_doc["birth_place"] = values["birth_place"] if values["birth_place"] else None
        if "household_role" in values:
            es_doc["household_role"] = (
                values["household_role"] if values["household_role"] else None
            )
        if "occupations" in values:
            es_doc["occupations"] = [values["occupations"]] if values["occupations"] else []
        if "occupations_index" in values:
            es_doc["occupations_index"] = (
                [values["occupations_index"]] if values["occupations_index"] else []
            )
        if "employer" in values:
            es_doc["employer"] = values["employer"] if values["employer"] else None
        if "nationality" in values:
            es_doc["nationality"] = values["nationality"] if values["nationality"] else None
        if "civil_status" in values:
            es_doc["civil_status"] = values["civil_status"] if values["civil_status"] else None
        if "additional_info" in values:
            es_doc["additional_info"] = (
                values["additional_info"] if values["additional_info"] else None
            )

        # Event fields
        if "event_date" in values:
            es_doc["event_date"] = values["event_date"] if values["event_date"] else None
            es_doc["event_year"] = values["event_date"] if values["event_date"] else None
        if "event_place" in values:
            es_doc["event_commune"] = values["event_place"] if values["event_place"] else None
            es_doc["event_country"] = DEFAULT_EVENT_COUNTRY if values["event_place"] else None
        if "event_department" in values:
            es_doc["event_department"] = (
                values["event_department"] if values["event_department"] else None
            )
            if "event_country" not in es_doc:
                es_doc["event_country"] = (
                    DEFAULT_EVENT_COUNTRY if values["event_department"] else None
                )
        if "event_commune" in values:
            es_doc["event_commune"] = values["event_commune"] if values["event_commune"] else None
            if "event_country" not in es_doc:
                es_doc["event_country"] = DEFAULT_EVENT_COUNTRY if values["event_commune"] else None

        # Complement fields
        if "cote" in values:
            es_doc["cote"] = values["cote"] if values["cote"] else None
        if "doc_page_line_id" in values:
            es_doc["doc_page_line_id"] = (
                values["doc_page_line_id"] if values["doc_page_line_id"] else None
            )
        if "household_id" in values:
            es_doc["household_id"] = values["household_id"] if values["household_id"] else None
        if "act_type" in values:
            es_doc["act_type"] = values["act_type"] if values["act_type"] else None
        if "source_url" in values:
            es_doc["source_url"] = values["source_url"] if values["source_url"] else None
        if "teklia_url" in values:
            es_doc["teklia_url"] = values["teklia_url"] if values["teklia_url"] else None

        # Authorities
        authorities, labels = [], []
        for eid, label in self.linked_authorities.get(values.get("stable_id", ""), []):
            authorities.append(eid)
            labels.append(label)

        if authorities:
            es_doc["agent"] = authorities

        return es_doc

    def build_es_source(self, attrs):
        """Build source for partial update.

        Only modification_date is automatically updated.
        creation_date is preserved (not included in doc).

        :param attrs: Document data
        :return: Dict for "doc" field in ES
        """
        authorities, labels = [], []
        for eid, label in self.linked_authorities.get(attrs["stable_id"], []):
            authorities.append(eid)
            labels.append(label)

        es_doc = {
            "service": self.service.eid,
            "stable_id": attrs["stable_id"],
            "modification_date": datetime.now(pytz.utc),
            "agent": authorities,
        }

        json_data = json.loads(attrs["json_data"])
        json_data["oai_id"] = attrs.get("oai_id")
        processed_list = NominaIndexJsonDataSerializable(self.cnx, json_data).process_json_data(
            self.service.code, attrs["stable_id"], alltext=" ".join(labels)
        )
        # Take first document for partial update (in case of split notices)
        if processed_list:
            es_doc.update(processed_list[0])
        return es_doc
