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
from contextlib import contextmanager
from typing import Any, Iterator, List

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
                    "builder_name": BuilderName.msim,
                    "global_build_flags": {
                        "systemverilog": (),
                        "verilog": (),
                        "vhdl": ("-global", "-global-build-flag"),
                    },
                    "single_build_flags": {
                        "systemverilog": (),
                        "verilog": (),
                        "vhdl": ("-single_build_flag_0", "-singlebuildflag"),
                    },
                },
            )

            def _resolve(path):
                return Path(p.join(it.path.dirname, path))

            it.assertCountEqual(
                sources,
                [
                    (_resolve("sample_file.vhd"), "work", ("-sample_file_flag",)),
                    (_resolve("sample_package.vhdl"), "work", ("-sample_package_flag",)),
                    (_resolve("TESTBENCH.VHD"), "work", ("-build-in", "some", "way")),
                    (Path("/some/abs/path.VHDL"), "lib", ()),
                    (_resolve("foo.v"), "work", ("-some-flag", "some", "value")),
                    (_resolve("bar.sv"), "work", ("some", "sv", "flag")),
                ],
            )


it.createTests(globals())
