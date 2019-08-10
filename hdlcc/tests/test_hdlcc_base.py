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

import json
import logging
import os
import os.path as p
import shutil
import tempfile
#  import time

import mock
import six
#  import unittest2
#  from mock import patch
from nose2.tools import such
from nose2.tools.params import params

import hdlcc
from hdlcc.builders import Fallback
from hdlcc.diagnostics import (BuilderDiag, DependencyNotUnique, DiagType,
                               LibraryShouldBeOmited, ObjectIsNeverUsed,
                               PathNotInProjectFile)
from hdlcc.hdlcc_base import CACHE_NAME
from hdlcc.parsers import DependencySpec
from hdlcc.tests.utils import (FailingBuilder, MockBuilder, SourceMock,
                               StandaloneProjectBuilder, assertSameFile,
                               cleanProjectCache, writeListToFile)

_logger = logging.getLogger(__name__)

TEMP_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp')
CACHE_BASE_PATH = p.join(TEMP_PATH, 'cache')
VIM_HDL_EXAMPLES = p.join(TEMP_PATH, "vim-hdl-examples")

class _SourceMock(SourceMock):
    base_path = TEMP_PATH


def patchClassMap(**kwargs):
    class_map = hdlcc.serialization.CLASS_MAP.copy()
    for name, value in kwargs.items():
        class_map.update({name: value})

    return mock.patch('hdlcc.serialization.CLASS_MAP', class_map)

class ConfigParserMock(hdlcc.config_parser.ConfigParser):
    #  def __init__(self, filename):
    #      self.filename = filename
    #      self.sources = {}

    #  def getSourceByPath(self, path):
    #      return self.sources[path]

    def getBuilder(self):
        return 'MockBuilder'

    #  def getBuildFlags(self, path, batch_mode):
    #      return []

    #  def __jsonEncode__(self):
    #      return {}

    #  @classmethod
    #  def __jsonDecode__(cls, state):
    #      return super(ConfigParserMock, cls).__new__(cls)

such.unittest.TestCase.maxDiff = None

with such.A("hdlcc project") as it:
    if six.PY2:
        it.assertCountEqual = it.assertItemsEqual

    it.assertSameFile = assertSameFile(it)

    def _assertMsgQueueIsEmpty(project):
        msg = []
        while not project._msg_queue.empty():
            msg += [str(project._msg_queue.get()), ]

        if msg:
            msg.insert(0, 'Message queue should be empty but has %d messages' % len(msg))
            it.fail('\n'.join(msg))

    it.assertMsgQueueIsEmpty = _assertMsgQueueIsEmpty

    # Patch utils.getCachePath to avoid using a common directory
    @it.has_setup
    def setup():
        _logger.fatal("setup")
        it.patch_cache = mock.patch('hdlcc.hdlcc_base.getCachePath',
                                    lambda: CACHE_BASE_PATH)

        it.patch_cache.start()

    @it.has_teardown
    def teardown():
        _logger.fatal("teardown")
        it.patch_cache.stop()

    with it.having('non existing project file'):
        @it.has_setup
        def setup():
            it.project_file = 'non_existing_file'
            if p.exists(CACHE_BASE_PATH):
                shutil.rmtree(CACHE_BASE_PATH)
            it.assertFalse(p.exists(it.project_file))

        @it.should('raise exception when trying to instantiate')
        def test():
            with it.assertRaises((OSError, IOError)):
                StandaloneProjectBuilder(it.project_file)

    with it.having('no project file at all'):
        @it.has_setup
        def setup():
            if p.exists(CACHE_BASE_PATH):
                shutil.rmtree(CACHE_BASE_PATH)

            it.project = StandaloneProjectBuilder(project_file=None)

        @it.should('use fallback to Fallback builder')
        def test():
            it.assertTrue(isinstance(it.project.builder, Fallback))

        @it.should('still report static messages')
        def test():
            source = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}],
                dependencies=[
                    DependencySpec(library='work', name='foo')])

            it.assertEqual(
                it.project.getMessagesBySource(source),
                [LibraryShouldBeOmited(
                    library='work',
                    filename=p.join(TEMP_PATH, "some_lib_target.vhd"),
                    line_number=1,
                    column_number=9)])

    with it.having('an existing and valid project file'):
        @it.has_setup
        def setup():
            if p.exists(CACHE_BASE_PATH):
                shutil.rmtree(CACHE_BASE_PATH)


            it.project_file = tempfile.mktemp(prefix='project_file_', suffix='.prj', dir=TEMP_PATH)
            open(it.project_file, 'w').close()
            #  it.project_file = 'project_file'

            it.config_parser_patch = mock.patch('hdlcc.hdlcc_base.ConfigParser', ConfigParserMock)
            it.msim_mock_patch = mock.patch('hdlcc.builders.getBuilderByName', new=lambda name: MockBuilder)

            it.config_parser_patch.start()
            it.msim_mock_patch.start()

            it.project = StandaloneProjectBuilder(project_file=it.project_file)

        @it.has_teardown
        def teardown():
            it.config_parser_patch.stop()
            _logger.info("Removing project file %s", it.project_file)
            #  os.remove(it.project_file)
            it.msim_mock_patch.stop()

        @it.should('use fallback to Fallback builder')
        def test():
            it.assertTrue(isinstance(it.project.builder, MockBuilder))

        @it.should('save cache after checking a source')
        def test():
            source = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}])

            with mock.patch('hdlcc.hdlcc_base.json.dump', spec=json.dump) as func:
                it.project.getMessagesBySource(source)
                func.assert_called_once()

        @it.should('recover from cache')
        @patchClassMap(ConfigParserMock=ConfigParserMock, MockBuilder=MockBuilder)
        def test():
            source = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}])

            it.project.getMessagesBySource(source)

            del it.project

            it.project = StandaloneProjectBuilder(project_file=it.project_file)

            cache_filename = it.project._getCacheFilename()

            it.assertIn(
                ('info', 'Recovered cache from \'{}\''.format(cache_filename)),
                it.project.getUiMessages())

        @it.should("warn when failing to recover from cache")
        def test():
            # Save contents before destroying the object
            project_file = it.project.project_file
            cache_filename = it.project._getCacheFilename()

            it.assertFalse(isinstance(it.project.builder, Fallback))

            del it.project

            # Corrupt the cache file
            open(cache_filename, 'w').write("corrupted cache contents")

            # Try to recreate
            it.project = StandaloneProjectBuilder(project_file)

            if six.PY2:
                it.assertIn(
                    ('warning', "Unable to recover cache from '{}': "
                                "No JSON object could be decoded".format(cache_filename)),
                    list(it.project.getUiMessages()))
            else:
                it.assertIn(
                    ('warning', "Unable to recover cache from '{}': "
                                "Expecting value: line 1 column 1 (char 0)".format(cache_filename)),
                    list(it.project.getUiMessages()))

            it.assertTrue(isinstance(it.project.builder, MockBuilder),
                          "Builder should be MockBuilderbut it's {} instead"
                          .format(type(it.project.builder)))

        @it.should("provide a VHDL source code object given its path")
        def test():
            path = p.join(VIM_HDL_EXAMPLES, 'basic_library',
                          'very_common_pkg.vhd')

            source, remarks = it.project.getSourceByPath(path)

            it.assertSameFile(source.filename, path)
            it.assertEqual(source.library, 'undefined')
            it.assertEqual(source.filetype, 'vhdl')

            it.assertEqual(remarks,
                           [PathNotInProjectFile(p.abspath(path)), ])

        @it.should("provide a Verilog source code object given a Verilog path")
        @params(p.join(VIM_HDL_EXAMPLES, 'verilog', 'parity.v'),
                p.join(VIM_HDL_EXAMPLES, 'verilog', 'parity.sv'))
        def test(_, path):
            source, remarks = it.project.getSourceByPath(path)

            it.assertSameFile(source.filename, path)
            it.assertEqual(source.library, 'undefined')

            it.assertEqual(
                source.filetype,
                'verilog' if path.endswith('.v') else 'systemverilog')

            it.assertEqual(remarks,
                           [PathNotInProjectFile(p.abspath(path)), ])

        @it.should("resolve dependencies into a list of libraries and units")
        def test():
            source = mock.MagicMock()
            source.library = 'some_lib'
            source.getDependencies = mock.MagicMock(
                return_value=[DependencySpec(library='some_lib',
                                             name='some_dependency')])

            it.assertEqual(list(it.project._resolveRelativeNames(source)),
                           [DependencySpec(library='some_lib',
                                           name='some_dependency')])

        @it.should("eliminate the dependency of a source on itself")
        def test():
            source = mock.MagicMock()
            source.library = 'some_lib'
            source.getDependencies = mock.MagicMock(
                return_value=[DependencySpec(library='some_lib',
                                             name='some_package')])

            source.getDesignUnits = mock.MagicMock(
                return_value=[{'type' : 'package',
                               'name' : 'some_package'}])

            it.assertEqual(list(it.project._resolveRelativeNames(source)), [])

        @it.should("return the correct build sequence")
        def test():
            target_src = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}],
                dependencies=[
                    DependencySpec(library='some_lib', name='direct_dep'),
                    DependencySpec(library='some_lib', name='common_dep')])

            direct_dep = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'direct_dep',
                               'type' : 'entity'}],
                dependencies=[
                    DependencySpec(library='some_lib', name='indirect_dep'),
                    DependencySpec(library='some_lib', name='common_dep')])

            indirect_dep = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'indirect_dep',
                               'type' : 'package'}],
                dependencies=[
                    DependencySpec(library='some_lib', name='indirect_dep'),
                    DependencySpec(library='some_lib', name='common_dep')])

            common_dep = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'common_dep',
                               'type' : 'package'}])

            with mock.patch(__name__ + '.it.project._config._sources',
                            {target_src.filename :  target_src,
                             direct_dep.filename :  direct_dep,
                             indirect_dep.filename :  indirect_dep,
                             common_dep.filename :  common_dep, }):

                it.assertEqual(it.project.getBuildSequence(target_src),
                               [common_dep, indirect_dep, direct_dep])

        @it.should("not include sources that are not dependencies")
        def test():
            target_src = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}],
                dependencies=[DependencySpec(library='some_lib',
                                             name='direct_dep')])

            direct_dep = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'direct_dep',
                               'type' : 'entity'}],
                dependencies=[])

            not_a_dependency = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'not_a_dependency',
                               'type' : 'package'}],
                dependencies=[])

            with mock.patch(__name__ + '.it.project._config._sources',
                            {target_src.filename :  target_src,
                             direct_dep.filename :  direct_dep,
                             not_a_dependency.filename :  not_a_dependency}):

                it.assertEqual(it.project.getBuildSequence(target_src),
                               [direct_dep])

        @it.should("handle cases where the source file for a dependency is not found")
        def test():
            target_src = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}],
                dependencies=[DependencySpec(library='some_lib',
                                             name='direct_dep')])

            with mock.patch(__name__ + '.it.project._config._sources',
                            {target_src.filename :  target_src}):

                it.assertEqual(it.project.getBuildSequence(target_src), [])

        @it.should("return empty list when the source has no dependencies")
        def test():
            target_src = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}],
                dependencies=[])

            with mock.patch(__name__ + '.it.project._config._sources',
                            {target_src.filename :  target_src}):

                it.assertEqual(it.project.getBuildSequence(target_src), [])

        @it.should("identify ciruclar dependencies")
        def test():
            _logger.fatal("Circular dependencies")
            target_src = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}],
                dependencies=[DependencySpec(library='some_lib',
                                             name='direct_dep')])

            direct_dep = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'direct_dep',
                               'type' : 'entity'}],
                dependencies=[DependencySpec(library='some_lib',
                                             name='target')])

            with mock.patch(__name__ + '.it.project._config._sources',
                            {target_src.filename :  target_src,
                             direct_dep.filename :  direct_dep}):

                it.assertEqual(it.project.getBuildSequence(target_src),
                               [direct_dep, ])

        @it.should("resolve conflicting dependencies by using signature")
        def test():
            target_src = _SourceMock(
                library='some_lib',
                filename='target_src.vhd',
                design_units=[{'name' : 'target',
                               'type' : 'entity'}],
                dependencies=[DependencySpec(library='some_lib',
                                             name='direct_dep',
                                             locations=[('target_src.vhd', 1, 2), ])])

            implementation_a = _SourceMock(
                library='some_lib',
                filename='implementation_a.vhd',
                design_units=[{'name' : 'direct_dep',
                               'type' : 'entity'}],
                dependencies=[])

            implementation_b = _SourceMock(
                library='some_lib',
                filename='implementation_b.vhd',
                design_units=[{'name' : 'direct_dep',
                               'type' : 'entity'}],
                dependencies=[])

            #  project = StandaloneProjectBuilder()
            messages = []
            it.project._handleUiWarning = mock.MagicMock(side_effect=messages.append)

            #  lambda message: messages += [message]
            it.project._config._sources = {}
            for source in (target_src, implementation_a, implementation_b):
                it.project._config._sources[source.filename] = source

            with mock.patch(__name__ + '.it.project._config._sources',
                            {target_src.filename :  target_src,
                             implementation_a.filename :  implementation_a,
                             implementation_b.filename :  implementation_b}):

                # Make sure there was no outstanding diagnostics prior to running
                it.assertFalse(it.project._outstanding_diags,
                               "Project should not have any outstanding diagnostics")

                it.project.updateBuildSequenceCache(target_src)
                _logger.info("processing diags: %s", it.project._outstanding_diags)

                # hdlcc should flag which one it picked, although the exact one might
                # vary
                it.assertEqual(len(it.project._outstanding_diags), 1,
                               "Should have exactly one outstanding diagnostics by now")
                it.assertIn(
                    it.project._outstanding_diags.pop(),
                    [DependencyNotUnique(filename="target_src.vhd",
                                         line_number=1,
                                         column_number=2,
                                         design_unit="some_lib.direct_dep",
                                         actual=implementation_a.filename,
                                         choices=[implementation_b, ]),
                     DependencyNotUnique(filename="target_src.vhd",
                                         line_number=1,
                                         column_number=2,
                                         design_unit="some_lib.direct_dep",
                                         actual=implementation_b.filename,
                                         choices=[implementation_a, ])])

                it.assertEqual(it.project._outstanding_diags, set())

        @it.should("get builder messages by path")
        def test():
            source = _SourceMock(
                library='some_lib',
                design_units=[{'name' : 'entity_a',
                               'type' : 'entity'}],
                dependencies=[DependencySpec(library='work', name='foo')])

            with mock.patch('hdlcc.hdlcc_base.json.dump'):
                path = p.abspath(source.filename)
                messages = it.project.getMessagesByPath(path)
                it.assertCountEqual(
                    messages,
                    [LibraryShouldBeOmited(library='work',
                                           filename=path,
                                           column_number=9,
                                           line_number=1),
                     PathNotInProjectFile(path),])

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
                    "filename": p.join(TEMP_PATH, "/myproject.prj")}}

            cache_path = p.join(TEMP_PATH, '.hdlcc', CACHE_NAME)
            if p.exists(p.dirname(cache_path)):
                shutil.rmtree(p.dirname(cache_path))

            os.mkdir(p.join(TEMP_PATH, '.hdlcc'))

            with open(cache_path, 'w') as fd:
                fd.write(repr(cache_content))

            #  project = StandaloneProjectBuilder()
            #  time.sleep(0.5)

            found = True
            while not it.project._msg_queue.empty():
                severity, message = it.project._msg_queue.get()
                _logger.info("Message found: [%s] %s", severity, message)
                if message == "Failed to create builder '%s'" % FailingBuilder.builder_name:
                    found = True
                    break

            it.assertTrue(found, "Failed to warn that cache recovering has failed")
            it.assertTrue(it.project.builder.builder_name, 'Fallback')

        #  with it.having('vim-hdl-examples as reference and a valid project file'):

        #      @it.has_setup
        #      def setup():
        #          _logger.fatal("Setting up...")
        #          if p.exists('modelsim.ini'):
        #              _logger.warning("Modelsim ini found at %s",
        #                              p.abspath('modelsim.ini'))
        #              os.remove('modelsim.ini')

        #          cleanProjectCache(it.PROJECT_FILE)

        #          builder = hdlcc.builders.getBuilderByName('msim')

        #          it.assertNotEqual(builder, hdlcc.builders.Fallback)

        #          with it.assertRaises(hdlcc.exceptions.SanityCheckError):
        #              builder(it.BUILDER_TARGET_FOLDER)

        #          # Add the builder path to the environment so we can call it
        #          #  it.patch = patchBuilder
        #          #  it.patch.start()
        #          #  it.patch = mock.patch.dict(
        #          #      'os.environ',
        #          #      {'PATH' : os.pathsep.join([it.BUILDER_PATH, os.environ['PATH']])})
        #          #  it.patch.__enter__()


        #          #  with mockBuilder():

        #          #      builder = hdlcc.builders.getBuilderByName('MockBuilder')
        #          #      it.assertEqual(builder, MockBuilder)

        #          #      try:
        #          #          builder(it.BUILDER_TARGET_FOLDER)
        #          #      except hdlcc.exceptions.SanityCheckError:
        #          #          it.fail("Builder creation failed even after configuring "
        #          #                  "the builder path")

        #          #      _logger.info("Creating project builder object")
        #          #      it.project = StandaloneProjectBuilder(it.PROJECT_FILE)

        #      @it.has_teardown
        #      def teardown():
        #          cleanProjectCache(it.PROJECT_FILE)
        #          #  it.patch.__next__()
        #          #  it.patch.__exit__(None, None, None)
        #          #  it.patch.stop()

        #          if p.exists(it.project._config.getTargetDir()):
        #              shutil.rmtree(it.project._config.getTargetDir())
        #          del it.project

        #      @it.should("get messages by path")
        #      def test005a():
        #          filename = p.join(VIM_HDL_EXAMPLES, 'another_library',
        #                            'foo.vhd')

        #          it.assertMsgQueueIsEmpty(it.project)

        #          diagnostics = it.project.getMessagesByPath(filename)

        #          it.assertIn(
        #              ObjectIsNeverUsed(
        #                  filename=filename,
        #                  line_number=43, column_number=12,
        #                  object_type='signal', object_name='neat_signal'),
        #              diagnostics)

        #          it.assertMsgQueueIsEmpty(it.project)

        #      @it.should("get messages with text")
        #      def test005b():
        #          filename = p.join(VIM_HDL_EXAMPLES, 'another_library',
        #                            'foo.vhd')

        #          original_content = open(filename, 'r').read().split('\n')

        #          content = '\n'.join(original_content[:43] +
        #                              ['signal another_signal : std_logic;'] +
        #                              original_content[43:])

        #          it.assertMsgQueueIsEmpty(it.project)

        #          diagnostics = it.project.getMessagesWithText(filename, content)

        #          if diagnostics:
        #              _logger.debug("Records received:")
        #              for diagnostic in diagnostics:
        #                  _logger.debug("- %s", diagnostic)
        #          else:
        #              _logger.warning("No diagnostics found")

        #          # Check that all diagnostics point to the original filename and
        #          # remove them from the diagnostics so it's easier to compare
        #          # the remaining fields
        #          for diagnostic in diagnostics:
        #              if diagnostic.filename:
        #                  it.assertSameFile(filename, diagnostic.filename)

        #          expected = [
        #              ObjectIsNeverUsed(filename=p.abspath(filename), line_number=43,
        #                                column_number=12, object_type='signal',
        #                                object_name='neat_signal'),
        #              ObjectIsNeverUsed(filename=p.abspath(filename), line_number=44,
        #                                column_number=8, object_type='signal',
        #                                object_name='another_signal'),]


        #          #  it.assertCountEqual([hash(x) for x in expected], [hash(x) for x in diagnostics])
        #          it.assertCountEqual(expected, diagnostics)
        #          it.assertMsgQueueIsEmpty(it.project)

        #      @it.should("get messages with text for file outside the project file")
        #      def test005c():
        #          filename = p.join(TEMP_PATH, 'some_file.vhd')
        #          writeListToFile(filename, ["entity some_entity is end;", ])

        #          content = "\n".join(["library work;",
        #                               "use work.all;",
        #                               "entity some_entity is end;"])

        #          it.assertMsgQueueIsEmpty(it.project)

        #          diagnostics = it.project.getMessagesWithText(filename, content)

        #          _logger.debug("Records received:")
        #          for diagnostic in diagnostics:
        #              _logger.debug("- %s", diagnostic)

        #          # Check that all diagnostics point to the original filename and
        #          # remove them from the diagnostics so it's easier to compare
        #          # the remaining fields
        #          for diagnostic in diagnostics:
        #              it.assertSameFile(filename, diagnostic.filename)

        #          expected = [
        #              LibraryShouldBeOmited(library='work',
        #                                    filename=p.abspath(filename),
        #                                    column_number=9,
        #                                    line_number=1),
        #              PathNotInProjectFile(p.abspath(filename)),]

        #          try:
        #              it.assertCountEqual(expected, diagnostics)
        #          except:
        #              _logger.warning("Expected:")
        #              for exp in expected:
        #                  _logger.warning(exp)

        #              raise

        #          it.assertMsgQueueIsEmpty(it.project)


        #      @it.should("get updated messages")
        #      def test006():
        #          filename = p.join(VIM_HDL_EXAMPLES, 'another_library',
        #                            'foo.vhd')

        #          it.assertMsgQueueIsEmpty(it.project)

        #          code = open(filename, 'r').read().split('\n')

        #          code[28] = '-- ' + code[28]

        #          writeListToFile(filename, code)

        #          diagnostics = it.project.getMessagesByPath(filename)

        #          try:
        #              it.assertNotIn(
        #                  ObjectIsNeverUsed(object_type='constant',
        #                                    object_name='ADDR_WIDTH',
        #                                    line_number=29,
        #                                    column_number=14),
        #                  diagnostics)
        #          finally:
        #              # Remove the comment we added
        #              code[28] = code[28][3:]
        #              writeListToFile(filename, code)

        #          it.assertMsgQueueIsEmpty(it.project)

        #      @it.should("get messages by path of a different source")
        #      def test007():
        #          if not it.PROJECT_FILE:
        #              _logger.info("Requires a valid project file")
        #              return

        #          filename = p.join(VIM_HDL_EXAMPLES, 'basic_library',
        #                            'clock_divider.vhd')

        #          it.assertMsgQueueIsEmpty(it.project)

        #          diagnostics = []
        #          for diagnostic in it.project.getMessagesByPath(filename):
        #              it.assertSameFile(filename, diagnostic.filename)
        #              diagnostics += [diagnostic]

        #          #  if it.BUILDER_NAME == 'msim':
        #          #      expected_records = [
        #          #          BuilderDiag(
        #          #              filename=filename,
        #          #              builder_name='msim',
        #          #              text="Synthesis Warning: Reset signal 'reset' "
        #          #                   "is not in the sensitivity list of process "
        #          #                   "'line__58'.",
        #          #              severity=DiagType.WARNING,
        #          #              line_number=58)]
        #          #  elif it.BUILDER_NAME == 'ghdl':
        #          #      expected_records = []
        #          #  elif it.BUILDER_NAME == 'xvhdl':
        #          #      expected_records = []

        #          it.assertEqual(diagnostics, [])

        #          it.assertMsgQueueIsEmpty(it.project)

        #      @it.should("get messages from a source outside the project file")
        #      def test009():
        #          if not it.PROJECT_FILE:
        #              _logger.info("Requires a valid project file")
        #              return
        #          filename = p.join(TEMP_PATH, 'some_file.vhd')
        #          writeListToFile(filename, ['library some_lib;'])

        #          it.assertMsgQueueIsEmpty(it.project)

        #          diagnostics = it.project.getMessagesByPath(filename)

        #          _logger.info("Records found:")
        #          for diagnostic in diagnostics:
        #              _logger.info(diagnostic)

        #          it.assertIn(
        #              PathNotInProjectFile(p.abspath(filename)),
        #              diagnostics)

        #          # The builder should find other issues as well...
        #          it.assertTrue(len(diagnostics) > 1,
        #                        "It was expected that the builder added some "
        #                        "message here indicating an error")

        #          it.assertMsgQueueIsEmpty(it.project)

        #      @it.should("rebuild sources when needed within the same library")
        #      def test010():
        #          if not it.PROJECT_FILE:
        #              _logger.info("Requires a valid project file")
        #              return

        #          filenames = (
        #              p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd'),
        #              p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clk_en_generator.vhd'))

        #          # Count how many messages each source has
        #          source_msgs = {}

        #          for filename in filenames:
        #              _logger.info("Getting messages for '%s'", filename)
        #              source_msgs[filename] = \
        #                  it.project.getMessagesByPath(filename)

        #          _logger.info("Changing very_common_pkg to force rebuilding "
        #                       "synchronizer and another one I don't recall "
        #                       "right now")
        #          very_common_pkg = p.join(VIM_HDL_EXAMPLES, 'basic_library',
        #                                   'very_common_pkg.vhd')

        #          code = open(very_common_pkg, 'r').read().split('\n')

        #          writeListToFile(very_common_pkg,
        #                          code[:22] + \
        #                          ["    constant TESTING : integer := 4;"] + \
        #                          code[22:])

        #          try:
        #              # The number of messages on all sources should not change
        #              it.assertEqual(it.project.getMessagesByPath(very_common_pkg), [])

        #              for filename in filenames:
        #                  if source_msgs[filename]:
        #                      _logger.info(
        #                          "Source %s had the following messages:\n%s",
        #                          filename, "\n".join([str(x) for x in
        #                                               source_msgs[filename]]))
        #                  else:
        #                      _logger.info("Source %s has no previous messages",
        #                                   filename)

        #                  it.assertEqual(source_msgs[filename],
        #                                 it.project.getMessagesByPath(filename))
        #          finally:
        #              _logger.info("Restoring previous content")
        #              writeListToFile(very_common_pkg, code)

        #      @it.should("rebuild sources when changing a package on different libraries")
        #      def test011():
        #          #  if not it.BUILDER_NAME:
        #          #      _logger.info("Test requires a builder")
        #          #      return

        #          filenames = (
        #              p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd'),
        #              p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd'))

        #          # Count how many messages each source has
        #          source_msgs = {}

        #          for filename in filenames:
        #              _logger.info("Getting messages for '%s'", filename)
        #              source_msgs[filename] = \
        #                  it.project.getMessagesByPath(filename)
        #              it.assertNotIn(
        #                  DiagType.ERROR, [x.severity for x in source_msgs[filename]])

        #          _logger.info("Changing very_common_pkg to force rebuilding "
        #                       "synchronizer and another one I don't recall "
        #                       "right now")
        #          very_common_pkg = p.join(VIM_HDL_EXAMPLES, 'basic_library',
        #                                   'very_common_pkg.vhd')

        #          code = open(very_common_pkg, 'r').read().split('\n')

        #          writeListToFile(very_common_pkg,
        #                          code[:22] + \
        #                          ["    constant ANOTHER_TEST_NOW : integer := 1;"] + \
        #                          code[22:])

        #          try:
        #              # The number of messages on all sources should not change
        #              it.assertEqual(it.project.getMessagesByPath(very_common_pkg), [])

        #              for filename in filenames:

        #                  if source_msgs[filename]:
        #                      _logger.info(
        #                          "Source %s had the following messages:\n%s",
        #                          filename, "\n".join([str(x) for x in
        #                                               source_msgs[filename]]))
        #                  else:
        #                      _logger.info("Source %s has no previous messages",
        #                                   filename)

        #                  it.assertEqual(source_msgs[filename],
        #                                  it.project.getMessagesByPath(filename))
        #          finally:
        #              _logger.info("Restoring previous content")
        #              writeListToFile(very_common_pkg, code)

        #      @it.should("rebuild sources when changing an entity on different libraries")
        #      def test012():
        #          #  if not it.BUILDER_NAME:
        #          #      _logger.info("Test requires a builder")
        #          #      return

        #          filenames = (
        #              p.join(VIM_HDL_EXAMPLES, 'basic_library', 'clock_divider.vhd'),
        #              p.join(VIM_HDL_EXAMPLES, 'another_library', 'foo.vhd'))
        #          # Count how many messages each source has
        #          source_msgs = {}

        #          for filename in filenames:
        #              _logger.info("Getting messages for '%s'", filename)
        #              source_msgs[filename] = \
        #                  it.project.getMessagesByPath(filename)
        #              it.assertNotIn(
        #                  DiagType.ERROR, [x.severity for x in source_msgs[filename]])

        #          _logger.info("Changing very_common_pkg to force rebuilding "
        #                       "synchronizer and another one I don't recall "
        #                       "right now")
        #          very_common_pkg = p.join(VIM_HDL_EXAMPLES, 'basic_library',
        #                                   'very_common_pkg.vhd')

        #          code = open(very_common_pkg, 'r').read().split('\n')

        #          writeListToFile(very_common_pkg,
        #                          code[:22] + \
        #                          ["    constant ANOTHER_TEST_NOW : integer := 1;"] + \
        #                          code[22:])

        #          try:
        #              # The number of messages on all sources should not change
        #              it.assertEqual(it.project.getMessagesByPath(very_common_pkg), [])

        #              for filename in filenames:

        #                  if source_msgs[filename]:
        #                      _logger.info(
        #                          "Source %s had the following messages:\n%s",
        #                          filename, "\n".join([str(x) for x in
        #                                               source_msgs[filename]]))
        #                  else:
        #                      _logger.info("Source %s has no previous messages",
        #                                   filename)

        #                  it.assertEqual(source_msgs[filename],
        #                                  it.project.getMessagesByPath(filename))
        #          finally:
        #              _logger.info("Restoring previous content")
        #              writeListToFile(very_common_pkg, code)

it.createTests(globals())
