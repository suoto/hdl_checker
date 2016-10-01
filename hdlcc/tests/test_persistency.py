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
import time
import logging
import shutil
from multiprocessing import Queue

from nose2.tools import such

import mock

import hdlcc
import hdlcc.utils as utils

_logger = logging.getLogger(__name__)

CACHE_BUILD_SPEEDUP = 2

VIM_HDL_EXAMPLES_PATH = p.join(
    p.dirname(__file__), '..', '..', '.ci', 'test_support', 'vim-hdl-examples')

class StandaloneProjectBuilder(hdlcc.HdlCodeCheckerBase):
    "Class for testing HdlCodeCheckerBase"
    _ui_handler = logging.getLogger('UI')
    def __init__(self, *args, **kwargs):
        self._msg_queue = Queue()
        super(StandaloneProjectBuilder, self).__init__(*args, **kwargs)

    def _handleUiInfo(self, message):
        self._ui_handler.info(message)
        self._msg_queue.put(('info', message))

    def _handleUiWarning(self, message):
        self._ui_handler.warning(message)
        self._msg_queue.put(('warning', message))

    def _handleUiError(self, message):
        self._ui_handler.error(message)
        self._msg_queue.put(('error', message))

with such.A("hdlcc project with persistency") as it:

    @it.has_setup
    def setup():
        it.BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
        it.BUILDER_PATH = os.environ.get('BUILDER_PATH', None)
        if not it.BUILDER_NAME:
            return

        it.PROJECT_FILE = p.join(VIM_HDL_EXAMPLES_PATH, it.BUILDER_NAME + '.prj')

        #  StandaloneProjectBuilder.cleanProjectCache(it.PROJECT_FILE)
        utils.cleanProjectCache(it.PROJECT_FILE)

        it.original_env = os.environ.copy()
        it.builder_env = os.environ.copy()

        #  utils.addToPath(it.BUILDER_PATH)
        it.patch = mock.patch.dict(
            'os.environ',
            {'PATH' : os.pathsep.join([it.BUILDER_PATH, os.environ['PATH']])})
        it.patch.start()

        _logger.info("Builder name: %s", it.BUILDER_NAME)
        _logger.info("Builder path: %s", it.BUILDER_PATH)

    @it.has_teardown
    def teardown():
        if not it.BUILDER_NAME:
            return
        #  StandaloneProjectBuilder.cleanProjectCache(it.PROJECT_FILE)
        target_dir, _ = hdlcc.config_parser.ConfigParser.simpleParse(it.PROJECT_FILE)
        if p.exists(target_dir):
            shutil.rmtree(target_dir)

        if p.exists('xvhdl.pb'):
            os.remove('xvhdl.pb')
        if p.exists('.xvhdl.init'):
            os.remove('.xvhdl.init')

    with it.having('a performance requirement'):

        @it.has_setup
        def setup():
            it.parse_times = []
            it.build_times = []

        @it.has_teardown
        def teardown():
            #  hdlcc.HdlCodeCheckerBase.cleanProjectCache(it.PROJECT_FILE)
            utils.cleanProjectCache(it.PROJECT_FILE)
            target_dir = hdlcc.config_parser.ConfigParser(it.PROJECT_FILE).getTargetDir()
            if p.exists(target_dir):
                shutil.rmtree(target_dir)
            cache_fname = utils.getDefaultCachePath(it.PROJECT_FILE)
            if p.exists(cache_fname):
                os.remove(cache_fname)

        @it.should('measure time taken to build a project without any cache')
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def test_001():
            if it.BUILDER_NAME not in ('msim', 'ghdl', 'xvhdl'):
                _logger.info("Test requires a builder")
                return
            for _ in range(5):
                start = time.time()
                project = StandaloneProjectBuilder(it.PROJECT_FILE)
                project.clean()
                parse_time = time.time() - start
                project.getMessagesByPath(p.join(VIM_HDL_EXAMPLES_PATH,
                                                 'another_library', 'foo.vhd'))
                build_time = time.time() - start - parse_time

                _logger.info("Parsing took %fs", parse_time)
                _logger.info("Building took %fs", build_time)

                it.parse_times += [parse_time]
                it.build_times += [build_time]

            _logger.info("Builds took between %f and %f",
                         min(it.build_times), max(it.build_times))

            # Remove spurious values we may have caught
            it.build_times.remove(max(it.build_times))
            it.build_times.remove(min(it.build_times))

            # Maximum and minimum time shouldn't be too different
            if max(it.build_times)/min(it.build_times) > 1.3:
                _logger.warning(
                    "Build times between %f and %f seems too different! "
                    "Complete build times: %s",
                    min(it.build_times), max(it.build_times), it.build_times)

            project._saveCache()

        @it.should('build at least %dx faster when recovering the info' %
                   CACHE_BUILD_SPEEDUP)
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def test_002():
            if it.BUILDER_NAME not in ('msim', 'ghdl', 'xvhdl'):
                _logger.info("Test requires a builder")
                return
            _logger.info("Creating object")
            start = time.time()
            project = StandaloneProjectBuilder(it.PROJECT_FILE)
            parse_time = time.time() - start
            _logger.info("Building de facto")
            project.getMessagesByPath(p.join(VIM_HDL_EXAMPLES_PATH,
                                             'another_library', 'foo.vhd'))
            _logger.info("Done")
            build_time = time.time() - start - parse_time

            _logger.info("Parsing took %fs", parse_time)
            _logger.info("Building took %fs", build_time)

            average = float(sum(it.build_times))/len(it.build_times)

            it.assertTrue(
                build_time < average/CACHE_BUILD_SPEEDUP,
                "Building with cache took %f (should be < %f)" % \
                    (build_time, average/CACHE_BUILD_SPEEDUP))

    @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
    def _buildWithoutCache():
        it.project = StandaloneProjectBuilder(it.PROJECT_FILE)
        it.project.waitForBuild()
        it.project._saveCache()

        messages = []
        failed = False
        while not it.project._msg_queue.empty():
            _, message = it.project._msg_queue.get()
            if message.startswith("Recovered cache from "):
                failed = True
            messages += [message]

        it.assertFalse(failed,
                       "Project shouldn't have recovered from cache. "
                       "Messages found:\n%s" % "\n".join(messages))

    @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
    def _buildWithCache():
        del it.project

        it.project = StandaloneProjectBuilder(it.PROJECT_FILE)
        it.project.waitForBuild()

        messages = []
        passed = False
        while not it.project._msg_queue.empty():
            _, message = it.project._msg_queue.get()
            if message.startswith("Recovered cache from "):
                passed = True
            messages += [message]

        it.assertTrue(passed,
                      "Project should have recovered from cache. "
                      "Messages found:\n%s" % "\n".join(messages))

    with it.having('an undecodable cache file'):
        @it.has_setup
        def setup():
            if not it.BUILDER_NAME:
                return
            #  cache_fname = utils.getDefaultCachePath(it.PROJECT_FILE)
            target_dir, _ = hdlcc.config_parser.ConfigParser.simpleParse(it.PROJECT_FILE)
            if p.exists(target_dir):
                _logger.info("Target dir '%s' removed", target_dir)
                shutil.rmtree(target_dir)
            else:
                _logger.info("target_dir '%s' not found", target_dir)

        @it.has_teardown
        def teardown():
            if not it.BUILDER_NAME:
                return
            #  hdlcc.HdlCodeCheckerBase.cleanProjectCache(it.PROJECT_FILE)
            target_dir, _ = hdlcc.config_parser.ConfigParser.simpleParse(it.PROJECT_FILE)
            shutil.rmtree(target_dir)

        @it.should('build a project without cache')
        def test_001():
            if not it.BUILDER_NAME:
                _logger.info("Skipping test, it requires a builder")
                return

            _buildWithoutCache()

        @it.should('recover from cache')
        def test_002():
            if not it.BUILDER_NAME:
                _logger.info("Skipping test, it requires a builder")
                return
            _buildWithCache()

        @it.should('build without cache if cache is invalid')
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def test_003():
            if not it.BUILDER_NAME:
                _logger.info("Skipping test, it requires a builder")
                return
            target_dir, _ = hdlcc.config_parser.ConfigParser.simpleParse(it.PROJECT_FILE)
            cache_fname = p.join(target_dir, '.hdlcc.cache')
            open(cache_fname, 'w').write("hello")
            project = StandaloneProjectBuilder(it.PROJECT_FILE)
            project.waitForBuild()
            project._saveCache()

            messages = []
            passed = False
            while not project._msg_queue.empty():
                level, message = project._msg_queue.get()
                if level == 'error' and \
                        message.startswith("Unable to recover cache from "):
                    passed = True
                messages += [message]

            it.assertTrue(passed,
                          "Project shouldn't have recovered from cache. "
                          "Messages found:\n%s" % "\n".join(messages))

    with it.having('the builder working folder erased'):
        @it.has_setup
        def setup():
            if not it.BUILDER_NAME:
                return
            target_dir, _ = hdlcc.config_parser.ConfigParser.simpleParse(it.PROJECT_FILE)
            if p.exists(target_dir):
                shutil.rmtree(target_dir)

        @it.has_teardown
        def teardown():
            if not it.BUILDER_NAME:
                return
            target_dir, _ = hdlcc.config_parser.ConfigParser.simpleParse(it.PROJECT_FILE)
            if p.exists(target_dir):
                shutil.rmtree(target_dir)

        @it.should('build without cache if cache is invalid')
        def test_001():
            if not it.BUILDER_NAME:
                _logger.info("Skipping test, it requires a builder")
                return
            _buildWithoutCache()
            target_dir = hdlcc.config_parser.ConfigParser(it.PROJECT_FILE).getTargetDir()
            shutil.rmtree(target_dir)
            _buildWithoutCache()

    with it.having('the builder failing to run'):
        @it.has_setup
        def setup():
            if not it.BUILDER_NAME:
                return
            cache_fname = utils.getDefaultCachePath(it.PROJECT_FILE)
            if p.exists(cache_fname):
                os.remove(cache_fname)

        @it.has_teardown
        def teardown():
            if not it.BUILDER_NAME:
                return
            utils.cleanProjectCache(it.PROJECT_FILE)

        @it.should('use fallback builder if recovering cache failed')
        @mock.patch('hdlcc.config_parser.hasVunit', lambda: False)
        def test_001():
            if not it.BUILDER_NAME:
                _logger.info("Skipping test, it requires a builder")
                return
            _logger.info("Building without cache")
            _buildWithoutCache()
            _logger.info("Restoring original path")
            #  utils.removeFromPath(it.BUILDER_PATH)
            it.patch.stop()

            _logger.info("Building with changed env")

            project = StandaloneProjectBuilder(it.PROJECT_FILE)
            time.sleep(1)
            project.waitForBuild()
            time.sleep(1)
            project._saveCache()
            time.sleep(1)

            _logger.info("Searching UI messages")

            matches, _ = _findMessageStartingWith(project, "Failed to create builder")

            if not matches:
                it.fail("Project failed to warn that it couldn't recover "
                        "from cache")

        def _findMessageStartingWith(project, msg_start, msg_level=None):
            messages = []
            matches = []
            if project._msg_queue.empty():
                _logger.info("Message queue is empty...")

            while not project._msg_queue.empty():
                level, message = project._msg_queue.get()
                _logger.info("Message: [%s] %s", level, message)
                if msg_level is None or msg_level == level:
                    if message.startswith(msg_start):
                        matches += [(level, message)]
                messages += [message]

            return matches, messages

it.createTests(globals())

