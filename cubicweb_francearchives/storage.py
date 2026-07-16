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

from contextlib import contextmanager
import csv
import glob
import gzip
from io import TextIOWrapper, BytesIO, StringIO
import logging
import os
import shutil
from tempfile import mkstemp, NamedTemporaryFile
import zipfile

from cubicweb import Binary
from cubicweb_francearchives import FranceArchivesS3Storage
from cubicweb_francearchives.dataimport import usha1, decode_filepath

LOGGER = logging.getLogger()

for s3logger in (
    "botocore",
    "s3transfer",
):
    logging.getLogger(s3logger).setLevel(logging.WARN)


class S3BucketError(Exception):
    """raised when there is en error with S3BucketError"""


class S3BfssStorageMixIn:
    """Helper class for S3/BFSS file storage"""

    def __init__(self, bfss=False, bucket_name=None, log=None):
        """Initialize S3BfssStorageMixIn
        :param boolean bfss: force FileSystem storage
        :param String bucket_name: name of S3 bucket
        :param Logger log: log

        """
        if log is None:
            log = logging.getLogger("S3BfssStorage")
        self.log = log
        if bfss:
            self.s3 = None
            self.s3_bucket = None
            return
        self.s3_bucket = bucket_name or os.environ.get("AWS_S3_BUCKET_NAME")
        if not self.s3_bucket:
            msg = "No name found for S3 bucket"
            self.log.error(msg)
            raise S3BucketError(msg)
        self.s3 = FranceArchivesS3Storage(self.s3_bucket)
        if self.s3_bucket not in self.get_buckets_list():
            msg = (
                "No bucket '%s' found. Please, "
                "contact the administrator to create it." % self.s3_bucket
            )
            self.log.error(msg)
            raise S3BucketError(msg)

    def get_buckets_list(self):
        response = self.s3.s3cnx.list_buckets()
        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            if "Buckets" not in response:
                self.log.error("No information about existing s3 buckets " "could be retrieved")
                return
        return [obj["Name"] for obj in response["Buckets"]]

    def s3_write_zipfile(self, zipfile, directory, exts=None):
        """Write a zipfile content in S3

        :zipfile: zipfile
        :directory: directory to add to the file key
        :exsts: list of file extensions to keep

        :returns: filepaths
        :rtype: list
        """
        filepaths = []
        for filename in zipfile.namelist():
            if exts and os.path.splitext(filename.lower())[1] not in exts:
                continue
            key = self.s3.ensure_key(f"{directory}/{filename}")
            self.s3.temporary_import_upload(zipfile.open(filename), key)
            filepaths.append(key)
        return filepaths

    def bfss_write_zipfile(self, zipfile, directory, exts=None):
        """Write a zipfile content on the fs

        :zipfile: zipfile
        :directory: directory to extract files
        :exsts: list of file extensions to keep

        :returns: filepaths
        :rtype: list
        """
        filepaths = []
        zipfile.extractall(directory)
        for filename in zipfile.namelist():
            if exts and os.path.splitext(filename.lower())[1] not in exts:
                continue
            filepaths.append(os.path.join(directory, filename))
        return filepaths

    def storage_write_zipfile(self, zipfile, directory, exts=None):
        """Write a zipfile content on the fs

        :param files: list of (filepath, filename)
        :param str archive: Zip archive
        :param log: log

        :returns: Zip archive
        :rtype: str
        """
        if self.s3_bucket:
            return self.s3_write_zipfile(zipfile, directory, exts=exts)
        return self.bfss_write_zipfile(zipfile, directory, exts=exts)

    def s3_create_zipfiles(self, files, zippath):
        """Write a zip file in S3

        :files: list of (filepath, filename)
        :zippath: path to zipfile
        :log: log
        """
        with zipfile.ZipFile(
            zippath, "a", compression=zipfile.ZIP_DEFLATED, allowZip64=True
        ) as zip_file:
            for key, filename in files:
                try:
                    response = self.s3.s3cnx.get_object(Bucket=self.s3.bucket, Key=key)
                except Exception as err:
                    self.log.warning(f"file {key}: {err}")
                    continue
                if response:
                    if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                        zip_file.writestr(filename, response["Body"].read())
                    else:
                        self.log.warning(
                            f"file {key} : got {response['ResponseMetadata']['HTTPStatusCode']} reponse"  # noqa
                        )

    def bfss_create_zipfiles(self, files, archive=""):
        """Create Zip archive. If archive is not set, a named temporary file is created.

        :param str archive: Zip archive
        :param list files: list of filename-arcname tuples

        :returns: Zip archive
        :rtype: str
        """
        if not archive:
            fp = NamedTemporaryFile(delete=False)
            archive = fp.name
            fp.close()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as fp:
            for filename, arcname in files:
                if not (os.path.exists(filename) and os.path.isfile(filename)):
                    self.log.warning(f"file {filename} does not exist")
                    continue
                try:
                    fp.write(filename, arcname=arcname)
                except Exception:
                    self.log.warning("failed to add %s to Zip archive %s", filename, archive)
            self.log.info("Zip archive contains %r files", len(fp.namelist()))
        return archive

    def storage_create_zipfiles(self, files, archive):
        """Create a Zip archive

        :param files: list of (filepath, filename)
        :param str archive: Zip archive
        :param log: log

        :returns: Zip archive
        :rtype: str
        """
        if self.s3_bucket:
            return self.s3_create_zipfiles(files, archive)
        return self.bfss_create_zipfiles(files, archive)

    def s3_write_file(self, filename, filecontent, subdirectories=[], compressed=False):
        """Write a file in S3

        :filename: filename
        :filecontent: file content
        :param list subdirectories: list of subdirectories
        :param compressed: file must or not be compressed

        :returns: filepath
        :rtype: str
        """
        parts = subdirectories + [filename]
        filepath = self.s3.ensure_key("/".join(parts))
        binary = Binary(filecontent)
        self.s3.temporary_import_upload(binary, filepath)
        return filepath

    def bfss_write_file(self, filename, filecontent, subdirectories=[], compressed=False):
        """Write a file on the fs

        :filename: filename
        :filecontent: file content
        :param compressed: file must or not be compressed

        :returns: filepath
        :rtype: str
        """
        if subdirectories:
            directory = self.bfss_makedir(subdirectories)
            filepath = os.path.join(directory, filename)
        else:
            filepath = filename
        with open(filepath, "wb") as f:
            f.write(filecontent)
            return filepath

    def storage_write_gz_file(self, filename, buf, output_dir=None):
        if not isinstance(buf, bytes):
            buf = buf.getvalue().encode("utf-8")
        if self.s3_bucket:
            return self.s3_storage_write_gz_file(filename, buf, output_dir)
        return self.bfss_storage_write_gz_file(filename, buf, output_dir)

    def s3_storage_write_gz_file(self, filename, buf, output_dir=None):
        """
        Write gzip file

        :param str filename: file name
        :param StringIO buf: content to write in the file
        :param str output_dir: directory for the file
        """
        if output_dir:
            filename = "/".join([output_dir, filename])
        key = self.s3.ensure_key(filename)
        gz_body = BytesIO()
        gz = gzip.GzipFile(None, "wb", 9, gz_body)
        gz.write(buf)
        gz.close()
        self.s3.s3cnx.upload_fileobj(
            Binary(gz_body.getvalue()),
            self.s3.bucket,
            key,
            ExtraArgs={"ContentType": "text/plain", "ContentEncoding": "gzip"},
        )

    def bfss_storage_write_gz_file(self, filename, buf, output_dir=None):
        """
        Write gzip file

        :param str filename: file name
        :param StringIO buf: content to write in the file
        :param str output_dir: directory for the file
        """
        if output_dir:
            filename = os.path.join(output_dir, filename)
        with gzip.open(filename, "wb") as stream:
            stream.write(buf)

    def storage_write_file(self, filepath, filecontent, subdirectories=[], compressed=False):
        if compressed:
            if subdirectories:
                if self.s3_bucket:
                    subdirectories = self.s3.ensure_key("/".join(subdirectories))
                else:
                    subdirectories = self.bfss_makedir(subdirectories)
            return self.storage_write_gz_file(filepath, filecontent, subdirectories)
        if self.s3_bucket:
            return self.s3_write_file(filepath, filecontent, subdirectories, compressed=False)
        return self.bfss_write_file(filepath, filecontent, subdirectories, compressed=False)

    def s3_write_csv_file(self, filename, rows, directory=None, delimiter=";"):
        """Write a csv in S3

        :filename: filename
        :filecontent: csv content
        :param directory: directory

        :returns: filepath
        :rtype: str
        """
        if directory:
            filename = f"{directory.rstrip('/')}/{filename}"
        filename = self.s3.ensure_key(filename)
        content = StringIO()
        writer = csv.writer(content, delimiter=delimiter)
        writer.writerows(rows)
        content = Binary(content.getvalue().encode("utf-8"))
        self.s3.s3cnx.upload_fileobj(
            content, self.s3.bucket, filename, ExtraArgs={"ContentType": "text/csv"}
        )
        return filename

    def bfss_write_csv_file(self, filename, rows, directory, delimiter=";"):
        """Write a csv file on the fs

        :filename: filename
        :filecontent: csv content
        :param directory: directory

        :returns: filepath
        :rtype: str
        """
        if directory:
            if not os.path.exists(directory):
                os.makedirs(directory)
            filename = os.path.join(directory, filename)
        with open(filename, "w") as f:
            writer = csv.writer(f, delimiter=delimiter)
            writer.writerows(rows)
            return filename

    def storage_write_csv_file(self, filepath, rows, directory=None, delimiter=";"):
        if self.s3_bucket:
            return self.s3_write_csv_file(filepath, rows, directory, delimiter)
        return self.bfss_write_csv_file(filepath, rows, directory, delimiter)

    @contextmanager
    def storage_handle_tmpfile_from_file(self, filepath, prefix=""):
        """
        If s3 write a tempfile from en existing file and remove it

        :filename: filename

        :returns: filepath
        :rtype: str

        """

        if self.s3_bucket:
            # load the filecontent
            tmpd_fdesc, tmp_filepath = mkstemp(prefix)
            try:
                content = self.s3_get_file_content(filepath)
                if content is None:
                    self.log.error("'%s' content is None", filepath)
                    content = b""
                with open(tmp_filepath, "wb") as f:
                    f.write(content)
                os.close(tmpd_fdesc)
                yield tmp_filepath
            finally:
                if os.path.isfile(tmp_filepath):
                    os.remove(tmp_filepath)
        else:
            yield filepath

    def s3_write_tmpfile(self, filepath, content):
        """Write content of input file to temporary file.

        :filepath: path to the file
        :param bytes content: content

        :returns: filepath
        :rtype: str
        """
        key = self.s3.ensure_key(filepath)
        # add mime type ?
        self.s3.s3cnx.upload_fileobj(Binary(content), self.s3.bucket, key)
        return key

    def bfss_write_tmpfile(self, _filepath, content):
        """Write content of input file to a temporary file.

        :_filepath: path to the file
        :param bytes content: content

        :returns: filename of temporary file
        :rtype: str
        """

        fd, filepath = mkstemp()
        os.write(fd, content)
        os.close(fd)
        return filepath

    def storage_write_tmpfile(self, filepath, content):
        """Write content of input file to a temporary file.

        :filepath: path to the file
        :param bytes content: content

        :returns: filename of temporary file
        :rtype: str
        """

        if self.s3_bucket:
            return self.s3_write_tmpfile(filepath, content)
        return self.bfss_write_tmpfile(filepath, content)

    def storage_delete_file(self, fpath):
        """Delete a file.

        :fpath: file to delete
        """
        if self.s3_bucket:
            self.s3.s3cnx.delete_object(Bucket=self.s3.bucket, Key=fpath)
        else:
            if os.path.isfile(fpath):
                os.remove(fpath)

    def s3_makedir(self, subdirectories):
        """Create directory(ies).

        :param list subdirectories: list of subdirectories

        :returns: directory
        :rtype: str
        """
        return "/".join(subdirectories)

    def bfss_makedir(self, subdirectories):
        """Create directory(ies).

        :param list subdirectories: list of subdirectories

        :returns: directory
        :rtype: str
        """
        directory = os.path.join(*subdirectories)
        if not os.path.exists(directory):
            os.makedirs(directory)
        return directory

    def storage_makedir(self, subdirectories):
        """Create directory(ies).

        :param list subdirectories: list of subdirectories

        :returns: directory
        :rtype: str
        """
        if self.s3_bucket:
            return self.s3_makedir(subdirectories)
        else:
            return self.bfss_makedir(subdirectories)

    def storage_handle_ape_ead_filepath(self, ape_filepath):
        """If S3 storage add the ape_ead XML file to the bucket and remove glameconv generated
        files (XML and log.json) from the FS.

        It should probably be done in glameconv.

        :filepath: generated APE-EAD xml filepath

        :returns: ape_filepath
        :rtype: str
        """
        if self.s3_bucket:
            # add ape_filepath to S3 storage
            ape_s3_key = self.s3.ensure_key(ape_filepath)
            with open(ape_filepath, "rb") as f:
                self.s3_write_file(ape_s3_key, f.read())
            # remove glamconv generated files
            log_ape_filepath = f"{os.path.splitext(ape_filepath)[0]}.log.json"
            for filepath in (ape_filepath, log_ape_filepath):
                if os.path.exists(filepath):
                    os.remove(filepath)
            return ape_s3_key
        else:
            return ape_filepath

    def storage_ufilepath(self, filepath):
        if self.s3_bucket:
            return filepath
        return os.path.abspath(decode_filepath(filepath))

    def storage_get_basepath(self, filepath):
        """
        Equivalent to osp.basename(ufilepath)
        """
        ufilepath = os.path.abspath(decode_filepath(filepath))
        return os.path.basename(ufilepath)

    def storage_make_symlink_to_publish(self, filepath, sha1, directory=None):
        """
        Create a symlink in the published directory for BFSS
        Create a file in s3
        """
        if self.s3_bucket:
            fname = os.path.basename(filepath)
            # don't take account of cnx.vreg.config["appfiles-dir"] which must be ""
            to_key = self.s3.ensure_key(f"{sha1}_{fname}")
            self.s3.temporary_import_copy(filepath, to_key)
        else:
            if directory:
                destpath = os.path.join(
                    directory, "{}_{}".format(str(sha1), os.path.basename(filepath))
                )
                if os.path.lexists(destpath):
                    os.unlink(destpath)
                os.symlink(filepath, destpath)

    def storage_handle_pdf_relfiles(self, filepath):
        """
        Handle related PDF files stored in /RELFILES subdirectory of an imported XML

        :filepath: XML imported filepath

        :returns: relfiles
        :rtype: dict
        """
        if self.s3_bucket:
            # TODO change to a split("/") ?
            relfiles_prefix = f"{self.s3.import_prefix}{os.path.dirname(filepath)}/RELFILES/"
            #  Returns some or all (up to 1,000) of the objects in a bucket
            #  which must be enough for FA
            response = self.s3.s3cnx.list_objects(
                Bucket=self.s3.bucket, Prefix=relfiles_prefix, Delimiter="/"
            )
            if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
                if "Contents" not in response:
                    return None
                relfiles = {}
                for obj in response["Contents"]:
                    # remove self.import_prefix if exists as relfiles serves
                    # only to link existing files with the IR, but no creating
                    # them
                    filepath = obj["Key"]
                    if self.s3.import_prefix:
                        filepath = filepath.split(self.s3.import_prefix)[1]
                    # only consider PDF files
                    if filepath.lower().endswith("pdf"):
                        s3key = self.s3.ensure_key(obj["Key"].split(relfiles_prefix)[1])
                        relfiles[s3key] = filepath
                return relfiles
        else:
            relfiles_dir = "{}/RELFILES".format(os.path.dirname(filepath))
            if os.path.isdir(relfiles_dir):
                relfiles = {}
                for fpath in glob.glob(f"{relfiles_dir}/*.pdf"):
                    relfiles[os.path.basename(fpath)] = fpath
                return relfiles

    def storage_get_metadata_file(self, filepath):
        """
        :filepath: XML imported filepath

        :returns: metadata filepath or s3key
        :rtype: string
        """
        if self.s3_bucket:
            from botocore.exceptions import ClientError

            metadata_file = f"{self.s3.import_prefix}{filepath}"
            metadata_key = self.s3.ensure_key(metadata_file)
            try:
                head = self.s3.s3cnx.head_object(Key=metadata_key, Bucket=self.s3.bucket)
                if head["ResponseMetadata"].get("HTTPStatusCode") == 200:
                    return metadata_key
            except ClientError as err:
                self.log.error(
                    f"[storage_get_metadata_file]: no {metadata_key} key found in bucket: {err}"
                )

        else:
            directory = os.path.dirname(filepath)
            metadata_file = os.path.join(directory, "metadata.csv")
            if not os.path.isfile(metadata_file):
                self.log.warning(
                    "ignoring PDF directory %s because metadata.csv file is missing", directory
                )
                return None
            return metadata_file

    @contextmanager
    def storage_read_file(self, filepath):
        if self.s3_bucket:
            stream = self.s3_get_file_content(filepath)
            yield TextIOWrapper(Binary(stream), encoding="utf-8", newline="")
        else:
            with open(filepath, "r") as stream:
                yield stream

    def s3_get_file_content(self, filepath):
        """
        Retrun a Binary file content
        """
        if isinstance(filepath, bytes):
            filepath = filepath.decode("utf-8")
        prefixed_key = self.s3.import_prefixed_key(filepath)
        # FIXME some hooks (e.g cubicweb_elasticsearch IndexEsOperation) are
        # called before the final version of key is created in
        # cubicweb_s3storage s3AddFileOp
        # its probably only happens in tests
        for key_ in (prefixed_key, self.s3.suffixed_key(prefixed_key)):
            try:
                return self.s3.download(key_).read()
            except Exception as ex:
                self.log.error("can't retrieve S3 object %s: %s", key_, ex)
                continue
        try:
            return self.s3.download(prefixed_key).read()
        except Exception as ex:
            self.log.error(f"can't retrieve S3 object {prefixed_key}: {ex}")
            return None

    def bfss_get_file_content(self, filepath):
        """
        Retrun a Binary file content
        """
        with open(filepath, "rb") as f:
            return f.read()

    def storage_get_file_content(self, filepath):
        """
        Retrun a Binary file content
        """
        if self.s3_bucket:
            return self.s3_get_file_content(filepath)
        return self.bfss_get_file_content(filepath)

    def storage_get_oaifile_content(self, filepath):
        """
        Retrun a Binary file content for oaifiles
        """
        if self.s3_bucket:
            http_pref = "file://"
            if filepath.startswith(http_pref):
                filepath = filepath.split(http_pref)[1]
            data = self.s3_get_file_content(filepath)
            return BytesIO(data)
        return filepath

    def get_file_sha1(self, filepath):
        if self.s3_bucket:
            binary = self.s3_get_file_content(filepath)
            if binary:
                return usha1(binary)
        else:
            with open(filepath, "rb") as f:
                return usha1(f.read())

    def s3_list_files(self, prefix="/", delimiter="/", start_after=""):
        prefix = prefix[1:] if prefix.startswith(delimiter) else prefix
        start_after = (start_after or prefix) if prefix.endswith(delimiter) else start_after
        s3_paginator = self.s3.s3cnx.get_paginator("list_objects_v2")
        for page in s3_paginator.paginate(
            Bucket=self.s3.bucket, Prefix=prefix, StartAfter=start_after
        ):
            for content in page.get("Contents", ()):
                yield content["Key"]

    def storage_clean_sitemap_files(self, dst):
        """Delete existing sitemap files

        :param str dst: directory or s3 prefix for files to delete
        """
        if self.s3_bucket:
            for key in self.s3_list_files(prefix=dst):
                self.s3.s3cnx.delete_object(Bucket=self.s3.bucket, Key=key)
        else:
            for fname in os.listdir(dst):
                fpath = os.path.join(dst, fname)
                if os.path.isfile(fpath):
                    os.unlink(fpath)
                else:
                    shutil.rmtree(fpath)

    def storage_write_sitemap_ini_file(self, filename, output_dir, buf):
        """
        Write the sitemap_index.xml and robots.txt files

        :param str filename: file name
        :param str output_dir: scnx.vreg.config.get("sitemap-dir") value
        :param StringIO buf: content to write in the file

        """
        extra_args = {}
        if filename.endswith(".xml"):
            extra_args = {"ContentType": "application/xml"}
        if self.s3_bucket:
            key = self.s3.ensure_key("/".join([output_dir, filename]))
            content = Binary(buf.getvalue().encode("utf-8"))
            self.s3.s3cnx.upload_fileobj(content, self.s3.bucket, key, ExtraArgs=extra_args)
        else:
            with open(os.path.join(output_dir, filename), "wb") as sitemap_file:
                sitemap_file.write(buf.getvalue().encode("utf8"))
