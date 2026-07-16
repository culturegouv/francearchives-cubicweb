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

from functools import partial
import logging
import time

from psycopg2 import OperationalError
from sickle.oaiexceptions import NoRecordsMatch

from cubicweb_francearchives import get_user_agent
from cubicweb_francearchives.dataimport import (
    log_in_db,
    load_services_map,
    service_infos_from_service_code,
)
from cubicweb_francearchives.dataimport import OAIPMH_EAD_PREFIXES, oai_ead, oai_dc
from cubicweb_francearchives.dataimport import oai_nomina
from cubicweb_francearchives.dataimport.oai_utils import OAIXMLError, parse_oai_url


def check_missing_service_infos(cnx, service_infos, base_url):
    missing = {"level", "code", "eid", "title"}.difference(service_infos.keys())
    if missing:
        services_map = load_services_map(cnx)
        if "code" not in service_infos:
            return service_infos
        services_map = load_services_map(cnx)
        service_infos = service_infos_from_service_code(service_infos["code"], services_map)
    if "oai_url" not in service_infos:
        # "oai_url" may be set in case of tests
        service_infos["oai_url"] = base_url
    return service_infos


@log_in_db
def harvest_oai_nomina(
    cnx,
    url,
    service_infos,
    store=None,
    dry_run=False,
    records_limit=None,
    csv_rows_limit=100000,
    rqtask_eid=None,
    log=None,
):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param str url: repository URL
    :param dict service_infos: service information
    :param RQLObjectStore store: store
    :param bool dry_run: create entities in database
    :param int records_limit: only import limit documents number
    :param int csv_rows_limit: rows limit in the harvested csv file
    :param int rqtask_eid: RqTask eid
    :param Logger log: logger
    """
    if log is None:
        log = logging.getLogger("rq.task")
    if url is None:
        log.error("Harvesting aborted: OAI repository URL is not defined.")
        return
    base_url, params = parse_oai_url(url.strip())
    assert params.pop("verb") == "ListRecords", "import_oai only handles `ListRecords` verb"
    service_infos = check_missing_service_infos(cnx, service_infos, base_url)
    if "code" not in service_infos or not service_infos["code"]:
        missing = {"code", "eid"}.difference(service_infos.keys())
        log.error(
            """Harvesting aborted: no "{}" information found for service""".format(
                ", ".join(missing)
            )
        )
        return
    headers = {"User-Agent": get_user_agent()}
    log.info(f" Write {csv_rows_limit} rows per file.")

    max_retries = 2
    retry_delay = 1.0
    attempt = 0
    result = None

    while attempt <= max_retries:
        try:
            result = oai_nomina.OAINominaHarvester(cnx).harvest_records(
                service_infos,
                headers,
                records_limit=records_limit,
                csv_rows_limit=csv_rows_limit,
                **params,
            )
            break
        except OperationalError as e:
            attempt += 1
            error_msg = str(e)
            if (
                "server closed the connection" in error_msg
                or "connection already closed" in error_msg
            ):
                log.warning(
                    f"PostgreSQL connection error (attempt {attempt}/{max_retries + 1}): {e}. "
                    f"Reconnecting and retrying..."
                )
                if attempt <= max_retries:
                    try:
                        cnx.commit_and_restart()
                        log.info("Connection restarted successfully")
                    except Exception as restart_error:
                        log.error(f"Failed to restart connection: {restart_error}")
                        raise
                    time.sleep(retry_delay * attempt)
                    continue
                else:
                    log.error(f"PostgreSQL connection error after {max_retries + 1} attempts.")
                    raise
            else:
                raise

    return result


@log_in_db
def harvest_oai(
    cnx,
    url,
    oaitask_eid,
    service_infos,
    store=None,
    dry_run=False,
    records_limit=None,
    log=None,
):
    """Import data based on OAI-PMH.

    :param Connection cnx: database connection
    :param str url: repository URL
    :param str oaitask_eid: eid of the related OAIImportTask
    :param dict service_infos: service information
    :param RQLObjectStore store: store
    :param bool dry_run: create entities in database
    :param int records_limit: only import limit documents number
    :param Logger log: logger
    """
    if log is None:
        log = logging.getLogger("rq.task")
    if url is None:
        log.error("Harvesting aborted: OAI repository URL is not defined.")
        return
    base_url, params = parse_oai_url(url.strip())
    assert params.pop("verb") == "ListRecords", "import_oai only handles `ListRecords` verb"
    service_infos = check_missing_service_infos(cnx, service_infos, base_url)
    if "code" not in service_infos or not service_infos["code"]:
        missing = {"code", "eid"}.difference(service_infos.keys())
        log.error(
            """Harvesting aborted: no "{}" information found for service""".format(
                ", ".join(missing)
            )
        )
        return
    headers = {"User-Agent": get_user_agent()}

    prefix = params.get("metadataPrefix")
    if prefix in OAIPMH_EAD_PREFIXES:
        return oai_ead.OAIEADHarvester(cnx, service_infos, log).harvest_records(
            oaitask_eid,
            headers=headers,
            records_limit=records_limit,
            dry_run=dry_run,
            **params,
        )
    if prefix == "oai_dc":
        return oai_dc.OAIDCHarvester(cnx, service_infos, log=log).harvest_records(
            oaitask_eid,
            headers=headers,
            records_limit=records_limit,
            dry_run=dry_run,
            **params,
        )
    expected_perfixes = OAIPMH_EAD_PREFIXES + ("oai_dc",)
    log.error(
        f'"{prefix}" import is not available: ' f"must be one of {', '.join(expected_perfixes)}"
    )


def check_options(repo, url, ignore_last_import, dry_run, records_limit, from_date=None):
    msg = []
    if not ignore_last_import:
        if from_date:
            msg.append("Harvest data from the last import date {}".format(from_date))
        else:
            msg.append("Harvest all data: no last import date exists")
    else:
        msg.append("Harvest all data: ignore last import date")
    if dry_run:
        msg.append("Do not import harvested records.")
    else:
        msg.append("Import harvested records.")
    if records_limit is None:
        msg.append("Harvest the whole repository.")
    else:
        msg.append(f"Only harvest {records_limit} records.")
    return msg


def harvest_delta(
    cnx,
    repo_eid,
    ignore_last_import=False,
    dry_run=False,
    records_limit=None,
    csv_rows_limit=None,
    log=None,
    reraise=False,
    rqtask_eid=None,
):
    """OAI-PMH harvest data.

    :param Connection cnx: database connection
    :param int repo_eid: ID of an OAIRepository entity of interest
    :param bool ignore_last_import: toggle continuing from last successful
    :param bool dry_run: create or not harvested entities in DB
    :param int records_limit: records limit number to import
    :param int csv_rows_limit: rows limit in the harvested csv file (only for nomina)
    :param Logger log: logger
    :param bool reraise: toggle exception re-raising on/off
    :param int rqtask_eid: RqTask eid

    :raises Exception: if import_oai raises Exception and reraise=True
    """
    repo = cnx.entity_from_eid(repo_eid)
    url = repo.url
    if url is None:
        log.error("Harvesting aborted: OAI repository URL is not defined.")
        return
    if log is None:
        log = logging.getLogger("rq.task")
    if records_limit is not None and records_limit < 1:
        log.error((f"No record will be harvested: records_limit set to {records_limit}."))
        return []
    from_date = None
    if not ignore_last_import:
        _from = repo.last_successful_import
        if _from is not None:
            from_date = _from.strftime("%Y-%m-%d")
            url += f"&from={from_date}"
    msgs = check_options(repo, url, ignore_last_import, dry_run, records_limit, from_date)
    log.info("  ".join(msgs))
    kwargs = {"oai_repository": repo_eid}
    if rqtask_eid:
        # oaiimport_task relation do not exists in cubicweb_francearchives schema
        kwargs["reverse_oaiimport_task"] = rqtask_eid
    oaitask = cnx.create_entity("OAIImportTask", **kwargs)
    cnx.commit()
    base_url, params = parse_oai_url(url.strip())
    service_infos = service_infos_from_service_code(repo.service[0].code, load_services_map(cnx))
    service_infos = check_missing_service_infos(cnx, service_infos, base_url)
    if "code" not in service_infos or not service_infos["code"]:
        missing = {"code", "eid"}.difference(service_infos.keys())
        log.error(
            """Harvesting aborted: no "{}" information found for service""".format(
                ", ".join(missing)
            )
        )
        return
    kwargs = dict(
        service_infos=service_infos,
        dry_run=dry_run,
        records_limit=records_limit,
        log=log,
    )
    oai_prefix = params.get("metadataPrefix")
    if oai_prefix == "nomina":
        harvest_func = partial(harvest_oai_nomina, cnx, url, log=log)
        kwargs.update({"rqtask_eid": rqtask_eid, "csv_rows_limit": csv_rows_limit})
    else:
        harvest_func = partial(harvest_oai, cnx, url, oaitask.eid, log=log)
    results = None
    oaitask_failed = False
    try:
        results = harvest_func(**kwargs)
    except NoRecordsMatch as exception:
        message = "Finished with message {} for {}".format(exception, url)
        log.info(message)
    except OAIXMLError as error:
        oaitask_failed = True
        log.error(error)
    except Exception as error:
        oaitask_failed = True
        log.error(error, exc_info=True)
        log.error("Harvesting aborted.")
    wf = oaitask.cw_adapt_to("IWorkflowable")
    formatted_exc = None
    if oaitask_failed:
        wf.fire_transition("wft_faimport_fail", formatted_exc)
        if reraise:
            raise
    else:
        wf.fire_transition("wft_faimport_complete")
    cnx.commit()
    return results
