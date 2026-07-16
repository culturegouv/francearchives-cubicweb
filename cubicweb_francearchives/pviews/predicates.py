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


class SegmentIsEnlargedETypePredicate(object):
    """A predicate that match if a given etype exist in schema or in its translations dict."""

    def __init__(self, definition, config):
        traverse_name, translations = definition
        self.traverse_name = traverse_name
        self.translations = translations

    def text(self):
        return "segment_is_enlarged_etype = %s " % self.traverse_name

    phash = text

    def __call__(self, info, request):
        etype = info["match"][self.traverse_name]
        requested_etype = etype.lower()
        etypes = request.registry["cubicweb.registry"].case_insensitive_etypes
        return requested_etype in etypes or requested_etype in self.translations


class MultiAcceptPredicate(object):
    def __init__(self, values, config):
        self.values = values

    def text(self):
        return "multiaccept = %s" % (self.values,)

    phash = text

    def __call__(self, context, request):
        list_accept = tuple(request.accept)
        if not list_accept:
            # requested accept is empty
            return False
        if "*/*" in tuple(request.accept):
            return False
        return any(val in request.accept for val in self.values)
