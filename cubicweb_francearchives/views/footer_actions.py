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
"""pnia_content views/footer_actions views and components"""


from logilab.mtconverter import xml_escape

from cubicweb_web import action

_ = str


class FooterAction(action.Action):
    """footer actions infos are displayed in the page footer."""

    __abstract__ = True
    category = "pnia-footer"
    title = None

    def url(self):
        raise NotImplementedError()


class LegalNoticeAction(FooterAction):
    __regid__ = "pnia.footer.legal-notices"
    order = 1
    title = _("Legal notices")

    def url(self):
        return xml_escape(self._cw.build_url("legal_notices"))


class AccessibilityAction(FooterAction):
    __regid__ = "pnia.footer.accessibilityt"
    order = 2
    title = _("Accessibility")

    def url(self):
        return xml_escape(self._cw.build_url("accessibility"))


class SiteMapAction(FooterAction):
    __regid__ = "pnia.footer.site-map"
    order = 3
    title = _("Site map")

    def url(self):
        return xml_escape(self._cw.build_url("sitemap"))


class CGUMapAction(FooterAction):
    __regid__ = "pnia.footer.cgu"
    order = 4
    title = _("CGU")

    def url(self):
        return xml_escape(self._cw.build_url("cgu"))


class PrivacyPolicyAction(FooterAction):
    __regid__ = "pnia.footer.privacy-policy"
    order = 5
    title = _("Privacy policy")

    def url(self):
        return xml_escape(self._cw.build_url("privacy_policy"))
