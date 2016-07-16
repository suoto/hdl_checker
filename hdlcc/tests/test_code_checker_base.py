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
from multiprocessing import Queue

from nose2.tools import such

import hdlcc
from hdlcc.utils import (writeListToFile,
                         addToPath,
                         removeFromPath,
                         samefile,
                         onCI)

_logger = logging.getLogger(__name__)

BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
BUILDER_PATH = p.expandvars(os.environ.get('BUILDER_PATH', \
                            p.expanduser("~/ghdl/bin/")))

HDLCC_CI = os.environ['HDLCC_CI']
VIM_HDL_EXAMPLES_PATH = p.join(HDLCC_CI, "vim-hdl-examples")

if BUILDER_NAME is not None:
    PROJECT_FILE = p.join(VIM_HDL_EXAMPLES_PATH, BUILDER_NAME + '.prj')
else:
    PROJECT_FILE = None

class StandaloneProjectBuilder(hdlcc.HdlCodeCheckerBase):
    "Class for testing HdlCodeCheckerBase"
    _msg_queue = Queue()
    _ui_handler = logging.getLogger('UI')
    def __init__(self, project_file=None):
        if project_file is None:
            super(StandaloneProjectBuilder, self).__init__(PROJECT_FILE)
        else:
            super(StandaloneProjectBuilder, self).__init__(project_file)

    def _handleUiInfo(self, message):
        self._msg_queue.put(('info', message))
        self._ui_handler.info(message)

    def _handleUiWarning(self, message):
        self._msg_queue.put(('warning', message))
        self._ui_handler.warning(message)

    def _handleUiError(self, message):
        self._msg_queue.put(('error', message))
        self._ui_handler.error(message)

with such.A("hdlcc project with '%s' builder" % str(BUILDER_NAME)) as it:

    it.DUMMY_PROJECT_FILE = p.join(os.curdir, 'remove_me')

    @it.has_setup
    def setup():
        StandaloneProjectBuilder.cleanProjectCache(PROJECT_FILE)

        _logger.info("Builder name: %s", BUILDER_NAME)
        _logger.info("Builder path: %s", BUILDER_PATH)

    @it.has_teardown
    def teardown():
        StandaloneProjectBuilder.cleanProjectCache(PROJECT_FILE)
        if p.exists(it.DUMMY_PROJECT_FILE):
            shutil.rmtree(it.DUMMY_PROJECT_FILE)

    with it.having('hdl_lib as reference and a valid project file'):

        @it.has_setup
        def setup():
            if p.exists('modelsim.ini'):
                _logger.warning("Modelsim ini found at %s",
                                p.abspath('modelsim.ini'))
                os.remove('modelsim.ini')

            hdlcc.HdlCodeCheckerBase.cleanProjectCache(PROJECT_FILE)

            builder = hdlcc.builders.getBuilderByName(BUILDER_NAME)

            if onCI() and BUILDER_NAME is not None:
                with it.assertRaises(hdlcc.exceptions.SanityCheckError):
                    builder(it.DUMMY_PROJECT_FILE)

            it.original_env = os.environ.copy()

            addToPath(BUILDER_PATH)

            it.assertNotEquals(os.environ['PATH'], it.original_env['PATH'])

            try:
                builder(it.DUMMY_PROJECT_FILE)
            except hdlcc.exceptions.SanityCheckError:
                it.fail("Builder creation failed even after configuring "
                        "the builder path")

        @it.has_teardown
        def teardown():
            hdlcc.HdlCodeCheckerBase.cleanProjectCache(PROJECT_FILE)
            removeFromPath(BUILDER_PATH)
            target_dir = it.project._config.getTargetDir()
            if p.exists(target_dir):
                shutil.rmtree(target_dir)
            if p.exists('modelsim.ini'):
                _logger.warning("Modelsim ini found at %s",
                                p.abspath('modelsim.ini'))
                os.remove('modelsim.ini')
            del it.project

        @it.should('build project by dependency in background')
        def test001(case):
            _logger.info("Creating project builder object")
            it.project = StandaloneProjectBuilder()
            _logger.info("Checking if msg queue is empty")
            if PROJECT_FILE is None:
                _logger.warning("Skipping '%s'", case)
                return
            it.assertTrue(it.project._msg_queue.empty())
            it.assertFalse(it.project.finishedBuilding())

        @it.should('notify if a build is already running')
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test002():
            it.project.buildByDependency()
            while it.project._msg_queue.empty():
                time.sleep(0.1)
            messages = []
            while not it.project._msg_queue.empty():
                messages.append(it.project._msg_queue.get())

            try:
                it.assertIn(('info', 'Build thread is already running'),
                            messages)
            except:
                it.project.waitForBuild()
                raise

        @it.should('warn when trying to build a source before the build '
                   'thread completes')
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test003():
            filename = p.join(VIM_HDL_EXAMPLES_PATH, 'another_library',
                              'foo.vhd')

            it.assertTrue(it.project._msg_queue.empty())

            it.project.getMessagesByPath(filename)

            _logger.info("Waiting for any message to arrive on message queue")
            for _ in range(50):
                if it.project._msg_queue.empty():
                    break
                time.sleep(0.1)

            messages = []
            while not it.project._msg_queue.empty():
                message = it.project._msg_queue.get()
                _logger.info("Appending message '%s'", message)
                messages.append(message)

            try:
                it.assertIn(('warning', "Project hasn't finished building, "
                                        "try again after it finishes."),
                            messages)
                _logger.info("OK, the mesage was found")
            finally:
                _logger.warning("Waiting until the project finishes building")
                it.project.waitForBuild()

        @it.should('wait until build has finished')
        def test004():
            it.project.waitForBuild()

        @it.should('get messages by path')
        def test005():
            filename = p.join(VIM_HDL_EXAMPLES_PATH, 'another_library',
                              'foo.vhd')

            it.assertTrue(it.project._msg_queue.empty())

            records = it.project.getMessagesByPath(filename)

            it.assertIn(
                {'error_subtype' : 'Style',
                 'line_number'   : 43,
                 'checker'       : 'HDL Code Checker/static',
                 'error_message' : "signal 'neat_signal' is never used",
                 'column'        : 12,
                 'error_type'    : 'W',
                 'error_number'  : '0',
                 'filename'      : None},
                records)

            it.assertTrue(it.project._msg_queue.empty())

        @it.should('get updated messages')
        def test006():
            filename = p.join(VIM_HDL_EXAMPLES_PATH, 'another_library',
                              'foo.vhd')

            it.assertTrue(it.project._msg_queue.empty())

            code = open(filename, 'r').read().split('\n')

            code[28] = '-- ' + code[28]

            writeListToFile(filename, code)

            records = it.project.getMessagesByPath(filename)

            try:
                it.assertNotIn(
                    {'error_subtype' : 'Style',
                     'line_number'   : 29,
                     'checker'       : 'HDL Code Checker/static',
                     'error_message' : "constant 'ADDR_WIDTH' is never used",
                     'column'        : 14,
                     'error_type'    : 'W',
                     'error_number'  : '0',
                     'filename'      : None},
                    records)
            finally:
                # Remove the comment we added
                code[28] = code[28][3:]
                writeListToFile(filename, code)

            it.assertTrue(it.project._msg_queue.empty())

        @it.should('get messages by path of a different source')
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test007():
            filename = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
                              'clock_divider.vhd')

            it.assertTrue(it.project._msg_queue.empty())

            records = []
            for record in it.project.getMessagesByPath(filename):
                it.assertTrue(samefile(filename, record.pop('filename')))
                records += [record]

            if BUILDER_NAME == 'msim':
                expected_records = [{
                    'checker': 'msim',
                    'column': None,
                    'error_message': "Synthesis Warning: Reset signal 'reset' "
                                     "is not in the sensitivity list of process "
                                     "'line__45'.",
                    'error_number': None,
                    'error_type': 'W',
                    'line_number': '45'}]
            elif BUILDER_NAME == 'ghdl':
                expected_records = []
            elif BUILDER_NAME == 'xvhdl':
                expected_records = []

            it.assertEquals(records, expected_records)

            it.assertTrue(it.project._msg_queue.empty())

        @it.should('get updated messages of a different source')
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test008():
            filename = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
                              'clock_divider.vhd')
            it.assertTrue(it.project._msg_queue.empty())

            code = open(filename, 'r').read().split('\n')

            _logger.info("Commenting line 28 should yield an error")
            _logger.info(repr(code[28]))

            code[28] = '-- ' + code[28]

            writeListToFile(filename, code)

            records = it.project.getMessagesByPath(filename)

            try:
                it.assertNotEquals(records, [])
            finally:
                # Remove the comment we added
                code[28] = code[28][3:]
                writeListToFile(filename, code)

            it.assertTrue(it.project._msg_queue.empty())

        @it.should('rebuild sources when needed within the same library')
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test009():
            # Count how many messages each source has
            source_msgs = {}

            for filename in (
                    p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
                    p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clk_en_generator.vhd')):

                _logger.info("Getting messages for '%s'", filename)
                source_msgs[filename] = \
                    it.project.getMessagesByPath(filename)

            _logger.info("Changing very_common_pkg to force rebuilding "
                         "synchronizer and another one I don't recall "
                         "right now")
            very_common_pkg = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
                                     'very_common_pkg.vhd')

            code = open(very_common_pkg, 'r').read().split('\n')

            writeListToFile(very_common_pkg,
                            code[:22] + \
                            ["    constant TESTING : integer := 4;"] + \
                            code[22:])

            # The number of messages on all sources should not change
            it.assertEquals(it.project.getMessagesByPath(very_common_pkg), [])

            for filename in (
                    p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
                    p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clk_en_generator.vhd')):

                if source_msgs[filename]:
                    _logger.info("Source %s had the following messages:\n%s",
                                 filename,
                                 "\n".join([str(x) for x in
                                            source_msgs[filename]]))
                else:
                    _logger.info("Source %s has no previous messages",
                                 filename)

                it.assertEquals(source_msgs[filename],
                                it.project.getMessagesByPath(filename))

            _logger.info("Restoring previous content")
            writeListToFile(very_common_pkg, code)

        @it.should('rebuild sources when needed for different libraries')
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test010():
            # Count how many messages each source has
            source_msgs = {}

            for filename in (
                    p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
                    p.join(VIM_HDL_EXAMPLES_PATH, 'another_library', 'foo.vhd')):

                _logger.info("Getting messages for '%s'", filename)
                source_msgs[filename] = \
                    it.project.getMessagesByPath(filename)

            _logger.info("Changing very_common_pkg to force rebuilding "
                         "synchronizer and another one I don't recall "
                         "right now")
            very_common_pkg = p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library',
                                     'very_common_pkg.vhd')

            code = open(very_common_pkg, 'r').read().split('\n')

            writeListToFile(very_common_pkg,
                            code[:22] + \
                            ["    constant ANOTHER_TEST_NOW : integer := 1;"] + \
                            code[22:])

            # The number of messages on all sources should not change
            it.assertEquals(it.project.getMessagesByPath(very_common_pkg), [])

            for filename in (
                    p.join(VIM_HDL_EXAMPLES_PATH, 'basic_library', 'clock_divider.vhd'),
                    p.join(VIM_HDL_EXAMPLES_PATH, 'another_library', 'foo.vhd')):

                if source_msgs[filename]:
                    _logger.info("Source %s had the following messages:\n%s",
                                 filename,
                                 "\n".join([str(x) for x in
                                            source_msgs[filename]]))
                else:
                    _logger.info("Source %s has no previous messages",
                                 filename)

                it.assertEquals(source_msgs[filename],
                                it.project.getMessagesByPath(filename))

            _logger.info("Restoring previous content")
            writeListToFile(very_common_pkg, code)

        @it.should("raise hdlcc.exceptions.DesignUnitNotFoundError when "
                   "a design unit can't be found")
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test012():
            with it.assertRaises(hdlcc.exceptions.DesignUnitNotFoundError) as exc:
                it.project._findSourceByDesignUnit('some_lib.some_unit')
                _logger.info("Raised exception: %s", str(exc))

            try:
                sources = it.project._findSourceByDesignUnit('another_library.foo')
                for source in sources:
                    it.assertTrue(
                        p.exists(source.filename),
                        "Couldn't find source with path '%s'" % source.filename)
            except hdlcc.exceptions.DesignUnitNotFoundError:
                it.fail("Shouldn't raise exception for a unit that is "
                        "supposed to be found")

    with it.having('vim-hdl-examples as reference and a valid project file'):

        @it.has_setup
        def setup():
            if BUILDER_NAME is None:
                return
            it.original_env = os.environ.copy()

            addToPath(BUILDER_PATH)

            it.vim_hdl_examples_path = p.join(HDLCC_CI, "vim-hdl-examples")
            it.project_file = p.join(it.vim_hdl_examples_path, BUILDER_NAME + '.prj')
            it.project = StandaloneProjectBuilder(it.project_file)
            it.project.waitForBuild()
            it.assertNotEquals(it.project.builder.builder_name, 'fallback')

        @it.has_teardown
        def teardown():
            if BUILDER_NAME is None:
                return
            hdlcc.HdlCodeCheckerBase.cleanProjectCache(it.project_file)
            removeFromPath(BUILDER_PATH)

            target_dir = it.project._config.getTargetDir()

            if p.exists(target_dir):
                shutil.rmtree(target_dir)
            if p.exists('modelsim.ini'):
                _logger.warning("Modelsim ini found at %s",
                                p.abspath('modelsim.ini'))
                os.remove('modelsim.ini')
            del it.project


        @it.should("rebuild sources when needed")
        @unittest.skipUnless(PROJECT_FILE is not None,
                             "Requires a valid project file")
        def test001():
            clk_en_generator = p.join(it.vim_hdl_examples_path,
                                      "basic_library", "clk_en_generator.vhd")

            very_common_pkg = p.join(it.vim_hdl_examples_path,
                                     "basic_library", "very_common_pkg.vhd")

            for path in (clk_en_generator,
                         very_common_pkg,
                         clk_en_generator):
                _logger.info("Building '%s'", path)
                records = it.project.getMessagesByPath(path)
                it.assertEqual(records, [])

it.createTests(globals())

