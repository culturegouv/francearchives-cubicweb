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

# standard library imports
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv

from io import StringIO

from cubicweb_francearchives.dataimport.oai_utils import (
    OAIHandler,
    OAIHarvester,
    OAIEADRecord,
    PniaSickle,
    PniaOAIItemIterator,
    check_harvested_oai_url,
)

from cubicweb_francearchives.dataimport import InvalidFindingAid
from cubicweb_francearchives.dataimport.ead import Reader, strip_nones


class OAIEADHandler(OAIHandler):

    def __init__(self, cnx, service_infos, oaitask_eid, log):
        """Initialize OAI-PMH handler.

        :param Connection cnx: CubicWeb database connection
        :param dict service_code: service code
        :param str oaitask_eid: eid of the related OAIImportTask
        :param Logger log: logger
        """
        super().__init__(cnx, service_infos, oaitask_eid, log)
        self.metadata = defaultdict(list)  # keep trace of record oai identifiers

    def write_metadata(self):
        """Add metadata CSV files to the current zip buffer"""
        for key, value in self.metadata.items():
            filename = f"{key}.csv"
            content = StringIO()
            writer = csv.writer(content, delimiter="\t")
            writer.writerows(value)
            self.zip_writer.writestr(filename, content.getvalue())

    def close_and_dump_zip_buffer(self):
        """Write metadata, close the current buffer and save it into a CWFile"""
        self.write_metadata()
        super().close_and_dump_zip_buffer()

    def save_record(self, idx, record=None):
        """Add record to list of records.
        :param int idx: record index
        :param _Element record: record
        """
        if idx is None:
            # write the current buffer and stop
            self.close_and_dump_zip_buffer()
        oai_id = self.compute_oai_id(record)
        if record.deleted:
            self.metadata["deleted"].append((oai_id,))
            return
        content = self.get_file_contents(record)
        record_size = len(content)
        if record_size + self.zip_buffer_size > self.max_zip_size:
            # write the current buffer
            self.close_and_dump_zip_buffer()
            # init a new buffer
            self.init_zip_buffer()
        # Write the file to the in-memory zip
        filename = self.get_file_name(record.eadid)
        self.zip_writer.writestr(filename, content)
        # add oai_id to the list
        self.metadata["identifiers"].append((record.eadid, oai_id))
        self.zip_buffer_size += record_size
        self.saved_files += 1

    def save_oai_url(self, oai_url):
        self.metadata["identifiers"].append(("oai_url", oai_url))


class OAIEADHarvester(OAIHarvester):
    """OAIEAD schema haverster.

    :ivar Connection cnx: connection
    :ivar dict service_infos: service information
    """

    def skip_record_errors(self, record, urlinfo):
        """Check record validity
        :param _Element record: LXML document
        :param str urlinfo: OAI URL for the record
        """
        service_code = self.service_infos["code"]
        if record.ead is None:
            error = record.metadata if hasattr(record, "metadata") else "no metadata found"
            self.log.warning("%s Skip the record: %s", urlinfo, error)
            return True
        identifier = record.header.identifier
        if identifier is None:
            msg = "%s Skip the record: no identifier found"
            self.log.warning(msg, urlinfo)
            return True
        eadid = record.eadid
        if not eadid:
            msg = "%s Skip the record: no EADID value found for record %r"
            self.log.warning(msg, urlinfo, identifier)
            return True
        if not eadid.startswith(service_code):
            msg = (
                '%s EADID value "%r" found for record %r is not valid: '
                "value does not start with service code. Import it anyway."
            )
            self.log.warning(msg, urlinfo, eadid, identifier)
        if record.ead.find("archdesc") is None:
            msg = "%s Skip the record: no archdesc value found for record %r (eadid %r)"
            self.log.error(msg, urlinfo, identifier, eadid)
            return True
        if record.ead.find("archdesc/did") is None:
            msg = "%s Skip the record: no archdesc.did value found for record %r (eadid %r)"
            self.log.error(msg, urlinfo, identifier, eadid)
            return True
        return False

    def process_harvested(self, oaitask_eid, downloaded_records, handlercls):
        records_to_delete = 0
        oai_handler = handlercls(self.cnx, self.service_infos, oaitask_eid, self.log)
        processed = []
        for execution in as_completed(downloaded_records):
            if execution.result():
                _idx, record = execution.result()
                if record.deleted:
                    records_to_delete += 1
                else:
                    eadid = record.eadid
                    if eadid in processed:
                        msg = (
                            "record %r, eadid %r ignored: "
                            "a record with the same eadid "
                            "has already been saved"
                        )
                        self.log.error(msg, record.header.identifier, eadid)
                        continue
                    processed.append(eadid)
                oai_handler.save_record(_idx, record)
        # then send the signal to stop and write the last files
        oai_handler.save_oai_url(self.oai_url)
        oai_handler.close_and_dump_zip_buffer()
        return oai_handler.saved_files, records_to_delete

    def download_records(self, records, oaitask_eid, records_limit):
        """Download records and check them containing the needed information

        :param list records: OAIEADRecords
        :param str oaitask_eid: eid of the related OAIImportTask
        :param int records_limit: only import limit documents number
        """

        downloaded, idx, skipped = 0, 0, 0
        complete_list_size = None
        with ThreadPoolExecutor(thread_name_prefix="oai") as executor:
            downloaded_records = []
            try:
                for idx, record in enumerate(records, start=1):
                    if record is None:
                        # PniaOAIItemIterator raised an error before creating a record
                        continue
                    downloaded += 1
                    try:
                        cursor = int(record.cursor) + 1
                    except Exception:
                        cursor = downloaded
                    if complete_list_size is None:
                        try:
                            complete_list_size = int(record.complete_list_size)
                        except TypeError:
                            pass
                        if complete_list_size:
                            msg = (
                                "Repository contains %s documents (completeListSize) "
                                "responding to request parameters." % complete_list_size
                            )
                            if records_limit:
                                msg = "%s Only %s records will be harvested" % (msg, records_limit)
                            self.log.info(msg)
                    lsz = records_limit or complete_list_size or "?"
                    urlinfo = "<div>{url}<div><div>(record {cur} out of {lsz}).</div>".format(
                        url=record.harvested_url, cur=cursor, lsz=lsz
                    )
                    if record.error:
                        if not hasattr(record, "metadata"):
                            self.log.error("%s Skip the record: no metadata found", urlinfo)
                        else:
                            self.log.error("%s Skip the record: %r", urlinfo, record.error)
                        skipped += 1
                        continue
                    if record.deleted:
                        self.log.warning(
                            "%s The record with identifier: %r is to be deleted",
                            urlinfo,
                            record.header.identifier,
                        )
                    else:
                        if self.skip_record_errors(record, urlinfo):
                            skipped += 1
                            continue
                        self.log.info(
                            "Process %s OAI identifier: %s, eadid: %s",
                            urlinfo,
                            record.header.identifier,
                            record.eadid,
                        )
                    downloaded_records.append(executor.submit(self.add_record, idx, record))
                    if idx == records_limit:
                        break
            except Exception as error:
                self.log.error("Harvesting aborted: %s", error)
            if idx:
                saved_files, records_to_delete = self.process_harvested(
                    oaitask_eid, downloaded_records, OAIEADHandler
                )
            else:
                saved_files, records_to_delete = 0, 0
        return {
            "complete_list_size": complete_list_size,
            "saved_files": saved_files,
            "records_to_delete": records_to_delete,
            "downloaded": downloaded,
            "processed": idx,
            "skipped": skipped,
        }

    def harvest_records(self, oaitask_eid, headers, records_limit=None, dry_run=False, **params):
        """Harvest data and check them containing the needed information

        :param str oaitask_eid: eid of the related OAIImportTask
        :param dict headers: headers for harvest
        :param int records_limit: only import limit documents number
        :param boolean dry_run: import or not harvested documents
        :param dict params: harvest parameters
        """
        oai_ead_mapping = {
            "ListRecords": OAIEADRecord,
            "GetRecord": OAIEADRecord,
        }
        client = PniaSickle(
            self.service_infos["oai_url"],
            iterator=PniaOAIItemIterator,
            class_mapping=oai_ead_mapping,
            headers=headers,
            max_retries=3,
            retry_status_codes=(500, 502, 503),
        )
        client.logger = self.log
        # harvest records
        params_ = "&".join(f"{k}={v}" for k, v in params.items())
        self.oai_url = f"{self.service_infos['oai_url']}?{params_}"
        self.log.info(f"Process {self.oai_url}")
        records = client.ListRecords(**params)
        results = self.download_records(records, oaitask_eid, records_limit)
        self.process_results(results, oaitask_eid, records_limit)


class OAIEADHarvestedReader(Reader):
    """OAI-PMH harvested record reader

    :ivar dict config: server-side configuration
    :ivar store: a CubicWeb `Store`
    :ivar dict identifiers: OAI identifier/EADID map for imported records
    """

    def __init__(self, config, store, identifiers):
        """Initialize OAI EAD record reader for OAI EAD harvested XML files.

        :param dict config: server-side configuration
        :param store: a CubicWeb `Store`
        :param dict identifiers: OAI identifier/EADID map for imported records

        """
        super().__init__(config, store)
        self.oai_identifiers = identifiers

    def check_document_validity(self, service_infos):
        """Check the EAD XML structure and constraintes"""
        error = check_harvested_oai_url(
            self.store._cnx, service_infos["code"], self.service_oai_url
        )
        if error:
            raise Exception(error)
        super().check_document_validity()

    def process_eadid(self, eadid, fa_support):
        eadid = super().process_eadid(eadid, fa_support)
        if eadid.strip() not in self.oai_identifiers:
            raise InvalidFindingAid(
                "No OAI identifier has been found for eadid '%s'."
                " Do not import the record" % eadid
            )
        return eadid

    def create_findingaid(self, attrs):
        """Add "oai_id" value to FindingAid"""
        attrs["oai_id"] = self.oai_identifiers.get(attrs["eadid"].strip())
        return self.create_entity("FindingAid", strip_nones(attrs))
