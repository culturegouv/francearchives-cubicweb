# -*- coding: utf-8 -*-
#
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
#
import logging

from pyramid.view import view_config

LOG = logging.getLogger(__name__)


def circulars_data(cnx):
    rset = cnx.execute(
        """
Any X, N, DC, C, S, DS, T, ST, CI, JSON_AGG(L)
GROUPBY X, N, DC, C, S, DS, T, ST, CI
WITH X, N, DC, C, S, DS, T, ST, CI, L BEING
(
    (Any X, N, DC, C, S, DS, T, ST, CI, L
    WHERE X is Circular, X nor N, X siaf_daf_code DC, X code C,
    X signing_date S, X siaf_daf_signing_date DS,
    X title T, X status ST, X circ_id CI,
    X business_field B, B preferred_label PL, PL label L)
    UNION
    (Any X, N, DC, C, S, DS, T, ST, CI, 'n/r'
    WHERE X is Circular, X nor N, X siaf_daf_code DC, X code C,
    X signing_date S, X siaf_daf_signing_date DS,
    X title T, X status ST, X circ_id CI, NOT X business_field B
    )
)
"""
    )
    rows = []
    for idx, (
        eid,
        nor,
        siaf_daf_code,
        code,
        signing_date,
        siaf_daf_signing_date,
        title,
        status,
        circ_id,
        business_fields,
    ) in enumerate(rset):
        if signing_date is not None:
            date = signing_date.isoformat()
        elif siaf_daf_signing_date is not None:
            date = siaf_daf_signing_date.isoformat()
        else:
            date = None
        row = {
            "eid": eid,
            "code": siaf_daf_code or code or nor or "",
            "date": date,
            "title": title,
            "url": cnx.build_url(f"circulaire/{circ_id}"),
            "status_orig": status,
            "status": cnx._(status),
            "business": tuple(cnx._(field) for field in business_fields) or (),
        }
        rows.append(row)
    return rows


@view_config(
    route_name="circulars-tb-data-json",
    renderer="json",
    http_cache=600,
    request_method=("GET", "HEAD"),
)
def circulars_data_view(request):
    cnx = request.cw_request
    return circulars_data(cnx)


def includeme(config):
    config.add_route("circulars-tb-data-json", "/circulars-tb-data.json")
    config.add_route("circulars_data", "/circulars/data")
    config.scan(__name__)
