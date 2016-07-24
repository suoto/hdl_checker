# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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
import sys
import shutil
import logging

import mock
from nose2.tools import such
from nose2.tools.params import params

import hdlcc
from hdlcc.config_parser import ConfigParser
from hdlcc.utils import writeListToFile

_logger = logging.getLogger(__name__)

TEST_SUPPORT_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support')

TEST_CONFIG_PARSER_SUPPORT_PATH = p.join(
    p.dirname(__file__), '..', '..', '.ci', 'test_support', 'test_config_parser')

with such.A('config parser object') as it:
    @it.should("raise UnknownParameterError exception when an unknown "
               "parameter is found")
    def test():
        with it.assertRaises(hdlcc.exceptions.UnknownParameterError):
            ConfigParser(
                p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'project_unknown_parm.prj'))

    @it.should("assign a default value for target dir equal to the builder value")
    def test():
        parser = ConfigParser(
            p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'project_no_target.prj'))
        it.assertEquals(
            parser.getTargetDir(),
            p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, '.hdlcc')))

    with it.having("a standard project file"):
        @it.has_setup
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def setup():
            project_filename = p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                      'standard_project_file.prj')
            it.parser = ConfigParser(project_filename)

        @it.has_teardown
        def teardown():
            target_dir = p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                          '.build'))
            if p.exists(target_dir):
                _logger.info("Removing target dir '%s'", target_dir)
                shutil.rmtree(target_dir)
            else:
                _logger.info("Target dir '%s' not found", target_dir)

        @it.should("extract builder")
        def test():
            it.assertEqual(it.parser.getBuilder(), 'msim')

        @it.should("extract target dir")
        def test():
            it.assertTrue(p.isabs(it.parser.getTargetDir()))
            it.assertEqual(
                it.parser.getTargetDir(),
                p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, '.build')))

        @it.should("extract build flags for single build")
        def test():
            it.assertItemsEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_file.vhd')),
                set(['-s0', '-s1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_package.vhd')),
                set(['-s0', '-s1', '-g0', '-g1', '-f1']))

            it.assertItemsEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_testbench.vhd')),
                set(['-s0', '-s1', '-g0', '-g1', '-build-using', 'some', 'way']))

        @it.should("extract build flags for batch builds")
        def test():
            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_file.vhd')),
                set(['-b0', '-b1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_package.vhd')),
                set(['-b0', '-b1', '-g0', '-g1', '-f1']))

        @it.should("include VHDL and Verilog sources")
        def test():
            it.assertItemsEqual(
                [x.filename for x in it.parser.getSources()],
                [p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_file.vhd')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_package.vhd')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_testbench.vhd')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo.v')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'bar.sv'))])

        @it.should("tell correctly if a path is on the project file")
        @params((p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_file.vhd'), True),
                (p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo.v'), True),
                (p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'bar.sv'), True),
                (p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'hello_world.vhd'), False))
        def test(case, path, result):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.hasSource(path), result)

        @it.should("return build flags for a VHDL file")
        def test():
            it.assertEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_testbench.vhd')),
                ['-g0', '-g1', '-b0', '-b1', '-build-using', 'some', 'way', ])
            it.assertEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_testbench.vhd')),
                ['-g0', '-g1', '-s0', '-s1', '-build-using', 'some', 'way', ])

        @it.should("return build flags for a Verilog file")
        def test():
            it.assertEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo.v')),
                ['-permissive', '-some-flag', 'some', 'value', ])
            it.assertEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo.v')),
                ['-lint', '-hazards', '-pedanticerrors', '-some-flag',
                 'some', 'value'])

        @it.should("return build flags for a System Verilog file")
        def test():
            it.assertEqual(
                it.parser.getBatchBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'bar.sv')),
                ['-permissive', 'some', 'sv', 'flag'])
            it.assertEqual(
                it.parser.getSingleBuildFlagsByPath(
                    p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'bar.sv')),
                ['-lint', '-hazards', '-pedanticerrors', 'some', 'sv', 'flag'])

        @it.should("Match the result of ConfigParser.simpleParse")
        def test():
            target_dir, builder_name = ConfigParser.simpleParse(it.parser.filename)
            it.assertEqual(it.parser.getTargetDir(), target_dir)
            it.assertEqual(it.parser.getBuilder(), builder_name)

        @it.should("get sources' paths")
        def test():
            it.assertListEqual(
                [x.filename for x in it.parser.getSources()],
                it.parser.getSourcesPaths())

        @it.should("restore from cached state")
        def test():
            state = it.parser.getState()
            restored = ConfigParser.recoverFromState(state)
            it.assertEqual(it.parser, restored)

    with it.having("no project file"):
        @it.should("create the object without error")
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def test():
            it.parser = ConfigParser()
            it.assertIsNotNone(it.parser)

        @it.should("return fallback as selected builder")
        def test():
            it.assertEqual(it.parser.getBuilder(), 'fallback')

        @it.should("return .fallback as target directory")
        def test():
            it.assertEqual(it.parser.getTargetDir(), '.fallback')

        @it.should("return empty single build flags for any path")
        @params(TEST_SUPPORT_PATH + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.getSingleBuildFlagsByPath(path), [])

        @it.should("return empty batch build flags for any path")
        @params(TEST_SUPPORT_PATH + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.getBatchBuildFlagsByPath(path), [])

        @it.should("say every path is on the project file")
        @params(TEST_SUPPORT_PATH + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertTrue(it.parser.hasSource(path))

    with it.having("not installed VUnit"):
        @it.should("not add VUnit files to the source list")
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def test():
            # We'll add no project file, so the only sources that should
            # be fond are VUnit's files
            project_filename = p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                      'builder_only_project.prj')
            parser = ConfigParser(project_filename)
            sources = parser.getSources()

            it.assertEquals(
                sources, [], "We shouldn't find any source but found %s" %
                ", ".join([x.filename for x in sources]))

    with it.having("VUnit installed"):
        @it.has_setup
        def setup():
            try:
                import vunit # pylint: disable=unused-variable
            except ImportError:
                it.fail("Couldn't import vunit")

        @it.should("add only VUnit VHDL files to the source list if the "
                   'builder only supports VHDL')
        def test():
            # We'll add no project file, so the only sources that should
            # be fond are VUnit's files
            it.assertIn('vunit', sys.modules)
            project_filename = p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                      'builder_only_project.prj')
            with mock.patch('hdlcc.builders.MSim.file_types',
                            new_callable=mock.PropertyMock,
                            return_value=('vhdl', )):
                parser = ConfigParser(project_filename)
            sources = parser.getSources()

            vunit_files = 0
            for source in sources:
                if 'vunit' in source.filename.lower():
                    vunit_files += 1

            it.assertEqual(len(sources), vunit_files,
                           "We should only find VUnit files")

            # Check that we find no verilog or systemverilog files
            for filetype in ('verilog', 'systemverilog'):
                it.assertNotIn(filetype, [x.filetype for x in sources],
                               "We should only find VUnit VHDL files")

        @it.should("add VUnit VHDL and SystemVerilog files to the source "
                   "list if the builder supports them")
        def test():
            # We'll add no project file, so the only sources that should
            # be fond are VUnit's files
            it.assertIn('vunit', sys.modules)
            project_filename = p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                      'builder_only_project.prj')
            with mock.patch('hdlcc.builders.MSim.file_types',
                            new_callable=mock.PropertyMock,
                            return_value=('vhdl', 'systemverilog')):
                parser = ConfigParser(project_filename)
            sources = parser.getSources()

            vunit_files = 0
            for source in sources:
                if 'vunit' in source.filename.lower():
                    vunit_files += 1

            it.assertEqual(len(sources), vunit_files,
                           "We should only find VUnit files")

            for filetype in ('vhdl', 'systemverilog'):
                it.assertIn(filetype, [x.filetype for x in sources],
                            "We should find %s files" % filetype)

    with it.having("a project file constantly updated"):
        @it.has_setup
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def setup():
            it.project_filename = 'test.prj'
            it.lib_path = p.join(TEST_SUPPORT_PATH, 'vim-hdl-examples')
            it.config_content = [
                r'vhdl work ' + p.normpath(p.join(
                    it.lib_path, 'another_library', 'foo.vhd')),
                r'vhdl work ' + p.normpath(p.join(
                    it.lib_path, 'basic_library', 'clock_divider.vhd')),]

            writeListToFile(it.project_filename, it.config_content)
            it.parser = ConfigParser(it.project_filename)

        @it.has_teardown
        def teardown():
            os.remove(it.project_filename)

        @it.should("Find only the sources given then the extra source")
        def test_01():
            _logger.info("Getting sources before adding the extra source")
            sources_pre = {}
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    sources_pre[source.filename] = source

            _logger.info("Paths found:")
            for source in sources_pre.keys():
                _logger.info(" - %s", source)

            it.assertItemsEqual(
                sources_pre.keys(),
                [p.normpath(p.join(it.lib_path, 'another_library', 'foo.vhd')),
                 p.normpath(p.join(it.lib_path, 'basic_library', 'clock_divider.vhd')),])


            _logger.info("Adding the extra source...")
            # Add an extra file
            writeListToFile(
                it.project_filename,
                it.config_content + [r'vhdl work ' + p.normpath(p.join(
                    it.lib_path, 'basic_library', 'very_common_pkg.vhd'))])

            sources_post = {}
            for source in it.parser.getSources():
                if 'vunit' not in source.filename:
                    sources_post[source.filename] = source

            _logger.info("Paths found:")
            for source in sources_post.keys():
                _logger.info(" - %s", source)


            it.assertItemsEqual(
                sources_post.keys(),
                [p.normpath(p.join(it.lib_path, 'another_library', 'foo.vhd')),
                 p.normpath(p.join(it.lib_path, 'basic_library', 'clock_divider.vhd')),
                 p.normpath(p.join(it.lib_path, 'basic_library', 'very_common_pkg.vhd')),])

            # Check the files originally found weren't re-created
            for path, source in sources_pre.items():
                it.assertEqual(source, sources_post[path])

        @it.should("Update the source library if changed")
        def test_02():
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
                [p.normpath(p.join(it.lib_path, 'another_library', 'foo.vhd')),
                 p.normpath(p.join(it.lib_path, 'basic_library', 'clock_divider.vhd')),
                 p.normpath(p.join(it.lib_path, 'basic_library', 'very_common_pkg.vhd')), ])

            added_path = p.normpath(p.join(it.lib_path, 'basic_library',
                                           'very_common_pkg.vhd'))

            added_source = sources_post[added_path]

            # Check that the sources that have been previously added are
            # the same
            for path in [
                    p.normpath(p.join(it.lib_path, 'another_library', 'foo.vhd')),
                    p.normpath(p.join(it.lib_path, 'basic_library', 'clock_divider.vhd'))]:
                it.assertEqual(sources_pre[path], sources_post[path])

            # Check that the source we changed library has changed
            it.assertNotEqual(sources_pre[added_path], sources_post[added_path])
            it.assertEqual(added_source.library, 'foo_lib')

            # Also, check that there is no extra source left behind
            it.assertEqual(len(sources_pre), len(sources_post))

it.createTests(globals())

