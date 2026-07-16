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

"""cubicweb-francearchives cssimages"""

from io import BytesIO
import os.path as osp
from PIL import Image

from cubicweb import Binary

from cubicweb_francearchives import static_css_dir, S3_ACTIVE

# sizes from css
HERO_SIZES = (
    ({"w": 544}, "xs"),
    ({"w": 768}, "sm"),
    ({"w": 922}, "md"),
    ({"w": 1200}, "lg"),
    ({"w": None, "q": 5}, "lr"),
    ({"w": None}, "xl"),
)


def thumbnail_name(basename, suffix, ext):
    return "{}-{}{}".format(basename, suffix, ext)


def generate_thumbnails(cnx, image_file, image_path, sizes):
    """generate X images for given sizes"""
    static_dir = static_css_dir(cnx.vreg.config.static_directory)
    for size, suffix in sizes:
        image_file.seek(0)
        thumb = Image.open(image_file)
        orig_width, orig_height = thumb.size
        width = size.get("w", orig_width) or orig_width
        height = size.get("h", orig_height) or orig_height
        quality = size.get("q", 100)
        thumb.thumbnail((width, height), Image.LANCZOS)
        basename, ext = osp.splitext(image_path)
        thumb_name = thumbnail_name(basename, suffix, ext)
        if S3_ACTIVE:
            byte_io = BytesIO()
            thumb.save(byte_io, "PNG", quality=quality)
            content = byte_io.getvalue()
        else:
            thumbpath = osp.join(static_dir, thumb_name)
            thumb.save(thumbpath, quality=quality)
            with open(thumbpath, "rb") as thumbfile:
                content = thumbfile.read()
        cnx.create_entity(
            "File",
            **{
                "title": f"static/css/{thumb_name}",
                "data": Binary(content),
                "data_format": image_file.data_format,
                "data_name": thumb_name,
            },
        )
