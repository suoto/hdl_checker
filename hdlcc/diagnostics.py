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
"Diagnostics holders for checkers"

import os.path as p

from hdlcc.utils import HashableByKey, samefile

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


class CheckerDiagnostic(HashableByKey):  # pylint: disable=too-many-instance-attributes
    """
    Base container for diagnostics
    """
    def __init__(self, # pylint: disable=too-many-arguments
                 checker, text, filename=None, line_number=None, column_number=None,
                 error_code=None, severity=None):

        # Checker can't be changed
        self.__checker = CHECKER_NAME if checker is None else checker

        # Modifiable attributes
        self.filename = filename
        self.error_code = error_code
        self.text = str(text)

        # Modifiable with rules
        self.__line_number = None if line_number is None else int(line_number)
        self.__column = None if column_number is None else int(column_number)
        self.__severity = severity

        if line_number is not None:
            self.line_number = line_number
        if column_number is not None:
            self.column_number = column_number
        if severity is not None:
            self.severity = severity

    def __repr__(self):
        filename = None if self.filename is None else self.filename
        error_code = None if self.error_code is None else self.error_code

        return ('{}(checker="{}", filename="{}", line_number={}, '
                'column_number={}, error_code={}, severity="{}", text="{}")'
                .format(self.__class__.__name__, self.checker, filename,
                        self.line_number, self.column_number, error_code,
                        self.severity, self.text))

    @property
    def __hash_key__(self):
        return (self.checker, self.column_number, self.error_code,
                self.filename, self.line_number, self.severity, self.text)

    #  def __hash__(self):
    #      #  for item in ('checker', 'column_number', 'error_code',
    #      #          'filename', 'line_number', 'severity', 'text'):
    #      #      try:
    #      #          hash(getattr(self, item))
    #      #      except TypeError:
    #      #          print("item %s is not hashable!" % item)
    #      return super(CheckerDiagnostic, self).__hash__()
    #      #  assert False, 'hey'

    def __eq__(self, other):
        if hash(self) != hash(other):
            return False

        if (self.filename is not None and p.exists(self.filename) and
                other.filename is not None and p.exists(other.filename)):
            if not samefile(self.filename, other.filename):
                return False

        return True

    def toDict(self):
        """Returns a dict representation of the object. All keys are always
        present but not values are necessearily set, in which case their values
        will be 'None'. Dict has the folowwing format:

            - checker: (string) Checker name
            - filename: (string)
            - error_code: (string)
            - text: (string)
            - line_number: (int or None)
            - column_number: (int or None)
            - severity: (string) Values taken from DiagType
        """
        return {'checker': self.checker,
                'filename': self.filename,
                'error_code': self.error_code,
                'text': self.text,
                'line_number': self.line_number,
                'column_number': self.column_number,
                'severity': self.severity}

    @classmethod
    def fromDict(cls, state):
        "Creates a diagnostics objects from state dict"
        return cls(
            checker=state['checker'],
            filename=state['filename'],
            error_code=state['error_code'],
            text=state['text'],
            line_number=state['line_number'],
            column_number=state['column_number'],
            severity=state['severity'])

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
    def column_number(self):
        "Diagnostics column_number"
        if self.__column is not None:
            return int(self.__column)
        return self.__column

    @column_number.setter
    def column_number(self, value):
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

class PathNotInProjectFile(CheckerDiagnostic):
    """
    Reports a check request on a file whose path in not present on the project
    file
    """
    def __init__(self, path):
        super(PathNotInProjectFile, self).__init__(
            checker=CHECKER_NAME, filename=path, severity=DiagType.WARNING,
            text='Path "{}" not found in project file'.format(path))

class StaticCheckerDiag(CheckerDiagnostic):
    "Base diagnostics issues from static checks"
    def __init__(self, # pylint: disable=too-many-arguments
                 text, severity, filename=None, line_number=None, column_number=None,
                 error_code=None):

        assert severity in (DiagType.STYLE_INFO, DiagType.STYLE_WARNING,
                            DiagType.STYLE_ERROR), \
            "Static checker diags should only carry style error types"

        super(StaticCheckerDiag, self).__init__(
            checker=STATIC_CHECKER_NAME, text=text, severity=severity,
            filename=filename, line_number=line_number, column_number=column_number,
            error_code=error_code)

class LibraryShouldBeOmited(StaticCheckerDiag):
    "Library declaration should be ommited"
    def __init__(self, library, filename=None, line_number=None, column_number=None):
        super(LibraryShouldBeOmited, self).__init__(
            line_number=line_number, column_number=column_number, filename=filename,
            severity=DiagType.STYLE_INFO,
            text="Declaration of library '{library}' can be omitted" \
                    .format(library=library))

class ObjectIsNeverUsed(StaticCheckerDiag):
    "Reports an object that was created but never used"
    def __init__(self,  # pylint: disable=too-many-arguments
                 filename=None, line_number=None, column_number=None,
                 object_name=None, object_type=None):
        super(ObjectIsNeverUsed, self).__init__(
            filename=filename, line_number=line_number, column_number=column_number,
            severity=DiagType.STYLE_WARNING,
            text="{} '{}' is never used".format(str(object_type).capitalize(),
                                                object_name))

class BuilderDiag(CheckerDiagnostic):
    """
    Reports issues when checking a file whose path in not present on the
    project file
    """
    def __init__(self, # pylint: disable=too-many-arguments
                 builder_name, text, filename=None, line_number=None, column_number=None,
                 error_code=None, severity=None):
        super(BuilderDiag, self).__init__(
            checker='{}/{}'.format(CHECKER_NAME, builder_name), text=text,
            filename=filename, severity=severity, line_number=line_number,
            column_number=column_number, error_code=error_code)

    def __hash__(self):
        #  for item in ('checker', 'column_number', 'error_code',
        #          'filename', 'line_number', 'severity', 'text'):
        #      try:
        #          hash(getattr(self, item))
        #      except TypeError:
        #          print("item %s is not hashable!" % item)
        return super(CheckerDiagnostic, self).__hash__()
        #  assert False, 'hey'



class FailedToCreateProject(CheckerDiagnostic):
    """
    Reports problems when reading the project file
    """
    def __init__(self, exception):
        text = "Exception while creating server: '{}'"

        super(FailedToCreateProject, self).__init__(
            checker=None, severity=DiagType.ERROR,
            text=text.format(str(exception)))


class DependencyNotUnique(CheckerDiagnostic):
    """
    Searching for a dependency should yield a single source file
    """
    def __init__(self, filename, design_unit, actual, choices, line_number=None,
                 column_number=None):
        text = ("Returning dependency '{}' for {}, but there were {} other "
                "matches:\n{}. The selected option may not be the correct "
                "one".format(actual, design_unit, len(choices),
                             ', '.join({"'%s'" % x.filename for x in choices})))

        super(DependencyNotUnique, self).__init__(
            checker=None, filename=filename, severity=DiagType.STYLE_WARNING,
            line_number=line_number, column_number=column_number, text=text)
