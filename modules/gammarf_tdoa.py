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

####
##
##  * DO NOT USE THIS MODULE - IT IS NOT IMPLEMENTED ON THE SERVER SIDE *
##
####




import os
import threading
import time
import numpy as np
from subprocess import Popen, STDOUT
from sys import builtin_module_names

import gammarf_util
from gammarf_base import GrfModuleBase

ABORT_SLEEP = 2
GO_WAIT = 5
MOD_NAME = "tdoa"
MODULE_TDOA = 7
PROTOCOL_VERSION = 1
QUERY_SLEEP = 2
REQ_TDOA_ACCEPT = 8
REQ_TDOA_GO = 9
REQ_TDOA_PUT = 5
REQ_TDOA_QUERY = 6
REQ_TDOA_REJECT = 7
SAMPLES = 250000  # this and sample rate need to be the same on all nodes
TDOA_SAMPLE_RATE = 2500000
TDOA_TYPE_TGT = 0
TDOA_TYPE_FIN = 1
TDOA_TYPE_REF = 2


def start(config):
    return GrfModuleTdoa(config)


class Tdoa(threading.Thread):
    def __init__(self, opts, system_mods, settings):
        threading.Thread.__init__(self)
        self.stoprequest = threading.Event()

        self.cmd = opts['cmd']
        self.devid = opts['devid']

        self.connector = system_mods['connector']
        self.devmod = system_mods['devices']
        self.sysdevid = self.devmod.get_sysdevid(self.devid)
        self.gain = self.devmod.get_rtlsdr_gain(self.devid)
        self.offset = self.devmod.get_rtlsdr_offset(self.devid)
        self.ppm = self.devmod.get_rtlsdr_ppm(self.devid)
        self.tdoa_max_freq = self.devmod.get_rtlsdr_maxfreq(self.devid)
        self.tdoa_min_freq = self.devmod.get_rtlsdr_minfreq(self.devid)

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
                time.sleep(ABORT_SLEEP)
                continue

            fixed_tdoafreq = tdoafreq + self.offset
            if fixed_tdoafreq < self.tdoa_min_freq or fixed_tdoafreq > self.tdoa_max_freq:
                req = {'request': REQ_TDOA_REJECT, 'requestor': requestor}
                resp = self.connector.sendcmd(req)
                time.sleep(ABORT_SLEEP)
                continue

            # we will accept this tdoa task
            req = {'request': REQ_TDOA_ACCEPT, 'requestor': requestor}
            resp = self.connector.sendcmd(req)
            if resp['reply'] != 'ok':
                time.sleep(ABORT_SLEEP)
                continue

            # ask the server if we should go ahead
            go_start = int(time.time())
            go = False
            while int(time.time()) < go_start + GO_WAIT:
                req = {'request': REQ_TDOA_GO}
                resp = self.connector.sendcmd(req)
                if resp['reply'] == 'go':
                    go = True
                    break

            if not go:
                continue

            try:
                gotick = resp['gotick']
                jobid = resp['jobid']
                refxmtr = int(resp['refxmtr']) + self.offset
            except:
                time.sleep(ABORT_SLEEP)
                continue

            if self.settings['print_tasks']:
                gammarf_util.console_message("targeting {} for {} "\
                        "(refxmtr: {})"
                .format(tdoafreq, requestor, refxmtr), MOD_NAME)

            outfile = '/tmp/'+jobid+'.tdoa'

            now = int(time.time())
            while now < gotick:
                now = int(time.time())
                time.sleep(.001)

            gammarf_util.console_message("GO at {}"
                    .format(time.time()), MOD_NAME)

            NULL = open(os.devnull, 'w')
            ON_POSIX = 'posix' in builtin_module_names
            self.cmdpipe = Popen([self.cmd, "-d {}".format(self.sysdevid),
                "-p {}".format(self.ppm), "-g {}".format(self.gain),
                "-f {}".format(refxmtr), "-h {}".format(fixed_tdoafreq),
                "-s {}".format(TDOA_SAMPLE_RATE),
                "-n {}".format(SAMPLES), outfile], stdout=NULL,
                stderr=STDOUT, close_fds=ON_POSIX)

            self.cmdpipe.wait()
            gammarf_util.console_message("STOP at {}"
                    .format(time.time()), MOD_NAME)

            # get the phase bytes; assume intel architecture (byte order)
            phases = np.fromfile(outfile, dtype=np.uint8)[::2]
            section_len = int(len(phases)/3)

            data = {}
            data['module'] = MODULE_TDOA
            data['protocol'] = PROTOCOL_VERSION
            data['jobid'] = jobid

            ref_phasediff = np.diff(phases[:section_len])
            for seqnum in range(section_len-1):
                data['type'] = TDOA_TYPE_REF
                data['seqnum'] = seqnum
                data['angle'] = int(ref_phasediff[seqnum])
                self.connector.senddat(data)

            target_phasediff = np.diff(phases[section_len:section_len*2])
            ##### send target data, as above but with TDOA_TYPE_TGT





            data['type'] = TDOA_TYPE_FIN
            self.connector.senddat(data)
            print("Sent TDOA data")
            os.remove(outfile)

            # remove dc component?
            # manually correlate refxmtrs - get it right (experiment with ref types, etc.)
            # automate: python lines up refxmtrs, calculates target location, messages all nodes, deletes from redis, web pop-up (with 'x' to close)


        return

    def join(self, timeout=None):
        self.stoprequest.set()
        super(Tdoa, self).join(timeout)


class GrfModuleTdoa(GrfModuleBase):
    """ TDOA: Work with other stations to locate a transmitter

        Usage: run tdoa devid
        or: tdoa station1 station2 station3 150M

        Example: run tdoa 1
        Example: tdoa stn01 stn02 stn03 150M

        Settings:
            print_tasks: List tdoa jobs your node performs for others
    """

    def __init__(self, config):
        if not 'rtl_2freq_path' in config['rtldevs']:
            raise Exception("'rtl_2freq_path' not appropriately defined in config")
        rtl_2freq_path = config['rtldevs']['rtl_2freq_path']

        command = rtl_2freq_path + '/' + 'rtl_sdr'
        if not os.path.isfile(command) or not os.access(command, os.X_OK):
            raise Exception("executable rtl_sdr not found in specified path")

        self.device_list = ["rtlsdr"]
        self.description = "tdoa module"
        self.settings = {'print_tasks': True}
        self.worker = None
        self.cmd = command

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
            gammarf_util.console_message("request sent", MOD_NAME)
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
                "usage: tdoa station1 station2 station3 freq")
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

        opts = {'cmd': self.cmd, 'devid': devid}

        self.worker = Tdoa(opts, self.system_mods, self.settings)
        self.worker.daemon = True
        self.worker.start()

        gammarf_util.console_message("{} added on device {}"
            .format(self.description, devid))
        return True
