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
import logging

from cubicweb_eac import sobjects as eac
from cubicweb_eac import dataimport


from cubicweb_francearchives.storage import S3BfssStorageMixIn
from cubicweb_francearchives.dataimport import OptimizedExtEntitiesImporter, first
from cubicweb_francearchives.dataimport.eac import init_extid2eid_index
from cubicweb_francearchives.dataimport.ape_eac import create_ape_eac_xml, preprocess_eac

LOGGER = logging.getLogger()


class EACOptimizedExtEntitiesImporter(OptimizedExtEntitiesImporter):
    """ """

    def __init__(
        self,
        schema,
        store,
        extid2eid=None,
        existing_relations=None,
        etypes_order_hint=(),
        import_log=None,
        raise_on_error=False,
        log=None,
        fpath=None,
    ):
        if log is None:
            self.log = LOGGER
        self.fpath = fpath
        super(EACOptimizedExtEntitiesImporter, self).__init__(
            schema,
            store,
            extid2eid,
            existing_relations,
            etypes_order_hint,
            import_log,
            raise_on_error,
        )
        self.storage = S3BfssStorageMixIn()

    def add_xml_support(self, ext_entity):
        ext_entity.values["xml_support"] = {self.storage.storage_ufilepath(self.fpath)}

    def add_ape_ead_file(self, ext_entity):
        xml_path = first(ext_entity.values["xml_support"])
        record_id = first(ext_entity.values["record_id"])
        binary = self.storage.storage_get_file_content(xml_path)
        try:
            binary = self.storage.storage_get_file_content(xml_path)
            tree = preprocess_eac(binary)
        except Exception as ex:
            self.log.error(f"[ape_ead] Could not generate ape_ead_file for {record_id}: {ex}")
            return
        service_infos = {"service_code": record_id.split("_")[0]}
        ape_file = create_ape_eac_xml(self.store._cnx, self.storage, tree, record_id, service_infos)
        self.extid2eid["file-{ape_file.eid}"] = ape_file.eid
        # add ape_file to
        ext_entity.values["ape_eac_file"] = {"file-{ape_file.eid}"}

    def create_maintainer(self, ext_entity):
        record_id = first(ext_entity.values["record_id"])
        service_code = record_id.split("_")[0]
        if service_code:
            service_extid = "service-{}".format(service_code)
            if service_extid in self.extid2eid:
                ext_entity.values["maintainer"] = set([service_extid])
            else:
                self.import_log.record_warning("no service found for {}".format(record_id))

    def complete_extentities(self, extentities):
        """process the `extentities` flow and add missing `Service` on
        ̀AuthorityRecord`.
        """
        for ext_entity in extentities:
            if ext_entity.etype == "AuthorityRecord":
                self.create_maintainer(ext_entity)
                self.add_xml_support(ext_entity)
                self.add_ape_ead_file(ext_entity)
            yield ext_entity

    def import_entities(self, extentities):
        super(EACOptimizedExtEntitiesImporter, self).import_entities(
            self.complete_extentities(extentities)
        )


class EACCPFImporter(dataimport.EACCPFImporter):
    """Override eac cube's EACCPFImporter to add a validator."""

    def check_notice_validity(self, extid2eid):
        control = self._elem_find(self._root, "eac:control")
        if control is None:
            raise dataimport.MissingTag("control")
        record_id = self._elem_find(control, "eac:recordId")
        if record_id is None or not record_id.text or not record_id.text.strip():
            raise dataimport.MissingTag("recordId")
        record_id = record_id.text.strip()
        service_code = record_id.split("_")[0]
        service_extid = "service-{}".format(service_code)
        if service_extid not in extid2eid:
            raise dataimport.InvalidEAC(
                "<recordId> value {} starts with an unknown service code".format(record_id)
            )

    def build_name_entry(self, element):
        """Build a NameEntry external entity.
        Entities need to be filtered because of the yield chain of the
        original function which yields the entity and its children
        """
        for entity in super(EACCPFImporter, self).build_name_entry(element):
            if entity.etype == "NameEntry":
                # In cubicweb_eac this value is set depending of an other xml element
                # than the one needed in francearchives.
                # We only care about the value of the attribute @localType
                # of the <nameEntry> tag
                entity.values["form_variant"] = {None}
                if element.get("localType") == "autorisée":
                    entity.values["form_variant"] = {"authorized"}
            yield entity


class EACImportService(eac.EACImportService):
    """Override eac cube's EACCPFService"""

    def external_entities_generator(self, stream, import_log):
        return EACCPFImporter(stream, import_log, self._cw._)

    def _import_eac_stream(self, stream, import_log, store, extid2eid=None, **kwargs):
        if extid2eid is None:
            source = self._cw.repo.system_source
            extid2eid = init_extid2eid_index(self._cw.cnx, source)
            # extid2eid = eac.init_extid2eid_index(self._cw, source)
        importer = EACOptimizedExtEntitiesImporter(
            self._cw.vreg.schema,
            store,
            import_log=import_log,
            extid2eid=extid2eid,
            etypes_order_hint=dataimport.ETYPES_ORDER_HINT,
            **kwargs,
        )
        generator = self.external_entities_generator(stream, import_log)
        generator.check_notice_validity(extid2eid)
        extentities = self.external_entities_stream(generator.external_entities(), extid2eid)
        importer.import_entities(extentities)
        if generator.record is not None:
            record_id = generator.record.values["record_id"]
            store._cnx.execute("DELETE AuthorityRecord X WHERE X record_id %(r)s", {"r": record_id})
            # ES delete operation will be triggerd by cw hook
            extid = generator.record.extid
            record_eid = importer.extid2eid[extid]
        else:
            record_eid, record_id = None, None
        record = {"record_id": record_id, "eid": record_eid}
        return importer.created, importer.updated, record, generator.not_visited()


def registration_callback(vreg):
    vreg.register_and_replace(EACImportService, eac.EACImportService)
