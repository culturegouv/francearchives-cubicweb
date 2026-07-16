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
"""cubicweb-francearchives application package

FranceArchives
"""
import os
import os.path as osp
import stat
from sched import scheduler

import psycopg2

from pyramid.settings import asbool

from logilab.common.decorators import monkeypatch
from logilab.common.registry import objectify_predicate

from cubicweb.__pkginfo__ import numversion as cwversion
from cubicweb.cwctl import init_cmdline_log_threshold
from cubicweb.cwconfig import CubicWebConfiguration
from cubicweb.entity import Entity, TransformData, ENGINE
from cubicweb.server.repository import Repository
from cubicweb.server.sources import storages
from cubicweb import repoapi

# MONKEYPATCH for db-create
from cubicweb.server.serverctl import CreateInstanceDBCommand
from cubicweb.server.serverctl import (
    check_options_consistency,
    get_db_helper,
    ASK,
    underline_title,
    _db_sys_cnx,
    CWCTL,
    createdb,
    source_cnx,
)

from cubicweb_francearchives.__pkginfo__ import numversion as faversion

from cubicweb_elasticsearch import es

from cubicweb_francearchives.htmlutils import soup2xhtml

from cubicweb_s3storage.storages import S3Storage, S3DeleteFileOp

# make sure psycopg2 always return unicode strings,
# cf. http://initd.org/psycopg/docs/faq.html#faq-unicode
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

GLOSSARY_CACHE = []

SECTIONS = {"gerer": None}

STATIC_CSS_DIRECTORY = "css"

S3_ACTIVE = bool(os.getenv("AWS_S3_BUCKET_NAME"))

POSTGRESQL_SUPERUSER = bool(int(os.getenv("CW_POSTGRESQL_SUPERUSER", 0)))
SITE_TYPE = os.getenv("CW_SITE_TYPE", "development")

FEATURE_ADVANCED_SEARCH = bool(int(os.getenv("FEATURE_ADVANCED_SEARCH", 0)))
FEATURE_SPARQL = bool(int(os.getenv("FEATURE_SPARQL", 0)))
FEATURE_SPARQL_ACCESSIBLE = bool(int(os.getenv("FEATURE_SPARQL_ACCESSIBLE", 0)))

FEATURE_CHATBOT_SECTIONS = os.getenv("FEATURE_CHATBOT_SECTIONS", "").split(",")

IIIF_MANIFEST_ROLE = "iiif_manifest"
SIAF_CODE = "FRSIAF"
SIAF_AGENTS_REF_CODE = "RIPA"


@objectify_predicate
def display_advanced_search_predicate(cls, req, rset, row=0, col=0, **kwargs):
    return FEATURE_ADVANCED_SEARCH


def get_user_agent():
    def format_version(numversion):
        return ".".join(str(i) for i in numversion)

    user_agent = (
        "FranceArchives/{faversion} (francearchives.siaf@culture.gouv.fr) CubicWeb/{cwversion}"
    )
    return user_agent.format(
        faversion=format_version(faversion), cwversion=format_version(cwversion)
    )


# safety belt to register a custom, hard-coded list of indexable types to avoid
# indexing Files, EmailAddress (or any unwanted entity type) by mistake

es.INDEXABLE_TYPES = [
    "Section",
    "CommemorationItem",
    "BaseContent",
    "Card",
    "NewsContent",
    "Circular",
    "Service",
    "Map",
    "ExternRef",
    "FindingAid",
    "FAComponent",
    "File",
    "BaseContentTranslation",
    "SectionTranslation",
    "CommemorationItemTranslation",
    "AuthorityRecord",
]

NOMINA_INDEXABLE_ETYPES = ("NominaRecord",)
AGENTS_REFERENCE_INDEXABLE_ETYPES = ("AgentRecord",)


SUPPORTED_LANGS = ("fr", "en", "de", "es")

SOCIAL_NETWORK_LIST = (
    "facebook",
    "twitter",
    "storify",
    "flickr",
    "wikimedia",
    "rss",
    "dailymotion",
    "blog",
    "pinterest",
    "foursquare",
    "scoop it",
    "vimeo",
    "youtube",
    "instagram",
)

CMS_OBJECTS = (
    "Section",
    "BaseContent",
    "NewsContent",
    "Circular",
    "CommemorationItem",
    "ExternRef",
    "Map",
)

ES_CMS_I18N_OBJECTS = (
    "SectionTranslation",
    "BaseContentTranslation",
    "CommemorationItemTranslation",
)

CMS_I18N_OBJECTS = ES_CMS_I18N_OBJECTS + ("FaqItemTranslation",)

FIRST_LEVEL_SECTIONS = {"rechercher", "decouvrir", "comprendre", "gerer"}


INDEX_ETYPE_2_URLSEGMENT = {
    "LocationAuthority": "location",
    "SubjectAuthority": "subject",
    "AgentAuthority": "agent",
}


class Authkey(object):
    def __init__(self, fa_stable_id, type, label, role):
        self.fa_stable_id = fa_stable_id
        self.type = type
        self.label = label
        self.role = role

    def as_tuple(self):
        return (self.fa_stable_id, self.type, self.label, self.role)


def register_auth_history(cnx, key, autheid):
    """make sure all of fa_stable_id, type, label, indexrole values are different
    from NONE, otherwise the ON CONFLICT statement does not work (SQL may be
    testing NULL = NULL instead of NULL is NULL)
    """
    cnx.system_sql(
        "INSERT INTO authority_history (fa_stable_id, type, label, indexrole, autheid) VALUES "
        "(%(fa)s, %(type)s, %(l)s, %(role)s, %(a)s) "
        "ON CONFLICT (fa_stable_id, type, label, indexrole) DO UPDATE SET autheid = EXCLUDED.autheid",  # noqa
        {
            "fa": key.fa_stable_id,
            "type": key.type,
            "l": key.label,
            "role": key.role or "index",
            "a": autheid,
        },
    )


class FABfssStorage(storages.BytesFileSystemStorage):
    wmode = stat.S_IRUSR | stat.S_IWUSR

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("wmode", self.wmode)
        super(FABfssStorage, self).__init__(*args, **kwargs)

    def new_fs_path(self, entity, attr):
        relpath = entity.bfss_storage_relpath(attr)
        fspath = osp.join(self.default_directory, relpath)
        destdir = osp.dirname(fspath)
        # XXX handle broken symlinks ? race conditions ?
        if not osp.isdir(destdir):
            os.makedirs(destdir)
        if osp.isfile(fspath):
            flags = os.O_RDWR | os.O_TRUNC | os.O_NOFOLLOW
        else:
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        fd = os.open(fspath, flags, self.wmode)
        return fd, fspath

    def entity_deleted(self, entity, attr):
        """an entity using this storage for attr has been deleted.
        Francearchives customization:
          while deleting a CWFile, only delete the referenced file from FS
          if there is no other CWFile referencing the same filepath (e.g same cw_data)
        """
        fpath = self.current_fs_path(entity, attr)
        if fpath is not None:
            sys_source = entity._cw.repo.system_source
            sql_query = """
            SELECT count(f.cw_eid) FROM cw_file f
            JOIN cw_file f1 ON f.cw_{attr}=f1.cw_{attr}
            WHERE f1.cw_eid =%(eid)s
                  AND f.cw_eid!=%(eid)s;
            """.format(
                attr=attr
            )
            attrs = {"eid": entity.eid}
            cu = sys_source.doexec(entity._cw, sql_query, attrs)
            res = cu.fetchone()[0]
            # only delete the file if there is no more cw_files referencing the same
            # fspath
            if not res:
                storages.DeleteFileOp.get_instance(entity._cw).add_data(fpath)


class FranceArchivesS3Storage(S3Storage):
    def __init__(self, bucket, suffix=".tmp", import_prefix=""):
        # TODO S3 add `import_prefix="import/"` to handle failed imports
        # If an import fails:
        #     all `import_prefixed` files must be removed.
        # If an import succeeds:
        #     all `import_prefixed` files must be renamed into
        #     files without the prefix
        # Note: with FABfssStorage those cases are not handled
        super(FranceArchivesS3Storage, self).__init__(bucket, suffix=suffix)
        self.import_prefix = import_prefix

    def ensure_key(self, s3key):
        """
        Ensure s3key only contains authorized characters and does not start with "/"
        """
        # TODO
        s3key = s3key.lstrip("/")
        return s3key

    def new_s3_key(self, entity, attr):
        return self.ensure_key(self.compute_new_s3_key(entity, attr))

    def compute_new_s3_key(self, entity, attr):
        if entity.title:
            # TODO replace this quick and dirty fix
            if entity.title.startswith("static/css"):
                return entity.title
        return f"{entity.data_hash}_{entity.data_name}"

    def get_upload_extra_args(self, _entity, _attr, _key):
        """This code is a copy from cubiweb_s3storage
        and must be removed after
        - https://forge.extranet.logilab.fr/cubicweb/cubes/s3storage/-/issues/5
        is resolved (1.0.3)
        """

        if _entity.data_format:
            return {"ContentType": _entity.data_format}

    def entity_deleted(self, entity, attr):
        """an entity using this storage for attr has been deleted.
        Francearchives customization:
          while deleting a CWFile, only delete the referenced file from FS
          if there is no other CWFile referencing the same fkey (e.g same cw_data)
        """
        key = self.get_s3_key(entity, attr)
        if key is not None:
            sys_source = entity._cw.repo.system_source
            sql_query = """
            SELECT count(f.cw_eid) FROM cw_file f
            JOIN cw_file f1 ON f.cw_{attr}=f1.cw_{attr}
            WHERE f1.cw_eid =%(eid)s
                  AND f.cw_eid!=%(eid)s;
            """.format(
                attr=attr
            )
            attrs = {"eid": entity.eid}
            cu = sys_source.doexec(entity._cw, sql_query, attrs)
            res = cu.fetchone()[0]
            # only delete the file if there is no more cw_files referencing the same
            # fspath
            if not res:
                S3DeleteFileOp.get_instance(entity._cw).add_data((self, key, entity.eid, attr))

    def file_exists(self, key):
        """
        Check if file exists using HEAD s3 command
        """
        from botocore.exceptions import ClientError

        if isinstance(key, bytes):
            key = key.decode("utf-8")
        try:
            head = self.s3cnx.head_object(Key=key, Bucket=self.bucket)
            return head["ResponseMetadata"].get("HTTPStatusCode") == 200
        except ClientError:
            # print(f"[file_exists]: no {key} key found in bucket: {err}")
            return False

    def rename_object(self, old_s3_key, new_s3_key):
        """
        Rename an object

        :old_s3_key: the key to rename from
        :new_s3_key: the key to rename to
        """
        self.s3cnx.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": old_s3_key},
            Key=new_s3_key,
        )
        self.s3cnx.delete_object(Bucket=self.bucket, Key=old_s3_key)
        self.info(f"Renamed {old_s3_key} into {new_s3_key}")

    def import_prefixed_key(self, key):
        return self.import_prefix + key

    def temporary_import_upload(self, binary, key, **extra_args):
        """
        Create temporary files during import
        """
        prefixed_key = self.import_prefixed_key(key)
        self.s3cnx.upload_fileobj(binary, self.bucket, prefixed_key, ExtraArgs=extra_args)

    def temporary_import_copy(self, from_key, to_key):
        """
        Copy temporary files during import
        """
        to_prefixed_key = self.import_prefixed_key(to_key)
        from_prefixed_key = self.import_prefixed_key(from_key)
        self.s3cnx.copy_object(
            Bucket=self.bucket,
            CopySource={"Bucket": self.bucket, "Key": from_prefixed_key},
            Key=to_prefixed_key,
        )


def admincnx(appid, loglevel=None):
    config = CubicWebConfiguration.config_for(appid)
    config["connections-pool-min-size"] = 2

    login = config.default_admin_config["login"]
    password = config.default_admin_config["password"]

    if loglevel is not None:
        init_cmdline_log_threshold(config, loglevel)

    repo = Repository(config, scheduler=scheduler())
    repo.bootstrap()
    return repoapi.connect(repo, login, password=password)


def init_bfss(repo):
    # TODO - remove this bottlekneck code call everywhere else
    if S3_ACTIVE:
        storage = FranceArchivesS3Storage(os.getenv("AWS_S3_BUCKET_NAME"))
    else:
        bfssdir = repo.config["appfiles-dir"]
        if not osp.exists(bfssdir):
            os.makedirs(bfssdir)
            print("created {}".format(bfssdir))
        storage = FABfssStorage(bfssdir)
    storages.set_attribute_storage(repo, "File", "data", storage)


def static_css_dir(static_directory):
    if S3_ACTIVE:
        return "/".join((osp.basename(static_directory), STATIC_CSS_DIRECTORY))
    else:
        return osp.join(static_directory, STATIC_CSS_DIRECTORY)


def check_static_css_dir(repo):
    if repo.config.name != "all-in-one":
        return
    directory = static_css_dir(repo.config.static_directory)
    if not S3_ACTIVE:
        if not osp.isdir(directory):
            repo.critical(
                "static css files directory {} does not exist. Trying to create it".format(
                    directory
                )
            )
            try:
                os.makedirs(directory)
            except Exception:
                repo.critical("could not create static css files directory {}".format(directory))
                raise
        if not os.access(directory, os.W_OK):
            raise ValueError('static css directory "{}" is not writable'.format(directory))


def includeme(config):
    if asbool(config.registry.settings.get("francearchives.autoinclude", True)):
        config.include(".pviews")
        config.include(".pviews.catch_all")


@monkeypatch(Entity)
def _cw_mtc_transform(self, data, format, target_format, encoding, _engine=ENGINE):
    trdata = TransformData(data, format, encoding, appobject=self)
    data = _engine.convert(trdata, target_format).decode()
    if target_format == "text/html":
        data = soup2xhtml(data, self._cw.encoding)
    return data


# patch from https://forge.extranet.logilab.fr/cubicweb/cubicweb/-/merge_requests/196/commits
# TODO remove when migrating to 3.31.x
# related issue : https://forge.extranet.logilab.fr/cubicweb/cubicweb/-/issues/296
@monkeypatch(CreateInstanceDBCommand)
def run(self, args):
    """run the command with its specific arguments"""
    check_options_consistency(self.config)
    automatic = self.get("automatic")
    drop_db = self.get("drop")
    appid = args.pop()
    config = CubicWebConfiguration.config_for(appid)
    source = config.system_source_config
    dbname = source["db-name"]
    driver = source["db-driver"]
    helper = get_db_helper(driver)

    def should_drop_db():
        """Return True if the database should be dropped.

        The logic is following:
            - if drop_db is set then respect the user choice (either True or False)
            - if drop_db is not set then drop only in non automatic mode and
                the user confirm the deletion
        """
        if drop_db is not None:
            return drop_db
        if automatic:
            return False
        drop_db_question = "Database %s already exists. Drop it?" % dbname
        return ASK.confirm(drop_db_question)

    if driver == "sqlite":
        if os.path.exists(dbname) and should_drop_db():
            os.unlink(dbname)
    elif self.config.create_db:
        print("\n" + underline_title("Creating the system database"))
        # connect on the dbms system base to create our base
        dbcnx = _db_sys_cnx(source, "CREATE/DROP DATABASE and / or USER", interactive=not automatic)
        cursor = dbcnx.cursor()
        try:
            if helper.users_support:
                user = source["db-user"]
                if not helper.user_exists(cursor, user) and (
                    automatic or ASK.confirm("Create db user %s ?" % user, default_is_yes=False)
                ):
                    helper.create_user(source["db-user"], source.get("db-password"))
                    print("-> user %s created." % user)
            if dbname in helper.list_databases(cursor):
                if should_drop_db():
                    cursor.execute('DROP DATABASE "%s"' % dbname)
                else:
                    print(
                        "The database %s already exists, but automatically dropping it "
                        "is currently forbidden. You may want to run "
                        '"cubicweb-ctl db-create --drop=y %s" to continue or '
                        '"cubicweb-ctl db-create --help" to get help.' % (dbname, config.appid)
                    )
                    raise Exception("Not allowed to drop existing database.")
            createdb(helper, source, dbcnx, cursor)
            dbcnx.commit()
            print("-> database %s created." % dbname)
        except BaseException:
            dbcnx.rollback()
            raise
    cnx = source_cnx(source, special_privs="CREATE LANGUAGE/SCHEMA", interactive=not automatic)
    cursor = cnx.cursor()
    helper.init_fti_extensions(cursor)
    namespace = source.get("db-namespace")
    if namespace and (
        automatic or ASK.confirm("Create schema %s in database %s ?" % (namespace, dbname))
    ):
        helper.create_schema(cursor, namespace)
    cnx.commit()
    # postgres specific stuff
    if driver == "postgres":
        # install plpgsql language
        langs = ("plpgsql",)
        for extlang in langs:
            if automatic or ASK.confirm("Create language %s ?" % extlang):
                try:
                    helper.create_language(cursor, extlang)
                except Exception as exc:
                    print("-> ERROR:", exc)
                    print(
                        "-> could not create language %s, "
                        "some stored procedures might be unusable" % extlang
                    )
                    cnx.rollback()
                else:
                    cnx.commit()
    print("-> database for instance %s created and necessary extensions installed." % appid)
    print()
    if automatic:
        CWCTL.run(["db-init", "--automatic", "--config-level", "0", config.appid])
    elif ASK.confirm("Run db-init to initialize the system database ?"):
        CWCTL.run(["db-init", "--config-level", str(self.config.config_level), config.appid])
    else:
        print("-> nevermind, you can do it later with " '"cubicweb-ctl db-init %s".' % config.appid)


def create_homepage_metadata(cnx):
    cnx.create_entity(
        "Metadata",
        uuid="metadata-homepage",
        title="FranceArchives.fr",
        description="Portail National des Archives de France",
        type="website",
    )


class ColoredLogsMixIn:
    failed_mark = "\033[91m" + "x" + "\033[0m"
    passed_mark = "\033[32m" + "\u2713" + "\33[0m"

    def log(self, cnx, message, status=None):
        if status is not None:
            print(f" {self.passed_mark if status else self.failed_mark} {message}")
        else:
            print(message)
        cnx.info(message)
