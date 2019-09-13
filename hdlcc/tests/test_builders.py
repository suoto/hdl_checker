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

import logging
import os
import os.path as p
import shutil
from typing import Any, List

import mock
import parameterized  # type: ignore
import unittest2  # type: ignore

from hdlcc import types as t
from hdlcc.builder_utils import (
    AVAILABLE_BUILDERS,
    GHDL,
    XVHDL,
    AnyBuilder,
    Fallback,
    MSim,
)
from hdlcc.builders.base_builder import RebuildLibraryUnit, RebuildPath, RebuildUnit
from hdlcc.diagnostics import BuilderDiag, DiagType
from hdlcc.exceptions import SanityCheckError
from hdlcc.parsers.elements.dependency_spec import DependencySpec
from hdlcc.parsers.elements.identifier import Identifier
from hdlcc.parsers.vhdl_parser import VhdlParser
from hdlcc.path import Path
from hdlcc.tests.utils import (
    SourceMock,
    TestCase,
    assertSameFile,
    getTestTempPath,
    logIterable,
    parametrizeClassWithBuilders,
    setupTestSuport,
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

    def setUp(self):
        # type: (...) -> Any
        setupTestSuport(TEST_TEMP_PATH)
        # Add builder path to the env
        self.original_env = os.environ.copy()

        # Add the builder path to the environment so we can call it
        if self.builder_path:
            _logger.info("Adding '%s' to the system path", self.builder_path)
            self.patch = mock.patch.dict(
                "os.environ",
                {"PATH": os.pathsep.join([self.builder_path, os.environ["PATH"]])},
            )
            self.patch.start()

        assert self.builder_name is not None  # To make mypy happy

        builder_class = BUILDER_CLASS_MAP[self.builder_name]
        _logger.info("Builder class: %s", builder_class)
        self.builder = builder_class(
            _temp("_%s" % self.builder_name), mock.MagicMock()
        )  # type: AnyBuilder
        self.builder_class = builder_class  # type: ignore

    def tearDown(self):
        # type: (...) -> Any
        if self.builder_name == "xvhdl":
            try:
                os.remove(".xvhdl.init")
            except OSError:
                pass
            try:
                os.remove("xvhdl.pb")
            except OSError:
                pass

        if self.builder_path:
            self.patch.stop()
        if p.exists("._%s" % self.builder_name):
            shutil.rmtree("._%s" % self.builder_name)

    def test_environment_check(self):
        # type: (...) -> Any
        self.builder.checkEnvironment()

    def test_builder_reports_its_available(self):  # pylint: disable=invalid-name
        # type: (...) -> Any
        self.assertTrue(self.builder_class.isAvailable())  # type: ignore

    def test_create_library_multiple_times(self):  # pylint: disable=invalid-name
        # type: (...) -> Any
        self.builder._createLibrary(Identifier("random_lib"))
        self.builder._createLibrary(Identifier("random_lib"))

    def test_builder_does_nothing_when_creating_builtin_libraries(
        self
    ):  # pylint: disable=invalid-name
        # type: (...) -> Any
        #  pre = open(self.builder._xvhdlini).read()
        self.builder._createLibrary(Identifier("ieee"))
        #  post = open(self.builder._xvhdlini).read()

    def test_finds_builtin_libraries(self):
        # type: (...) -> Any
        expected = []  # type: List[str]

        if self.builder_name != "fallback":
            expected += ["ieee", "std"]

        if self.builder_name == "msim":
            expected += ["modelsim_lib"]

        for lib in map(Identifier, expected):
            self.assertIn(lib, self.builder.getBuiltinLibraries())

    @parameterized.parameterized.expand(
        [
            ("/some/file/with/abs/path.vhd",),
            ("some/file/with/relative/path.vhd",),
            ("some_file_on_same_level.vhd",),
            (r"C:\some\file\on\windows.vhd",),
        ]
    )
    def test_parse_msim_result(self, path):
        # type: (...) -> Any
        if self.builder_name != "msim":
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
                    line_number=21,
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
                    line_number=23,
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
                    line_number=39,
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
                    line_number=7,
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
                    line_number="7",
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
                    line_number="103",
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
                    line_number="31",
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
    def test_parse_ghdl_result(self, path):
        # type: (...) -> Any
        if self.builder_name != "ghdl":
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
                line_number=11,
                column_number=35,
                severity=DiagType.ERROR,
                text="extra ';' at end of interface list",
            )
        ]

        _logger.warning("records: %s", records)
        _logger.warning("records:  %s", list(map(hash, records)))
        _logger.warning("records:  %s", list(map(type, records)))
        _logger.warning("expected: %s", list(map(hash, expected)))
        _logger.warning("expected: %s", list(map(type, expected)))

        #  _logger.warning(" -> %s", records.pop == expected.pop())

        self.assertCountEqual(records, expected)

    @parameterized.parameterized.expand(
        [
            ("/some/file/with/abs/path.vhd",),
            ("some/file/with/relative/path.vhd",),
            ("some_file_on_same_level.vhd",),
        ]
    )
    def test_parse_xvhdl_result(self, path):
        # type: (...) -> Any
        if self.builder_name != "XVHDL":
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
                    filename=path,
                    line_number=12,
                    error_code="VRFC 10-1412",
                    severity=DiagType.ERROR,
                )
            ],
        )

    def test_vhdl_compilation(self):
        # type: (...) -> Any
        if t.FileType.vhdl not in self.builder_class.file_types:  # type: ignore
            raise unittest2.SkipTest(
                "Builder {} doesn't support VHDL".format(self.builder_name)
            )

        source = _source("no_messages.vhd")
        with mock.patch.object(
            self.builder._database, "getLibrary", return_value=Identifier("work")
        ):
            records, rebuilds = self.builder.build(source, Identifier("work"))
        self.assertNotIn(
            DiagType.ERROR,
            [x.severity for x in records],
            "This source should not generate errors.",
        )
        self.assertFalse(rebuilds)

    def test_verilog_compilation(self):
        # type: (...) -> Any
        if t.FileType.verilog not in self.builder_class.file_types:  # type: ignore
            raise unittest2.SkipTest(
                "Builder {} doesn't support Verilog".format(self.builder_name)
            )

        source = _source("no_messages.v")
        with mock.patch.object(
            self.builder._database, "getLibrary", return_value=Identifier("work")
        ):
            records, rebuilds = self.builder.build(source, Identifier("work"))
        self.assertNotIn(
            DiagType.ERROR,
            [x.severity for x in records],
            "This source should not generate errors.",
        )
        self.assertFalse(rebuilds)

    def test_systemverilog_compilation(self):
        # type: (...) -> Any
        if t.FileType.systemverilog not in self.builder_class.file_types:
            raise unittest2.SkipTest(
                "Builder {} doesn't support SystemVerilog".format(self.builder_name)
            )

        source = _source("no_messages.sv")

        with mock.patch.object(
            self.builder._database, "getLibrary", return_value=Identifier("work")
        ):
            records, rebuilds = self.builder.build(source, Identifier("work"))

        self.assertNotIn(
            DiagType.ERROR,
            [x.severity for x in records],
            "This source should not generate errors.",
        )
        self.assertFalse(rebuilds)

    def test_catch_a_known_error(self):
        # type: (...) -> Any
        #  source = VhdlParser(_source("source_with_error.vhd"))
        source = _source("source_with_error.vhd")
        self.builder._database.getDependenciesByPath = mock.MagicMock(
            return_value=[
                t.LibraryAndUnit(Identifier("ieee"), Identifier("std_logic_1164"))
            ]
        )

        records, rebuilds = self.builder.build(source, Identifier("lib"), forced=True)

        for record in records:
            _logger.info(record)

        if self.builder_name == "msim":
            expected = [
                BuilderDiag(
                    filename=source,
                    builder_name=self.builder_name,
                    text='Unknown identifier "some_lib".',
                    line_number=4,
                    error_code="vcom-1136",
                    severity=DiagType.ERROR,
                )
            ]
        elif self.builder_name == "ghdl":
            expected = [
                BuilderDiag(
                    filename=source,
                    builder_name=self.builder_name,
                    text='no declaration for "some_lib"',
                    line_number=4,
                    column_number=5,
                    severity=DiagType.ERROR,
                )
            ]
        elif self.builder_name == "xvhdl":
            expected = [
                BuilderDiag(
                    filename=source,
                    builder_name=self.builder_name,
                    text="some_lib is not declared",
                    line_number=4,
                    error_code="VRFC 10-91",
                    severity=DiagType.ERROR,
                ),
                BuilderDiag(
                    filename=source,
                    builder_name=self.builder_name,
                    text="'some_lib' is not declared",
                    line_number="4",
                    error_code="VRFC 10-2989",
                    severity=DiagType.ERROR,
                ),
            ]

        if self.builder_name != "fallback":
            self.assertEqual(len(records), 1)
            record = records.pop()
            #  assertSameFile(self)(record.filename, source.abspath)
            self.assertEqual(
                record.filename,
                source,
                "{} != {}".format(repr(record.filename), repr(source)),
            )

            #  # By this time the path to the file is the same, so we'll force the
            #  # expected record's filename to use the __eq__ operator
            #  for expected_diag in expected:
            #      expected_diag.filename = source.

            self.assertIn(record, expected)
        else:
            self.assertEqual(records, set())

        self.assertFalse(rebuilds)

    def test_msim_recompile_msg_0(self):
        # type: (...) -> Any
        if self.builder_name != "msim":
            raise unittest2.SkipTest("ModelSim only test")

        line = (
            "** Error: (vcom-13) Recompile foo_lib.bar_component because "
            "foo_lib.foo_lib_pkg has changed."
        )

        self.assertEqual(
            [{"library_name": "foo_lib", "unit_name": "bar_component"}],
            self.builder._searchForRebuilds(line),
        )

    def test_msim_recompile_msg_1(self):
        # type: (...) -> Any
        if self.builder_name != "msim":
            raise unittest2.SkipTest("ModelSim only test")

        line = (
            "** Error: (vcom-13) Recompile foo_lib.bar_component because "
            "foo_lib.foo_lib_pkg, base_library.very_common_package have changed."
        )

        self.assertEqual(
            [{"library_name": "foo_lib", "unit_name": "bar_component"}],
            self.builder._searchForRebuilds(line),
        )

    def test_ghdl_recompile_msg(self):
        # type: (...) -> Any
        if self.builder_name != "ghdl":
            raise unittest2.SkipTest("GHDL only test")

        line = 'somefile.vhd:12:13: package "leon3" is obsoleted by package "amba"'

        self.assertEqual(
            [{"unit_type": "package", "unit_name": "leon3"}],
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
                RebuildUnit(name="very_common_pkg", type_="package"),
            ),
            # Should replace 'work' with the path's library
            (
                {"library_name": "work", "unit_name": "foo"},
                RebuildLibraryUnit(name="foo", library="some_lib"),
            ),
            # Should not touch the library name when != 'work'
            (
                {"library_name": "foo", "unit_name": "bar"},
                RebuildLibraryUnit(name="bar", library="foo"),
            ),
            ({"rebuild_path": "some_path"}, RebuildPath("some_path")),
        ]
    )
    def test_get_rebuilds(self, rebuild_info, expected):
        # type: (...) -> Any
        _logger.info("Rebuild info is %s", rebuild_info)
        library = Identifier("some_lib", False)
        with mock.patch.object(
            self.builder, "_searchForRebuilds", return_value=[rebuild_info]
        ):
            self.builder._database.getDependenciesByPath = mock.MagicMock(
                return_value=[
                    DependencySpec(
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


class TestSanityError(unittest2.TestCase):
    @parameterized.parameterized.expand([(x,) for x in AVAILABLE_BUILDERS])
    def test_not_available(self, builder_class):
        # type: (...) -> Any
        if builder_class is Fallback:
            self.assertTrue(builder_class.isAvailable())
        else:
            self.assertFalse(builder_class.isAvailable())

    @parameterized.parameterized.expand([(x,) for x in AVAILABLE_BUILDERS])
    def test_raises_sanity_error(self, builder_class):
        # type: (...) -> Any
        if builder_class is Fallback:
            raise self.skipTest("Fallback won't raise any exception")

        _logger.info("Testing builder %s", builder_class.builder_name)

        with self.assertRaises(SanityCheckError):
            _ = builder_class(
                Path(p.join(TEST_TEMP_PATH, "_%s" % builder_class.builder_name)), None
            )
