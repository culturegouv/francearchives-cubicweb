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

from logilab.mtconverter import xml_escape

from cubicweb.predicates import is_instance
from cubicweb_web.view import EntityView
from cubicweb_web.component import EntityCtxComponent

from cubicweb_francearchives.views import add_js_translations
from cubicweb_francearchives.utils import cut_words


class TreeOnelineView(EntityView):
    __select__ = EntityView.__select__ & is_instance("FindingAid", "FAComponent")
    __regid__ = "tree-oneline"

    def cell_call(self, row, col, selected, _class, has_leafs):
        entity = self.cw_rset.get_entity(row, col)
        w = self.w
        with T.p(w, Class=_class):
            full_title = entity.dc_title()
            title = cut_words(full_title, 230)
            if entity.eid == selected:
                kwargs = {"aria_current": "true"}
                if self._cw.lang != "fr":
                    kwargs["lang"] = "fr"
                w(T.span(xml_escape(title), _class="detailed-path-list-item-active", **kwargs))
            else:
                kwargs = {"href": xml_escape(entity.absolute_url())}
                if title != full_title:
                    kwargs["title"] = xml_escape(full_title)
                with T.a(w, **kwargs):
                    if self._cw.lang == "fr":
                        w(xml_escape(title))
                    else:
                        w(f'<span lang="fr">{xml_escape(title)}</span>')


def display_tree_last_item(req, w, item, _class):
    with T.p(w, Class=_class):
        full_title = item[3] or item[4] or "???"  # did.dc_title
        title = cut_words(full_title, 230)
        kwargs = {"href": xml_escape(req.build_url(f"facomponent/{item[1]}"))}
        if full_title != title:
            kwargs["title"] = xml_escape(full_title)
        if req.lang == "fr":
            w(T.a(title, **kwargs))
        else:
            with T.a(w, **kwargs):
                w(T.span(xml_escape(title), lang="fr"))


class AbstractFindingAidTreeComponent(EntityCtxComponent):
    __abstract__ = True
    __regid__ = "findinaid.tree"
    context = "fa-inventory-context"
    order = 1
    children_count = None
    limit = None

    def render(self, w, view=None):
        self.render_content(w)

    def tree_items(self, entity, limit=None):
        raise NotImplementedError

    def add_dot_item(self, w):
        kwargs = {
            "id": "fa-context-container",
            "data_fa_context_stable_id": self.entity.stable_id,
            "data_fa_context_entity_type": self.entity.cw_etype,
            "data_fa_context_element_count": str(self.children_count),
        }
        if self._cw.lang != "fr":
            kwargs["data_lang"] = "fr"
        with T.li(w):
            w(T.div(**kwargs))

    def display_service_link(self, entity, w):
        service = entity.related_service
        if service:
            label = f"{self._cw._('Service')}{self._cw._(':')}"
            with T.p(w):
                w(label)
                w(service.view("incontext"))
        else:
            w(self.entity.publisher)

    def render_content(self, w):
        add_js_translations(self._cw)
        self._cw.add_js("bundle-fa-context.js", {"defer": True})
        self.entity = self.cw_rset.get_entity(0, 0)
        self.children_count = self.entity.top_children_count
        self.limit = 10 if self.children_count > 10 else None
        tree_items = self.tree_items(self.entity, limit=self.limit)
        if tree_items:
            with T.section(w, Class="fr-container detailed-path"):
                with T.div(w, Class="fr-grid-row fr-grid-row--gutters"):
                    with T.div(w, id="tree-hierarchy", Class="fr-col-md-10"):
                        with T.h2(w):
                            w(self._cw._("Description context:"))
                        self.display_service_link(self.entity, w)
                        with T.nav(w, Class="detailed-path-inner-levels"):
                            self.render_tree(w, self.entity, tree_items, limit=self.limit)
                if self.limit:
                    if self.children_count > 1000:
                        with T.p(w):
                            w(T.span(Class="fr-icon-error-warning-line fr-link--icon-left fa-blue"))
                            w(
                                T.span(
                                    self._cw._(
                                        "This context contains %s elements: displaying them all can take several seconds."  # noqa
                                    )
                                    % self.children_count
                                )
                            )  # noqa

    def render_tree(self, w, entity, tree_items, limit=None):
        with T.ul(w, Class="detailed-path-list-root"):
            tree_items = list(tree_items)
            total = len(tree_items)
            with T.li(w):
                w(
                    entity.view(
                        "tree-oneline",
                        selected=entity.eid,
                        _class="detailed-path-list-item",
                        has_leafs=bool(total),
                    )
                )
                with T.ul(w, Class="detailed-path-list fr-col-12 fr-col-lg-9"):
                    item_class = "detailed-path-list-item"
                    for i, item in enumerate(tree_items, 1):
                        add_dot = limit and total == i
                        _class = (
                            "detailed-path-list-item-last"
                            if total == i and not add_dot
                            else item_class
                        )
                        with T.li(w):
                            display_tree_last_item(self._cw, w, item, _class=_class)

                        if add_dot:
                            self.add_dot_item(w)


class FindingAidTreeComponent(AbstractFindingAidTreeComponent):
    __select__ = is_instance("FindingAid")

    def tree_items(self, entity, limit=None):
        limit = f"LIMIT {limit}" if limit else ""
        return self._cw.execute(
            "Any C,CI,D,DT,DI "
            "ORDERBY CO {} "
            "WHERE X top_components C, X eid %(x)s, "
            "C stable_id CI, C did D, D unittitle DT, "
            "D unitid DI, C component_order CO".format(limit),
            {"x": self.entity.eid, "l": limit},
        )


class FAComponentTreeComponent(AbstractFindingAidTreeComponent):
    __select__ = is_instance("FAComponent")
    order = 1

    def get_children(self, entity, limit=None):
        limit = f"LIMIT {limit}" if limit else ""
        return self._cw.execute(
            "Any C,CI,D,DT,DI "
            "ORDERBY CO {} "
            "WHERE C parent_component X, X eid %(x)s, "
            "C stable_id CI, C did D, D unittitle DT, "
            "D unitid DI, C component_order CO".format(limit),
            {"x": self.entity.eid, "l": limit},
        )

    def tree_items(self, entity, limit=None):
        finding_aid = entity.finding_aid[0]
        component_chain = []
        children = self.get_children(entity, limit=limit)
        if children:
            component_chain.insert(0, list(children.entities()))
        component_chain.insert(0, [entity])
        parent = entity.parent_component
        while parent:
            component_chain.insert(0, parent)
            parent = parent[0].parent_component
        component_chain.insert(0, [finding_aid])
        return component_chain

    def render_tree(self, w, entity, tree_items, level=1, limit=None, **kwargs):
        ul_class = "detailed-path-list-root" if level == 1 else "detailed-path-list"
        with T.ul(w, Class=ul_class, **kwargs):
            total = len(tree_items[0])
            has_leafs = len(tree_items) > 1
            for i, _entity in enumerate(tree_items[0], 1):
                add_dot = not has_leafs and limit and total == i
                with T.li(w):
                    _class = (
                        "detailed-path-list-item-last"
                        if total == i and not add_dot
                        else "detailed-path-list-item"
                    )
                    w(
                        _entity.view(
                            "tree-oneline", selected=entity.eid, _class=_class, has_leafs=has_leafs
                        )
                    )
                    if add_dot:
                        self.add_dot_item(w)
            if has_leafs:
                with T.li(w):
                    self.render_tree(w, entity, tree_items[1:], level + 1, limit=limit)
