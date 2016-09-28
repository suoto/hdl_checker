# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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
import logging
import re
import subprocess as subp
import shutil
from unittest import skipUnless

from nose2.tools import such
from nose2.tools.params import params

_logger = logging.getLogger(__name__)

HDLCC_LOCATION = p.join("hdlcc", "standalone.py")
BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = os.environ.get("BUILDER_PATH", p.expanduser("~/ghdl/bin/"))

_BUILDER_ENV = os.environ.copy()
_BUILDER_ENV["PATH"] = p.expandvars(os.pathsep.join([BUILDER_PATH, \
                                    _BUILDER_ENV["PATH"]]))

TEST_SUPPORT_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support')

if BUILDER_NAME is not None:
    PROJECT_FILE = p.join(TEST_SUPPORT_PATH, "vim-hdl-examples", BUILDER_NAME + ".prj")
else:
    PROJECT_FILE = None

def shell(cmd):
    """Dummy wrapper for running shell commands, checking the return value and
    logging"""

    _logger.debug(cmd)
    exc = None
    stdout = []
    try:
        stdout += list(subp.check_output(
            cmd, stderr=subp.STDOUT, env=_BUILDER_ENV).split("\n"))
    except subp.CalledProcessError as exc:
        stdout += list(exc.output.split("\n"))

    for line in stdout:
        if re.match(r"^\s*$", line):
            continue
        if exc:
            _logger.fatal(line)
        else:
            _logger.debug(line)

    if exc:
        _logger.warning("os.path: %s", os.environ["PATH"])
        _logger.warning("_BUILDER_ENV path: %s", _BUILDER_ENV["PATH"])
        raise exc   # pylint: disable=raising-bad-type

    return stdout

with such.A("hdlcc standalone tool") as it:
    @it.has_setup
    def setup():
        it.assertTrue(p.exists(HDLCC_LOCATION))

    @it.has_teardown
    def teardown():
        cmd = ["coverage", "run",
               HDLCC_LOCATION, PROJECT_FILE,
               "--clean"]

        if PROJECT_FILE is not None:
            shell(cmd)

            if p.exists(p.join(p.dirname(PROJECT_FILE), '.build')):
                shutil.rmtree(p.join(p.dirname(PROJECT_FILE), '.build'))

        if p.exists(p.join(TEST_SUPPORT_PATH, "vim-hdl-examples/.build")):
            shutil.rmtree(p.join(TEST_SUPPORT_PATH, "vim-hdl-examples/.build"))

    with it.having("a valid project file"):

        @it.has_setup
        def setup():
            cleanUp()

        @it.has_teardown
        def teardown():
            cleanUp()

        def cleanUp():
            # Ensure there is no leftover files from previous runs
            path = p.join(TEST_SUPPORT_PATH, "vim-hdl-examples/.build")
            if p.exists(path):
                shutil.rmtree(path)


        with it.having("a valid environment"):

            @it.should("print the tool's help")
            def test():
                cmd = ["coverage", "run",
                       HDLCC_LOCATION, "-h"]
                shell(cmd)

            #  @it.should("build a project")
            #  def test():
            #      cmd = ["coverage", "run",
            #             HDLCC_LOCATION, PROJECT_FILE,
            #             "--build"]

            #      shell(cmd)

            @it.should("run debug arguments with '%s'" % BUILDER_NAME)
            @skipUnless(PROJECT_FILE is not None, "This requires a project file")
            @params(
                ("--debug-print-sources", ),
                ("--debug-print-compile-order", ),

                ("-vvv", "-s",
                 p.join(TEST_SUPPORT_PATH, "vim-hdl-examples/another_library/foo.vhd")),

                ("--debug-parse-source-file", "-s",
                 p.join(TEST_SUPPORT_PATH, "vim-hdl-examples/another_library/foo.vhd")),

                ("--debug-parse-source-file", "-s",
                 p.join(TEST_SUPPORT_PATH, "vim-hdl-examples/basic_library/clk_en_generator.vhd")),

                ("--debug-run-static-check", "-s",
                 p.join(TEST_SUPPORT_PATH, "vim-hdl-examples/basic_library/clock_divider.vhd")),
                )

            def test(case, *args):
                _logger.info("Running '%s'", case)
                cmd = ["coverage", "run",
                       HDLCC_LOCATION, PROJECT_FILE]
                for arg in args:
                    cmd.append(arg)

                shell(cmd)


            @it.should("save profiling info if requested")
            @skipUnless(PROJECT_FILE is not None, "This requires a project file")
            def test():
                cmd = ["coverage", "run",
                       HDLCC_LOCATION, PROJECT_FILE,
                       "--debug-profiling", "output.stats"]

                if p.exists("output.stats"):
                    os.remove("output.stats")

                shell(cmd)

                it.assertTrue(p.exists("output.stats"))
                os.remove("output.stats")

            @it.should("control debugging level")
            @skipUnless(PROJECT_FILE is not None, "This requires a project file")
            def test():
                cmd = ["coverage", "run",
                       HDLCC_LOCATION, PROJECT_FILE,
                       "--clean", ]

                it.assertEqual(shell(cmd), [""])

                previous = None
                for level in range(1, 5):
                    stdout = shell(cmd + ["-" + "v"*level])
                    it.assertTrue(len(stdout) >= previous)
                    previous = len(stdout)

it.createTests(globals())

