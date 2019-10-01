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
# pylint: disable=protected-access
# pylint: disable=useless-object-inheritance

import json
import logging
import os.path as p
from pprint import pformat

from hdlcc.tests import TestCase, getTestTempPath

from hdlcc.parser_utils import flattenConfig, getIncludedConfigs
from hdlcc.path import Path
from hdlcc.types import BuildFlagScope, FileType
from hdlcc.utils import removeIfExists

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.join(TEST_TEMP_PATH, "test_project")

TEST_CONFIG_PARSER_SUPPORT_PATH = p.join(TEST_TEMP_PATH, "test_config_parser")


def _path(*args):
    # type: (str) -> str
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return p.join(TEST_TEMP_PATH, *args)


def _Path(*args):
    # type: (str) -> Path
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return Path(_path(*args))


def json_dump(obj, stream):
    _logger.info("JSON dump: %s:\n%s", stream, pformat(obj))
    json.dump(obj, stream)


class _ConfigDict(object):
    def __init__(self):
        self.sources = []
        self.flags = {}
        self.include = []
        for lang in FileType:
            self.flags[lang] = {}
            for scope in BuildFlagScope:
                self.flags[lang][scope] = []

    def toDict(self):
        d = {"sources": tuple(self.sources), "include": tuple(self.include)}

        for lang in FileType:
            d[lang.value] = {"flags": {}}
            for scope in BuildFlagScope:
                d[lang.value]["flags"][scope.value] = tuple(self.flags[lang][scope])
        return d


class TestConfigHandlers(TestCase):
    maxDiff = None

    def test_direct_inclusion(self):
        incl_0 = _path("incl_0.json")
        incl_1 = _path("incl_1.json")
        incl_2 = _path("incl_2.json")
        incl_3 = _path("incl_3.json")
        #  incl_4 = _path('incl_4.json')

        search_paths = (incl_0, "incl_1.json")

        # Direct inclusion
        json_dump({"include": (incl_1,), "name": "incl_0"}, open(incl_0, "w"))
        # Direct multiple inclusion
        json_dump({"include": (incl_2, incl_3), "name": "incl_1"}, open(incl_1, "w"))
        # No inclusion (enpoints)
        json_dump({"name": "incl_2"}, open(incl_2, "w"))
        json_dump({"name": "incl_3"}, open(incl_3, "w"))

        result = list(getIncludedConfigs(search_paths, TEST_TEMP_PATH))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(
            result,
            (
                (TEST_TEMP_PATH, {"name": "incl_0"}),
                (TEST_TEMP_PATH, {"name": "incl_1"}),
                (TEST_TEMP_PATH, {"name": "incl_2"}),
                (TEST_TEMP_PATH, {"name": "incl_3"}),
            ),
        )

    def test_recursive_inclusion(self):
        incl_0 = _path("incl_0.json")
        incl_1 = _path("incl_1.json")

        search_paths = (incl_0,)

        json_dump({"include": (incl_1,), "name": "incl_0"}, open(incl_0, "w"))
        json_dump({"include": (incl_0,), "name": "incl_1"}, open(incl_1, "w"))

        result = list(getIncludedConfigs(search_paths, TEST_TEMP_PATH))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(
            result,
            (
                (TEST_TEMP_PATH, {"name": "incl_0"}),
                (TEST_TEMP_PATH, {"name": "incl_1"}),
            ),
        )

    def test_ignores_non_existing_files(self):
        incl_0 = _path("incl_0.json")
        incl_1 = _path("incl_1.json")

        search_paths = (incl_0, incl_1)

        removeIfExists(incl_0)
        json_dump({"name": "incl_1"}, open(incl_1, "w"))

        result = list(getIncludedConfigs(search_paths, TEST_TEMP_PATH))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(result, ((TEST_TEMP_PATH, {"name": "incl_1"}),))

    def test_ignores_json_decoding_errors(self):
        search_paths = (_path("incl_0.json"),)

        open(_path("incl_0.json"), "w").write("hello")

        result = list(getIncludedConfigs(search_paths, TEST_TEMP_PATH))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(result, ())

    def test_includes_relative_paths(self):
        incl_0 = _path("incl_0.json")
        incl_1 = _path("incl_1.json")
        incl_2 = _path("incl_2.json")

        search_paths = (incl_0, "incl_1.json")

        # Direct inclusion
        json_dump({"include": ("incl_1.json",), "name": "incl_0"}, open(incl_0, "w"))
        # Direct multiple inclusion
        json_dump({"include": ("incl_2.json",), "name": "incl_1"}, open(incl_1, "w"))
        # No inclusion (enpoints)
        json_dump({"name": "incl_2"}, open(incl_2, "w"))

        result = list(getIncludedConfigs(search_paths, TEST_TEMP_PATH))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(
            result,
            (
                (TEST_TEMP_PATH, {"name": "incl_0"}),
                (TEST_TEMP_PATH, {"name": "incl_1"}),
                (TEST_TEMP_PATH, {"name": "incl_2"}),
            ),
        )

    def test_flatten_config_and_preserve_scopes(self):
        incl_0 = _path("incl_0.json")
        incl_1 = _path("incl_1.json")
        #  incl_2 = _path("incl_2.json")

        incl_0_cfg = _ConfigDict()

        incl_0_cfg.include += [incl_1]

        incl_0_cfg.sources += [
            "src_0_0.vhd",
            "src_0_1.v",
            "src_0_2.sv",
            #  ("src_0_3.vhd", {"library": "some_library"}),
            #  ("src_0_4.vhd", {"flags": ("some_flag",)}),
            #  ("src_0_5.vhd", {"library": "lib", "flags": ("and_flag",)}),
            ("src_0_3.vhd", {"library": "l_0_3"}),
            ("src_0_4.vhd", {"flags": ("f_0_4",)}),
            ("src_0_5.vhd", {"library": "l_0_5", "flags": ("f_0_5",)}),
        ]

        incl_0_cfg.flags = {
            FileType.vhdl: {
                BuildFlagScope.all: ["vhdl/0/glob"],
                BuildFlagScope.dependencies: ["vhdl/0/deps"],
                BuildFlagScope.single: ["vhdl/0/single"],
            },
            FileType.verilog: {
                BuildFlagScope.all: ["verilog/0/glob"],
                BuildFlagScope.dependencies: ["verilog/0/deps"],
                BuildFlagScope.single: ["verilog/0/single"],
            },
            FileType.systemverilog: {
                BuildFlagScope.all: ["systemverilog/0/glob"],
                BuildFlagScope.dependencies: ["systemverilog/0/deps"],
                BuildFlagScope.single: ["systemverilog/0/single"],
            },
        }

        incl_1_cfg = _ConfigDict()

        incl_1_cfg.sources += [
            _path("src_1_0.vhd"),
            "src_1_1.v",
            "src_1_2.sv",
            ("src_1_3.vhd", {"library": "l_1_3"}),
            (_path("src_1_4.vhd"), {"flags": ("f_1_4",)}),
            ("src_1_5.vhd", {"library": "l_1_5", "flags": ("f_1_5",)}),
        ]

        incl_1_cfg.flags = {
            FileType.vhdl: {
                BuildFlagScope.all: ["vhdl/1/glob"],
                BuildFlagScope.dependencies: ["vhdl/1/deps"],
                BuildFlagScope.single: ["vhdl/1/single"],
            },
            FileType.verilog: {
                BuildFlagScope.all: ["verilog/1/glob"],
                BuildFlagScope.dependencies: ["verilog/1/deps"],
                BuildFlagScope.single: ["verilog/1/single"],
            },
            FileType.systemverilog: {
                BuildFlagScope.all: ["systemverilog/1/glob"],
                BuildFlagScope.dependencies: ["systemverilog/1/deps"],
                BuildFlagScope.single: ["systemverilog/1/single"],
            },
        }

        json_dump(incl_0_cfg.toDict(), open(incl_0, "w"))
        json_dump(incl_1_cfg.toDict(), open(incl_1, "w"))

        result = list(flattenConfig(incl_0_cfg.toDict(), TEST_TEMP_PATH))

        _logger.info("Result:\n%s", pformat(result))

        self.assertCountEqual(
            result,
            (
                (
                    _Path("src_0_0.vhd"),
                    None,
                    ("vhdl/0/glob", "vhdl/0/single"),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    _Path("src_0_1.v"),
                    None,
                    ("verilog/0/glob", "verilog/0/single"),
                    ("verilog/0/glob", "verilog/0/deps"),
                ),
                (
                    _Path("src_0_2.sv"),
                    None,
                    ("systemverilog/0/glob", "systemverilog/0/single"),
                    ("systemverilog/0/glob", "systemverilog/0/deps"),
                ),
                (
                    _Path("src_0_3.vhd"),
                    "l_0_3",
                    ("vhdl/0/glob", "vhdl/0/single"),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    _Path("src_0_4.vhd"),
                    None,
                    ("vhdl/0/glob", "vhdl/0/single", "f_0_4"),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    _Path("src_0_5.vhd"),
                    "l_0_5",
                    ("vhdl/0/glob", "vhdl/0/single", "f_0_5"),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    _Path("src_1_0.vhd"),
                    None,
                    ("vhdl/1/glob", "vhdl/1/single"),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
                (
                    _Path("src_1_1.v"),
                    None,
                    ("verilog/1/glob", "verilog/1/single"),
                    ("verilog/1/glob", "verilog/1/deps"),
                ),
                (
                    _Path("src_1_2.sv"),
                    None,
                    ("systemverilog/1/glob", "systemverilog/1/single"),
                    ("systemverilog/1/glob", "systemverilog/1/deps"),
                ),
                (
                    _Path("src_1_3.vhd"),
                    "l_1_3",
                    ("vhdl/1/glob", "vhdl/1/single"),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
                (
                    _Path("src_1_4.vhd"),
                    None,
                    ("vhdl/1/glob", "vhdl/1/single", "f_1_4"),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
                (
                    _Path("src_1_5.vhd"),
                    "l_1_5",
                    ("vhdl/1/glob", "vhdl/1/single", "f_1_5"),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
            ),
        )
