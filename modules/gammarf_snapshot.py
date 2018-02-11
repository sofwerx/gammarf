#!/usr/bin/env python3
# snapshot module
#
# Joshua Davis (gammarf -*- covert.codes)
# http://gammarf.io
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import datetime
import threading
import time
from uuid import uuid4

import gammarf_util
from gammarf_base import GrfModuleBase

MAX_BW = int(100e6)
MOD_NAME = "snapshot"
MODULE_SNAPSHOT = 5
PROTOCOL_VERSION = 1
SEND_SLEEP = .001


def start(config):
    return GrfModuleSnapshot(config)


class Snapshot(threading.Thread):
    def __init__(self, lowfreq, highfreq, devid,
            system_mods, settings, remotetask):

        threading.Thread.__init__(self)

        self.connector = system_mods['connector']
        self.devmod = system_mods['devices']
        self.spectrum = system_mods['spectrum']

        self.lowfreq = lowfreq
        self.highfreq = highfreq
        self.devid = devid
        self.remotetask = remotetask

    def run(self):
        data = {}
        snapshotid = str(uuid4())
        data['snapshotid'] = snapshotid
        data['module'] = MODULE_SNAPSHOT
        data['protocol'] = PROTOCOL_VERSION

        freq = self.lowfreq
        step = self.devmod.get_hackrf_step()
        while freq <= self.highfreq:
            pwr = str(self.spectrum.pwr(freq))
            if not pwr:
                continue

            data['freq'] = freq
            data['pwr'] = pwr
            try:
                self.connector.senddat(data)
            except:  # shutting down
                pass

            freq += step
            time.sleep(SEND_SLEEP)

        data['freq'] = 0  # inform server this is final
        self.connector.senddat(data)
        gammarf_util.console_message("sent snapshot (id: {}) at {}"
                .format(snapshotid, datetime.datetime.now()),
                MOD_NAME)

        if not self.remotetask:
            self.devmod.freedev(self.devid)

        return


class GrfModuleSnapshot(GrfModuleBase):
    """ Snapshot: Take a snapshot of the RF spectrum

        Usage: run snapshot devid lowfreq highfreq
            Where lowfreq and highfreq are rtl_power format or integers

        Example: > run snapshot 0 100M 200M

        Settings:
    """

    def __init__(self, config):
        self.device_list = ["hackrf", "virtual"]
        self.description = "snapshot module"
        self.settings = {}
        self.worker = None

        self.thread_timeout = 3

        gammarf_util.console_message("loaded", MOD_NAME)

    # overridden 
    def run(self, grfstate, devid, cmdline, remotetask=False):
        self.remotetask = remotetask
        system_mods = grfstate.system_mods
        devmod = system_mods['devices']

        try:
            lowfreq, highfreq = cmdline.split()
        except (ValueError, AttributeError):
            gammarf_util.console_message(self.__doc__)
            return

        lowfreq = gammarf_util.str_to_hz(lowfreq)
        highfreq = gammarf_util.str_to_hz(highfreq)
        if not lowfreq or not highfreq:
            gammarf_util.console_message(self.__doc__)
            return

        maxfreq = int(devmod.get_hackrf_maxfreq()*1e6)
        minfreq = int(devmod.get_hackrf_minfreq()*1e6)
        if lowfreq < minfreq or highfreq > maxfreq:
            gammarf_util.console_message("frequency out of range",
                    MOD_NAME)
            return

        if highfreq < lowfreq:
            gammarf_util.console_message("invalid frequency range",
                    MOD_NAME)
            return


        if highfreq - lowfreq > MAX_BW:
            gammarf_util.console_message(
                    "range exceeds maximum bandwidth of {}".format(MAX_BW),
                    MOD_NAME)
            return

        self.worker = Snapshot(int(lowfreq), int(highfreq),
                devid, system_mods, self.settings, self.remotetask)
        self.worker.daemon = True
        self.worker.start()

        gammarf_util.console_message("{} added on device {}"
                .format(self.description, devid),
                MOD_NAME)
        return True

    def stop(self, devid, devmod):
        if self.worker:
            gammarf_util.console_message("please wait for job to finish",
                    MOD_NAME)
        return False
