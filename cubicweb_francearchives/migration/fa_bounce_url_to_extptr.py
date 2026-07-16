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
from cubicweb_francearchives.migration.utils import drop_column_from_published_table

logger = logging.getLogger("francearchives.migration")
logger.setLevel(logging.INFO)

logger.info("transform bounce_url into exptr")

for i, (fa, did, extptr, dv, url, illustration_url) in enumerate(
    rql(
        "Any X, D, DE, DV, DVU, DVIU WHERE X is FAComponent, X did D, D extptr DE, X digitized_versions DV, DV role 'fa_bounce_url', DV url DVU, DV illustration_url DVIU"
    ).iter_rows_with_entities()
):
    assert not extptr
    assert url
    assert not illustration_url
    did.cw_set(extptr=url)
    # remove dao
    dv.cw_delete()
    if not i % 1000:
        cnx.commit()
cnx.commit()
