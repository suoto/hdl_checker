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
import shutil as shell
import logging

from nose2.tools import such
from nose2.tools.params import params

import hdlcc
from hdlcc.utils import writeListToFile

_logger = logging.getLogger(__name__)

with such.A('config parser object') as it:

    @it.has_setup
    def setup():
        it.project_filename = 'test.prj'
        if p.exists(it.project_filename):
            os.remove(it.project_filename)

    @it.has_teardown
    def teardown():
        if p.exists(it.project_filename):
            os.remove(it.project_filename)
        if p.exists('.build'):
            shell.rmtree('.build')

        del it.project_filename
        del it.parser

    with it.having('a standard project file'):
        @it.has_setup
        def setup():
            config_content = [
                r'batch_build_flags = -b0 -b1',
                r'single_build_flags = -s0 -s1',
                r'global_build_flags = -g0 -g1',
                r'builder = msim',
                r'target_dir = .build',
                r'vhdl work ' + p.join('.ci',
                                       'vim-hdl-examples',
                                       'another_library',
                                       'foo.vhd') + ' -f0',
                r'vhdl work ' + p.abspath(p.join('.ci',
                                                 'vim-hdl-examples',
                                                 'basic_library',
                                                 'clock_divider.vhd')) + ' -f1',
                r'verilog work ' + p.join('.ci',
                                          'vim-hdl-examples',
                                          'another_library',
                                          'foo.v')
            ]

            writeListToFile(it.project_filename, config_content)

            it.parser = hdlcc.config_parser.ConfigParser(it.project_filename)

        @it.has_teardown
        def teardown():
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
                it.parser.getSingleBuildFlagsByPath(
                    p.join('.ci', 'vim-hdl-examples',
                           'another_library',
                           'foo.vhd')),
                set(['-s0', '-s1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join('.ci', 'vim-hdl-examples', 'basic_library',
                           'clock_divider.vhd')),
                set(['-s0', '-s1', '-g0', '-g1', '-f1']))

        @it.should('extract build flags for batch builds')
        def test():
            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join('.ci', 'vim-hdl-examples', 'another_library',
                           'foo.vhd')),
                set(['-b0', '-b1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join('.ci', 'vim-hdl-examples', 'basic_library',
                           'clock_divider.vhd')),
                set(['-b0', '-b1', '-g0', '-g1', '-f1']))

        @it.should('only include VHDL sources')
        def test():
            expected_sources = [p.abspath(x) \
                for x in ('.ci/vim-hdl-examples/another_library/foo.vhd',
                          '.ci/vim-hdl-examples/basic_library/clock_divider.vhd')]

            parser_sources = []

            # Don't add VUnit sources or else this test will fail
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    parser_sources += [source.filename]

            it.assertItemsEqual(parser_sources, expected_sources)

        @it.should('tell correctly if a path is on the project file')
        @params(('.ci/vim-hdl-examples/basic_library/clock_divider.vhd',
                 True),
                (p.abspath('.ci/vim-hdl-examples/basic_library/'
                           'clock_divider.vhd',),
                 True),
                ('hello', False))
        def test(case, path, result):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.hasSource(path), result)

        @it.should('keep build flags in the same order given by the user')
        def test():
            project_filename = 'test.prj'
            source = '.ci/vim-hdl-examples/another_library/foo.vhd'
            config_content = [
                r'batch_build_flags = -a -b1 --some-flag some_value',
                r'single_build_flags = --zero 0 --some-flag some_value 12',
                r'builder = msim',
                r'vhdl work ' + source,
            ]

            writeListToFile(project_filename, config_content)

            parser = hdlcc.config_parser.ConfigParser(project_filename)
            it.assertEqual(parser.getBatchBuildFlagsByPath(source),
                           ['-a', '-b1', '--some-flag', 'some_value'])
            it.assertEqual(parser.getSingleBuildFlagsByPath(source),
                           ['--zero', '0', '--some-flag', 'some_value', '12'])

    with it.having('a project file with some non-standard stuff'):
        @it.has_teardown
        def teardown():
            if p.exists('temp'):
                shell.rmtree('temp')

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
                r'vhdl work .ci/vim-hdl-examples/another_library/foo.vhd',
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
                r'vhdl work .ci/vim-hdl-examples/another_library/foo.vhd',
            ]

            writeListToFile(project_filename, config_content)

            parser = hdlcc.config_parser.ConfigParser(project_filename)
            it.assertEquals(parser.getTargetDir(), p.abspath('.msim'))

        @it.should('report target dir relative to project path')
        def test():
            if not p.exists('temp'):
                os.mkdir('temp')
            project_filename = p.join('temp', 'test.prj')
            config_content = [
                r'batch_build_flags = -batch0 -batch1',
                r'single_build_flags = -single0 -single1',
                r'global_build_flags = -global0 -global1',
                r'target_dir = .build',
                r'builder = msim',
                r'vhdl work .ci/vim-hdl-examples/another_library/foo.vhd',
            ]

            writeListToFile(project_filename, config_content)

            parser = hdlcc.config_parser.ConfigParser(project_filename)
            it.assertEquals(parser.getTargetDir(),
                            p.abspath(p.join('temp', '.build')))

    with it.having('no project file'):
        @it.should('create the object without error')
        def test():
            it.parser = hdlcc.config_parser.ConfigParser()
            it.assertIsNotNone(it.parser)

        @it.should('return fallback as selected builder')
        def test():
            it.assertEqual(it.parser.getBuilder(), 'fallback')

        @it.should('return .fallback as target directory')
        def test():
            it.assertEqual(it.parser.getTargetDir(), '.fallback')

        @it.should('return empty single build flags for any path')
        @params('.ci/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.getSingleBuildFlagsByPath(path), [])

        @it.should('return empty batch build flags for any path')
        @params('.ci/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.getBatchBuildFlagsByPath(path), [])

        @it.should('say every path is on the project file')
        @params('.ci/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertTrue(it.parser.hasSource(path))

it.createTests(globals())

