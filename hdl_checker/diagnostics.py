# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.
"Diagnostics holders for checkers"

from typing import Iterable, Optional

from hdl_checker.parsers.elements.dependency_spec import (  # pylint: disable=unused-import
    BaseDependencySpec,
    RequiredDesignUnit,
)
from hdl_checker.parsers.elements.identifier import (  # pylint: disable=unused-import
    Identifier,
)
from hdl_checker.path import Path  # pylint: disable=unused-import
from hdl_checker.types import Location  # pylint: disable=unused-import
from hdl_checker.utils import HashableByKey

# pylint: disable=useless-object-inheritance

CHECKER_NAME = "HDL Checker"
STATIC_CHECKER_NAME = "HDL Checker/static"


class DiagType(object):  # pylint: disable=too-few-public-methods
    """
    Enum-like class for error types
    """

    NONE = "None"
    INFO = "Info"
    WARNING = "Warning"
    ERROR = "Error"
    STYLE_INFO = "Info (style)"
    STYLE_WARNING = "Warning (style)"
    STYLE_ERROR = "Error (style)"


class CheckerDiagnostic(HashableByKey):  # pylint: disable=too-many-instance-attributes
    """
    Base container for diagnostics
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        text,  # type: str
        checker=None,  # type: Optional[str]
        filename=None,  # type: Optional[Path]
        line_number=None,  # type: Optional[int]
        column_number=None,  # type: Optional[int]
        error_code=None,
        severity=None,
    ):

        # Checker can't be changed
        self._checker = CHECKER_NAME if checker is None else checker

        # Modifiable attributes
        self._filename = filename  # type: Optional[Path]
        self._error_code = error_code
        self._text = str(text)

        # Modifiable with rules
        self._line_number = None if line_number is None else int(line_number)
        self._column = None if column_number is None else int(column_number)
        self._severity = DiagType.ERROR if severity is None else severity

    def copy(self, **kwargs):
        """
        Returns a copy of the object replacing __init__ arguments for values
        for kwargs keys.
        """
        return CheckerDiagnostic(
            checker=kwargs.get("checker", getattr(self, "checker", None)),
            text=kwargs.get("text", getattr(self, "text", None)),
            filename=kwargs.get("filename", getattr(self, "filename", None)),
            line_number=kwargs.get("line_number", getattr(self, "line_number", None)),
            column_number=kwargs.get(
                "column_number", getattr(self, "column_number", None)
            ),
            error_code=kwargs.get("error_code", getattr(self, "error_code", None)),
            severity=kwargs.get("severity", getattr(self, "severity", None)),
        )

    def __repr__(self):
        return (
            '{}(checker="{}", filename={}, line_number={}, column_number={}, '
            "error_code={}, severity={}, text={})".format(
                self.__class__.__name__,
                repr(self.checker),
                repr(self.filename),
                repr(self.line_number),
                repr(self.column_number),
                repr(self.error_code),
                repr(self.severity),
                repr(self.text),
            )
        )

    @property
    def __hash_key__(self):
        return (
            self.filename,
            self.checker,
            self.column_number,
            self.error_code,
            self.line_number,
            self.severity,
            self.text,
        )

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
        return {
            "checker": self.checker,
            "filename": str(self.filename),
            "error_code": self.error_code,
            "text": self.text,
            "line_number": self.line_number,
            "column_number": self.column_number,
            "severity": self.severity,
        }

    @classmethod
    def fromDict(cls, state):
        "Creates a diagnostics objects from state dict"
        return cls(
            checker=state["checker"],
            filename=state["filename"],
            error_code=state["error_code"],
            text=state["text"],
            line_number=state["line_number"],
            column_number=state["column_number"],
            severity=state["severity"],
        )

    @property
    def checker(self):
        "Full checker name"
        return self._checker

    @property
    def filename(self):
        "Full checker name"
        return self._filename

    @property
    def text(self):
        "Full checker name"
        return self._text

    @property
    def error_code(self):
        "Full checker name"
        return self._error_code

    @property
    def line_number(self):
        "Diagnostics line number"
        if self._line_number is not None:
            return int(self._line_number)
        return self._line_number

    @property
    def column_number(self):
        "Diagnostics column_number"
        if self._column is not None:
            return int(self._column)
        return self._column

    @property
    def severity(self):
        "Diagnostics severity (use diagnostics.DiagType for consistency)"
        return self._severity


class PathNotInProjectFile(CheckerDiagnostic):
    """
    Reports a check request on a file whose path in not present on the project
    file
    """

    def __init__(self, path):
        super(PathNotInProjectFile, self).__init__(
            checker=CHECKER_NAME,
            filename=path,
            severity=DiagType.WARNING,
            text='Path "{}" not found in project file'.format(path),
        )


class StaticCheckerDiag(CheckerDiagnostic):
    "Base diagnostics issues from static checks"

    def __init__(  # pylint: disable=too-many-arguments
        self,
        text,
        severity,
        filename=None,
        line_number=None,
        column_number=None,
        error_code=None,
    ):

        assert severity in (
            DiagType.STYLE_INFO,
            DiagType.STYLE_WARNING,
            DiagType.STYLE_ERROR,
        ), "Static checker diags should only carry style error types"

        super(StaticCheckerDiag, self).__init__(
            checker=STATIC_CHECKER_NAME,
            text=text,
            severity=severity,
            filename=filename,
            line_number=line_number,
            column_number=column_number,
            error_code=error_code,
        )


class LibraryShouldBeOmited(StaticCheckerDiag):
    "Library declaration should be ommited"

    def __init__(self, library, filename=None, line_number=None, column_number=None):
        super(LibraryShouldBeOmited, self).__init__(
            line_number=line_number,
            column_number=column_number,
            filename=filename,
            severity=DiagType.STYLE_INFO,
            text="Declaration of library '{library}' can be omitted".format(
                library=library
            ),
        )


class ObjectIsNeverUsed(StaticCheckerDiag):
    "Reports an object that was created but never used"

    def __init__(  # pylint: disable=too-many-arguments
        self,
        filename=None,
        line_number=None,
        column_number=None,
        object_name=None,
        object_type=None,
    ):
        super(ObjectIsNeverUsed, self).__init__(
            filename=filename,
            line_number=line_number,
            column_number=column_number,
            severity=DiagType.STYLE_WARNING,
            text="{} '{}' is never used".format(
                str(object_type).capitalize(), object_name
            ),
        )


class BuilderDiag(CheckerDiagnostic):
    """
    Reports issues when checking a file whose path in not present on the
    project file
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        builder_name,
        text,
        filename=None,
        line_number=None,
        column_number=None,
        error_code=None,
        severity=None,
    ):
        super(BuilderDiag, self).__init__(
            checker="{}/{}".format(CHECKER_NAME, builder_name),
            text=text,
            filename=filename,
            severity=severity,
            line_number=line_number,
            column_number=column_number,
            error_code=error_code,
        )


class FailedToCreateProject(CheckerDiagnostic):
    """
    Reports problems when reading the project file
    """

    def __init__(self, exception):
        text = "Exception while creating server: {}"

        super(FailedToCreateProject, self).__init__(
            checker=CHECKER_NAME,
            severity=DiagType.ERROR,
            text=text.format(str(exception)),
        )


class DependencyNotUnique(CheckerDiagnostic):
    """
    Searching for a dependency should yield a single source file
    """

    def __init__(  # pylint: disable=too-many-arguments
        self, filename, dependency, choices, line_number=None, column_number=None
    ):
        # Revert to str and not Paths for the ease for sorting, which helps esp
        # when testing (order of sets depend on their hash)
        _choices = sorted(list(map(str, choices)))

        if isinstance(dependency, RequiredDesignUnit):
            text = (
                "Dependency '{}' (library={}) has {} definitions (files are {}). "
                "The selected option may not be the correct one".format(
                    dependency.name,
                    dependency.library,
                    len(_choices),
                    ", ".join(('"%s"' % x for x in _choices)),
                )
            )
        else:
            text = (
                "Inclue path '{}' has {} definitions (files are {}). "
                "The selected option may not be the correct one".format(
                    dependency.name,
                    len(_choices),
                    ", ".join(('"%s"' % x for x in _choices)),
                )
            )

        super(DependencyNotUnique, self).__init__(
            filename=filename,
            severity=DiagType.STYLE_WARNING,
            line_number=line_number,
            column_number=column_number,
            text=text,
        )


class PathLibraryIsNotUnique(CheckerDiagnostic):
    """
    Searching for a dependency should yield a single source file
    """

    def __init__(self, filename, actual, choices):
        # type: (Path, Identifier, Iterable[Identifier]) -> None
        _choices = list(choices)

        msg = []
        for library in set(_choices):
            msg.append("'{}' (x{})".format(library, _choices.count(library)))

        text = (
            "Using library '{}' for this file but its units are referenced in "
            "multiple libraries: {}".format(actual, ", ".join(msg))
        )

        super(PathLibraryIsNotUnique, self).__init__(
            filename=filename, severity=DiagType.WARNING, text=text
        )


class UnresolvedDependency(CheckerDiagnostic):
    """
    Marks dependencies that could not be resolved for a file
    """

    def __init__(self, dependency, location):
        # type: (BaseDependencySpec, Location) -> None
        if isinstance(dependency, RequiredDesignUnit):
            reference = "%s.%s" % (dependency.library or "work", dependency.name)
        else:
            reference = str(dependency.name)

        super(UnresolvedDependency, self).__init__(
            filename=dependency.owner,
            severity=DiagType.STYLE_ERROR,
            line_number=location.line,
            column_number=location.column,
            text="Unable to resolve '{}' to a path".format(reference),
        )
