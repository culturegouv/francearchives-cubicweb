# -*- coding: utf-8 -*-
#
# Copyright © LOGILAB S.A. (Paris, FRANCE) 2025
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

"""small utility functions"""

import hashlib
import logging
import pickle
import redis


from cubicweb.cwconfig import CubicWebConfiguration as cwcfg
from cubicweb.pyramid import settings_from_cwconfig


logger = logging.getLogger("francearchives.redis.cache")


class RedisConnector:
    _instance = None
    _redis_url = None

    def __new__(cls, cnx):
        if cls._instance is None:
            conf = settings_from_cwconfig(cwcfg.config_for(cnx.vreg.config.appid))
            cls._redis_url = conf["redis.sessions.url"]
            cls.pool = redis.ConnectionPool.from_url(cls._redis_url)
            try:
                cls._instance = super().__new__(cls)
                cls._instance.connection = redis.Redis(connection_pool=cls.pool)
            except redis.ConnectionError as ex:
                cls._instance = None
                logger.error(f"No connection found fo redis {cls._redis_url}: {ex}")
        return cls._instance

    def set(self, key, value, expire=86400):
        if self.connection:
            key = self.ensure_key(key)
            self.connection.set(key, pickle.dumps(value), ex=expire)
        else:
            logger.error(f"No connection found fo redis {self._redis_url}")

    def ensure_key(self, key):
        return "pgcache:" + hashlib.sha256((key).encode()).hexdigest()

    def get(self, key):
        if self.connection:
            _key = self.ensure_key(key)
            try:
                value = self.connection.get(_key)
                return pickle.loads(value)
            except Exception as ex:
                logger.error(f"Error while retrieving {key} from redis: {ex}")
        else:
            logger.error(f"No connection found fo redis {self._redis_url}")

        return None


def get_data_with_cache(cnx, key, func, ttl=86400):
    """
    Retrieve data from Redis if available; otherwise,
    call func(**params), cache its result, and return it.

    Args:
        cnx Connection: CubicWeb database connection
        key (str): Redis key under which to cache the data.
        func_params (tuple): params to the func
        ttl (int): Optional time-to-live in seconds (default: 1 day).

    Returns:
        Any: The data (from cache or freshly computed).
    """
    try:
        redis_connection = RedisConnector(cnx)
    except KeyError:
        cached_data = None
        redis_connection = None
    else:
        cached_data = redis_connection.get(key)
    if cached_data:
        return cached_data
    result = func(cnx)
    if redis_connection:
        redis_connection.set(key, result, expire=ttl)
    return result
