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
"""
Diagnostics holders for checkers
"""

# pylint: disable=useless-object-inheritance

CHECKER_NAME = 'HDL Code Checker'
STATIC_CHECKER_NAME = 'HDL Code Checker/static'

class DiagType(object):  # pylint: disable=too-few-public-methods
    """
    Enum-like class for error types
    """
    NONE = 0
    INFO = 1
    WARNING = 2
    ERROR = 3
    STYLE_INFO = 4
    STYLE_WARNING = 5
    STYLE_ERROR = 6

class BaseDiagnostic(object):  # pylint: disable=too-few-public-methods
    """
    Base container for diagnostics
    """
    def __init__(self, checker=CHECKER_NAME, filename=None, line_number=None,
                 column=None, error_number=None, error_type=None,
                 text=None):

        self._checker = checker
        self._filename = filename
        self._line_number = line_number
        self._column = column
        self._error_number = error_number
        self._error_type = error_type
        self._text = text

    def __str__(self):
        return ('{}(checker="{}", filename="{}", line_number="{}", '
                'column="{}", error_number="{}", error_type="{}", '
                'text={})'
                .format(self.__class__.__name__, self._checker, self._filename,
                        self._line_number, self._column, self._error_number,
                        self._error_type, repr(self._text)))

    def __eq__(self, other):
        # Won't compare apples to oranges
        if not isinstance(other, BaseDiagnostic):
            return False

        # Compare attributes
        for attr in ('checker', 'filename', 'line_number', 'column',
                     'error_number', 'error_type', 'text'):
            try:
                if getattr(self, attr) != getattr(other, attr):
                    return False
            except AttributeError:
                return False

        return True

    @property
    def checker(self):
        return self._checker

    @property
    def line_number(self):
        return self._line_number

    @property
    def column(self):
        return self._column

    @property
    def filename(self):
        return self._filename

    @property
    def error_number(self):
        return self._error_number

    @property
    def error_type(self):
        return self._error_type

    @property
    def text(self):
        return self._text

class PathNotInProjectFile(BaseDiagnostic):
    """
    Reports a check request on a file whose path in not present on the project
    file
    """
    def __init__(self, path):
        super(PathNotInProjectFile, self).__init__(
            checker=CHECKER_NAME, filename=path, error_type=DiagType.WARNING,
            text='Path "{}" not found in project file'.format(path))

class StaticCheckerDiag(BaseDiagnostic):
    def __init__(self, filename=None, line_number=None, column=None,
                 error_number=None, error_type=None, text=None):

        assert error_type in (DiagType.STYLE_INFO, DiagType.STYLE_WARNING,
                              DiagType.STYLE_ERROR), \
            "Static checker diags should only carry style error types"

        super(StaticCheckerDiag, self).__init__(
            checker=STATIC_CHECKER_NAME, filename=filename,
            line_number=line_number, column=column, error_number=error_number,
            error_type=error_type, text=text)

class LibraryShouldBeOmited(StaticCheckerDiag):
    def __init__(self, filename=None, line_number=None, column=None,
                 library=None):
        super(LibraryShouldBeOmited, self).__init__(
            line_number=line_number, column=column, filename=filename,
            error_type=DiagType.STYLE_WARNING,
            text="Declaration of library '{library}' can be "
                    "omitted".format(library=library))


class ObjectIsNeverUsed(StaticCheckerDiag):
    def __init__(self, filename=None, line_number=None, column=None,
                 object_name=None, object_type=None):
        super(ObjectIsNeverUsed, self).__init__(
            filename=filename, line_number=line_number, column=column,
            error_type=DiagType.STYLE_WARNING,
            text="{} '{}' is never used".format(object_type, object_name))

class BuilderDiag(BaseDiagnostic):
    """
    text issues when checking a file whose path in not present on the
    project file
    """
    _name = '{}/{}'.format(CHECKER_NAME, 'msim')

    def __init__(self, filename=None, line_number=None, column=None,
                 error_number=None, error_type=None, text=None):
        super(BuilderDiag, self).__init__(
            checker=self._name, filename=filename, error_type=error_type,
            text=text)
