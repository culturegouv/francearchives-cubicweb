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

from datetime import datetime
import unittest

from cubicweb_web.devtools.testlib import WebCWTC
from lxml import etree

import os
from os import path as osp

from cubicweb.dataimport.stores import RQLObjectStore

from cubicweb_francearchives.dataimport import (
    dc,
    usha1,
    CSVIntegrityError,
    service_infos_from_filepath,
    load_services_map,
    normalize_entry,
)
from cubicweb_francearchives.entities.es import DZFacetValues
from cubicweb_francearchives.testutils import (
    XMLCompMixin,
    PostgresTextMixin,
    S3BfssStorageTestMixin,
)
from cubicweb_francearchives.utils import pick

from pgfixtures import setup_module, teardown_module  # noqa


class CSVImportMixIn(XMLCompMixin, S3BfssStorageTestMixin):
    def setUp(self):
        super(CSVImportMixIn, self).setUp()
        import_dir = self.datapath("tmp")
        self.config.set_option("appfiles-dir", import_dir)
        if not osp.isdir(import_dir):
            os.mkdir(import_dir)

    def csv_filepath(self, filepath):
        return self.get_or_create_imported_filepath(f"csv/{filepath}")

    def _test_medatadata_csv(self, cnx, service=None, fa=None):
        if not service:
            service = cnx.entity_from_eid(self.service_eid)
        if fa is None:
            fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
            fac_count = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")[0][0]
            self.assertEqual(10, fac_count)
        self.assertEqual(fa.name, "FRAD092_9FI_cartes-postales.csv")
        self.assertEqual(fa.eadid, "FRAD092_9FI_cartes-postales")
        self.assertEqual(fa.did[0].unitid, None)
        self.assertEqual(fa.did[0].unittitle, "Cartes postales anciennes")
        self.assertEqual(fa.did[0].unitdate, "1900 - 1944-05-31")
        self.assertEqual(fa.did[0].startyear, 1900)
        self.assertEqual(fa.did[0].stopyear, 1944)
        self.assertEqual(fa.did[0].origination, "Archives des Hauts-de-Seine")
        self.assertEqual(fa.did[0].lang_description, "italien")
        self.assertEqual(
            fa.did[0].extptr, "https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/"
        )
        self.assertEqual(fa.fa_header[0].titleproper, "Cartes postales anciennes")
        self.assertIn('<div class="ead-p">5 cartons</div>', fa.did[0].physdesc)
        self.assertIn(
            '<div class="ead-p">Cartes postales anciennes (1900-1944)</div>', fa.scopecontent
        )
        self.assertIn(
            '<div class="ead-p">Collection photographie département Essonne.</div>',
            fa.additional_resources,
        )
        self.assertIn('<div class="ead-p">Libre accès</div>', fa.accessrestrict)
        self.assertIn('<div class="ead-p">Libre de droit</div>', fa.userestrict)
        self.assertEqual(fa.publisher, "AD 92")
        self.assertEqual(fa.service[0].eid, service.eid)
        self.assertEqual(fa.findingaid_support[0].data_name, "FRAD092_9FI_cartes-postales.csv")
        self.assertEqual(fa.findingaid_support[0].data_format, "text/csv")
        index_entries = sorted(
            [(ie.authority[0].cw_etype, ie.authority[0].label, ie.role) for ie in fa.reverse_index]
        )
        self.assertCountEqual(
            index_entries,
            [
                ("AgentAuthority", "Alphonse Germain", "index"),
                ("AgentAuthority", "Archives des Hauts-de-Seine", "originator"),
                ("AgentAuthority", "Jules Ferry", "index"),
                ("AgentAuthority", "Service des postes", "index"),
                ("LocationAuthority", "Antony (Hauts-de-Seine)", "index"),
                ("LocationAuthority", "Corse (France ; département)", "index"),
                (
                    "LocationAuthority",
                    "Digne-les-Bains (Alpes-de-Haute-Provence, France ; arrondissement )",
                    "index",
                ),
                ("LocationAuthority", "Digne-les-Bains (Alpes-de-Haute-Provence, France)", "index"),
                ("LocationAuthority", "Hauts-de-Seine", "index"),
                ("LocationAuthority", "Paris", "index"),
                (
                    "LocationAuthority",
                    "Sisteron (Alpes-de-Haute-Provence, France ; arrondissement)",
                    "index",
                ),
                ("LocationAuthority", "méditerranée (mer)", "index"),
                ("SubjectAuthority", "Cartes postales", "index"),
                ("SubjectAuthority", "photographie", "index"),
                ("SubjectAuthority", "urbanisation", "index"),
            ],
        )
        facs_rset = cnx.execute("Any FA WHERE FA finding_aid F, F eid %(e)s", {"e": fa.eid})
        self.assertEqual(facs_rset.rowcount, 10)
        facs = sorted(facs_rset.entities(), key=lambda fac: fac.did[0].unitid)
        fac1 = facs[0]
        self.assertIn('<div class="ead-p">Est développée la notion', fac1.scopecontent)
        self.assertIn('<div class="ead-p">Collection photographie, BNF', fac1.additional_resources)
        self.assertIn('<div class="ead-p">Libre accès</div>', fac1.accessrestrict)
        self.assertIn('<div class="ead-p">Libre de droit</div>', fac1.userestrict)
        self.assertEqual(fac1.did[0].unitid, "9FI/BAG_10")
        self.assertEqual(fac1.did[0].unittitle, "Le Dépot des Tramways")
        self.assertEqual(fac1.did[0].unitdate, "1900")
        self.assertEqual(fac1.did[0].startyear, 1900)
        self.assertEqual(fac1.did[0].stopyear, 1900)
        self.assertEqual(fac1.did[0].origination, "Archives privées Mr X")
        self.assertEqual(fac1.did[0].lang_description, None)
        self.assertIn('<div class="ead-p">12x19 cm</div>', fac1.did[0].physdesc)
        self.assertEqual(len(fac1.digitized_versions), 2)
        self.assertEqual(
            fac1.digitized_versions[0].url,
            "https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/table/?sort=id",
        )
        self.assertEqual(
            fac1.digitized_versions[1].illustration_url,
            "https://opendata.hauts-de-seine.fr/api/datasets/1.0/cartes-postales/images/8ee3d34b124926666f78afa361566542",  # noqa
        )
        index_entries = [
            (ie.authority[0].cw_etype, ie.authority[0].label, ie.role) for ie in fac1.reverse_index
        ]
        self.assertCountEqual(
            index_entries,
            [
                ("SubjectAuthority", "Bâtiment public > Gare", "index"),
                ("AgentAuthority", "Charles Baudelaire", "index"),
                ("LocationAuthority", "Bagneux", "index"),
                ("SubjectAuthority", "photographie", "index"),
                ("AgentAuthority", "Archives privées Mr X", "originator"),
            ],
        )
        fac5 = facs[5]
        self.assertIn('<div class="ead-p">Duis aute irure dolor in', fac5.scopecontent)
        self.assertEqual(fac5.additional_resources, None)
        self.assertIn('<div class="ead-p">Libre accès</div>', fac5.accessrestrict)
        self.assertIn('<div class="ead-p">Libre de droit</div>', fac5.userestrict)
        self.assertEqual(fac5.did[0].unitid, "9FI/BAG_21")
        self.assertEqual(fac5.did[0].unittitle, "La Sous-Station Electrique")
        self.assertEqual(fac5.did[0].unitdate, "1900")
        self.assertEqual(fac5.did[0].startyear, 1900)
        self.assertEqual(fac5.did[0].stopyear, 1900)
        self.assertEqual(fac5.did[0].origination, "Entreprise Pajol")
        self.assertEqual(fac5.did[0].lang_description, None)
        self.assertIn('<div class="ead-p">17x19 cm</div>', fac5.did[0].physdesc)
        self.assertEqual(len(fac5.digitized_versions), 1)
        self.assertEqual(
            fac5.digitized_versions[0].url,
            "https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/table/?sort=id",
        )  # noqa
        self.assertEqual(fac5.digitized_versions[0].illustration_url, None)
        index_entries = [
            (ie.authority[0].cw_etype, ie.authority[0].label, ie.role) for ie in fac5.reverse_index
        ]
        self.assertCountEqual(
            index_entries,
            [
                ("SubjectAuthority", "Bâtiment public", "index"),
                ("AgentAuthority", "Emma Bovary", "index"),
                ("AgentAuthority", "Claudette Levy", "index"),
                ("AgentAuthority", "Société Beguin-Say", "index"),
                ("LocationAuthority", "Bagneux", "index"),
                ("SubjectAuthority", "photographie", "index"),
                ("AgentAuthority", "Entreprise Pajol", "originator"),
            ],
        )
        # not illustration_url for fac3 dao as its length is > 512
        fac3 = facs[3]
        self.assertEqual(fac3.did[0].unitid, "9FI/BAG_19")
        self.assertEqual(len(fac3.digitized_versions), 1)
        self.assertEqual(
            fac3.digitized_versions[0].url,
            "https://opendata.hauts-de-seine.fr/explore/dataset/cartes-postales/table/?sort=id",
        )
        self.assertEqual(
            fac3.digitized_versions[0].illustration_url,
            None,
        )  # noqa


class CSVDCImportTC(CSVImportMixIn, PostgresTextMixin, WebCWTC):
    readerconfig = {
        "noes": True,
        "esonly": False,
        "appid": "data",
        "nodrop": False,
        "dc_no_cache": True,
        "index-name": "dummy",
    }

    def setUp(self):
        super(CSVDCImportTC, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service_eid = cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            ).eid
            cnx.commit()

    def test_import_findingaid_esonly(self):
        with self.admin_access.cnx() as cnx:
            fpath = self.csv_filepath("frmaee_findingaid.csv")
            config = self.readerconfig.copy()
            config["esonly"] = True
            store = RQLObjectStore(cnx)
            importer = dc.CSVReader(config, store)
            services_map = load_services_map(cnx)
            service_infos = service_infos_from_filepath(fpath, services_map)
            es_docs = [e["_source"] for e in importer.import_filepath(service_infos, fpath)]
            self.assertEqual(len(es_docs), 4)
            fa_docs = [
                e for e in es_docs if e["stable_id"] == "444ba40fb5ab981a1c9a1b47615c77005db0d8de"
            ]
            service = fa_docs[0].pop("service")
            self.assertEqual(set(service.keys()), {"code", "eid", "level", "title"})
            did = fa_docs[0].pop("did")
            self.assertEqual(set(did.keys()), {"unitid", "unittitle"})
            # no dates found in did
            self.assertEqual(
                set(fa_docs[0].keys()),
                {
                    "alltext",
                    "escategory",
                    "cw_etype",
                    "eid",
                    "stable_id",
                    "fa_stable_id",
                    "index_entries",
                    "scopecontent",
                    "eadid",
                    "creation_date",
                    "originators",
                    "digitized",
                    "digitized_all",
                },
            )
            self.assertEqual(["frmaee"], fa_docs[0]["originators"])
            for attr in ("year", "sortdate", "stopyear", "startyear"):
                self.assertNotIn(attr, fa_docs[0])

    def test_import_one_facomponent_esonly(self):
        with self.admin_access.cnx() as cnx:
            fpath = self.csv_filepath("frmaee_findingaid.csv")
            config = self.readerconfig.copy()
            config["esonly"] = True
            store = RQLObjectStore(cnx)
            importer = dc.CSVReader(config, store)
            services_map = load_services_map(cnx)
            service_infos = service_infos_from_filepath(fpath, services_map)
            es_docs = [e["_source"] for e in importer.import_filepath(service_infos, fpath)]
            es_docs = [e for e in es_docs if e["cw_etype"] == "FAComponent"]
            self.assertEqual(len(es_docs), 3)
            es_doc = [e for e in es_docs if e["did"]["unitid"] == "TRA13680001"][0]
            self.assertEqual(
                set(es_doc.keys()),
                {
                    "escategory",
                    "eid",
                    "cw_etype",
                    "did",
                    "stable_id",
                    "fa_stable_id",
                    "index_entries",
                    "eadid",
                    "scopecontent",
                    "digitized",
                    "digitized_all",
                    "creation_date",
                    "sortdate",
                    "startyear",
                    "stopyear",
                    "dates",
                    "service",
                    "originators",
                },
            )
            for attr in ("year",):
                self.assertNotIn(attr, es_doc)
            es_index_entries = es_doc["index_entries"]
            self.assertTrue(all("type" in i and "label" in i for i in es_index_entries))
            self.assertEqual(len(es_index_entries), 6)
            es_doc = pick(es_doc, *(set(es_doc) - {"extid", "stable_id"}))
            # ensure `index_entries` list is alway in same order
            es_doc["index_entries"] = sorted(
                es_doc["index_entries"], key=lambda k: normalize_entry(k["label"])
            )
            self.assertTrue(es_doc.pop("creation_date"))
            self.assertCountEqual(
                es_doc,
                {
                    "cw_etype": "FAComponent",
                    "dates": {"gte": 1500, "lte": 1500},
                    "did": {
                        "unitid": "TRA13680001",
                        "unittitle": "Recueil de traités (1368-1408)",
                    },
                    "digitized": True,
                    "digitized_all": DZFacetValues.nondz,
                    "eadid": None,
                    "eid": None,
                    "escategory": "archives",
                    "fa_stable_id": "d8e6d65766871576a026b2a75b3fc2fa349d6040",
                    "index_entries": [
                        {
                            "label": "Clermont-Ferrand",
                            "type": "geogname",
                            "authority": None,
                            "authfilenumber": None,
                            "authtype": "LocationAuthority",
                        },
                        {
                            "label": "corporname",
                            "type": "corpname",
                            "authority": None,
                            "authfilenumber": None,
                            "authtype": "AgentAuthority",
                        },
                        {
                            "label": "Henri VII",
                            "type": "persname",
                            "authority": None,
                            "authfilenumber": None,
                            "authtype": "AgentAuthority",
                        },
                        {
                            "label": "subject",
                            "type": "subject",
                            "role": "index",
                            "authority": None,
                            "authfilenumber": None,
                            "authtype": "SubjectAuthority",
                        },
                        {
                            "authfilenumber": None,
                            "authority": None,
                            "label": "type1",
                            "type": "genreform",
                            "authtype": "SubjectAuthority",
                        },
                        {
                            "authfilenumber": None,
                            "authority": None,
                            "label": "origine1",
                            "role": "index",
                            "type": "originator",
                            "authtype": "AgentAuthority",
                        },
                    ],
                    "originators": ["origine1"],
                    "scopecontent": "Validit\xe9 du trait\xe9 : historique.",
                    "sortdate": "1500-01-01",
                    "startyear": 1500,
                    "stopyear": 1500,
                    "service": {"eid": None, "level": "None", "code": "FRMAEE", "title": "FRMAEE"},
                },
            )
            self.assertEqual(["origine1"], es_doc["originators"])

    def test_import_filepath(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("frmaee_findingaid.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                did = fa.did[0]
                self.assertEqual(fa.name, "frmaee_findingaid.csv")
                self.assertEqual(fa.eadid, "frmaee_findingaid")
                self.assertEqual(fa.publisher, "FRMAEE")
                self.assertEqual(fa.scopecontent, None)
                self.assertEqual(fa.additional_resources, None)
                self.assertEqual(fa.accessrestrict, None)
                self.assertEqual(fa.userestrict, None)
                self.assertEqual(did.unitid, None)
                self.assertEqual(did.unittitle, "frmaee_findingaid")
                self.assertEqual(did.unitdate, None)
                self.assertEqual(did.startyear, None)
                self.assertEqual(did.stopyear, None)
                self.assertEqual(did.origination, "frmaee")
                self.assertEqual(did.lang_description, None)
                self.assertEqual(fa.fa_header[0].titleproper, "frmaee_findingaid")
                self.assertEqual(fa.findingaid_support[0].data_name, "frmaee_findingaid.csv")
                self.assertEqual(fa.findingaid_support[0].data_format, "text/csv")
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label, ie.role)
                    for ie in fa.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("AgentAuthority", "frmaee", "originator"),
                    ],
                )
                dids_rset = cnx.execute("Any D WHERE D is Did")
                self.assertEqual(len(dids_rset), 4)
                ies_rset = cnx.execute("Any X WHERE X is IN (AgentName, Geogname, Subject)")
                self.assertEqual(len(ies_rset), 13)
                dvs_rset = cnx.execute("Any D WHERE D is DigitizedVersion")
                self.assertEqual(len(dvs_rset), 5)
                facs_rset = cnx.execute("Any F WHERE F is FAComponent")
                self.assertEqual(len(facs_rset), 3)
                facs = list(facs_rset.entities())
                facs.sort(key=lambda fac: fac.did[0].unitid)
                fac1, fac2, fac3 = facs
                fac1_did = fac1.did[0]
                self.assertIn("Validité du traité : historique.", fac1.scopecontent)
                self.assertIn("Ressource complementaire 1", fac1.additional_resources)
                self.assertIn('<div class="ead-p">Libre accès</div>', fac1.accessrestrict)
                self.assertIn('<div class="ead-p">Libre de droit</div>', fac1.userestrict)
                self.assertEqual(fac1_did.unitid, "TRA13680001")
                self.assertEqual(fac1_did.unittitle, "Recueil de traités (1368-1408)")
                self.assertEqual(fac1_did.unitdate, "1500-01-01")
                self.assertEqual(fac1_did.startyear, 1500)
                self.assertEqual(fac1_did.stopyear, 1500)
                self.assertEqual(fac1_did.origination, "origine1")
                self.assertIn('<div class="ead-p">fra</div>', fac1_did.lang_description)
                self.assertIn('<div class="ead-p">Format 1</div>', fac1_did.physdesc)
                self.assertEqual(len(fac1.digitized_versions), 2)
                expected_dao = [
                    (d.role, d.illustration_url, d.url) for d in fac1.digitized_versions
                ]
                self.assertCountEqual(
                    expected_dao,
                    [
                        (
                            None,
                            None,
                            "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13680001",  # noqa
                        ),
                        ("thumbnail", "img1", None),
                    ],
                )
                self.assertEqual(
                    fac1.digitized_urls[0],
                    "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13680001",
                )
                self.assertEqual(fac1.illustration_url, None)
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label, ie.role)
                    for ie in fac1.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "type1", "index"),
                        ("SubjectAuthority", "subject", "index"),
                        ("AgentAuthority", "corporname", "index"),
                        ("AgentAuthority", "Henri VII", "index"),
                        ("LocationAuthority", "Clermont-Ferrand", "index"),
                        ("AgentAuthority", "origine1", "originator"),
                    ],
                )
                self.assertIn(
                    "Validité du traité : historique. Lieu de signature : Vincennes.",
                    fac2.scopecontent,
                )
                self.assertIn("Ressource complementaire 2", fac2.additional_resources)
                self.assertIn('<div class="ead-p">Libre accès</div>', fac2.accessrestrict)
                self.assertIn('<div class="ead-p">Libre de droit</div>', fac2.userestrict)
                self.assertEqual(fac1.component_order, 0)
                fac2_did = fac2.did[0]
                self.assertEqual(fac2_did.unitid, "TRA13690001")
                self.assertEqual(fac2_did.unittitle, "Lettres patentes de Charles V, roi de France")
                self.assertEqual(fac2_did.unitdate, "1671-07-11 - 1683-09-13")
                self.assertEqual(fac2_did.startyear, 1671)
                self.assertEqual(fac2_did.stopyear, 1683)
                self.assertIn("Format 2", fac2_did.physdesc)
                self.assertIn('<div class="ead-p">eng</div>', fac2_did.lang_description)
                self.assertIn('<div class="ead-p">Format 2</div>', fac2_did.physdesc)
                self.assertEqual(fac2_did.origination, "origine2")
                self.assertEqual(len(fac2.digitized_versions), 2)
                expected_dao = [
                    (d.role, d.illustration_url, d.url) for d in fac2.digitized_versions
                ]
                self.assertCountEqual(
                    expected_dao,
                    [
                        (
                            None,
                            None,
                            "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13690001",  # noqa
                        ),
                        ("thumbnail", "http://www.diplomatie.gouv.fr/img2", None),
                    ],
                )

                self.assertEqual(
                    fac2.digitized_urls[0],
                    "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA13690001",
                )
                self.assertEqual(fac2.illustration_url, "http://www.diplomatie.gouv.fr/img2")
                self.assertEqual(len(fac2.reverse_index), 6)
                index_entries = [
                    (ie.authority[0].cw_etype, ie.authority[0].label, ie.role)
                    for ie in fac2.reverse_index
                ]
                self.assertCountEqual(
                    index_entries,
                    [
                        ("SubjectAuthority", "type2", "index"),
                        ("SubjectAuthority", "subject2", "index"),
                        ("AgentAuthority", "corporname2", "index"),
                        ("AgentAuthority", "Charles V", "index"),
                        ("LocationAuthority", "Paris", "index"),
                        ("AgentAuthority", "origine2", "originator"),
                    ],
                )
                fac3_did = fac3.did[0]
                self.assertEqual(fac2.component_order, 1)
                self.assertEqual(fac3_did.physdesc, None)
                self.assertEqual(fac3_did.lang_description, None)
                self.assertEqual(fac3.additional_resources, None)
                self.assertEqual(fac3_did.origination, None)
                self.assertEqual(fac3_did.unitid, "TRA13690003")
                self.assertEqual(
                    fac3.digitized_versions[0].url,
                    "http://www.diplomatie.gouv.fr/traites/affichetraite.do?accord=TRA15590001",
                )
                self.assertEqual(fac3.digitized_versions[0].illustration_url, None)
                self.assertEqual(fac3.component_order, 2)
                self.assertEqual(len(fac3.reverse_index), 0)

    def test_findingaid_support_hash_csv_without_metadatafile(self):
        """
        Trying: import csv file without metadata
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
                self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
                self.assertTrue(fa_support.check_hash())

    def test_import_csv_without_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                dc.import_filepath(cnx, config, fpath)
                self._test_medatadata_csv(cnx)

    def test_import_csv_with_metadatafile_symlink(self):
        """
        Trying: import csv file with metadata
        Expecting: a symlink to the appfiles-dir is set for the csv file
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                config["appfiles-dir"] = self.config["appfiles-dir"]
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                csvfile = cnx.execute("Any F WHERE X findingaid_support F").one()
                self.assertEqual(csvfile.data_hash, csvfile.compute_hash())
                self.assertTrue(csvfile.check_hash())
                destpath = f"{csvfile.data_hash}_{osp.basename(fpath)}"
                if not self.s3_bucket_name:
                    destpath = osp.join(self.config["appfiles-dir"], destpath)
                self.assertNotEqual(destpath, fpath)
                self.assertTrue(self.fileExists(destpath))
                if not self.s3_bucket_name:
                    self.assertTrue(osp.islink(destpath))

    def test_findingaid_support_hash_csv_with_metadatafile(self):
        """
        Trying: import csv file with metadata
        Expecting: findingaid_support data_hash is correctly set
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_support = cnx.execute("Any X WHERE F findingaid_support X").one()
                self.assertEqual(fa_support.data_hash, fa_support.compute_hash())
                self.assertTrue(fa_support.check_hash())

    def test_import_csv_with_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)

    def test_metadata_csv_failed(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport a similar but same file
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales-ko.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_rset = cnx.execute("Any COUNT(FA) WHERE FA is FindingAid")
                self.assertEqual(fa_rset[0][0], 2)
                facs_rset = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")
                self.assertEqual(facs_rset[0][0], 18)
                fa = cnx.find("FindingAid", eadid="FRAD092_9FI_cartes-postales").one()
                self._test_medatadata_csv(cnx, fa=fa)

    def test_metadata_reimport_csv_tab_dialect(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_rset = cnx.execute("Any COUNT(FA) WHERE FA is FindingAid")
                self.assertEqual(fa_rset[0][0], 1)
                facs_rset = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")
                self.assertEqual(facs_rset[0][0], 10)
                # reimport a file with data separated by a tabulation
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales-tab.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa_rset = cnx.execute("Any COUNT(FA) WHERE FA is FindingAid")
                self.assertEqual(fa_rset[0][0], 1)
                facs_rset = cnx.execute("Any COUNT(FA) WHERE FA is FAComponent")
                self.assertEqual(facs_rset[0][0], 10)

    def test_metadata_csv_wrong_identifier(self):
        """
        Trying: process a fname which not exists in "identifiant_fichier" column of metadata.csv
        Expecting: CSVIntegrityError is raised
        """
        metadata_filepath = self.csv_filepath("metadata.csv")
        with self.assertRaises(CSVIntegrityError):
            fname = "FRAD092_9F2_cartes-postales.csv"
            dc.csv_metadata_without_cache(fname, metadata_filepath)

    def test_metadata_csv_reimport(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                self.assertEqual(2, cnx.execute("Any COUNT(X) WHERE X is File")[0][0])
                fa.cw_set(name="toto", publisher="titi")
                cnx.commit()
                self.assertEqual(fa.name, "toto")
                # reimport the same file
                config.update({"dc_no_cache": False, "reimport": True, "force_delete": True})
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)
                self.assertEqual(2, cnx.execute("Any COUNT(X) WHERE X is File")[0][0])
                for row in cnx.execute(f"Any {self.fkeyfunc}(D) WHERE X data D, X is File"):
                    fkey = row[0].getvalue()
                    self.assertTrue(self.fileExists(fkey))

    def test_create_ape_ead_file(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                ape_ead_file = fa.ape_ead_file[0]
                filepath = cnx.execute(
                    "Any FSPATH(D) WHERE X eid %(e)s, X data D", {"e": ape_ead_file.eid}
                )[0][0].getvalue()
                expected_filepath = self.get_filepath_by_storage(
                    f"{self.config['appfiles-dir']}/ape-ead/FRAD092/ape-FRAD092_9FI_cartes-postales.xml"  # noqa
                )
                self.assertEqual(filepath.decode("utf-8"), expected_filepath)
                self.assertTrue(self.fileExists(filepath))
                content = ape_ead_file.data.read()
                tree = etree.fromstring(content)
                eadid = tree.xpath("//e:eadid", namespaces={"e": tree.nsmap[None]})[0]
                self.assertEqual(
                    eadid.attrib["url"], "https://francearchives.gouv.fr/{}".format(fa.rest_path())
                )
                self.assertEqual(eadid.attrib["countrycode"], "FR")

    def test_FRAD010_62FI_ape_ead(self):
        """Test APE_EAD mapping for digitized versions

        Trying: Import a csv:
        Expecting:
           - column "sources_images" (thumbnail) is added as
             <dao xlink:href="" xlink:type="simple" xlink:role="thumbnail"/>
           - colum "identifiant_URI" (digitized version) is added as
             <dao xlink:href="" xlink:type="simple" xlink:title=""/>
        """
        with self.admin_access.cnx() as cnx:
            fpath = self.csv_filepath("FRAD010_62FI.csv")
            config = self.readerconfig.copy()
            config["dc_no_cache"] = False
            with cnx.allow_all_hooks_but("es"):
                dc.import_filepath(cnx, config, fpath)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                ape_filepath = cnx.execute(
                    "Any FSPATH(D) WHERE X ape_ead_file F, F data D, X eid %(x)s", {"x": fa.eid}
                )[0][0].getvalue()
                self.assertTrue(self.fileExists(ape_filepath))
                ape_expected_filepath = self.datapath(osp.join("ape_ead_data"), "FRAD010_62FI.xml")
                content = fa.ape_ead_file[0].data.read()
                tree = etree.fromstring(content)
                with open(ape_expected_filepath, "r") as expected:
                    self.assertXMLEqual(etree.parse(expected).getroot(), tree)
                self.assertFalse(fa.digitized_versions)
                illustration_urls = []
                digitized_urls = []
                daos = tree.xpath("//e:dao", namespaces={"e": tree.nsmap[None]})
                for dao in daos:
                    url = dao.attrib.get("{{{}}}href".format(tree.nsmap["xlink"]))
                    role = dao.attrib.get("{{{}}}role".format(tree.nsmap["xlink"]))
                    if not role:
                        digitized_urls.append(url)
                    elif role == "thumbnail":
                        illustration_urls.append(url)
                    else:
                        raise
                for fa in cnx.find("FAComponent").entities():
                    for dao in fa.digitized_versions:
                        if dao.role == "thumbnail":
                            illustration_urls.remove(dao.illustration_url)
                        elif not dao.role:
                            digitized_urls.remove(dao.url)
                self.assertFalse(illustration_urls)
                self.assertFalse(digitized_urls)

    def test_name_stable_id_dc_with_metadata(self):
        """stable_id is based in the filename with extension:
        - column 'identifiant_fichier' of metadata file with extension:"""
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.find("FindingAid").one()
                self.assertEqual("FRAD092_9FI_cartes-postales", fa.eadid)
                self.assertEqual("FRAD092_9FI_cartes-postales.csv", fa.name)
                self.assertEqual(fa.stable_id, usha1(fa.name))

    def test_name_stable_id_dc_without_metadata(self):
        """stable id is based on filename without extension"""
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath)
                fa = cnx.find("FindingAid").one()
                self.assertEqual("FRAD092_9FI_cartes-postales", fa.eadid)
                self.assertEqual("FRAD092_9FI_cartes-postales.csv", fa.name)
                self.assertEqual(fa.stable_id, usha1(fa.name))

    def test_import_csv_with_metadatafile_faprops(self):
        """
        Trying: import a FindingAid with dates
        Expecting: displayed FindingAid dates are the same as FindingAid unitdate
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.execute("Any FA WHERE FA is FindingAid").one()
                self.assertEqual(fa.did[0].unitdate, "1900 - 1944-05-31")
                self.assertEqual(fa.did[0].period, "1900 - 1944")
                adapter = fa.cw_adapt_to("entity.main_props")
                self.assertEqual(adapter.dates, "1900 - 1944-05-31")

    def test_import_csv_authorities_facomponent(self):
        """
        Trying: import a FindingComponent with authorities with ";" in labels
        Expecting: Authorities are correctly parsed
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                config = self.readerconfig.copy()
                fpath = self.csv_filepath("FRAM059017_data_archives_anciennes.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fc = cnx.execute("Any FA WHERE FA is FAComponent").one()
                index_entries = sorted(
                    [
                        (
                            ie.authority[0].cw_etype,
                            ie.authority[0].label,
                            ie.role,
                        )
                        for ie in fc.reverse_index
                    ]
                )
                expected = [
                    ("AgentAuthority", "Ville d’Armentières", "originator"),
                    ("AgentAuthority", "Egmont (famille d’)", "index"),
                    ("AgentAuthority", "Jacques III de Luxembourg-Fiennes (12..-1530)", "index"),
                    (
                        "AgentAuthority",
                        "Jean Ier de Bourgogne (1371-1419\xa0; dit Jean Sans Peur)",
                        "index",
                    ),
                    ("LocationAuthority", "Armentières (Nord, France)", "index"),
                    ("LocationAuthority", "Bois-Grenier (Nord, France)", "index"),
                    ("LocationAuthority", "Fleurbaix (Pas-de-Calais, France)", "index"),
                    ("LocationAuthority", "Frelinghien\xa0(Nord, France)", "index"),
                    ("LocationAuthority", "Houplines (Nord, France)", "index"),
                    ("LocationAuthority", "La Chapelle-d’Armentières (Nord, France)", "index"),
                ]
                self.assertCountEqual(expected, index_entries)

    def test_import_csv_with_cote_complete(self):
        """
        Trying: import csv file with a dedicated cote column `cote_complete`
        Expecting: FAComponent stable_id are still based on identifiant_cote column, but the cote
                   value comes from the new column
        """
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                self.service_eid = cnx.create_entity(
                    "Service", code="FRAN", short_name="FRAN", category="foo"
                ).eid
                cnx.commit()
                config = self.readerconfig.copy()
                fpath = self.csv_filepath("FRAN_base_leonore_lettre_i.csv")
                meta_fpath = self.csv_filepath("leonore_metadata.csv")
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                rset = cnx.execute(
                    "Any U, ST ORDERBY U WHERE F is FAComponent, "
                    "F stable_id ST, F did D, D unitid U"
                )
                self.assertEqual(rset.rowcount, 5)
                expected = [
                    ["19800035/109/13672", "1f502908963fc64164e710baf9bddbe69664e820"],
                    ["19800035/1345/55885", "c38449fc98ed65478491d16f4af4605bf918da1d"],
                    ["19800035/368/49441", "edf12d3915bfa4b29f3b74c9f4b9d4f17de2d386"],
                    ["LH//1332/2", "e6b64b83e6e8762d9e03ea85663ee2ad7cbf512a"],
                    ["LH//1332/3", "b4dd6ad923c6dd309624b2deba74c4cd773d960a"],
                ]
                self.assertEqual(expected, rset.rows)


class CSVDCReImportTC(CSVImportMixIn, PostgresTextMixin, WebCWTC):
    readerconfig = {
        "noes": True,
        "esonly": False,
        "appid": "data",
        "nodrop": True,
        "dc_no_cache": True,
        "reimport": True,
        "force_delete": True,
        "index-name": "dummy",
    }

    def setUp(self):
        super(CSVDCReImportTC, self).setUp()
        with self.admin_access.cnx() as cnx:
            self.service_eid = cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            ).eid
            cnx.commit()

    def test_index_reimport(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                ferry = cnx.execute(
                    "Any X WHERE X is AgentAuthority, X label %(e)s", {"e": "Jules Ferry"}
                ).one()
                self.assertEqual(len(ferry.reverse_authority[0].index), 1)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath)
                # we shell have only one AgentAuthority for Jules Ferry
                new_ferry = cnx.execute(
                    "Any X WHERE X is AgentAuthority, X label %(e)s", {"e": "Jules Ferry"}
                ).one()
                self.assertEqual(ferry.eid, new_ferry.eid)

    def test_reimport_csv_with_files(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpaths = [
                    self.csv_filepath("FRAD092_9FI_cartes-postales.csv"),
                    self.csv_filepath("FRAD092_affiches_culture.csv"),
                    self.csv_filepath("FRAD092_affiches_anciennes.csv"),
                ]
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepaths(cnx, config, fpaths)
                fa1, fa2, f3 = cnx.find("FindingAid").entities()

    def test_reimport_csv_without_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath)
                self._test_medatadata_csv(cnx)

    def test_reimport_csv_with_metadatafile(self):
        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                # reimport the same file
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                self._test_medatadata_csv(cnx)

    def test_creation_date_dc_import(self):
        """Test FindingAid, FAComponent creation date is keept between reimports

        Trying: import and reimport a FindingAid
        Expecting: reimported FindingAid and FAComponent have original creation_date
        """
        with self.admin_access.cnx() as cnx:
            cnx.create_entity(
                "Service", code="FRAD092", short_name="AD 92", level="level-D", category="foo"
            )
            cnx.commit()
            fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
            meta_fpath = self.csv_filepath("metadata.csv")
            config = self.readerconfig.copy()
            dc.import_filepath(cnx, config, fpath, meta_fpath)
            fa_old = cnx.execute("Any X WHERE X is FindingAid").one()
            comp_stable_id = "e3de7aefc6f62dfea3a5026232d5f295f388cedf"
            comp_old = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": comp_stable_id}).one()
            # FindingAid
            adapter = fa_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                fa_old.creation_date.isoformat(),
            )
            creation_date = datetime(1914, 4, 5)
            fmt = "%a %b %d %H:%M:%S %Y"
            fa_old.cw_set(creation_date=creation_date)
            comp_old.cw_set(creation_date=creation_date)
            cnx.commit()
            fa_old = cnx.execute("Any X WHERE X is FindingAid").one()
            fa_old_date = fa_old.creation_date
            comp_old_date = comp_old.creation_date
            self.assertEqual(
                creation_date.strftime(fmt),
                fa_old_date.strftime(fmt),
            )
            adapter = fa_old.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                fa_old.creation_date.isoformat(),
            )
            # reimport the same file
            config.update({"dc_no_cache": False, "reimport": True, "force_delete": True})
            dc.import_filepath(cnx, config, fpath, meta_fpath)
            fa = cnx.execute("Any X WHERE X is FindingAid").one()
            self.assertNotEqual(fa_old.eid, fa.eid)
            adapter = fa.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                fa.creation_date.isoformat(),
            )
            self.assertEqual(fa_old_date, fa.creation_date)
            # FAComponent
            comp = cnx.execute("Any X WHERE X stable_id %(s)s", {"s": comp_stable_id}).one()
            adapter = comp.cw_adapt_to("IFullTextIndexSerializable")
            self.assertEqual(
                adapter.serialize()["creation_date"],
                comp.creation_date.isoformat(),
            )
            self.assertEqual(comp.creation_date, comp_old_date)

    def test_findingaid_esdoc(self):
        """Testing FindingAid IFullTextIndexSerializable

        Trying: import a FindingAid
        Expecting: FindingAid ESDocument content is correct
                   and equal to es_json from generated from DB
        """

        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fa = cnx.find("FindingAid").one()
                authorities = {}
                for etype in ("AgentAuthority", "LocationAuthority", "SubjectAuthority"):
                    authorities.update(
                        {e[0]: e[1] for e in cnx.execute(f"Any L, X WHERE X is {etype}, X label L")}
                    )
                expected = {
                    "alltext": "Cartes postales anciennes",
                    "creation_date": fa.creation_date.isoformat(),
                    "cw_etype": "FindingAid",
                    "dates": {"gte": 1900, "lte": 1944},
                    "did": {"unitid": None, "unittitle": "Cartes postales anciennes"},
                    "digitized": False,
                    "digitized_all": DZFacetValues.nondz,
                    "eadid": "FRAD092_9FI_cartes-postales",
                    "eid": fa.eid,
                    "escategory": "archives",
                    "fa_stable_id": "300c316509c34bd7c830f1420f7a46e275fc4f95",
                    "index_entries": [
                        {
                            "authfilenumber": None,
                            "authority": authorities["Jules Ferry"],
                            "authtype": "AgentAuthority",
                            "label": "Jules Ferry",
                            "type": "persname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Alphonse Germain"],
                            "authtype": "AgentAuthority",
                            "label": "Alphonse Germain",
                            "type": "persname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Service des postes"],
                            "authtype": "AgentAuthority",
                            "label": "Service des postes",
                            "type": "corpname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Hauts-de-Seine"],
                            "authtype": "LocationAuthority",
                            "label": "Hauts-de-Seine",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Antony (Hauts-de-Seine)"],
                            "authtype": "LocationAuthority",
                            "label": "Antony (Hauts-de-Seine)",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Paris"],
                            "authtype": "LocationAuthority",
                            "label": "Paris",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities[
                                "Digne-les-Bains (Alpes-de-Haute-Provence, France ; arrondissement )"  # noqa
                            ],
                            "authtype": "LocationAuthority",
                            "label": "Digne-les-Bains (Alpes-de-Haute-Provence, France "
                            "; arrondissement )",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities[
                                "Sisteron (Alpes-de-Haute-Provence, France ; arrondissement)"
                            ],
                            "authtype": "LocationAuthority",
                            "label": "Sisteron (Alpes-de-Haute-Provence, France ; "
                            "arrondissement)",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities[
                                "Digne-les-Bains (Alpes-de-Haute-Provence, France)"
                            ],
                            "authtype": "LocationAuthority",
                            "label": "Digne-les-Bains (Alpes-de-Haute-Provence, " "France)",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["méditerranée (mer)"],
                            "authtype": "LocationAuthority",
                            "label": "méditerranée (mer)",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Corse (France ; département)"],
                            "authtype": "LocationAuthority",
                            "label": "Corse (France ; département)",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Cartes postales"],
                            "authtype": "SubjectAuthority",
                            "label": "Cartes postales",
                            "type": "subject",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["urbanisation"],
                            "authtype": "SubjectAuthority",
                            "label": "urbanisation",
                            "type": "subject",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["photographie"],
                            "authtype": "SubjectAuthority",
                            "label": "photographie",
                            "type": "genreform",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Archives des Hauts-de-Seine"],
                            "authtype": "AgentAuthority",
                            "label": "Archives des Hauts-de-Seine",
                            "type": "name",
                        },
                    ],
                    "originators": ["Archives des Hauts-de-Seine"],
                    "scopecontent": "Cartes postales anciennes (1900-1944)",
                    "service": {
                        "code": "FRAD092",
                        "eid": self.service_eid,
                        "level": "level-D",
                        "title": "AD 92",
                    },
                    "sortdate": "1900-01-01",
                    "stable_id": "300c316509c34bd7c830f1420f7a46e275fc4f95",
                    "startyear": 1900,
                    "stopyear": 1944,
                }
                adapted = fa.cw_adapt_to("IFullTextIndexSerializable")
                self.assertEqual(expected, adapted.serialize())
                self.assertEqual(expected, adapted.serialize_from_db())

    def test_facomponent_esdoc(self):
        """Testing FAComponent IFullTextIndexSerializable

        Trying: import a FindingAid
        Expecting: FAComponent ESDocument content is correct
                   and equal to es_json from generated from DB
        """

        with self.admin_access.cnx() as cnx:
            with cnx.allow_all_hooks_but("es"):
                fpath = self.csv_filepath("FRAD092_9FI_cartes-postales.csv")
                meta_fpath = self.csv_filepath("metadata.csv")
                config = self.readerconfig.copy()
                config["dc_no_cache"] = False
                dc.import_filepath(cnx, config, fpath, meta_fpath)
                fc = cnx.execute(
                    "Any X WHERE X is FAComponent, X did D, D unitid %(unitid)s",
                    {"unitid": "9FI/BAG_23"},
                ).one()
                authorities = {}
                for etype in ("AgentAuthority", "LocationAuthority", "SubjectAuthority"):
                    authorities.update(
                        {e[0]: e[1] for e in cnx.execute(f"Any L, X WHERE X is {etype}, X label L")}
                    )
                expected = {
                    "creation_date": fc.creation_date.isoformat(),
                    "cw_etype": "FAComponent",
                    "dates": {"gte": 1932, "lte": 1932},
                    "did": {"unitid": "9FI/BAG_23", "unittitle": "Cité des Oiseaux"},
                    "digitized": True,
                    "digitized_all": [DZFacetValues.dz, DZFacetValues.dz_noniiif],
                    "eadid": None,
                    "eid": fc.eid,
                    "escategory": "archives",
                    "fa_stable_id": "300c316509c34bd7c830f1420f7a46e275fc4f95",
                    "index_entries": [
                        {
                            "authfilenumber": None,
                            "authority": authorities["Société Beguin-Say"],
                            "authtype": "AgentAuthority",
                            "label": "Société Beguin-Say",
                            "type": "corpname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Bagneux"],
                            "authtype": "LocationAuthority",
                            "label": "Bagneux",
                            "type": "geogname",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Logement social > Cité du Champ des Oiseaux"],
                            "authtype": "SubjectAuthority",
                            "label": "Logement social > Cité du Champ des Oiseaux",
                            "type": "subject",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["photographie"],
                            "authtype": "SubjectAuthority",
                            "label": "photographie",
                            "type": "genreform",
                        },
                        {
                            "authfilenumber": None,
                            "authority": authorities["Entreprise Pajol"],
                            "authtype": "AgentAuthority",
                            "label": "Entreprise Pajol",
                            "type": "name",
                        },
                    ],
                    "originators": ["Entreprise Pajol"],
                    "scopecontent": "Duis aute irure dolor in reprehenderit in voluptate velit "
                    "esse cillum dolore eu fugiat nulla pariatur. Excepteur sint "
                    "occaecat cupidatat non proident, sunt in culpa qui officia "
                    "deserunt mollit anim id est laborum.",
                    "service": {
                        "code": "FRAD092",
                        "eid": self.service_eid,
                        "level": "level-D",
                        "title": "AD 92",
                    },
                    "sortdate": "1932-01-01",
                    "stable_id": "b33218db14182849513e3f8675bbfac2b3c81509",
                    "startyear": 1932,
                    "stopyear": 1932,
                }
                adapted = fc.cw_adapt_to("IFullTextIndexSerializable")
                self.assertEqual(expected, adapted.serialize())
                es_from_db = adapted.serialize_from_db()
                es_from_db.update({"eadid": None})
                index_expected = expected.pop("index_entries")
                index_db = es_from_db.pop("index_entries")
                self.assertEqual(expected, es_from_db)
                self.assertCountEqual(index_expected, index_db)


if __name__ == "__main__":
    unittest.main()
