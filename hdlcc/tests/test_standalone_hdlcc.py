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

HDLCC_LOCATION = './hdlcc.py'

def shell(cmd):
    """Dummy wrapper for running shell commands, checking the return value and
    logging"""

    _logger.debug(cmd)
    for line in subp.check_output(cmd, ).split("\n"):
        if re.match(r"^\s*$", line):
            continue
        _logger.debug(line)

with such.A('hdlcc standalone tool') as it:
    @it.has_setup
    def setup():
        it.assertTrue(p.exists(HDLCC_LOCATION))

    with it.having('a valid project file'):

        with it.having('a valid environment'):

            @it.should("print the tool's help")
            def test():
                cmd = [HDLCC_LOCATION, '-h']
                shell(cmd)

            @it.should("build a project")
            def test():
                cmd = [HDLCC_LOCATION, 'dependencies/hdl_lib/ghdl.prj',
                       '-b']

                shell(cmd)

            @it.should("run debug arguments")
            @params(('--debug-print-sources', ),
                    ('--debug-print-compile-order', ),
                    ('--debug-parse-source-file', '-s',
                     './dependencies/hdl_lib/memory/testbench/async_fifo_tb.vhd'),
                    ('--debug-run-static-check', '-s',
                     './dependencies/hdl_lib/memory/testbench/async_fifo_tb.vhd'),)
            def test(case, *args):
                _logger.info("Running '%s'", case)
                cmd = [HDLCC_LOCATION, 'dependencies/hdl_lib/ghdl.prj']
                for arg in args:
                    cmd.append(arg)

                shell(cmd)

        with it.having('an invalid environment'):
            pass

it.createTests(globals())

