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

import os
import os.path as osp
from PIL import Image

import unittest

from cubicweb import Binary
from cubicweb_web.devtools.testlib import WebCWTC

from cubicweb_francearchives.cssimages import static_css_dir, HERO_SIZES
from cubicweb_francearchives.testutils import S3BfssStorageTestMixin


class ImageTests(S3BfssStorageTestMixin, WebCWTC):
    def setup_database(self):
        self.static_dir = static_css_dir(self.config.static_directory)

    def tearDown(self):
        self.cleanup_static_css()
        super(ImageTests, self).tearDown()

    def cleanup_static_css(self):
        directory = static_css_dir(self.config.static_directory)
        if self.s3_bucket_name:
            # TODO delete files
            pass
        else:
            for fname in os.listdir(directory):
                fullname = osp.join(directory, fname)
                os.unlink(fullname)

    def static_filepath(self, filepath):
        if self.s3_bucket_name:
            return f"static/css/{filepath}"
        return osp.join(self.static_dir, filepath)

    def test_generate_thumbnails(self):
        """do not generate thumbnailes as cssid is specified"""
        with self.admin_access.cnx() as cnx:
            section = cnx.create_entity("Section", name="decouvrir", title="Découvrir")
            # upload the image for s3
            self.get_or_create_imported_filepath("hero-decouvrir.jpg")
            filepath = osp.join(self.datadir, "hero-decouvrir.jpg")
            orig_width, orig_height = Image.open(filepath).size
            with open(filepath, "rb") as stream:
                content = stream.read()
            image_file = cnx.create_entity(
                "File",
                data_name="hero-decouvrir.jpg",
                data_format="image/jpeg",
                data=Binary(content),
            )
            cnx.create_entity(
                "CssImage",
                cssid="hero-decouvrir",
                caption="Décourvir 15",
                order=2,
                cssimage_of=section,
                image_file=image_file,
            )
            cnx.commit()
            for size, suffix in HERO_SIZES:
                image_path = "hero-decouvrir-%s.jpg" % suffix
                content = self.getFileContent(self.static_filepath(image_path))
                from io import BytesIO

                image = Image.open(BytesIO(content))
                self.assertEqual(image.size[0], size["w"] or orig_width)

    def test_dont_generate_thumbnails(self):
        """do not generate thumbnailes as cssid is not specified"""
        with self.admin_access.cnx() as cnx:
            self.get_or_create_imported_filepath("hero-decouvrir.jpg")
            with open(osp.join(self.datadir, "hero-decouvrir.jpg"), "rb") as stream:
                content = stream.read()
            cnx.create_entity(
                "File",
                title="static/css/decouvrir.jpg",
                data_name="hero-decouvrir.jpg",
                data_format="image/jpeg",
                data=Binary(content),
                reverse_image_file=cnx.create_entity("Image", caption="Décourvir 15"),
            )
            cnx.commit()
            for size, suffix in HERO_SIZES:
                image_path = "hero-decouvrir-%s.jpg" % suffix
                self.assertFalse(self.fileExists(self.static_filepath(image_path)))

    def test_update_thumbnails(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            self.get_or_create_imported_filepath("hero-decouvrir.jpg")
            with open(osp.join(self.datadir, "hero-decouvrir.jpg"), "rb") as stream:
                image_file = ce(
                    "File",
                    data_name="hero-decouvrir.jpg",
                    data_format="image/jpeg",
                    data=Binary(stream.read()),
                )
                ce("CssImage", cssid="hero-gerer", order=1, caption="Gerer", image_file=image_file)
                cnx.commit()
            sm_filename = self.static_filepath("hero-gerer-sm.jpg")
            content = self.getFileContent(sm_filename)
            image = cnx.find("CssImage", cssid="hero-gerer").one()
            self.get_or_create_imported_filepath("hero-gerer.jpg")
            with open(osp.join(self.datadir, "hero-gerer.jpg"), "rb") as stream:
                image.image_file[0].cw_set(data=Binary(stream.read()))
                cnx.commit()
            new_content = self.getFileContent(sm_filename)
            self.assertNotEqual(content, new_content)

    def test_dont_update_thumbnails(self):
        with self.admin_access.cnx() as cnx:
            ce = cnx.create_entity
            self.get_or_create_imported_filepath("hero-gerer.jpg")
            sm_filename = self.static_filepath("hero-gerer-sm.jpg")
            with open(osp.join(self.datadir, "hero-decouvrir.jpg"), "rb") as stream:
                image_file = ce(
                    "File",
                    data_name="hero-decouvrir.jpg",
                    data_format="image/jpeg",
                    data=Binary(stream.read()),
                )
                ce("Image", caption="Gerer", image_file=image_file)
                cnx.commit()
            self.assertFalse(self.isFile(sm_filename))
            image = cnx.find("Image").one()
            with open(osp.join(self.datadir, "hero-gerer.jpg"), "rb") as stream:
                image.image_file[0].cw_set(data=Binary(stream.read()))
                cnx.commit()
            self.assertFalse(self.isFile(sm_filename))


if __name__ == "__main__":
    unittest.main()
