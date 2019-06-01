# This file is part of HDL Code Checker.
#
# Copyright (c) 2015-2019 Andre Souto
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

from nose2.tools import such
from nose2.tools.params import params

import hdlcc.builders
import hdlcc.utils as utils
from hdlcc.diagnostics import BuilderDiag, DiagType
from hdlcc.parsers import VhdlParser

_logger = logging.getLogger(__name__)

with such.A("builder object") as it:
    @it.has_setup
    def setup():
        it.BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
        it.BUILDER_PATH = os.environ.get('BUILDER_PATH', None)
        it.SOURCES_PATH = p.join(p.dirname(__file__), '..', '..', '.ci',
                                 'test_support', 'test_builders')

    @it.has_teardown
    def teardown():
        if it.BUILDER_NAME == 'xvhdl':
            os.remove('.xvhdl.init')
            os.remove('xvhdl.pb')

    with it.having('its binary executable'):
        @it.has_setup
        def setup():
            it.original_env = os.environ.copy()

            # Add the builder path to the environment so we can call it
            if it.BUILDER_PATH:
                it.patch = mock.patch.dict(
                    'os.environ',
                    {'PATH' : os.pathsep.join([it.BUILDER_PATH, os.environ['PATH']])})
                it.patch.start()

            cls = hdlcc.builders.getBuilderByName(it.BUILDER_NAME)
            it.builder = cls('._%s' % it.BUILDER_NAME)
            it.cls = cls

        @it.has_teardown
        def teardown():
            if it.BUILDER_PATH:
                it.patch.stop()
            if p.exists('._%s' % it.BUILDER_NAME):
                shutil.rmtree('._%s' % it.BUILDER_NAME)

        @it.should('pass environment check')
        def test():
            it.builder.checkEnvironment()

        @it.should('should be available')
        def test():
            it.assertTrue(it.cls.isAvailable())

        @it.should('not fail when creating the same library multiple times')
        def test():
            it.builder._createLibrary('random_lib')
            it.builder._createLibrary('random_lib')

        @it.should('do nothing when trying to create builtin libraries')
        def test():
            it.builder._createLibrary('ieee')

        @it.should("find GHDL builtin libraries")
        def test():
            if it.BUILDER_NAME not in ('msim', 'ghdl', 'xvhdl'):
                _logger.info("Test requires a builder")
                return
            expected = ['ieee', 'std']

            if it.BUILDER_NAME == "msim":
                expected += ['modelsim_lib']

            for lib in expected:
                it.assertIn(lib, it.builder.getBuiltinLibraries())

        @it.should("parse MSim lines correctly")
        @params('/some/file/with/abs/path.vhd',
                'some/file/with/relative/path.vhd',
                'some_file_on_same_level.vhd',
                r'C:\some\file\on\windows.vhd')
        def test(case, path):
            if it.BUILDER_NAME != "msim":
                _logger.info("MSim only test")
                return

            _logger.info("Running '%s'", case)
            it.assertEqual(
                it.builder._makeRecords(
                    "** Error: %s(21): near \"EOF\": (vcom-1576) expecting \';\'." % path),
                [BuilderDiag(
                    builder_name=it.BUILDER_NAME,
                    text="near \"EOF\": expecting \';\'.",
                    filename=path,
                    line_number=21,
                    error_number='1576',
                    severity=DiagType.ERROR)])

            it.assertEqual(
                it.builder._makeRecords(
                    "** Warning: %s(23): (vcom-1320) Type of expression "
                    "\"(OTHERS => '0')\" is ambiguous; using element type "
                    "STD_LOGIC_VECTOR, not aggregate type register_type." % path),

                [BuilderDiag(
                    builder_name=it.BUILDER_NAME,
                    text="Type of expression \"(OTHERS => '0')\" is "
                         "ambiguous; using element type STD_LOGIC_VECTOR, not "
                         "aggregate type register_type.",
                    filename=path,
                    line_number=23,
                    error_number='1320',
                    severity=DiagType.WARNING)])

            it.assertEquals(
                it.builder._makeRecords(
                    "** Warning: %s(39): (vcom-1514) Range choice direction "
                    "(downto) does not determine aggregate index range "
                    "direction (to)." % path),
                [BuilderDiag(
                    builder_name=it.BUILDER_NAME,
                    text="Range choice direction (downto) does not determine "
                         "aggregate index range direction (to).",
                    filename=path,
                    line_number=39,
                    error_number='1514',
                    severity=DiagType.WARNING)])

            it.assertEquals(
                it.builder._makeRecords(
                    "** Error: (vcom-11) Could not find work.regfile_pkg."),
                [BuilderDiag(
                    builder_name=it.BUILDER_NAME,
                    text="Could not find work.regfile_pkg.",
                    error_number='11',
                    severity=DiagType.ERROR)])

            it.assertEquals(
                it.builder._makeRecords(
                    "** Error (suppressible): %s(7): (vcom-1195) Cannot find "
                    "expanded name \"work.regfile_pkg\"." % path),
                [BuilderDiag(
                    builder_name=it.BUILDER_NAME,
                    text="Cannot find expanded name \"work.regfile_pkg\".",
                    filename=path,
                    line_number=7,
                    error_number='1195',
                    severity=DiagType.ERROR)])

            it.assertEquals(
                it.builder._makeRecords(
                    "** Error: %s(7): Unknown expanded name." % path),
                [BuilderDiag(
                    builder_name=it.BUILDER_NAME,
                    text="Unknown expanded name.",
                    line_number='7',
                    filename=path,
                    severity=DiagType.ERROR)])

        @it.should("parse GHDL builder lines correctly")
        @params('/some/file/with/abs/path.vhd',
                'some/file/with/relative/path.vhd',
                'some_file_on_same_level.vhd',
                r'C:\some\file\on\windows.vhd')
        def test(case, path):
            if it.BUILDER_NAME != "ghdl":
                _logger.info("GHDL only test")
                return
            _logger.info("Running %s", case)
            it.assertEquals(it.builder._makeRecords(
                "%s:11:35: extra ';' at end of interface list" % path),
                [{'checker'        : 'ghdl',
                  'line_number'    : '11',
                  'column'         : '35',
                  'filename'       : path,
                  'error_number'   : None,
                  'severity'     : 'E',
                  'error_message'  : "extra ';' at end of interface list"}])

        @it.should("parse XVHDL builder lines correctly")
        @params('/some/file/with/abs/path.vhd',
                'some/file/with/relative/path.vhd',
                'some_file_on_same_level.vhd')
                #  r'C:\some\file\on\windows.vhd')
        def test(case, path):
            if it.BUILDER_NAME != "XVHDL":
                _logger.info("XVHDL only test")
                return
            _logger.info("Running %s", case)
            it.assertEquals(it.builder._makeRecords(
                'ERROR: [VRFC 10-1412] syntax error near ) [%s:12]' % path),
                [{'checker'        : 'xvhdl',
                  'line_number'    : '12',
                  'column'         : None,
                  'filename'       : path,
                  'error_number'   : 'VRFC 10-1412',
                  'severity'     : 'E',
                  'error_message'  : "syntax error near )"}])

        @it.should('compile a VHDL source without errors')
        def test():
            source = VhdlParser(p.join(it.SOURCES_PATH, 'no_messages.vhd'))
            records, rebuilds = it.builder.build(source)
            it.assertNotIn('E', [x['severity'] for x in records],
                           'This source should not generate errors.')
            it.assertEqual(rebuilds, [])

        @it.should('compile a Verilog source without errors')
        def test():
            if it.BUILDER_NAME != "msim":
                _logger.info("MSim only test")
                return
            source = VhdlParser(p.join(it.SOURCES_PATH, 'no_messages.v'))
            records, rebuilds = it.builder.build(source)
            it.assertNotIn('E', [x['severity'] for x in records],
                           'This source should not generate errors.')
            it.assertEqual(rebuilds, [])

        @it.should('compile a SystemVerilog source without errors')
        def test():
            if it.BUILDER_NAME != "msim":
                _logger.info("MSim only test")
                return
            source = VhdlParser(p.join(it.SOURCES_PATH, 'no_messages.sv'))
            records, rebuilds = it.builder.build(source)
            it.assertNotIn('E', [x['severity'] for x in records],
                           'This source should not generate errors.')
            it.assertEqual(rebuilds, [])


        @it.should('catch a known error on a VHDL source')
        def test():
            if it.BUILDER_NAME not in ('msim', 'ghdl', 'xvhdl'):
                _logger.info("Test requires a builder")
                return

            source = VhdlParser(p.join(it.SOURCES_PATH,
                                       'source_with_error.vhd'))
            records, rebuilds = it.builder.build(source, forced=True)

            for record in records:
                _logger.info(record)

            if it.BUILDER_NAME == 'msim':
                expected = [BuilderDiag(
                    builder_name=it.BUILDER_NAME,
                    text='Unknown identifier "some_lib".',
                    line_number=4,
                    error_number='1136',
                    severity=DiagType.ERROR)]
            elif it.BUILDER_NAME == 'ghdl':
                expected = [{
                    'line_number': '4',
                    'error_number': None,
                    'error_message': 'no declaration for "some_lib"',
                    'column': '5',
                    'severity': 'E',
                    'checker': 'ghdl'}]
            elif it.BUILDER_NAME == 'xvhdl':
                expected = [
                    {'line_number': '4',
                     'error_number': 'VRFC 10-91',
                     'error_message': 'some_lib is not declared',
                     'column': None,
                     'severity': 'E',
                     'checker': 'xvhdl'},

                    {'line_number': '4',
                     'error_number': 'VRFC 10-2989',
                     'error_message': "'some_lib' is not declared",
                     'column': None,
                     'severity': 'E',
                     'checker': 'xvhdl'}]

            it.assertEqual(len(records), 1)
            record = records.pop()
            it.assertTrue(utils.samefile(record.filename,
                                         source.filename))

            # By this time the path to the file is the same, so we'll force the
            # expected record's filename to use the __eq__ operator
            for expected_diag in expected:
                expected_diag.filename = source.filename

            it.assertIn(record, expected)

            it.assertEqual(rebuilds, [])

        @it.should("catch MSim rebuilds by messages")
        @params(
            "** Error: (vcom-13) Recompile foo_lib.bar_component because "
            "foo_lib.foo_lib_pkg has changed.",)
        def test(case, line):
            if it.BUILDER_NAME != 'msim':
                _logger.info("ModelSim test only")
                return
            _logger.info("Running %s", case)

            it.assertEquals(
                [{'library_name': 'foo_lib', 'unit_name': 'bar_component'}],
                it.builder._searchForRebuilds(line))

        @it.should("catch GHDL rebuilds by messages")
        @params(
            "somefile.vhd:12:13: package \"leon3\" is obsoleted by package \"amba\"")
        def test(case, line):
            if it.BUILDER_NAME != 'ghdl':
                _logger.info("GHDL test only")
                return
            _logger.info("Running %s", case)

            it.assertEquals(
                [{'unit_type': 'package', 'unit_name': 'leon3'}],
                it.builder._searchForRebuilds(line))

it.createTests(globals())

