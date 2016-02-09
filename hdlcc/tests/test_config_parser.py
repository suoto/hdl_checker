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

import os
import os.path as path
import logging

from nose2.tools import such

import hdlcc
from hdlcc.tests.utils import writeListToFile

_logger = logging.getLogger(__name__)

with such.A('config parser') as it:

    @it.has_setup
    def setup():
        it.project_filename = 'test.prj'

    @it.has_teardown
    def teardown():
        if path.exists(it.project_filename):
            os.remove(it.project_filename)

    @it.should('extract basic build info')
    def test(case):
        config_content = [
            r'batch_build_flags = -batch0 -batch1',
            r'single_build_flags = -single0 -single1',
            r'global_build_flags = -global0 -global1',
            r'builder = msim',
            r'target_dir = .build',
            r'vhdl work ./dependencies/vim-hdl-examples/another_library/foo.vhd',
        ]

        writeListToFile(it.project_filename, config_content)

        target_dir, builder_name, builder_flags, source_list = \
            hdlcc.config_parser.readConfigFile(it.project_filename)

        it.assertEqual(target_dir, path.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({'-batch0', '-batch1'}, builder_flags['batch'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])

        it.assertItemsEqual(
            [(path.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'),
              'work',
              set())],
            source_list)

    @it.should('handle missing batch build flags')
    def test(case):
        config_content = [
            'single_build_flags = -single0 -single1',
            'global_build_flags = -global0 -global1',
            'builder = msim',
            'target_dir = .build',
            'vhdl work ./dependencies/vim-hdl-examples/another_library/foo.vhd',
        ]

        writeListToFile(it.project_filename, config_content)

        target_dir, builder_name, builder_flags, source_list = \
            hdlcc.config_parser.readConfigFile(it.project_filename)

        it.assertEqual(target_dir, path.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({}, builder_flags['batch'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])

        it.assertItemsEqual(
            [(path.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'),
              'work',
              set())],
            source_list)

    @it.should('only include VHDL sources')
    def test(case):
        config_content = [
            'single_build_flags = -single0 -single1',
            'global_build_flags = -global0 -global1',
            'builder = msim',
            'target_dir = .build',
            'vhdl work ./dependencies/vim-hdl-examples/another_library/foo.vhd',
            'verilog work ./dependencies/vim-hdl-examples/another_library/foo.v',
        ]

        writeListToFile(it.project_filename, config_content)

        target_dir, builder_name, builder_flags, source_list = \
            hdlcc.config_parser.readConfigFile(it.project_filename)

        it.assertEqual(target_dir, path.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({}, builder_flags['batch'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])

        it.assertItemsEqual(
            [(path.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'),
              'work',
              set())],
            source_list)

    @it.should('raise UnknownParameterError exception when an unknown parameter '
               'is found')
    def test(case):
        config_content = [
            'hello = world',
            'global_build_flags = -global0 -global1',
            'builder = msim',
            'target_dir = .build',
            'vhdl work dependencies/vim-hdl-examples/another_library/foo.vhd',
        ]

        writeListToFile(it.project_filename, config_content)

        with it.assertRaises(hdlcc.exceptions.UnknownParameterError):
            hdlcc.config_parser.readConfigFile(it.project_filename)

    @it.should('handle absolute and relative paths')
    def test(case):
        config_content = [
            'builder = msim',
            'target_dir = .build',
            'vhdl work dependencies/vim-hdl-examples/another_library/foo.vhd',
        ]

        config_content += [
            'vhdl work %s' % path.abspath('./dependencies/vim-hdl-examples/'
                                          'basic_library/clock_divider.vhd'),
        ]

        writeListToFile(it.project_filename, config_content)

        target_dir, builder_name, builder_flags, source_list = \
            hdlcc.config_parser.readConfigFile(it.project_filename)

        it.assertEqual(target_dir, path.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        #  it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({}, builder_flags['batch'])
        it.assertItemsEqual({}, builder_flags['global'])
        it.assertItemsEqual({}, builder_flags['single'])

        it.assertItemsEqual([
            (path.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'), \
                    'work', set()),
            (path.abspath('dependencies/vim-hdl-examples/basic_library/clock_divider.vhd'),\
                    'work', set()),
            ], \
            source_list)

    @it.should('assign a default value for target dir equal to the builder value')
    def test(case):
        config_content = [
            'builder = msim',
            'vhdl work dependencies/vim-hdl-examples/another_library/foo.vhd',
        ]

        writeListToFile(it.project_filename, config_content)

        target_dir, builder_name, _, source_list = \
            hdlcc.config_parser.readConfigFile(it.project_filename)

        it.assertEqual(target_dir, '.msim')
        it.assertEqual(builder_name, 'msim')
        #  it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])

        it.assertItemsEqual([
            (path.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'), \
                    'work', set()),
            ], \
            source_list)

it.createTests(globals())

