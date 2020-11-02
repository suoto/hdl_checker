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

import logging
import os
import os.path as p
import shutil
from multiprocessing import Queue
from tempfile import mkdtemp
from typing import Any, List, Optional

import parameterized  # type: ignore
import unittest2  # type: ignore
from mock import MagicMock, patch

from hdl_checker.tests import (
    SourceMock,
    TestCase,
    getTestTempPath,
    parametrizeClassWithBuilders,
    setupTestSuport,
)

from hdl_checker.builder_utils import (
    AVAILABLE_BUILDERS,
    GHDL,
    XVHDL,
    AnyBuilder,
    Fallback,
    MSim,
)
from hdl_checker.database import Database
from hdl_checker.diagnostics import BuilderDiag, DiagType
from hdl_checker.exceptions import SanityCheckError
from hdl_checker.parsers.elements.dependency_spec import (
    IncludedPath,
    RequiredDesignUnit,
)
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.parsers.elements.parsed_element import Location
from hdl_checker.path import Path
from hdl_checker.types import (
    BuildFlagScope,
    DesignUnitType,
    FileType,
    RebuildLibraryUnit,
    RebuildPath,
    RebuildUnit,
)

_logger = logging.getLogger(__name__)

TEST_TEMP_PATH = getTestTempPath(__name__)
SOURCES_PATH = p.join(TEST_TEMP_PATH, "test_builders")

BUILDER_CLASS_MAP = {"msim": MSim, "xvhdl": XVHDL, "ghdl": GHDL, "fallback": Fallback}


class _SourceMock(SourceMock):
    base_path = TEST_TEMP_PATH


def _source(*args):
    # type: (str) -> Path
    "Helper to reduce foorprint of Path(p.join(SOURCES_PATH, *args))"
    return Path(p.join(SOURCES_PATH, *args))


def _temp(*args):
    # type: (str) -> Path
    "Helper to reduce foorprint of Path(p.join(TEST_TEMP_PATH, *args))"
    return Path(p.join(TEST_TEMP_PATH, *args))


@parametrizeClassWithBuilders
class TestBuilder(TestCase):
    # Create defaults so that pylint doesn't complain about non existing
    # members
    builder_name = None
    builder_path = None

    @classmethod
    def setUpClass(cls):
        setupTestSuport(TEST_TEMP_PATH)

    def setUp(self):
        # type: (...) -> Any
        # Add builder path to the env
        self.original_env = os.environ.copy()

        # Add the builder path to the environment so we can call it
        if self.builder_path:
            _logger.info("Adding '%s' to the system path", self.builder_path)
            self.assertTrue(
                p.exists(self.builder_path),
                "Path for builder '%s' does not exists" % self.builder_name,
            )
            self.patch = patch.dict(
                "os.environ",
                {"PATH": os.pathsep.join([self.builder_path, os.environ["PATH"]])},
            )
            self.patch.start()

        assert self.builder_name is not None  # To make mypy happy

        builder_class = BUILDER_CLASS_MAP[self.builder_name]
        work_folder = _temp("_%s" % self.builder_name)
        _logger.info("Builder class: %s, work folder is %s", builder_class, work_folder)
        self.builder = builder_class(work_folder, MagicMock())  # type: AnyBuilder
        self.builder_class = builder_class

    def tearDown(self):
        # type: (...) -> Any
        if self.builder_path:
            self.patch.stop()
        if p.exists("._%s" % self.builder_name):
            shutil.rmtree("._%s" % self.builder_name)

    def test_EnvironmentCheck(self):
        # type: (...) -> Any
        self.builder.checkEnvironment()

    def test_BuilderReportsItsAvailable(self):  # pylint: disable=invalid-name
        # type: (...) -> Any
        self.assertTrue(self.builder_class.isAvailable())  # type: ignore

    def test_CreateLibraryMultipleTimes(self):  # pylint: disable=invalid-name
        # type: (...) -> Any
        self.builder._createLibraryIfNeeded(Identifier("random_lib"))
        self.builder._createLibraryIfNeeded(Identifier("random_lib"))

    def test_BuilderDoesNothingWhenCreatingBuiltinLibraries(
        self,
    ):  # pylint: disable=invalid-name
        # type: (...) -> Any
        self.builder._createLibraryIfNeeded(Identifier("ieee"))

    def test_FindsBuiltinLibraries(self):
        # type: (...) -> Any
        expected = []  # type: List[str]

        if not isinstance(self.builder, Fallback):
            expected += ["ieee", "std"]

        if isinstance(self.builder, MSim):
            expected += ["modelsim_lib"]

        for lib in map(Identifier, expected):
            self.assertIn(lib, self.builder.builtin_libraries)

    @parameterized.parameterized.expand(
        [
            ("/some/file/with/abs/path.vhd",),
            ("some/file/with/relative/path.vhd",),
            ("some_file_on_same_level.vhd",),
            (r"C:\some\file\on\windows.vhd",),
        ]
    )
    def test_ParseMsimResult(self, path):
        # type: (...) -> Any
        if not isinstance(self.builder, MSim):
            raise unittest2.SkipTest("ModelSim only test")

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    '** Error: %s(21): near "EOF": (vcom-1576) ' "expecting ';'." % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="near \"EOF\": expecting ';'.",
                    filename=Path(path),
                    line_number=20,
                    error_code="vcom-1576",
                    severity=DiagType.ERROR,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "** Warning: %s(23): (vcom-1320) Type of expression "
                    "\"(OTHERS => '0')\" is ambiguous; using element type "
                    "STD_LOGIC_VECTOR, not aggregate type register_type." % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="Type of expression \"(OTHERS => '0')\" is "
                    "ambiguous; using element type STD_LOGIC_VECTOR, not "
                    "aggregate type register_type.",
                    filename=Path(path),
                    line_number=22,
                    error_code="vcom-1320",
                    severity=DiagType.WARNING,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "** Warning: %s(39): (vcom-1514) Range choice direction "
                    "(downto) does not determine aggregate index range "
                    "direction (to)." % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="Range choice direction (downto) does not determine "
                    "aggregate index range direction (to).",
                    filename=Path(path),
                    line_number=38,
                    error_code="vcom-1514",
                    severity=DiagType.WARNING,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "** Error: (vcom-11) Could not find work.regfile_pkg."
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="Could not find work.regfile_pkg.",
                    error_code="vcom-11",
                    severity=DiagType.ERROR,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "** Error (suppressible): %s(7): (vcom-1195) Cannot find "
                    'expanded name "work.regfile_pkg".' % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text='Cannot find expanded name "work.regfile_pkg".',
                    filename=Path(path),
                    line_number=6,
                    error_code="vcom-1195",
                    severity=DiagType.ERROR,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "** Error: %s(7): Unknown expanded name." % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="Unknown expanded name.",
                    line_number="6",
                    filename=Path(path),
                    severity=DiagType.ERROR,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "** Warning: [14] %s(103): (vcom-1272) Length of expected "
                    "is 4; length of actual is 8." % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="Length of expected is 4; length of actual is 8.",
                    line_number="102",
                    error_code="vcom-1272",
                    filename=Path(path),
                    severity=DiagType.WARNING,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "** Warning: [14] %s(31): (vcom-1246) Range -1 downto 0 "
                    "is null." % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="Range -1 downto 0 is null.",
                    line_number="30",
                    error_code="vcom-1246",
                    filename=Path(path),
                    severity=DiagType.WARNING,
                )
            ],
        )

    @parameterized.parameterized.expand(
        [
            ("/some/file/with/abs/path.vhd",),
            ("some/file/with/relative/path.vhd",),
            ("some_file_on_same_level.vhd",),
            (r"C:\some\file\on\windows.vhd",),
        ]
    )
    def test_ParseGhdlResult(self, path):
        # type: (...) -> Any
        if not isinstance(self.builder, GHDL):
            raise unittest2.SkipTest("GHDL only test")

        records = list(
            self.builder._makeRecords(
                "%s:11:35: extra ';' at end of interface list" % path
            )
        )

        expected = [
            BuilderDiag(
                builder_name=self.builder_name,
                filename=Path(path),
                line_number=10,
                column_number=34,
                severity=DiagType.ERROR,
                text="extra ';' at end of interface list",
            )
        ]

        self.assertCountEqual(records, expected)

    @parameterized.parameterized.expand(
        [
            ("/some/file/with/abs/path.vhd",),
            ("some/file/with/relative/path.vhd",),
            ("some_file_on_same_level.vhd",),
        ]
    )
    def test_ParseXvhdlResult(self, path):
        # type: (...) -> Any
        if not isinstance(self.builder, XVHDL):
            raise unittest2.SkipTest("XVHDL only test")

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "ERROR: [VRFC 10-1412] syntax error near ) [%s:12]" % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="syntax error near )",
                    filename=Path(path),
                    line_number=11,
                    error_code="VRFC 10-1412",
                    severity=DiagType.ERROR,
                )
            ],
        )

        self.assertEqual(
            list(
                self.builder._makeRecords(
                    "WARNING: [VRFC 10-1256] possible infinite loop; process "
                    "does not have a wait statement [%s:119]" % path
                )
            ),
            [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text="possible infinite loop; process does not have a wait statement",
                    filename=Path(path),
                    line_number=118,
                    error_code="VRFC 10-1256",
                    severity=DiagType.WARNING,
                )
            ],
        )

    @patch("hdl_checker.database.Database.getLibrary", return_value=Identifier("work"))
    def test_VhdlCompilation(self, *args):
        # type: (...) -> Any
        if FileType.vhdl not in self.builder.file_types:
            raise unittest2.SkipTest(
                "Builder {} doesn't support VHDL".format(self.builder_name)
            )

        source = _source("no_messages.vhd")
        records, rebuilds = self.builder.build(
            source, Identifier("work"), BuildFlagScope.single
        )
        self.assertNotIn(
            DiagType.ERROR,
            [x.severity for x in records],
            "This source should not generate errors.",
        )
        self.assertFalse(rebuilds)

    @patch("hdl_checker.database.Database.getLibrary", return_value=Identifier("work"))
    def test_VerilogCompilation(self, *args):
        # type: (...) -> Any
        if FileType.verilog not in self.builder.file_types:
            raise unittest2.SkipTest(
                "Builder {} doesn't support Verilog".format(self.builder_name)
            )

        source = _source("no_messages.v")

        records, rebuilds = self.builder.build(
            source, Identifier("work"), BuildFlagScope.single
        )

        self.assertNotIn(
            DiagType.ERROR,
            [x.severity for x in records],
            "This source should not generate errors.",
        )
        self.assertFalse(rebuilds)

    @patch("hdl_checker.database.Database.getLibrary", return_value=Identifier("work"))
    def test_SystemverilogCompilation(self, *args):
        # type: (...) -> Any
        if FileType.systemverilog not in self.builder.file_types:
            raise unittest2.SkipTest(
                "Builder {} doesn't support SystemVerilog".format(self.builder_name)
            )

        source = _source("no_messages.sv")

        records, rebuilds = self.builder.build(
            source, Identifier("work"), BuildFlagScope.single
        )

        self.assertNotIn(
            DiagType.ERROR,
            [x.severity for x in records],
            "This source should not generate errors.",
        )
        self.assertFalse(rebuilds)

    def test_CatchAKnownError(self):
        # type: (...) -> Any
        source = _source("source_with_error.vhd")

        records, rebuilds = self.builder.build(
            source, Identifier("lib"), forced=True, scope=BuildFlagScope.single
        )

        for record in records:
            _logger.info(record)

        if self.builder_name == "msim":
            expected = [
                {
                    BuilderDiag(
                        filename=source,
                        builder_name=self.builder_name,
                        text='Unknown identifier "some_lib".',
                        line_number=3,
                        error_code="vcom-1136",
                        severity=DiagType.ERROR,
                    )
                }
            ]
        elif self.builder_name == "ghdl":
            expected = [
                {
                    BuilderDiag(
                        filename=source,
                        builder_name=self.builder_name,
                        text='no declaration for "some_lib"',
                        line_number=3,
                        column_number=4,
                        severity=DiagType.ERROR,
                    ),
                    BuilderDiag(
                        filename=source,
                        builder_name=self.builder_name,
                        text="entity 'source_with_error' was not analysed",
                        line_number=17,
                        column_number=34,
                        severity=DiagType.ERROR,
                    ),
                }
            ]
        elif self.builder_name == "xvhdl":
            # XVHDL reports different errors depending on the version
            expected = [
                {
                    BuilderDiag(
                        filename=source,
                        builder_name=self.builder_name,
                        text="some_lib is not declared",
                        line_number=3,
                        error_code="VRFC 10-91",
                        severity=DiagType.ERROR,
                    )
                },
                {
                    BuilderDiag(
                        filename=source,
                        builder_name=self.builder_name,
                        text="'some_lib' is not declared",
                        line_number=3,
                        error_code="VRFC 10-2989",
                        severity=DiagType.ERROR,
                    )
                },
            ]

        if not isinstance(self.builder, Fallback):
            self.assertIn(records, expected)
        else:
            self.assertFalse(records)

        self.assertFalse(rebuilds)

    def test_MsimRecompileMsg0(self):
        # type: (...) -> Any
        if not isinstance(self.builder, MSim):
            raise unittest2.SkipTest("ModelSim only test")

        line = (
            "** Error: (vcom-13) Recompile foo_lib.bar_component because "
            "foo_lib.foo_lib_pkg has changed."
        )

        self.assertEqual(
            [{"library_name": "foo_lib", "unit_name": "bar_component"}],
            self.builder._searchForRebuilds(line),
        )

    def test_MsimRecompileMsg1(self):
        # type: (...) -> Any
        if not isinstance(self.builder, MSim):
            raise unittest2.SkipTest("ModelSim only test")

        line = (
            "** Error: (vcom-13) Recompile foo_lib.bar_component because "
            "foo_lib.foo_lib_pkg, base_library.very_common_package have changed."
        )

        self.assertEqual(
            [{"library_name": "foo_lib", "unit_name": "bar_component"}],
            self.builder._searchForRebuilds(line),
        )

    def test_GhdlRecompileMsg(self):
        # type: (...) -> Any
        if not isinstance(self.builder, GHDL):
            raise unittest2.SkipTest("GHDL only test")

        line = 'somefile.vhd:12:13: package "leon3" is obsoleted by package "amba"'

        self.assertEqual(
            [{"unit_type": "package", "unit_name": "leon3"}],
            self.builder._searchForRebuilds(line),
        )

    def test_XvhdlRecompileMsg0(self):
        # type: (...) -> Any
        if not isinstance(self.builder, XVHDL):
            raise unittest2.SkipTest("XVHDL only test")

        line = (
            "ERROR: [VRFC 10-113] {} needs to be re-saved since std.standard "
            "changed".format(
                p.join("some", "path", "xsim.dir", "some_library", "some_package.vdb")
            )
        )

        self.assertEqual(
            [{"library_name": "some_library", "unit_name": "some_package"}],
            self.builder._searchForRebuilds(line),
        )

    # Rebuild formats are:
    # - {unit_type: '', 'unit_name': }
    # - {library_name: '', 'unit_name': }
    # - {rebuild_path: ''}
    @parameterized.parameterized.expand(
        [
            (
                {"unit_type": "package", "unit_name": "very_common_pkg"},
                RebuildUnit(
                    name=Identifier("very_common_pkg"), type_=DesignUnitType.package
                ),
            ),
            # Should replace 'work' with the path's library
            (
                {"library_name": "work", "unit_name": "foo"},
                RebuildLibraryUnit(
                    name=Identifier("foo"), library=Identifier("some_lib")
                ),
            ),
            # Should not touch the library name when != 'work'
            (
                {"library_name": "foo", "unit_name": "bar"},
                RebuildLibraryUnit(name=Identifier("bar"), library=Identifier("foo")),
            ),
            ({"rebuild_path": "some_path"}, RebuildPath(Path("some_path"))),
        ]
    )
    def test_GetRebuilds(self, rebuild_info, expected):
        # type: (...) -> Any
        _logger.info("Rebuild info is %s", rebuild_info)
        library = Identifier("some_lib", False)
        with patch.object(
            self.builder, "_searchForRebuilds", return_value=[rebuild_info]
        ):
            self.builder._database.getDependenciesByPath = MagicMock(
                return_value=[
                    RequiredDesignUnit(
                        owner=Path(""),
                        name=Identifier("very_common_pkg"),
                        library=Identifier("work"),
                    )
                ]
            )

            self.assertCountEqual(
                self.builder._getRebuilds(_source("source.vhd"), "", library),
                {expected},
            )


class TestMiscCases(TestCase):
    @parameterized.parameterized.expand([(x,) for x in AVAILABLE_BUILDERS])
    def test_NotAvailable(self, builder_class):
        # type: (...) -> Any
        if builder_class is Fallback:
            self.assertTrue(builder_class.isAvailable())
        else:
            self.assertFalse(builder_class.isAvailable())

    @parameterized.parameterized.expand([(x,) for x in AVAILABLE_BUILDERS])
    def test_RaisesSanityError(self, builder_class):
        # type: (...) -> Any
        if builder_class is Fallback:
            raise self.skipTest("Fallback won't raise any exception")

        _logger.info("Testing builder %s", builder_class.builder_name)

        with self.assertRaises(SanityCheckError):
            _ = builder_class(
                Path(p.join(TEST_TEMP_PATH, "_%s" % builder_class.builder_name)), None
            )

    @parameterized.parameterized.expand(
        [(x,) for x in (FileType.verilog, FileType.systemverilog)]
    )
    def test_IncludedPaths(self, filetype):
        # type: (...) -> Any
        work_folder = mkdtemp()
        database = MagicMock(spec=Database)

        def includedPath(name):
            return IncludedPath(
                name=Identifier(name),
                owner=Path("owner"),
                locations=frozenset([Location(0, 0)]),
            )

        def requiredDesignUnit(name):
            return RequiredDesignUnit(
                name=Identifier(name),
                owner=Path("owner"),
                locations=frozenset([Location(0, 0)]),
            )

        included_results = Queue()  # type: Queue[Optional[Path]]
        included_results.put(Path(p.join("", "library", "some", "")))
        included_results.put(None)

        def resolveIncludedPath(*_):
            return included_results.get(block=False)

        database.getDependenciesByPath.return_value = [
            includedPath(name="resolved/include"),
            includedPath(name="unresolved/include"),
            requiredDesignUnit(name="some_unit"),
        ]

        database.resolveIncludedPath = resolveIncludedPath

        calls = []  # type: List[List[str]]

        def shell(cmd_with_args, *args, **kwargs):
            calls.append(cmd_with_args)
            _logger.debug("$ %s", cmd_with_args)
            if "-version" in cmd_with_args:
                return ("vcom 10.2c Compiler 2013.07 Jul 18 2013",)
            return ("",)

        if filetype is FileType.verilog:
            source = _source("no_messages.v")
        else:
            source = _source("no_messages.sv")

        with patch("hdl_checker.builders.msim.runShellCommand", shell):
            builder = MSim(Path(work_folder), database=database)

            records, rebuilds = builder.build(
                source, Identifier("work"), BuildFlagScope.single
            )

        expected = [
            "vlog",
            "-modelsimini",
            p.join(work_folder, "modelsim.ini"),
            "-quiet",
            "-work",
            p.join(work_folder, "work"),
        ]

        if filetype is FileType.systemverilog:
            expected += ["-sv"]

        expected += [
            "-lint",
            "-hazards",
            "-pedanticerrors",
            "-L",
            "work",
            "+incdir+" + p.join("", "library", "some"),
            str(source),
        ]

        self.assertEqual(expected, calls[-1])

        self.assertFalse(records)
        self.assertFalse(rebuilds)
