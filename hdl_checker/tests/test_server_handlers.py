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

# pylint: disable=function-redefined
# pylint: disable=missing-docstring
# pylint: disable=protected-access
# pylint: disable=invalid-name

import logging
import os
import os.path as p

from mock import MagicMock, patch

from webtest import TestApp  # type: ignore # pylint: disable=import-error

from nose2.tools import such  # type: ignore

from hdl_checker.tests import (
    disableVunit,
    getTestTempPath,
    setupTestSuport,
)

import hdl_checker
import hdl_checker.handlers as handlers
from hdl_checker.diagnostics import CheckerDiagnostic, DiagType, StaticCheckerDiag
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path

TEST_TEMP_PATH = getTestTempPath(__name__)
TEST_PROJECT = p.abspath(p.join(TEST_TEMP_PATH, "test_project"))

SERVER_LOG_LEVEL = os.environ.get("SERVER_LOG_LEVEL", "INFO")

_logger = logging.getLogger(__name__)
HDL_CHECKER_BASE_PATH = p.abspath(p.join(p.dirname(__file__), "..", ".."))


def _path(*args):
    # type: (str) -> str
    "Helper to reduce foorprint of p.join(TEST_TEMP_PATH, *args)"
    return p.join(TEST_TEMP_PATH, *args)


with such.A("hdl_checker bottle app") as it:

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
                u"hdl_checker version: %s" % hdl_checker.__version__,
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
                u"hdl_checker version: %s" % hdl_checker.__version__,
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
                u"hdl_checker version: %s" % hdl_checker.__version__,
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

        with patch("hdl_checker.handlers.terminateProcess", pids.append):
            reply = it.app.post("/shutdown")

        it.assertEqual(pids, [os.getpid()])

    @it.should("rebuild the project with directory cleanup")  # type: ignore
    @disableVunit
    def test():
        project_file = _path("hello.prj")
        open(_path("hello.prj"), "w").write("")
        server = MagicMock()

        servers = MagicMock()
        servers.__getitem__.side_effect = {
            Path(p.dirname(project_file)): server
        }.__getitem__

        with patch.object(hdl_checker.handlers, "servers", servers):
            it.app.post("/rebuild_project", {"project_file": project_file})

        # Check the object was removed from the servers list
        servers.__delitem__.assert_called_once_with(Path(p.dirname(project_file)))
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
            line_number=0,
            column_number=3,
            text="TODO: Nothing to see here",
            severity=DiagType.STYLE_INFO,
        )

        it.assertIn(expected, messages)

    @it.should("get messages by path")  # type: ignore
    @patch(
        "hdl_checker.handlers.Server.getMessagesByPath",
        return_value=[CheckerDiagnostic(text="some text")],
    )
    def test(meth):
        filename = p.join(TEST_PROJECT, "basic_library", "clock_divider.vhd")
        data = {"project_file": it.project_file, "path": filename}

        ui_reply = it.app.post("/get_ui_messages", data)
        reply = it.app.post("/get_messages_by_path", data)

        meth.assert_called_once()

        _logger.info("UI reply: %s", ui_reply)
        _logger.info("Reply: %s", reply)

        it.assertCountEqual(
            reply.json["messages"], [CheckerDiagnostic(text="some text").toDict()]
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
            return (Identifier("ieee"),)

        such.unittest.TestCase.maxDiff = None
        with patch.object(
            hdl_checker.builders.base_builder.BaseBuilder,
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
