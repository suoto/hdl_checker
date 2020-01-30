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
"Handlers for hdl_checker server"

import logging
import os
import os.path as p
import signal
import tempfile
from multiprocessing import Queue
from typing import Any, Dict, List, Optional, Tuple

import bottle  # type: ignore

from hdl_checker import __version__ as version
from hdl_checker.base_server import BaseServer
from hdl_checker.builders.fallback import Fallback
from hdl_checker.path import Path
from hdl_checker.types import ConfigFileOrigin
from hdl_checker.utils import terminateProcess

_logger = logging.getLogger(__name__)

app = bottle.Bottle()  # pylint: disable=invalid-name


class Server(BaseServer):
    """
    HDL Checker project builder class
    """

    def __init__(self, *args, **kwargs):
        # type: (...) -> None
        self._msg_queue = Queue()  # type: Queue[Tuple[str, str]]
        super(Server, self).__init__(*args, **kwargs)

    def _handleUiInfo(self, message):
        # type: (...) -> Any
        self._msg_queue.put(("info", message))

    def _handleUiWarning(self, message):
        # type: (...) -> Any
        self._msg_queue.put(("warning", message))

    def _handleUiError(self, message):
        # type: (...) -> Any
        self._msg_queue.put(("error", message))

    def getQueuedMessages(self):
        # type: (...) -> Any
        "Returns queued UI messages"
        while not self._msg_queue.empty():  # pragma: no cover
            yield self._msg_queue.get()


def _getServerByProjectFile(project_file):
    # type: (Optional[str]) -> Server
    """
    Returns the Server object that corresponds to the given project file. If
    the object doesn't exists yet it gets created and then returned
    """
    _logger.debug("project_file: %s", project_file)
    if isinstance(project_file, str) and project_file.lower() == "none":
        project_file = None

    # If there's no project file to use, create a temporary path to use
    if project_file is None:
        root_dir = Path(tempfile.mkdtemp())
    else:
        root_dir = Path(p.dirname(project_file))

    if root_dir not in servers:
        _logger.info("Creating server for %s (root=%s)", project_file, root_dir)
        try:
            project = Server(root_dir=root_dir)
            if project_file is not None:
                project.setConfig(project_file, origin=ConfigFileOrigin.user)
            _logger.debug("Created new project server for '%s'", project_file)
        except (IOError, OSError):
            _logger.info("Failed to create checker, reverting to fallback")
            project = Server(None)

        servers[root_dir] = project
    return servers[root_dir]


def _exceptionWrapper(func):
    """
    Wraps func to log exception to the standard logger
    """

    def _wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:  # pragma: no cover
            _logger.exception("Error running '%s'", func.__name__)
            raise

    return _wrapper


def setupSignalHandlers():
    # type: (...) -> Any
    """
    Configures signal handlers that will be called when exiting Python
    shell
    """

    def signalHandler(sig, _):
        "Handle to disable hdl_checker server"
        _logger.info("Handling signal %s", repr(sig))
        import sys

        sys.exit()

    for sig in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(sig, signalHandler)


def _getProjectDiags(project_file):
    # type: (str) -> Any
    """
    Get project specific diagnose
    """
    diags = []  # type: List[str]
    server = _getServerByProjectFile(project_file)

    if isinstance(server.builder, Fallback):
        diags += ["Builder: none"]
    else:
        diags += ["Builder: %s" % server.builder.builder_name]

    return diags


@app.post("/get_diagnose_info")
@_exceptionWrapper
def getDiagnoseInfo():
    # type: (...) -> Any
    """
    Collects misc diagnose info for the clients
    """
    _logger.info("Collecting diagnose info")
    project_file = bottle.request.forms.get("project_file")  # pylint: disable=no-member
    response = ["hdl_checker version: %s" % version, "Server PID: %d" % os.getpid()]

    response += _getProjectDiags(project_file)

    _logger.info("Diagnose info collected:")
    for diag in response:
        _logger.info(" - %s", diag)

    return {"info": response}


@app.post("/get_messages_by_path")
@_exceptionWrapper
def getMessagesByPath():
    # type: (...) -> Any
    """
    Get messages for a given projec_file/path pair
    """
    project_file = bottle.request.forms.get("project_file")  # pylint: disable=no-member
    path = Path(bottle.request.forms.get("path"))  # pylint: disable=no-member
    content = bottle.request.forms.get("content", None)  # pylint: disable=no-member

    _logger.debug(
        "Getting messages for '%s', '%s', %s",
        project_file,
        path,
        "no content" if content is None else "with content",
    )

    server = _getServerByProjectFile(project_file)
    if content is None:
        messages = server.getMessagesByPath(path)
    else:
        messages = server.getMessagesWithText(path, content)

    _logger.info("messages: %s", [x.toDict() for x in messages])

    # Messages at this point need to be serializable so that bottle can send
    # them over
    return {"messages": tuple(x.toDict() for x in messages)}


@app.post("/get_ui_messages")
@_exceptionWrapper
def getUiMessages():
    # type: (...) -> Any
    """
    Get messages for a given projec_file/path pair
    """

    project_file = bottle.request.forms.get("project_file")  # pylint: disable=no-member
    server = _getServerByProjectFile(project_file)

    ui_messages = list(server.getQueuedMessages())

    if not ui_messages:  # pragma: no cover
        _logger.debug("Project '%s' has no UI messages", project_file)
    else:  # pragma: no cover
        _logger.info("Project '%s' UI messages:", project_file)

    for msg in ui_messages:  # pragma: no cover
        _logger.info(msg)

    response = {"ui_messages": ui_messages}

    return response


@app.post("/rebuild_project")
@_exceptionWrapper
def rebuildProject():
    # type: (...) -> Any
    """
    Rebuilds the current project
    """
    _logger.info("Rebuilding project")
    project_file = bottle.request.forms.get("project_file")  # pylint: disable=no-member
    server = _getServerByProjectFile(project_file)
    server.clean()
    _logger.debug("Removing and recreating server object")
    root_dir = Path(p.dirname(project_file))
    del servers[root_dir]
    _getServerByProjectFile(project_file)


@app.post("/shutdown")
@_exceptionWrapper
def shutdownServer():
    # type: (...) -> Any
    """
    Terminates the current process to shutdown the server
    """
    _logger.info("Shutting down server")
    terminateProcess(os.getpid())


@app.post("/get_dependencies")
@_exceptionWrapper
def getDependencies():
    # type: (...) -> Any
    """
    Returns the direct dependencies of a given source path
    """
    project_file = bottle.request.forms.get("project_file")  # pylint: disable=no-member
    path = Path(bottle.request.forms.get("path"))  # pylint: disable=no-member

    _logger.debug("Getting dependencies for '%s', '%s'", project_file, path)

    server = _getServerByProjectFile(project_file)
    content = []
    for dependency in server.database.getDependenciesByPath(path):
        content.append(
            "%s.%s" % (dependency.library.display_name, dependency.name.display_name)
        )

    _logger.debug("Found %d dependencies", len(content))

    return {"dependencies": content}


@app.post("/get_build_sequence")
@_exceptionWrapper
def getBuildSequence():
    # type: (...) -> Any
    """
    Returns the build sequence of a given source path
    """
    project_file = bottle.request.forms.get("project_file")  # pylint: disable=no-member
    path = Path(bottle.request.forms.get("path"))  # pylint: disable=no-member

    _logger.debug("Getting build sequence for '%s', '%s'", project_file, path)

    server = _getServerByProjectFile(project_file)
    server._updateConfigIfNeeded()

    return {
        "sequence": tuple(
            "%s (library: %s)" % (path, library)
            for library, path in server.database.getBuildSequence(
                path, server.builder.builtin_libraries
            )
        )
    }


#  We'll store a dict to store differents hdl_checker objects
servers = {}  # type: Dict[Path, Server] # pylint: disable=invalid-name
setupSignalHandlers()
