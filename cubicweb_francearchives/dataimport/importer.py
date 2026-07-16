# -*- coding: utf-8 -*-
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


# standard library imports
import logging
import multiprocessing as mp
import os.path as osp

from itertools import chain

# third party imports
# CubicWeb specific imports
from cubicweb.dataimport.stores import RQLObjectStore

# library specific imports
from cubicweb_francearchives import admincnx, init_bfss
from cubicweb_francearchives.dataimport import (
    capture_exception,
    es_bulk_index,
    FakeQueue,
    init_sentry_client,
    load_services_map,
    log_in_db,
    OAIPMH_DC_PATH,
    service_infos_from_filepath,
    sqlutil,
)
from cubicweb_francearchives.dataimport.oai_dc import import_oai_dc_filepath
from cubicweb_francearchives.dataimport.ead import Reader
from cubicweb_francearchives.dataimport.stores import create_massive_store


LOGGER = logging.getLogger()


def findingaid_importer(appid, filepath_queue, config):
    init_sentry_client(config)
    with admincnx(appid) as cnx:
        _findingaid_importer(cnx, filepath_queue, config)


def _findingaid_importer(cnx, filepath_queue, config):
    """import from files"""
    services_map = load_services_map(cnx)
    # bfss should be initialized to enable `FSPATH` in rql
    init_bfss(cnx.repo)
    if not config["esonly"]:
        store = create_massive_store(cnx, slave_mode=True)
    else:
        store = RQLObjectStore(cnx)
    readercls = config.get("readercls", Reader)
    r = readercls(config, store)
    indexer = cnx.vreg["es"].select("indexer", cnx)
    es = indexer.get_connection()
    es_docs = []
    while True:
        next_job = filepath_queue.get()
        # worker got None in the queue, job is finished
        if next_job is None:
            break
        filepath = next_job
        if isinstance(filepath, bytes):
            filepath = filepath.decode("utf-8")
        try:
            service_infos = service_infos_from_filepath(filepath, services_map)
            if OAIPMH_DC_PATH in filepath:
                es_docs = import_oai_dc_filepath(store, filepath, service_infos, config)
            else:
                es_docs = r.import_filepath(filepath, service_infos)
        except Exception as exc:
            import traceback

            traceback.print_exc()
            print("failed to import", repr(filepath))
            LOGGER.exception("failed to import %r", filepath)
            capture_exception(exc, filepath)
            continue
        if not config["esonly"]:
            store.flush()
            store.commit()
        if es_docs and not config["noes"]:
            es_bulk_index(es, es_docs, logger=LOGGER)
    if not config["esonly"]:
        cnx.commit()


def _import_filepaths(cnx, filepaths, config):
    indexer = cnx.vreg["es"].select("indexer", cnx)
    indexer.create_index(index_name="{}_all".format(indexer._cw.vreg.config["index-name"]))
    # leave at least one process available
    nb_processes = config.get("nb_processes", max(mp.cpu_count() - 1, 1))
    if cnx.vreg.config.mode == "test":
        fake_queue = FakeQueue([None] + filepaths)
        _findingaid_importer(cnx, fake_queue, config)
    elif nb_processes == 1:
        fake_queue = FakeQueue([None] + filepaths)
        findingaid_importer(config["appid"], fake_queue, config)
    else:
        queue = mp.Queue(2 * nb_processes)
        workers = []
        for i in range(nb_processes):
            # findingaid_importer(appid, filepath_queue, config):
            workers.append(
                mp.Process(target=findingaid_importer, args=(config["appid"], queue, config))
            )
        for w in workers:
            w.start()
        nb_files = len(filepaths)
        for idx, job in enumerate(chain(filepaths, (None,) * nb_processes)):
            if job is not None:
                if not osp.isfile(job):
                    LOGGER.warning("ignoring unknown file %r", job)
                    continue
                print("pushing %s/%s job in queue - %s" % (idx + 1, nb_files, osp.basename(job)))
            queue.put(job)
        for w in workers:
            w.join()


@log_in_db
def import_filepaths(cnx, filepaths, config, store=None):
    foreign_key_tables = sqlutil.ead_foreign_key_tables(cnx.vreg.schema)
    if not config["esonly"]:
        store = store or create_massive_store(cnx, nodrop=config["nodrop"])
        store.master_init()
        if config["nodrop"]:
            with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
                sqlutil.disable_triggers(su_cnx, foreign_key_tables)
        cnx.commit()
    _import_filepaths(cnx, filepaths, config)
    if not config["esonly"]:
        store.finish()
        store.commit()
    if config["nodrop"]:
        with sqlutil.sudocnx(cnx, interactive=False) as su_cnx:
            sqlutil.enable_triggers(su_cnx, foreign_key_tables)
