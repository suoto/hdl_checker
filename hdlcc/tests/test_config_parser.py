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
import sys
import os.path as p
import shutil as shell
import logging

from nose2.tools import such
from nose2.tools.params import params

import hdlcc
from hdlcc.utils import writeListToFile

_logger = logging.getLogger(__name__)

HDLCC_CI = os.environ['HDLCC_CI']

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
                r'vhdl work ' + p.join(HDLCC_CI,
                                       'vim-hdl-examples',
                                       'another_library',
                                       'foo.vhd') + ' -f0',
                r'vhdl work ' + p.abspath(p.join(HDLCC_CI,
                                                 'vim-hdl-examples',
                                                 'basic_library',
                                                 'clock_divider.vhd')) + ' -f1',
                r'verilog work ' + p.join(HDLCC_CI,
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
                    p.join(HDLCC_CI, 'vim-hdl-examples',
                           'another_library',
                           'foo.vhd')),
                set(['-s0', '-s1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join(HDLCC_CI, 'vim-hdl-examples', 'basic_library',
                           'clock_divider.vhd')),
                set(['-s0', '-s1', '-g0', '-g1', '-f1']))

        @it.should('extract build flags for batch builds')
        def test():
            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join(HDLCC_CI, 'vim-hdl-examples', 'another_library',
                           'foo.vhd')),
                set(['-b0', '-b1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join(HDLCC_CI, 'vim-hdl-examples', 'basic_library',
                           'clock_divider.vhd')),
                set(['-b0', '-b1', '-g0', '-g1', '-f1']))

        @it.should('only include VHDL sources')
        def test():
            expected_sources = [p.abspath(x) \
                for x in (HDLCC_CI + '/vim-hdl-examples/another_library/foo.vhd',
                          HDLCC_CI + '/vim-hdl-examples/basic_library/clock_divider.vhd')]

            parser_sources = []

            # Don't add VUnit sources or else this test will fail
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    parser_sources += [source.filename]

            it.assertItemsEqual(parser_sources, expected_sources)

        @it.should('tell correctly if a path is on the project file')
        @params((HDLCC_CI + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                 True),
                (p.abspath(HDLCC_CI + '/vim-hdl-examples/basic_library/'
                           'clock_divider.vhd',),
                 True),
                ('hello', False))
        def test(case, path, result):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.hasSource(path), result)

        @it.should('keep build flags in the same order given by the user')
        def test():
            project_filename = 'test.prj'
            source = HDLCC_CI + '/vim-hdl-examples/another_library/foo.vhd'
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
                r'vhdl work ' + HDLCC_CI + '/vim-hdl-examples/another_library/foo.vhd',
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
                r'vhdl work ' + HDLCC_CI + '/vim-hdl-examples/another_library/foo.vhd',
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
                r'vhdl work ' + HDLCC_CI + '/vim-hdl-examples/another_library/foo.vhd',
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
        @params(HDLCC_CI + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.getSingleBuildFlagsByPath(path), [])

        @it.should('return empty batch build flags for any path')
        @params(HDLCC_CI + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.getBatchBuildFlagsByPath(path), [])

        @it.should('say every path is on the project file')
        @params(HDLCC_CI + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertTrue(it.parser.hasSource(path))

    with it.having('not installed VUnit'):
        @it.has_setup
        def setup():
            import hdlcc.config_parser as cp
            it.config_parser = cp
            it.config_parser._HAS_VUNIT = False

        @it.should('not add VUnit files to the source list')
        def test():
            # We'll add no project file, so the only sources that should
            # be fond are VUnit's files
            sources = it.config_parser.ConfigParser().getSources()

            it.assertEquals(
                sources, [], "We shouldn't find any source but found %s" %
                ", ".join([x.filename for x in sources]))

    with it.having('VUnit installed'):
        @it.has_setup
        def setup():
            try:
                import vunit # pylint: disable=unused-variable
            except ImportError:
                it.fail("Couldn't import vunit")

        @it.should('add VUnit files to the source list')
        def test():
            # We'll add no project file, so the only sources that should
            # be fond are VUnit's files
            it.assertIn('vunit', sys.modules)
            sources = hdlcc.config_parser.ConfigParser().getSources()

            vunit_files = 0
            for source in sources:
                if 'vunit' in source.filename.lower():
                    vunit_files += 1

            it.assertEqual(len(sources), vunit_files,
                           "We should only find VUnit files")

    with it.having("a project file constantly updated"):
        @it.has_setup
        def setup():
            it.lib_path = p.join(HDLCC_CI, 'vim-hdl-examples')
            it.config_content = [
                r'vhdl work ' + p.join(it.lib_path, 'another_library',
                                       'foo.vhd'),
                r'vhdl work ' + p.join(it.lib_path, 'basic_library',
                                       'clock_divider.vhd'),
            ]

            writeListToFile(it.project_filename, it.config_content)
            it.parser = hdlcc.config_parser.ConfigParser(it.project_filename)

        @it.should("Find only the sources given then the extra source")
        def test():
            sources_pre = {}
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    sources_pre[source.filename] = source

            it.assertItemsEqual(
                sources_pre.keys(),
                [p.join(it.lib_path, 'another_library', 'foo.vhd'),
                 p.join(it.lib_path, 'basic_library', 'clock_divider.vhd'),])

            # Add an extra file
            writeListToFile(
                it.project_filename,
                it.config_content + [r'vhdl work ' + p.join(it.lib_path, 'basic_library',
                                                            'very_common_pkg.vhd'), ])

            sources_post = {}
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    sources_post[source.filename] = source

            it.assertItemsEqual(
                sources_post.keys(),
                [p.join(it.lib_path, 'another_library', 'foo.vhd'),
                 p.join(it.lib_path, 'basic_library', 'clock_divider.vhd'),
                 p.join(it.lib_path, 'basic_library', 'very_common_pkg.vhd'), ])

            # Check the files originally found weren't re-created
            for path, source in sources_pre.items():
                it.assertEqual(source, sources_post[path])

        @it.should("Update the source library if changed")
        def test():
            sources_pre = {}
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    sources_pre[source.filename] = source

            # Add an extra file
            writeListToFile(
                it.project_filename,
                it.config_content + [r'vhdl foo_lib ' + p.join(it.lib_path, 'basic_library',
                                                               'very_common_pkg.vhd'), ])

            sources_post = {}
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    sources_post[source.filename] = source

            it.assertItemsEqual(
                sources_post.keys(),
                [p.join(it.lib_path, 'another_library', 'foo.vhd'),
                 p.join(it.lib_path, 'basic_library', 'clock_divider.vhd'),
                 p.join(it.lib_path, 'basic_library', 'very_common_pkg.vhd'), ])

            added_path = p.join(it.lib_path, 'basic_library',
                                'very_common_pkg.vhd')

            added_source = sources_post[added_path]

            # Check that the sources that have been previously added are
            # the same
            for path in [p.join(it.lib_path, 'another_library', 'foo.vhd'),
                         p.join(it.lib_path, 'basic_library', 'clock_divider.vhd')]:
                it.assertEqual(sources_pre[path], sources_post[path])

            # Check that the source we changed library has changed
            it.assertNotEqual(sources_pre[added_path], sources_post[added_path])
            it.assertEqual(added_source.library, 'foo_lib')

            # Also, check that there is no extra source left behind
            it.assertEqual(len(sources_pre), len(sources_post))

it.createTests(globals())

