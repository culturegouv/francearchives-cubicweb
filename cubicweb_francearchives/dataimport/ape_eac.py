# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2022
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
from copy import deepcopy
import json
from lxml import etree
import mimetypes
import os.path as osp
from uuid import uuid4


from glamconv.cli.commands import eac_to_ape
from cubicweb import Binary

from cubicweb_francearchives.dataimport import compute_ape_relpath
from cubicweb_francearchives.storage import S3BfssStorageMixIn
from cubicweb_francearchives.xmlutils import XMLParser


def create_file(cnx, filepath):
    """Create CWFile with S3BfssStorageMixIn storage"""
    cnx.transaction_data["fs_importing"] = True
    ufilepath = S3BfssStorageMixIn().storage_ufilepath(filepath)
    basepath = osp.basename(ufilepath)
    return cnx.create_entity(
        "File",
        **{
            "data": Binary(ufilepath.encode("utf-8")),
            "data_format": str(mimetypes.guess_type(filepath)[0]),
            "data_name": basepath,
            "uuid": str(uuid4().hex),
        },
    )


def preprocess_eac(data):
    """Preprocesses the EAC xml file to remove ns and internal content

    Parameters:
    -----------

    data : the path to the EAD xml file or EAD xml file  Binary file content

    Returns:
    --------

    the lxml etree object, cleaned from internal content
    """
    if isinstance(data, bytes):
        from io import BytesIO

        data = BytesIO(data)
    return etree.parse(data, parser=XMLParser)


def generate_ape_eac_file_from_xml(cnx, tree, service_infos, record_id, ape_filepath):
    base_url = cnx.vreg.config.get("consultation-base-url")
    ar_url = f"{base_url}/autorityrecord.{record_id}"
    transform_ape_eac_file(ar_url, tree, ape_filepath)


def create_ape_eac_xml(cnx, storage, tree, record_id, service_infos):
    """
    Create ape_eac_xml file for the imported AuthorityRecord
    """
    ape_filepath = generate_ape_eac_xml(cnx, tree, record_id, service_infos)
    ape_filepath = storage.storage_handle_ape_ead_filepath(ape_filepath)
    return create_file(cnx, ape_filepath)


def generate_ape_eac_xml(cnx, tree, record_id, service_infos):
    """
    Compute ape_eac_xml file and write it in the ape_filepath
    """
    ape_filepath = osp.join(
        cnx.vreg.config["appfiles-dir"],
        compute_ape_relpath(cnx, "ape-eac", record_id, service_infos),
    )
    generate_ape_eac_file_from_xml(cnx, tree, service_infos, record_id, ape_filepath)
    return ape_filepath


def eac_to_ape_settings():
    """load default eac2 -> ape transformation settings"""
    settings_filepath = osp.join(
        osp.dirname(__file__), "francearchives-eac-cpf-to-ape-settings.json"
    )
    with open(settings_filepath) as inputf:
        return json.load(inputf)


def transform_ape_eac_file(ar_url, tree, ape_filepath):
    eac_to_ape(deepcopy(tree), ape_filepath)
