# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2016-2020
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

import logging

from cubicweb_francearchives import SUPPORTED_LANGS

logger = logging.getLogger("francearchives.migration")
logger.setLevel(logging.INFO)
logger.info("Increase the size the size public.ExternalUri.cw_extid to 256 chars")

cnx.system_sql("""ALTER TABLE public.cw_ExternalUri ALTER COLUMN cw_extid TYPE VARCHAR(256)""")
sync_schema_props_perms("extid")
cnx.commit()

sync_schema_props_perms("on_homepage")

logger.info("Creating missing cards in all supported languages")

TITLES = {
    "no_focus_census": {"fr": "Rechercher dans les recensements"},
    "no_focus_military_register": {"fr": "Rechercher dans les registres de matricules"},
    "no_focus_civilstatus": {"fr": "Rechercher dans l'état civil"},
}

CONTENT = {
    "no_focus_census": {
        "fr": """<p><a href="../basedenoms_recensement?es_names=&es_forenames=&es_locations=&fulltext_facet=">Retrouver toutes les archives numérisées des recensements sur FranceArchives</a></p>"""
    },
    "no_focus_military_register": {
        "fr": """<p><a href="../basedenoms_militaire?es_names=&es_forenames=&es_locations=&fulltext_facet=">Retrouver toutes les archives numérisées des matricules militaires sur FranceArchives</a></p>""",
    },
    "no_focus_civilstatus": {
        "fr": """<p><a href="../basedenoms_etat_civil?es_names=&es_forenames=&es_locations=&fulltext_facet=">Retrouver toutes les archives numérisées de l'état civils sur FranceArchives</a></p>""",
    },
}

with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):

    for wikiid, descr in TITLES.items():
        title = descr["fr"]
        for lang in SUPPORTED_LANGS:
            _wikiid = "%s-%s" % (wikiid, lang)
            ex = cnx.execute("Any X WHERE X wikiid %(w)s", {"w": _wikiid})
            if ex:
                continue
            content = CONTENT.get(wikiid).get(lang, title)
            if not content:
                content = CONTENT[wikiid]["fr"]
            title = TITLES.get(wikiid, {}).get(lang, title)
            cnx.create_entity(
                "Card",
                wikiid=_wikiid,
                title=title,
                content=content,
                content_format="text/html",
                do_index=False,
            )
            logger.info(f"Created Card {_wikiid} - {title}")
    cnx.commit()

logger.info("Updating cards content")
