#!/usr/bin/env python3
# location module
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
from gps3 import agps3

import gammarf_util
from gammarf_base import GrfModuleBase

GPS_EXPIRE_S = 15
GPS_SLEEP = 0.01
MOD_NAME = "location"


def start(config):
    return GrfModuleLocation(config)


class StaticGpsWorker():
    def __init__(self, gpslat, gpslng):
        self.lat = gpslat
        self.lng = gpslng

    def get_current(self):
        return {'lat': self.lat,
                'lng': self.lng,
                'alt': 0,
                'epx': 0,
                'epy': 0,
                'epv': 0}

    def get_status(self):
        return 'static'


class GpsWorker(threading.Thread):
    def __init__(self):
        self.stoprequest = threading.Event()
        threading.Thread.__init__(self)

        self.gps_socket = agps3.GPSDSocket()
        self.data_stream = agps3.DataStream()
        self.gps_socket.connect()
        self.gps_socket.watch()

        self.current = {}
        self.previous = None
        self.last_time = None

    def get_current(self):
        if (self.last_time) and (int(time.time())
                - self.last_time > GPS_EXPIRE_S):
            return None

        fix = {'lat': str(self.current['lat']),
                'lng': str(self.current['lng']),
                'alt': str(self.current['alt']),
                'epx': str(self.current['epx']),  #
                'epy': str(self.current['epy']),  # position error
                'epv': str(self.current['epv'])}  #

        for key, val in fix.items():
            if val == 'n/a':
                return self.previous

        self.previous = {'lat': fix['lat'],
                'lng': fix['lng'],
                'alt': fix['alt'],
                'epx': fix['epx'],
                'epy': fix['epy'],
                'epv': fix['epv']}

        return fix

    def get_status(self):
        return 'gps'

    def run(self):
        while not self.stoprequest.isSet():
            for new_data in self.gps_socket:
                if new_data:
                    self.data_stream.unpack(new_data)
                    self.current['lat'] = self.data_stream.lat
                    self.current['lng'] = self.data_stream.lon
                    self.current['alt'] = self.data_stream.alt
                    self.current['epx'] = self.data_stream.epx
                    self.current['epy'] = self.data_stream.epy
                    self.current['epv'] = self.data_stream.epv

                    self.last_time = int(time.time())
                else:
                    time.sleep(GPS_SLEEP)

        return

    def join(self, timeout=None):
        self.stoprequest.set()
        super(GpsWorker, self).join(timeout)


class GrfModuleLocation(GrfModuleBase):
    def __init__(self, config):
        if not 'location' in config:
            raise Exception("No location section defined in config")

        try:
            usegps = config['location']['usegps']
        except KeyError:
            raise Exception("param 'usegps' not appropriately "\
                    "defined in config")

        self.usegps = int(usegps)
        if self.usegps == 0:
            try:
                slat = config['location']['lat']
                slng = config['location']['lng']
            except KeyError:
                raise Exception("GPS off, but static location not "\
                        "defined in config")
            else:
                self.worker = StaticGpsWorker(slat, slng)
                gammarf_util.console_message("using static location",
                        MOD_NAME)

        elif self.usegps == 1:
            self.worker = GpsWorker()
            self.worker.daemon = True
            self.worker.start()
            gammarf_util.console_message("using GPS", MOD_NAME)
        else:
            raise Exception("usegps in config must be 0 or 1")

        self.description = "location module"
        self.settings = {}

        self.thread_timeout = 3

        gammarf_util.console_message("loaded", MOD_NAME)

    def get_current(self):
        return self.worker.get_current()

    def get_status(self):
        return self.worker.get_status()

    # overridden 
    def info(self):
        if self.usegps:
            gammarf_util.console_message("using GPS", MOD_NAME)
        else:
            gammarf_util.console_message("using static location", MOD_NAME)

        fix = self.worker.get_current()
        if not fix:
            gammarf_util.console_message("no gps fix", MOD_NAME)
        else:
            gammarf_util.console_message("lat: {}, lng: {}"
                    .format(fix['lat'], fix['lng']),
                    MOD_NAME)

    def shutdown(self):
        gammarf_util.console_message("shutting down {}"
                .format(self.description))
        return
