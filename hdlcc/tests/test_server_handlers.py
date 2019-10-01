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

# pylint: disable=function-redefined
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=invalid-name

import logging
import os
import os.path as p

import six
from webtest import TestApp  # type: ignore

from nose2.tools import such  # type: ignore

from hdlcc.tests import assertCountEqual, disableVunit, getTestTempPath, setupTestSuport

import hdlcc
import hdlcc.handlers as handlers
from hdlcc.diagnostics import (
    CheckerDiagnostic,
    DiagType,
    ObjectIsNeverUsed,
    StaticCheckerDiag,
)
from hdlcc.parsers.elements.identifier import Identifier
from hdlcc.path import Path

try:  # Python 3.x
    import unittest.mock as mock  # pylint: disable=import-error, no-name-in-module
except ImportError:  # Python 2.x
    import mock  # type: ignore


TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.abspath(p.join(TEST_TEMP_PATH, "test_project"))

SERVER_LOG_LEVEL = os.environ.get("SERVER_LOG_LEVEL", "INFO")

_logger = logging.getLogger(__name__)
HDLCC_BASE_PATH = p.abspath(p.join(p.dirname(__file__), "..", ".."))


def _path(*args):
    # type: (str) -> str
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return p.join(TEST_TEMP_PATH, *args)


with such.A("hdlcc bottle app") as it:
    # Workaround for Python 2.x and 3.x differences
    if six.PY2:
        it.assertCountEqual = assertCountEqual(it)

    @it.has_setup
    def setup():
        setupTestSuport(TEST_TEMP_PATH)

        it.project_file = p.join(TEST_PROJECT, "vimhdl.prj")
        it.app = TestApp(handlers.app)

    @it.should("get diagnose info without any project")
    @disableVunit
    def test():
        reply = it.app.post_json("/get_diagnose_info")
        it.assertCountEqual(
            reply.json["info"],
            [
                u"hdlcc version: %s" % hdlcc.__version__,
                u"Server PID: %d" % os.getpid(),
                u"Builder: none",
            ],
        )

    @it.should("get diagnose info with an existing project file")  # type: ignore
    @disableVunit
    def test():
        reply = it.app.post("/get_diagnose_info", {"project_file": it.project_file})

        _logger.info("Reply is %s", reply.json["info"])

        it.assertCountEqual(
            reply.json["info"],
            [
                u"hdlcc version: %s" % hdlcc.__version__,
                u"Server PID: %d" % os.getpid(),
                u"Builder: none",
            ],
        )

    @it.should("get diagnose info with a non existing project file")  # type: ignore
    @disableVunit
    def test():
        open(_path("foo_bar.prj"), "w").write("")

        reply = it.app.post(
            "/get_diagnose_info", {"project_file": _path("foo_bar.prj")}
        )

        _logger.info("Reply is %s", reply.json["info"])
        it.assertCountEqual(
            reply.json["info"],
            [
                u"hdlcc version: %s" % hdlcc.__version__,
                u"Server PID: %d" % os.getpid(),
                u"Builder: none",
            ],
        )

    @it.should("shutdown the server when requested")  # type: ignore
    @disableVunit
    def test():
        open(_path("some_project"), "w").write("")
        # Ensure the server is active
        reply = it.app.post(
            "/get_diagnose_info", {"project_file": _path("some_project")}
        )
        it.assertEqual(reply.status, "200 OK")

        # Send a request to shutdown the server and check if it
        # calls the terminate process method
        pids = []

        with mock.patch("hdlcc.handlers.terminateProcess", pids.append):
            reply = it.app.post("/shutdown")

        it.assertEqual(pids, [os.getpid()])

    @it.should("rebuild the project with directory cleanup")  # type: ignore
    @disableVunit
    def test():
        project_file = _path("hello.prj")
        open(_path("hello.prj"), "w").write("")
        server = mock.MagicMock()

        servers = mock.MagicMock()
        servers.__getitem__.side_effect = {
            Path(p.dirname(project_file)): server
        }.__getitem__

        with mock.patch.object(hdlcc.handlers, "servers", servers):
            it.app.post("/rebuild_project", {"project_file": project_file})

        # Check the object was removed from the servers list
        servers.__delitem__.assert_called_once_with(project_file)
        # Check the original server cleaned things up
        server.clean.assert_called_once()

    @it.should("get messages with content")  # type: ignore
    def test():
        data = {
            "project_file": it.project_file,
            "path": p.join(TEST_PROJECT, "another_library", "foo.vhd"),
            "content": "-- TODO: Nothing to see here",
        }

        ui_reply = it.app.post("/get_ui_messages", data)
        reply = it.app.post("/get_messages_by_path", data)

        _logger.info("UI reply: %s", ui_reply)
        _logger.info("Reply: %s", reply)

        messages = [CheckerDiagnostic.fromDict(x) for x in reply.json["messages"]]

        it.assertIn(data["path"], [x.filename for x in messages])

        expected = StaticCheckerDiag(
            filename=data["path"],
            line_number=1,
            column_number=4,
            text="TODO: Nothing to see here",
            severity=DiagType.STYLE_INFO,
        )

        it.assertIn(expected, messages)

    @it.should("get messages by path")  # type: ignore
    def test():
        filename = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")
        data = {"project_file": it.project_file, "path": filename}

        ui_reply = it.app.post("/get_ui_messages", data)
        reply = it.app.post("/get_messages_by_path", data)

        _logger.info("UI reply: %s", ui_reply)
        _logger.info("Reply: %s", reply)

        messages = [CheckerDiagnostic.fromDict(x) for x in reply.json["messages"]]

        it.assertCountEqual(
            messages,
            [
                ObjectIsNeverUsed(
                    filename=filename,
                    line_number=27,
                    column_number=12,
                    object_type="signal",
                    object_name="clk_enable_unused",
                )
            ],
        )

    @it.should("get source dependencies")  # type: ignore
    @disableVunit
    def test():
        data = {
            "project_file": it.project_file,
            "path": p.join(TEST_PROJECT, "another_library", "foo.vhd"),
        }

        for _ in range(10):
            ui_reply = it.app.post("/get_ui_messages", data)
            reply = it.app.post("/get_dependencies", data)

            _logger.info("UI reply: %s", ui_reply)
            _logger.info("Reply: %s", reply)

        dependencies = reply.json["dependencies"]

        _logger.info("Dependencies: %s", ", ".join(dependencies))

        it.assertCountEqual(
            ["ieee.std_logic_1164", "ieee.numeric_std", "basic_library.clock_divider"],
            dependencies,
        )

    @it.should("get source build sequence")  # type: ignore
    def test():
        data = {
            "project_file": it.project_file,
            "path": p.join(TEST_PROJECT, "another_library", "foo.vhd"),
        }

        @property
        def builtin_libraries(_):
            return {Identifier("ieee")}

        such.unittest.TestCase.maxDiff = None
        with mock.patch.object(
            hdlcc.builders.base_builder.BaseBuilder,
            "builtin_libraries",
            builtin_libraries,
        ):
            reply = it.app.post("/get_build_sequence", data)
            #  reply = it.app.post("/shutdown")
            sequence = reply.json["sequence"]

        _logger.info("Sequence: %s", sequence)

        very_common_pkg = p.join(TEST_PROJECT, "basic_library", "very_common_pkg.vhd")
        package_with_constants = p.join(
            TEST_PROJECT, "basic_library", "package_with_constants.vhd"
        )
        clock_divider = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")

        it.assertEqual(
            sequence,
            [
                "%s (library: basic_library)" % very_common_pkg,
                "%s (library: basic_library)" % package_with_constants,
                "%s (library: basic_library)" % clock_divider,
            ],
        )


it.createTests(globals())
