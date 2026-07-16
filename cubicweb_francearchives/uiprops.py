# flake8: noqa
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

STYLESHEETS = [
    data("dsfr/dsfr.min.css"),
    data("dsfr/utility/utility.min.css"),
    data("dsfr/utility/icons/icons.min.css"),
    data("css/francearchives.bundle.css"),
]

# don't use ``JAVASCRIPTS`` since CW will automatically add
# ``cubicweb.js`` to it.
PNIA_JAVASCRIPTS = [
    data("jquery-3.1.1.min.js"),
    data("jquery-typeahead/jquery.typeahead.min.js"),
    data("cubes.pnia_portal.js"),
    data("bundle-portal-francearchives.js"),
]  # noqa

IIIF_LOGO = data("images/logo-iiif.png")
DOCUMENT_IMG = data("images/FranceArchives_NoImage-narrow.jpg")
DIGITIZED_IMG = data("images/FranceArchives_NoDigitized.png")
AMP_LOGO = data("images/logo_francearchives_amp.png")
# country (languages) flags

FLAG_FR = data("images/header_topbar_language-france.png")
FLAG_EN = data("images/header_topbar_language-united-kingdom.png")
FLAG_DE = data("images/header_topbar_language-germany.png")
FLAG_ES = data("images/header_topbar_language-spain.png")

CITY_PICTO = data("dsfr/artwork/pictograms/buildings/city-hall.svg")
SIGN_DOC_PICTO = data("dsfr/artwork/pictograms/document/document-signature.svg")
SEARCH_PICTO = data("dsfr/artwork/pictograms/digital/search.svg")
DOC_PICTO = data("dsfr/artwork/pictograms/document/document.svg")
