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
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=invalid-name

import json
import logging
import os
import os.path as p
import shutil

import unittest2
from webtest import TestApp

import hdlcc.handlers as handlers
from hdlcc.builders.fallback import Fallback
from hdlcc.builders.ghdl import GHDL
from hdlcc.builders.msim import MSim
from hdlcc.builders.xvhdl import XVHDL
from hdlcc.tests.utils import getTestTempPath, setupTestSuport

try:  # Python 3.x
    import unittest.mock as mock
except ImportError:  # Python 2.x
    import mock  # type: ignore


TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.abspath(p.join(TEST_TEMP_PATH, "test_project"))

SERVER_LOG_LEVEL = os.environ.get("SERVER_LOG_LEVEL", "INFO")

_logger = logging.getLogger(__name__)
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), "..", ".."))

BUILDER_CLASS_MAP = {"msim": MSim, "xvhdl": XVHDL, "ghdl": GHDL, "fallback": Fallback}


class TestConfigGenerator(unittest2.TestCase):
    maxDiff = None
    @classmethod
    def setUpClass(cls):
        setupTestSuport(TEST_TEMP_PATH)

    def setUp(self):
        self.app = TestApp(handlers.app)

        # Needs to agree with vroom test file
        self.dummy_test_path = p.join(TEST_TEMP_PATH, "dummy_test_path")

        self.assertFalse(
            p.exists(self.dummy_test_path),
            "Path '%s' shouldn't exist right now" % p.abspath(self.dummy_test_path),
        )

        os.makedirs(self.dummy_test_path)

        os.mkdir(p.join(self.dummy_test_path, "path_a"))
        os.mkdir(p.join(self.dummy_test_path, "path_b"))
        os.mkdir(p.join(self.dummy_test_path, "v_includes"))
        os.mkdir(p.join(self.dummy_test_path, "sv_includes"))
        # Create empty sources and some extra files as well
        for path in (
            "README.txt",  # This shouldn't be included
            "nonreadable.txt",  # This shouldn't be included
            p.join("path_a", "some_source.vhd"),
            p.join("path_a", "header_out_of_place.vh"),
            p.join("path_a", "source_tb.vhd"),
            p.join("path_b", "some_source.vhd"),
            p.join("path_b", "a_verilog_source.v"),
            p.join("path_b", "a_systemverilog_source.sv"),
            # Create headers for both extensions
            p.join("v_includes", "verilog_header.vh"),
            p.join("sv_includes", "systemverilog_header.svh"),
            # Make the tree 'dirty' with other source types
            p.join("path_a", "not_hdl_source.log"),
            p.join("path_a", "not_hdl_source.py"),
        ):
            _logger.info("Writing to %s", path)
            open(p.join(self.dummy_test_path, path), "w").write("")

    def teardown(self):
        # Create a dummy arrangement of sources
        if p.exists(self.dummy_test_path):
            _logger.info("Removing %s", repr(self.dummy_test_path))
            shutil.rmtree(self.dummy_test_path)

    @mock.patch(
        "hdlcc.config_generators.simple_finder.isFileReadable",
        lambda path: "nonreadable" not in path.name,
    )
    def test_run_simple_config_gen(self):
        data = {
            "generator": "SimpleFinder",
            "kwargs": json.dumps({"paths": [self.dummy_test_path]}),
        }

        reply = self.app.post("/run_config_generator", data)

        content = reply.json["content"].split("\n")

        intro = [
            "# Files found: 5",
            "include_paths[verilog] = %s %s"
            % (
                p.join(self.dummy_test_path, "path_a"),
                p.join(self.dummy_test_path, "v_includes"),
            ),
            "include_paths[systemverilog] = "
            + p.join(self.dummy_test_path, "sv_includes"),
            "",
        ]

        files = [
            "vhdl work %s" % p.join(self.dummy_test_path, "path_a", "some_source.vhd"),
            "vhdl work %s" % p.join(self.dummy_test_path, "path_a", "source_tb.vhd"),
            "systemverilog work %s"
            % p.join(self.dummy_test_path, "path_b", "a_systemverilog_source.sv"),
            "verilog work %s"
            % p.join(self.dummy_test_path, "path_b", "a_verilog_source.v"),
            "vhdl work %s" % p.join(self.dummy_test_path, "path_b", "some_source.vhd"),
        ]

        _logger.info("Resulting file:")
        for i, line in enumerate(content):
            _logger.info("%2d | %s", i + 1, line)

        self.assertEqual(content[: len(intro)], intro)
        self.assertEqual(content[len(intro) :], files)
