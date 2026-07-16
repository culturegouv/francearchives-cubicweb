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
import csv
import tempfile
import os.path
import shutil

# third party imports
# CubicWeb specific imports
from cubicweb_web.devtools.testlib import WebCWTC

# library specific imports
from cubicweb_francearchives.scripts import cleanup


class CleanupTest(WebCWTC):
    def setUp(self):
        """Set test cases up."""
        super().setUp()
        with self.admin_access.cnx() as cnx:
            cnx.create_entity("AgentAuthority", label="foo\t\tbar\n\nbaz")
            cnx.create_entity("LocationAuthority", label="foo  bar foobar")
            cnx.create_entity("SubjectAuthority", label="foo\u0090bar")
            cnx.commit()

    def test_clean(self):
        with self.admin_access.cnx() as cnx:
            expected = ["foo bar baz", "foo bar foobar", "foobar"]
            labels = [
                row[0]
                for row in cnx.system_sql(
                    """SELECT cw_label FROM cw_agentauthority UNION
                    SELECT cw_label FROM cw_locationauthority UNION
                    SELECT cw_label FROM cw_subjectauthority"""
                )
            ]
            self.assertCountEqual(expected, cleanup.clean(*labels))

    def test_import_clean(self):
        tempdir = tempfile.mkdtemp()
        filenames = [
            os.path.join(tempdir, "agent_clean.csv"),
            os.path.join(tempdir, "location_clean.csv"),
            os.path.join(tempdir, "subject_clean.csv"),
        ]
        with self.admin_access.cnx() as cnx:
            try:
                headers = ("", "", "", "")
                for etype, authority, filename in zip(
                    ("AgentAuthority", "LocationAuthority", "SubjectAuthority"),
                    ("agent", "location", "subject"),
                    filenames,
                ):
                    with open(filename, "w") as fp:
                        writer = csv.writer(fp)
                        entity = cnx.execute("Any X WHERE X is {}".format(etype)).one()
                        clean = list(cleanup.clean(entity.label))[0]
                        writer.writerows(
                            [headers, (entity.eid, "", entity.label, clean, authority)]
                        )
                cleanup.import_clean(cnx, *filenames)
                expected = ["foo bar baz", "foo bar foobar", "foobar"]
                labels = [
                    row[0]
                    for row in cnx.system_sql(
                        """SELECT cw_label FROM cw_agentauthority UNION
                        SELECT cw_label FROM cw_locationauthority UNION
                        SELECT cw_label FROM cw_subjectauthority"""
                    )
                ]
                self.assertCountEqual(expected, labels)
            except:  # noqa
                raise
            finally:
                shutil.rmtree(tempdir)
