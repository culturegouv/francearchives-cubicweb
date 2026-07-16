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
from collections import defaultdict
from datetime import datetime
from itertools import count
import json
import logging
import os.path
import time

from psycopg2 import OperationalError
from sickle.models import Record

from cubicweb.dataimport.importer import ExtEntity


from cubicweb_francearchives.dataimport import usha1


from cubicweb_francearchives.dataimport.oai_utils import OAIPMHWriter, PniaSickle
from cubicweb_francearchives.dataimport.oai_utils import PniaOAIItemIterator


def qname(tag):
    return "{http://www.france-genealogie.fr/ns/nomina/1.0}" + tag


def first(value):
    return next(iter(value))


def compute_nomina_stable_id(service_code, notice_id):
    if notice_id.startswith(f"{service_code}_"):
        stable_id = notice_id
    else:
        stable_id = f"{service_code}_{notice_id}"
    return usha1(stable_id)


class OAIENominaRecord(Record):
    def __init__(self, record_element, strip_ns=True):
        self.error = None
        try:
            super(OAIENominaRecord, self).__init__(record_element, strip_ns=strip_ns)
        except Exception as e:
            self.error = e
            return
        self.nomina = self.xml.find(".//" + self._oai_namespace + "metadata/")
        self.harvested_url = ""


class OAINominaWriter(OAIPMHWriter):
    """OAI-PMH writer (Nomina)."""

    headers = [("stable_id", "oai_id", "json_data", "service", "delete", "harvested_url")]

    def __init__(self, nomina_services_dir, service_infos, log=None):
        """Initialize OAI-PMH writer (Dublin Core).

        :param str nomina_services_dir: location of backup files
        :param dict service_infos: service information
        :param Logger log: logger
        """
        super(OAINominaWriter, self).__init__(
            nomina_services_dir, service_infos, subdirectories=["oaipmh"]
        )
        if log is None:
            log = logging.getLogger("rq.task")
        self.log = log
        self.rows = []
        self.file_counter = 0
        self.filepaths = []
        self.service_code = self.service_infos["code"]

    def init_csv(self):
        #  add headers
        self.rows = self.headers[:]
        self.file_counter += 1

    @property
    def get_filepath(self):
        """Get file path.
        :returns: file path
        :rtype: str
        """
        date = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{self.service_code}_nomina_{date}_{self.file_counter}.csv"
        filepath = os.path.join(self.directory, filename)
        if self.storage.s3_bucket:
            return self.storage.s3.ensure_key(filepath)
        return filepath

    def dump_csv(self):
        """Dump file contents.
        :param str file_contents: file contents

        :returns: str file_path: filepath
        """
        filepath = self.get_filepath
        self.log.info(f"Writing {len(self.rows) - 1} rows in {filepath}")
        if len(self.rows) > 1 or self.rows != self.headers:
            fpath = self.storage.storage_write_csv_file(filepath, self.rows)
            self.filepaths.append(fpath)

    def add_record(self, record, nomina=None):
        stable_id = nomina.values["stable_id"] if nomina else ""
        if stable_id:
            stable_id = stable_id.pop()
        self.rows.append(
            (
                stable_id,
                record.header.identifier,
                nomina.values["json_data"].pop() if nomina else "",
                self.service_code,
                "y" if record.deleted else "n",
                record.harvested_url,
            )
        )


class OAINominaHarvester:
    """OAI Nomina schema haverster.

    :ivar dict config: server-side configuration
    :ivar OAINominaReader reader: OAI Nomina schema reader
    """

    def __init__(self, cnx, log=None):
        """Initialize OAI Nomina schema reader.

        :param Connection cnx: CubicWeb database connection
        :param Logger log: logger
        """
        self.cnx = cnx
        if log is None:
            log = logging.getLogger("rq.task")
        self.log = log
        self.reader = OAINominaReader()
        self.filepaths = []

    def harvest_records(
        self,
        service_infos,
        headers,
        records_limit=None,
        csv_rows_limit=100000,
        **params,
    ):
        """Harvest data and check they contain the needed information
        :param Connection cnx: connection
        :param dict service_infos: service information
        :param String headers: http headers
        :param int records_limit: only import limit documents number
        :param int csv_rows_limit: rows limit in the resulting csv file
        :param Logger log: logger

        :param dict params: harvest parameters
        """
        csv_rows_limit = int(csv_rows_limit)
        base_url = service_infos["oai_url"]
        oai_mapping = {
            "ListRecords": OAIENominaRecord,
            "GetRecord": OAIENominaRecord,
        }
        self.client = PniaSickle(
            base_url,
            iterator=PniaOAIItemIterator,
            class_mapping=oai_mapping,
            headers=headers,
            max_retries=3,
            retry_status_codes=(500, 502, 503),
        )
        self.client.logger = self.log
        self.log.setLevel(logging.INFO)

        max_retries = 2
        retry_delay = 1.0
        attempt = 0
        idx, complete_list_size = None, None
        nomina_dir = self.cnx.vreg.config["nomina-services-dir"]
        nomina_writer = OAINominaWriter(nomina_dir, service_infos, self.log)
        nomina_writer.init_csv()

        while attempt <= max_retries:
            try:
                records = self.client.ListRecords(**params)
                for idx, record in enumerate(records):
                    if complete_list_size is None:
                        try:
                            complete_list_size = record.complete_list_size
                            self.log.info(
                                "Repository contains %s documents (completeListSize).",
                                record.complete_list_size,
                            )
                        except Exception:
                            pass
                    if record is None:
                        # PniaOAIItemIterator raise an error before creating a record
                        continue
                    identifier = record.header.identifier
                    url = record.harvested_url
                    if idx and idx % 1000 == 0:
                        self.log.info("Processed %s documents", idx + 1)
                    if not hasattr(record, "metadata") and not record.deleted:
                        self.log.warning(
                            "%s. The record with identifier %r has no metadata.",
                            url,
                            identifier,
                        )
                        continue
                    if idx and idx % csv_rows_limit == 0.0:
                        nomina_writer.dump_csv()
                        nomina_writer.init_csv()
                    if record.deleted:
                        self.log.info(
                            "%s. The record with identifier %r is set to be deleted.",
                            url,
                            identifier,
                        )
                        nomina_writer.add_record(record, nomina=None)
                        continue
                    for nomina in self.reader(
                        record.nomina, record.header, service_infos, self.log
                    ):
                        if nomina:
                            nomina_writer.add_record(record, nomina)
                    if records_limit and idx == (records_limit - 1):
                        break
                break
            except OperationalError as e:
                attempt += 1
                error_msg = str(e)
                if (
                    "server closed the connection" in error_msg
                    or "connection already closed" in error_msg
                ):
                    self.log.warning(
                        f"PostgreSQL connection error (attempt {attempt}/{max_retries + 1}): {e}. "
                        f"Reconnecting and retrying..."
                    )
                    if attempt <= max_retries:
                        try:
                            self.cnx.commit_and_restart()
                            self.log.info("Connection restarted successfully")
                        except Exception as restart_error:
                            self.log.error(f"Failed to restart connection: {restart_error}")
                            raise
                        time.sleep(retry_delay * attempt)
                        continue
                    else:
                        self.log.error(
                            f"PostgreSQL connection error after {max_retries + 1} attempts."
                        )
                        raise
                else:
                    raise
            except Exception as err:
                self.log.error("Harvest aborted: %s", err)
                raise

        if complete_list_size is None:
            self.log.info(
                """No information about records list size (completeListSize) could be found."""
            )
        if records_limit:
            self.log.info("Expected %s documents.", records_limit)
        self.log.info("Processed %s records.", idx + 1 if idx is not None else 0)
        nomina_writer.dump_csv()
        return nomina_writer.filepaths or []


class OAINominaReader(object):
    def __init__(self):
        self.next_id = lambda c=count(1): next(c)

    def __call__(self, record, header, service_infos, log):
        """Generate extentities read from `record` etree"""
        doctype_node = record.find(qname("type"))
        if doctype_node is None:
            log.warning("No document type found for record %s", header.identifier)
            return
        persons = build_persons(record)
        if len(persons) == 0:
            log.warning(
                "No person name or person firstname found for record  %s", header.identifier
            )
            return
        service_eid = service_infos["eid"]
        stable_id = compute_nomina_stable_id(service_infos["code"], header.identifier)
        info = {}
        info["t"] = doctype_node.get("code", "#UN")
        uri = record.get("uri")
        if uri:
            info["u"] = uri
        for code, data in (
            ("e", build_events(record)),
            ("p", persons),
            ("c", build_complement(record)),
        ):
            if data:
                info[code] = data
        json_data = json.dumps(info, sort_keys=True)
        nomina_data = {
            "stable_id": {stable_id},
            "oai_id": {header.identifier},
            "json_data": {json_data},
            "service": {f"service-{service_eid}"},
        }
        nomina_id = self.next_id()
        nomina = ExtEntity("NominaRecord", nomina_id, nomina_data)
        yield nomina


def str2bool(value):
    if value in ("oui", "o", "1"):
        return "y"
    else:
        return "n"


def get_text(node):
    if node is not None and node.text and node.text.strip():
        return str(node.text.strip())


def build_events(record):
    events = {}
    locations = build_locations(record)
    dates = build_dates(record)
    for key, value in dates.items():
        desc = {"d": value}
        loc = locations.pop(key, None)
        if loc:
            desc["l"] = loc
        events[key] = desc
    for key, value in locations.items():
        assert key not in events
        events[key] = {"l": value}
    return events


def build_dates(record):
    dates = defaultdict(list)
    for date in record.findall(qname("date")):
        fields = {}
        code = date.get("code", "###")  # code is a mandatory attribute
        full_date = date.text.strip() if date.text else ""
        year = date.attrib.get("annee", "")
        if not (year or full_date):
            continue
        if year == full_date:
            fields["y"] = year
        else:
            if year:
                fields["y"] = year
            if full_date:
                fields["d"] = full_date
        if fields:
            dates[code].append(fields)
    return dates


def build_persons(record):
    persons_data = []
    for person in record.findall(qname("personne")):
        nomelt = person.find(qname("nom"))
        data = {}
        if nomelt is not None:
            data["n"] = get_text(nomelt)
        forenames = []
        for forenames_node in person.findall(qname("prenoms")):
            if forenames_node is not None:
                text = get_text(forenames_node)
                if text:
                    forenames.append(text)
        if forenames:
            data["f"] = " ".join(forenames)
        if data:
            persons_data.append(data)
    return persons_data


def build_locations(record):
    locations = defaultdict(list)
    for location in record.findall(qname("localisation")):
        code = location.get("code", "###")
        fields = {}
        pays = location.find(qname("pays"))
        if pays is not None and pays.text and pays.text.strip():
            fields["c"] = pays.text.strip()
            pays_code = pays.get("code")
            if pays_code:
                fields["cc"] = pays_code
        department = location.find(qname("departement"))
        text = get_text(department)
        if text:
            fields["d"] = text
            department_code = department.get("code")
            if department_code:
                fields["dc"] = department_code
        precisions = []
        for precision_node in location.findall(qname("precision")):
            text = get_text(precision_node)
            if text:
                precisions.append(text)
        if precisions:
            fields["p"] = ", ".join(precisions)
        if fields:
            locations[code].append(fields)
    return locations


def build_complement(record):
    info = defaultdict(list)
    complement = record.find(qname("complement"))
    if complement is not None:
        for key, tag in (
            ("f", "conflit"),
            ("c", "code"),
            ("e", "niveau"),
            ("n", "nro"),
            ("m", "mention"),
        ):
            node = complement.find(qname(tag))
            if node is not None and node.text and node.text.strip:
                info[key] = node.text.strip()
        professions = []
        for profession in complement.findall(qname("profession")):
            if profession.text:
                professions.append(profession.text.strip())
        if professions:
            info["o"] = professions
    return info
