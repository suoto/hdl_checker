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

# pylint: disable=function-redefined, missing-docstring, protected-access

import os
import os.path as p
import logging

from nose2.tools import such

import hdlcc
from hdlcc import ProjectBuilder

_logger = logging.getLogger(__name__)

_BUILDER = os.environ.get('BUILDER', 'ghdl')
if _BUILDER == 'msim':
    _PRJ_FILENAME = 'dependencies/vim-hdl-examples/project.prj'
    _PATH = "/home/souto/modelsim/modeltech/linux_x86_64/"
else:
    _PRJ_FILENAME = 'dependencies/vim-hdl-examples/ghdl.prj'
    _PATH = p.expanduser("~/ghdl/bin")

_PRJ_FILENAME = p.expanduser(_PRJ_FILENAME)

from multiprocessing import Queue

class StandaloneProjectBuilder(ProjectBuilder):
    "Class for testing ProjectBuilder"
    _msg_queue = Queue()
    _ui_handler = logging.getLogger('UI')
    def __init__(self):
        super(StandaloneProjectBuilder, self).__init__(_PRJ_FILENAME)

    def _handleUiInfo(self, message):
        self._msg_queue.put(('info', message))
        self._ui_handler.info(message)

    def _handleUiWarning(self, message):
        self._msg_queue.put(('warning', message))
        self._ui_handler.warning(message)

    def _handleUiError(self, message):
        self._msg_queue.put(('error', message))
        self._ui_handler.error(message)

with such.A('hdlcc test using vim-hdl-examples') as it:

    with it.having('a valid project file'):

        with it.having('a valid environment'):

            @it.has_setup
            def setup():
                it.original_path = os.environ['PATH']
                os.environ['PATH'] += ':' + _PATH

                it.project = StandaloneProjectBuilder()
                it.assertTrue(it.project._msg_queue.empty())

            @it.has_teardown
            def teardown():
                os.environ['PATH'] = it.original_path
                del it.project

            @it.should('build project by dependency')
            def test():
                _logger.info("Checking if msg queue is empty")
                it.assertTrue(it.project._msg_queue.empty())
                _logger.info("Calling setup")
                it.project.buildByDependency()

                #  _logger.info("Checking for hdlcc message")
                #  it.assertEqual(
                #      ("warning", "Setup thread is already running"),
                #      it.project._msg_queue.get())
                #  _logger.info("Waiting for setup to finish")
                #  #  with it.project._lock:
                #  #      _logger.info("Build lock released")

            # TODO: Check if this should be removed. This has caused
            # the test to hang several times
            #  @it.should('handle foreground build request before background build'
            #             ' finishes')
            #  def test():
            #       time.sleep(0.5)
            #      _logger.info("Checking if msg queue is empty")
            #      it.assertTrue(it.project._msg_queue.empty())
            #      _logger.info("Calling setup")
            #      it.project.setup(blocking=True)

            #      _logger.info("Checking for hdlcc message")
            #      it.assertEqual(
            #          ("warning", "Setup thread is already running"),
            #          it.project._msg_queue.get())
            #      _logger.info("Waiting for setup to finish")
            #      #  with it.project._lock:
            #      #      _logger.info("Build lock released")

            @it.should('get messages by path')
            def test():
                it.assertTrue(it.project._msg_queue.empty())
                records = it.project.getMessagesByPath(\
                    p.expanduser('dependencies/vim-hdl-examples/'
                                 'another_library/foo.vhd'))
                for record in records:
                    _logger.info(record)
                it.assertNotEqual(len(records), 0)
                it.assertTrue(it.project._msg_queue.empty())

            #  @it.should('mark the project file as valid')
            #  def test():
            #      it.assertTrue(it.project._project_file['valid'])
            #      it.assertTrue(it.project._msg_queue.empty())


            @it.should('recover from cache')
            def test():
                it.project = StandaloneProjectBuilder()

            @it.should("warn when a source wasn't found in the project file")
            def test():
                test_path = p.abspath('file_outside_the_prj_file.vhd')
                expected_msg = 'Path "%s" not found in project file' % test_path
                if not p.exists(test_path):
                    open(test_path, 'w').close()
                records = it.project.getMessagesByPath(\
                    p.expanduser(test_path))

                found = False
                for record in records:
                    if record['error_type'] == 'W' and \
                            record['error_message'] == expected_msg:
                        found = True
                        break

                it.assertTrue(found, "File not found error not found")

            @it.should("find source containing a given design unit")
            def test():
                sources = it.project._findSourceByDesignUnit("another_library.foo")
                it.assertTrue(len(sources) == 1, "Should find a single source "
                                                 "but found %d" % len(sources))
                source = sources.pop()
                it.assertIsInstance(source, hdlcc.source_file.VhdlSourceFile, \
                    "Source file returned is not an instance of "
                    "hdlcc.source_file.VhdlSourceFile")

                it.assertEqual(source.library, "another_library", \
                    "Source file library '%s' is not 'another_library" % source.library)

                it.assertEqual(source.filename, \
                    p.abspath("dependencies/vim-hdl-examples/"
                              "another_library/foo.vhd"))

            @it.should("fail to find source containing a non-existing design unit")
            def test():
                sources = it.project._findSourceByDesignUnit("foo_bar.foo")
                it.assertTrue(len(sources) == 0, "Should not find any source!")

            @it.should("clean up generated files")
            def test():
                #  cache_fname = StandaloneProjectBuilder._getCacheFilename(_PRJ_FILENAME)
                #  it.assertTrue(p.exists(cache_fname),
                #                "Cache file '%s' not found" % cache_fname)

                #  cache_folder = it.project.builder._target_folder

                #  it.assertTrue(p.exists(cache_folder),
                #                "Cache folder '%s' not found" % cache_folder)

                # Do this twice to check that the project builder doesn't
                # fails if we try to clean up more than once
                for _ in range(2):
                    StandaloneProjectBuilder.clean(_PRJ_FILENAME)

                    #  it.assertFalse(p.exists(cache_fname),
                    #                 "Cache file '%s' still exists" % cache_fname)

                    #  #  it.assertFalse(p.exists(cache_folder),
                    #  #                 "Cache folder '%s' still exists" % cache_folder)

        with it.having('an invalid environment'):
            @it.has_setup
            def setup():
                it.assertTrue(_PATH not in os.environ['PATH'].split(':'), \
                    "'%s' should not be on os.environ['PATH']" % _PATH)

                it.project = StandaloneProjectBuilder()
                it.assertTrue(it.project._msg_queue.empty())

            @it.has_teardown
            def teardown():
                del it.project

            #  @it.should('add a project file')
            #  def test():
            #      it.project.setProjectFile(_PRJ_FILENAME)
            #      it.assertTrue(it.project._msg_queue.empty())

            #  @it.should('read project file and build by dependency in background')
            #  def test():
            #      it.assertTrue(it.project._msg_queue.empty())
            #      it.project.setup(blocking=False)
            #      it.assertTrue(it.project._msg_queue.empty())

            #      for _ in range(10):
            #          if it.project._setup_thread.isAlive():
            #              _logger.info("Build lock is locked")
            #              break
            #          else:
            #              _logger.warning("Waiting for build lock to be locked...")
            #          time.sleep(1)

            #  @it.should('handle foreground build request before background build '
            #             'finishes')
            #  def test():
            #      _logger.info("Message queue is empty: %s",
            #                   it.project._msg_queue.empty())
            #      it.project.setup(blocking=True)
            #      _logger.info("Message queue is empty: %s",
            #                   it.project._msg_queue.empty())

            #      it.assertEqual(
            #          ("warning", "Setup thread is already running"),
            #          it.project._msg_queue.get(1))
            #      _logger.info("ProjectBuilder message checked")
            #      for _ in range(10):
            #          if not it.project._setup_thread.isAlive():
            #              _logger.info("Build lock released")
            #              return
            #          else:
            #              _logger.warning("Waiting for build lock release...")
            #          time.sleep(1)

            #      it.assertTrue(False, "Could not acquire lock")

            #  @it.should('get messages by path')
            #  def test():
            #      it.assertTrue(it.project._msg_queue.empty())
            #      records = it.project.getMessagesByPath(\
            #          p.expanduser('dependencies/vim-hdl-examples/another_library/foo.vhd'))
            #      it.assertNotEqual(len(records), 0)
            #      it.assertTrue(it.project._msg_queue.empty())

            #  @it.should('mark the project file as valid')
            #  def test():
            #      it.assertTrue(it.project._project_file['valid'])
            #      it.assertTrue(it.project._msg_queue.empty())


            #  @it.should('recover from cache')
            #  def test():
            #      it.project = StandaloneProjectBuilder()
            #      it.project.setProjectFile(p.expanduser(_PRJ_FILENAME))
            #      it.project.setup()

            #  @it.should("warn when a source wasn't found in the project file")
            #  def test():
            #      test_path = p.abspath('file_outside_the_prj_file.vhd')
            #      expected_msg = 'Path "%s" not found in project file' % test_path
            #      if not p.exists(test_path):
            #          open(test_path, 'w').close()
            #      records = it.project.getMessagesByPath(\
            #          p.expanduser(test_path))

            #      found = False
            #      for record in records:
            #          if record['error_type'] == 'W' and record['error_message'] == expected_msg:
            #              found = True
            #              break

            #      it.assertTrue(found, "File not found error not found")

            #  @it.should("find source containing a given design unit")
            #  def test():
            #      sources = it.project._findSourceByDesignUnit("another_library.foo")
            #      it.assertTrue(len(sources) == 1, "Should find a single source")
            #      source = sources.pop()
            #      it.assertIsInstance(source, hdlcc.source_file.VhdlSourceFile, \
            #          "Source file returned is not an instance of "
            #          "hdlcc.source_file.VhdlSourceFile")

            #      it.assertEqual(source.library, "another_library", \
            #          "Source file library '%s' is not 'another_library" % source.library)

            #      it.assertEqual(source.filename, \
            #          p.abspath("dependencies/vim-hdl-examples/another_library/foo.vhd"))

            #  @it.should("fail to find source containing a non-existing design unit")
            #  def test():
            #      sources = it.project._findSourceByDesignUnit("foo_bar.foo")
            #      it.assertTrue(len(sources) == 0, "Should not find any source!")

            #  @it.should("clean up generated files")
            #  def test():
            #      cache_fname = StandaloneProjectBuilder._getCacheFilename(_PRJ_FILENAME)
            #      it.assertTrue(p.exists(cache_fname),
            #                    "Cache file '%s' not found" % cache_fname)

            #      cache_folder = it.project.builder._target_folder

            #      it.assertTrue(p.exists(cache_folder),
            #                    "Cache folder '%s' not found" % cache_folder)

            #      # Do this twice to check that the project builder doesn't
            #      # fails if we try to clean up more than once
            #      for _ in range(2):
            #          StandaloneProjectBuilder.clean(_PRJ_FILENAME)

            #          it.assertFalse(p.exists(cache_fname),
            #                         "Cache file '%s' still exists" % cache_fname)

            #          #  it.assertFalse(p.exists(cache_folder),
            #          #                 "Cache folder '%s' still exists" % cache_folder)


it.createTests(globals())
