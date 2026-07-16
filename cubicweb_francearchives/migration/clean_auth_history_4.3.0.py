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

"""check and repare authority_history table"""

from argparse import ArgumentParser

import logging
from cubicweb.utils import admincnx

from cubicweb_francearchives import IIIF_MANIFEST_ROLE, Authkey, register_auth_history

from pprint import pprint

failed_mark = "\033[91m" + "x" + "\033[0m"
passed_mark = "\033[32m" + "\u2713" + "\33[0m"


class AuthorityHistoryHandler:

    def __init__(self, logger, options):
        self.logger = logger
        self.options = options

    def log(self, message, res, status=None):
        self.logger.info("")
        if status is not None:
            self.logger.info(f" {passed_mark if status else failed_mark} {message}")
        else:
            self.logger.info(message)
        if self.options.verbose and res:
            pprint(res)

    def check_grouped_authorities(self, auth_types=None):
        with admincnx(options.CW_INSTANCE) as cnx:
            cursor = cnx.cnxset.cu
            auth_types = auth_types or ("agent", "subject", "location")
            for auth_type in auth_types:
                cursor.execute(
                    f"""
                    SELECT format('{auth_type}/%s', ah.autheid) as autheid,
                        format('{auth_type}/%s', sub.cw_eid) as cw_eid,
                        format('{auth_type}/%s', g.eid_to) as grouping_eid,
                        ah.label, sub.cw_label, sub.cw_quality,
                        ah.fa_stable_id
                    FROM authority_history as ah,
                        cw_{auth_type}authority as sub
                    JOIN grouped_with_relation as g ON sub.cw_eid=g.eid_from
                    WHERE ah.autheid=sub.cw_eid
                    ORDER BY 1, 2;
                    """
                )
                rset = cursor.fetchall()
                count = len(rset) if rset else 0
                msg = (
                    f"authority_history contains {count} grouped "
                    f"{auth_type.capitalize()}Authority"
                )
                self.log(msg, rset, status=count == 0)

    def check_duplicated_rows(self):
        with admincnx(options.CW_INSTANCE) as cnx:
            cursor = cnx.cnxset.cu
            cursor.execute(
                """
                SELECT * from (
                    SELECT fa_stable_id,
                        ROW_NUMBER() OVER(PARTITION BY
                             fa_stable_id, type, indexrole, label
                        ORDER BY fa_stable_id asc) AS row
                    FROM  authority_history ) as duplicated
                WHERE duplicated.row > 1;
            """
            )
            rset = cursor.fetchall()

            count = len(rset) if rset else 0
            msg = f"authority_history contains {count} duplicated rows"
            self.log(msg, rset, status=count == 0)

    def check_authority_history(self):
        with admincnx(options.CW_INSTANCE) as cnx:
            cursor = cnx.cnxset.cu

            cursor.execute(
                """
            SELECT ah.autheid, ah.type
            FROM authority_history as ah
            WHERE ah.type IN ('persname', 'corpname', 'famname', 'name') AND
                  NOT EXISTS(SELECT cw_eid
                      FROM cw_AgentAuthority as sub
                      WHERE ah.autheid = cw_eid);
           """
            )
            rset = cursor.fetchall()

            count = len(rset) if rset else 0
            msg = f"authority_history contains {count} agents which are not in cw_AgentAuthority"
            self.log(msg, rset, status=count == 0)
            cursor.execute(
                """
            SELECT ah.autheid, ah.type
            FROM authority_history as ah
            WHERE ah.type='geogname' AND
                  NOT EXISTS(SELECT cw_eid
                      FROM cw_LocationAuthority as sub
                      WHERE ah.autheid = cw_eid);
           """
            )
            rset = cursor.fetchall()

            count = len(rset) if rset else 0
            msg = (
                f"authority_history contains {count} locations which are not "
                "in cw_LocationAuthority"
            )
            self.log(msg, rset, status=count == 0)

            cursor.execute(
                """
                SELECT ah.autheid, ah.type
                FROM authority_history as ah
                WHERE ah.type IN ('subject', 'function', 'genreform', 'occupation') AND
                NOT EXISTS(SELECT cw_eid
                FROM cw_SubjectAuthority as sub
                WHERE ah.autheid = cw_eid);
                """
            )
            rset = cursor.fetchall()
            count = len(rset) if rset else 0
            msg = f"authority_history contains {count} subject which are not in cw_SubjectAuthority"
            self.log(msg, rset, status=count == 0)

            cursor.execute(
                """
                SELECT ah.autheid
                FROM authority_history as ah
                WHERE NOT EXISTS(SELECT eid
                FROM entities
                WHERE  ah.autheid = entities.eid);
                """
            )
            rset = cursor.fetchall()
            count = len(rset) if rset else 0
            msg = f"authority_history contains {count} authorities which are not in entities"
            self.log(msg, rset, status=count == 0)

            cursor.execute(
                """
                SELECT DISTINCT(e.type)
                FROM authority_history as ah, entities as e
                WHERE ah.autheid=e.eid;
                """
            )
            rset = cursor.fetchall()
            got = {r for r, in rset}
            msg = f"authority_history contains {got} authorities cw_etypes"
            expected = {"AgentAuthority", "SubjectAuthority", "LocationAuthority"}
            self.log(msg, rset, status=expected == got)

    def fix_grouped_authorities(self):
        """Change autheid of grouped authority_history authorities
        to grouping authorities
        """
        auth_types = ["agent", "subject", "location"]
        self.check_grouped_authorities(auth_types=auth_types)
        expected = []
        with admincnx(options.CW_INSTANCE) as cnx:
            cursor = cnx.cnxset.cu
            for auth_type in auth_types:
                cursor.execute(
                    f"""
                    SELECT ah.autheid, ah.fa_stable_id, ah.type, ah.label, ah.indexrole, g.eid_to
                    FROM authority_history as ah,
                    cw_{auth_type}authority as sub
                    JOIN grouped_with_relation as g ON sub.cw_eid=g.eid_from
                    WHERE ah.autheid=sub.cw_eid
                    ORDER BY 1, 2;
                    """
                )
                data = cursor.fetchall()
                self.logger.info(f"Fix {len(data)} rows in cw_{auth_type}authority")

                for old_autheid, fa_stable_id, itype, label, role, new_autheid in data:
                    key = Authkey(fa_stable_id, itype, label, role)
                    register_auth_history(cnx, key, new_autheid)
                    cursor.execute(
                        """
                        SELECT autheid FROM authority_history
                        WHERE fa_stable_id=%(fa)s AND type=%(type)s AND
                        label=%(l)s AND indexrole=%(role)s
                        """,
                        {
                            "fa": key.fa_stable_id,
                            "type": key.type,
                            "l": key.label,
                            "role": key.role or "index",
                        },
                    )
                    msg = f"Fixed {old_autheid, fa_stable_id, itype, label, role} -> {new_autheid}"
                    got_autheid = cursor.fetchall()[0][0]
                    self.log(msg, "", status=got_autheid == new_autheid)
                    if got_autheid == new_autheid:
                        cnx.commit()
                    else:
                        cnx.rollback()
            self.check_grouped_authorities(auth_types=auth_types)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("CW_INSTANCE", help="Name of the CW application instance")

    parser.add_argument(
        "-f",
        "--f",
        dest="fix",
        action="store_true",
        default=False,
        help="Clean authority_history",
    )
    parser.add_argument(
        "-c",
        "--check",
        dest="check",
        action="store_true",
        default=False,
        help="Check authority_history table",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        dest="verbose",
        action="store_true",
        default=False,
        help="Write sql query results",
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
        default="/tmp/clean_auth_history.log",
    )
    return parser.parse_args()


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


if __name__ == "__main__":
    options = parse_args()
    print(options)
    logger = init_logger(options)
    handler = AuthorityHistoryHandler(logger, options)
    if options.check:
        logger.info("check authority_history")
        handler.check_duplicated_rows()
        handler.check_grouped_authorities()
        handler.check_authority_history()

    if options.fix:
        logger.info("fix authority_history")
        handler.fix_grouped_authorities()
