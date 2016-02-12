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

# pylint: disable=function-redefined, missing-docstring

import os
import os.path as p
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
        if p.exists(it.project_filename):
            os.remove(it.project_filename)

    @it.should('extract basic build info')
    def test():
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

        it.assertEqual(target_dir, p.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({'-batch0', '-batch1'}, builder_flags['batch'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])

        it.assertItemsEqual(
            [(p.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'),
              'work',
              set())],
            source_list)

    @it.should('handle missing batch build flags')
    def test():
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

        it.assertEqual(target_dir, p.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({}, builder_flags['batch'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])

        it.assertItemsEqual(
            [(p.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'),
              'work',
              set())],
            source_list)

    @it.should('only include VHDL sources')
    def test():
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

        it.assertEqual(target_dir, p.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({}, builder_flags['batch'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])
        it.assertItemsEqual({'-global0', '-global1'}, builder_flags['global'])

        it.assertItemsEqual(
            [(p.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'),
              'work',
              set())],
            source_list)

    @it.should('raise UnknownParameterError exception when an unknown parameter '
               'is found')
    def test():
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
    def test():
        config_content = [
            'builder = msim',
            'target_dir = .build',
            'vhdl work dependencies/vim-hdl-examples/another_library/foo.vhd',
        ]

        config_content += [
            'vhdl work %s' % p.abspath('./dependencies/vim-hdl-examples/'
                                       'basic_library/clock_divider.vhd'),
        ]

        writeListToFile(it.project_filename, config_content)

        target_dir, builder_name, builder_flags, source_list = \
            hdlcc.config_parser.readConfigFile(it.project_filename)

        it.assertEqual(target_dir, p.abspath('.build'))
        it.assertEqual(builder_name, 'msim')
        #  it.assertItemsEqual({'-single0', '-single1'}, builder_flags['single'])
        it.assertItemsEqual({}, builder_flags['batch'])
        it.assertItemsEqual({}, builder_flags['global'])
        it.assertItemsEqual({}, builder_flags['single'])

        it.assertItemsEqual([
            (p.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'), \
                    'work', set()),
            (p.abspath('dependencies/vim-hdl-examples/basic_library/clock_divider.vhd'),\
                    'work', set()),
            ], \
            source_list)

    @it.should('assign a default value for target dir equal to the builder value')
    def test():
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
            (p.abspath('dependencies/vim-hdl-examples/another_library/foo.vhd'), \
                    'work', set()),
            ], \
            source_list)

with such.A('config parser object') as it:

    with it.having('a standard project file'):
        @it.has_setup
        def setup():
            it.project_filename = 'test.prj'
            config_content = [
                r'batch_build_flags = -b0 -b1',
                r'single_build_flags = -s0 -s1',
                r'global_build_flags = -g0 -g1',
                r'builder = msim',
                r'target_dir = .build',
                r'vhdl work ./dependencies/vim-hdl-examples/another_library/foo.vhd -f0',
                r'vhdl work ' + p.abspath('./dependencies/vim-hdl-examples/'
                                          'basic_library/clock_divider.vhd') + ' -f1',
                'verilog work ./dependencies/vim-hdl-examples/another_library/foo.v',
            ]

            writeListToFile(it.project_filename, config_content)

            it.parser = hdlcc.config_parser.ConfigParser(it.project_filename)

        @it.has_teardown
        def teardown():
            del it.project_filename
            del it.parser

        @it.should('extract builder')
        def test():
            it.assertEqual(it.parser.getBuilder(), 'msim')

        @it.should('extract target dir')
        def test():
            it.assertTrue(p.isabs(it.parser.getTargetDir()))
            it.assertEqual(it.parser.getTargetDir(), p.abspath('.build'))

        @it.should('extract build flags for single build')
        def test():
            it.assertItemsEqual(
                it.parser.getSingleBuildFlagsByPath('./dependencies/vim-hdl-examples/'
                                                    'another_library/foo.vhd'),
                set(['-s0', '-s1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getSingleBuildFlagsByPath('./dependencies/vim-hdl-examples/'
                                                    'basic_library/clock_divider.vhd'),
                set(['-s0', '-s1', '-g0', '-g1', '-f1']))

        @it.should('extract build flags for batch builds')
        def test():
            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath('./dependencies/vim-hdl-examples/'
                                                   'another_library/foo.vhd'),
                set(['-b0', '-b1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath('./dependencies/vim-hdl-examples/'
                                                   'basic_library/clock_divider.vhd'),
                set(['-b0', '-b1', '-g0', '-g1', '-f1']))

        @it.should('only include VHDL sources')
        def test():
            expected_sources = [p.abspath(x) \
                for x in ('dependencies/vim-hdl-examples/another_library/foo.vhd',
                          'dependencies/vim-hdl-examples/basic_library/clock_divider.vhd')]

            parser_sources = [x.filename for x in it.parser.getSources()]

            it.assertItemsEqual(parser_sources, expected_sources)

    with it.having('a project file with some non-standard stuff'):
        @it.should('raise UnknownParameterError exception when an unknown parameter '
                   'is found')
        def test():
            project_filename = 'test.prj'
            config_content = [
                r'some_parm = -batch0 -batch1',
                r'batch_build_flags = -batch0 -batch1',
                r'single_build_flags = -single0 -single1',
                r'global_build_flags = -global0 -global1',
                r'builder = msim',
                r'target_dir = .build',
                r'vhdl work ./dependencies/vim-hdl-examples/another_library/foo.vhd',
            ]

            writeListToFile(project_filename, config_content)

            with it.assertRaises(hdlcc.exceptions.UnknownParameterError):
                hdlcc.config_parser.ConfigParser(project_filename)

        @it.should('assign a default value for target dir equal to the builder value')
        def test():
            project_filename = 'test.prj'
            config_content = [
                r'batch_build_flags = -batch0 -batch1',
                r'single_build_flags = -single0 -single1',
                r'global_build_flags = -global0 -global1',
                r'builder = msim',
                r'vhdl work ./dependencies/vim-hdl-examples/another_library/foo.vhd',
            ]

            writeListToFile(project_filename, config_content)

            parser = hdlcc.config_parser.ConfigParser(project_filename)
            it.assertEquals(parser.getTargetDir(), p.abspath('.msim'))

        #  @it.should('raise UnknownParameterError exception when an unknown parameter '
        #             'is found')
        #  def test():
        #      project_filename = 'foo.prj'

        #      try:
        #          parser = hdlcc.config_parser.ConfigParser(project_filename)
        #      except:
        #          pass

        #      print parser


it.createTests(globals())

