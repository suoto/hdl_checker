# This file is part of HDL Code Checker.
#
# Copyright (c) 2015-2019 Andre Souto
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
"Base class for creating a project file"

import abc
import logging
import os.path as p

from hdlcc.utils import getFileType

_SOURCE_EXTENSIONS = 'vhdl', 'sv', 'v'
_HEADER_EXTENSIONS = 'vh', 'svh'

_DEFAULT_LIBRARY_NAME = {
        'vhdl': 'lib',
        'verilog': 'lib',
        'systemverilog': 'lib'}

class BaseGenerator:
    """
    Base class implementing creation of config file semi automatically
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, builders):
        """
        Arguments:
            - builders: list of builder names that the server has reported as
                        working
        """
        self._builders = builders
        self._logger = logging.getLogger(self.__class__.__name__)
        self._sources = set()
        self._include_paths = {'verilog': set(),
                               'systemverilog': set()}


    def _addSource(self, path, flags, library=None):
        """
        Add a source to project. 'flags' and 'library' are only used for
        regular sources and not for header files (files ending in .vh or .svh)
        """
        self._logger.debug("Adding path %s (flgas=%s, library=%s)", path,
                           flags, library)

        if p.basename(path).split('.')[-1].lower() in ('vh', 'svh'):
            file_type = getFileType(path)
            if file_type in ('verilog', 'systemverilog'):
                self._include_paths[file_type].add(p.dirname(path))
        else:
            self._sources.add((path, ' '.join([str(x) for x in flags]),
                               library))

    @abc.abstractmethod
    def _populate(self):
        """
        Method that will be called for generating the project file contets and
        should be implemented by child classes
        """

    @abc.abstractmethod
    def _getPreferredBuilder(self):
        """
        Method should be overridden by child classes to express the preferred
        builder
        """

    def _formatIncludePaths(self, paths):
        """
        Format a list of paths to be used as flags by the builder. (Still needs
        a bit of thought, ideally only the builder know how to do this)
        """
        builder = self._getPreferredBuilder()

        if builder == 'msim':
            return ' '.join(['+incdir+%s' % path for path in paths])

        return ''

    def generate(self):
        """
        Runs the child class algorithm to populate the parent object with the
        project info and writes the result to the project file
        """

        self._populate()

        contents = ['# Files found: %s' % len(self._sources),
                    '# Available builders: %s' % ', '.join(self._builders)]

        builder = self._getPreferredBuilder()
        if builder in self._builders:
            contents += ['builder = %s' % builder]

        # Add include paths if they exists. Need to iterate sorted keys to
        # generate results always in the same order
        for lang in sorted(self._include_paths.keys()):
            paths = sorted(self._include_paths[lang])
            include_paths = self._formatIncludePaths(paths)
            if include_paths:
                contents += ['global_build_flags[%s] = %s' % (lang, include_paths)]

        if self._include_paths:
            contents += ['']

        # Add sources
        sources = []

        for path, flags, library in self._sources:
            file_type = getFileType(path)
            sources.append((file_type, library, path, flags))

        sources.sort(key=lambda x: x[2])

        for file_type, library, path, flags in sources:
            contents += ['{0} {1} {2}{3}'.format(file_type, library, path,
                                                 ' %s' % flags if flags else '')]

        self._logger.info("Resulting file has %d lines", len(contents))

        return '\n'.join(contents)
