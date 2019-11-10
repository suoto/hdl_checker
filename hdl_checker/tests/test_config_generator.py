# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.

# pylint: disable=function-redefined
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=invalid-name

import logging
import os
import os.path as p
from tempfile import mkdtemp

from mock import patch
from webtest import TestApp  # type: ignore # pylint:disable=import-error

from hdl_checker.tests import TestCase

import hdl_checker.handlers as handlers
from hdl_checker.config_generators.simple_finder import SimpleFinder
from hdl_checker.utils import removeDirIfExists

_logger = logging.getLogger(__name__)


class TestConfigGenerator(TestCase):
    maxDiff = None

    def setUp(self):
        self.app = TestApp(handlers.app)

        self.dummy_test_path = mkdtemp(prefix=__name__ + "_")

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
        removeDirIfExists(self.dummy_test_path)

    @patch(
        "hdl_checker.parser_utils.isFileReadable",
        lambda path: "nonreadable" not in path,
    )
    def test_run_simple_config_gen(self):
        # type: (...) -> None
        finder = SimpleFinder([self.dummy_test_path])

        config = finder.generate()

        self.assertCountEqual(
            config.pop("sources"),
            {
                p.join(self.dummy_test_path, "path_a", "some_source.vhd"),
                p.join(self.dummy_test_path, "path_b", "a_systemverilog_source.sv"),
                p.join(self.dummy_test_path, "path_a", "source_tb.vhd"),
                p.join(self.dummy_test_path, "path_b", "some_source.vhd"),
                p.join(self.dummy_test_path, "path_b", "a_verilog_source.v"),
                p.join(self.dummy_test_path, "sv_includes", "systemverilog_header.svh"),
                p.join(self.dummy_test_path, "v_includes", "verilog_header.vh"),
                p.join(self.dummy_test_path, "path_a", "header_out_of_place.vh"),
            },
        )

        # Assert there's no extra elements
        self.assertFalse(config)
