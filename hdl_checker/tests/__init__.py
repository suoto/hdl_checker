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

# pylint: disable=missing-docstring
# pylint: disable=useless-object-inheritance

import functools
import logging
import os
import os.path as p
import shutil
import subprocess as subp
import time
from multiprocessing import Queue
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import mock
import six
import unittest2  # type: ignore
from parameterized import parameterized_class  # type: ignore
from pygls import uris
from unittest2 import TestCase

from hdl_checker import exceptions
from hdl_checker.base_server import BaseServer
from hdl_checker.builders.base_builder import BaseBuilder
from hdl_checker.diagnostics import CheckerDiagnostic
from hdl_checker.parsers.elements.dependency_spec import RequiredDesignUnit
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path
from hdl_checker.types import FileType
from hdl_checker.utils import ON_LINUX, ON_WINDOWS, removeDuplicates, samefile

_logger = logging.getLogger(__name__)


MockDep = Union[Tuple[str], Tuple[str, str]]


class DummyServer(BaseServer):
    "Class for testing BaseServer"
    _server_index = 0

    def __init__(self, *args, **kwargs):
        _logger.info("Creating server %d", DummyServer._server_index)
        self._msg_queue = Queue()  # type: Queue[Tuple[str, str]]
        self._ui_handler = logging.getLogger("server %d/UI" % DummyServer._server_index)
        DummyServer._server_index += 1
        super(DummyServer, self).__init__(*args, **kwargs)

    def _handleUiInfo(self, message):
        self._msg_queue.put(("info", message))
        self._ui_handler.info("[UI INFO]: %s", message)

    def _handleUiWarning(self, message):
        self._msg_queue.put(("warning", message))
        self._ui_handler.info("[UI WARNING]: %s", message)

    def _handleUiError(self, message):
        self._msg_queue.put(("error", message))
        self._ui_handler.info("[UI ERROR]: %s", message)

    def getUiMessages(self):
        while not self._msg_queue.empty():
            yield self._msg_queue.get()


class SourceMock(object):
    _logger = logging.getLogger("SourceMock")
    base_path = ""

    def __init__(
        self,
        design_units,  # type: Iterable[Dict[str, str]]
        library=None,  # type: str
        dependencies=None,  # type: Iterable[MockDep]
        filename=None,  # type: Optional[str]
    ):

        self._design_units = list(design_units or [])

        if filename is not None:
            self._filename = Path(p.join(self.base_path, filename))
        else:
            library = "lib_not_set" if library is None else library
            self._filename = Path(
                p.join(
                    self.base_path,
                    library,
                    "_{}.vhd".format(self._design_units[0]["name"]),
                )
            )

        self.filetype = FileType.fromPath(self.filename)
        #  self.abspath = p.abspath(self.filename)
        self.flags = []  # type: ignore

        self.library = library
        self._dependencies = []  # type: List[RequiredDesignUnit]
        for dep_spec in dependencies or []:
            _name = dep_spec[0]
            _library = "work"

            try:
                _library, _name = dep_spec  # type: ignore
            except ValueError:
                pass

            self._dependencies.append(
                RequiredDesignUnit(
                    self._filename,
                    Identifier(_name, False),
                    Identifier(_library, False),
                )
            )

        self._createMockFile()

    @property
    def filename(self):
        # type: () -> Path
        return self._filename

    def getLibraries(self):
        return removeDuplicates([x.library for x in self._dependencies])

    def _createMockFile(self):
        # type: () -> None
        self._logger.debug("Creating mock file: %s", self)
        libs = self.getLibraries()

        lines = []

        for lib in libs:
            lines.append("library {0};".format(lib.display_name))

        for dependency in self._dependencies:
            if dependency.library is not None:
                dependency_name = dependency.library.display_name
            else:
                dependency_name = "work"
            lines.append(
                "use {0}.{1};".format(dependency_name, dependency.name.display_name)
            )

        # Separate if there was libraries already added
        if lines:
            lines.append("")

        for design_unit in self._design_units:
            type_ = design_unit["type"]
            name = design_unit["name"]

            lines.append("{0} {1} is".format(type_, name))
            lines.append("")
            lines.append("end {0} {1};".format(type_, name))
            lines.append("")

        for i, line in enumerate(lines, 1):
            self._logger.debug("%2d | %s", i, line)

        try:
            os.makedirs(p.dirname(self.filename.name))
        except OSError:
            pass

        with open(self.filename.name, "w") as fd:
            fd.write("\n".join(lines))

    def __repr__(self):
        return (
            "{}(library='{}', design_units={}, dependencies={}, "
            "filename={}".format(
                self.__class__.__name__,
                self.library,
                self._design_units,
                self._dependencies,
                self.filename,
            )
        )

    def getmtime(self):
        return p.getmtime(self.filename)

    def getDesignUnits(self):
        return self._design_units

    def getDependencies(self):
        return self._dependencies

    def getRawSourceContent(self):
        return open(self.filename).read()


class MockBuilder(BaseBuilder):  # pylint: disable=abstract-method
    _logger = logging.getLogger("MockBuilder")
    builder_name = "mock_builder"
    file_types = (FileType.vhdl,)

    def __init__(self, work_folder, *args, **kwargs):
        # type: (...) -> None
        self._work_folder = work_folder  # type: Path
        if not p.exists(self._work_folder.name):
            os.makedirs(self._work_folder.name)

        super(MockBuilder, self).__init__(work_folder, *args, **kwargs)

    def _makeRecords(self, _):  # pragma: no cover
        return []

    def _shouldIgnoreLine(self, line):  # pragma: no cover
        return True

    def _checkEnvironment(self):
        return

    @staticmethod
    def isAvailable():
        return True

    def _buildSource(self, path, library, flags=None):
        self._logger.debug(
            "Building path=%s, library=%s, flags=%s", path, library, flags
        )
        return [], []

    def _createLibrary(self, library):  # pylint: disable=unused-argument
        pass

    def _parseBuiltinLibraries(self):
        # type: (...) -> Any
        return (
            Identifier("ieee", case_sensitive=False),
            Identifier("std", case_sensitive=False),
        )


class FailingBuilder(MockBuilder):  # pylint: disable=abstract-method
    _logger = logging.getLogger("FailingBuilder")
    builder_name = "FailingBuilder"

    def _checkEnvironment(self):
        raise exceptions.SanityCheckError(self.builder_name, "Fake error")


disableVunit = mock.patch("hdl_checker.builder_utils.foundVunit", lambda: False)


class PatchBuilder(object):
    def __init__(self, meth=None):
        def getBuilderByName(name):
            "Returns the builder class given a string name"
            from hdl_checker.builders.msim import MSim
            from hdl_checker.builders.ghdl import GHDL
            from hdl_checker.builders.xvhdl import XVHDL
            from hdl_checker.builders.fallback import Fallback

            # Check if the builder selected is implemented and create the
            # builder attribute
            _logger.info("Getting builder class for %s", name)
            if name == MockBuilder.builder_name:
                return MockBuilder
            if name == "msim":
                return MSim
            if name == "xvhdl":
                return XVHDL
            if name == "ghdl":
                return GHDL

            return Fallback

        self.meth = meth
        self.patches = (
            mock.patch(
                "hdl_checker.base_server.getPreferredBuilder",
                side_effect=[MockBuilder,],
            ),
            mock.patch("hdl_checker.base_server.getBuilderByName", getBuilderByName),
            disableVunit,
        )

    def __enter__(self):
        _logger.info("Starting patches")
        list(x.start() for x in self.patches)

    def __exit__(self, *args, **kwargs):
        _logger.info("Stopping patches")
        list(x.stop() for x in self.patches)

    def __call__(self, *args, **kwargs):
        self.__enter__()
        try:
            if self.meth is not None:
                yield self.meth()
            else:
                yield None
        except:
            _logger.exception("Failed to run %s", self.meth)
            raise
        finally:
            self.__exit__()


def sanitizePath(*args):
    """
    Join args with pathsep, gets the absolute path and normalizes
    """
    return p.normpath(
        p.abspath(p.join(*args))  # pylint: disable=no-value-for-parameter
    )


def assertSameFile(it):  # pylint: disable=invalid-name
    def wrapper(first, second, msg=None):
        try:
            os.stat(first)
        except TypeError:
            it.fail("Invalid first argument of type {}".format(type(first)))
        try:
            os.stat(second)
        except TypeError:
            it.fail("Invalid first argument of type {}".format(type(second)))
        if not samefile(p.abspath(first), p.abspath(second)):
            _msg = "" if msg is None else "{}\n".format(msg)
            it.fail(
                "{}Paths '{}' and '{}' differ".format(
                    _msg, p.abspath(first), p.abspath(second)
                )
            )

    return wrapper


#  def assertCountEqual(it):  # pylint: disable=invalid-name

#      assert six.PY2, "Only needed on Python2"

#      def wrapper(first, second, msg=None):
#          temp = list(second)  # make a mutable copy
#          not_found = []
#          for elem in first:
#              try:
#                  temp.remove(elem)
#              except ValueError:
#                  not_found.append(elem)

#          error_details = []

#          if not_found:
#              error_details += [
#                  "Second list is missing item {}".format(x) for x in not_found
#              ]

#          error_details += ["First list is missing item {}".format(x) for x in temp]

#          if error_details:
#              # Add user message at the top
#              error_details = [msg] + error_details
#              error_details += ["", "Lists {} and {} differ".format(first, second)]
#              it.fail("\n".join([str(x) for x in error_details]))

#      return wrapper


def writeListToFile(filename, _list):  # pragma: no cover
    "Well... writes '_list' to 'filename'. This is for testing only"
    # Wait a little bit to force the timestamp rad via os.path.getmtime to
    # change
    time.sleep(0.1)
    open(filename, mode="w").write("\n".join([str(x) for x in _list]))

    for i, line in enumerate(_list):
        _logger.debug("%2d | %s", i + 1, line)


if not ON_WINDOWS:
    TEST_ENVS = {
        "ghdl": os.environ["GHDL_PATH"],
        "msim": os.environ["MODELSIM_PATH"],
        "xvhdl": os.environ["XSIM_PATH"],
        "fallback": None,
    }
else:
    TEST_ENVS = {"fallback": None}


def parametrizeClassWithBuilders(cls):
    cls.assertSameFile = assertSameFile(cls)

    keys = ["builder_name", "builder_path"]
    values = []
    for name, path in TEST_ENVS.items():
        values += [(name, path)]

    return parameterized_class(keys, values)(cls)


def getTestTempPath(name):
    # type: (str) -> str
    name = name.replace(".", "_")
    path = p.abspath(p.join(os.environ["TOX_ENV_DIR"], "tmp", name))

    # Create a path for each test to allow running multiple tests concurrently
    i = 0
    while p.exists(path):
        path = p.abspath(p.join(os.environ["TOX_ENV_DIR"], "tmp", "%s_%d" % (name, i)))
        i += 1

    if not p.exists(path):
        os.makedirs(path)
    return path


def setupTestSuport(path):
    # type: (str) -> None
    """Copy contents of .ci/test_support_path/ to the given path"""
    _logger.info("Setting up test support at %s", path)

    test_support_path = os.environ["CI_TEST_SUPPORT_PATH"]

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


def logIterable(msg, iterable, func):
    # type: (str, Iterable[Any], Callable) -> None
    func(msg)
    for i, item in enumerate(iterable, 1):
        func("- {:2d} {}".format(i, item))


def windowsOnly(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not ON_WINDOWS:
            return unittest2.skip("Windows only test")
        return func(*args, **kwargs)

    return wrapper


def linuxOnly(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not ON_LINUX:
            return unittest2.skip("Linux only test")
        return func(*args, **kwargs)

    return wrapper


def toCheckerDiagnostic(uri: str, diags: Any) -> Iterable[CheckerDiagnostic]:
    for diag in diags:
        yield CheckerDiagnostic(
            text=diag.message,
            checker=diag.source,
            filename=uris.to_fs_path(uri),
            line_number=diag.range.start.line,
            column_number=diag.range.start.character,
            error_code=diag.code,
            severity="Error",
        )
