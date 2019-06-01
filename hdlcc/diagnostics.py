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
    NONE = 'None'
    INFO = 'Info'
    WARNING = 'Warning'
    ERROR = 'Error'
    STYLE_INFO = 'Info (style)'
    STYLE_WARNING = 'Warning (style)'
    STYLE_ERROR = 'Error (style)'

class BaseDiagnostic(object):  # pylint: disable=too-few-public-methods
    """
    Base container for diagnostics
    """
    def __init__(self, # pylint: disable=too-many-arguments
                 checker, text, filename=None, line_number=None, column=None,
                 error_number=None, severity=None):

        # Checker can't be changed
        self.__checker = CHECKER_NAME if checker is None else checker

        # Modifiable attributes
        self.filename = filename
        self.error_number = error_number
        self.text = text

        # Modifiable with rules
        self.__line_number = line_number
        self.__column = column
        self.__severity = severity

        if line_number is not None:
            self.line_number = line_number
        if column is not None:
            self.column = column
        if severity is not None:
            self.severity = severity

    def __repr__(self):
        return ('{}(checker="{}", filename="{}", line_number="{}", '
                'column="{}", error_number="{}", severity="{}", '
                'text={})'
                .format(self.__class__.__name__, self.__checker, self.filename,
                        self.__line_number, self.__column, self.error_number,
                        self.__severity, repr(self.text)))

    def __eq__(self, other):
        # Won't compare apples to oranges
        if not isinstance(other, BaseDiagnostic):
            return False

        try:
            # Compare attributes
            for attr in ('checker', 'filename', 'line_number', 'column',
                         'error_number', 'severity', 'text'):
                if getattr(self, attr) != getattr(other, attr):
                    return False
        except AttributeError:
            return False

        return True

    @property
    def checker(self):
        "Full checker name"
        return self.__checker

    @property
    def line_number(self):
        "Diagnostics line number"
        if self.__line_number is not None:
            return int(self.__line_number)
        return self.__line_number

    @line_number.setter
    def line_number(self, value):
        self.__line_number = int(value)

    @property
    def column(self):
        "Diagnostics column"
        if self.__column is not None:
            return int(self.__column)
        return self.__column

    @column.setter
    def column(self, value):
        self.__column = int(value)

    @property
    def severity(self):
        "Diagnostics severity (use diagnostics.DiagType for consistency)"
        return self.__severity

    @severity.setter
    def severity(self, value):
        assert value in DiagType.__dict__.values(), \
            "Invalid severity {}".format(repr(value))
        self.__severity = value

class PathNotInProjectFile(BaseDiagnostic):
    """
    Reports a check request on a file whose path in not present on the project
    file
    """
    def __init__(self, path):
        super(PathNotInProjectFile, self).__init__(
            checker=CHECKER_NAME, filename=path, severity=DiagType.WARNING,
            text='Path "{}" not found in project file'.format(path))

class StaticCheckerDiag(BaseDiagnostic):
    "Base diagnostics issues from static checks"
    def __init__(self, # pylint: disable=too-many-arguments
                 text, severity, filename=None, line_number=None, column=None,
                 error_number=None):

        assert severity in (DiagType.STYLE_INFO, DiagType.STYLE_WARNING,
                            DiagType.STYLE_ERROR), \
            "Static checker diags should only carry style error types"

        super(StaticCheckerDiag, self).__init__(
            checker=STATIC_CHECKER_NAME, text=text, severity=severity,
            filename=filename, line_number=line_number, column=column,
            error_number=error_number)

class LibraryShouldBeOmited(StaticCheckerDiag):
    "Library declaration should be ommited"
    def __init__(self, library, filename=None, line_number=None, column=None):
        super(LibraryShouldBeOmited, self).__init__(
            line_number=line_number, column=column, filename=filename,
            severity=DiagType.STYLE_WARNING,
            text="Declaration of library '{library}' can be omitted" \
                    .format(library=library))

class ObjectIsNeverUsed(StaticCheckerDiag):
    "Reports an object that was created but never used"
    def __init__(self,  # pylint: disable=too-many-arguments
                 filename=None, line_number=None, column=None,
                 object_name=None, object_type=None):
        super(ObjectIsNeverUsed, self).__init__(
            filename=filename, line_number=line_number, column=column,
            severity=DiagType.STYLE_WARNING,
            text="{} '{}' is never used".format(object_type, object_name))

class BuilderDiag(BaseDiagnostic):
    """
    text issues when checking a file whose path in not present on the
    project file
    """
    def __init__(self, # pylint: disable=too-many-arguments
                 builder_name, text, filename=None, line_number=None, column=None,
                 error_number=None, severity=None):
        super(BuilderDiag, self).__init__(
            checker='{}/{}'.format(CHECKER_NAME, builder_name), text=text,
            filename=filename, line_number=line_number, column=column,
            error_number=error_number, severity=severity)
