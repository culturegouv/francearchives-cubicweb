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

logger.info("Replace translate_entity")


TRANSLATE_ENTITY_QUERY = r"""
CREATE OR REPLACE FUNCTION translate_entity(etype varchar, eid int, attr varchar, lang varchar)
RETURNS varchar AS $$
DECLARE
    label varchar;
    label_lang varchar;
BEGIN
    EXECUTE format('SELECT cw_%s FROM cw_%s WHERE cw_eid=%s', attr, etype, eid) INTO label ;
    IF lang = 'fr' THEN
        RETURN label;
    ELSE
        IF etype = ANY ('{Section, BaseContent, CommemorationItem, FaqItem}'::varchar[]) THEN
            EXECUTE format('SELECT cw_%s FROM cw_%sTranslation WHERE cw_translation_of=%s AND cw_language=''%s''', attr, etype, eid, lang) INTO label_lang ;
            IF label_lang is NOT NULL THEN
               RETURN label_lang;
            ELSE
               RETURN label;
            END IF;
        END IF;
        RETURN label;
    END IF;
END;
$$ LANGUAGE plpgsql;
    """

cnx.system_sql(TRANSLATE_ENTITY_QUERY)
cnx.commit()

logger.info("Drop the old translate_entity")

cnx.system_sql("""DROP function IF EXISTS translate_entity(eid int, attr varchar, lang varchar)""")
cnx.commit()
