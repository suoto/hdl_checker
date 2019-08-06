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

import logging
import os
import os.path as p
import shutil
from multiprocessing import Queue

import mock
from nose2.tools import such

import hdlcc
from hdlcc.tests.utils import (cleanProjectCache, disableVunit,
                               getDefaultCachePath)

_logger = logging.getLogger(__name__)

BASE_PATH = p.join(os.environ['TOX_ENV_DIR'], 'tmp', 'grlib')

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

with such.A("hdlcc project with persistence") as it:

    @it.has_setup
    def setup():
        it.BUILDER_NAME = os.environ.get('BUILDER_NAME', None)
        it.BUILDER_PATH = os.environ.get('BUILDER_PATH', None)
        if not it.BUILDER_NAME:
            return

        it.PROJECT_FILE = p.join(BASE_PATH, it.BUILDER_NAME + '.prj')

        #  StandaloneProjectBuilder.cleanProjectCache(it.PROJECT_FILE)
        cleanProjectCache(it.PROJECT_FILE)

        it.original_env = os.environ.copy()
        it.builder_env = os.environ.copy()

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

    @disableVunit
    def _buildWithoutCache():
        it.project = StandaloneProjectBuilder(it.PROJECT_FILE)

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

    @disableVunit
    def _buildWithCache():
        del it.project

        it.project = StandaloneProjectBuilder(it.PROJECT_FILE)

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
            #  cache_fname = getDefaultCachePath(it.PROJECT_FILE)
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
        @disableVunit
        def test_003():
            if not it.BUILDER_NAME:
                _logger.info("Skipping test, it requires a builder")
                return
            target_dir, _ = hdlcc.config_parser.ConfigParser.simpleParse(it.PROJECT_FILE)
            cache_fname = p.join(target_dir, '.hdlcc.cache')
            open(cache_fname, 'w').write("hello")
            project = StandaloneProjectBuilder(it.PROJECT_FILE)

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
            cache_fname = getDefaultCachePath(it.PROJECT_FILE)
            if p.exists(cache_fname):
                os.remove(cache_fname)

        @it.has_teardown
        def teardown():
            if not it.BUILDER_NAME:
                return
            cleanProjectCache(it.PROJECT_FILE)

        @it.should('use fallback builder if recovering cache failed')
        @disableVunit
        def test_001():
            if not it.BUILDER_NAME:
                _logger.info("Skipping test, it requires a builder")
                return
            _logger.info("Building without cache")
            _buildWithoutCache()
            _logger.info("Restoring original path")
            it.patch.stop()

            _logger.info("Building with changed env")

            project = StandaloneProjectBuilder(it.PROJECT_FILE)

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
