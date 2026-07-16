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

import re
import sys
import time
import logging
import string
import csv
import hashlib
import os.path as osp
import unicodedata
from datetime import datetime
from contextlib import contextmanager

from cubicweb_web.devtools.testlib import FakeRequest
from psycopg2.errorcodes import READ_ONLY_SQL_TRANSACTION

import sentry_sdk

from lxml import etree

from logilab.common.textutils import unormalize
from logilab.common.decorators import cachedproperty

from elasticsearch.exceptions import ConnectionTimeout, SerializationError, ConnectionError
from elasticsearch import helpers as es_helpers

from cubicweb import Binary
from cubicweb.dataimport.importer import ExtEntity, ExtEntitiesImporter

from cubicweb_francearchives import Authkey
from cubicweb_francearchives.entities import compute_file_data_hash
from cubicweb_francearchives.dataimport.meminfo import memprint
from cubicweb_francearchives.utils import remove_html_tags
from cubicweb_francearchives.utils import pick, TRANSMAP, NO_PUNCT_MAP

LOGGER = logging.getLogger()


RELFILES_DIR = "RELFILES"

OAIPMH_DC_PATH = "oaipmh/dc"
OAIPMH_EAD_PATH = "oaipmh/ead"
QUALITY_SERVICE_EID = -1
OAIPMH_EAD_PREFIXES = ("oai_ead", "ead")

logging.getLogger("ead.transform").setLevel(logging.CRITICAL)
logging.getLogger("glamconv.transform").setLevel(logging.CRITICAL)

INDEX_AUTHORITY_TYPE_MAP = {
    "persname": ("AgentName", "AgentAuthority"),
    "corpname": ("AgentName", "AgentAuthority"),
    "name": ("AgentName", "AgentAuthority"),
    "famname": ("AgentName", "AgentAuthority"),
    "geogname": ("Geogname", "LocationAuthority"),
    "subject": ("Subject", "SubjectAuthority"),
    "function": ("Subject", "SubjectAuthority"),
    "genreform": ("Subject", "SubjectAuthority"),
    "occupation": ("Subject", "SubjectAuthority"),
}


def get_oaipmh_ead_dirs(cnx, service_code):
    ead_services_dir = cnx.vreg.config["ead-services-dir"]
    return [ead_services_dir, service_code] + OAIPMH_EAD_PATH.split("/")


def get_oaipmh_dc_dirs(cnx, service_code):
    ead_services_dir = cnx.vreg.config["ead-services-dir"]
    return [ead_services_dir, service_code] + OAIPMH_DC_PATH.split("/")


def es_bulk_index(es, es_docs, max_retry=3, logger=None, **kwargs):
    if not logger:
        logger = LOGGER
    if not es:
        logger.error("Failed to index, could not connect to ES")
        return
    numtry = 0
    while numtry < max_retry:
        try:
            success, failed = es_helpers.bulk(es, es_docs, stats_only=True, **kwargs)
            if failed:
                # failed is number of errors if ``stats_only`` is set to ``True``
                # and list of errors otherwise
                logger.error("Failed to bulk %s document(s) in ES", failed)
        except (ConnectionTimeout, SerializationError, ConnectionError):
            logger.warning("failed to bulk index in ES, will retry in 0.5sec")
            numtry += 1
            time.sleep(0.5)
        else:
            break


def log_in_db(func):
    logger = logging.getLogger("francearchives.dataimport")

    def wrapped(cnx, *args, **kwargs):
        # cnx is an internal_cnx
        if isinstance(cnx, FakeRequest):
            # Skip logging for test
            return func(cnx, *args, **kwargs)
        log_cmd_in_db(cnx, func.__name__, logger)
        res = func(cnx, *args, **kwargs)
        log_cmd_in_db(cnx, func.__name__, logger, stop=True)
        return res

    return wrapped


def log_cmd_in_db(cnx, cmd_name, logger=None, stop=False):
    try:
        sqlcnx = cnx.repo.system_source.get_connection()
        crs = sqlcnx.cursor()
        if stop:
            crs.execute(
                "SELECT start FROM executed_command "
                "WHERE name=%(cmd_name)s "
                "ORDER BY start DESC",
                {"cmd_name": cmd_name},
            )
            start = crs.fetchone()
            if not start and logger:
                logger.warning('no command with name "%s" in db log' % cmd_name)
                return
            crs.execute(
                "UPDATE executed_command "
                "SET stop=%(stop)s, memory=%(mem)s "
                "WHERE name=%(cmdname)s AND start=%(start)s;",
                {
                    "stop": datetime.utcnow(),
                    "start": start[0],
                    "cmdname": cmd_name,
                    "mem": memprint(logger=logger),
                },
            )
        else:
            crs.execute(
                "INSERT INTO executed_command (name) " "VALUES (%(cmd_name)s);",
                {"cmd_name": cmd_name},
            )
        sqlcnx.commit()
    except Exception as error:
        if error.pgcode == READ_ONLY_SQL_TRANSACTION:
            if logger:
                logger.warning("can not insert log on command in a read-only db")
            return
        import traceback

        traceback.print_exc()
        if logger:
            logger.exception("error when inserting log on command")
        raise


def normalize_entry(entry):
    r"""
     - unaccent
     - replace punctuation by ' '
     - lower
     - remove mutiple whitespaces
    remove previously operations :
    1. do not remove dates between parentheses as it is too dangerous on agents
       entry = re.sub(r"\(\s*[\d.]+\s*-\s*[\d.]+\s*\)", "", entry)
    2. do not sort words as it is too dangerous on agents
       entry = " ".join(sorted(entry.split()))
    """
    if isinstance(entry, bytes):
        entry = entry.translate(" ", string.punctuation)
    else:
        entry = entry.translate(NO_PUNCT_MAP).translate(TRANSMAP)
    entry = entry.lower()
    return " ".join(entry.split())


def remove_extension(identifier):
    basename, ext = osp.splitext(identifier)
    if ext in {".pdf", ".csv", ".xml"}:
        return basename
    return identifier


def compute_ape_relpath(cnx, prefix, filepath_or_id, service_infos):
    if service_infos is None:
        service_map = load_services_map(cnx)
        service_infos = service_infos_from_filepath(filepath_or_id, service_map)
    basename = osp.basename(filepath_or_id)
    if not basename.endswith(".xml"):
        # can happen when basename comes from the <eadid> tag content
        basename += ".xml"
    publisher_code = service_infos.get("code") or default_service_name(basename)
    # XXX make sure to provide a different basename than the original EAD file
    # or else the importer will believe the file has already been imported.
    return f"{prefix}/{publisher_code}/ape-{basename}"


def unique_indices(entries, keys=("type", "normalized")):
    done = set()
    uniques = []
    for entry in entries:
        key = tuple(entry[k] for k in keys)
        if key not in done:
            done.add(key)
            uniques.append(entry)
    return uniques


class IndexImporterMixin(object):

    def __init__(self, *args, **kwargs):
        self.indices = {}
        self._current_service = None
        self.all_authorities = {}
        self.sames_as = set([])
        super(IndexImporterMixin, self).__init__(*args, **kwargs)

    @cachedproperty
    def concepts(self):
        return {
            label.lower(): eid
            for label, eid in self.store.rql(
                "Any LL, X WHERE X is Concept, L label_of X, L label LL"
            )
        }

    def _init_auth_history(self):
        self.auth_history = {}
        sql = self.store._cnx.system_sql
        cu = sql("select fa_stable_id, type, label, indexrole, autheid from authority_history")
        for fa_stable_id, type, label, indexrole, auth in cu.fetchall():
            key = Authkey(fa_stable_id, type, label, indexrole)
            self.auth_history[key.as_tuple()] = auth

    def _init_blacklisted_authorities(self):
        """for now all blacklisted authorities are Subjects"""
        self.blacklisted_authorities = []
        sql = self.store._cnx.system_sql
        cu = sql("select label from blacklisted_authorities")
        self.blacklisted_authorities = [e for e, in cu.fetchall()]

    def _init_unnormalized_authorities(self):
        """authorities that must not be normalized for alignment."""
        cu = self.store._cnx.system_sql("select label, autheid from unnormalized_authorities")
        self.unnormalized_authorities = {label: autheid for label, autheid in cu.fetchall()}
        # cache values
        self.unnormalized_authorities_eids = self.unnormalized_authorities.values()

    def global_authorities_rql_parts(self, auth_types):
        # return rqlquery with:
        # eid, label (normalized or not), etype, service_eid (0), sortorder
        #
        # 1. take grouping authorities eid with their grouped labels (sortorder 2)
        #
        # 2. take grouping authorities eid with their own labels (sortorder 1)
        #
        # 3. take selfstanding authorities with their own labels (sortorder 0)
        #
        # order is use to fill self.all_authorities and self.global_authorities dictionaries
        # so order 0 will be overwritten by order 1 and 2 and
        # in case of grouping and selfstanding authorities with a same label the
        # grouping one will finally be kept.
        #
        return " UNION ".join(
            """
                   (DISTINCT Any A, {{label}}, T, 0, 2 WHERE
                       GA is ET, ET name T,
                       A is {auth}, GA is {auth},
                       GA grouped_with A, GA label L)
                   UNION
                   (DISTINCT Any A, {{label}}, T, 0, 1 WHERE
                       A is ET, ET name T,
                       A is {auth},
                       GA grouped_with A, A label L)
                   UNION
                   (DISTINCT Any A, {{label}}, T, 0, 0 WHERE
                       A is ET, ET name T,
                       A is {auth},
                       NOT EXISTS(GA grouped_with A), NOT EXISTS(A grouped_with A2), A label L)
            """.format(
                auth=auth
            )
            for auth in auth_types
        )

    def _init_authorities(self):
        autodedupe_authorities = self.index_policy.get("autodedupe_authorities")
        self.log.debug("Start initiating authorities with index policy: %r", autodedupe_authorities)
        if not autodedupe_authorities:
            self.global_authorities = {}
            return
        global_or_service, should_normalize = autodedupe_authorities.split("/")
        assert global_or_service in ("global", "service")
        assert should_normalize in ("strict", "normalize")
        if should_normalize == "normalize":
            label = "NORMALIZE_ENTRY(L)"
        else:
            label = "L"
        if global_or_service == "global":
            # load all existing authorities
            auth_types = ("SubjectAuthority", "LocationAuthority", "AgentAuthority")
            rql = self.global_authorities_rql_parts(auth_types)
        else:
            # load all orphan authorities in order to try to recycle them. This data
            # will later be completed with the particular service related authorities in
            # update_authorities_cache method
            #
            auth_types = ("AgentAuthority", "LocationAuthority")
            # the first query is a built UNION instead of basic rql query like:
            #       Any A WHERE A is IN (AgentAuthority, LocationAuthority, SubjectAuthority), NOT
            #       EXISTS(I authority A)
            # because of bug in rql2sql (not so easy to reproduce in unit test)
            #
            # Authorities linked exclusively by :
            #  1. `related_authority` to "CommemorationItem", "ExternRef", "BaseContent"
            #  2. `same_as` to "AuthorityRecord", "ExternalUri", "ExternalId"
            #
            #  (e.g not linked by an Findingaid "NOT EXISTS(I authority A))
            # are included in the orphan resultset aswell
            #
            rql = " UNION ".join(
                '(Any A, {{label}}, "{0}", 0, 0 WHERE A is {0}, A label L, '
                "NOT EXISTS(I authority A), "
                "NOT EXISTS(A1 grouped_with A), NOT EXISTS(A grouped_with A2), "
                "A quality False"  # qualified authorities are processed as such
                ")".format(auth)
                for auth in auth_types
            )
            rql += " UNION " + "UNION ".join(
                '(Any A, {{label}}, "{0}", 0, 1 WHERE A is {0}, A label L, '
                "NOT EXISTS(I authority A), "
                "A1 grouped_with A, "
                "A quality False"  # qualified authorities are processed as such
                ")".format(auth)
                for auth in auth_types
            )
            # add grouped authorities targets with source authority's label
            rql += " UNION " + "UNION ".join(
                '(Any A, {{label}}, "{0}", 0, 2 WHERE A is {0}, GA label L, '
                "GA grouped_with A, "
                "NOT EXISTS(I authority A), "
                "A quality False"  # qualified authorities are processed as such
                ")".format(auth)
                for auth in auth_types
            )
            # add qualified (and not grouped) authorities: normally grouped
            # authorities are automatically dequalified in grouping
            rql += " UNION " + "UNION ".join(
                '(Any A, {{label}}, "{0}", {1}, 3 WHERE A is {0}, A label L, '
                "A quality True, "
                "NOT EXISTS(A grouped_with A1) "  # should not exist
                ")".format(auth, QUALITY_SERVICE_EID)
                for auth in auth_types
            )
            # add all SubjectAuthorities as they must always be treated globally (e.g #74018090)
            rql += " UNION  " + self.global_authorities_rql_parts(("SubjectAuthority",))
        rql = "DISTINCT Any A, L, T, S, O ORDERBY O WITH A, L, T, S, O BEING ({0})".format(rql)
        execute = self.store._cnx.execute
        # `all_authorities` is first initialized as global_authorities then we will call
        # `update_authorities_cache` to update `all_authorities`
        self.all_authorities = self.global_authorities = {
            hash((etype, label, service_eid)): eid
            for eid, label, etype, service_eid, order in execute(
                rql.format(label=label), build_descr=False
            )
        }
        self.log.debug(f"Found {len(self.all_authorities)} all_authorities")

    def update_authorities_cache(self, service_eid):
        """This will update `all_authorities` attribute.

        To perform this update we use authorities linked to service (one
        with `service_eid`) through FindingAid or through FAComponent via FindingAid

        Authorities linked exclusively by:
           1. `related_authority` to "CommemorationItem", "ExternRef", "BaseContent"
           2. `same_as` to "AuthorityRecord", "ExternalUri", "ExternalId"
        are already included in the self.all_authorities dictionary
        """
        if self._current_service == service_eid:
            return self.all_authorities
        self._current_service = service_eid
        autodedupe_authorities = self.index_policy.get("autodedupe_authorities")
        if not autodedupe_authorities:
            return
        global_or_service, should_normalize = autodedupe_authorities.split("/")
        if global_or_service == "global":
            return
        if should_normalize == "normalize":
            label = "NORMALIZE_ENTRY(a.cw_label)"
            a1label = "NORMALIZE_ENTRY(a1.cw_label)"
        else:
            label = "a.cw_label"
            a1label = "a1.cw_label"
        template = """
        SELECT DISTINCT a.cw_eid, {label}, '{etype}'
        FROM
          {authtable} a
          JOIN {indextable} it ON it.cw_authority = a.cw_eid
          JOIN index_relation i ON i.eid_from = it.cw_eid
          JOIN cw_findingaid fa ON fa.cw_eid = i.eid_to
        WHERE fa.cw_service = %(s)s
        UNION
        SELECT DISTINCT a.cw_eid, {label}, '{etype}'
        FROM
          {authtable} a
          JOIN {indextable} it ON it.cw_authority = a.cw_eid
          JOIN index_relation i ON i.eid_from = it.cw_eid
          JOIN cw_facomponent fac ON fac.cw_eid = i.eid_to
          JOIN cw_findingaid fa ON fa.cw_eid = fac.cw_finding_aid
        WHERE fa.cw_service = %(s)s
        UNION
        SELECT DISTINCT a.cw_eid, {a1label}, '{etype}'
        FROM
           {authtable} a
           JOIN grouped_with_relation ga ON a.cw_eid=ga.eid_to
           JOIN {authtable} a1 ON a1.cw_eid = ga.eid_from
           JOIN {indextable} it ON it.cw_authority = a.cw_eid
           JOIN index_relation i ON i.eid_from = it.cw_eid
           JOIN cw_findingaid fa ON fa.cw_eid = i.eid_to
        WHERE fa.cw_service = %(s)s
        UNION
        SELECT DISTINCT a.cw_eid, {a1label}, '{etype}'
        FROM
          {authtable} a
          JOIN grouped_with_relation ga ON a.cw_eid=ga.eid_to
          JOIN {authtable} a1 ON a1.cw_eid = ga.eid_from
          JOIN {indextable} it ON it.cw_authority = a.cw_eid
          JOIN index_relation i ON i.eid_from = it.cw_eid
          JOIN cw_facomponent fac ON fac.cw_eid = i.eid_to
          JOIN cw_findingaid fa ON fa.cw_eid = fac.cw_finding_aid
        WHERE fa.cw_service = %(s)s
         """
        # for now SubjectAuthorities are always treated globally (e.g #74018090)
        # and thus they are already present in self.all_authorities and self.global_authorities
        q = " union ".join(
            template.format(etype=e, authtable=at, indextable=it, label=label, a1label=a1label)
            for e, at, it in (
                ("LocationAuthority", "cw_locationauthority", "cw_geogname"),
                ("AgentAuthority", "cw_agentauthority", "cw_agentname"),
            )
        )
        self.all_authorities = self.global_authorities.copy()
        sql = self.store._cnx.system_sql
        self.log.debug(
            "Start fetching authorities for service with eid %s with index policy: %r",
            service_eid,
            autodedupe_authorities,
        )
        for autheid, authlabel, authtype in sql(q, {"s": service_eid}).fetchall():
            self.all_authorities[hash((authtype, authlabel, service_eid))] = autheid
        self.log.debug("End fetching authorities %s", service_eid)

    def create_authority(self, authtype, indextype, label, quality, service, hist_key):
        if hist_key.as_tuple() in self.auth_history:
            return self.auth_history[hist_key.as_tuple()]
        if label in self.unnormalized_authorities:
            return self.unnormalized_authorities[label]
        keys = self.build_authority_key(authtype, label, service)
        for key in keys:
            if key in self.all_authorities:
                eid = self.all_authorities[key]
                if eid not in self.unnormalized_authorities_eids:
                    return eid
        key = keys[0]  # preferred key is in first position
        self.all_authorities[key] = self.global_authorities[key] = auth = self.create_entity(
            authtype, {"label": label, "quality": quality}
        )["eid"]
        return auth

    def build_authority_key(self, authtype, label, service):
        autodedupe_authorities = self.index_policy.get("autodedupe_authorities")
        # always present quality labels firts
        if authtype == "SubjectAuthority":
            if not autodedupe_authorities or autodedupe_authorities.endswith("/strict"):
                keys = [(authtype, label, QUALITY_SERVICE_EID), (authtype, label, 0)]
            else:
                keys = [
                    (authtype, normalize_entry(label), QUALITY_SERVICE_EID),
                    (authtype, normalize_entry(label), 0),
                ]
        elif not autodedupe_authorities or autodedupe_authorities == "service/strict":
            keys = [
                (authtype, label, QUALITY_SERVICE_EID),
                (authtype, label, service),
                # in service case we should also try to align on orphan authorities
                (authtype, label, 0),
            ]
        elif autodedupe_authorities == "service/normalize":
            keys = [
                (authtype, normalize_entry(label), QUALITY_SERVICE_EID),
                (authtype, normalize_entry(label), service),
                # in service case we should also try to align on orphan authorities
                # and on SubjectAuthorities always imported globally
                (authtype, normalize_entry(label), 0),
            ]
        elif autodedupe_authorities == "global/normalize":
            keys = [
                (authtype, normalize_entry(label), QUALITY_SERVICE_EID),
                (authtype, normalize_entry(label), 0),
            ]
        elif autodedupe_authorities == "global/strict":
            keys = [(authtype, label, QUALITY_SERVICE_EID), (authtype, label, 0)]
        return [hash(key) for key in keys]

    def create_index(self, infos, target, fa_attrs):
        # key will be fields for Geogname, AgentName, Subject entities
        # and values are set of targets that will be index relations
        # if authority is blacklisted, do nothing
        indextype, authtype = INDEX_AUTHORITY_TYPE_MAP[infos["type"]]
        # if SubjectAuthority is blacklisted, do nothing
        if authtype == "SubjectAuthority" and infos["label"] in self.blacklisted_authorities:
            return
        key = Authkey(fa_attrs["stable_id"], infos["type"], infos["label"], infos["role"])
        sames_as = []
        # same_as
        authfilenumber = infos["authfilenumber"]
        if authfilenumber is not None:
            authrecord_eid = self.authority_records.get(authfilenumber)
            if authrecord_eid:
                sames_as.append(authrecord_eid)
        if infos["type"] in ("subject", "function", "occupation", "genreform"):
            concept = self.concepts.get(infos["label"].lower())
            if concept is not None:
                sames_as.append(concept)
        if key.as_tuple() not in self.indices:
            quality = bool(sames_as)
            autheid = self.create_authority(
                authtype,
                infos["type"],
                infos["label"],
                quality,
                fa_attrs.get("service"),
                hist_key=key,
            )
            attrs = dict(pick(infos, "role", "label", "authfilenumber"), authority=autheid)
            attrs["type"] = infos["type"]
            indexeid = self.create_entity(indextype, attrs)["eid"]
            self.indices[key.as_tuple()] = indexeid, autheid
        else:
            indexeid, autheid = self.indices[key.as_tuple()]
        self.add_rel(indexeid, "index", target)
        # same_as
        for entity_eid in sames_as:
            if (autheid, entity_eid) not in self.sames_as:
                self.add_rel(autheid, "same_as", entity_eid)
                self.sames_as.add((autheid, entity_eid))
        # add authority link to infos for elasticsearch
        infos["authority"] = autheid


def first(values):
    if values:
        return next(iter(values))
    return None


def int_or_none(value):
    if isinstance(value, int):
        return value
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    return None


def clean_row_dc_csv(row):
    for key, value in list(row.items()):
        if isinstance(value, bytes):
            row[key] = value.decode("utf-8")
        row[key] = row[key].strip()
        row[key.lower().strip()] = row.pop(key)
    for indextype in (
        "index_matiere",
        "index_collectivite",
        "index_personne",
        "index_lieu",
    ):
        row[indextype] = [s.strip() for s in re.split(INDEX_SEP_RE, row[indextype])]
    return row


class CSVIntegrityError(Exception):
    pass


INDEX_SEP_RE = re.compile(r";(?![^\(\)]*\))")


def load_metadata_file(read_func, metadata_filepath, csv_filename=None):
    """

    :read_func: read function for file
    :metadata_filepath: filepath to the file to read
    :csv_filename: csv filename

    expected columns are:
    ["identifiant_fichier", "titre", "origine", "date1" , "date2" , "description",
    "type",  # not used
     "format" ,"index_matiere", "index_lieu" , "index_personne" ,"index_collectivite",
    "langue", "conditions_acces", "conditions_utilisation", "source_complementaire",
    "identifiant_URI", "source_image"]
    """
    all_metadata = {}
    csv_empty_value = 'Missing required value for column "{col}", row "{row}"'
    csv_missing_col = 'The required column "{col}" is missing'
    wrong_idfile = 'The "{rn}" was not found in "identifiant_fichier" column of "{mf}"'
    mandatory_columns = ("identifiant_fichier", "titre")
    errors = []
    csv_filenames = []
    with read_func(metadata_filepath) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, 1):
            if i == 1:
                errors.extend(
                    [csv_missing_col.format(col=col) for col in mandatory_columns if col not in row]
                )
                if errors:
                    break
            # skip empty lignes
            if not any(row.values()):
                continue
            errors.extend(
                [
                    csv_empty_value.format(row=i, col=col)
                    for col in mandatory_columns
                    if not row[col]
                ]
            )
            csv_filenames.append(row["identifiant_fichier"].strip())
            if not errors:
                row = clean_row_dc_csv(row)
                # extension is not removed from 'identifiant_fichier' but
                # probaly should be as it is dont in default_csv_metadata
                all_metadata[row["identifiant_fichier"].strip()] = row
    if csv_filename and csv_filename not in csv_filenames:
        errors.append(wrong_idfile.format(mf=osp.basename(metadata_filepath), rn=csv_filename))
    if errors:
        raise CSVIntegrityError(" ;\n ".join(errors))
    return all_metadata


class FileExtEntity(ExtEntity):
    """Extend default ExtEntity class to bypass the auto-binary wrapping"""

    def prepare(self, *args, **kwargs):
        deferred = super(FileExtEntity, self).prepare(*args, **kwargs)
        # If we're using FileExtEntity, we don't want Binary instances, just
        # the plain string (which is supposed to a be a filepath)
        for key, value in list(self.values.items()):
            if isinstance(value, Binary):
                self.values[key] = value.getvalue()
        return deferred


class OptimizedExtEntitiesImporter(ExtEntitiesImporter):
    """'Optimized' (CPU-wise, not memory-wise) importer

    Default importer stores "non-ready" entites in a queue
    and loops on the queue each time a new entity is added
    to see if some entities in the loop might now be ready.

    In our case, this is not a good idea since we end up looping
    and looping over manif programs (or any other non-ready
    entity). Instead, just enqueue any non-ready entity and flush
    the queue at the end. This will lead to higher memory consumption
    but will be _a lot_ faster.
    """

    def iter_ext_entities(self, ext_entities, deferred, queue):
        """override default importer method to process queue
        once and for all at the end
        """
        schema = self.schema
        extid2eid = self.extid2eid
        for ext_entity in ext_entities:
            # check data in the transitional representation and prepare it
            # for later insertion in the database
            for subj_uri, rtype, obj_uri in ext_entity.prepare(schema):
                deferred.setdefault(rtype, set()).add((subj_uri, obj_uri))
            if not ext_entity.is_ready(extid2eid):
                queue.setdefault(ext_entity.etype, []).append(ext_entity)
                continue
            yield ext_entity
        # all ready entities have been imported, now flush the queue
        for ext_entity in self.process_deferred_queue(queue):
            yield ext_entity

    def process_deferred_queue(self, queue):
        extid2eid = self.extid2eid
        order_hint = list(self.etypes_order_hint)
        # check for some entities in the queue that may now be ready. We'll have to restart
        # search for ready entities until no one is generated
        for etype in queue:
            if etype not in order_hint:
                order_hint.append(etype)
        new = True
        while new:
            new = False
            for etype in order_hint:
                if etype in queue:
                    new_queue = []
                    for ext_entity in queue[etype]:
                        if ext_entity.is_ready(extid2eid):
                            yield ext_entity
                            # may unlock entity previously handled within this loop
                            new = True
                        else:
                            new_queue.append(ext_entity)
                    if new_queue:
                        queue[etype][:] = new_queue
                    else:
                        del queue[etype]


class ExtentityWithIndexImporter(IndexImporterMixin, OptimizedExtEntitiesImporter):
    """add Index optimization"""

    def __init__(
        self,
        schema,
        store,
        extid2eid=None,
        existing_relations=None,
        etypes_order_hint=(),
        import_log=None,
        raise_on_error=False,
        index_policy=None,
        log=None,
    ):
        if log is None:
            log = LOGGER
        self.log = log
        self.index_policy = index_policy
        # XXX, redundant with ExtEntitiesImporter's __init__ but required by
        # `_init_authorities()`
        self.store = store
        self._init_authorities()
        self._init_blacklisted_authorities()
        self._init_unnormalized_authorities()
        self._init_auth_history()
        if extid2eid is None:
            extid2eid = {}
        super(ExtentityWithIndexImporter, self).__init__(
            schema,
            store,
            extid2eid,
            existing_relations,
            etypes_order_hint,
            import_log,
            raise_on_error,
        )
        service_extids = [v for k, v in list(extid2eid.items()) if k.startswith("service-")]
        service_eid = None
        if service_extids:
            service_eid = service_extids.pop()
        self.update_authorities_cache(service_eid)
        extid2eid.update(self.all_authorities)


@contextmanager
def sqlcursor(cnx, logger=LOGGER):
    try:
        yield cnx.cnxset.cu
    except Exception:
        logger.exception("SQL execution failed")
        cnx.rollback()
    else:
        cnx.commit()


def execute_sqlscript(cnx, script_path):
    with open(script_path) as f:
        sql = f.read()
    with sqlcursor(cnx) as crs:
        crs.execute(sql)


def strip_html(html):
    """Strip HTML tags from string"""
    if html is None:
        return None
    try:
        # Etree does not like HTML without a single root element
        # so we need to wrap it inside a div.
        tree = etree.fromstring("<div>{}</div>".format(html))
    except etree.XMLSyntaxError:
        return html.strip()
    return " ".join(tree.xpath("//text()")).strip()


def strip_nones(props, defaults=None):
    """Strip None or empty strings.

    :param dict props: map to clean up
    :param dict defaults: values to replace None or empty strings by
    """
    if defaults is None:
        defaults = {}
    for key, value in list(props.items()):
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        if value is not None and isinstance(value, str):
            value = value.strip() if value else None
            if not value:
                value = None
            if value is not None and not remove_html_tags(value).strip():
                value = None
        if value is None:
            if key in defaults:
                props[key] = defaults[key]
            else:
                del props[key]
    return props


def clean_values(values):
    """clean `values` attributes dict
    - convert str to unicode
    - ignore None attributes
    """
    formatted = {}
    for key, value in list(values.items()):
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        formatted[key] = value
    return strip_nones(formatted)


def usha1(content):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return compute_file_data_hash(content)


def default_csv_metadata(title):
    return {
        "identifiant_fichier": title,  # ead
        "titre": remove_extension(title),
        "origine": default_service_name(title),
        "date1": None,
        "date2": None,
        "description": None,
        "type": None,
        "format": None,
        "index_matiere": None,
        "index_lieu": None,
        "index_personne": None,
        "index_collectivite": None,
        "langue": None,
        "conditions_acces": None,
        "conditions_utilisation": None,
        "source_complementaire": None,
        "identifiant_uri": None,  # dao
        "source_image": None,
    }


def component_stable_id_for_dc(identifier, fa_stable_id):
    if isinstance(identifier, str):
        identifier = identifier.encode("utf-8")
    if isinstance(fa_stable_id, str):
        fa_stable_id = fa_stable_id.encode("utf-8")
    return hashlib.sha1(fa_stable_id + identifier).hexdigest()


PUNCTUATION = "".join([s for s in string.punctuation if s != "-"]) + string.whitespace


def normalize_for_filepath(data):
    """Clean up data to create a filename.

    :param str data: data

    :returns: cleaned-up data
    (replace punctuation and whitespace with "_" and remove non-ASCII)
    :rtype: str
    """
    if not data or not data.strip():
        return ""
    data = data.strip()
    data = "".join(char if char not in PUNCTUATION else "_" for char in data)
    return unormalize(data, substitute="_")


class InvalidFindingAid(Exception):
    """raised when finding aid is invalid (e.g. required elements missing)"""


def cleanup_ns(tree, ns=None):
    """hack: remove default NS.

    Some EAD files use the 'urn:isbn:1-931666-22-9' namesapce, some don't.
    To ease XML processing, remove it to access nodes using unqualified
    names in all cases.
    """
    if hasattr(tree, "getroot"):
        root = tree.getroot()
    else:
        root = tree
    if ns in root.nsmap:
        for elt in root.getiterator():
            if not hasattr(elt.tag, "find"):
                continue
            ns_idx = elt.tag.find("}")
            if ns_idx > 0:
                elt.tag = elt.tag[ns_idx + 1 :]
    return root


def to_unicode(obj):
    """Turn some object (usually an exception) to unicode"""
    try:
        # The exception message might already be a unicode string.
        return str(obj)
    except UnicodeDecodeError:
        return bytes(obj).decode(sys.getdefaultencoding(), "ignore")


def decode_filepath(filepath):
    if isinstance(filepath, str):
        return filepath
    try:
        return filepath.decode("utf-8")
    except UnicodeDecodeError:
        return filepath.decode("iso-8859-15")


class FakeQueue(list):
    def get(self, *args):
        return self.pop(*args)


def init_sentry_client(config):
    sentry_dsn = config.get("sentry-dsn")
    if sentry_dsn:
        sentry_sdk.init(dsn=sentry_dsn)


def capture_exception(exc, filepath):
    with sentry_sdk.push_scope() as scope:
        scope.set_extra("filepath", filepath)
        ident = sentry_sdk.capture_exception(exc)
        if ident:
            LOGGER.error("Exception caught; reference is %s", ident)


def load_services_map(cnx):
    services = {}
    rset = cnx.execute(
        """Any X, C, N, N2, SN, L, IP, IS WHERE X is Service,
        X code C, X name N, X name2 N2, X short_name SN,
        X level L, X iiif_ead_policy IP, X iiif_extptr IS"""
    )
    for service in rset.entities():
        code = service.code
        if code is not None:
            code = code.upper()
        services[code] = service
    return services


def service_infos_from_filepath(filepath, services_map):
    if isinstance(filepath, bytes):
        filepath = filepath.decode("utf-8")
    filename = osp.basename(filepath)
    infos = None
    for service_code, service in services_map.items():
        if filename.upper().startswith("{}_".format(service_code)):
            infos = {
                "code": service_code,
                "name": service.publisher(),
                "title": service.dc_title(),
                "level": service.level,
                "eid": service.eid,
                "iiif_ead_policy": service.save_iiif_ead_policy,
            }
            break
    if infos is None:
        service_code = default_service_name(filename).upper()
        infos = {
            "code": service_code,
            "name": service_code,
            "title": service_code,
            "level": None,
            "eid": None,
            "iiif_ead_policy": None,
        }
    return infos


def service_infos_from_service_code(service_code, services_map):
    service = services_map.get(service_code)
    if service:
        return {
            "code": service_code,
            "name": service.publisher(),
            "title": service.dc_title(),
            "level": service.level,
            "eid": service.eid,
            "iiif_ead_policy": service.save_iiif_ead_policy,
        }
    return {
        "code": service_code,
        "name": service_code,
        "title": service_code,
        "level": None,
        "eid": None,
        "iiif_ead_policy": None,
    }


def default_service_name(name):
    """
    Retrive a default service code for a string (may be a filepath or an eadid).
    This function is used if no existing service for filepath is found.

    Although `service_code` may contain _ (e.g FR_920509801), we stll
    take the first split on `_` result as `service_code` as we have no better solution.

    Normaly, this should not happen as a service code is always provided in import
    or computed by `service_infos_from_filepath` method.
    """
    if isinstance(name, bytes):
        name = name.decode("utf-8")
    return name.split("_", 1)[0]


def clean(*labels):
    """Clean label(s).

    :returns: cleaned label(s)
    :rtype: str
    """
    # substitute \t\n\r and consecutive whitespaces by single whitespace
    # remove leading and/or trailing whitespaces
    whitespace = re.compile(r"[ \t\n\r]+")
    for label in labels:
        label = whitespace.sub(" ", label).strip()
        label = "".join(char for char in label if not unicodedata.category(char).startswith("C"))
        yield (label)


YEAR_RGX = [
    re.compile(
        r"""
        ^\s*(?P<year>\d{2,4})/\d{1,2}/\d{1,2}\s*$""",
        re.X,
    ),
    re.compile(
        r"""
        ^\s*(?P<year>\d{2,4})-\d{1,2}-\d{1,2}\s*$""",
        re.X,
    ),
    re.compile(
        r"^\s*(?P<start>\d{2,4})/\d{1,2}/\d{1,2}\s*$",
        re.X,
    ),
    re.compile(r"^\s*(?P<year>\d{2,4})\s*$"),
]


def get_year(date):
    """Extract a year from string representing a date

    Known formats are:
     - yyyy-mm-dd
     - yyyy/mm/dd
     - yyyy
    """
    if not date:
        return
    for rgx in YEAR_RGX:
        match = rgx.match(date)
        if match:
            return match.group("year")


def get_date(start, stop):
    chunks = []
    if start:
        chunks.append(start)
    if stop and stop != start:
        chunks.append(stop)
    if chunks:
        return " - ".join(chunks)
    return None


YEAR_RANGE_RGX = [
    re.compile(
        r"""
        ^\s*(?P<start>\d{2,4})/\d{1,2}/\d{1,2}\s*-
        \s*(?P<stop>\d{2,4})/\d{1,2}/\d{1,2}\s*$""",
        re.X,
    ),
    re.compile(
        r"""
        ^\s*(?P<start>\d{2,4})-\d{1,2}-\d{1,2}\s*/
        \s*(?P<stop>\d{2,4})-\d{1,2}-\d{1,2}\s*$""",
        re.X,
    ),
    re.compile(
        r"""
        ^\s*(?P<start>\d{2,4})-\d{1,2}\s*[/-]\s*
        (?P<stop>\d{2,4})-\d{1,2}\s*$""",
        re.X,
    ),
    re.compile(r"^\s*(?P<start>\d{2,4})\s*[/-]\s*(?P<stop>\d{2,4})\s*$"),
    re.compile(
        r"^\s*(?P<start>\d{2,4})-\d{1,2}-\d{1,2}\s*$",
        re.X,
    ),
    re.compile(
        r"^\s*(?P<start>\d{2,4})/\d{1,2}/\d{1,2}\s*$",
        re.X,
    ),
    re.compile(r"^\s*(?P<start>\d{2,4})\s*$"),
]


def parse_normalized_daterange(value):
    """try to guess {start, stop} date range from a unitdate label

    Known formats are:
        - yyyy-mm-dd / yyyy-dd-dd
        - yyyy/mm/dd - yyyy/mm/dd
        - yyyy-mm / yyyy-mm (with / or - separator)
        - yyyy - yyyy
        - yyyy-mm-dd
        - yyyy/mm/dd
        - yyyy

    If ``start`` is greater than ``stop``, ``stop`` gets lowered back
    to ``start``.

    If ``start`` or ``stop`` are greater than 2100, they are ignored.
    If ``stop`` is not defined, it defaults to ``start``.
    Returns:
        - None if nothing could be parsed
        - {'start', 'stop'} mapping on success
    """
    start = stop = None
    if value is not None:
        for rgx in YEAR_RANGE_RGX:
            match = rgx.match(value)
            if match is not None:
                start = int(match.group("start"))
                if "stop" in match.groupdict():
                    stop = int(match.group("stop"))
                if start and start > 2100:
                    start = None
                if stop and stop > 2100:
                    stop = None
                if start and stop and start > stop:
                    stop = None
                stop = start if stop is None else stop
                if start and stop:
                    return {"start": start, "stop": stop}
    return None


def parse_unitdate(date_info):
    """
    Parse date related infos

    :param dict date_info: {"text": data, "normal": date ISO}
    """
    infos = {
        "date": None,
        "start": None,
        "stop": None,
    }
    text = date_info.get("text")
    if text:
        text = text.strip()
        infos["date"] = text
        for datelabel in (date_info.get("normal"), text):
            year_range = parse_normalized_daterange(datelabel)
            if year_range is not None:
                infos.update(year_range)
                break
    return infos
