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

import os
import os.path as p
import time
import logging
import re
import subprocess as subp
import re

from nose2.tools import such
from nose2.tools.params import params

_logger = logging.getLogger(__name__)

HDLCC_LOCATION = './hdlcc/runner.py'

def shell(cmd):
    """Dummy wrapper for running shell commands, checking the return value and
    logging"""

    _logger.debug(cmd)
    exc = None
    try:
        stdout = list(subp.check_output(
            cmd, stderr=subp.STDOUT).split("\n"))
    except subp.CalledProcessError as exc:
        stdout = list(exc.output.split("\n"))

    for line in stdout:
        if re.match(r"^\s*$", line):
            continue
        _logger.debug(line)

    if exc:
        raise exc

    return stdout

with such.A('hdlcc standalone tool') as it:
    @it.has_setup
    def setup():
        it.assertTrue(p.exists(HDLCC_LOCATION))

    with it.having('a valid project file'):

        with it.having('a valid environment'):

            @it.should("print the tool's help")
            def test():
                cmd = ['coverage', 'run',
                       HDLCC_LOCATION, '-h']
                shell(cmd)

            @it.should("build a project")
            def test():
                cmd = ['coverage', 'run',
                       HDLCC_LOCATION, 'dependencies/hdl_lib/ghdl.prj', '-b']

                shell(cmd)

            @it.should("run debug arguments")
            @params(('--debug-print-sources', ),
                    ('--debug-print-compile-order', ),

                    ('--build', '-s',
                     './dependencies/hdl_lib/memory/testbench/async_fifo_tb.vhd'),

                    ('--debug-parse-source-file', '-s',
                     './dependencies/hdl_lib/memory/testbench/async_fifo_tb.vhd'),

                    ('--debug-run-static-check', '-s',
                     './dependencies/hdl_lib/memory/testbench/async_fifo_tb.vhd'),)

            def test(case, *args):
                _logger.info("Running '%s'", case)
                cmd = ['coverage', 'run',
                       HDLCC_LOCATION, 'dependencies/hdl_lib/ghdl.prj']
                for arg in args:
                    cmd.append(arg)

                shell(cmd)


            @it.should("save profiling info if requested")
            def test():
                cmd = ['coverage', 'run',
                       HDLCC_LOCATION, 'dependencies/hdl_lib/ghdl.prj',
                       '--debug-profiling', 'output.stats']

                if p.exists('output.stats'):
                    os.remove('output.stats')

                shell(cmd)

                it.assertTrue(p.exists('output.stats'))

            @it.should("control debugging level")
            def test():
                cmd = ['coverage', 'run',
                       HDLCC_LOCATION, 'dependencies/hdl_lib/ghdl.prj', '-cb']

                it.assertEqual(shell(cmd), [''])

                previous = None
                for level in range(1, 5):
                    stdout = shell(cmd + ['-' + 'v'*level])
                    it.assertTrue(len(stdout) >= previous)
                    previous = len(stdout)

        with it.having('an invalid environment'):
            pass

it.createTests(globals())

