#!/usr/bin/env python3
# tdoa module
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

import gammarf_util
from gammarf_base import GrfModuleBase

ABORT_DELAY = 2
GO_DELAY = 2  # don't change this
GO_SLEEP = 2  # don't change this
MOD_NAME = "tdoa"
MODULE_TDOA = 7
PROTOCOL_VERSION = 1
QUERY_SLEEP = 5  # don't change this
REQ_TDOA_ACCEPT = 8
REQ_TDOA_GO = 9
REQ_TDOA_PUT = 5
REQ_TDOA_QUERY = 6
REQ_TDOA_REJECT = 7
TDOA_MAX_FREQ = 1.6e9
TDOA_MIN_FREQ = 30e6


def start(config):
    return GrfModuleTdoa(config)


class Tdoa(threading.Thread):
    def __init__(self, opts, system_mods, settings):
        threading.Thread.__init__(self)
        self.stoprequest = threading.Event()

        self.devid = opts['devid']

        self.connector = system_mods['connector']
        self.devmod = system_mods['devices']
        self.sysdevid = devmod.get_sysdevid(devid)

        self.settings = settings

    def run(self):
        while not self.stoprequest.isSet():
            req = {'request': REQ_TDOA_QUERY}
            resp = self.connector.sendcmd(req)
            if resp['reply'] != 'task':
                time.sleep(QUERY_SLEEP)
                continue

            try:
                requestor = resp['requestor']
                tdoafreq = resp['tdoafreq']
            except KeyError:
                continue

            if tdoafreq < TDOA_MIN_FREQ or tdoafreq > TDOA_MAX_FREQ:
                req = {'request': REQ_TDOA_REJECT, 'requestor': requestor}
                resp = self.connector.sendcmd(req)
                time.sleep(ABORT_DELAY)
                continue

            # we will accept this tdoa task
            req = {'request': REQ_TDOA_ACCEPT, 'requestor': requestor}
            resp = self.connector.sendcmd(req)
            if resp['reply'] != 'ok':
                time.sleep(ABORT_DELAY)
                continue

            # wait for other stations to accept / reject as well
            time.sleep(GO_SLEEP)

            # ask the server if we should go ahead
            req = {'request': REQ_TDOA_GO}
            resp = self.connector.sendcmd(req)
            if resp['reply'] != 'go':
                time.sleep(ABORT_DELAY)
                continue








            ### server will answer with which refxmtr to use in 'go'
            # (the highest powered 3 probably)
            # when you plug in a pi do wireless first and see if disconnects, then moved to wired and compare (enable message output)
            refxmtr = resp['']





            if self.settings['print_tasks']:
                gammarf_util.console_message("targeting {} for {}"
                .format(tdoafreq, requestor), MOD_NAME)

            time.sleep(GO_DELAY)  # wait for other stations





            # set gain, ppm, and freq offset if defined in conf (use devmod)
            # scan for enough time that there's bound to be enough overlap w/ the other stations' data
            # don't go back to the top of the while loop until all data is send to the server
            # final has 'fin' so it can trigger the server-side relay












        return

    def join(self, timeout=None):
        self.stoprequest.set()
        super(Tdoa, self).join(timeout)


class GrfModuleTdoa(GrfModuleBase):
    """ TDOA: Work with other stations to locate a transmitter

        Usage: run tdoa devid
        or: tdoa station1 station2 station3 150M

        Example: run tdoa 0 1
        Example: tdoa stn01 stn02 stn03 150M

        Settings:
            print_tasks: List tdoa jobs your node performs for others
    """

    def __init__(self, config):
        self.device_list = ["rtlsdr"]
        self.description = "tdoa module"
        self.settings = {'print_tasks': True}
        self.worker = None

        self.thread_timeout = 3

        gammarf_util.console_message("loaded", MOD_NAME)

    def request(self, reqline, connector):
        if not reqline:
            self.request_help()
            return

        args = reqline.split(None)
        if len(args) != 4:
            self.request_help()
            return

        station1, station2, station3, tdoa_freq = args

        tdoa_freq = gammarf_util.str_to_hz(tdoa_freq)
        if not tdoa_freq:
            self.request_help()
            return

        data = {}
        data['request'] = REQ_TDOA_PUT
        data['station1'] = station1
        data['station2'] = station2
        data['station3'] = station3
        data['tdoafreq'] = tdoa_freq
        data['protocol'] = PROTOCOL_VERSION

        resp = connector.sendcmd(data)
        if resp['reply']  == 'ok':
            gammarf_util.console_message("request accepted", MOD_NAME)
        else:
            if resp['error'] == 'invalid station':
                gammarf_util.console_message("invalid station: {}"
                        .format(resp['station']), MOD_NAME)
            elif resp['error'] == 'busy':
                gammarf_util.console_message("station busy: {}"
                    .format(resp['station']), MOD_NAME)
            else:
                gammarf_util.console_message("problem sending task: {}"
                        .format(resp['error']), MOD_NAME)

        return

    def request_help(self):
        gammarf_util.console_message(
                "usage: tdoa station1 station2 station3 freq(MHz)")
        return

    # Commands we provide
    def cmd_tdoa(self, grfstate, args):
        """Request stations run a tdoa"""

        system_mods = grfstate.system_mods
        self.request(args, system_mods['connector'])
        return

    # overridden 
    def commands(self):
        return [('tdoa', self.cmd_tdoa)]

    def run(self, grfstate, devid, cmdline, remotetask=False):
        self.remotetask = remotetask
        self.system_mods = grfstate.system_mods
        self.connector = self.system_mods['connector']
        self.devmod = self.system_mods['devices']
        self.devid = devid

        if self.worker:
            gammarf_util.console_message("module already running", MOD_NAME)
            return

        if self.worker:
            gammarf_util.console_message(
                "module already running (one allowed per node)")
            return

        opts = {'devid': devid}

        self.worker = Tdoa(opts, self.system_mods, self.settings)
        self.worker.daemon = True
        self.worker.start()

        gammarf_util.console_message("{} added on device {}"
            .format(self.description, devid))
        return True
