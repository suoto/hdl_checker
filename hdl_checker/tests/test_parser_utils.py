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
# pylint: disable=invalid-name
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=useless-object-inheritance

import json
import logging
import os
import os.path as p
import subprocess as subp
import time
from pprint import pformat
from tempfile import NamedTemporaryFile, mkdtemp
from typing import Any

from mock import patch

from hdl_checker.tests import TestCase

from hdl_checker import DEFAULT_PROJECT_FILE
from hdl_checker.parser_utils import (
    SourceEntry,
    filterGitIgnoredPaths,
    flattenConfig,
    getIncludedConfigs,
    isGitRepo,
)
from hdl_checker.path import Path
from hdl_checker.types import BuildFlagScope, FileType
from hdl_checker.utils import removeIfExists

_logger = logging.getLogger(__name__)


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
                if scope is BuildFlagScope.source_specific:
                    continue
                d[lang.value]["flags"][scope.value] = tuple(self.flags[lang][scope])
        return d


class TestConfigHandlers(TestCase):
    maxDiff = None

    def setUp(self):
        self.base_path = mkdtemp()

        def _path(*args):
            # type: (str) -> str
            "Helper to reduce foorprint of p.join(self.base_path, *args)"
            return p.join(self.base_path, *args)

        def _Path(*args):
            # type: (str) -> Path
            "Helper to reduce foorprint of Path(p.join(self.base_path, *args))"
            return Path(_path(*args))

        self._path = _path
        self._Path = _Path

    def test_DirectInclusion(self):
        incl_0 = self._path("incl_0.json")
        incl_1 = self._path("incl_1.json")
        incl_2 = self._path("incl_2.json")
        incl_3 = self._path("incl_3.json")
        #  incl_4 = self._path('incl_4.json')

        search_paths = (incl_0, "incl_1.json")

        # Direct inclusion
        json_dump({"include": (incl_1,), "name": "incl_0"}, open(incl_0, "w"))
        # Direct multiple inclusion
        json_dump({"include": (incl_2, incl_3), "name": "incl_1"}, open(incl_1, "w"))
        # No inclusion (enpoints)
        json_dump({"name": "incl_2"}, open(incl_2, "w"))
        json_dump({"name": "incl_3"}, open(incl_3, "w"))

        result = list(getIncludedConfigs(search_paths, self.base_path))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(
            result,
            (
                (self.base_path, {"name": "incl_0"}),
                (self.base_path, {"name": "incl_1"}),
                (self.base_path, {"name": "incl_2"}),
                (self.base_path, {"name": "incl_3"}),
            ),
        )

    def test_RecursiveInclusion(self):
        incl_0 = self._path("incl_0.json")
        incl_1 = self._path("incl_1.json")

        search_paths = (incl_0,)

        json_dump({"include": (incl_1,), "name": "incl_0"}, open(incl_0, "w"))
        json_dump({"include": (incl_0,), "name": "incl_1"}, open(incl_1, "w"))

        result = list(getIncludedConfigs(search_paths, self.base_path))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(
            result,
            (
                (self.base_path, {"name": "incl_0"}),
                (self.base_path, {"name": "incl_1"}),
            ),
        )

    def test_IgnoresNonExistingFiles(self):
        incl_0 = self._path("incl_0.json")
        incl_1 = self._path("incl_1.json")

        search_paths = (incl_0, incl_1)

        removeIfExists(incl_0)
        json_dump({"name": "incl_1"}, open(incl_1, "w"))

        result = list(getIncludedConfigs(search_paths, self.base_path))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(result, ((self.base_path, {"name": "incl_1"}),))

    def test_IgnoresJsonDecodingErrors(self):
        search_paths = (self._path("incl_0.json"),)

        open(self._path("incl_0.json"), "w").write("hello")

        result = list(getIncludedConfigs(search_paths, self.base_path))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(result, ())

    def test_IncludesRelativePaths(self):
        incl_0 = self._path("incl_0.json")
        incl_1 = self._path("incl_1.json")
        incl_2 = self._path("incl_2.json")

        search_paths = (incl_0, "incl_1.json")

        # Direct inclusion
        json_dump({"include": ("incl_1.json",), "name": "incl_0"}, open(incl_0, "w"))
        # Direct multiple inclusion
        json_dump({"include": ("incl_2.json",), "name": "incl_1"}, open(incl_1, "w"))
        # No inclusion (enpoints)
        json_dump({"name": "incl_2"}, open(incl_2, "w"))

        result = list(getIncludedConfigs(search_paths, self.base_path))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(
            result,
            (
                (self.base_path, {"name": "incl_0"}),
                (self.base_path, {"name": "incl_1"}),
                (self.base_path, {"name": "incl_2"}),
            ),
        )

    def test_IncludeFolderShouldUseConfigFileIfPossible(self):
        # type: (...) -> None
        folder = mkdtemp()
        config_file = p.join(folder, DEFAULT_PROJECT_FILE)
        open(config_file, "w").close()
        _logger.info("folder=%s, config_file=%s", folder, config_file)

        with patch("hdl_checker.parser_utils.json.load") as load:
            load.return_value = {"foo": "bar"}
            result = list(getIncludedConfigs((folder,), self.base_path))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(result, [(folder, {"foo": "bar"})])

    def test_IncludeFolderShouldSearch(self):
        # type: (...) -> None
        folder = mkdtemp()

        with patch("hdl_checker.parser_utils.findRtlSourcesByPath") as meth:
            meth.return_value = ["sources.vhd"]
            result = list(getIncludedConfigs((folder,), self.base_path))
            meth.assert_called_once_with(Path(folder))

        _logger.info("Result:\n%s", pformat(result))
        self.assertCountEqual(result, [(folder, {"sources": ("sources.vhd",)})])

    # glob needs an existing path or else it won't return anything. Paths on
    # this test don't exist, so need to mock that
    @patch("hdl_checker.parser_utils.glob", lambda x, recursive=True: [x])
    def test_FlattenConfigAndPreserveScopes(self):
        incl_0 = self._path("incl_0.json")
        incl_1 = self._path("incl_1.json")
        #  incl_2 = self._path("incl_2.json")

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
            self._path("src_1_0.vhd"),
            "src_1_1.v",
            "src_1_2.sv",
            ("src_1_3.vhd", {"library": "l_1_3"}),
            (self._path("src_1_4.vhd"), {"flags": ("f_1_4",)}),
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

        result = list(flattenConfig(incl_0_cfg.toDict(), self.base_path))

        _logger.info("Result:\n%s", pformat(result))

        self.assertCountEqual(
            result,
            (
                (
                    self._Path("src_0_0.vhd"),
                    None,
                    (),
                    ("vhdl/0/glob", "vhdl/0/single"),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    self._Path("src_0_1.v"),
                    None,
                    (),
                    ("verilog/0/glob", "verilog/0/single"),
                    ("verilog/0/glob", "verilog/0/deps"),
                ),
                (
                    self._Path("src_0_2.sv"),
                    None,
                    (),
                    ("systemverilog/0/glob", "systemverilog/0/single"),
                    ("systemverilog/0/glob", "systemverilog/0/deps"),
                ),
                (
                    self._Path("src_0_3.vhd"),
                    "l_0_3",
                    (),
                    ("vhdl/0/glob", "vhdl/0/single"),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    self._Path("src_0_4.vhd"),
                    None,
                    ("f_0_4",),
                    ("vhdl/0/glob", "vhdl/0/single",),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    self._Path("src_0_5.vhd"),
                    "l_0_5",
                    ("f_0_5",),
                    ("vhdl/0/glob", "vhdl/0/single",),
                    ("vhdl/0/glob", "vhdl/0/deps"),
                ),
                (
                    self._Path("src_1_0.vhd"),
                    None,
                    (),
                    ("vhdl/1/glob", "vhdl/1/single"),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
                (
                    self._Path("src_1_1.v"),
                    None,
                    (),
                    ("verilog/1/glob", "verilog/1/single"),
                    ("verilog/1/glob", "verilog/1/deps"),
                ),
                (
                    self._Path("src_1_2.sv"),
                    None,
                    (),
                    ("systemverilog/1/glob", "systemverilog/1/single"),
                    ("systemverilog/1/glob", "systemverilog/1/deps"),
                ),
                (
                    self._Path("src_1_3.vhd"),
                    "l_1_3",
                    (),
                    ("vhdl/1/glob", "vhdl/1/single"),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
                (
                    self._Path("src_1_4.vhd"),
                    None,
                    ("f_1_4",),
                    ("vhdl/1/glob", "vhdl/1/single",),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
                (
                    self._Path("src_1_5.vhd"),
                    "l_1_5",
                    ("f_1_5",),
                    ("vhdl/1/glob", "vhdl/1/single",),
                    ("vhdl/1/glob", "vhdl/1/deps"),
                ),
            ),
        )


class TestExpandingPathNames(TestCase):
    maxDiff = None

    def join(self, *args):
        return p.join(self.base_path, *args)

    def setUp(self):
        self.base_path = mkdtemp(prefix=__name__ + "_")

        # Create some files
        for path in (
            self.join("README.md"),
            self.join("some_vhd.vhd"),
            self.join("some_v.v"),
            self.join("some_sv.sv"),
            self.join("dir_0", "some_vhd.vhd"),
            self.join("dir_0", "some_v.v"),
            self.join("dir_0", "some_sv.sv"),
            self.join("dir_0", "dir_1", "some_vhd.vhd"),
            self.join("dir_0", "dir_1", "some_v.v"),
            self.join("dir_0", "dir_1", "some_sv.sv"),
            self.join("dir_2", "some_vhd.vhd"),
            self.join("dir_2", "some_v.v"),
            self.join("dir_2", "some_sv.sv"),
            self.join("dir_2", "dir_3", "some_vhd.vhd"),
            self.join("dir_2", "dir_3", "some_v.v"),
            self.join("dir_2", "dir_3", "some_sv.sv"),
        ):
            self.assertFalse(p.exists(path))
            try:
                os.makedirs(p.dirname(path))
            except OSError:
                pass
            open(path, "w").close()
            self.assertTrue(p.exists(path))

    def test_ExpandWithFileWildcards(self):
        # type: (...) -> Any
        config = {
            "sources": [
                self.join("*.vhd"),
                self.join("*", "some_v.v"),
                self.join("*", "dir_1", "*.sv"),
            ]
        }

        _logger.info("config:\n%s", pformat(config))

        self.assertCountEqual(
            flattenConfig(config, root_path=self.base_path),
            (
                SourceEntry(Path(x), None, (), (), ())
                for x in (
                    self.join("some_vhd.vhd"),
                    self.join("dir_0", "some_v.v"),
                    self.join("dir_2", "some_v.v"),
                    self.join("dir_0", "dir_1", "some_sv.sv"),
                )
            ),
        )

    def test_ExpandWithRecursiveWildcards(self):
        # type: (...) -> Any
        """
        Recursive wildcards are only available on Python3, expected result will
        be different but we're not porting it back
        """
        config = {"sources": [self.join("**", "*.vhd")]}

        _logger.info("config:\n%s", pformat(config))

        expected = (
            SourceEntry(Path(x), None, (), (), ())
            for x in (
                self.join("some_vhd.vhd"),
                self.join("dir_0", "some_vhd.vhd"),
                self.join("dir_0", "dir_1", "some_vhd.vhd"),
                self.join("dir_2", "some_vhd.vhd"),
                self.join("dir_2", "dir_3", "some_vhd.vhd"),
            )
        )

        self.assertCountEqual(flattenConfig(config, root_path=self.base_path), expected)

    def test_ExpandWithRecursiveWildcardsAndRelativePaths(self):
        # type: (...) -> Any
        """
        Recursive wildcards are only available on Python3, expected result will
        be different but we're not porting it back
        """
        config = {"sources": [p.join("**", "*.sv")]}

        _logger.info("config:\n%s", pformat(config))

        expected = (
            SourceEntry(Path(x), None, (), (), ())
            for x in (
                self.join("some_sv.sv"),
                self.join("dir_0", "some_sv.sv"),
                self.join("dir_0", "dir_1", "some_sv.sv"),
                self.join("dir_2", "some_sv.sv"),
                self.join("dir_2", "dir_3", "some_sv.sv"),
            )
        )

        self.assertCountEqual(flattenConfig(config, root_path=self.base_path), expected)

    def test_ExpandWhenPatternMatchesNonRtlFiles(self):
        # type: (...) -> Any
        """
        Recursive wildcards are only available on Python3, expected result will
        be different but we're not porting it back
        """
        config = {"sources": [p.join("**", "*")]}

        _logger.info("config:\n%s", pformat(config))

        expected = (
            SourceEntry(Path(x), None, (), (), ())
            for x in (
                self.join("some_vhd.vhd"),
                self.join("some_v.v"),
                self.join("some_sv.sv"),
                self.join("dir_0", "some_vhd.vhd"),
                self.join("dir_0", "some_v.v"),
                self.join("dir_0", "some_sv.sv"),
                self.join("dir_0", "dir_1", "some_vhd.vhd"),
                self.join("dir_0", "dir_1", "some_v.v"),
                self.join("dir_0", "dir_1", "some_sv.sv"),
                self.join("dir_2", "some_vhd.vhd"),
                self.join("dir_2", "some_v.v"),
                self.join("dir_2", "some_sv.sv"),
                self.join("dir_2", "dir_3", "some_vhd.vhd"),
                self.join("dir_2", "dir_3", "some_v.v"),
                self.join("dir_2", "dir_3", "some_sv.sv"),
            )
        )

        self.assertCountEqual(flattenConfig(config, root_path=self.base_path), expected)


def timeit(f):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        end = time.time()
        _logger.info("Running %s(%s, %s) took %.2fs", f, args, kwargs, end - start)
        return result

    return wrapper


class TestFilterGitIgnoredPaths(TestCase):
    def join(self, *args):
        return p.join(self.base_path, *args)

    @timeit
    def setUp(self):
        # type: (...) -> Any
        self.base_path = mkdtemp(prefix=__name__ + "_")

        self.out_of_repo = NamedTemporaryFile(
            prefix=__name__ + "_out_of_repo", suffix=".txt"
        ).name

        self.paths = (
            self.join("regular_file"),
            self.join("untracked_file"),
            self.join("ignored_file"),
            self.out_of_repo,
        )

        # Create some files
        for path in self.paths:
            self.assertFalse(p.exists(path))
            try:
                os.makedirs(p.dirname(path))
            except OSError:
                pass
            open(path, "w").close()
            self.assertTrue(p.exists(path))

        open(self.join(".gitignore"), "w").write("ignored_file")

        for cmd in (
            ["git", "init"],
            ["git", "add", "regular_file", ".gitignore"],
            ["git", "config", "--local", "user.name", "foo"],
            ["git", "config", "--local", "user.email", "bar"],
            ["git", "commit", "-m", "'initial'"],
        ):
            _logger.debug("$ %s", cmd)
            subp.check_call(cmd, cwd=self.base_path, stdout=subp.PIPE)

        _logger.debug(
            "Status:\n%s",
            subp.check_output(("git", "status"), cwd=self.base_path).decode(),
        )

    @timeit
    def test_FilterGitPaths(self):
        # type: (...) -> Any
        self.assertTrue(isGitRepo(Path(self.base_path)))

        result = list(
            filterGitIgnoredPaths(Path(self.base_path), (Path(x) for x in self.paths))
        )

        _logger.info("Result: %s", result)

        self.assertCountEqual(
            result,
            (
                Path(x)
                for x in (
                    self.join("regular_file"),
                    self.join("untracked_file"),
                    self.out_of_repo,
                )
            ),
        )
