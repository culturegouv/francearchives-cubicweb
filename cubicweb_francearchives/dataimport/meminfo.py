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
"""based on http://www.pixelbeat.org/scripts/ps_mem.py"""
import os


PAGESIZE = os.sysconf("SC_PAGE_SIZE") / 1024  # KiB


def human(num, power="Ki"):
    powers = ["Ki", "Mi", "Gi", "Ti"]
    while num >= 1000:  # 4 digits
        num /= 1024.0
        power = powers[powers.index(power) + 1]
    return "%.1f %sB" % (num, power)


def memprint(pid=None, logger=None):
    if pid is None:
        pid = os.getpid()
    have_pss = False
    private_lines = []
    shared_lines = []
    pss_lines = []
    try:
        rss = int(open("/proc/%s/statm" % pid).readline().split()[1]) * PAGESIZE
    except IOError:
        if logger is not None:
            logger.error("unknown process", pid)
        return
    if os.path.exists("/proc/%s/smaps" % pid):  # stat
        for line in open("/proc/%s/smaps" % pid).readlines():  # open
            if line.startswith("Shared"):
                shared_lines.append(line)
            elif line.startswith("Private"):
                private_lines.append(line)
            elif line.startswith("Pss"):
                have_pss = True
                pss_lines.append(line)
        shared = sum([int(line.split()[1]) for line in shared_lines])
        private = sum([int(line.split()[1]) for line in private_lines])
        # Note shared + Private = Rss above
        # The Rss in smaps includes video card mem etc.
        if have_pss:
            pss_adjust = 0.5  # add 0.5KiB as this average error due to trunctation
            pss = sum([float(line.split()[1]) + pss_adjust for line in pss_lines])
            shared = pss - private
    else:
        shared = int(open("/proc/%s/statm" % pid).readline().split()[2])
        shared *= PAGESIZE
        private = rss - shared
    # private : private
    # shared : shared
    # rss : RAM used
    return human(rss)
