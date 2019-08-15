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
"Handlers for hdlcc server"

import json
import logging
import os
import signal
from multiprocessing import Queue
from typing import Dict

import bottle

from hdlcc import __version__ as version
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import Fallback, getWorkingBuilders
from hdlcc.config_generators import getGeneratorByName
from hdlcc.hdlcc_base import HdlCodeCheckerBase
from hdlcc.utils import terminateProcess

_logger = logging.getLogger(__name__)

app = bottle.Bottle()  # pylint: disable=invalid-name


class HdlCodeCheckerServer(HdlCodeCheckerBase):
    """
    HDL Code Checker project builder class
    """
    def __init__(self, *args, **kwargs):
        self._msg_queue = Queue()
        super(HdlCodeCheckerServer, self).__init__(*args, **kwargs)

    def _handleUiInfo(self, message):
        self._msg_queue.put(("info", message))

    def _handleUiWarning(self, message):
        self._msg_queue.put(("warning", message))

    def _handleUiError(self, message):
        self._msg_queue.put(("error", message))

    def getQueuedMessages(self):
        "Returns queued UI messages"
        while not self._msg_queue.empty():  # pragma: no cover
            yield self._msg_queue.get()


def _getServerByProjectFile(project_file):
    """
    Returns the HdlCodeCheckerServer object that corresponds to the given
    project file. If the object doesn't exists yet it gets created and
    then returned
    """
    if isinstance(project_file, str) and project_file.lower() == 'none':
        project_file = None

    if project_file not in servers:
        try:
            project = HdlCodeCheckerServer(project_file)
            _logger.debug("Created new project server for '%s'", project_file)
        except (IOError, OSError) as exc:
            _logger.info("Failed to create checker, reverting to fallback")
            project = HdlCodeCheckerServer(None)

        servers[project_file] = project
    return servers[project_file]


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
    """
    Configures signal handlers that will be called when exiting Python
    shell
    """
    def signalHandler(sig, _):
        "Handle to disable hdlcc server"
        _logger.info("Handling signal %s", repr(sig))
        import sys
        sys.exit()

    for sig in [signal.SIGTERM,
                signal.SIGINT]:
        signal.signal(sig, signalHandler)


def _getProjectDiags(project_file):
    """
    Get project specific diagnose
    """
    diags = []
    server = _getServerByProjectFile(project_file)

    if server.config_parser.isParsing():
        diags += ["Builder: <unknown> (config file parsing is underway)"]
    elif isinstance(server.builder, Fallback):
        diags += ["Builder: none"]
    else:
        diags += ["Builder: %s" % server.builder.builder_name]

    return diags


@app.post('/get_diagnose_info')
@_exceptionWrapper
def getDiagnoseInfo():
    """
    Collects misc diagnose info for the clients
    """
    _logger.info("Collecting diagnose info")
    project_file = bottle.request.forms.get('project_file')
    response = ["hdlcc version: %s" % version,
                "Server PID: %d" % os.getpid()]

    response += _getProjectDiags(project_file)

    _logger.info("Diagnose info collected:")
    for diag in response:
        _logger.info(" - %s", diag)

    return {'info': response}


@app.post('/run_config_generator')
@_exceptionWrapper
def runConfigGenerator():
    """
    Runs the config generator
    request should have
        - 'generator': generator's class name
        - 'args', 'kwargs': arguments to be passed to the generator constructor
    """
    name = bottle.request.forms.get('generator', None)
    args = json.loads(bottle.request.forms.get('args'))
    kwargs = json.loads(bottle.request.forms.get('kwargs'))

    _logger.info("Running config generator %s(%s, %s)",
                 repr(name), repr(args), repr(kwargs))

    kwargs['builders'] = list(getWorkingBuilders())

    _logger.debug("Running config generator: %s(%s, %s)", name, args, kwargs)
    generator = getGeneratorByName(name)(*args, **kwargs)
    content = generator.generate()

    return {'content': content}


@app.post('/on_buffer_visit')
@_exceptionWrapper
def onBufferVisit():
    "Hook for doing actions related to visiting a buffer"
    project_file = bottle.request.forms.get('project_file')
    path = bottle.request.forms.get('path')
    _logger.debug("Buffer visited is ('%s') '%s'", project_file, path)

    server = _getServerByProjectFile(project_file)
    server.onBufferVisit(path)

    return {}


@app.post('/get_messages_by_path')
@_exceptionWrapper
def getMessagesByPath():
    """
    Get messages for a given projec_file/path pair
    """
    project_file = bottle.request.forms.get('project_file')
    path = bottle.request.forms.get('path')
    content = bottle.request.forms.get('content', None)

    _logger.debug("Getting messages for '%s', '%s', %s", project_file, path,
                  "no content" if content is None else "with content")

    server = _getServerByProjectFile(project_file)
    if content is None:
        messages = server.getMessagesByPath(path)
    else:
        messages = server.getMessagesWithText(path, content)

    # Messages at this point need to be serializable so that bottle can send
    # them over
    return {'messages': [x.toDict() for x in messages]}


@app.post('/get_ui_messages')
@_exceptionWrapper
def getUiMessages():
    """
    Get messages for a given projec_file/path pair
    """

    project_file = bottle.request.forms.get('project_file')
    server = _getServerByProjectFile(project_file)

    ui_messages = list(server.getQueuedMessages())

    if not ui_messages:  # pragma: no cover
        _logger.debug("Project '%s' has no UI messages", project_file)
    else:  # pragma: no cover
        _logger.info("Project '%s' UI messages:", project_file)

    for msg in ui_messages:  # pragma: no cover
        _logger.info(msg)

    response = {'ui_messages': ui_messages}

    return response


@app.post('/rebuild_project')
@_exceptionWrapper
def rebuildProject():
    """
    Rebuilds the current project
    """
    _logger.info("Rebuilding project")
    project_file = bottle.request.forms.get('project_file')
    server = _getServerByProjectFile(project_file)
    server.clean()
    _logger.debug("Removing and recreating server object")
    del servers[project_file]
    _getServerByProjectFile(project_file)


@app.post('/shutdown')
@_exceptionWrapper
def shutdownServer():
    """
    Terminates the current process to shutdown the server
    """
    _logger.info("Shutting down server")
    terminateProcess(os.getpid())


@app.post('/get_dependencies')
@_exceptionWrapper
def getDependencies():
    """
    Returns the direct dependencies of a given source path
    """
    project_file = bottle.request.forms.get('project_file')
    path = bottle.request.forms.get('path')

    _logger.debug("Getting dependencies for '%s', '%s'", project_file, path)

    server = _getServerByProjectFile(project_file)
    source, _ = server.getSourceByPath(path)
    content = []
    for dependency in source.getDependencies():
        content.append("%s.%s" % (str(dependency.library),
                                  str(dependency.name)))

    _logger.debug("Found %d dependencies", len(content))

    return {'dependencies': content}


@app.post('/get_build_sequence')
@_exceptionWrapper
def getBuildSequence():
    """
    Returns the build sequence of a given source path
    """
    project_file = bottle.request.forms.get('project_file')
    path = bottle.request.forms.get('path')

    _logger.debug("Getting build sequence for '%s', '%s'", project_file, path)

    server = _getServerByProjectFile(project_file)
    source, _ = server.getSourceByPath(path)

    return {'sequence': [x.filename for x in
                         server.updateBuildSequenceCache(source)]}


#  We'll store a dict to store differents hdlcc objects
servers = {}  # type: Dict[t.Path, HdlCodeCheckerServer] # pylint: disable=invalid-name
setupSignalHandlers()
