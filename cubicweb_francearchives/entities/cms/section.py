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
# with loading, using, modifying and/or developing or reproducing thep
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

"""cubicweb-pnia-content section management"""

from cubicweb.entities import fetch_config
from cubicweb.predicates import is_instance

from cubicweb_francearchives.entities.cms import (
    AlltextIFTIAdapterMixin,
    CmsObject,
    TranslatableCmsObject,
    TranslationMixin,
    CMSIFTIAdapterMixin,
)

from cubicweb_francearchives.entities.es import (
    TranslatableIndexSerializableMixin,
    PniaIFullTextIndexSerializable,
)


def get_children(cnx, section_eid, only_sections=False):
    children = []
    if only_sections:
        restriction = ", X is Section"
    else:
        restriction = ""
    rset = cnx.execute(
        "Any X, T ORDERBY O WHERE S is Section,"
        "X order O, "
        f"S eid %(eid)s, S children X, X title T {restriction}",
        {"eid": section_eid, "r": restriction},
    )
    for child in rset.entities():
        infos = dict(
            title=child.title, etype=child.cw_etype, url=child.absolute_url(), children=None
        )
        if child.cw_etype == "Section":
            infos["children"] = get_children(cnx, child.eid, only_sections=only_sections)
        children.append(infos)
    return children


class Section(TranslatableCmsObject):
    __regid__ = "Section"
    rest_attr = "eid"
    fetch_attrs, cw_fetch_order = fetch_config(
        ["order", "title", "subtitle", "content", "short_description", "display_mode"], order="DESC"
    )
    i18nfields = ("title", "subtitle", "content", "short_description")

    def dc_title(self):
        if self._cw.lang != "fr":
            entity = self.cw_adapt_to("ITemplatable").entity_param()
        else:
            entity = self
        titles = [entity.title, entity.subtitle]
        return " - ".join(t for t in titles if t)

    def breadcrumbs_title(self):
        if self._cw.lang == "fr":
            return self.title
        return self.cw_adapt_to("ITemplatable").entity_param().title

    @property
    def display_tree(self):
        return self.display_mode == "mode_tree"

    @property
    def display_themes(self):
        return self.display_mode == "mode_themes"

    @property
    def display_default(self):
        return self.display_mode == "mode_no_display"

    @property
    def image(self):
        images = self.section_image or self.reverse_cssimage_of
        return images[0] if images else None


class SectionTranslation(TranslationMixin, CmsObject):
    __regid__ = "SectionTranslation"


class SectionIFullTextIndexSerializable(
    CMSIFTIAdapterMixin,
    TranslatableIndexSerializableMixin,
    PniaIFullTextIndexSerializable,
    AlltextIFTIAdapterMixin,
):
    __select__ = PniaIFullTextIndexSerializable.__select__ & is_instance("Section")
    numeric_indexable = False

    def serialize(self, complete=True, **kwargs):
        data = super(SectionIFullTextIndexSerializable, self).serialize(complete)
        data.update(self.add_translations(complete=complete, **kwargs))
        data.update({"alltext": self.alltext_values(data)})
        return data
