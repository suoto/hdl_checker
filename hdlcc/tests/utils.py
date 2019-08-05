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

import hdlcc
from hdlcc.utils import getFileType, onWindows, removeDuplicates, samefile

_logger = logging.getLogger(__name__)

class StandaloneProjectBuilder(hdlcc.HdlCodeCheckerBase):
    "Class for testing HdlCodeCheckerBase"
    _msg_queue = Queue()
    _ui_handler = logging.getLogger('UI')

    def _handleUiInfo(self, msg):
        self._msg_queue.put(('info', msg))
        self._ui_handler.info(msg)

    def _handleUiWarning(self, msg):
        self._msg_queue.put(('warning', msg))
        self._ui_handler.warning(msg)

    def _handleUiError(self, msg):
        self._msg_queue.put(('error', msg))
        self._ui_handler.error(msg)

class SourceMock(object):
    def __init__(self, library, design_units, dependencies=None, filename=None):
        if filename is not None:
            self.filename = filename
        else:
            self.filename = library + '_' + design_units[0]['name'] + '.vhd'

        self.filetype = getFileType(self.filename)
        self.abspath = p.abspath(self.filename)
        self.flags = []

        self.library = library
        self._design_units = design_units
        if dependencies is not None:
            self._dependencies = dependencies
        else:
            self._dependencies = []

        self._createMockFile()

    def _createMockFile(self):
        with open(self.filename, 'w') as fd:
            libs = removeDuplicates(
                [x.library for x in self._dependencies])

            for lib in libs:
                fd.write("library {0};\n".format(lib))

            for dependency in self._dependencies:
                fd.write("use {0}.{1};\n".format(dependency.library,
                                                 dependency.name))

            for design_unit in self._design_units:
                fd.write("{0} is {1} end {0} {1};\n".
                         format(design_unit['type'],
                                design_unit['name']))

    def __del__(self):
        if p.exists(self.filename):
            os.remove(self.filename)

    def getmtime(self):
        return p.getmtime(self.filename)

    def __str__(self):
        return "[%s] %s" % (self.library, self.filename)

    def getDesignUnits(self):
        return self._design_units

    def getDependencies(self):
        return self._dependencies

class MSimMock(hdlcc.builders.base_builder.BaseBuilder):  # pylint: disable=abstract-method
    _logger = logging.getLogger('MSimMock')
    builder_name = 'msim_mock'
    file_types = ('vhdl', )
    def __init__(self, target_folder):
        self._target_folder = target_folder
        if not p.exists(self._target_folder):
            os.mkdir(self._target_folder)

        super(MSimMock, self).__init__(target_folder)

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
        return [], []

    def _createLibrary(self, library):  # pylint: disable=unused-argument
        pass

    def getBuiltinLibraries(self):  # pylint: disable=unused-argument
        return []


class FailingBuilder(MSimMock):  # pylint: disable=abstract-method
    _logger = logging.getLogger("FailingBuilder")
    builder_name = 'FailingBuilder'
    def _checkEnvironment(self):
        raise hdlcc.exceptions.SanityCheckError(
            self.builder_name, "Fake error")


def disableVunit(func):
    return mock.patch('hdlcc.config_parser.foundVunit', lambda: False)(func)


def deleteFileOrDir(path):
    if p.isdir(path):
        shutil.rmtree(path)
    else:
        os.remove(path)


def handlePathPlease(*args):
    """
    Join args with pathsep, gets the absolute path and normalizes
    """
    return p.normpath(p.abspath(p.join(*args)))  # pylint: disable=no-value-for-parameter


def getDefaultCachePath(project_file): # pragma: no cover
    """
    Gets the default path of hdlcc cache.
    Intended for testing only.
    """
    return p.join(p.abspath(p.dirname(project_file)), '.hdlcc')


def cleanProjectCache(project_file): # pragma: no cover
    """
    Removes the default hdlcc cache folder.
    Intended for testing only.
    """
    if project_file is None:
        _logger.debug("Can't clean None")
    else:
        cache_folder = getDefaultCachePath(project_file)
        if p.exists(cache_folder):
            shutil.rmtree(cache_folder)


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
            it.fail('\n'.join(error_details))

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
