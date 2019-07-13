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

import logging
import os
import os.path as p
import shutil
import time

import mock
import six

from nose2.tools import such
from nose2.tools.params import params

import hdlcc
from hdlcc.diagnostics import (BuilderDiag, DiagType, LibraryShouldBeOmited,
                               ObjectIsNeverUsed, PathNotInProjectFile)
from hdlcc.parsers import VerilogParser, VhdlParser
from hdlcc.tests.mocks import (FailingBuilder, MSimMock, SourceMock,
                               StandaloneProjectBuilder)
from hdlcc.utils import cleanProjectCache, onCI, samefile, writeListToFile

_logger = logging.getLogger(__name__)

TEMP_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')
VIM_HDL_EXAMPLES = p.join(TEMP_PATH, "vim-hdl-examples")

with such.A("hdlcc project") as it:
    if six.PY2:
        it.assertCountEqual = it.assertItemsEqual

    def _assertSameFile(first, second):
        if not samefile(p.abspath(first), p.abspath(second)):
            it.fail("Paths '{}' and '{}' differ".format(p.abspath(first),
                                                        p.abspath(second)))

    it.assertSameFile = _assertSameFile

    def _assertMsgQueueIsEmpty(project):
        msg = []
        while not project._msg_queue.empty():
            msg += [str(project._msg_queue.get()), ]

        if msg:
            msg.insert(0, 'Message queue should be empty but has %d messages' % len(msg))
            it.fail('\n'.join(msg))

    it.assertMsgQueueIsEmpty = _assertMsgQueueIsEmpty

    it.DUMMY_PROJECT_FILE = p.join(TEMP_PATH, 'remove_me')

    @it.has_setup
    def setup():
        it.BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
        it.BUILDER_PATH = os.environ.get('BUILDER_PATH', None)
        if it.BUILDER_NAME:
            it.PROJECT_FILE = p.join(VIM_HDL_EXAMPLES, it.BUILDER_NAME + '.prj')
        else:
            it.PROJECT_FILE = None

        cleanProjectCache(it.PROJECT_FILE)

        _logger.info("Builder name: %s", it.BUILDER_NAME)
        _logger.info("Builder path: %s", it.BUILDER_PATH)

        it._patch = mock.patch('hdlcc.config_parser.foundVunit', lambda: False)
        it._patch.start()

    @it.has_teardown
    def teardown():
        cleanProjectCache(it.PROJECT_FILE)

        _logger.debug("Cleaning up test files")
        for path in (it.DUMMY_PROJECT_FILE, '.fallback', '.hdlcc',
                     'myproject.prj', 'some_file.vhd', 'xvhdl.pb',
                     '.xvhdl.init'):
            if p.exists(path):
                _logger.debug("Removing %s", path)
                if p.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)

        it._patch.stop()

    @it.should("get the path to the cache filename with no config file")
    def test():
        project = StandaloneProjectBuilder()
        it.assertIsNone(project._getCacheFilename())
        it.assertEqual(project._getCacheFilename('some_path'),
                       p.join('some_path', '.hdlcc.cache'))

    @it.should("not save anything if there is no config file")
    def test():
        def _dump(*args, **kwargs):  # pylint:disable=unused-argument
            it.fail("This shouldn't be called")

        project = StandaloneProjectBuilder()
        with mock.patch('logging.root.error', new=_dump):
            project._saveCache()

    @it.should("do nothing when trying to recover when there is not "
               "config file")
    def test():
        project = StandaloneProjectBuilder()
        project._recoverCache(project._getCacheFilename())

    @it.should("recover from cache when recreating a project object")
    @mock.patch('hdlcc.builders.getBuilderByName', new=lambda name: MSimMock)
    @mock.patch('hdlcc.config_parser.AVAILABLE_BUILDERS', [MSimMock, ])
    def test():
        # First create a project file with something in it
        project_file = p.join(TEMP_PATH, 'myproject.prj')
        writeListToFile(project_file, [])

        # Create a project object and force saving the cache
        project = StandaloneProjectBuilder(project_file)
        project._saveCache()
        it.assertTrue(p.exists(p.join(TEMP_PATH, '.hdlcc',
                                      '.hdlcc.cache')),
                      "Cache filename not found")

        # Now recreate the project and ensure it has recovered from the cache
        del project
        project = StandaloneProjectBuilder(project_file)
        time.sleep(0.5)

        found = False

        while not project._msg_queue.empty():
            severity, message = project._msg_queue.get()
            _logger.info("Message found: [%s] %s", severity, message)
            if message.startswith("Recovered cache from"):
                found = True
                break

        if p.exists('.hdlcc'):
            shutil.rmtree('.hdlcc')
        it.assertTrue(found, "Failed to warn that cache recovering has worked")
        it.assertTrue(project.builder.builder_name, 'MSimMock')

    @it.should("warn when failing to recover from cache")
    @mock.patch('hdlcc.builders.getBuilderByName', new=lambda name: MSimMock)
    @mock.patch('hdlcc.config_parser.AVAILABLE_BUILDERS', [MSimMock, ])
    def test():
        # First create a project file with something in it
        project_file = p.join(TEMP_PATH, 'myproject.prj')
        writeListToFile(project_file, [])

        project = StandaloneProjectBuilder(project_file)
        project._saveCache()
        it.assertTrue(p.exists(p.join(TEMP_PATH, '.hdlcc',
                                      '.hdlcc.cache')),
                      "Cache filename not found")

        open(p.join(TEMP_PATH, '.hdlcc', '.hdlcc.cache'), 'a').write("something\n")

        project = StandaloneProjectBuilder(project_file)
        found = False
        while not project._msg_queue.empty():
            severity, message = project._msg_queue.get()
            _logger.info("Message found: [%s] %s", severity, message)
            if message.startswith("Unable to recover cache from"):
                found = True
                break

        if p.exists('.hdlcc'):
            shutil.rmtree('.hdlcc')
        it.assertTrue(found, "Failed to warn that cache recovering has failed")
        it.assertTrue(project.builder.builder_name, 'Fallback')

    @it.should("do nothing when cleaning files without config file")
    def test():
        project = StandaloneProjectBuilder()
        it.assertIsNotNone(project.builder)
        project.clean()
        it.assertIsNone(project.builder)

    @it.should("provide a VHDL source code object given its path")
    def test():
        path = p.join(VIM_HDL_EXAMPLES, 'basic_library',
                      'very_common_pkg.vhd')
        project = StandaloneProjectBuilder()
        source, remarks = project.getSourceByPath(path)
        it.assertEquals(source, VhdlParser(path, library='undefined'))
        if project.builder.builder_name in ('msim', 'ghdl', 'xvhdl'):
            it.assertEquals(remarks,
                            [PathNotInProjectFile(p.abspath(path)), ])
        else:
            it.assertEquals(remarks, [])

    @it.should("provide a Verilog source code object given a Verilog path")
    @params(p.join(VIM_HDL_EXAMPLES, 'verilog', 'parity.v'),
            p.join(VIM_HDL_EXAMPLES, 'verilog', 'parity.sv'))
    def test(_, path):
        project = StandaloneProjectBuilder()
        source, remarks = project.getSourceByPath(path)
        it.assertEquals(source, VerilogParser(path, library='undefined'))
        if project.builder.builder_name in ('msim', 'ghdl', 'xvhdl'):
            it.assertEquals(remarks,
                            [PathNotInProjectFile(p.abspath(path)), ])
        else:
            it.assertEquals(remarks, [])

    @it.should("resolve dependencies into a list of libraries and units")
    def test():
        source = mock.MagicMock()
        source.library = 'some_lib'
        source.getDependencies = mock.MagicMock(
            return_value=[{'library' : 'some_lib',
                           'unit' : 'some_dependency'}])

        project = StandaloneProjectBuilder()
        it.assertEqual(list(project._resolveRelativeNames(source)),
                       [('some_lib', 'some_dependency')])

    @it.should("eliminate the dependency of a source on itself")
    def test():
        source = mock.MagicMock()
        source.library = 'some_lib'
        source.getDependencies = mock.MagicMock(
            return_value=[{'library' : 'some_lib',
                           'unit' : 'some_package'}])

        source.getDesignUnits = mock.MagicMock(
            return_value=[{'type' : 'package',
                           'name' : 'some_package'}])

        project = StandaloneProjectBuilder()
        it.assertEqual(list(project._resolveRelativeNames(source)), [])

    @it.should("return the correct build sequence")
    def test():
        target_source = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'target',
                           'type' : 'entity'}],
            dependencies=[{'unit' : 'direct_dependency',
                           'library' : 'some_lib'},
                          {'unit' : 'common_dependency',
                           'library' : 'some_lib'}])

        direct_dependency = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'direct_dependency',
                           'type' : 'entity'}],
            dependencies=[{'unit' : 'indirect_dependency',
                           'library' : 'some_lib'},
                          {'unit' : 'common_dependency',
                           'library' : 'some_lib'}])

        indirect_dependency = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'indirect_dependency',
                           'type' : 'package'}],
            dependencies=[{'unit' : 'indirect_dependency',
                           'library' : 'some_lib'},
                          {'unit' : 'common_dependency',
                           'library' : 'some_lib'}])

        common_dependency = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'common_dependency',
                           'type' : 'package'}],
            dependencies=[])

        project = StandaloneProjectBuilder()
        project._config._sources = {}
        for source in (target_source, direct_dependency, indirect_dependency,
                       common_dependency):
            project._config._sources[str(source)] = source
        it.assertEqual(
            [common_dependency, indirect_dependency, direct_dependency],
            project.updateBuildSequenceCache(target_source))

    @it.should("not include sources that are not dependencies")
    def test():
        target_source = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'target',
                           'type' : 'entity'}],
            dependencies=[{'unit' : 'direct_dependency',
                           'library' : 'some_lib'}])

        direct_dependency = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'direct_dependency',
                           'type' : 'entity'}],
            dependencies=[])

        not_a_dependency = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'not_a_dependency',
                           'type' : 'package'}],
            dependencies=[])

        project = StandaloneProjectBuilder()
        project._config._sources = {}
        for source in (target_source, direct_dependency, not_a_dependency):
            project._config._sources[str(source)] = source
        it.assertEqual([direct_dependency],
                       project.updateBuildSequenceCache(target_source))

    @it.should("handle cases where the source file for a dependency is not found")
    def test():
        target_source = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'target',
                           'type' : 'entity'}],
            dependencies=[{'unit' : 'direct_dependency',
                           'library' : 'some_lib'}])

        project = StandaloneProjectBuilder()
        project._config._sources = {}
        for source in (target_source, ):
            project._config._sources[str(source)] = source

        it.assertEqual([], project.updateBuildSequenceCache(target_source))

    @it.should("return empty list when the source has no dependencies")
    def test():
        target_source = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'target',
                           'type' : 'entity'}],
            dependencies=[])

        project = StandaloneProjectBuilder()
        project._config._sources = {}
        for source in (target_source, ):
            project._config._sources[str(source)] = source

        it.assertEqual([], project.updateBuildSequenceCache(target_source))

    @it.should("identify ciruclar dependencies")
    def test():
        target_source = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'target',
                           'type' : 'entity'}],
            dependencies=[{'unit' : 'direct_dependency',
                           'library' : 'some_lib'}])

        direct_dependency = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'direct_dependency',
                           'type' : 'entity'}],
            dependencies=[{'unit' : 'target',
                           'library' : 'some_lib'}])

        project = StandaloneProjectBuilder()
        project._config._sources = {}
        for source in (target_source, direct_dependency):
            project._config._sources[str(source)] = source

        it.assertEqual([direct_dependency, ],
                       project.updateBuildSequenceCache(target_source))

    @it.should("resolve conflicting dependencies by using signature")
    def test():
        target_source = SourceMock(
            library='some_lib',
            design_units=[{'name' : 'target',
                           'type' : 'entity'}],
            dependencies=[{'unit' : 'direct_dependency',
                           'library' : 'some_lib'}])

        implementation_a = SourceMock(
            library='some_lib',
            filename='implementation_a.vhd',
            design_units=[{'name' : 'direct_dependency',
                           'type' : 'entity'}],
            dependencies=[])

        implementation_b = SourceMock(
            library='some_lib',
            filename='implementation_b.vhd',
            design_units=[{'name' : 'direct_dependency',
                           'type' : 'entity'}],
            dependencies=[])

        project = StandaloneProjectBuilder()
        messages = []
        project._handleUiWarning = mock.MagicMock(    # pylint: disable=invalid-name
            side_effect=lambda x: messages.append(x)) # pylint: disable=unnecessary-lambda

        #  lambda message: messages += [message]
        project._config._sources = {}
        for source in (target_source, implementation_a, implementation_b):
            project._config._sources[str(source)] = source

        project.updateBuildSequenceCache(target_source)

        it.assertNotEqual(messages, [])

    @it.should("get builder messages by path")
    def test():
        sources = (
            SourceMock(
                library='some_lib',
                design_units=[{'name' : 'entity_a',
                               'type' : 'entity'}]),
            SourceMock(
                library='some_lib',
                design_units=[{'name' : 'entity_b',
                               'type' : 'entity'}]),
            SourceMock(
                library='some_lib',
                design_units=[{'name' : 'package_a',
                               'type' : 'package'}]),
            )

        project = StandaloneProjectBuilder()
        path = sources[0].filename
        messages = project.getMessagesByPath(path)
        if project.builder.builder_name in ('msim', 'ghdl', 'xvhdl'):
            it.assertEquals(
                messages,
                [PathNotInProjectFile(p.abspath(path)), ])
        else:
            it.assertEquals(messages, [])

    @it.should("warn when unable to recreate a builder described in cache")
    @mock.patch('hdlcc.builders.getBuilderByName', new=lambda name: FailingBuilder)
    @mock.patch('hdlcc.config_parser.AVAILABLE_BUILDERS', [FailingBuilder, ])
    def test():
        cache_content = {
            "_logger": {
                "name": "hdlcc.hdlcc_base",
                "level": 0},
            "builder": {
                "_builtin_libraries": [],
                "_added_libraries": [],
                "_logger": "hdlcc.builders.msim_mock",
                "_target_folder": "/home/souto/dev/vim-hdl/dependencies/hdlcc/.hdlcc",
                "_build_info_cache": {}},
            "_config": {
                "_parms": {
                    "target_dir": "/home/souto/dev/vim-hdl/dependencies/hdlcc/.hdlcc",
                    "builder": "msim_mock",
                    "single_build_flags": {
                        "verilog": [],
                        "vhdl": [],
                        "systemverilog": []},
                    "batch_build_flags": {
                        "verilog": [],
                        "vhdl": [],
                        "systemverilog": []},
                    "global_build_flags": {
                        "verilog": [],
                        "vhdl": [],
                        "systemverilog": []}},
                "_timestamp": 1474839625.2375762,
                "_sources": {},
                "filename": p.join(TEMP_PATH, "/myproject.prj")},
            "serializer": "json"}

        cache_path = p.join(TEMP_PATH, '.hdlcc', '.hdlcc.cache')
        if p.exists(p.dirname(cache_path)):
            shutil.rmtree(p.dirname(cache_path))

        os.mkdir(p.join(TEMP_PATH, '.hdlcc'))

        with open(cache_path, 'w') as fd:
            fd.write(repr(cache_content))

        project = StandaloneProjectBuilder()
        time.sleep(0.5)

        found = True
        while not project._msg_queue.empty():
            severity, message = project._msg_queue.get()
            _logger.info("Message found: [%s] %s", severity, message)
            if message == "Failed to create builder '%s'" % FailingBuilder.builder_name:
                found = True
                break

        it.assertTrue(found, "Failed to warn that cache recovering has failed")
        it.assertTrue(project.builder.builder_name, 'Fallback')

    with it.having('vim-hdl-examples as reference and a valid project file'):

        @it.has_setup
        def setup():
            if p.exists('modelsim.ini'):
                _logger.warning("Modelsim ini found at %s",
                                p.abspath('modelsim.ini'))
                os.remove('modelsim.ini')

            cleanProjectCache(it.PROJECT_FILE)

            builder = hdlcc.builders.getBuilderByName(it.BUILDER_NAME)

            if onCI() and it.BUILDER_NAME is not None:
                with it.assertRaises(hdlcc.exceptions.SanityCheckError):
                    builder(it.DUMMY_PROJECT_FILE)

            # Add the builder path to the environment so we can call it
            if it.BUILDER_PATH:
                it.patch = mock.patch.dict(
                    'os.environ',
                    {'PATH' : os.pathsep.join([it.BUILDER_PATH, os.environ['PATH']])})
                it.patch.start()

            try:
                builder(it.DUMMY_PROJECT_FILE)
            except hdlcc.exceptions.SanityCheckError:
                it.fail("Builder creation failed even after configuring "
                        "the builder path")

            _logger.info("Creating project builder object")
            it.project = StandaloneProjectBuilder(it.PROJECT_FILE)

        @it.has_teardown
        def teardown():
            cleanProjectCache(it.PROJECT_FILE)
            if it.BUILDER_PATH:
                it.patch.stop()

            if p.exists(it.project._config.getTargetDir()):
                shutil.rmtree(it.project._config.getTargetDir())
            del it.project

        @it.should("get messages by path")
        def test005a():
            filename = p.join(VIM_HDL_EXAMPLES, 'another_library',
                              'foo.vhd')

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesByPath(filename)

            it.assertIn(
                ObjectIsNeverUsed(
                    filename=filename,
                    line_number=43, column=12,
                    object_type='signal', object_name='neat_signal'),
                diagnostics)

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages with text")
        def test005b():
            filename = p.join(VIM_HDL_EXAMPLES, 'another_library',
                              'foo.vhd')

            original_content = open(filename, 'r').read().split('\n')

            content = '\n'.join(original_content[:43] +
                                ['signal another_signal : std_logic;'] +
                                original_content[43:])

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesWithText(filename, content)

            if diagnostics:
                _logger.debug("Records received:")
                for diagnostic in diagnostics:
                    _logger.debug("- %s", diagnostic)
            else:
                _logger.warning("No diagnostics found")

            # Check that all diagnostics point to the original filename and
            # remove them from the diagnostics so it's easier to compare
            # the remaining fields
            for diagnostic in diagnostics:
                if diagnostic.filename:
                    it.assertSameFile(filename, diagnostic.filename)

            expected = [
                ObjectIsNeverUsed(filename=p.abspath(filename), line_number=43,
                                  column=12, object_type='signal',
                                  object_name='neat_signal'),
                ObjectIsNeverUsed(filename=p.abspath(filename), line_number=44,
                                  column=8, object_type='signal',
                                  object_name='another_signal')]

            #  if it.BUILDER_NAME == 'msim':
            #      expected += [
            #          BuilderDiag(builder_name='msim',
            #                      filename=p.abspath(filename), line_number=58,
            #                      severity=DiagType.WARNING,
            #                      text="Synthesis Warning: Reset signal 'reset' "
            #                      "is not in the sensitivity list of process "
            #                      "'line__58'.")]

            it.assertCountEqual(expected, diagnostics)
            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages with text for file outside the project file")
        def test005c():
            filename = 'some_file.vhd'
            writeListToFile(filename, ["entity some_entity is end;", ])

            content = "\n".join(["library work;",
                                 "use work.all;",
                                 "entity some_entity is end;"])

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesWithText(filename, content)

            _logger.debug("Records received:")
            for diagnostic in diagnostics:
                _logger.debug("- %s", diagnostic)

            # Check that all diagnostics point to the original filename and
            # remove them from the diagnostics so it's easier to compare
            # the remaining fields
            for diagnostic in diagnostics:
                it.assertSameFile(filename, diagnostic.filename)

            if it.project.builder.builder_name in ('msim', 'ghdl', 'xvhdl'):
                expected = [
                    LibraryShouldBeOmited(library='work',
                                          filename=p.abspath(filename),
                                          column=9,
                                          line_number=1),
                    PathNotInProjectFile(p.abspath(filename)),]

                try:
                    it.assertCountEqual(expected, diagnostics)
                except:
                    _logger.warning("Expected:")
                    for exp in expected:
                        _logger.warning(exp)

                    raise

            else:
                it.assertCountEqual(
                    [LibraryShouldBeOmited(library='work',
                                           filename=p.abspath(filename),
                                           column=9,
                                           line_number=1)],
                    diagnostics)

            it.assertMsgQueueIsEmpty(it.project)


        @it.should("get updated messages")
        def test006():
            filename = p.join(VIM_HDL_EXAMPLES, 'another_library',
                              'foo.vhd')

            it.assertMsgQueueIsEmpty(it.project)

            code = open(filename, 'r').read().split('\n')

            code[28] = '-- ' + code[28]

            writeListToFile(filename, code)

            diagnostics = it.project.getMessagesByPath(filename)

            try:
                it.assertNotIn(
                    ObjectIsNeverUsed(object_type='constant',
                                      object_name='ADDR_WIDTH',
                                      line_number=29,
                                      column=14),
                    diagnostics)
            finally:
                # Remove the comment we added
                code[28] = code[28][3:]
                writeListToFile(filename, code)

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages by path of a different source")
        def test007():
            if not it.PROJECT_FILE:
                _logger.info("Requires a valid project file")
                return

            filename = p.join(VIM_HDL_EXAMPLES, 'basic_library',
                              'clock_divider.vhd')

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = []
            for diagnostic in it.project.getMessagesByPath(filename):
                it.assertSameFile(filename, diagnostic.filename)
                diagnostics += [diagnostic]

            if it.BUILDER_NAME == 'msim':
                expected_records = [
                    BuilderDiag(
                        filename=filename,
                        builder_name='msim',
                        text="Synthesis Warning: Reset signal 'reset' "
                             "is not in the sensitivity list of process "
                             "'line__58'.",
                        severity=DiagType.WARNING,
                        line_number=58)]
            elif it.BUILDER_NAME == 'ghdl':
                expected_records = []
            elif it.BUILDER_NAME == 'xvhdl':
                expected_records = []

            it.assertEqual(diagnostics, expected_records)

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("get messages from a source outside the project file")
        def test009():
            if not it.PROJECT_FILE:
                _logger.info("Requires a valid project file")
                return
            filename = 'some_file.vhd'
            writeListToFile(filename, ['library some_lib;'])

            it.assertMsgQueueIsEmpty(it.project)

            diagnostics = it.project.getMessagesByPath(filename)

            _logger.info("Records found:")
            for diagnostic in diagnostics:
                _logger.info(diagnostic)

            it.assertIn(
                PathNotInProjectFile(p.abspath(filename)),
                diagnostics)

            # The builder should find other issues as well...
            it.assertTrue(len(diagnostics) > 1,
                          "It was expected that the builder added some "
                          "message here indicating an error")

            it.assertMsgQueueIsEmpty(it.project)

        @it.should("rebuild sources when needed within the same library")
        def test010():
            if not it.PROJECT_FILE:
                _logger.info("Requires a valid project file")
                return

            filenames = (
                p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd'),
                p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clk_en_generator.vhd'))

            # Count how many messages each source has
            source_msgs = {}

            for filename in filenames:
                _logger.info("Getting messages for '%s'", filename)
                source_msgs[filename] = \
                    it.project.getMessagesByPath(filename)

            _logger.info("Changing very_common_pkg to force rebuilding "
                         "synchronizer and another one I don't recall "
                         "right now")
            very_common_pkg = p.join(VIM_HDL_EXAMPLES, 'basic_library',
                                     'very_common_pkg.vhd')

            code = open(very_common_pkg, 'r').read().split('\n')

            writeListToFile(very_common_pkg,
                            code[:22] + \
                            ["    constant TESTING : integer := 4;"] + \
                            code[22:])

            try:
                # The number of messages on all sources should not change
                it.assertEquals(it.project.getMessagesByPath(very_common_pkg), [])

                for filename in filenames:
                    if source_msgs[filename]:
                        _logger.info(
                            "Source %s had the following messages:\n%s",
                            filename, "\n".join([str(x) for x in
                                                 source_msgs[filename]]))
                    else:
                        _logger.info("Source %s has no previous messages",
                                     filename)

                    it.assertEquals(source_msgs[filename],
                                    it.project.getMessagesByPath(filename))
            finally:
                _logger.info("Restoring previous content")
                writeListToFile(very_common_pkg, code)

        @it.should("rebuild sources when changing a package on different libraries")
        def test011():
            if not it.BUILDER_NAME:
                _logger.info("Test requires a builder")
                return

            filenames = (
                p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd'),
                p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd'))

            # Count how many messages each source has
            source_msgs = {}

            for filename in filenames:
                _logger.info("Getting messages for '%s'", filename)
                source_msgs[filename] = \
                    it.project.getMessagesByPath(filename)
                it.assertNotIn(
                    DiagType.ERROR, [x.severity for x in source_msgs[filename]])

            _logger.info("Changing very_common_pkg to force rebuilding "
                         "synchronizer and another one I don't recall "
                         "right now")
            very_common_pkg = p.join(VIM_HDL_EXAMPLES, 'basic_library',
                                     'very_common_pkg.vhd')

            code = open(very_common_pkg, 'r').read().split('\n')

            writeListToFile(very_common_pkg,
                            code[:22] + \
                            ["    constant ANOTHER_TEST_NOW : integer := 1;"] + \
                            code[22:])

            try:
                # The number of messages on all sources should not change
                it.assertEquals(it.project.getMessagesByPath(very_common_pkg), [])

                for filename in filenames:

                    if source_msgs[filename]:
                        _logger.info(
                            "Source %s had the following messages:\n%s",
                            filename, "\n".join([str(x) for x in
                                                 source_msgs[filename]]))
                    else:
                        _logger.info("Source %s has no previous messages",
                                     filename)

                    it.assertEquals(source_msgs[filename],
                                    it.project.getMessagesByPath(filename))
            finally:
                _logger.info("Restoring previous content")
                writeListToFile(very_common_pkg, code)

        @it.should("rebuild sources when changing an entity on different libraries")
        def test012():
            if not it.BUILDER_NAME:
                _logger.info("Test requires a builder")
                return

            filenames = (
                p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd'),
                p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd'))
            # Count how many messages each source has
            source_msgs = {}

            for filename in filenames:
                _logger.info("Getting messages for '%s'", filename)
                source_msgs[filename] = \
                    it.project.getMessagesByPath(filename)
                it.assertNotIn(
                    DiagType.ERROR, [x.severity for x in source_msgs[filename]])

            _logger.info("Changing very_common_pkg to force rebuilding "
                         "synchronizer and another one I don't recall "
                         "right now")
            very_common_pkg = p.join(VIM_HDL_EXAMPLES, 'basic_library',
                                     'very_common_pkg.vhd')

            code = open(very_common_pkg, 'r').read().split('\n')

            writeListToFile(very_common_pkg,
                            code[:22] + \
                            ["    constant ANOTHER_TEST_NOW : integer := 1;"] + \
                            code[22:])

            try:
                # The number of messages on all sources should not change
                it.assertEquals(it.project.getMessagesByPath(very_common_pkg), [])

                for filename in filenames:

                    if source_msgs[filename]:
                        _logger.info(
                            "Source %s had the following messages:\n%s",
                            filename, "\n".join([str(x) for x in
                                                 source_msgs[filename]]))
                    else:
                        _logger.info("Source %s has no previous messages",
                                     filename)

                    it.assertEquals(source_msgs[filename],
                                    it.project.getMessagesByPath(filename))
            finally:
                _logger.info("Restoring previous content")
                writeListToFile(very_common_pkg, code)

it.createTests(globals())
