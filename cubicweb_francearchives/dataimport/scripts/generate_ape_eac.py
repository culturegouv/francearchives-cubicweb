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

import logging


from cubicweb_francearchives import init_bfss
from cubicweb_francearchives.dataimport import load_services_map
from cubicweb_francearchives.dataimport.ape_eac import (
    generate_ape_eac_xml,
    create_file,
    preprocess_eac,
)
from cubicweb_francearchives.storage import S3BfssStorageMixIn


def generate_ape_eac_file_by_storage(cnx, st, tree, record_id, service_infos):
    """
    Generate the right ape-ead filepath depending on the storage
    """
    # FIXME s3 we should not take account of cnx.vreg.config["appfiles-dir"]
    # which must be ""
    ape_filepath = generate_ape_eac_xml(cnx, tree, record_id, service_infos)
    return st.storage_handle_ape_ead_filepath(ape_filepath)


def get_service_infos(services_map, service_code):
    infos = {
        "code": service_code,
        "name": service_code,
        "eid": None,
    }
    if service_code in services_map:
        service = services_map[service_code]
        infos.update(
            {
                "eid": service.eid,
                "name": service.publisher(),
            }
        )
    return infos


def generate_ape_eac_from_xml(cnx, logger, regenerate=False, service_code=None, from_eid=None):
    """generate all ape_eac_files from xml"""
    args = {}
    query = (
        "Any X, SI, FSP, FSPATH(AD), CS "
        "WHERE X is AuthorityRecord, X xml_support FSP, X record_id SI, "
        "X ape_eac_file AF?, AF data AD, "
        "X maintainer S, S code CS"
    )
    if service_code:
        query += ", S code %(code)s"
        args["code"] = service_code
    elif from_eid:
        query += ", X eid %(eid)s"
        args["eid"] = from_eid
    rset = cnx.execute(query, args)
    if service_code:
        logger.info(f"Found {rset.rowcount} AuthorityRecords for service code {service_code}")
    elif from_eid:
        logger.info(f"Found {rset.rowcount} AuthorityRecords for eid {from_eid}")
    else:
        logger.info(f"Found {rset.rowcount} AuthorityRecords")
    if rset:
        generate_ape_eac_from_rset(cnx, rset, logger, regenerate=regenerate)


def generate_ape_eac_from_rset(cnx, rset, logger, regenerate=False):
    services_map = load_services_map(cnx)
    st = S3BfssStorageMixIn()
    for ar_eid, record_id, xml_path, ape_eac_fspath, service_code in rset:
        if ape_eac_fspath and not regenerate:
            # do not regenerate the file
            continue
        try:
            binary = st.storage_get_file_content(xml_path)
            tree = preprocess_eac(binary)
        except Exception as ex:
            logger.error(f"[ape_ead] Could not generate ape_ead_file for {record_id}: {ex}")
            continue
        service_infos = get_service_infos(services_map, service_code)
        ape_filepath = generate_ape_eac_file_by_storage(cnx, st, tree, record_id, service_infos)
        ape_file = create_file(cnx, ape_filepath)
        cnx.execute(
            "SET X ape_eac_file F WHERE X eid %(x)s, F eid %(f)s",
            {"x": ar_eid, "f": ape_file.eid},
        )
        cnx.commit()
        logger.debug(f"[ape_ead] Generated ape_ead_file for {record_id}")


def generate_ape_eac_files(cnx, config, logger=None):
    init_bfss(cnx.repo)
    if logger is None:
        logger = logging.getLogger("ape-eac")
    if config.debug:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    generate_ape_eac_from_xml(
        cnx,
        regenerate=config.regenerate,
        service_code=config.service or None,
        from_eid=config.eid or None,
        logger=logger,
    )
