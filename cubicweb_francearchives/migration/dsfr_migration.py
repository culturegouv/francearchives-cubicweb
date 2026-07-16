# -*- coding: utf-8 -*-
#
# flake8: noqa
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2024
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

# library specific imports
import logging
from collections import defaultdict

logger = logging.getLogger("francearchives.migration")
logger.setLevel(logging.INFO)

from cubicweb_francearchives import SUPPORTED_LANGS

logger.info("Creating missing cards in all supported languages")

rset = cnx.execute(
    "Any X, W, T ORDERBY W, T WHERE X is Card, X wikiid W, X title T, NOT X wikiid ILIKE 'emplois%'"
)
all_cards = defaultdict(list)


with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):
    for entity, wikiid, title in rset.iter_rows_with_entities():
        try:
            cid, lang = wikiid.rsplit("-", 1)
        except ValueError:
            if wikiid == "emploi":
                continue
            new_wikiid = f"{wikiid}-fr"
            logger.error(f'Card "{title}" ({wikiid}) has no language, make if french: {new_wikiid}')
            entity.cw_set(wikiid=new_wikiid)
            cnx.commit()
            cid, lang = new_wikiid.rsplit("-", 1)
        all_cards[cid].append(lang)
    # for lang in SUPPORTED_LANGS:
    assert "emplois" not in all_cards
    for cid, languages in all_cards.items():
        fr_wikiid = f"{cid}-fr"
        rset = cnx.execute(f"Any X WHERE X is Card, X wikiid '{fr_wikiid }'")
        if not rset:
            logger.error(f"Card ({fr_wikiid})  not found")
            continue
        card = rset.one()
        for missing_lang in set(SUPPORTED_LANGS).difference(languages):
            new_wikiid = f"{cid}-{missing_lang}"
            create_entity(
                "Card",
                wikiid=new_wikiid,
                title=card.title,
                content_format="text/html",
                do_index=card.do_index,
            )
            cnx.commit()
            logger.info(f"Created Card {new_wikiid} in {missing_lang }, index: {card.do_index}")


logger.info("Creating new Cards")

TITLES = {
    "error_notfound": {"fr": "Page non trouvée"},
    "key_figures": {
        "fr": "Chiffres-clés",
        "en": "Key figures",
        "es": "Cifras clave",
        "de": "Schlüsselzahlen",
    },
    "hp_focus_archives": {"fr": "Rechercher des archives numérisées"},
    "hp_focus_subjects": {"fr": "Découvrir les publications des services d'archives"},
    "hp_focus_locations": {"fr": "Rechercher un lieu"},
}

CONTENT = {
    "error_notfound": {
        "fr": """<p class="fr-text--sm fr-mb-3w">Erreur 404</p>
      <p class="fr-text--lead fr-mb-3w">La page que vous cherchez est introuvable. Excusez-nous pour la gène occasionnée.</p>
      <p class="fr-text--sm fr-mb-5w">
        Si vous avez tapé l'adresse web dans le navigateur, vérifiez qu'elle est correcte. La page n’est peut-être plus disponible.
        <br>Dans ce cas, pour continuer votre visite vous pouvez consulter notre page d’accueil, ou effectuer une recherche avec notre moteur de recherche en haut de page.
        <br>Sinon contactez-nous pour que l’on puisse vous rediriger vers la bonne information.
      </p>"""
    },
    "key_figures": {
        "fr": """<p>Chiffres-clés des principaux services de FranceArchives. Ils comprennent les mots-clefs identifiant des lieux, des personnes, des institutions ou des thèmes dans les archives référencées, qui sont appelés "autorités". Ils sont harmonisés, alignés vers des référentiels nationaux et internationaux, et groupés, pour constituer un réservoir d’autorités certifiées dites « autorités de qualité ».</p>""",
        "en": """<p>Key figures for the main services on FranceArchives . They include keywords identifying places, people, institutions or themes in the archives referenced, which are called "authorities". They are harmonised, aligned with national and international vocabularies, and grouped together to form a pool of certified authorities known as "quality authorities".</p>""",
        "de": """<p>Schlüsselzahlen der wichtigsten Abteilungen von FranceArchives. Sie umfassen die Schlüsselwörter, die Orte, Personen, Institutionen oder Themen in den referenzierten Archiven identifizieren, die als "Autoritäten" bezeichnet werden. Sie werden harmonisiert, an nationale und internationale Referenzsysteme angeglichen und gruppiert, um ein Reservoir von zertifizierten Autoritäten, den sogenannten "Qualitätsautoritäten", zu bilden.</p>""",
        "es": """<p>Cifras clave de los principales servicios de FranceArchives. Incluyen palabras clave que identifican lugares, personas, instituciones o temas de los archivos referenciados, que se denominan "autoridades". Se armonizan, se alinean con los sistemas de referencia nacionales e internacionales y se agrupan para formar un conjunto de autoridades certificadas denominadas "autoridades de calidad".</p>""",
    },
    "hp_focus_archives": {
        "fr": """<p><a href="../inventaires?es_digitized=True">Retrouver toutes les archives num&eacute;ris&eacute;es r&eacute;f&eacute;renc&eacute;es sur FranceArchives</a></p>
<p><a href="../search?advanced=true&amp;es_digitized=True&amp;es_escategory=archives&amp;searches=%5B%22%2A%22%5D&amp;searches_op=%5B%5D&amp;searches_t=%5B%22t%22%5D&amp;services=%5B33366%2C33640%2C34221%2C34295%2C33887%2C34318%2C34471%2C34141%2C26288072%2C73504319%5D&amp;services_op=%22OU%22">Voir les archives diffus&eacute;es en utilisant le protocole IIIF</a></p>
<p><a title="Lien vers la page &quot;IIIF, un outil pour visualiser les archives num&eacute;ris&eacute;es&quot; sur FranceArchives" href="714850036">Pour en savoir plus sur le IIIF</a>.</p>"""
    },
    "hp_focus_subjects": {
        "fr": """<p>D&eacute;couvrez les catalogues d'expositions, ouvrages de recherche et publications p&eacute;dagogiques publi&eacute;s par les services d'archives.</p>
<p><a title="Lien vers la rubrique &quot;Publications des services d'archives&quot; sur FranceArchives" href="../section/28204596">Voir les publications des services archives</a></p>""",
    },
    "hp_focus_locations": {
        "fr": """<p>Acc&egrave;dez aux archives par&nbsp;<a title="la carte des lieux des archives - lien vers la carte sur FranceArchives" href="../carte-inventaires">la carte des lieux des archives</a> et d&eacute;couvrez les sources li&eacute;es &agrave; un territoire.</p>"""
    },
}

with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):

    for wikiid, title in (
        ("key_figures", "Chiffres clés"),
        ("error_notfound", "Page non trouvée"),
        ("hp_focus_archives", "Rechercher des archives numérisées"),
        ("hp_focus_subjects", "Rechercher un thème"),
        ("hp_focus_locations", "Rechercher un lieu"),
    ):
        for lang in SUPPORTED_LANGS:
            _wikiid = "%s-%s" % (wikiid, lang)
            ex = cnx.execute("Any X WHERE X wikiid %(w)s", {"w": _wikiid})
            if ex:
                continue
                ex.one().cw_delete()
                cnx.commit()
            content = CONTENT.get(wikiid).get(lang, title)
            if not content:
                content = CONTENT[wikiid]["fr"]
            title = TITLES.get(wikiid, {}).get(lang, title)
            create_entity(
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

UPDATED_CONTENT = {
    "tableau-circulaires": {
        "fr": """<p>Notes et instructions minist&eacute;rielles et interminist&eacute;rielles relatives &agrave; la gestion des archives publiques&nbsp;: r&egrave;gles de communicabilit&eacute;, s&eacute;curit&eacute; des b&acirc;timents, r&eacute;utilisation, s&eacute;lection et collecte des archives notamment.</p>
<p>Le tableau et la liste des circulaires ci-dessous fournissent exactement les m&ecirc;mes informations. Le tableau n&rsquo;est cependant pas compatible avec les &eacute;crans mobiles et les assistants de lecture.</p>"""
    }
}

with cnx.allow_all_hooks_but("es", "sync", "varnish", "reindex-suggest-es"):
    for wikiid, values in UPDATED_CONTENT.items():
        for lang, content in values.items():
            _wikiid = "%s-%s" % (wikiid, lang)
            ex = cnx.execute("Any X WHERE X wikiid %(w)s", {"w": _wikiid})
            if not ex:
                logger.error(f"Card  {_wikiid} doesn't exist")
                continue
            card = ex.one()
            card.cw_set(content=content)
            logger.info(f"Updated Card {_wikiid} - {card.title}")
    cnx.commit()


# modify SiteLink
from contextlib import contextmanager
from cubicweb.server.serverctl import system_source_cnx
from cubicweb.dataimport.massive_store import PGHelper


logger.info("Adding a new value in SiteLink vocabulary")

for e, context, label_fr in cnx.execute(
    "Any X, C, L WHERE X is SiteLink, X context C, X label_fr L"
).iter_rows_with_entities():
    if context not in (
        "main_menu_links",
        "archiviste_hp_links",
        "footer_ministries",
        "footer_public_sites",
        "footer_archives_sites",
        "footer_search_notebooks",
        "footer_usefull_links",
        "footer_links_directories",
        "footer_links",
        "foundout_link",
    ):
        print(e, context, label_fr)

set_size_constraint("SiteLink", "context", 50, commit=True)
sync_schema_props_perms("SiteLink", syncprops=True)
