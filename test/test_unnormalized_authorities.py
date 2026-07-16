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

# third party imports
# CubicWeb specific imports
import unittest
from cubicweb.devtools.testlib import CubicWebTC

# library specific imports
from pgfixtures import setup_module, teardown_module  # noqa

from cubicweb_francearchives.utils import merge_dicts
from cubicweb_francearchives.utils import (
    register_unnormalized_authority,
    get_unnormalized_authorities,
)
from cubicweb_francearchives.testutils import EADImportMixin, PostgresTextMixin
from cubicweb_francearchives.dataimport.sqlutil import delete_from_filename


def get_indexed_ir(authority):
    return [fa for i in authority.reverse_authority for fa in i.index]


class UnnormalizedAuthoritiesTC(EADImportMixin, PostgresTextMixin, CubicWebTC):
    readerconfig = merge_dicts(
        {}, EADImportMixin.readerconfig, {"reimport": True, "nodrop": False, "force_delete": True}
    )

    @unittest.skip("please, fix cure is now indexed by 4 documents")
    def test_unnormalized_authority_merged(self):
        """
        Trying: import an IR and check the authorities that have been created.
                The subjects "Cure" and "Curé" are merged into the same Subject Authority.
                Create a new SubjectAuthority with the label 'curé' and register it in
                 the unnormalized_authorities table. Then, delete and reimport the IR."
        Expecting: "Cure" and "Curé" are still merged as no SubjectAuthority
                   with exact label "Curé" has been registered as an unnormalized label."
        """
        with self.admin_access.cnx() as cnx:
            filepath = "FRAD095_00374.xml"
            self.import_filepath(cnx, filepath)
            subjects = {e.label: e.eid for e in cnx.find("SubjectAuthority").entities()}
            for label in ("curé", "Curé"):
                self.assertNotIn(label, subjects)
            self.assertIn("Cure", subjects)
            cure = cnx.find("SubjectAuthority", label="Cure").one()
            # cure, curé, Cure are indexed by 5 documents
            self.assertEqual(5, len(get_indexed_ir(cure)))
            # create and register curé label in the unnormalized_authorities table
            accentuated_cure = cnx.create_entity("SubjectAuthority", label="curé")
            cnx.commit()
            register_unnormalized_authority(cnx, accentuated_cure.label, accentuated_cure.eid)
            self.assertEqual(
                {accentuated_cure.label: accentuated_cure.eid}, get_unnormalized_authorities(cnx)
            )
            # delete the imported IR and reimport the filepath
            delete_from_filename(cnx, filepath, interactive=False, esonly=False)
            cnx.commit()
            self.import_filepath(cnx, filepath)
            subjects = [e.label for e in cnx.find("SubjectAuthority").entities()]
            cure = cnx.entity_from_eid(cure.eid)
            # cure is now indexed by 4 documents
            self.assertEqual(4, len(get_indexed_ir(cure)))
            # curé is indexed on its own autority
            accentuated_cure = cnx.entity_from_eid(accentuated_cure.eid)
            self.assertEqual(1, len(get_indexed_ir(accentuated_cure)))

    def test_unnormalized_authority_not_merged(self):
        """
        Trying: import an IR and check the authorities that have been created.
                The Subjects "Cure" and "Curé" are merged into the same SubjectAuthority.
                Create a new SubjectAuthority with the label "Curé" and register "Curé"
                and "cure" in unnormalized_authorities table. Delete and reimport IR.

        Expecting: "Curé" and "Cure" are not merged. "Curé" is aligned to the right authorty.
        """
        with self.admin_access.cnx() as cnx:
            filepath = "FRAD095_00374.xml"
            self.import_filepath(cnx, filepath)
            subjects = {e.label: e.eid for e in cnx.find("SubjectAuthority").entities()}
            for label in ("curé", "Curé"):
                self.assertNotIn(label, subjects)
            self.assertIn("Cure", subjects)
            cure = cnx.find("SubjectAuthority", label="Cure").one()
            # cure, curé, Cure are indexed by 5 documents
            self.assertEqual(5, len(get_indexed_ir(cure)))
            # create and register Curé label
            accentuated_cure = cnx.create_entity("SubjectAuthority", label="Curé")
            cnx.commit()
            register_unnormalized_authority(cnx, accentuated_cure.label, accentuated_cure.eid)
            register_unnormalized_authority(cnx, cure.label, cure.eid)
            # both labels must be registered in unnormalized authorities
            self.assertDictEqual(
                {accentuated_cure.label: accentuated_cure.eid, cure.label: cure.eid},
                get_unnormalized_authorities(cnx),
            )
            # delete the imported IR aend reimport the filepath
            delete_from_filename(cnx, filepath, interactive=False, esonly=False)
            cnx.commit()
            self.import_filepath(cnx, filepath)
            # cure is now indexed by 1 document
            cure = cnx.entity_from_eid(cure.eid)
            self.assertEqual(1, len(get_indexed_ir(cure)))
            # Curé is indexed by 1 document
            accentuated_cure = cnx.entity_from_eid(accentuated_cure.eid)
            self.assertEqual(1, len(get_indexed_ir(accentuated_cure)))

    def test_unnormalized_authority_lower_not_merged(self):
        """
        Trying: create two Subjects "Cure" and "Curé". Register the labels "cure" and "curé"
                in the unnormalized_authorities table with their corresponding authorities.
        Expecting: The labels "Curé" and "Cure" are merged.
               The labels "cure" and "curé" are not merged.
        """
        with self.admin_access.cnx() as cnx:
            lower_cure = cnx.create_entity("SubjectAuthority", label="cure")
            lower_accentuated_cure = cnx.create_entity("SubjectAuthority", label="curé")
            cnx.commit()
            register_unnormalized_authority(cnx, lower_cure.label, lower_cure.eid)
            register_unnormalized_authority(
                cnx, lower_accentuated_cure.label, lower_accentuated_cure.eid
            )
            self.assertDictEqual(
                {
                    lower_cure.label: lower_cure.eid,
                    lower_accentuated_cure.label: lower_accentuated_cure.eid,
                },
                get_unnormalized_authorities(cnx),
            )

            filepath = "FRAD095_00374.xml"
            self.import_filepath(cnx, filepath)
            # Cure is indexed by 2 documents
            cure = cnx.find("SubjectAuthority", label="Cure").one()
            self.assertEqual(2, len(get_indexed_ir(cure)))
            self.assertFalse(cnx.find("SubjectAuthority", label="Curé"))
            lower_cure = cnx.entity_from_eid(lower_cure.eid)
            self.assertEqual(2, len(get_indexed_ir(lower_cure)))
            lower_accentuated_cure = cnx.entity_from_eid(lower_accentuated_cure.eid)
            self.assertEqual(1, len(get_indexed_ir(lower_accentuated_cure)))
