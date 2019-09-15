# This file is part of HDL Code Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
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

# pylint: disable=function-redefined
# pylint: disable=invalid-name
# pylint: disable=missing-docstring

import logging
import os.path as p
import pprint
import tempfile
import time
from contextlib import contextmanager
from multiprocessing import Event
from threading import Thread
from typing import Any, Iterator, List

import mock
import six

from nose2.tools import such  # type: ignore

from hdlcc.builder_utils import BuilderName
from hdlcc.exceptions import UnknownParameterError
from hdlcc.parsers.config_parser import ConfigParser
from hdlcc.path import Path
from hdlcc.tests.utils import assertCountEqual, getTestTempPath, setupTestSuport

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")


@contextmanager
def fileWithContent(content):  # type: (bytes) -> Iterator[str]
    with tempfile.NamedTemporaryFile(delete=False) as fd:
        print("Writing to %s (%s)" % (fd, fd.name))
        fd.write(content)
        fd.flush()
        yield fd.name


such.unittest.TestCase.maxDiff = None

with such.A("config parser object") as it:

    if six.PY2:
        # Can't use assertCountEqual for lists of unhashable types.
        # Workaround for https://bugs.python.org/issue10242
        it.assertCountEqual = assertCountEqual(it)

    @it.has_setup
    def setup():
        # type: (...) -> Any
        setupTestSuport(TEST_TEMP_PATH)

    #  @it.has_teardown
    #  def teardown():
    #      for temp_path in ('.build', '.hdlcc'):
    #          temp_path = p.abspath(p.join(CONFIG_PARSER_SUPPORT_PATH,
    #                                       temp_path))
    #          if p.exists(temp_path):
    #              shutil.rmtree(temp_path)

    @it.should(
        "raise UnknownParameterError exception when an unknown " "parameter is found"
    )
    def test_raises_exception():
        # type: (...) -> Any
        with it.assertRaises(UnknownParameterError):
            with fileWithContent(b"foo = bar") as name:
                parser = ConfigParser(Path(name))
                parser.parse()

    with it.having("a regular file"):

        @it.has_setup
        def setup():
            # type: (...) -> Any
            it.path = Path(tempfile.mktemp())

            contents = b"""
single_build_flags[vhdl] = -single_build_flag_0 -singlebuildflag
global_build_flags[vhdl] = -global -global-build-flag

builder = msim
target_dir = .build

vhdl work sample_file.vhd -sample_file_flag
vhdl work sample_package.vhdl -sample_package_flag
vhdl work TESTBENCH.VHD -build-in some way

vhdl lib /some/abs/path.VHDL

verilog work foo.v -some-flag some value

systemverilog work bar.sv some sv flag
"""

            with open(it.path.name, "wb") as fd:
                fd.write(contents)
                fd.flush()

        @it.should("find the correct info")
        def test_parsing_regular_file():
            # type: (...) -> Any
            parser = ConfigParser(it.path)
            config = parser.parse()

            _logger.info("Parsed config:\n%s", pprint.pformat(config))
            sources = config.pop("sources")

            it.assertDictEqual(
                config,
                {
                    "builder_name": BuilderName.msim.name,
                    "vhdl": {"flags": ("-global", "-global-build-flag")},
                    "verilog": {"flags": ()},
                    "systemverilog": {"flags": ()},
                },
            )

            def _resolve(path):
                return p.join(it.path.dirname, path)

            it.assertCountEqual(
                sources,
                [
                    (
                        _resolve("sample_file.vhd"),
                        {"library": "work", "flags": ("-sample_file_flag",)},
                    ),
                    (
                        _resolve("sample_package.vhdl"),
                        {"library": "work", "flags": ("-sample_package_flag",)},
                    ),
                    (
                        _resolve("TESTBENCH.VHD"),
                        {"library": "work", "flags": ("-build-in", "some", "way")},
                    ),
                    ("/some/abs/path.VHDL", {"library": "lib", "flags": ()}),
                    (
                        _resolve("foo.v"),
                        {"library": "work", "flags": ("-some-flag", "some", "value")},
                    ),
                    (
                        _resolve("bar.sv"),
                        {"library": "work", "flags": ("some", "sv", "flag")},
                    ),
                ],
            )

        @it.should("only parse when the file actually changes")
        def test_only_parse_when_source_changes():
            # type: (...) -> Any
            parser = ConfigParser(it.path)

            _logger.info("Parsing %s for the 1st time", it.path)
            with mock.patch.object(parser, "_parseLine") as _parseLine:
                parser.parse()
                _parseLine.assert_called()

            time.sleep(0.1)

            _logger.info("Parsing %s for the 2nd time", it.path)
            with mock.patch.object(parser, "_parseLine") as _parseLine:
                parser.parse()
                _parseLine.assert_not_called()

        @it.should("report parsing in progress")
        def test_should_report_parsing_in_progress():
            # type: (...) -> Any
            parser = ConfigParser(it.path)
            it.assertFalse(parser.isParsing(), "Parser should not be busy right now")

            event = Event()

            # Make parsing wait until we set the event to mitigate race
            # conditions
            def _parse(*args, **kwargs):
                it.assertTrue(event.wait(timeout=3), "Timeout waiting for event")

            with mock.patch.object(parser, "_parse", _parse):
                thread = Thread(target=parser.parse)
                thread.start()
                time.sleep(0.1)
                it.assertTrue(
                    parser.isParsing(), "Parser should indicate it's still parsing"
                )
                event.set()


it.createTests(globals())
