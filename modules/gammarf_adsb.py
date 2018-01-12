#!/usr/bin/env python3
# ads-b module
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

import os
import threading
import time
import pyModeS as pms
from subprocess import Popen, PIPE
from sys import builtin_module_names

import gammarf_util
from gammarf_base import GrfModuleBase

MOD_NAME = "adsb"
MODULE_ADSB = 3
PROTOCOL_VERSION = 1


def start(config):
    return GrfModuleAdsb(config)


class Adsb(threading.Thread):
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
        self.cmdpipe = Popen([cmd, "-d {}".format(sysdevid),
            "-p {}".format(ppm), "-g {}".format(gain)], stdout=PIPE,
            close_fds=ON_POSIX)


    def run(self):
        data = {}
        data['module'] = MODULE_ADSB
        data['protocol'] = PROTOCOL_VERSION

        poscache = {}

        while not self.stoprequest.isSet():
            msg = self.cmdpipe.stdout.readline().strip()

            if len(msg) == 0:
                continue

            msg = msg.decode('utf-8')
            if not msg.startswith('*') or not msg.endswith(';'):
                continue

            msg = msg[1:-1]
            if len(msg) != 28:
                continue

            crc = pms.util.hex2bin(msg[-6:])
            p = pms.util.crc(msg, encode=True)
            if p != crc:
                continue

            df = pms.df(msg)  # downlink format
            if df == 17:  # ads-b
                tc = pms.adsb.typecode(msg)  # type code
                if 1 <= tc <= 4:  # identification message
                    icao = pms.adsb.icao(msg)
                    callsign = pms.adsb.callsign(msg)

                    if self.settings['print_all']:
                        gammarf_util.console_message("(ID) ICAO: {}, Callsign: {}"
                                .format(icao, callsign),
                                MOD_NAME)

                    data['icao'] = icao
                    data['callsign'] = callsign.strip('_')
                    data['aircraft_lat'] = None
                    data['aircraft_lng'] = None
                    data['altitude'] = None
                    data['heading'] = None
                    data['updownrate'] = None
                    data['speedtype'] = None
                    data['speed'] = None

                elif 9 <= tc <= 18:  # airborne position
                    icao = pms.adsb.icao(msg)
                    altitude = pms.adsb.altitude(msg)

                    if icao in poscache and poscache[icao]:
                        (recent_tc, recent_msg, recent_time) = poscache[icao]
                        if recent_tc != tc:
                            poscache[icao] = None
                            continue

                        recent_odd = (pms.util.hex2bin(recent_msg)[53] == '1')
                        msg_odd = (pms.util.hex2bin(msg)[53] == '1')

                        if recent_odd != msg_odd:
                            if recent_odd:
                                oddmsg = recent_msg
                                evenmsg = msg
                                t_odd = recent_time
                                t_even = time.time()
                            else:
                                oddmsg = msg
                                evenmsg = recent_msg
                                t_odd = time.time()
                                t_even = recent_time

                            pos = pms.adsb.position(oddmsg, evenmsg,
                                    t_odd, t_even)
                            if not pos:
                                continue
                            lat, lng = pos

                        else:
                            poscache[icao] = (tc, msg, time.time())
                            continue

                    else:
                        poscache[icao] = (tc, msg, time.time())
                        continue

                    if self.settings['print_all']:
                        gammarf_util.console_message(
                            "(POS) ICAO: {}, Lat: {}, Lng: {}, Alt: {}"
                                .format(icao, lat, lng, altitude),
                                MOD_NAME)

                    data['icao'] = icao
                    data['callsign'] = None
                    data['aircraft_lat'] = lat
                    data['aircraft_lng'] = lng
                    data['altitude'] = altitude
                    data['heading'] = None
                    data['updownrate'] = None
                    data['speedtype'] = None
                    data['speed'] = None

                elif tc == 19:  # airborne velocities
                    icao = pms.adsb.icao(msg)
                    velocity = pms.adsb.velocity(msg)
                    speed, heading, updownrate, speedtype = velocity

                    if self.settings['print_all']:
                        gammarf_util.console_message(
                                "[adsb] (VEL) ICAO: {}, Heading: {}, "\
                                "ClimbRate: {}, Speedtype: {}, Speed: {}"
                                .format(icao, heading, updownrate,
                                    speedtype, speed),
                                MOD_NAME)

                    data['icao'] = icao
                    data['callsign'] = None
                    data['aircraft_lat'] = None
                    data['aircraft_lng'] = None
                    data['altitude'] = None
                    data['heading'] = heading
                    data['updownrate'] = updownrate
                    data['speedtype'] = speedtype
                    data['speed'] = speed

                else:
                    continue

                self.connector.senddat(data)

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
        super(Adsb, self).join(timeout)


class GrfModuleAdsb(GrfModuleBase):
    """ ADS-B: Report flight information

        Usage: run adsb devid

        Example: run adsb 0

        Settings:
                print_all: Print flight messages as they're intercepted
    """

    def __init__(self, config):
        if not 'rtl_path' in config['rtldevs']:
            raise Exception("'rtl_path' not appropriately defined in config")
        rtl_path = config['rtldevs']['rtl_path']

        command = rtl_path + '/' + 'rtl_adsb'
        if not os.path.isfile(command) or not os.access(command, os.X_OK):
            raise Exception("executable rtl_adsb not found in specified path")

        self.device_list = ["rtlsdr"]
        self.description = "adsb module"
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

        self.worker = Adsb(opts, self.system_mods, self.settings)
        self.worker.daemon = True
        self.worker.start()

        gammarf_util.console_message("{} added on device {}"
                .format(self.description, devid))
        return True
