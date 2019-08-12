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

# pylint: disable=missing-docstring
# pylint: disable=useless-object-inheritance

import logging
import os
import os.path as p
import shutil
import subprocess as subp
import time
from multiprocessing import Queue

import mock
import six
from parameterized import parameterized_class

import hdlcc
from hdlcc.builders.base_builder import BaseBuilder
from hdlcc.utils import (getCachePath, getFileType, onWindows,
                         removeDuplicates, samefile)

_logger = logging.getLogger(__name__)

class StandaloneProjectBuilder(hdlcc.HdlCodeCheckerBase):
    "Class for testing HdlCodeCheckerBase"
    _msg_queue = Queue()
    _ui_handler = logging.getLogger('UI')

    def _handleUiInfo(self, message):
        self._msg_queue.put(('info', message))
        self._ui_handler.info('[UI INFO]: %s', message)

    def _handleUiWarning(self, message):
        self._msg_queue.put(('warning', message))
        self._ui_handler.info('[UI WARNING]: %s', message)

    def _handleUiError(self, message):
        self._msg_queue.put(('error', message))
        self._ui_handler.info('[UI ERROR]: %s', message)

    def getUiMessages(self):
        while not self._msg_queue.empty():
            yield self._msg_queue.get()

class SourceMock(object):
    _logger = logging.getLogger('SourceMock')
    base_path = ''

    def __init__(self, library, design_units, dependencies=None, filename=None):
        if filename is not None:
            self._filename = p.join(self.base_path, filename)
        else:
            self._filename = p.join(self.base_path,
                                    library + '_' + design_units[0]['name'] + '.vhd')

        self.filetype = getFileType(self.filename)
        self.abspath = p.abspath(self.filename)
        self.flags = []

        self.library = library
        self._design_units = list(design_units or [])
        self._dependencies = list(dependencies or [])

        self._createMockFile()

    @property
    def filename(self):
        return self._filename

    def getLibraries(self):
        return [x.library for x in self._dependencies]

    def _createMockFile(self):
        self._logger.debug("Creating mock file: %s", self.filename)
        with open(self.filename, 'w') as fd:
            libs = removeDuplicates(
                [x.library for x in self._dependencies])

            for lib in libs:
                fd.write("library {0};\n".format(lib))

            for dependency in self._dependencies:
                fd.write("use {0}.{1};\n".format(dependency.library,
                                                 dependency.name))

            fd.write('\n')

            for design_unit in self._design_units:
                fd.write("{0} {1} is\n\nend {0} {1};\n".
                         format(design_unit['type'],
                                design_unit['name']))

    #  def __del__(self):
    #      if p.exists(self.filename):
    #          self._logger.debug("Deleting %s", self.filename)
    #          os.remove(self.filename)

    def __repr__(self):
        return ("{}(library='{}', design_units={}, dependencies={}, "
                "filename={}".format(self.__class__.__name__, self.library,
                                     self._design_units, self._dependencies,
                                     self.filename))

    def getmtime(self):
        return p.getmtime(self.filename)

    def __str__(self):
        return "[%s] %s" % (self.library, self.filename)

    def getDesignUnits(self):
        return self._design_units

    def getDependencies(self):
        return self._dependencies

    def getRawSourceContent(self):
        return open(self.filename).read()


class MockBuilder(BaseBuilder):  # pylint: disable=abstract-method
    _logger = logging.getLogger('MockBuilder')
    builder_name = 'msim_mock'
    file_types = ('vhdl', )

    def __init__(self, target_folder):
        self._target_folder = target_folder
        if not p.exists(self._target_folder):
            os.mkdir(self._target_folder)

        super(MockBuilder, self).__init__(target_folder)


    def _makeRecords(self, _): # pragma: no cover
        return []

    def _shouldIgnoreLine(self, line): # pragma: no cover
        return True

    def _checkEnvironment(self):
        return

    @staticmethod
    def isAvailable():
        return True

    def _buildSource(self, path, library, flags=None):  # pylint: disable=unused-argument
        self._logger.debug("Building path=%s, library=%s, flags=%s",
                           path, library, flags)
        return [], []

    def _createLibrary(self, library):  # pylint: disable=unused-argument
        pass

    def getBuiltinLibraries(self):  # pylint: disable=unused-argument
        return []


class FailingBuilder(MockBuilder):  # pylint: disable=abstract-method
    _logger = logging.getLogger("FailingBuilder")
    builder_name = 'FailingBuilder'
    def _checkEnvironment(self):
        raise hdlcc.exceptions.SanityCheckError(
            self.builder_name, "Fake error")


disableVunit = mock.patch('hdlcc.config_parser.foundVunit', lambda: False)


def sanitizePath(*args):
    """
    Join args with pathsep, gets the absolute path and normalizes
    """
    return p.normpath(p.abspath(p.join(*args)))  # pylint: disable=no-value-for-parameter


def assertCountEqual(it):  # pylint: disable=invalid-name

    assert six.PY2, "Only needed on Python2"

    def wrapper(first, second, msg=None):
        temp = list(second)   # make a mutable copy
        not_found = []
        for elem in first:
            try:
                temp.remove(elem)
            except ValueError:
                not_found.append(elem)

        error_details = []

        if not_found:
            error_details += ['Second list is missing item {}'.format(x)
                              for x in not_found]

        error_details += ['First list is missing item {}'.format(x) for x in
                          temp]

        if error_details:
            # Add user message at the top
            error_details = [msg, ] + error_details
            error_details += ['', "Lists {} and {} differ".format(first, second)]
            it.fail('\n'.join([str(x) for x in error_details]))

    return wrapper

def assertSameFile(it):  # pylint: disable=invalid-name
    def wrapper(first, second):
        if not samefile(p.abspath(first), p.abspath(second)):
            it.fail("Paths '{}' and '{}' differ".format(p.abspath(first),
                                                        p.abspath(second)))
    return wrapper

def writeListToFile(filename, _list): # pragma: no cover
    "Well... writes '_list' to 'filename'. This is for testing only"
    _logger.debug("Writing to %s", filename)

    open(filename, mode='w').write(
        '\n'.join([str(x) for x in _list]))

    mtime = p.getmtime(filename)
    time.sleep(0.01)

    for i, line in enumerate(_list):
        _logger.debug('%2d | %s', i, line)

    if onWindows():
        cmd = 'copy /Y "{0}" +,,{0}'.format(filename)
        _logger.debug(cmd)
        subp.check_call(cmd, shell=True)
    else:
        subp.check_call(['touch', filename])

    for i in range(10):
        if p.getmtime(filename) != mtime:
            break
        _logger.debug("Waiting...[%d]", i)
        time.sleep(0.1)


if not onWindows():
    TEST_ENVS = {
        'ghdl': os.environ['GHDL_PATH'],
        'msim': os.environ['MODELSIM_PATH'],
        'xvhdl': os.environ['XSIM_PATH'],
        'fallback': None}
else:
    TEST_ENVS = {'fallback': None}


def parametrizeClassWithBuilders(cls):
    cls.assertSameFile = assertSameFile(cls)

    keys = ['builder_name', 'builder_path']
    values = []
    for name, path in TEST_ENVS.items():
        values += [(name, path)]

    return parameterized_class(keys, values)(cls)

def removeCacheData():
    cache_path = getCachePath()
    if p.exists(cache_path):
        shutil.rmtree(cache_path)
        _logger.info("Removed %s", cache_path)

def getTestTempPath(name):
    name = name.replace('.', '_')
    path = p.abspath(p.join(os.environ['TOX_ENV_DIR'], 'tmp', name))
    if not p.exists(path):
        os.makedirs(path)
    return path

def setupTestSuport(path):
    """Copy contents of .ci/test_support_path/ to the given path"""
    _logger.info("Setting up test support at %s", path)

    test_support_path = os.environ['CI_TEST_SUPPORT_PATH']

    paths_to_copy = os.listdir(test_support_path)

    # Create the parent directory
    if not p.exists(p.dirname(path)):
        _logger.info("Creating %s", p.dirname(path))
        os.makedirs(p.dirname(path))

    for path_to_copy in paths_to_copy:
        src = p.join(test_support_path, path_to_copy)
        dest = p.join(path, path_to_copy)

        if p.exists(dest):
            _logger.info("Destination path %s already exists, removing it", dest)
            shutil.rmtree(dest)

        _logger.info("Copying %s to %s", src, dest)
        shutil.copytree(src, dest)
