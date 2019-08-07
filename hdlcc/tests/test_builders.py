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

# pylint: disable=function-redefined, missing-docstring, protected-access

import logging
import os
import os.path as p
import shutil

import mock
import parameterized
import unittest2

from hdlcc.builders import getBuilderByName
from hdlcc.diagnostics import BuilderDiag, DiagType
from hdlcc.parsers import VhdlParser
from hdlcc.tests.utils import assertSameFile, parametrizeClassWithBuilders

_logger = logging.getLogger(__name__)

TEST_SUPPORT_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')

SOURCES_PATH = p.join(p.dirname(__file__), '..', '..', '.ci',
                      'test_support', 'test_builders')

@parametrizeClassWithBuilders
class TestBuilder(unittest2.TestCase):
    # Create defaults so that pylint doesn't complain about non existing
    # members
    builder_name = None
    builder_path = None

    @classmethod
    def setUpClass(cls):
        # Add builder path to the env
        cls.original_env = os.environ.copy()

        # Add the builder path to the environment so we can call it
        if cls.builder_path:
            cls.patch = mock.patch.dict(
                'os.environ',
                {'PATH' : os.pathsep.join([cls.builder_path, os.environ['PATH']])})
            cls.patch.start()

        builder_class = getBuilderByName(cls.builder_name)
        cls.builder = builder_class(p.join(TEST_SUPPORT_PATH,
                                           '._%s' % cls.builder_name))
        cls.builder_class = builder_class

        # Copy sources path to tox env
        cls.sources_path = p.join(TEST_SUPPORT_PATH,
                                  'test_support_{}'.format(cls.builder_name))

        shutil.copytree(SOURCES_PATH, cls.sources_path)

    @classmethod
    def tearDownClass(cls):
        if cls.builder_name == 'xvhdl':
            try:
                os.remove('.xvhdl.init')
            except OSError:
                pass
            try:
                os.remove('xvhdl.pb')
            except OSError:
                pass

        if cls.builder_path:
            cls.patch.stop()
        if p.exists('._%s' % cls.builder_name):
            shutil.rmtree('._%s' % cls.builder_name)

    def test_environment_check(self):
        self.builder.checkEnvironment()

    def test_builder_reports_its_available(self):
        self.assertTrue(self.builder_class.isAvailable())

    def test_create_library_multiple_times(self):
        self.builder._createLibrary('random_lib')
        self.builder._createLibrary('random_lib')

    def test_builder_does_nothing_when_creating_builtin_libraries(self):
        self.builder._createLibrary('ieee')

    def test_finds_builtin_libraries(self):
        expected = ['ieee', 'std']

        if self.builder_name == "msim":
            expected += ['modelsim_lib']

        for lib in expected:
            self.assertIn(lib, self.builder.getBuiltinLibraries())

    @parameterized.parameterized.expand([
        ('/some/file/with/abs/path.vhd', ),
        ('some/file/with/relative/path.vhd', ),
        ('some_file_on_same_level.vhd', ),
        (r'C:\some\file\on\windows.vhd', )])
    def test_parse_msim_result(self, path):
        if self.builder_name != "msim":
            raise unittest2.SkipTest("ModelSim only test")

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Error: %s(21): near \"EOF\": (vcom-1576) "
                "expecting \';\'." % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="near \"EOF\": expecting \';\'.",
                filename=path,
                line_number=21,
                error_code='vcom-1576',
                severity=DiagType.ERROR)])

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Warning: %s(23): (vcom-1320) Type of expression "
                "\"(OTHERS => '0')\" is ambiguous; using element type "
                "STD_LOGIC_VECTOR, not aggregate type register_type." % path)),

            [BuilderDiag(
                builder_name=self.builder_name,
                text="Type of expression \"(OTHERS => '0')\" is "
                     "ambiguous; using element type STD_LOGIC_VECTOR, not "
                     "aggregate type register_type.",
                filename=path,
                line_number=23,
                error_code='vcom-1320',
                severity=DiagType.WARNING)])

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Warning: %s(39): (vcom-1514) Range choice direction "
                "(downto) does not determine aggregate index range "
                "direction (to)." % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="Range choice direction (downto) does not determine "
                     "aggregate index range direction (to).",
                filename=path,
                line_number=39,
                error_code='vcom-1514',
                severity=DiagType.WARNING)])

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Error: (vcom-11) Could not find work.regfile_pkg.")),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="Could not find work.regfile_pkg.",
                error_code='vcom-11',
                severity=DiagType.ERROR)])

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Error (suppressible): %s(7): (vcom-1195) Cannot find "
                "expanded name \"work.regfile_pkg\"." % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="Cannot find expanded name \"work.regfile_pkg\".",
                filename=path,
                line_number=7,
                error_code='vcom-1195',
                severity=DiagType.ERROR)])

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Error: %s(7): Unknown expanded name." % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="Unknown expanded name.",
                line_number='7',
                filename=path,
                severity=DiagType.ERROR)])

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Warning: [14] %s(103): (vcom-1272) Length of expected "
                "is 4; length of actual is 8." % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="Length of expected is 4; length of actual is 8.",
                line_number='103',
                error_code='vcom-1272',
                filename=path,
                severity=DiagType.WARNING)])

        self.assertEqual(
            list(self.builder._makeRecords(
                "** Warning: [14] %s(31): (vcom-1246) Range -1 downto 0 "
                "is null." % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="Range -1 downto 0 is null.",
                line_number='31',
                error_code='vcom-1246',
                filename=path,
                severity=DiagType.WARNING)])

    @parameterized.parameterized.expand([
        ('/some/file/with/abs/path.vhd', ),
        ('some/file/with/relative/path.vhd', ),
        ('some_file_on_same_level.vhd', ),
        (r'C:\some\file\on\windows.vhd', )])
    def test_parse_ghdl_result(self, path):
        if self.builder_name != "ghdl":
            raise unittest2.SkipTest("GHDL only test")

        self.assertEqual(
            list(self.builder._makeRecords(
                "%s:11:35: extra ';' at end of interface list" % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                filename=path,
                line_number=11,
                column_number=35,
                severity=DiagType.ERROR,
                text="extra ';' at end of interface list")])

    @parameterized.parameterized.expand([
        ('/some/file/with/abs/path.vhd',),
        ('some/file/with/relative/path.vhd',),
        ('some_file_on_same_level.vhd',)])
    def test_parse_xvhdl_result(self, path):
        if self.builder_name != "XVHDL":
            raise unittest2.SkipTest("XVHDL only test")

        self.assertEqual(
            list(self.builder._makeRecords(
                'ERROR: [VRFC 10-1412] syntax error near ) [%s:12]' % path)),
            [BuilderDiag(
                builder_name=self.builder_name,
                text="syntax error near )",
                filename=path,
                line_number=12,
                error_code='VRFC 10-1412',
                severity=DiagType.ERROR)])

    def test_vhdl_compilation(self):
        if 'vhdl' not in self.builder_class.file_types:
            raise unittest2.SkipTest("Builder {} doesn't support VHDL"
                                     .format(self.builder_name))

        source = VhdlParser(p.join(SOURCES_PATH, 'no_messages.vhd'))
        records, rebuilds = self.builder.build(source)
        self.assertNotIn(DiagType.ERROR, [x.severity for x in records],
                         'This source should not generate errors.')
        self.assertEqual(rebuilds, [])

    def test_verilog_compilation(self):
        if 'verilog' not in self.builder_class.file_types:
            raise unittest2.SkipTest("Builder {} doesn't support Verilog"
                                     .format(self.builder_name))

        source = VhdlParser(p.join(SOURCES_PATH, 'no_messages.v'))
        records, rebuilds = self.builder.build(source)
        self.assertNotIn(DiagType.ERROR, [x.severity for x in records],
                         'This source should not generate errors.')
        self.assertEqual(rebuilds, [])

    def test_systemverilog_compilation(self):
        if 'systemverilog' not in self.builder_class.file_types:
            raise unittest2.SkipTest("Builder {} doesn't support SystemVerilog"
                                     .format(self.builder_name))

        source = VhdlParser(p.join(SOURCES_PATH, 'no_messages.sv'))
        records, rebuilds = self.builder.build(source)
        self.assertNotIn(DiagType.ERROR, [x.severity for x in records],
                         'This source should not generate errors.')
        self.assertEqual(rebuilds, [])

    def test_catch_a_known_error(self):
        source = VhdlParser(p.join(SOURCES_PATH,
                                   'source_with_error.vhd'))
        records, rebuilds = self.builder.build(source, forced=True)

        for record in records:
            _logger.info(record)

        if self.builder_name == 'msim':
            expected = [BuilderDiag(
                builder_name=self.builder_name,
                text='Unknown identifier "some_lib".',
                line_number=4,
                error_code='vcom-1136',
                severity=DiagType.ERROR)]
        elif self.builder_name == 'ghdl':
            expected = [BuilderDiag(
                builder_name=self.builder_name,
                text='no declaration for "some_lib"',
                line_number=4,
                column_number=5,
                severity=DiagType.ERROR)]
        elif self.builder_name == 'xvhdl':
            expected = [
                BuilderDiag(
                    builder_name=self.builder_name,
                    text='some_lib is not declared',
                    line_number=4,
                    error_code='VRFC 10-91',
                    severity=DiagType.ERROR),

                BuilderDiag(
                    builder_name=self.builder_name,
                    text="'some_lib' is not declared",
                    line_number='4',
                    error_code='VRFC 10-2989',
                    severity=DiagType.ERROR)]

        self.assertEqual(len(records), 1)
        record = records.pop()
        assertSameFile(self)(record.filename, source.filename)

        # By this time the path to the file is the same, so we'll force the
        # expected record's filename to use the __eq__ operator
        for expected_diag in expected:
            expected_diag.filename = source.filename

        self.assertIn(record, expected)

        self.assertEqual(rebuilds, [])

    def test_msim_recompile_msg(self):
        if self.builder_name != "msim":
            raise unittest2.SkipTest("ModelSim only test")

        line = ("** Error: (vcom-13) Recompile foo_lib.bar_component because "
                "foo_lib.foo_lib_pkg has changed.")

        self.assertEqual(
            [{'library_name': 'foo_lib', 'unit_name': 'bar_component'}],
            self.builder._searchForRebuilds(line))

    def test_ghdl_recompile_msg(self):
        if self.builder_name != "ghdl":
            raise unittest2.SkipTest("GHDL only test")

        line = "somefile.vhd:12:13: package \"leon3\" is obsoleted by package \"amba\""

        self.assertEqual(
            [{'unit_type': 'package', 'unit_name': 'leon3'}],
            self.builder._searchForRebuilds(line))
