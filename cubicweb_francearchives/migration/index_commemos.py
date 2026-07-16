# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2021
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
"""add indexes to CommemorationItems"""

from argparse import ArgumentParser
import csv
from collections import OrderedDict
import os.path as osp
import re

from cubicweb.utils import admincnx

WARNING = False


FIELDNAMES = OrderedDict(
    [
        ("titre", "commemo_title"),
        ("url Page d’histoire", "commemo_url"),
        ("sujet", "subjects_title"),
        ("url sujet", "subjects_url"),
        ("agent", "agents_title"),
        ("url agent", "agents_url"),
        ("Lieux", "locations_title"),
        ("url Lieux", "locations_url"),
    ]
)


INDEX_URL = re.compile(".*/(?P<type>location|subject|agent)/(?P<eid>[0-9]+)$")  # noqa
EID_URL = re.compile(".*/(?P<eid>[0-9]+)$")  # noqa

INDEXES = {
    "agent": "AgentAuthority",
    "location": "LocationAuthority",
    "subject": "SubjectAuthority",
}


def clean_value(value):
    """Strip separator and leading/trailing whitespaces from value.

    :param str value: value to clean

    :returns: cleaned value
    :rtype: str
    """
    if value and isinstance(value, str):
        value = value.strip()
    return value


def add_indexes(cnx, csvfile, commit=False):
    sep = "###"
    with open(csvfile) as f:
        fieldnames = FIELDNAMES
        reader = csv.DictReader(
            f,
            delimiter="\t",
            fieldnames=list(fieldnames.keys()),
        )
        header = next(reader)  # noqa
        idx, added = 0, 0
        while True:
            try:
                line = next(reader)
                idx += 1
            except csv.Error as exception:
                print(f"line {idx}: skipped line ({exception})")
                continue
            except StopIteration:
                print(f"Imported {idx} lines")
                if commit:
                    print(f"""\n -> Added {added} indexes""")
                else:
                    print(f"""\n -> {added} indexes could be added""")

                return
            values = {fieldnames[key]: clean_value(value) for key, value in line.items()}
            if not any(line.values()):
                # skip empty line
                continue
            commemo_url = values["commemo_url"]
            commemo_title = values["commemo_title"]
            match = EID_URL.match(commemo_url)
            if not match:
                print(f"""-> line {idx+1}: no match for "{commemo_title}" {repr(commemo_url)}""")
                continue
            commemo_eid = match["eid"]
            try:
                commemo = cnx.find("CommemorationItem", eid=commemo_eid).one()
            except Exception as err:
                print(
                    f"""\n -> Error: line {idx+1}: authority "{commemo_title}" {commemo_url} not found: {err}\n"""  # noqa
                )
            for index_type in ("subjects", "agents", "locations"):
                labels = values[f"{index_type}_title"]
                urls = values[f"{index_type}_url"]
                if not (labels and urls):
                    continue
                if WARNING and ";" in labels and sep not in urls:
                    print(f""" --> line {idx+1}: found "{labels}" for a single url {urls}""")
                if labels and not urls:
                    print(f"""-> line {idx+1}: no url found for "{labels}" """)
                    continue
                for label, url in zip(labels.split(sep), urls.split(sep)):
                    url = url.strip()
                    if not url:
                        print(f"""-> line {idx+1}: no url found for "{label}" """)
                        continue
                    match = INDEX_URL.match(url)
                    if not match:
                        print(f"""-> line {idx+1}: wrong url "{repr(url)}" for "{label}" """)
                        continue
                    index_etype = INDEXES[match["type"]]
                    index_eid = match["eid"]
                    try:
                        authority = cnx.find(index_etype, eid=index_eid)
                    except Exception as err:
                        print(
                            f"""\n -> Error: line {idx+1}: authority "{label}" {url} not found: {err}\n"""
                        )
                        continue
                    if not authority:
                        print(f""" -> line {idx+1}: authority "{label}" {url} not found""")
                        continue
                    indexes = [res[0] for res in commemo.indexes()]
                    if int(index_eid) in indexes:
                        continue
                    added += 1
                    cnx.execute(
                        f"""SET X related_authority Y
                           WHERE X is CommemorationItem,
                           X eid {commemo_eid}, Y eid {index_eid},
                           NOT X related_authority Y"""
                    )
                    if commit:
                        cnx.commit()
                    else:
                        cnx.rollback()
    print(f"""\n -> Added {added} indexes""")


def parse_args():
    parser = ArgumentParser(description="CLI tools add indexes to CommemorationItems")
    parser.add_argument("CW_INSTANCE", help="Name of the CW application instance")

    parser.add_argument(
        "-c",
        "--commit",
        dest="commit",
        action="store_true",
        help="commit changes",
    )
    parser.add_argument(
        "-f",
        "--csvfile",
        dest="csvfile",
        help="CSV datafile",
    )

    return parser.parse_args()


def main():
    args = parse_args()
    csvfile = args.csvfile
    if not csvfile:
        HERE = osp.join(osp.abspath(osp.dirname(__file__)))
        csvfile = osp.join(HERE, "initialdata", "Indexation_Commemos_v1_logilab.csv")
    with admincnx(args.CW_INSTANCE) as cnx:
        add_indexes(cnx, csvfile, commit=args.commit)


if __name__ == "__main__":
    main()
