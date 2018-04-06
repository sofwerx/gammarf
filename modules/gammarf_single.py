#!/usr/bin/env python3
# single module
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

import threading
import time
import numpy as np
from rtlsdr import RtlSdr
from scipy import signal

import gammarf_util
from gammarf_base import GrfModuleBase

F_BW = 500
Fs = 2.4e6
MOD_NAME = "single"
MODULE_SINGLE = 9
N = 65536
PROTOCOL_VERSION = 1
LPF_TAPS = 64


def start(config):
    return GrfModuleSingle(config)


class Single(threading.Thread):
    def __init__(self, opts, system_mods, settings):
        self.stoprequest = threading.Event()
        threading.Thread.__init__(self)

        self.connector = system_mods['connector']
        devmod = system_mods['devices']

        self.freq = opts['freq']
        self.thresh = opts['thresh']

        self.devid = opts['devid']
        self.gain = devmod.get_rtlsdr_gain(self.devid)
        self.ppm = devmod.get_rtlsdr_ppm(self.devid)
        self.sysdevid = devmod.get_sysdevid(self.devid)

        self.settings = settings


    def run(self):
        try:
            self.sdr = RtlSdr(self.sysdevid)
            self.sdr.sample_rate = Fs
            self.sdr.center_freq = self.freq
            self.sdr.gain = self.gain
            self.sdr.ppm = self.ppm
        except:
            gammarf_util.console_message("error initializing device", MOD_NAME)
            self.devmod.freedev(self.devid)
            self.sdr.close()
            return

        data = {}
        data['module'] = MODULE_SINGLE
        data['protocol'] = PROTOCOL_VERSION

        self.lpf = signal.remez(LPF_TAPS,
                [0, F_BW, F_BW+(Fs/2-F_BW)/4, Fs/2], [1,0], Hz=Fs)

        while not self.stoprequest.isSet():
            x1 = self.sdr.read_samples(N)
            x3 = signal.lfilter(self.lpf, 1.0, x1)

            pwr = (10*np.log10(np.mean(np.absolute(x3))))
            if pwr > self.thresh:
                if self.settings['print_all']:
                    gammarf_util.console_message("hit on {}: {}"
                            .format(self.freq, pwr), MOD_NAME)

                data['freq'] = self.freq
                data['thresh'] = self.thresh
                data['pwr'] = pwr
                self.connector.senddat(data)

        try:
            self.sdr.close()
        except:
            gammarf_util.console_message("error closing device", MOD_NAME)
            self.devmod.removedev(self.devid)

        return

    def join(self, timeout=None):
        self.stoprequest.set()
        super(Single, self).join(timeout)


class GrfModuleSingle(GrfModuleBase):
    """ Single: watch power just around a single frequency

        Usage: run single devid freq threshold

        Example: run single 0 100M -10

        Settings:
                print_all: Print hits
    """

    def __init__(self, config):
        self.device_list = ["rtlsdr"]
        self.description = "single module"
        self.settings = {'print_all': False}
        self.worker = None

        self.thread_timeout = 5

        gammarf_util.console_message("loaded", MOD_NAME)

    # overridden
    def run(self, grfstate, devid, cmdline, remotetask=False):
        self.remotetask = remotetask
        self.system_mods = grfstate.system_mods
        devmod = self.system_mods['devices']

        if self.worker:
            gammarf_util.console_message("module already running", MOD_NAME)
            return

        try:
            freq, thresh = cmdline.split()
        except (ValueError, AttributeError):
            gammarf_util.console_message(self.__doc__)
            return

        freq = gammarf_util.str_to_hz(freq)
        if not freq:
            gammarf_util.console_message(self.__doc__)
            return

        try:
            thresh = float(thresh)
        except ValueError:
            gammarf_util.console_message(self.__doc__)
            return

        opts = {'devid': devid,
                'freq': freq,
                'thresh': thresh}

        self.worker = Single(opts, self.system_mods, self.settings)
        self.worker.daemon = True
        self.worker.start()

        gammarf_util.console_message("{} added on device {}"
                .format(self.description, devid))
        return True
