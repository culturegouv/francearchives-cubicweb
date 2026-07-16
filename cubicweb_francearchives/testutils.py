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

import datetime as dt
import csv
from io import BytesIO, TextIOWrapper
from lxml import etree
import shutil
import os
import os.path as osp
from uuid import uuid4

import boto3
import mock
from moto import mock_s3
from botocore.exceptions import ClientError
import zipfile

from logilab.common.date import ustrftime

from cubicweb import Binary
from cubicweb.cwconfig import CubicWebConfiguration


# library specific imports
from cubicweb_francearchives import S3_ACTIVE, FranceArchivesS3Storage, IIIF_MANIFEST_ROLE
from cubicweb_francearchives.dataimport import (
    eac,
    ead,
    load_services_map,
    service_infos_from_filepath,
)
from cubicweb_francearchives.dataimport.oai import harvest_delta, harvest_oai
from cubicweb_francearchives.dataimport.oai_utils import PniaOAIResponse, PniaSickle
from cubicweb_francearchives.dataimport.sqlutil import (
    disable_triggers,
    enable_triggers,
    sudocnx,
    ead_foreign_key_tables,
)
from cubicweb_francearchives.dataimport.csv_nomina.nomina import CSVNominaReader
from cubicweb_francearchives.dataimport.csv_nomina.socface import CSVNominaSocfaceReader

from cubicweb_francearchives.dataimport.oai_ead import OAIEADHarvestedReader
from cubicweb_francearchives.dataimport.stores import create_massive_store
from cubicweb_francearchives.storage import S3BfssStorageMixIn

from cubicweb_web.devtools.testlib import WebPostgresApptestConfiguration


def create_findingaid(cnx, eadid, service):
    return cnx.create_entity(
        "FindingAid",
        name=eadid,
        stable_id="stable_id{}".format(eadid),
        eadid=eadid,
        publisher="publisher",
        did=cnx.create_entity(
            "Did", unitid="unitid {}".format(eadid), unittitle="title {}".format(eadid)
        ),
        fa_header=cnx.create_entity("FAHeader"),
        service=service,
    )


def find_component(cnx, unitid):
    rset = cnx.execute(
        "Any X WHERE X is FAComponent, X did D, " "D unitid %(unitid)s", {"unitid": unitid}
    )
    if rset:
        return rset.one()
    return None


class PostgresTextMixin(object):
    """unittest mixin for postgresql-based tests

    - define configcls
    - setup postgresql extensions
    """

    configcls = WebPostgresApptestConfiguration

    def setUp(self):
        super(PostgresTextMixin, self).setUp()
        with self.admin_access.cnx() as cnx:
            # unaccent will already be added in production
            cnx.system_sql("CREATE EXTENSION IF NOT EXISTS unaccent")
            cnx.commit()


class HashMixIn(object):
    @classmethod
    def init_config(cls, config):
        super(HashMixIn, cls).init_config(config)
        config.set_option("compute-hash", True)
        config.set_option("hash-algorithm", "sha1")


class S3BfssStorageTestMixin(HashMixIn):
    s3_endpoint = os.environ.get("AWS_S3_ENDPOINT_URL", "")

    @classmethod
    def init_config(cls, config):
        """Initialize configuration."""
        super().init_config(config)
        config.set_option("ead-services-dir", "/tmp")
        config.set_option("eac-services-dir", "/tmp")
        config.set_option("nomina-services-dir", "/tmp")
        config.set_option("nomina-index-name", "nomina_index")

    def s3_test_with_mock(self):
        return S3_ACTIVE and "9000" not in self.s3_endpoint

    def s3_test_with_minio(self):
        return S3_ACTIVE and "9000" in self.s3_endpoint

    def setUp(self):
        self.fkeyfunc = "STKEY"
        self.s3_bucket_name = "siaf-tests-{}".format(uuid4()) if S3_ACTIVE else None
        if self.s3_test_with_mock():
            s3_mock = mock_s3()
            s3_mock.start()
            resource = boto3.resource("s3", region_name="us-east-1")
            self.s3_bucket = resource.create_bucket(Bucket=self.s3_bucket_name)
            patched_storage_s3_client = mock.patch(
                "cubicweb_s3storage.storages.S3Storage._s3_client",
                return_value=boto3.client("es3"),
            )
            patched_storage_s3_client.start()
            self._mocks = [
                s3_mock,
                patched_storage_s3_client,
            ]
            # TODO mock pyramid s3 cnx too
            print("S3 Storage activated")
        elif self.s3_test_with_minio():
            os.environ["AWS_S3_BUCKET_NAME"] = self.s3_bucket_name
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            try:
                storage.s3cnx.create_bucket(Bucket=self.s3_bucket_name)
            except ClientError:
                print("Bucket {} already exists".format(self.s3_bucket_name))
            ape_ead_bucket_name = os.environ.get("AWS_S3_APE_BUCKET_NAME")
            if ape_ead_bucket_name:
                try:
                    storage.s3cnx.create_bucket(Bucket=ape_ead_bucket_name)
                except ClientError:
                    print("Bucket {} already exists".format(ape_ead_bucket_name))
            print("S3 Storage activated with minio")
        else:
            # we are not on S3Storage
            self.fkeyfunc = "FSPATH"
            print("BFSS Storage activated")
        super(S3BfssStorageTestMixin, self).setUp()

    def tearDown(self):
        super(S3BfssStorageTestMixin, self).tearDown()
        if self.s3_test_with_mock():
            while self._mocks:
                self._mocks.pop().stop()
        elif self.s3_test_with_minio():
            try:
                s3 = boto3.resource("s3", endpoint_url=os.environ.get("AWS_S3_ENDPOINT_URL"))
                bucket = s3.Bucket(self.s3_bucket_name)
                bucket.objects.all().delete()
                bucket.delete()
            except ClientError as exc:
                print(exc)
                print("[test.treaDown] Failed to delete bucket {}".format(self.s3_bucket_name))

    def fileExists(self, fkey, bucket_name=None):
        """
        Returns boolean
        """
        if not self.s3_bucket_name:
            return osp.exists(fkey)

        bucket_name = bucket_name if bucket_name else self.s3_bucket_name

        if isinstance(fkey, bytes):
            fkey = fkey.decode()
        if self.s3_test_with_mock():
            s3 = boto3.resource("s3")
            s3_object = s3.Object(bucket_name, fkey)
            try:
                return s3_object.get()["Body"]
            except s3.meta.client.exceptions.NoSuchKey:
                print(f"[test.fileExists] no {fkey} key found in {bucket_name} bucket")
                return False
        elif self.s3_test_with_minio():
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            try:
                head = storage.s3cnx.head_object(Key=fkey, Bucket=bucket_name)
                return head["ResponseMetadata"].get("HTTPStatusCode") == 200
            except ClientError:
                print(f"[test.fileExists] no {fkey} key found in {bucket_name} bucket")
                return False

    def getFileContent(self, fkey, bucket_name=None):
        """
        Returns file contents or None if no file is found
        """
        if not self.s3_bucket_name:
            with open(fkey, "rb") as fp:
                return fp.read()

        bucket_name = bucket_name if bucket_name else self.s3_bucket_name

        if isinstance(fkey, bytes):
            fkey = fkey.decode()
        if self.s3_test_with_mock():
            s3 = boto3.resource("s3")
            s3_object = s3.Object(bucket_name, fkey)
            try:
                return s3_object.get()["Body"].read()
            except s3.meta.client.exceptions.NoSuchKey:
                print(f"[test.getFileContent] no {fkey} key found in {bucket_name} bucket")
                return False
        elif self.s3_test_with_minio():
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            try:
                result = storage.s3cnx.get_object(Bucket=bucket_name, Key=fkey)
                return result["Body"].read()
            except ClientError:
                print(f"[test.getFileContent] no {fkey} key found in {bucket_name} bucket")

    def deleteFile(self, fkey, bucket_name=None):
        """
        Delete a file
        """
        if not self.s3_bucket_name:
            os.remove(fkey)

        bucket_name = bucket_name if bucket_name else self.s3_bucket_name

        if isinstance(fkey, bytes):
            fkey = fkey.decode()
        if self.s3_test_with_mock():
            s3 = boto3.resource("s3")
            try:
                s3.Object(bucket_name, fkey).delete()
            except Exception as err:
                print(f"[test.deleteFile] coud not delete {fkey} from {bucket_name} bucket : {err}")
        elif self.s3_test_with_minio():
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            try:
                storage.s3cnx.delete_object(Bucket=bucket_name, Key=fkey)
            except ClientError as err:
                print(f"[test.deleteFile] coud not delete {fkey} from {bucket_name} bucket : {err}")

    def isFile(self, fkey, bucket_name=None):
        if self.s3_bucket_name:
            bucket_name = bucket_name if bucket_name else self.s3_bucket_name
            return self.fileExists(fkey, bucket_name)
        else:
            return osp.isfile(fkey)

    def get_filepath_by_storage(self, filepath):
        """
        Compute the filepath for test.

        :create: if true, upload imported files in s3
        :filepath: imported filepath

        :returns: filepath
        :rtype: str
        """
        if self.s3_bucket_name:
            return filepath.lstrip("/")
        else:
            return self.datapath(filepath)

    def storage_write_file(self, filepath, content, replace=False):
        """
        Write a file with the give content
        """
        if self.s3_bucket_name:
            if not replace and self.fileExists(filepath):
                return filepath
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            storage.temporary_import_upload(Binary(content.encode("utf8")), filepath)
        else:
            dirs, basename = os.path.split(filepath)
            if not osp.exists(dirs):
                os.makedirs(dirs)
            with open(filepath, "w+") as fp:
                fp.write(content)

    def get_or_create_imported_filepath(self, filepath):
        """
        Compute the filepath for test.

        :create: if true, upload ead test files in s3
        :filepath: imported filepath

        :returns: filepath
        :rtype: str
        """

        if self.s3_bucket_name:
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            if storage.file_exists(filepath):
                # we are probably testing file reimports
                return filepath
            fs_filepath = self.datapath(filepath)
            with open(fs_filepath, "rb") as stream:
                storage.temporary_import_upload(Binary(stream.read()), filepath)
            # also upload "RELFILES" if exist
            relfiles_dir = f"{osp.dirname(fs_filepath)}/RELFILES"
            for root, dirs, files in os.walk(relfiles_dir):
                for relfname in files:
                    relkey = storage.ensure_key(f"{osp.dirname(filepath)}/RELFILES/{relfname}")
                    with open(osp.join(root, relfname), "rb") as stream:
                        storage.temporary_import_upload(Binary(stream.read()), relkey)
            # also upload metadata file if exists
            metadata_file = f"{osp.dirname(fs_filepath)}/metadata.csv"
            if osp.isfile(metadata_file):
                with open(metadata_file, "rb") as stream:
                    metadata_key = storage.ensure_key(f"{osp.dirname(filepath)}/metadata.csv")
                    storage.temporary_import_upload(Binary(stream.read()), metadata_key)

        else:
            filepath = self.datapath(filepath)
        return filepath

    def load_directory_folder(self, fs_folderpath, prefix):
        """
        Compute the filepath for test.

        :fs_folderpath: file system folder path to import
        :filepath: imported filepath
        """

        if self.s3_bucket_name:
            storage = FranceArchivesS3Storage(self.s3_bucket_name)
            for root, dirs, files in os.walk(fs_folderpath):
                for filename in files:
                    fs_filepath = osp.join(root, filename)
                    fkey = storage.ensure_key(fs_filepath.replace(fs_folderpath, prefix))
                    with open(fs_filepath, "rb") as stream:
                        storage.temporary_import_upload(Binary(stream.read()), fkey)


class APEEADMixin:

    def get_ape_ead_content(self, cnx):
        """Return ape ead file content"""
        return cnx.execute("Any D WHERE X ape_ead_file F, F data D")[0][0].read()

    def _test_ape_ead_iiif_daos(self, cnx, expected_manifests):
        """
        Expecting: iiif dao for ape ead has been added
        """
        content = self.get_ape_ead_content(cnx)
        tree = etree.fromstring(content)
        daos = self.get_iiif_manifests_from_tree(tree)
        got = sorted([dao.attrib.get(f"{{{tree.nsmap['xlink']}}}href") for dao in daos])
        self.assertEqual(sorted(got), sorted(expected_manifests))

    def get_iiif_manifests_from_tree(self, tree):
        return tree.xpath(
            "//e:dao[@link:role='MANIFEST']",
            namespaces={"e": tree.nsmap[None], "link": tree.nsmap["xlink"]},
        )

    def get_iiif_manifests(self, cnx):
        return [
            url
            for url, in cnx.execute(
                f"Any U WHERE X is DigitizedVersion, X url U, X role '{IIIF_MANIFEST_ROLE}'"
            ).rows
        ]


class EADImportMixin(APEEADMixin, S3BfssStorageTestMixin):
    readerconfig = {
        "esonly": False,
        "index-name": "dummy",
        "appid": "data",
        "nodrop": False,
    }

    def setUp(self):
        super(EADImportMixin, self).setUp()
        import_dir = self.datapath("tmp")
        self.config.set_option("appfiles-dir", import_dir)
        self.config.set_option("ead-services-dir", "/tmp")
        self.config.set_option("eac-services-dir", "/tmp")
        self.config.set_option("eac-services-dir", "/tmp")

        if not osp.isdir(import_dir):
            os.mkdir(import_dir)
        self.imported_filepath = None

    def tearDown(self):
        super(EADImportMixin, self).tearDown()
        import_dir = self.datapath("tmp")
        if osp.exists(import_dir):
            shutil.rmtree(import_dir)

    def init_reader(self, settings, store, *args):
        return ead.Reader(settings, store, *args)

    def import_filepath(self, cnx, filepaths, service_infos=None, *reader_args, **custom_settings):
        if not isinstance(filepaths, (list, tuple)):
            filepaths = [filepaths]
        if service_infos is None:
            services_map = load_services_map(cnx)
            service_infos = service_infos_from_filepath(filepaths[0], services_map)
        if not self.readerconfig["nodrop"]:
            fk_tables = ead_foreign_key_tables(cnx.vreg.schema)
            with sudocnx(cnx, interactive=False) as su_cnx:
                disable_triggers(su_cnx, fk_tables)
        store = create_massive_store(cnx, nodrop=self.readerconfig["nodrop"])
        settings = self.readerconfig.copy()
        settings["appfiles-dir"] = self.config["appfiles-dir"]
        settings.update(custom_settings)
        self.reader = self.init_reader(settings, store, *reader_args)
        es_docs = []
        for filepath in filepaths:
            filepath = self.get_or_create_imported_filepath(filepath)
            if isinstance(filepath, bytes):
                filepath = filepath.decode("utf-8")
            self.imported_filepath = filepath
            es_docs.extend(self.reader.import_filepath(filepath, service_infos))
        store.flush()
        store.finish()
        if not self.readerconfig["nodrop"]:
            with sudocnx(cnx, interactive=False) as su_cnx:
                enable_triggers(su_cnx, fk_tables)
        return es_docs


class EACImportMixin(S3BfssStorageTestMixin):

    def setup_database(self):
        # create services
        super(EACImportMixin, self).setup_database()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service",
                category="?",
                name="Les Archives Nationales",
                short_name="Les AN",
                code="FRAN",
            )
            cnx.commit()

    def eac_filepath(self, fname):
        """joins the object's datadir and `fname`"""
        return self.get_or_create_imported_filepath(f"eac/{fname}")

    def massif_import_files(self, cnx, fspaths):
        store = create_massive_store(cnx, nodrop=True)
        eac.eac_import_files(cnx, fspaths, store=store)


class NominaImportMixin(S3BfssStorageTestMixin):
    def setUp(self):
        super(NominaImportMixin, self).setUp()
        import_dir = self.datapath("tmp")
        self.config.set_option("appfiles-dir", import_dir)
        if not osp.isdir(import_dir):
            os.mkdir(import_dir)

    readerconfig = {
        "nomina-index-name": "dummy_nomina",
    }

    def tearDown(self):
        super(NominaImportMixin, self).tearDown()
        import_dir = self.datapath("tmp")
        if osp.exists(import_dir):
            shutil.rmtree(import_dir)

    def import_filepath(self, cnx, filepath, doctype, delimiter=";"):
        readercls = CSVNominaReader if doctype != "SOCFACE" else CSVNominaSocfaceReader
        reader = readercls(self.readerconfig, cnx, self.service.code)
        st = S3BfssStorageMixIn()
        return list(reader.import_records(st, filepath, doctype=doctype, delimiter=delimiter))


class XMLCompMixin(object):
    def assertXMLEqual(self, etree0, etree1):
        """Assert element tree equivalence.

        :param Element etree0: element tree element
        :param Element etree1: element tree element
        """

        self.assertEqual(etree0.attrib, etree1.attrib)
        self.assertEqual(etree0.tag, etree1.tag)
        self.assertEqual(etree0.tail, etree1.tail)
        self.assertEqual(etree0.text, etree1.text)
        for child0, child1 in zip(etree0.getchildren(), etree1.getchildren()):
            self.assertXMLEqual(child0, child1)

    def assertXmlValid(self, xml_data, xsd_filename, debug=False):
        """Validate an XML file (.xml) according to an XML schema (.xsd)."""
        with open(xsd_filename) as xsd:
            xmlschema = etree.XMLSchema(etree.parse(xsd))
        # Pretty-print xml_data to get meaningfull line information.
        xml_data = etree.tostring(etree.fromstring(xml_data), pretty_print=True)
        root = etree.fromstring(xml_data)
        if debug and not xmlschema.validate(root):
            print(xml_data)
        xmlschema.assertValid(root)


class EsSerializableMixIn(object):
    def setUp(self):
        super(EsSerializableMixIn, self).setUp()
        if "PIFPAF_ES_ELASTICSEARCH_URL" in os.environ:
            self.config.global_set_option(
                "elasticsearch-locations", os.environ["PIFPAF_ES_ELASTICSEARCH_URL"]
            )
        else:
            self.config.global_set_option(
                "elasticsearch-locations", "http://nonexistant.elastic.search:9200"
            )
        self.index_name = "unittest_index_name"
        self.config.global_set_option("index-name", self.index_name)

    def setup_database(self):
        super(EsSerializableMixIn, self).setup_database()
        self.orig_config_for = CubicWebConfiguration.config_for
        config_for = lambda appid: self.config  # noqa
        CubicWebConfiguration.config_for = staticmethod(config_for)


class MockOaiSickleResponse(object):
    """Mimics the response object returned by HTTP requests."""

    def __init__(self, text):
        # request's response object carry an attribute 'text' which contains
        # the server's response data encoded as unicode.
        self.text = text
        self.content = text.encode("utf-8")


class OaiSickleMixin(object):
    def filepath(self, filepath):
        raise NotImplementedError

    def __init__(self, *args, **kwargs):
        self.patch = mock.patch(
            "cubicweb_francearchives.dataimport.oai_utils.PniaSickle.harvest", self.mock_harvest
        )
        self.filename = None
        super(OaiSickleMixin, self).__init__(*args, **kwargs)

    def setUp(self):
        super(OaiSickleMixin, self).setUp()
        self.patch.start()
        self.sickle = PniaSickle("http://localhost")

    def tearDown(self):
        """Tear down test cases."""
        super(OaiSickleMixin, self).tearDown()
        self.patch.stop()

    def mock_harvest(self, *args, **kwargs):
        verb = kwargs.get("verb")
        filename = self.filename
        assert filename is not None
        if verb:
            if not self.filename.endswith(f"_{verb.lower()}.xml"):
                base, ext = self.filename.split(".")
                filename = f"{base}_{verb.lower()}.{ext}"
        with open(self.filepath(filename), "r") as fp:
            response = MockOaiSickleResponse(fp.read())
            return PniaOAIResponse(response, kwargs)

    def ListSets(self):
        return self.sickle.ListSets()


class OaiImportMixin(EADImportMixin, OaiSickleMixin):

    def path(self, service_infos=None):
        raise NotImplementedError

    def get_create_service(self, cnx, service_infos):
        eid = service_infos.get("eid")
        return cnx.find("Service", eid=eid).one() if eid else None

    def init_reader(self, settings, store, *args):
        if args:
            return OAIEADHarvestedReader(settings, store, args[0])
        return ead.Reader(settings, store, *args)

    def create_repo(self, cnx, url, service=None, delta=False):
        if service is None:
            service = cnx.find("Service", eid=self.service_eid).one()
        repo = cnx.create_entity(
            "OAIRepository", name="{} repo".format(service.code), service=service, url=url
        )
        if not delta:
            oaitask = cnx.create_entity("OAIImportTask", oai_repository=repo.eid)
        else:
            oaitask = None
        cnx.commit()
        return repo, oaitask

    def import_oai(self, cnx, url, service_infos=None, delta=False, repo=None):
        """Harvest and import records"""
        service_infos = service_infos or self.service_infos
        service = self.get_create_service(cnx, service_infos)
        if delta:
            if repo is None:
                repo, oaitask = self.create_repo(cnx, url, delta=delta)
            harvest_delta(cnx, repo.eid, service_infos)
            repo.cw_clear_all_caches()
            oaitask = repo.reverse_oai_repository[0]
        else:
            repo, oaitask = self.create_repo(cnx, url, service=service, delta=delta)
            harvest_oai(cnx, url, oaitask.eid, service_infos)
        zipfiles = self.get_oaitask_zipfiles(cnx, oaitask.eid)
        for zfile in zipfiles:
            zf = self.get_zipfile(cnx, zfile)
            filepaths = []
            for filename in zf.namelist():
                if filename.endswith(".xml"):
                    filecontent = TextIOWrapper(zf.open(filename)).read()
                    filepath = self.get_filepath_by_storage(
                        os.path.join(self.path(service_infos), filename)
                    )
                    self.storage_write_file(filepath, filecontent, replace=True)
                    filepaths.append(filepath)
            self.import_filepath(cnx, filepaths, service_infos, self.get_identifiers(zf))

    def get_zipfile(self, cnx, cwfile):
        filepath = cnx.execute("Any FSPATH(D) WHERE X eid %(e)s, X data D", {"e": cwfile.eid})[0][
            0
        ].getvalue()
        return zipfile.ZipFile(BytesIO(self.getFileContent(filepath)), mode="r")

    def get_oaitask_zipfiles(self, cnx, oaitask_eid):
        oaitask = cnx.entity_from_eid(oaitask_eid)
        return oaitask.fatask_oaiharvest_file

    def get_identifiers(self, zf):
        if "identifiers.csv" in zf.namelist():
            return dict(self.read_csv_zipfile(zf, "identifiers.csv"))

    def read_csv_zipfile(self, zf, filename):
        return list(csv.reader(TextIOWrapper(zf.open(filename), "utf-8"), delimiter="\t"))


def format_date(date, fmt="%Y-%m-%d"):
    return ustrftime(date, fmt)


def create_authority_record(cnx, name=None, record_id=None):
    rset = cnx.find("Service", code="CODE")
    if rset:
        service = rset.get_entity(0, 0)
    else:
        service = cnx.create_entity(
            "Service", category="other", name="Service", code="CODE", short_name="ADP"
        )
    name = name or "Jean Cocotte"
    subject = cnx.create_entity(
        "AgentAuthority",
        label=name,
        reverse_authority=cnx.create_entity(
            "AgentName",
            role="person",
            label="name",
        ),
    )
    kind_eid = cnx.find("AgentKind", name="person")[0][0]
    record = cnx.create_entity(
        "AuthorityRecord",
        record_id=record_id or "FRAN_NP_006883",
        agent_kind=kind_eid,
        maintainer=service.eid,
        reverse_name_entry_for=cnx.create_entity(
            "NameEntry", parts=name, form_variant="authorized"
        ),
        xml_support="foo",
        start_date=dt.date(1940, 1, 1),
        end_date=dt.date(2000, 5, 1),
        reverse_occupation_agent=cnx.create_entity("Occupation", term="éleveur de poules"),
        reverse_history_agent=cnx.create_entity("History", text="<p>Il aimait les poules</p>"),
        same_as=subject,
    )
    return record


def sort_authorities(authorities):
    # it is possible to have different indexes with different types linked to
    # the same authority
    return sorted(authorities, key=lambda x: (x["authority"], x["type"]))
