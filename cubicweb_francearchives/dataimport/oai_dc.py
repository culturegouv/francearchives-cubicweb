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
from concurrent.futures import ThreadPoolExecutor, as_completed

from isodate import datetime_isoformat

from lxml import etree
from lxml.builder import E, ElementMaker

from sickle.utils import get_namespace

from cubicweb.utils import json_dumps

from cubicweb_oaipmh import utcnow

from cubicweb_francearchives import IIIF_MANIFEST_ROLE

from cubicweb_francearchives.dataimport import (
    usha1,
    clean_values,
    strip_html,
    get_year,
    component_stable_id_for_dc,
)

from cubicweb_francearchives.dataimport.oai_utils import (
    PniaSickle,
    PniaOAIItemIterator,
    OAIDCRecord,
    OAIHandler,
    OAIHarvester,
    compute_oai_id,
    check_harvested_oai_url,
    get_oai_dc_url_from_tree,
)
from cubicweb_francearchives.dataimport.ead import Reader, service_infos_for_es_doc
from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.xmlutils import XMLParser


EXTIDS = {"ConceptScheme": "siaf", "IndexRole": "virtual-exhibit"}


def get_sets_dict(setIterator):
    return {s.setSpec: s.setName for s in setIterator}


class OAIDCHandler(OAIHandler):

    def __init__(self, cnx, service_infos, oaitask_eid, log):
        """Initialize OAI-DC handler.

        :param Connection cnx: CubicWeb database connection
        :param dict service_code: service code
        :param str oaitask_eid: eid of the related OAIImportTask
        :param Logger log: logger
        """
        super().__init__(cnx, service_infos, oaitask_eid, log)
        self.oai_records = defaultdict(list, {})

    def to_xml(self, eadid):
        """Convert records to XML file format compliant tree.

        :param str eadid: EAD ID

        :returns: element factory
        :rtype: ElementMaker
        """
        date = E.responseDate(datetime_isoformat(utcnow()))
        nsmap = {
            None: "http://www.openarchives.org/OAI/2.0/",
            "xsi": "http://www.w3.org/2001/XMLSchema-instance",
        }
        request = E.request(self.oai_url, verb="ListRecords", metadataPrefix="oai_dc")
        maker = ElementMaker(nsmap=nsmap)
        attributes = {
            "{%s}schemaLocation"
            % nsmap["xsi"]: " ".join(
                [
                    "http://www.openarchives.org/OAI/2.0/",
                    "http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd",
                ]
            )
        }
        oai_records = [record.xml for record in self.oai_records[eadid]]
        body_elements = [E("ListRecords", *oai_records)]
        return maker("OAI-PMH", date, request, *body_elements, **attributes)

    def get_file_contents(self, eadid):
        """Get file contents.

        :param str eadid: EAD ID
        """
        return etree.tostring(self.to_xml(eadid), encoding="utf-8", xml_declaration=True)

    def write_all_in_zips(self):
        """Write all harvested data"""
        for idx, (eadid, records) in enumerate(self.oai_records.items(), start=1):
            content = self.get_file_contents(eadid)
            record_size = len(content)
            if record_size + self.zip_buffer_size > self.max_zip_size:
                # write the current buffer
                self.close_and_dump_zip_buffer()
                # init a new buffer
                self.init_zip_buffer()
            # Write the file to the in-memory zip
            filename = self.get_file_name(eadid)
            self.zip_writer.writestr(filename, content)
            self.zip_buffer_size += record_size
            self.saved_files += 1
        # write the current buffer
        self.close_and_dump_zip_buffer()


class OAIDCHarvester(OAIHarvester):
    """OAIDC schema haverster.

    :ivar Connection cnx: connection
    :ivar dict service_infos: service information
    """

    def process_harvested(self, oaitask_eid, downloaded_records, handlercls):
        records_to_delete = 0
        oai_handler = handlercls(self.cnx, self.service_infos, oaitask_eid, self.log)
        for execution in as_completed(downloaded_records):
            if execution.result():
                idx_, record = execution.result()
                if record.deleted:
                    records_to_delete += 1
                eadid = record.eadid
                oai_handler.oai_records[eadid].append(record)
        oai_handler.write_all_in_zips()
        return oai_handler.saved_files, records_to_delete

    def download_records(self, records, oaitask_eid, records_limit):
        """Download records and check them containing the needed information

        :param list records: OAIEADRecords
        :param str oaitask_eid: eid of the related OAIImportTask
        :param int records_limit: only import limit documents number
        """

        downloaded, idx, skipped = 0, 0, 0
        complete_list_size = None
        service_code = self.service_infos["code"]
        with ThreadPoolExecutor(thread_name_prefix="oai") as executor:
            downloaded_records = []
            try:
                for idx, record in enumerate(records, start=1):
                    if record is None:
                        # PniaOAIItemIterator raised an error before creating a record
                        continue
                    downloaded += 1
                    identifier = record.header.identifier
                    try:
                        cursor = int(record.cursor) + 1
                    except Exception:
                        cursor = downloaded
                    if complete_list_size is None:
                        try:
                            complete_list_size = int(record.complete_list_size)
                        except TypeError:
                            pass
                    lsz = records_limit or complete_list_size or "?"
                    urlinfo = "<div>{url}<div><div>(record {cur} out of {lsz}).</div>".format(
                        url=record.harvested_url, cur=cursor, lsz=lsz
                    )
                    # eadid is caclulated from header.setSpec()
                    if record.deleted:
                        self.log.warning(
                            "%s The record with identifier %r is to be deleted", urlinfo, identifier
                        )
                    else:
                        eadid = record.eadid
                        if eadid is None:
                            msg = (
                                "%s Skip the record: ignoring identifier %r because of "
                                "unspecified setSpec "
                                "which is used as eadid value"
                            )
                            self.log.error(msg, urlinfo, identifier)
                            skipped += 1
                            continue
                        if not record.metadata.get("title"):
                            msg = (
                                "%s Skip the record: ignoring identifier %r because of "
                                " unspecified dc_title "
                                "which is used as unittitle"
                            )
                            self.log.error(msg, urlinfo, identifier)
                            skipped += 1
                            continue
                        if not eadid.startswith(service_code):
                            msg = (
                                '%s: EADID value "%r" found for record %r is not valid:'
                                "value does not start with service_code. Import it anyway."
                            )
                            self.log.warning(msg, urlinfo, eadid, identifier)
                        else:
                            self.log.info(
                                "Process %s OAI identifier: %s, eadid: %s",
                                urlinfo,
                                identifier,
                                eadid,
                            )
                    downloaded_records.append(executor.submit(self.add_record, idx, record))
                    if idx == records_limit:
                        break
            except Exception as error:
                self.log.error("Harvesting aborted: %s", error)
            if idx:
                saved_files, records_to_delete = self.process_harvested(
                    oaitask_eid, downloaded_records, OAIDCHandler
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
        """Harvest data and check that they contain the needed information
        :param function records: read-in records (generator)
        """
        oai_mapping = {
            "ListRecords": OAIDCRecord,
            "GetRecord": OAIDCRecord,
        }
        client = PniaSickle(
            self.service_infos["oai_url"],
            iterator=PniaOAIItemIterator,
            class_mapping=oai_mapping,
            headers=headers,
            max_retries=3,
            retry_status_codes=(500, 502, 503),
        )
        client.logger = self.log
        # harvest records
        params_ = "&".join(f"{k}={v}" for k, v in params.items())
        self.log.info(f'Process {self.service_infos["oai_url"]} with {params_}')
        results = self.download_records(client.ListRecords(**params), oaitask_eid, records_limit)
        self.process_results(results, oaitask_eid, records_limit)


def get_oai_dc_xml_records(tree):
    if hasattr(tree, "getroot"):
        root = tree.getroot()
    else:
        root = tree
    return root.findall("{ns}ListRecords/{ns}record".format(ns=get_namespace(root)))


class OAIDCHarvestedReader(Reader):
    """OAI-DC record reader

    :ivar dict config: server-side configuration
    :ivar store: a CubicWeb `Store`
    :ivar dict identifiers: OAI identifier/EADID map for imported records
    """

    def __init__(self, config, store, identifiers=None):
        """Initialize OAI EAD record reader for OAI EAD harvested XML files.

        :param dict config: server-side configuration
        :param store: a CubicWeb `Store`
        :param dict identifiers: OAI identifier/EADID map for imported records

        """
        super().__init__(config, store)
        self._created_fa = {}

    def richstring_html(self, data, attr):
        if data:
            if not isinstance(data, (list, tuple)):
                data = [data]
            return self.richstring_template.format(data=" ".join(data), attr=attr)
        return None

    def process_oaidc_xml(self, filepath):
        data = self.storage.storage_get_oaifile_content(filepath)
        try:
            return etree.parse(data, parser=XMLParser)
        except Exception:
            self.log.exception('Could not process file "%r"', filepath)
            return

    def oai_sets(self, tree):
        """Retrieve ListSets"""
        if hasattr(tree, "getroot"):
            root = tree.getroot()
        else:
            root = tree
        sets = {}
        request = root.findall("{ns}request".format(ns=get_namespace(root)))
        if request is not None:
            oai_url = request[0].text
            if oai_url:
                # This code retrieves ListSets to get the setName in case the OAI-PMH
                # in case this information is not provied in ListRecords (BnF recommendation)
                try:
                    return get_sets_dict(PniaSickle(oai_url).ListSets())
                except Exception as ex:
                    self.log.exception("No sets could be found: %s", ex)
        return sets

    def import_filepath(self, filepath, service_infos=None, **kwargs):
        """Generate extentities read from `record` etree"""
        service_infos = self.ensure_service(filepath, service_infos=service_infos)
        if not service_infos["code"]:
            self.log.error("Import aborted: no service code found: %s", service_infos)
            return []
        if not service_infos["eid"]:
            self.log.error("Import aborted: no service eid found: %s", service_infos)
            return []
        tree = self.process_oaidc_xml(filepath)
        service_oai_url = get_oai_dc_url_from_tree(tree)
        _error = check_harvested_oai_url(self.store._cnx, service_infos["code"], service_oai_url)
        if _error:
            self.exception(_error)
            return []
        service_infos["oai_url"] = service_oai_url
        self.log.info("Importing files harvested from %r", service_oai_url)
        # assert the oai_url is an service repository
        sets = self.oai_sets(tree)
        es_documents = []
        records = get_oai_dc_xml_records(tree)
        for idx, record in enumerate(records):
            record = OAIDCRecord(record)
            try:
                esdoc = self.import_record(record, idx, filepath, service_infos, sets)
            except Exception:
                import traceback

                traceback.print_exc()
                eadid = record.eadid
                self.log.exception("Failed to import %r", eadid)
                continue
            es_documents.extend(esdoc)
        return es_documents

    def import_record(self, record, idx, filepath, service_infos, sets):
        eadid = record.eadid
        header = record.build_dc_header(sets)
        if record.deleted:
            self.delete_record(header, service_infos)
            return {}
        self.log.info("Importing %r, eadid %r", record.header.identifier, eadid)
        # check that FindingAid did.unittitle could be retrieved from the
        # record's setName or setSpec or raise an error
        if not header["name"]:
            self.log.exception(
                (
                    "Failed to import (eadid %r): check that the setName or "
                    "SetSpec is provided in the record. If no setName provided, "
                    "check that the ListSets does include the specified setSpec"
                ),
                eadid,
            )
            return {}
        es_docs = []
        metadata = record.build_dc_metadata()
        fa_key = usha1(eadid)
        fa_es_doc, creation_date = self._created_fa.get(fa_key, (None, None))
        if fa_es_doc is None:
            creation_date = self.creation_date_from_filepath(filepath)
            # directory exists, will not be overwritten
            findingaid_support = self.create_file(filepath)
            self.delete_from_filename(filepath)
            ir_name, stable_id = self.process_existing_findingaids(eadid, findingaid_support)
            header.update({"stable_id": stable_id, "irname": ir_name})
            metadata["creation_date"] = creation_date
            fa_es_doc = self.import_findingaid(header, metadata, service_infos, findingaid_support)
            self._created_fa[fa_key] = (fa_es_doc, creation_date)
            es_docs.append(fa_es_doc)
        fa_data = fa_es_doc["_source"].copy()
        fa_data.update({"service": service_infos.get("eid"), "creation_date": creation_date})
        es_doc = self.import_facomponent(
            metadata, idx, fa_data, header["identifier"], service_infos
        )
        if es_doc:
            es_docs.append(es_doc)
        return es_docs

    def delete_record(self, header, service_infos):
        """this method is not implemented as the record.deleted is set on a
        FAcomponent, not on FindingAid
        """
        pass
        # identifier = header["identifier"]
        # self.log.warning("no FindingAid found for deleted record: %r", identifier)

    def import_findingaid(self, header, metadata, service_infos, findingaid_support):
        name = header["name"] or "Sans titre"
        origination = " ; ".join(metadata["creator"])
        did_attrs = {
            "unittitle": name,
            "origination": origination,
        }
        did_data = self.create_entity("Did", clean_values(did_attrs))
        fa_header_data = self.create_entity("FAHeader", {"titleproper": name})
        publisher = service_infos.get("name")
        if not publisher:
            publisher = "; ".join(metadata["publisher"]) or "XXX"
        fa_attrs = {
            "name": header["irname"],
            "eadid": header["eadid"],
            "did": did_data["eid"],
            "publisher": publisher,
            "service": service_infos.get("eid"),
            "stable_id": header["stable_id"],
            "fa_header": fa_header_data["eid"],
            "findingaid_support": findingaid_support["eid"],
            "oai_id": compute_oai_id(service_infos["oai_url"], header["identifier"]),
        }
        fa_attrs["creation_date"] = metadata["creation_date"]
        fa_data = self.create_entity("FindingAid", clean_values(fa_attrs))
        indexes = self.index_entries(
            {"origine": metadata["creator"]},
            fa_data["eid"],
            fa_attrs,
        )
        fa_es_attrs = {
            "fa_stable_id": fa_data["stable_id"],
            "scopecontent": strip_html(fa_attrs.get("scopecontent")),
            "originators": [origination],
            "index_entries": indexes,
            "digitized": False,
            "digitized_all": DZFacetValues.index_values(False, False),
            "alltext": name,
            **service_infos_for_es_doc(self.store._cnx, service_infos),
        }
        es_doc = self.build_complete_es_doc("FindingAid", fa_data, did_data, **fa_es_attrs)
        self.create_entity(
            "EsDocument", {"doc": json_dumps(es_doc["_source"]), "entity": fa_data["eid"]}
        )
        return es_doc

    def get_extptr(self, metadata):
        """take the first found <dc:identifier> as extptr (cf. 611)"""
        for url in metadata["identifier"]:
            if url and len(url) > 2048:
                self.log.error(
                    "do not import import extptr length %s: %r",
                    len(url),
                    url,
                )
            else:
                return url

    def digitized_version(self, metadata):
        dao = []
        bnf_prefix = "vignette :"
        for url in metadata["relation"]:
            illustration_url = None
            if bnf_prefix in url:
                # clean url : BNF adds "vignette :" before the url
                url = illustration_url = url.split(bnf_prefix)[1].strip()
            if not self.is_dao_url_valid(url):
                self.log.error(
                    "Do not import import dao with relation url length %s: %r",
                    len(url),
                    url,
                )
                continue
            if illustration_url:
                # vignette -> illustration url
                dao.append({"illustration_url": illustration_url.strip(), "role": "thumbnail"})
            else:
                # without vignette -> viewer url
                dao.append({"url": url.strip()})
        for url in metadata.get("hasFormat", []):
            if not self.is_dao_url_valid(url):
                self.log.error(
                    "Do not import dao with hasFormat url length %s: %r",
                    len(url),
                    url,
                )
            else:
                dao.append({"url": url.strip(), "role": IIIF_MANIFEST_ROLE})
        return dao

    def import_facomponent(
        self, metadata, component_order, findingaid_data, identifier, service_infos
    ):
        fa_stable_id = findingaid_data["stable_id"]
        unittitle = " ; ".join(metadata["title"])
        # Use <header><identifier> to compute the stable_id
        # cf https://extranet.logilab.fr/ticket/64684874
        fac_stable_id = component_stable_id_for_dc(identifier, fa_stable_id)
        did_attrs = {
            "unitid": " ; ".join(metadata["source"]),
            "unittitle": unittitle,
            "unitdate": metadata["date"],
            "startyear": metadata["date1"] or get_year(metadata["date"]),
            "stopyear": metadata["date2"],
            "physdesc": self.richstring_html(" ; ".join(metadata["format"]), "physdesc"),
            "physdesc_format": "text/html",
            "origination": " ; ".join(metadata["creator"]),
            "extptr": self.get_extptr(metadata),
        }
        languages = " ; ".join(metadata["language"])
        if len(languages) < 4:
            did_attrs["lang_code"] = languages
        else:
            did_attrs["lang_description"] = self.richstring_html(languages, "language")
            did_attrs["lang_description_format"] = "text/html"
        did_data = self.create_entity("Did", clean_values(did_attrs))
        comp_attrs = {
            "finding_aid": findingaid_data["eid"],
            "stable_id": fac_stable_id,
            "did": did_data["eid"],
            "scopecontent": self.richstring_html(
                " ; ".join(metadata["description"]), "scopecontent"
            ),
            "scopecontent_format": "text/html",
            "userestrict": self.richstring_html(metadata["rights"], "userestrict"),
            "userestrict_format": "text/html",
            "component_order": component_order,
        }
        comp_attrs["creation_date"] = findingaid_data.get("creation_date")
        comp_data = self.create_entity("FAComponent", clean_values(comp_attrs))
        # add daos
        comp_eid = comp_data["eid"]
        daodefs = self.digitized_version(metadata)
        for daodef in daodefs:
            digit_ver_attrs = self.create_entity("DigitizedVersion", clean_values(daodef))
            self.add_rel(comp_eid, "digitized_versions", digit_ver_attrs["eid"])
        else:
            digit_ver_attrs = {}
        indexes = self.index_entries(
            {
                "index_personne": metadata["contributor"],
                "index_lieu": metadata["coverage"],
                "index_matiere": metadata["subject"],
                "origine": metadata["creator"],
            },
            comp_eid,
            findingaid_data,
        )
        iiif = bool([d for d in daodefs if d.get("role") == IIIF_MANIFEST_ROLE])
        es_doc = self.build_complete_es_doc(
            "FAComponent",
            comp_data,
            did_data,
            fa_stable_id=fa_stable_id,
            scopecontent=strip_html(comp_attrs.get("scopecontent")),
            originators=metadata["creator"],
            index_entries=indexes,
            digitized=bool(daodefs),
            digitized_all=DZFacetValues.index_values(digitized=bool(daodefs), iiif=iiif),
            **service_infos_for_es_doc(self.store._cnx, service_infos),
        )
        self.create_entity("EsDocument", {"doc": json_dumps(es_doc["_source"]), "entity": comp_eid})
        return es_doc


def import_oai_dc_filepath(store, filepath, service_infos, config=None):
    reader = OAIDCHarvestedReader(config, store)
    return reader.import_filepath(filepath, service_infos)
