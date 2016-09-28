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
import shutil
import time
import logging
import unittest

from nose2.tools import such
from nose2.tools.params import params

import mock

import hdlcc
from hdlcc.utils import (writeListToFile,
                         addToPath,
                         removeFromPath,
                         samefile,
                         onCI,
                         cleanProjectCache)

from hdlcc.tests.mocks import (StandaloneProjectBuilder,
                               MSimMock,
                               FailingBuilder,
                               SourceMock)

from hdlcc.parsers import VerilogParser, VhdlParser

_logger = logging.getLogger(__name__)

BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = p.expandvars(os.environ.get('BUILDER_PATH', \
                            p.expanduser("~/ghdl/bin/")))

TEST_SUPPORT_PATH = p.join(p.dirname(__file__), '..', '..', '.ci', 'test_support')
VIM_HDL_EXAMPLES_PATH = p.join(TEST_SUPPORT_PATH, "vim-hdl-examples")

if BUILDER_NAME is not None:
    PROJECT_FILE = p.join(VIM_HDL_EXAMPLES_PATH, BUILDER_NAME + '.prj')
else:
    PROJECT_FILE = None

with such.A("hdlcc project with '%s' builder" % str(BUILDER_NAME)) as it:

    it.DUMMY_PROJECT_FILE = p.join(os.curdir, 'remove_me')

    @it.has_setup
    def setup():
        cleanProjectCache(PROJECT_FILE)

        _logger.info("Builder name: %s", BUILDER_NAME)
        _logger.info("Builder path: %s", BUILDER_PATH)

    @it.has_teardown
    def teardown():
        cleanProjectCache(PROJECT_FILE)
        if p.exists(it.DUMMY_PROJECT_FILE):
            shutil.rmtree(it.DUMMY_PROJECT_FILE)

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
    @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
    def test():
        # First create a project file with something in it
        project_file = 'myproject.prj'
        writeListToFile(project_file, [])

        # Create a project object and force saving the cache
        project = StandaloneProjectBuilder(project_file)
        project._saveCache()
        it.assertTrue(p.exists(p.join('.hdlcc', '.hdlcc.cache')),
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
    @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
    def test():
        # First create a project file with something in it
        project_file = 'myproject.prj'
        writeListToFile(project_file, [])

        project = StandaloneProjectBuilder(project_file)
        project._saveCache()
        it.assertTrue(p.exists(p.join('.hdlcc', '.hdlcc.cache')),
                      "Cache filename not found")

        open(p.join('.hdlcc', '.hdlcc.cache'), 'a').write("something\n")

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
        path = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
                      'very_common_pkg.vhd')
        project = StandaloneProjectBuilder()
        source, remarks = project._getSourceByPath(path)
        it.assertEquals(source, VhdlParser(path, library='undefined'))
        it.assertEquals(
            remarks,
            [{'checker'        : 'hdlcc',
              'line_number'    : '',
              'column'         : '',
              'filename'       : '',
              'error_number'   : '',
              'error_type'     : 'W',
              'error_message'  : 'Path "%s" not found in project file' %
                                 p.abspath(path)}])

    @it.should("provide a Verilog source code object given a Verilog path")
    @params(p.join(VIM_HDL_EXAMPLES_PATH, 'verilog', 'parity.v'),
            p.join(VIM_HDL_EXAMPLES_PATH, 'verilog', 'parity.sv'))
    def test(_, path):
        project = StandaloneProjectBuilder()
        source, remarks = project._getSourceByPath(path)
        it.assertEquals(source, VerilogParser(path, library='undefined'))
        it.assertEquals(
            remarks,
            [{'checker'        : 'hdlcc',
              'line_number'    : '',
              'column'         : '',
              'filename'       : '',
              'error_number'   : '',
              'error_type'     : 'W',
              'error_message'  : 'Path "%s" not found in project file' %
                                 p.abspath(path)}])

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

    @it.should("sort build messages")
    def test():
        records = []
        for error_type in ('E', 'W'):
            for line_number in (10, 11):
                for error_number in (12, 13):
                    records += [{'error_type' : error_type,
                                 'line_number' : line_number,
                                 'error_number' : error_number}]

        it.assertEqual(
            StandaloneProjectBuilder._sortBuildMessages(records),
            [{'error_type': 'E', 'line_number': 10, 'error_number': 12},
             {'error_type': 'E', 'line_number': 10, 'error_number': 13},
             {'error_type': 'E', 'line_number': 11, 'error_number': 12},
             {'error_type': 'E', 'line_number': 11, 'error_number': 13},
             {'error_type': 'W', 'line_number': 10, 'error_number': 12},
             {'error_type': 'W', 'line_number': 10, 'error_number': 13},
             {'error_type': 'W', 'line_number': 11, 'error_number': 12},
             {'error_type': 'W', 'line_number': 11, 'error_number': 13}])

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
            project.getBuildSequence(target_source))

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
                       project.getBuildSequence(target_source))

    @it.should("fail if the source file for a dependency is not found")
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

        with it.assertRaises(hdlcc.exceptions.DesignUnitNotFoundError):
            project.getBuildSequence(target_source)

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

        it.assertEqual([], project.getBuildSequence(target_source))

    @it.should("catch ciruclar dependencies")
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

        with it.assertRaises(hdlcc.exceptions.CircularDependencyFound):
            project.getBuildSequence(target_source)

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

        project.getBuildSequence(target_source)

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
        project._config._sources = {}
        for source in sources:
            project._config._sources[source.filename] = source

        path = sources[0].filename
        it.assertEquals(
            project._getBuilderMessages(path),
            [{'checker'        : 'hdlcc',
              'line_number'    : '',
              'column'         : '',
              'filename'       : '',
              'error_number'   : '',
              'error_type'     : 'W',
              'error_message'  : 'Path "%s" not found in project file' %
                                 p.abspath(path)}])


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
                "filename": "/home/souto/dev/vim-hdl/dependencies/hdlcc/myproject.prj"},
            "serializer": "json"}

        cache_path = p.join('.hdlcc', '.hdlcc.cache')
        if p.exists(p.dirname(cache_path)):
            shutil.rmtree(p.dirname(cache_path))

        os.mkdir('.hdlcc')

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

    #  with it.having('vim-hdl-examples as reference and a valid project file'):

    #      @it.has_setup
    #      def setup():
    #          if p.exists('modelsim.ini'):
    #              _logger.warning("Modelsim ini found at %s",
    #                              p.abspath('modelsim.ini'))
    #              os.remove('modelsim.ini')

    #          #  hdlcc.HdlCodeCheckerBase.cleanProjectCache(PROJECT_FILE)
    #          cleanProjectCache(PROJECT_FILE)

    #          builder = hdlcc.builders.getBuilderByName(BUILDER_NAME)

    #          if onCI() and BUILDER_NAME is not None:
    #              with it.assertRaises(hdlcc.exceptions.SanityCheckError):
    #                  builder(it.DUMMY_PROJECT_FILE)

    #          it.original_env = os.environ.copy()

    #          addToPath(BUILDER_PATH)

    #          it.assertNotEquals(os.environ['PATH'], it.original_env['PATH'])

    #          try:
    #              builder(it.DUMMY_PROJECT_FILE)
    #          except hdlcc.exceptions.SanityCheckError:
    #              it.fail("Builder creation failed even after configuring "
    #                      "the builder path")

    #          _logger.info("Creating project builder object")
    #          it.project = StandaloneProjectBuilder(PROJECT_FILE)

    #      @it.has_teardown
    #      def teardown():
    #          #  hdlcc.HdlCodeCheckerBase.cleanProjectCache(PROJECT_FILE)
    #          cleanProjectCache(PROJECT_FILE)
    #          removeFromPath(BUILDER_PATH)
    #          target_dir = it.project._config.getTargetDir()
    #          if p.exists(target_dir):
    #              shutil.rmtree(target_dir)
    #          if p.exists('modelsim.ini'):
    #              _logger.warning("Modelsim ini found at %s",
    #                              p.abspath('modelsim.ini'))
    #              os.remove('modelsim.ini')
    #          del it.project

        #  @it.should("build project by dependency in background")
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test001():
        #      _logger.info("Checking if msg queue is empty")
        #      it.assertTrue(it.project._msg_queue.empty())
        #      it.project.buildByDependency()
        #      it.assertFalse(it.project.hasFinishedBuilding())

        #  @it.should("notify if a build is already running")
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test002():
        #      it.project.buildByDependency()
        #      while it.project._msg_queue.empty():
        #          time.sleep(0.1)
        #      messages = []
        #      while not it.project._msg_queue.empty():
        #          messages.append(it.project._msg_queue.get())

        #      try:
        #          it.assertIn(('info', 'Build thread is already running'),
        #                      messages)
        #      except:
        #          it.project.waitForBuild()
        #          raise

        #  @it.should("warn when trying to build a source before the build "
        #             'thread completes')
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test003():
        #      filename = p.join(VIM_HDL_EXAMPLES_PATH, 'another_library',
        #                        'foo.vhd')

        #      it.assertTrue(it.project._msg_queue.empty())

        #      it.project.getMessagesByPath(filename)

        #      _logger.info("Waiting for any message to arrive on message queue")
        #      for _ in range(50):
        #          if it.project._msg_queue.empty():
        #              break
        #          time.sleep(0.1)

        #      messages = []
        #      while not it.project._msg_queue.empty():
        #          message = it.project._msg_queue.get()
        #          _logger.info("Appending message '%s'", message)
        #          messages.append(message)

        #      try:
        #          it.assertIn(('warning', "Project hasn't finished building, "
        #                                  "try again after it finishes."),
        #                      messages)
        #          _logger.info("OK, the mesage was found")
        #      finally:
        #          _logger.warning("Waiting until the project finishes building")
        #          it.project.waitForBuild()

        #  @it.should("wait until build has finished")
        #  def test004():
        #      it.project.waitForBuild()

        #  @it.should("get messages by path")
        #  def test005():
        #      filename = p.join(VIM_HDL_EXAMPLES_PATH, 'another_library',
        #                        'foo.vhd')

        #      it.assertTrue(it.project._msg_queue.empty())

        #      records = it.project.getMessagesByPath(filename)

        #      it.assertIn(
        #          {'error_subtype' : 'Style',
        #           'line_number'   : 43,
        #           'checker'       : 'HDL Code Checker/static',
        #           'error_message' : "signal 'neat_signal' is never used",
        #           'column'        : 12,
        #           'error_type'    : 'W',
        #           'error_number'  : '0',
        #           'filename'      : None},
        #          records)

        #      it.assertTrue(it.project._msg_queue.empty())

        #  @it.should("get updated messages")
        #  def test006():
        #      filename = p.join(VIM_HDL_EXAMPLES_PATH, 'another_library',
        #                        'foo.vhd')

        #      it.assertTrue(it.project._msg_queue.empty())

        #      code = open(filename, 'r').read().split('\n')

        #      code[28] = '-- ' + code[28]

        #      writeListToFile(filename, code)

        #      records = it.project.getMessagesByPath(filename)

        #      try:
        #          it.assertNotIn(
        #              {'error_subtype' : 'Style',
        #               'line_number'   : 29,
        #               'checker'       : 'HDL Code Checker/static',
        #               'error_message' : "constant 'ADDR_WIDTH' is never used",
        #               'column'        : 14,
        #               'error_type'    : 'W',
        #               'error_number'  : '0',
        #               'filename'      : None},
        #              records)
        #      finally:
        #          # Remove the comment we added
        #          code[28] = code[28][3:]
        #          writeListToFile(filename, code)

        #      it.assertTrue(it.project._msg_queue.empty())

        #  @it.should("get messages by path of a different source")
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test007():
        #      filename = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
        #                        'clock_divider.vhd')

        #      it.assertTrue(it.project._msg_queue.empty())

        #      records = []
        #      for record in it.project.getMessagesByPath(filename):
        #          it.assertTrue(samefile(filename, record.pop('filename')))
        #          records += [record]

        #      if BUILDER_NAME == 'msim':
        #          expected_records = [{
        #              'checker': 'msim',
        #              'column': None,
        #              'error_message': "Synthesis Warning: Reset signal 'reset' "
        #                               "is not in the sensitivity list of process "
        #                               "'line__45'.",
        #              'error_number': None,
        #              'error_type': 'W',
        #              'line_number': '45'}]
        #      elif BUILDER_NAME == 'ghdl':
        #          expected_records = []
        #      elif BUILDER_NAME == 'xvhdl':
        #          expected_records = []

        #      it.assertEquals(records, expected_records)

        #      it.assertTrue(it.project._msg_queue.empty())

        #  @it.should("get updated messages of a different source")
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test008():
        #      filename = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
        #                        'clock_divider.vhd')
        #      it.assertTrue(it.project._msg_queue.empty())

        #      code = open(filename, 'r').read().split('\n')

        #      _logger.info("Commenting line 28 should yield an error")
        #      _logger.info(repr(code[28]))

        #      code[28] = '-- ' + code[28]

        #      writeListToFile(filename, code)

        #      records = it.project.getMessagesByPath(filename)

        #      try:
        #          it.assertNotEquals(records, [])
        #      finally:
        #          # Remove the comment we added
        #          code[28] = code[28][3:]
        #          writeListToFile(filename, code)

        #      it.assertTrue(it.project._msg_queue.empty())

        #  @it.should("get messages from a source outside the project file")
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test009():
        #      filename = 'some_file.vhd'
        #      writeListToFile(filename, ['library some_lib;'])

        #      it.assertTrue(it.project._msg_queue.empty())

        #      records = it.project.getMessagesByPath(filename)

        #      _logger.info("Records found:")
        #      for record in records:
        #          _logger.info(record)

        #      it.assertIn(
        #          {'checker'        : 'hdlcc',
        #           'line_number'    : '',
        #           'column'         : '',
        #           'filename'       : '',
        #           'error_number'   : '',
        #           'error_type'     : 'W',
        #           'error_message'  : 'Path "%s" not found in '
        #                              'project file' % p.abspath(filename)},
        #          records)

        #      # The builder should find other issues as well...
        #      it.assertTrue(len(records) > 1,
        #                    "It was expected that the builder added some "
        #                    "message here indicating an error")

        #      it.assertTrue(it.project._msg_queue.empty())

        #  @it.should("rebuild sources when needed within the same library")
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test010():
        #      # Count how many messages each source has
        #      source_msgs = {}

        #      for filename in (
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clk_en_generator.vhd')):

        #          _logger.info("Getting messages for '%s'", filename)
        #          source_msgs[filename] = \
        #              it.project.getMessagesByPath(filename)

        #      _logger.info("Changing very_common_pkg to force rebuilding "
        #                   "synchronizer and another one I don't recall "
        #                   "right now")
        #      very_common_pkg = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
        #                               'very_common_pkg.vhd')

        #      code = open(very_common_pkg, 'r').read().split('\n')

        #      writeListToFile(very_common_pkg,
        #                      code[:22] + \
        #                      ["    constant TESTING : integer := 4;"] + \
        #                      code[22:])

        #      # The number of messages on all sources should not change
        #      it.assertEquals(it.project.getMessagesByPath(very_common_pkg), [])

        #      for filename in (
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clk_en_generator.vhd')):

        #          if source_msgs[filename]:
        #              _logger.info("Source %s had the following messages:\n%s",
        #                           filename,
        #                           "\n".join([str(x) for x in
        #                                      source_msgs[filename]]))
        #          else:
        #              _logger.info("Source %s has no previous messages",
        #                           filename)

        #          it.assertEquals(source_msgs[filename],
        #                          it.project.getMessagesByPath(filename))

        #      _logger.info("Restoring previous content")
        #      writeListToFile(very_common_pkg, code)

        #  @it.should("rebuild sources when needed for different libraries")
        #  @unittest.skipUnless(PROJECT_FILE is not None,
        #                       "Requires a valid project file")
        #  def test011():
        #      # Count how many messages each source has
        #      source_msgs = {}

        #      for filename in (
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'another_library', 'foo.vhd')):

        #          _logger.info("Getting messages for '%s'", filename)
        #          source_msgs[filename] = \
        #              it.project.getMessagesByPath(filename)

        #      _logger.info("Changing very_common_pkg to force rebuilding "
        #                   "synchronizer and another one I don't recall "
        #                   "right now")
        #      very_common_pkg = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
        #                               'very_common_pkg.vhd')

        #      code = open(very_common_pkg, 'r').read().split('\n')

        #      writeListToFile(very_common_pkg,
        #                      code[:22] + \
        #                      ["    constant ANOTHER_TEST_NOW : integer := 1;"] + \
        #                      code[22:])

        #      # The number of messages on all sources should not change
        #      it.assertEquals(it.project.getMessagesByPath(very_common_pkg), [])

        #      for filename in (
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
        #              p.join(VIM_HDL_EXAMPLES_PATH, 'another_library', 'foo.vhd')):

        #          if source_msgs[filename]:
        #              _logger.info("Source %s had the following messages:\n%s",
        #                           filename,
        #                           "\n".join([str(x) for x in
        #                                      source_msgs[filename]]))
        #          else:
        #              _logger.info("Source %s has no previous messages",
        #                           filename)

        #          it.assertEquals(source_msgs[filename],
        #                          it.project.getMessagesByPath(filename))

        #      _logger.info("Restoring previous content")
        #      writeListToFile(very_common_pkg, code)

    #  with it.having('vim-hdl-examples as reference and a valid project file'):

    #      @it.has_setup
    #      @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
    #      def setup():
    #          if BUILDER_NAME is None:
    #              return
    #          it.original_env = os.environ.copy()

    #          addToPath(BUILDER_PATH)

    #          it.vim_hdl_examples_path = p.join(TEST_SUPPORT_PATH, "vim-hdl-examples")
    #          it.project_file = p.join(it.vim_hdl_examples_path, BUILDER_NAME + '.prj')
    #          it.project = StandaloneProjectBuilder(it.project_file)
    #          it.project.buildByDependency()
    #          it.project.waitForBuild()
    #          it.assertNotEquals(it.project.builder.builder_name, 'fallback')

    #      @it.has_teardown
    #      def teardown():
    #          if BUILDER_NAME is None:
    #              return
    #          #  hdlcc.HdlCodeCheckerBase.cleanProjectCache(it.project_file)
    #          cleanProjectCache(PROJECT_FILE)
    #          removeFromPath(BUILDER_PATH)

    #          target_dir = it.project._config.getTargetDir()

    #          if p.exists(target_dir):
    #              shutil.rmtree(target_dir)
    #          if p.exists('modelsim.ini'):
    #              _logger.warning("Modelsim ini found at %s",
    #                              p.abspath('modelsim.ini'))
    #              os.remove('modelsim.ini')
    #          del it.project


    #      @it.should("rebuild sources when needed")
    #      @unittest.skipUnless(PROJECT_FILE is not None,
    #                           "Requires a valid project file")
    #      def test001():
    #          clk_en_generator = p.join(it.vim_hdl_examples_path,
    #                                    "basic_library", "clk_en_generator.vhd")

    #          very_common_pkg = p.join(it.vim_hdl_examples_path,
    #                                   "basic_library", "very_common_pkg.vhd")

    #          for path in (clk_en_generator,
    #                       very_common_pkg,
    #                       clk_en_generator):
    #              _logger.info("Building '%s'", path)
    #              records = it.project.getMessagesByPath(path)
    #              it.assertEqual(records, [])

it.createTests(globals())

