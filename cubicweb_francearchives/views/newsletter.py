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

from cwtags import tag as T

from cubicweb import _
from cubicweb_web.view import StartupView

from cubicweb_francearchives.utils import find_card


class NewsLetterView(StartupView):
    __regid__ = "newsletter"
    title = _("Newsletter")
    eulerian_tag = True
    eulerian_pagegroup = "editorial"

    @property
    def breadcrumbs(self, view=None, recurs=None):
        _ = self._cw._
        return [
            (self._cw.build_url(""), _("Home")),
            (None, self._cw._(self.title)),
        ]

    def call(self, **kwargs):
        card = find_card(self._cw, self.__regid__)
        if card is not None:
            self.wview("primary", entity=card)
        with T.div(self.w, Class="fr-container fa-mb"):
            with T.div(self.w, klass="fr-grid-row fr-grid-row--gutters fr-grid-row--center"):
                with T.div(self.w, klass="fr-col-12 fr-col-lg-8"):
                    self.w(
                        T.iframe(
                            id="newsletter-frame",
                            width="100%",
                            height="100%",
                            overflow="auto;",
                            frameborder="0",
                            scrolling="auto",
                            src="https://go.formulaire.info/form?p=iWw6BYP8",
                        )
                    )
