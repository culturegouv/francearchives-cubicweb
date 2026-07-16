# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
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

"""Remove viewers relatives URL from DB"""

from argparse import ArgumentParser

import logging

from cubicweb.utils import admincnx
from cubicweb_francearchives import IIIF_MANIFEST_ROLE
from cubicweb_francearchives.dataimport.sqlutil import no_trigger

logger = logging.getLogger("francearchives.migration")
logger.setLevel(logging.INFO)

from pprint import pprint

failed_mark = "\033[91m" + "x" + "\033[0m"
passed_mark = "\033[32m" + "\u2713" + "\33[0m"


def log(logger, message, res, status=None, print_rset=True):
    logger.info("")
    if status is not None:
        logger.info(f" {passed_mark if status else failed_mark} {message}")
    else:
        logger.info(message)
    if print_rset:
        if status:
            logger.info(res)
        else:
            logger.error(res)
        pprint(res)


def init_logger(options):
    # init logger
    logfile = options.logfile
    logger = logging.getLogger("francearchives.clean_authority_record")
    handler = logging.FileHandler(logfile)
    if options.log:
        logger.setLevel(getattr(logging, options.log.upper()))
    else:
        logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


def check_daos(logger, options):
    with admincnx(options.CW_INSTANCE) as cnx:
        cursor = cnx.cnxset.cu
        cursor.execute(
            """
            SELECT distinct digitized_versions_relation.eid_to
            FROM cw_findingaid, digitized_versions_relation
            WHERE NOT EXISTS(SELECT eid
            FROM entities
            WHERE digitized_versions_relation.eid_to = entities.eid) AND
                digitized_versions_relation.eid_from=cw_findingaid.cw_eid;
            """
        )
        rset = cursor.fetchall()
        count = len(rset) if rset else 0
        msg = f"digitized_versions_relation dao {count} not in entities "
        log(logger, msg, rset, status=count == 0)
        cursor.execute(
            """SELECT distinct dz.cw_eid
                FROM cw_DigitizedVersion dz
                WHERE NOT EXISTS(SELECT eid
                      FROM entities
                      WHERE dz.cw_eid = entities.eid);
            """
        )
        rset = cursor.fetchall()
        count = len(rset) if rset else 0
        msg = f"DigitizedVersion {count} not in entities"
        log(logger, msg, rset, status=count == 0)
        return
        cursor.execute(
            """
            SELECT dv.eid_from, count(dv.eid_from)
            FROM digitized_versions_relation dv
            GROUP BY dv.eid_from
            HAVING COUNT(dv.eid_from) > 100
            ORDER BY 2 DESC;           """
        )
        rset = cursor.fetchall()
        count = len(rset) if rset else 0
        # msg = (
        #    f"3 {count} dv "
        # )
        ## log(logger, msg, rset, status=count == 0)


def remove_daos_with_relatif_url(logger, options, delete=False):
    """
    remove daos with relative url. As more transformation is done in FA code,
    we can remove all useless relative url.
    """
    with admincnx(options.CW_INSTANCE) as cnx:
        logger.info(
            "create 'dao_to_remove' table with DAO references with relative "
            "cw_digitizedversion.url, this will take a few minutes"
        )
        cursor = cnx.cnxset.cu
        cursor.execute("DROP TABLE IF EXISTS dao_to_remove")
        cursor.execute("CREATE TABLE dao_to_remove (eid integer, url varchar)")
        cursor.execute("CREATE INDEX dao_to_remove_idx ON dao_to_remove(eid)")
        ## remove empty and relative cw_url (viewer)
        cursor.execute(
            """INSERT INTO dao_to_remove
               SELECT dz.cw_eid, dz.cw_url
               FROM cw_DigitizedVersion dz
               WHERE coalesce(TRIM(cw_url), '') !='' AND
                   not dz.cw_url  ~* 'http' AND
                   not dz.cw_url  ~* '^www';
            """
        )
        ## remove daos
        cursor.execute(
            """INSERT INTO dao_to_remove
               SELECT dz.cw_eid, dz.cw_url
               FROM cw_DigitizedVersion dz
               WHERE coalesce(TRIM(cw_url), '') ='' AND
                   coalesce(TRIM(cw_illustration_url), '') =''
        """
        )
        cursor.execute("Select count(cw_url) from cw_DigitizedVersion")
        rset = cursor.fetchall()
        count = rset[0][0]
        msg = f"Found {count} DAOs in DigitizedVersion "
        log(logger, msg, rset)

        cursor.execute("Select count(eid) from dao_to_remove")
        rset = cursor.fetchall()
        count = rset[0][0]
        msg = f"Found {count} DAOs in dao_to_remove"
        log(logger, msg, rset)

        cursor.execute("select * from dao_to_remove where url ~* 'http';")
        rset = cursor.fetchall()
        count = len(rset) if rset else 0
        msg = f"{count} URL from dao_to_remove where url ~* 'http';'"
        log(logger, msg, rset, status=count == 0)

        cursor.execute("select * from dao_to_remove where url ~* '^//';")
        rset = cursor.fetchall()
        count = len(rset) if rset else 0
        msg = f"{count} URL from dao_to_remove where url ~* '^//'"
        log(logger, msg, rset, status=count == 0)
        cursor.execute("select * from dao_to_remove where coalesce(TRIM(url), '') ='';")
        rset = cursor.fetchall()
        count = len(rset) if rset else 0
        msg = f"{count} URL from dao_to_remove where coalesce(TRIM(url), '') =''"
        log(logger, msg, rset)

        cursor.execute("select * from dao_to_remove where url is NULL;")
        rset = cursor.fetchall()
        count = len(rset) if rset else 0
        msg = f"{count} URL from dao_to_remove where  where url is NULL;"
        log(logger, msg, rset)

        if delete:
            with no_trigger(
                cnx,
                tables=(
                    "entities",
                    "created_by_relation",
                    "owned_by_relation",
                    "cw_source_relation",
                    "is_relation",
                    "is_instance_of_relation",
                    "cw_digitizedversion",
                    "digitized_versions_relation",
                ),
                interactive=False,
                logger=logger,
            ):
                logger.info(
                    "Start deleting DAO references with relative cw_digitizedversion.url, "
                    "this will take a few minutes"
                )
                cursor.execute("BEGIN;")
                cursor.execute("SELECT delete_entities('cw_digitizedversion', 'dao_to_remove')")
                cursor.execute("COMMIT;")
                print("\t=> entities deleted")
        cursor.execute("DROP TABLE IF EXISTS dao_to_remove")


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("CW_INSTANCE", help="Name of the CW application instance")

    parser.add_argument(
        "-f",
        "--f",
        dest="fix",
        action="store_true",
        default=False,
        help="Prepare to clean dao",
    ),
    parser.add_argument(
        "-d",
        "--d",
        dest="commit",
        action="store_true",
        default=False,
        help="Clean daos and commit",
    )
    parser.add_argument(
        "-c",
        "--check",
        dest="check",
        action="store_true",
        default=False,
        help="Check daos",
    )
    parser.add_argument(
        "-log",
        "--log",
        dest="log",
        help="Logs level (INFO, WARNING, ERROR)",
    )
    parser.add_argument(
        "--logfile",
        dest="logfile",
        help="logfile",
        default="/tmp/clean_daos.log",
    )
    return parser.parse_args()


if __name__ == "__main__":
    options = parse_args()
    print(options)
    logger = init_logger(options)
    if options.check:
        logger.info("check daos integrity")
        check_daos(logger, options)
    if options.fix:
        logger.info("remove daos with relatif url ")
        remove_daos_with_relatif_url(logger, options, delete=options.commit)
