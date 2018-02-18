#!/usr/bin/env python3
# tpms module
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

import json
import os
import threading
import time
from subprocess import Popen, PIPE
from sys import builtin_module_names

import gammarf_util
from gammarf_base import GrfModuleBase

LOOP_SLEEP = 0.1
MOD_NAME = "tpms"
MODULE_TPMS = 8
PROTOCOL_VERSION = 1
RTL_433_PROTOS = [59, 60, 82, 88, 89, 90, 95]

def start(config):
    return GrfModuleTpms(config)


class Tpms(threading.Thread):
    def __init__(self, opts, system_mods, settings):
        self.stoprequest = threading.Event()
        threading.Thread.__init__(self)

        cmd = opts['cmd']
        devid = opts['devid']

        self.connector = system_mods['connector']
        devmod = system_mods['devices']
        gain = devmod.get_rtlsdr_gain(devid)
        ppm = devmod.get_rtlsdr_ppm(devid)
        sysdevid = devmod.get_sysdevid(devid)

        self.settings = settings

        ON_POSIX = 'posix' in builtin_module_names
        # no gain option b/c works best with '0' (auto) gain
        cmd_list = [cmd, "-d {}".format(sysdevid), "-p {}".format(ppm),
                "-F{}".format('json')]
        cmd_list.extend(["-R{}".format(i) for i in RTL_433_PROTOS])
        self.cmdpipe = Popen(cmd_list, stdout=PIPE, close_fds=ON_POSIX)

    def run(self):
        data = {}
        data['module'] = MODULE_TPMS
        data['protocol'] = PROTOCOL_VERSION

        while not self.stoprequest.isSet():
            msg = self.cmdpipe.stdout.readline().strip()
            if len(msg) == 0:
                time.sleep(LOOP_SLEEP)
                continue

            msg = msg.decode('utf-8')
            try:
                msg = json.loads(msg)
            except Exception as e:
                continue

            try:
                model = msg['model']
                tpms_type = msg['type']
                tpms_id = msg['id']
            except Exception:
                continue

            data['model'] = model
            data['type'] = tpms_type
            data['id'] = tpms_id
            self.connector.senddat(data)

            if self.settings['print_all']:
                gammarf_util.console_message("Model: {}, Type: {}, ID: {}"
                        .format(model, tpms_type, tpms_id),
                        MOD_NAME)

        try:
            self.cmdpipe.stdout.close()
            self.cmdpipe.kill()
            os.kill(self.cmdpipe.pid, 9)
            os.wait()
        except:
            pass

        return

    def join(self, timeout=None):
        self.stoprequest.set()
        super(Tpms, self).join(timeout)


class GrfModuleTpms(GrfModuleBase):
    """ TPMS: Vehicle tire pressure

        Usage: run tpms devid

        Example: run tpms 0

        Settings:
                print_all: Print results as they're intercepted
    """

    def __init__(self, config):
        if not 'rtl_path' in config['rtldevs']:
            raise Exception("'rtl_path' not appropriately defined in config")
        rtl_path = config['rtldevs']['rtl_path']

        command = rtl_path + '/' + 'rtl_433'
        if not os.path.isfile(command) or not os.access(command, os.X_OK):
            raise Exception("executable rtl_433 not found in specified path")

        self.device_list = ["rtlsdr"]
        self.description = "tpms module"
        self.settings = {'print_all': False}
        self.worker = None
        self.cmd = command

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

        opts = {'cmd': self.cmd,
                'devid': devid}

        self.worker = Tpms(opts, self.system_mods, self.settings)
        self.worker.daemon = True
        self.worker.start()

        gammarf_util.console_message("{} added on device {}"
                .format(self.description, devid))
        return True
