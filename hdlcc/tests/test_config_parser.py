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

# pylint: disable=function-redefined, missing-docstring, protected-access

import os
import os.path as p
import sys
import shutil
import logging

from nose2.tools import such
from nose2.tools.params import params

import six
import mock

import hdlcc
from hdlcc.config_parser import ConfigParser
from hdlcc.utils import writeListToFile, handlePathPlease

_logger = logging.getLogger(__name__)

TEST_SUPPORT_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support')

TEST_CONFIG_PARSER_SUPPORT_PATH = p.join(
    p.dirname(__file__), '..', '..', '.ci', 'test_support', 'test_config_parser')

with such.A('config parser object') as it:
    # Workaround for Python 2.x and 3.x differences
    if six.PY3:
        it.assertItemsEqual = it.assertCountEqual

    @it.has_teardown
    def teardown():
        for temp_path in ('.build', '.hdlcc'):
            temp_path = p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                         temp_path))
            if p.exists(temp_path):
                shutil.rmtree(temp_path)


    @it.should("raise UnknownParameterError exception when an unknown "
               "parameter is found")
    def test():
        with it.assertRaises(hdlcc.exceptions.UnknownParameterError):
            parser = ConfigParser(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                         'project_unknown_parm.prj'))
            parser.getSources()

    @it.should("assign a default value for target dir equal to the builder value")
    def test():
        parser = ConfigParser(
            p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'project_no_target.prj'))
        it.assertEquals(
            parser.getTargetDir(),
            p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, '.hdlcc')))

    with it.having("a standard project file"):
        @it.has_setup
        def setup():
            it.no_vunit = mock.patch('hdlcc.config_parser.foundVunit',
                                     lambda: False)
            it.no_vunit.start()

            project_filename = p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                      'standard_project_file.prj')
            it.parser = ConfigParser(project_filename)

            # Create empty files listed in the project file to avoid
            # crashing the config parser
            open(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo.v'), 'a')
            open(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'bar.sv'), 'a')

        @it.has_teardown
        def teardown():
            os.remove(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo.v'))
            os.remove(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'bar.sv'))
            it.no_vunit.stop()

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
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'sample_file.vhd'),
                                        batch_mode=False),
                set(['-s0', '-s1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'sample_package.vhd'),
                                        batch_mode=False),
                set(['-s0', '-s1', '-g0', '-g1', '-f1']))

            it.assertItemsEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'sample_testbench.vhd'),
                                        batch_mode=False),
                set(['-s0', '-s1', '-g0', '-g1', '-build-using', 'some', 'way']))

        @it.should("extract build flags for batch builds")
        def test():
            it.assertItemsEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'sample_file.vhd'),
                                        batch_mode=True),
                set(['-b0', '-b1', '-g0', '-g1', '-f0']))

            it.assertItemsEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'sample_package.vhd'),
                                        batch_mode=True),
                set(['-b0', '-b1', '-g0', '-g1', '-f1']))

        @it.should("include VHDL and Verilog sources")
        def test():
            it.assertItemsEqual(
                [p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_file.vhd')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_package.vhd')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'sample_testbench.vhd')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo.v')),
                 p.abspath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'bar.sv'))],
                [x.filename for x in it.parser.getSources()])

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
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'sample_testbench.vhd'),
                                        batch_mode=True),
                ['-g0', '-g1', '-b0', '-b1', '-build-using', 'some', 'way', ])
            it.assertEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'sample_testbench.vhd'),
                                        batch_mode=False),
                ['-g0', '-g1', '-s0', '-s1', '-build-using', 'some', 'way', ])

        @it.should("return build flags for a Verilog file")
        def test():
            it.assertEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'foo.v'),
                                        batch_mode=True),
                ['-permissive', '-some-flag', 'some', 'value', ])
            it.assertEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'foo.v'),
                                        batch_mode=False),
                ['-lint', '-hazards', '-pedanticerrors', '-some-flag',
                 'some', 'value'])

        @it.should("return build flags for a System Verilog file")
        def test():
            it.assertEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'bar.sv'),
                                        batch_mode=True),
                ['-permissive', 'some', 'sv', 'flag'])
            it.assertEqual(
                it.parser.getBuildFlags(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                               'bar.sv'),
                                        batch_mode=False),
                ['-lint', '-hazards', '-pedanticerrors', 'some', 'sv', 'flag'])

        @it.should("Match the result of ConfigParser.simpleParse")
        def test():
            target_dir, builder_name = ConfigParser.simpleParse(it.parser.filename)
            it.assertEqual(it.parser.getTargetDir(), target_dir)
            it.assertEqual(it.parser.getBuilder(), builder_name)

        @it.should("restore from cached state")
        def test():
            state = it.parser.getState()
            restored = ConfigParser.recoverFromState(state)
            it.assertEqual(it.parser, restored)

        @it.should("find the correct source defining a design unit")
        def test():
            it.assertEquals(
                [], it.parser.findSourcesByDesignUnit('some_unit', 'some_lib'))

            sources = it.parser.findSourcesByDesignUnit('sample_package')
            for source in sources:
                it.assertTrue(
                    p.exists(source.filename),
                    "Couldn't find source with path '%s'" % source.filename)

        @it.should("find the correct source defining a design unit when case "
                   "doesn't match")
        def test():
            lower_insensitive = it.parser.findSourcesByDesignUnit(
                'sample_package', case_sensitive=False)
            lower_sensitive = it.parser.findSourcesByDesignUnit(
                'sample_package', case_sensitive=True)

            upper_insensitive = it.parser.findSourcesByDesignUnit(
                'SAMPLE_PACKAGE', case_sensitive=False)
            upper_sensitive = it.parser.findSourcesByDesignUnit(
                'SAMPLE_PACKAGE', case_sensitive=True)

            it.assertNotEqual(lower_insensitive, [])
            it.assertNotEqual(lower_sensitive, [])
            it.assertItemsEqual(lower_insensitive, lower_sensitive)

            it.assertNotEqual(upper_insensitive, [])
            it.assertEquals(upper_sensitive, [])

            it.assertItemsEqual(lower_insensitive, upper_insensitive)

            for source in lower_insensitive:
                it.assertTrue(
                    p.exists(source.filename),
                    "Couldn't find source with path '%s'" % source.filename)

        @it.should("consider non absolute paths are relative to the "
                   "configuration file path")
        def test():
            file_path = p.normpath(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH, 'foo',
                                          'bar.vhd'))

            # Consider non absolute paths are relative to the configuration
            # file path
            it.assertEquals(file_path,
                            it.parser._getSourcePath(p.join('foo', 'bar.vhd')))

            # Absolute paths should refer to the current path
            it.assertEquals(
                p.abspath(p.join('foo', 'bar.vhd')),
                it.parser._getSourcePath(p.abspath(p.join('foo', 'bar.vhd'))))

    with it.having("no project file"):
        @it.should("create the object without error")
        @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
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
            it.assertEqual(it.parser.getBuildFlags(path, batch_mode=False), [])

        @it.should("return empty batch build flags for any path")
        @params(TEST_SUPPORT_PATH + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertEqual(it.parser.getBuildFlags(path, batch_mode=True), [])

        @it.should("say every path is on the project file")
        @params(TEST_SUPPORT_PATH + '/vim-hdl-examples/basic_library/clock_divider.vhd',
                'hello')
        def test(case, path):
            _logger.info("Running %s", case)
            it.assertTrue(it.parser.hasSource(path))

    with it.having("not installed VUnit"):
        @it.should("not add VUnit files to the source list")
        @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
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

            _logger.info("Sources found:")
            for source in sources:
                _logger.info("- %s", source)

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

        def getSourcesFrom(sources=None):
            prj_content = []
            if sources is None:
                sources = list(it.sources)

            for lib, path in sources:
                prj_content += ["vhdl %s %s" % (lib, path)]

            writeListToFile(it.project_filename, prj_content)

            result = {}
            for source in it.parser.getSources():
                result[source.filename] = source

            return result

        @it.has_setup
        #  @mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
        def setup():
            it.no_vunit = mock.patch('hdlcc.config_parser.foundVunit',
                                     lambda: False)
            it.no_vunit.start()

            it.project_filename = 'test.prj'
            it.lib_path = p.join(TEST_SUPPORT_PATH, 'vim-hdl-examples')
            it.sources = [
                ('work', p.join('another_library', 'foo.vhd')),
                ('work', p.join('basic_library', 'clock_divider.vhd'))]

            writeListToFile(
                it.project_filename,
                ["vhdl %s %s" % (lib, path) for lib, path in it.sources])

            it.parser = ConfigParser(it.project_filename)

        @it.has_teardown
        def teardown():
            os.remove(it.project_filename)
            it.no_vunit.stop()

        @it.should("Find only the sources given then the extra source")
        def test_01():
            _logger.info("Getting sources before adding the extra source")
            sources_pre = getSourcesFrom()

            _logger.info("Paths found:")
            for source in sources_pre:
                _logger.info(" - %s", source)

            it.assertItemsEqual(
                sources_pre.keys(),
                [handlePathPlease('another_library', 'foo.vhd'),
                 handlePathPlease('basic_library', 'clock_divider.vhd')])

            _logger.info("Adding the extra source...")

            sources_post = getSourcesFrom(
                it.sources +
                [('work', p.join('basic_library', 'very_common_pkg.vhd'))])

            _logger.info("Paths found:")
            for source in sources_post:
                _logger.info(" - %s", source)

            it.assertItemsEqual(
                sources_post.keys(),
                [handlePathPlease('another_library', 'foo.vhd'),
                 handlePathPlease('basic_library', 'clock_divider.vhd'),
                 handlePathPlease('basic_library', 'very_common_pkg.vhd')])

            # Check the files originally found weren't re-created
            for path, source in sources_pre.items():
                it.assertEqual(source, sources_post[path])

        @it.should("Update the source library if changed")
        def test_02():
            sources_pre = getSourcesFrom(
                it.sources +
                [('work', p.join('basic_library', 'very_common_pkg.vhd'))])

            sources_post = getSourcesFrom(
                it.sources +
                [('foo_lib', p.join('basic_library', 'very_common_pkg.vhd'))])

            it.assertItemsEqual(
                sources_post.keys(),
                [handlePathPlease('another_library', 'foo.vhd'),
                 handlePathPlease('basic_library', 'clock_divider.vhd'),
                 handlePathPlease('basic_library', 'very_common_pkg.vhd')])

            added_path = handlePathPlease('basic_library', 'very_common_pkg.vhd')

            added_source = sources_post[added_path]

            # Check that the sources that have been previously added are
            # the same
            for path in [
                    handlePathPlease('another_library', 'foo.vhd'),
                    handlePathPlease('basic_library', 'clock_divider.vhd')]:
                it.assertEqual(sources_pre[path], sources_post[path])

            _logger.warning("added path: %s", added_path)
            _logger.warning("sources pre:\n%s", "\n".join(sources_pre.keys()))
            _logger.warning("sources post:\n%s", "\n".join(sources_post.keys()))
            # Check that the source we changed library has changed
            it.assertNotEqual(sources_pre[added_path], sources_post[added_path])
            it.assertEqual(added_source.library, 'foo_lib')

            # Also, check that there is no extra source left behind
            it.assertEqual(len(sources_pre), len(sources_post))

        @it.should("Remove sources from config object if they were removed "
                   "from the project file")
        def test_03():
            sources_pre = getSourcesFrom(
                it.sources +
                [('work', p.join('basic_library', 'very_common_pkg.vhd'))])

            it.assertItemsEqual(
                sources_pre.keys(),
                [handlePathPlease('another_library', 'foo.vhd'),
                 handlePathPlease('basic_library', 'clock_divider.vhd'),
                 handlePathPlease('basic_library', 'very_common_pkg.vhd')])

            sources_post = getSourcesFrom()

            it.assertItemsEqual(
                sources_post.keys(),
                [handlePathPlease('another_library', 'foo.vhd'),
                 handlePathPlease('basic_library', 'clock_divider.vhd')])

    with it.having("no builder configured on the project file"):
        @it.has_setup
        def setup():
            it.patcher = mock.patch('hdlcc.config_parser.foundVunit',
                                    lambda: False)
            it.patcher.start()

        @it.has_teardown
        def teardown():
            it.patcher.stop()

        @it.should("find a builder should it pass the environment check")
        @params('MSim', 'GHDL', 'XVHDL')
        def test(case, builder):
            _logger.info("%s: Testing builder %s", case, builder)
            commands = []

            def _subprocessMocker(self, cmd_with_args, shell=False, env=None):
                commands.append(cmd_with_args)
                return []

            @staticmethod
            def isAvailable():
                return True

            patches = [
                mock.patch('hdlcc.builders.%s.checkEnvironment' % builder,
                           lambda self: setattr(self, '_version', '<foo>')),
                mock.patch('hdlcc.builders.%s._subprocessRunner' % builder,
                           _subprocessMocker),
                mock.patch('hdlcc.builders.%s.isAvailable' % builder,
                           isAvailable)]

            for patch in patches:
                patch.start()

            try:
                parser = ConfigParser(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                             'project_wo_builder_wo_target_dir.prj'))
                for cmd in commands:
                    _logger.warning('> %s', str(cmd))
                it.assertEquals(parser.getBuilder(), builder.lower())
            finally:
                for patch in patches:
                    patch.stop()

        @it.should("use fallback if no builder pass")
        def test():
            parser = ConfigParser(p.join(TEST_CONFIG_PARSER_SUPPORT_PATH,
                                         'project_wo_builder_wo_target_dir.prj'))
            it.assertEquals(parser.getBuilder(), 'fallback')

it.createTests(globals())

