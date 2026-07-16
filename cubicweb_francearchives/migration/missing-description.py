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


from cubicweb_francearchives.dataimport import load_metadata_file, remove_extension


def main(cnx, metadata_filepaths):
    result = {}
    for metadata_file in metadata_filepaths:
        allmetadata = load_metadata_file(metadata_file)
        for identifier, metadata in list(allmetadata.items()):
            descr = metadata.get("dc_description ", "").strip()
            if descr:
                identifier = remove_extension(metadata["dc_identifier"])
                result[identifier] = descr
    pg_cwcnx = cnx.repo.system_source.get_connection()
    pg_cwcu = pg_cwcnx.cursor()

    print("start executing sql")
    pg_cwcu.executemany(
        "UPDATE cw_findingaid SET cw_description = %s FROM cw_did where cw_did.cw_eid = cw_findingaid.cw_did AND cw_did.cw_unitid = %s",
        [(descr, identifier) for identifier, descr in list(result.items())],
    )
    pg_cwcnx.commit()


main(cnx, __args__)  # noqa
