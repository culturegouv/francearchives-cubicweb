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
from collections import defaultdict

from cubicweb.dataimport.stores import MetadataGenerator
from cubicweb.dataimport.massive_store import MassiveObjectStore, PGHelper, eschema_sql_def

from cubicweb_francearchives.dataimport.sqlutil import deffer_foreign_key_constraints


def clean_massive_store(store):
    """clean any temporary table left by a previous massive import"""
    store.logger.info("Start cleaning")
    # Get all the initialized etypes/rtypes
    if store._dbh.table_exists("cwmassive_initialized"):
        cu = store.sql("SELECT retype, type, uuid FROM cwmassive_initialized")
        entities = defaultdict(list)
        relations = defaultdict(list)
        for retype, _type, uuid in cu.fetchall():
            if _type == "rtype":
                relations[retype].append(uuid)
            else:  # _type = 'etype'
                entities[retype].append(uuid)
        # get back entity data from the temporary tables
        for etype, uuids in list(entities.items()):
            tablename = "cw_%s" % etype.lower()
            for uuid in uuids:
                tmp_tablename = "%s_%s" % (tablename, uuid)
                store._tmp_data_cleanup(tmp_tablename, etype, uuid)
        # get back relation data from the temporary tables
        for rtype, uuids in list(relations.items()):
            tablename = "%s_relation" % rtype.lower()
            for uuid in uuids:
                tmp_tablename = "%s_%s" % (tablename, uuid)
                store._tmp_data_cleanup(tmp_tablename, rtype, uuid)
    # delete the meta data table
    store.sql("DROP TABLE IF EXISTS cwmassive_initialized")
    store.commit()


class NoDropPGHelper(PGHelper):
    def drop_indexes(self, tablename):
        """Drop indexes and constraints, storing them in a table for later restore."""
        # Create a table to save the constraints, it allows reloading even after crash
        pass

    def drop_constraints(self, tablename):
        pass


class DeferredMassiveObjectStore(MassiveObjectStore):
    def master_init(self, commit=True):
        super().master_init(commit=commit)
        if not self._dbh.table_exists("cwmassive_initialized"):
            return
        # ADD REPLICA IDENTITY
        self.sql('ALTER TABLE IF EXISTS "cwmassive_initialized" REPLICA IDENTITY FULL;')
        if commit:
            self.commit()

    def prepare_insert_relation(self, eid_from, rtype, eid_to, **kwargs):
        """Insert into the database a  relation ``rtype`` between entities with eids ``eid_from``
        and ``eid_to``.

        Relation must not be inlined.
        """
        if rtype not in self._initialized:
            if not self.slave_mode:
                self.master_init(commit=False)
            assert not self._cnx.vreg.schema.relation_schema_for(rtype).inlined
            self._initialized[rtype] = None
            tablename = "%s_relation" % rtype.lower()
            tmp_tablename = "%s_%s" % (tablename, self.uuid)
            self.sql(
                "INSERT INTO cwmassive_initialized VALUES (%(r)s, 'rtype', %(uuid)s)",
                {"r": rtype, "uuid": self.uuid},
            )
            self.sql("CREATE TABLE %s(eid_from integer, eid_to integer)" % tmp_tablename)
            # start FA
            self.sql("ALTER TABLE %s ADD PRIMARY KEY (eid_from, eid_to);" % tmp_tablename)
            # stop FA
        self._data_relations[rtype].append({"eid_from": eid_from, "eid_to": eid_to})

    def prepare_insert_entity(self, etype, **data):
        """Given an entity type, attributes and inlined relations, returns the inserted entity's
        eid.
        """
        if etype not in self._initialized:
            if not self.slave_mode:
                self.master_init(commit=False)
            tablename = "cw_%s" % etype.lower()
            tmp_tablename = "%s_%s" % (tablename, self.uuid)
            self.sql(
                "INSERT INTO cwmassive_initialized VALUES (%(e)s, 'etype', %(uuid)s)",
                {"e": etype, "uuid": self.uuid},
            )
            attr_defs = eschema_sql_def(self._source_dbhelper, self.schema[etype])
            self.sql(
                "CREATE TABLE %s(%s);"
                % (
                    tmp_tablename,
                    ", ".join("cw_%s %s" % (column, sqltype) for column, sqltype in attr_defs),
                )
            )
            # start FA
            self.sql("ALTER TABLE %s ADD PRIMARY KEY (cw_eid);" % tmp_tablename)
            # stop FA
            self._initialized[etype] = [attr for attr, _ in attr_defs]

        if "eid" not in data:
            # If eid is not given and the eids sequence is set, use the value from the sequence
            eid = self.get_next_eid()
            data["eid"] = eid
        self._data_entities[etype].append(data)
        return data["eid"]

    def finish(self):
        """differ all differable constraints (foreign keys) to allow delete/insert/update
        in any order in the massive import with no superuser"""
        deffer_foreign_key_constraints(self._cnx)
        super().finish()

    def flush_relations(self):
        """Flush the relations data from in-memory structures to a temporary table."""
        for rtype, data in self._data_relations.items():
            if not data:
                # There is no data for these etype for this flush round.
                continue
            # remove duplicated values
            self._data_relations[rtype] = [
                dict(x) for x in set(tuple(y.items()) for y in self._data_relations[rtype])
            ]
        super().flush_relations()


def create_massive_store(cnx, nodrop=False, **kwargs):
    metagen = MetadataGenerator(cnx, meta_skipped=("owned_by", "created_by"))
    store = DeferredMassiveObjectStore(cnx, metagen=metagen, **kwargs)
    if nodrop:
        store._dbh = NoDropPGHelper(cnx)
    return store
