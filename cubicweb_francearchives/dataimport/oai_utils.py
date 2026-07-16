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

""":synopsis: OAI-PMH utils."""

# standard library imports
import datetime
from io import BytesIO
import hashlib
import logging
from lxml import etree

import os
import os.path
from sickle import Sickle
from sickle.iterator import OAIItemIterator
from sickle.models import Record
from sickle.response import OAIResponse, XMLParser
from sickle.utils import get_namespace

from uuid import uuid4
import zipfile

import urllib.parse

from logilab.common.decorators import cachedproperty

from cubicweb import Binary

from cubicweb_francearchives.dataimport import (
    normalize_for_filepath,
    cleanup_ns,
    parse_unitdate,
)

from cubicweb_francearchives.storage import S3BfssStorageMixIn


def build_header(header, sets, eadid=None):
    # check on the eadid is done before this method is called
    setSpec = header.setSpecs[0] if header.setSpecs else None  # should not happen
    setNames = [setName.text for setName in header.xml.findall(header._oai_namespace + "setName")]
    setName = setNames[0] if setNames else None
    if setName is None and setSpec:
        setName = sets.get(setSpec)
    eadid = eadid or setSpec
    return {"identifier": header.identifier, "name": setName, "eadid": eadid}


def build_metadata(data):
    keys = [
        "title",
        "creator",
        "subject",
        "description",
        "publisher",
        "contributor",
        "type",
        "format",
        "identifier",
        "source",
        "language",
        "relation",
        "coverage",
        "rights",
    ]
    metadata = dict.fromkeys(keys, [])
    metadata.update(data)
    date = ""
    if "date" in metadata:
        date = metadata.pop("date")
        if date and isinstance(date, (list, tuple)):
            date = date[0]
    infos = parse_unitdate({"text": date})
    metadata["date"] = date
    metadata["date1"] = str(infos["start"]) if infos["start"] else ""
    metadata["date2"] = str(infos["stop"]) if infos["stop"] else ""
    return metadata


def get_oai_dc_url_from_tree(tree):
    if hasattr(tree, "getroot"):
        root = tree.getroot()
    else:
        root = tree
    request = root.findall("{ns}request".format(ns=get_namespace(root)))
    if request is not None:
        url = request[0].text
        if url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            allowed = {"from", "until", "set", "metadataPrefix", "verb"}
            if allowed.intersection(qs):
                url = urllib.parse.urlunparse(parsed._replace(query=""))
            return f"{url}?{'&'.join(f'{k}={v}' for k, v in request[0].attrib.items())}"


def parse_oai_url(url):
    url = urllib.parse.urlparse(url)
    qs = urllib.parse.parse_qs(url.query)
    allowed = {"from", "until", "set", "metadataPrefix", "verb"}
    if set(qs) - allowed:
        raise ValueError(
            "Got invalid query parameter(s): {}".format(
                ", ".join(["'{}'".format(param) for param in set(qs) - allowed])
            )
        )
    base_url = urllib.parse.urlunparse(url._replace(query=""))
    params = {k: v[0] for k, v in list(qs.items()) if len(v) == 1}
    return base_url, params


def check_harvested_oai_url(cnx, service_code, oai_url):
    if not oai_url:
        return cnx._(
            "No URL found for OAI PMH repository in uploaded data. "
            "Your data may be corrupted: please harvest your data again."
        )
    oai_urls = cnx.execute(
        "Any U WHERE X is OAIRepository, X url U, X service S, S code %(e)s",
        {"e": service_code},
    )
    file_base_url, file_params = parse_oai_url(oai_url.strip())
    prefix = file_params["metadataPrefix"]
    for (_url,) in oai_urls:
        base_url, params = parse_oai_url(_url.strip())
        if base_url == file_base_url and params.get("metadataPrefix") == prefix:
            return
    else:
        return cnx._('"{}" service does not have any {} PMH repository with "{}" URL').format(
            service_code, prefix.upper(), oai_url
        )


class PniaOAIResponse(OAIResponse):
    @cachedproperty
    def http_fixed_content(self):
        return self.http_response.content.replace(
            b"https://www.openarchives.org/OAI", b"http://www.openarchives.org/OAI"
        )

    @property
    def xml(self):
        """The server's response as parsed XML, after the HTTPS replacement."""
        return etree.XML(self.http_fixed_content, parser=XMLParser)


class PniaSickle(Sickle):
    def harvest(self, **kwargs):
        """Make HTTP requests to the OAI server.

        :param kwargs: OAI HTTP parameters.
        :rtype: :class:`PniaOAIResponse`
        """
        oai_response = super(PniaSickle, self).harvest(**kwargs)
        return PniaOAIResponse(oai_response.http_response, oai_response.params)


class OAIXMLError(Exception):
    """XML errors from OAI response"""

    pass


class OAIHandler:
    """OAI-PMH record handler."""

    def __init__(self, cnx, service_infos, oaitask_eid, log):
        """Initialize OAI-PMH handler.

        :param Connection cnx: CubicWeb database connection
        :param dict service_code: service code
        :param str oaitask_eid: eid of the related OAIImportTask
        :param Logger log: logger
        """
        self.cnx = cnx
        self.log = log
        self.service_code = service_infos["code"]
        self.oai_url = service_infos["oai_url"]
        self.storage = S3BfssStorageMixIn(log=self.log)
        self.max_zip_size = 2 * (1024 * 1024 * 1024)  # 2BG
        self.saved_files = 0
        self.oaitask_eid = oaitask_eid
        self.init_zip_buffer()

    def compute_oai_id(self, record):
        return compute_oai_id(self.oai_url, record.header.identifier)

    def init_zip_buffer(self):
        """Init variables for a new zip file"""
        self.zip_buffer_size = 0
        self.zip_buffer = BytesIO()
        self.zip_writer = zipfile.ZipFile(
            self.zip_buffer, mode="a", compression=zipfile.ZIP_DEFLATED
        )

    def close_and_dump_zip_buffer(self):
        """Close the current buffer and save it into a CWFile"""
        date = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"{self.service_code}_{self.saved_files}_{date}.zip"
        try:
            self.zip_writer.close()
        except Exception as err:
            self.log.error("Current Zip buffer: %s", err)
        if self.zip_buffer_size or len(self.metadata):
            self.create_zip_file(filename)

    def create_zip_file(self, filename):
        """Create a CWFile with harvested record
        :param str filepath: stored filepath
        :param str oaitask_eid: eid of the related OAIImportTask
        add a multithreading
        """
        self.storage.storage_write_file(filename, self.zip_buffer.getvalue())
        ufilepath = self.storage.storage_ufilepath(filename)
        self.cnx.transaction_data["fs_importing"] = True
        cwfile = self.cnx.create_entity(
            "File",
            title=filename,
            data=Binary(ufilepath.encode("utf-8")),
            data_format="application/zip ",  # mimetypes.guess_type(filepath)[0]),
            data_name=filename,
            uuid=str(uuid4().hex),
            reverse_fatask_oaiharvest_file=self.oaitask_eid,
        )
        self.log.debug(f"Created File {filename} (eid: {cwfile.eid})")

    def get_file_contents(self, record):
        """Get file contents.

        :param _Element metadata: LXML record
        """
        return etree.tostring(record.ead, encoding="utf-8", xml_declaration=True)

    def get_file_name(self, eadid):
        return f"{normalize_for_filepath(eadid)}.xml"

    def write_all_in_zips(self):
        """Write all harvested data"""
        raise NotImplementedError

    def save_record(self, idx, record=None):
        """Add record to list of records.
        :param int idx: record index
        :param _Element record: record
        """
        raise NotImplementedError


class OAIHarvester:
    """OAIEAD schema haverster.

    :ivar Connection cnx: connection
    :ivar dict service_infos: service information
    """

    def __init__(self, cnx, service_infos, log=None):
        """Initialize OAI Nomina schema reader.

        :param Connection cnx: CubicWeb database connection
        :param dict service_infos: service information
        :param Logger log: logger
        """
        self.cnx = cnx
        self.service_infos = service_infos
        if log is None:
            log = logging.getLogger("rq.task")
        self.log = log
        self.oai_url = None

    def add_record(self, idx, record):
        return idx, record

    def harvest_records(self, oaitask_eid, headers, records_limit=None, dry_run=False, **params):
        """Harvest data and check them containing the needed information

        :param str oaitask_eid: eid of the related OAIImportTask
        :param dict headers: headers for harvest
        :param int records_limit: only import limit documents number
        :param boolean dry_run: import or not harvested documents
        :param dict params: harvest parameters
        """
        raise NotImplementedError

    def process_results(self, results, oaitask_eid, records_limit):
        """Write results in log

        :param dict records: results
        :param str oaitask_eid: eid of the related OAIImportTask
        :param int records_limit: only import limit documents number
        """
        complete_list_size = results["complete_list_size"]
        if complete_list_size is None:
            self.log.warning(
                """No information about records list size (completeListSize) could be found.""",
            )
            expected = records_limit or "?"
        else:
            expected = (
                records_limit
                if records_limit and records_limit < complete_list_size
                else complete_list_size
            )
        cw_files = self.cnx.execute(
            f"Any COUNT(F) WHERE X eid {oaitask_eid}, X fatask_oaiharvest_file F"
        )[0][0]
        self.log.info(
            f"<p>Processed {results['processed']} record(s).</p>"
            f"<p>Downloaded {results['downloaded']} out of {expected} record(s).</p>"
            f"<p>Skipped record(s):  {results['skipped']}.</p>"
            f"<p>Record(s) to delete: {results['records_to_delete']}.</p>"
            f"<p>Saved {results['saved_files']} record(s) in {cw_files} ZIP file(s)</p>"
        )


class OAIPMHWriter:
    """OAI-PMH writer."""

    def __init__(self, ead_services_dir, service_infos, subdirectories=[]):
        """Initialize OAI-PMH writer.

        :param str ead_services_dir: location of backup files
        :param dict service_infos: service information
        :param list subdirectories: list of subdirectories
        """
        self.storage = S3BfssStorageMixIn()
        self.ead_services_dir = ead_services_dir
        self.service_infos = service_infos
        self.directory = self.makedir(subdirectories)

    def makedir(self, subdirectories=[]):
        """Create directory(ies).

        :param list subdirectories: list of subdirectories

        :returns: directory
        :rtype: str
        """
        dirs = [self.ead_services_dir, self.service_infos["code"]]
        if subdirectories:
            dirs.extend(subdirectories)
        return self.storage.storage_makedir(dirs)

    def get_file_path(self, eadid):
        """Get file path.

        :param str eadid: EADID

        :returns: file path
        :rtype: str
        """
        eadid = normalize_for_filepath(eadid)
        filename = eadid + ".xml"
        # add lower test
        postfix = "{}_".format(self.service_infos["code"])
        if not filename.startswith(postfix):
            if filename.startswith(postfix.lower()):
                filename = "{}{}".format(postfix, filename.split(postfix.lower())[1])
            else:
                filename = "{}{}".format(postfix, filename)
        file_path = os.path.join(self.directory, filename)
        if self.storage.s3_bucket:
            return self.storage.s3.ensure_key(file_path)
        return file_path

    def get_file_contents(self, *args):
        """Get file contents."""
        raise NotImplementedError

    def dump(self, eadid, file_contents):
        """Dump file contents.
        :param str eadid: EADID
        :param str file_contents: file contents

        :returns: str file_path: filepath
        """
        filepath = self.get_file_path(eadid)
        return self.storage.storage_write_file(filepath, file_contents)

    def add_record(self, header, metadata):
        """Add record to list of records.

        :param _Element header: header
        :param _Element metadata: metadata
        """
        raise NotImplementedError


class PniaOAIItemIterator(OAIItemIterator):
    def __init__(self, sickle, params, ignore_deleted=False):
        super(PniaOAIItemIterator, self).__init__(sickle, params, ignore_deleted=ignore_deleted)
        self._next_harvested_url(init=True)

    def _next_harvested_url(self, init=False):
        params = self.params
        if not init and self.resumption_token and self.resumption_token.token:
            params = {"resumptionToken": self.resumption_token.token, "verb": self.verb}
        args = urllib.parse.urlencode(params)
        self._harvested_url = "{}?{}".format(self.sickle.endpoint, args)

    def _next_response(self):
        self._next_harvested_url()
        # initialize the previous resumption token in case self.oai_response.xml <request>
        # dont contain the resumptionToken which normally must not happen
        previous_resumption_token = self.resumption_token and self.resumption_token.token or None
        try:
            super(PniaOAIItemIterator, self)._next_response()
        except Exception as exception:
            if (
                hasattr(self, "oai_response")
                and self.oai_response
                and hasattr(self.oai_response, "xml")
            ):
                if self.oai_response.xml is None:
                    raise OAIXMLError(
                        """{} Stop harvesting.
                        <div>The response may not be a XML page</div>""".format(
                            self._harvested_url
                        )
                    )
            raise exception
        if self.resumption_token:
            request = self.oai_response.xml.find(".//" + self.sickle.oai_namespace + "request")
            if request:
                previous_resumption_token = request.attrib.get(
                    "resumptionToken", previous_resumption_token
                )
            if (
                previous_resumption_token
                and self.resumption_token.token == previous_resumption_token
            ):
                raise OAIXMLError(
                    """Stop harvesting. The next resumptionToken value <div>{}<div>
                    found in {} is the same as for the previous one""".format(
                        self.resumption_token.token, self._harvested_url
                    )
                )

    def stop_iteration_log(self):
        if (
            not (self.resumption_token and self.resumption_token.token)
            and hasattr(self, "oai_response")
            and self.oai_response
        ):
            xml = self.oai_response.xml
            if hasattr(self.oai_response, "xml") and self.oai_response.xml is not None:
                if xml.tag == "html":
                    body = xml.find(".//body")
                    if body is not None:
                        try:
                            body = etree.tostring(body[0], encoding="utf-8")
                            self.sickle.logger.error(body)
                        except Exception:
                            pass
                    raise OAIXMLError(
                        """Stop harvesting. No resumptionToken found in {}.
                        Got HTML instead of XML: the service may be unavailable.
                        """.format(
                            self._harvested_url
                        )
                    )
            elif hasattr(self.oai_response, "raw") and self.oai_response.raw:
                if "<resumptionToken" in self.oai_response.raw:
                    raise OAIXMLError(
                        """Stop harvesting. No resumptionToken found in "{}".
                        <div>The XML may not be valid</div>""".format(
                            self._harvested_url
                        )
                    )

    def next(self):
        """Return the next record/header/set.
        FranceArchives customizations:
          - add logs about harvested uri;
          - add `harvested_url` attribute on returned Record.
        """
        try:
            record = super(PniaOAIItemIterator, self).next()
            record.harvested_url = self._harvested_url
            record.cursor, record.complete_list_size = None, None
            if self.resumption_token:
                record.cursor = self.resumption_token.cursor
                record.complete_list_size = self.resumption_token.complete_list_size
            return record
        except StopIteration:
            self.stop_iteration_log()
            raise StopIteration
        except Exception:
            if self.resumption_token and self.resumption_token.token:
                self._next_response()
            else:
                self.stop_iteration_log()
                raise StopIteration


class OAIEADRecord(Record):
    def __init__(self, record_element, strip_ns=True):
        self.error = None
        try:
            super(OAIEADRecord, self).__init__(record_element, strip_ns=strip_ns)
        except Exception as e:
            self.error = e
            return
        self.ead = self.xml.find(".//" + self._oai_namespace + "metadata/")
        self.harvested_url = ""
        self.preprocess_ead()

    @cachedproperty
    def eadid(self):
        eadid = self.metadata.get("eadid")
        if eadid and eadid[0]:
            return eadid[0].strip()

    def preprocess_ead(self):
        """Preprocesses the EAD xml file to remove ns and internal content
           (adapted from dataimport.eadreader.preprocess_ead)

        :param XMLElement record: the lxml etree object (metadata)

        :returns the lxml etree object (ead), cleaned from internal content or
        None if the lxml etree is empty

        """
        if self.ead is not None:
            cleanup_ns(self.ead)
            for elt in self.ead.findall('.//*[@audience="internal"]'):
                elt.getparent().remove(elt)


class OAIDCRecord(Record):
    def __init__(self, record_element, strip_ns=True):
        self.error = None
        try:
            super(OAIDCRecord, self).__init__(record_element, strip_ns=strip_ns)
        except Exception as e:
            self.error = e
            return
        self.harvested_url = ""

    @cachedproperty
    def eadid(self):
        eadids = self.header.setSpecs
        return eadids[0].strip() if eadids else None

    def build_dc_header(self, sets):
        return build_header(self.header, sets, self.eadid)

    def build_dc_metadata(self):
        return build_metadata(self.metadata)


def compute_oai_id(base_url, identifier):
    """Compute an unique identifier based on record identifier and OAI repository url"""
    if isinstance(base_url, str):
        base_url = base_url.encode("utf-8")
    return "{}_{}".format(hashlib.sha1(base_url).hexdigest(), identifier)
