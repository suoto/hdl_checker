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
# pylint: disable=useless-object-inheritance

import logging
import os
import os.path as p
from multiprocessing import Queue

import mock
import six

import hdlcc

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

        self.filetype = hdlcc.utils.getFileType(self.filename)
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
            libs = hdlcc.utils.removeDuplicates(
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


def assertCountEqual(it):  # pylint: disable=invalid-name
    """

    """

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
        if not hdlcc.utils.samefile(p.abspath(first), p.abspath(second)):
            it.fail("Paths '{}' and '{}' differ".format(p.abspath(first),
                                                        p.abspath(second)))
    return wrapper
