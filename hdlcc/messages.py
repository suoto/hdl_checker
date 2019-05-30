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

# pylint: disable=useless-object-inheritance

CHECKER_NAME = 'HDL Code Checker'
STATIC_CHECKER_NAME = 'HDL Code Checker/static'

class ErrorType(object):  # pylint: disable=too-few-public-methods
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

class BaseMessage(object):  # pylint: disable=too-few-public-methods
    """
    Base container for an extracted message
    """
    def __init__(self, checker=CHECKER_NAME, filename=None, line_number=None,
                 column=None, error_number=None, error_type=None,
                 message=None):

        self._checker = checker
        self._filename = filename
        self._line_number = line_number
        self._column = column
        self._error_number = error_number
        self._error_type = error_type
        self._message = message

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
    def message(self):
        return self._message

class PathNotInProjectFileMessage(BaseMessage):
    """
    Message issues when checking a file whose path in not present on the
    project file
    """
    def __init__(self, path):
        super(PathNotInProjectFileMessage, self).__init__(
            checker=CHECKER_NAME, filename=path, error_type=ErrorType.WARNING,
            message='Path "{}" not found in project file'.format(path))

class StaticCheckerMessage(BaseMessage):
    def __init__(self, filename=None, line_number=None, column=None,
                 error_number=None, error_type=None, message=None):

        assert error_type in (ErrorType.STYLE_INFO, ErrorType.STYLE_WARNING,
                              ErrorType.STYLE_ERROR), \
            "Static checker messages should only carry style error types"

        super(StaticCheckerMessage, self).__init__(
            checker=STATIC_CHECKER_NAME, filename=filename,
            line_number=line_number, column=column, error_number=error_number,
            error_type=error_type, message=message)

class LibraryCanBeOmmitedMessage(StaticCheckerMessage):
    def __init__(self, filename=None, line_number=None, column=None,
                 library=None):
        super(LibraryCanBeOmmitedMessage, self).__init__(
            line_number=line_number, column=column, filename=filename,
            error_type=ErrorType.STYLE_WARNING,
            message="Declaration of library '{library}' can be "
                    "omitted".format(library=library))


class UnusedObjectMessage(StaticCheckerMessage):
    def __init__(self, filename=None, line_number=None, column=None,
                 object_name=None, object_type=None):
        super(UnusedObjectMessage, self).__init__(
            filename=filename, line_number=line_number, column=column,
            error_type=ErrorType.STYLE_WARNING,
            message="{} '{}' is never used".format(object_type, object_name))

            #  , error_type=ErrorType.WARNING,
            #  message='Path "{}" not found in project file'.format(path))

            #      'checker'        : 'HDL Code Checker/static',
            #      'line_number'    : lnum,
            #      'column'         : match.start(match.lastindex - 1) + 1,
            #      'filename'       : None,
            #      'error_number'   : '0',
            #      'error_type'     : 'W',
            #      'error_subtype'  : '',
            #      'error_message'  : "%s: %s" % (_dict['tag'].upper(), _dict['text'])
