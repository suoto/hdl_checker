# This file is part of HDL Code Checker.
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
import shutil as shell
import time
import unittest
from nose2.tools import such
from nose2.tools.params import params
import hdlcc.builders
import hdlcc.utils as utils
from hdlcc.parsers.vhdl_source_file import VhdlSourceFile


BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = os.environ.get('BUILDER_PATH', p.expanduser("~/builders/ghdl/bin/"))
SOURCES_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support',
                      'test_builders')

_logger = logging.getLogger(__name__)

with such.A("'%s' builder object" % str(BUILDER_NAME)) as it:
    with it.having('its binary executable'):
        @it.has_setup
        def setup():
            it.original_env = os.environ.copy()

            utils.addToPath(BUILDER_PATH)

            cls = hdlcc.builders.getBuilderByName(BUILDER_NAME)
            it.builder = cls('._%s' % BUILDER_NAME)

        @it.has_teardown
        def teardown():
            utils.removeFromPath(BUILDER_PATH)
            if p.exists('._%s' % BUILDER_NAME):
                shell.rmtree('._%s' % BUILDER_NAME)

        @it.should('pass environment check')
        def test():
            it.builder.checkEnvironment()

        @it.should("parse MSim lines correctly")
        @unittest.skipUnless(BUILDER_NAME == "msim", "MSim only test")
        @params('/some/file/with/abs/path.vhd',
                'some/file/with/relative/path.vhd',
                'some_file_on_same_level.vhd',
                r'C:\some\file\on\windows.vhd')
        def test(case, path):
            _logger.info("Running '%s'", case)
            it.assertEquals(it.builder._makeMessageRecords(
                "** Error: %s(21): near \"EOF\": (vcom-1576) expecting \';\'." % path),
                [{'checker'        : 'msim',
                  'line_number'    : '21',
                  'column'         : None,
                  'filename'       : path,
                  'error_number'   : '1576',
                  'error_type'     : 'E',
                  'error_message'  : "near \"EOF\": expecting \';\'."}])

            it.assertEquals(it.builder._makeMessageRecords(
                "** Warning: %s(23): (vcom-1320) Type of expression \"(OTHERS => '0')\" is ambiguous; using element type STD_LOGIC_VECTOR, not aggregate type register_type." % path),
                [{'checker'        : 'msim',
                  'line_number'    : '23',
                  'column'         : None,
                  'filename'       : path,
                  'error_number'   : '1320',
                  'error_type'     : 'W',
                  'error_message'  : "Type of expression \"(OTHERS => '0')\" is ambiguous; using element type STD_LOGIC_VECTOR, not aggregate type register_type."}])

            it.assertEquals(it.builder._makeMessageRecords(
                "** Warning: %s(39): (vcom-1514) Range choice direction (downto) does not determine aggregate index range direction (to)." % path),
                [{'checker'        : 'msim',
                  'line_number'    : '39',
                  'column'         : None,
                  'filename'       : path,
                  'error_number'   : '1514',
                  'error_type'     : 'W',
                  'error_message'  : "Range choice direction (downto) does not determine aggregate index range direction (to)."}])

            it.assertEquals(it.builder._makeMessageRecords(
                "** Error: (vcom-11) Could not find work.regfile_pkg."),
                [{'checker'        : 'msim',
                  'line_number'    : None,
                  'column'         : None,
                  'filename'       : None,
                  'error_number'   : '11',
                  'error_type'     : 'E',
                  'error_message'  : "Could not find work.regfile_pkg."}])

            it.assertEquals(it.builder._makeMessageRecords(
                "** Error (suppressible): %s(7): (vcom-1195) Cannot find expanded name \"work.regfile_pkg\"." % path),
                [{'checker'        : 'msim',
                  'line_number'    : '7',
                  'column'         : None,
                  'filename'       : path,
                  'error_number'   : '1195',
                  'error_type'     : 'E',
                  'error_message'  : "Cannot find expanded name \"work.regfile_pkg\"."}])

            it.assertEquals(it.builder._makeMessageRecords(
                "** Error: %s(7): Unknown expanded name." % path),
                [{'checker'        : 'msim',
                  'line_number'    : '7',
                  'column'         : None,
                  'filename'       : path,
                  'error_number'   : None,
                  'error_type'     : 'E',
                  'error_message'  : "Unknown expanded name."}])

        @it.should("parse GHDL builder lines correctly")
        @unittest.skipUnless(BUILDER_NAME == "ghdl", "GHDL only test")
        @params('/some/file/with/abs/path.vhd',
                'some/file/with/relative/path.vhd',
                'some_file_on_same_level.vhd',
                r'C:\some\file\on\windows.vhd')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEquals(it.builder._makeMessageRecords(
                "%s:11:35: extra ';' at end of interface list" % path),
                [{'checker'        : 'ghdl',
                  'line_number'    : '11',
                  'column'         : '35',
                  'filename'       : path,
                  'error_number'   : None,
                  'error_type'     : 'E',
                  'error_message'  : "extra ';' at end of interface list"}])


        @it.should("parse XVHDL builder lines correctly")
        @unittest.skipUnless(BUILDER_NAME == "xvhdl", "XVHDL only test")
        @params('/some/file/with/abs/path.vhd',
                'some/file/with/relative/path.vhd',
                'some_file_on_same_level.vhd')
                #  r'C:\some\file\on\windows.vhd')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEquals(it.builder._makeMessageRecords(
                'ERROR: [VRFC 10-1412] syntax error near ) [%s:12]' % path),
                [{'checker'        : 'xvhdl',
                  'line_number'    : '12',
                  'column'         : None,
                  'filename'       : path,
                  'error_number'   : 'VRFC 10-1412',
                  'error_type'     : 'E',
                  'error_message'  : "syntax error near ) "}])

        @it.should('compile a VHDL source without errors')
        def test():
            source = VhdlSourceFile(p.join(SOURCES_PATH, 'no_messages.vhd'))
            records, rebuilds = it.builder.build(source)
            it.assertNotIn('E', [x['error_type'] for x in records],
                           'This source should not generate errors.')
            it.assertEqual(rebuilds, [])

        @it.should('catch a known error on a VHDL source')
        def test():
            source = VhdlSourceFile(p.join(SOURCES_PATH,
                                           'source_with_error.vhd'))
            records, rebuilds = it.builder.build(source)

            for record in records:
                _logger.info(record)

            if BUILDER_NAME == 'msim':
                expected = [{
                    'line_number': '12',
                    'error_number': None,
                    'error_message': "near \")\": expecting FUNCTION or PROCEDURE or IMPURE or PURE",
                    'column': None,
                    'error_type': 'E',
                    'checker': 'msim'}]
            elif BUILDER_NAME == 'ghdl':
                expected = [{
                    'line_number': '11',
                    'error_number': None,
                    'error_message': "extra ';' at end of interface list",
                    'column': '35',
                    'error_type': 'E',
                    'checker': 'ghdl'}]
            elif BUILDER_NAME == 'xvhdl':
                expected = [{
                    'line_number': '12',
                    'error_number': 'VRFC 10-1412',
                    'error_message': 'syntax error near ) ',
                    'column': None,
                    'error_type': 'E',
                    'checker': 'xvhdl'}]

            it.assertEqual(len(records), 1)
            it.assertTrue(utils.samefile(records[0].pop('filename'),
                                         source.filename))
            it.assertEquals(records, expected)

            it.assertEqual(rebuilds, [])

if BUILDER_NAME is not None:
    it.createTests(globals())

