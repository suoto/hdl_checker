# This file is part of HDL Code Checker.
#
# HDL Code Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Code Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.

# pylint: disable=function-redefined, missing-docstring, protected-access

import sys
import logging
import os
import os.path as p
from nose2.tools import such
import subprocess as subp
import requests
import time

BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = os.environ.get('BUILDER_PATH', p.expanduser("~/builders/ghdl/bin/"))
HDL_LIB_PATH = p.abspath(p.join(".ci", "hdl_lib"))

if BUILDER_NAME is not None:
    PROJECT_FILE = p.join(HDL_LIB_PATH, BUILDER_NAME + '.prj')
else:
    PROJECT_FILE = None

import hdlcc
from hdlcc.utils import terminateProcess, addToPath, removeFromPath

_logger = logging.getLogger(__name__)
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), '..', '..'))

with such.A("hdlcc server handler") as it:
    def setupPaths():
        "Add our dependencies to sys.path"
        for path in (
                p.join(HDLCC_BASE_PATH, 'dependencies', 'bottle'),
                p.join(HDLCC_BASE_PATH, 'dependencies', 'requests'),
            ):
            path = p.abspath(path)
            if path not in sys.path:
                _logger.info("Adding '%s'", path)
                sys.path.insert(0, path)
            else:
                _logger.warning("WARNING: '%s' was already on sys.path!", path)

    def startCodeCheckerServer():
        hdlcc_server_fname = p.join(HDLCC_BASE_PATH, 'hdlcc',
                                    'code_checker_server.py')

        it._host = '127.0.0.1'
        it._port = '50000'
        it._url = 'http://{0}:{1}'.format(it._host, it._port)
        cmd = ['python',
               '-m', 'coverage', 'run',
               hdlcc_server_fname,
               '--host', it._host, '--port', it._port,
               #  '--attach-to-pid', str(os.getpid()),
               '--stdout', 'hdlcc-stdout.log',
               '--stderr', 'hdlcc-stderr.log',
               '--log-level', 'DEBUG',
              ]

        _logger.info("Starting hdlcc server with '%s'", " ".join(cmd))

        it._server = subp.Popen(
            cmd,
            #  stdout=it._stdout_wr_pipe, stderr=it._stderr_wr_pipe,
            #  stdout=subp.PIPE, stderr=subp.PIPE,
            env=os.environ.copy())

        time.sleep(2)

    @it.has_setup
    def setup():
        _logger.info("Builder name: %s", BUILDER_NAME)
        _logger.info("Builder path: %s", BUILDER_PATH)
        addToPath(BUILDER_PATH)
        setupPaths()
        startCodeCheckerServer()

    @it.has_teardown
    def teardown():
        _logger.info("Shutting down server")
        terminateProcess(it._server.pid)
        removeFromPath(BUILDER_PATH)
        time.sleep(1)

    @it.should("get diagnose info without any project")
    def test():
        reply = requests.post(it._url + '/get_diagnose_info', timeout=10)
        content = reply.json()
        _logger.info(reply.text)
        it.assertNotIn('unknown', content['hdlcc version'])
        it.assertEquals(content, {'hdlcc version' : hdlcc.__version__})

    @it.should("get diagnose info with a non existing project file")
    def test():
        reply = requests.post(it._url + '/get_diagnose_info', timeout=10,
                              data={'project_file' : 'some_project'})
        content = reply.json()
        _logger.info(reply.text)
        it.assertNotIn('unknown', content['hdlcc version'])
        it.assertEquals(content, {'hdlcc version' : hdlcc.__version__})

    @it.should("get diagnose info with an existing project file before it has "
               "parsed the configuration file")
    def test():
        reply = requests.post(it._url + '/get_diagnose_info', timeout=10,
                              data={'project_file' : PROJECT_FILE})
        content = reply.json()
        _logger.info(reply.text)
        it.assertIn('hdlcc version', content)
        it.assertNotIn('error', content)
        it.assertNotIn('unknown', content['hdlcc version'])
        it.assertEquals(
            content,
            {"builder": "<unknown>", "hdlcc version": hdlcc.__version__})

    @it.should("get UI warning when getting messages before project build "
               "has finished")
    def test():
        data = {
            'project_file' : PROJECT_FILE,
            'path'         : p.join(HDL_LIB_PATH, 'memory', 'testbench',
                                    'async_fifo_tb.vhd')}

        ui_messages = requests.post(it._url + '/get_ui_messages', timeout=10,
                                    data=data)

        build_messages = requests.post(it._url + '/get_messages_by_path',
                                       timeout=10, data=data)

        _logger.info(build_messages.text)
        _logger.info("Messages:")
        for message in build_messages.json()['messages']:
            _logger.info(message)

        it.assertEquals(
            build_messages.json(),
            {u'messages': [
                {u'checker'       : u'HDL Code Checker/static',
                 u'column'        : 14,
                 u'error_message' : u"constant 'ADDR_WIDTH' is never used",
                 u'error_number'  : u'0',
                 u'error_subtype' : u'Style',
                 u'error_type'    : u'W',
                 u'filename'      : None,
                 u'line_number'   : 29}]})

        ui_messages = requests.post(it._url + '/get_ui_messages', timeout=10,
                                    data=data)

        _logger.info(ui_messages.text)
        it.assertEquals(
            ui_messages.json(),
            {'ui_messages': [['warning', "Project hasn't finished building, "
                                         "try again after it finishes."]]})

        _logger.info("Waiting for 30s until build is finished")
        for i in range(30):
            time.sleep(1)
            _logger.info("Elapsed %ds", i)
            build_messages = requests.post(it._url + '/get_messages_by_path',
                                           timeout=10, data=data)
            ui_messages = requests.post(it._url + '/get_ui_messages',
                                        timeout=10, data=data)
            _logger.debug("==> %s", ui_messages.json())
            if ui_messages.json()['ui_messages'] == []:
                _logger.info("Ok, done")
                break

if BUILDER_NAME is not None:
    it.createTests(globals())

