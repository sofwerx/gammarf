#!/usr/bin/env python3
# remotetask module
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

ERROR_SLEEP = 1
JOBSTOP_SLEEP = 2
LOOP_SLEEP = 5
MOD_NAME = "remotetask"
PROTOCOL_VERSION = 1
REQ_RTASK_ASKCANCEL = 10
REQ_RTASK_GET = 3
REQ_RTASK_PUT = 2


def start(config):
    return GrfModuleRemotetask(config)


class RemoteTaskDispatcher(threading.Thread):
    def __init__(self, devid, module, grfstate, settings):
        threading.Thread.__init__(self)
        self.stoprequest = threading.Event()

        self.config = grfstate.config
        self.connector = grfstate.system_mods['connector']
        self.devmod = grfstate.system_mods['devices']
        self.devid = devid
        self.grfstate = grfstate
        self.loadedmods = grfstate.loadedmods
        self.settings = settings

        self.targetmod = module
        self.jobmodule = grfstate.loadedmods[self.targetmod]

    def run(self):
        while not self.stoprequest.isSet():
            resp = self.connector.sendcmd({'request': REQ_RTASK_GET,
                'module': self.targetmod, 'protocol': PROTOCOL_VERSION})
            reply = resp['reply']
            if reply == 'ok':
                try:
                    duration = int(resp['duration'])
                    fromstn = resp['from']
                    taskid = resp['taskid']
                    params = resp['params']
                except Exception:
                    continue

                if self.jobmodule.run(self.grfstate, self.devid,
                        params, remotetask=True):
                    started = time.time()
                    if self.settings['print_tasks']:
                        gammarf_util.console_message(
                                "received {} task from {} with "\
                                "duration {} and params {} for device {}"
                                .format(self.targetmod, fromstn, duration,
                                    params, self.devid), MOD_NAME)

                    while True:
                        if time.time() - started >= duration:
                            self.jobmodule.stop(self.devid, self.devmod)

                            if self.settings['print_tasks']:
                                gammarf_util.console_message(
                                        "finished {} task on device {}"
                                        .format(self.targetmod, self.devid),
                                        MOD_NAME)

                            break

                        elif self.stoprequest.isSet():
                            self.jobmodule.stop(self.devid, self.devmod)
                            break

                        resp = self.connector.sendcmd({
                            'request': REQ_RTASK_ASKCANCEL,
                            'taskid': taskid,
                            'protocol': PROTOCOL_VERSION})
                        reply = resp['reply']
                        if reply == 'cancel':
                            gammarf_util.console_message(
                                "job for {} on device {} canceled by server"
                                    .format(self.targetmod, self.devid),
                                    MOD_NAME)

                            self.jobmodule.stop(self.devid, self.devmod)
                            break
                        elif reply == 'nocancel':
                            pass
                        elif reply == 'error':
                            gammarf_util.console_message(
                                "error asking cancel status for task: {}"
                                .format(resp['error']), MOD_NAME)

                        time.sleep(LOOP_SLEEP)

            elif reply == 'error':
                gammarf_util.console_message("error receiving task: {}"
                        .format(resp['error']),
                        MOD_NAME)
                time.sleep(LOOP_SLEEP)

            else:  # 'none'
                time.sleep(LOOP_SLEEP)

        self.devmod.freedev(self.devid)
        return

    def join(self, timeout=None):
        self.stoprequest.set()
        super(RemoteTaskDispatcher, self).join(timeout)


class GrfModuleRemotetask(GrfModuleBase):
    """ Remotetask: Run tasks for others

        Usage: run remotetask devid module
        or: remotetask station duration module args
            (to request another station to run a module on your behalf.
                duration is in seconds.)

        Example: run remotetask 0 scanner
        Example: remotetask grf01 5000 freqwatch 100M

        Settings:
            print_tasks: List remote tasks your node grabs from the queue
    """

    def __init__(self, config):
        self.description = "remotetask module"
        self.config = config
        self.settings = {'print_tasks': True}
        self.workers = []

        self.thread_timeout = 3

        gammarf_util.console_message("loaded", MOD_NAME)

    def request(self, reqline, connector):
        if not reqline:
            self.request_help()
            return

        args = reqline.split(None, 3)
        if len(args) < 3:  # module params optional
            self.request_help()
            return

        try:
            target = args[0]
            duration = int(args[1])
            module = args[2]
        except Exception as e:
            self.request_help()
            return

        data = {}
        data['request'] = REQ_RTASK_PUT
        data['target'] = target
        data['duration'] = int(duration)
        data['module'] = module
        data['protocol'] = PROTOCOL_VERSION
        data['params'] = 'none'

        if len(args) == 4:
            data['params'] = args[3]

        resp = connector.sendcmd(data)
        if resp['reply']  == 'ok':
            gammarf_util.console_message("task sent",
                    MOD_NAME)

        elif resp['reply'] == 'task_exists':
            gammarf_util.console_message("only one uncompleted request "\
                    "per module type per station can exist in "\
                    "the database at once",
                    MOD_NAME)

        else:
            gammarf_util.console_message("error sending task: {}"
                    .format(resp['error']),
                    MOD_NAME)

        return

    def request_help(self):
        gammarf_util.console_message(
                "usage: remotetask station duration(s) module [args]",
                MOD_NAME)
        return

    # Commands we provide
    def cmd_remotetask(self, grfstate, args):
        """Request a task be run on another station"""

        system_mods = grfstate.system_mods
        self.request(args, system_mods['connector'])
        return

    # overridden 
    def commands(self):
        return [('remotetask', self.cmd_remotetask)]

    def isproxy(self):
        return True

    def run(self, grfstate, devid, cmdline, remotetask=False):
        config = grfstate.config
        loadedmods = grfstate.loadedmods
        system_mods = grfstate.system_mods
        devmod = system_mods['devices']

        if not cmdline:
            gammarf_util.console_message(self.__doc__)
            return

        args = cmdline.split(None, 1)
        module = args[0]

        if module == 'remotetask':
            gammarf_util.console_message(
                    "remotetask cannot be run remotely",
                    MOD_NAME)
            return

        if module == 'tdoa':
            gammarf_util.console_message("module cannot be run remotely",
                    MOD_NAME)
            return

        if (not module in loadedmods) or (module in system_mods):
            gammarf_util.console_message("invalid module: {}"
                    .format(module),
                    MOD_NAME)
            return

        if loadedmods[module].ispseudo():
            gammarf_util.console_message(
                    "remotetask does not support pseudo modules",
                    MOD_NAME)
            return

        devtype = devmod.get_devtype(devid)
        if not devtype in loadedmods[module].devices():
            gammarf_util.console_message(
                    "device type {} not supported by module"
                    .format(devtype),
                    MOD_NAME)
            return

        rtdispatcher = RemoteTaskDispatcher(devid, module,
                grfstate, self.settings)
        rtdispatcher.daemon = True
        rtdispatcher.start()
        self.workers.append( (devid, rtdispatcher) )

        gammarf_util.console_message("{} added on device {}"
                .format(self.description, devid))
        return True

    def setting(self, setting, arg=None):
        if setting == None:
            for setting, state in self.settings.items():
                gammarf_util.console_message("{}: {} ({})"
                        .format(setting, state, type(state)))
            return True

        if setting == 0:
            return self.settings.keys()

        if setting not in self.settings:
            return False

        if isinstance(self.settings[setting], bool):
            new = not self.settings[setting]
        elif not arg:
            gammarf_util.console_message(
                    "non-boolean setting requires an argument")
            return True
        else:
            if isinstance(self.settings[setting], int):
                new = int(arg)
            elif isinstance(self.settings[setting], float):
                new = float(arg)
            else:
                new = arg

        self.settings[setting] = new

    def shutdown(self):
        gammarf_util.console_message("shutting down {}"
                .format(self.description))
        for worker in self.workers:
            devid, thread = worker
            thread.join(self.thread_timeout)

        return

    def stop(self, devid, devmod):
        for worker in self.workers:
            worker_devid, thread = worker

            if worker_devid == devid:
                thread.join(self.thread_timeout)
                self.workers.remove( (worker_devid, thread) )

                return True

        return False
