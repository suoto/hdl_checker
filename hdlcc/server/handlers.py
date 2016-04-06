# This file is part of HDL Code Checker.
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

import sys
import os.path as p
import bottle
import logging
import json
from multiprocessing import Queue

_logger = logging.getLogger(__name__)

import hdlcc
from hdlcc.code_checker_base import HdlCodeCheckerBase

app = bottle.Bottle() # pylint: disable=invalid-name

#  We'll store a dict to store differents hdlcc objects
_hdlcc_objects = {} # pylint: disable=invalid-name

class HdlCodeCheckerSever(HdlCodeCheckerBase):
    "HDL Code Checker project builder class"
    def __init__(self, *args, **kwargs):
        self._msg_queue = Queue()
        super(HdlCodeCheckerSever, self).__init__(*args, **kwargs)

    def _handleUiInfo(self, message):
        self._msg_queue.put(("info", message))

    def _handleUiWarning(self, message):
        self._msg_queue.put(("warning", message))

    def _handleUiError(self, message):
        self._msg_queue.put(("error", message))

    def getQueuedMessages(self):
        "Returns queued UI messages"
        while not self._msg_queue.empty():
            yield self._msg_queue.get()

def _getServerByProjectFile(project_file):
    if p.isabs(project_file) or project_file is None:
        if project_file not in _hdlcc_objects:
            _logger.debug("Created new project server for '%s'", project_file)
            _hdlcc_objects[project_file] = HdlCodeCheckerSever(project_file)
        return _hdlcc_objects[project_file]
    else:
        _logger.error("Paths must be absolute")
        return

@app.post('/open_project_file')
def _loadProject():
    "Loads a project file"
    project_file = bottle.request.forms.get('project_file')
    response = {'error' : None}
    if _getServerByProjectFile(project_file) is None:
        response = {'error' : "Path '%s' is not absolute"}

    return json.dumps(response)

@app.get('/get_diagnose_info')
def _getDiagnoseInfo():
    "Collects misc diagnose info for the clients"
    _logger.info("Collecting diagnose info")
    project_file = bottle.request.forms.get('project_file')
    response = {'error' : None}
    if not p.isabs(project_file):
        _logger.warning("Paths must be absolute")
        response = {'error' : "Path '%s' is not absolute"}

    server = _getServerByProjectFile(project_file)
    response['builder'] = server.builder.builder_name
    response['hdlcc version'] = hdlcc.__version__

    _logger.info("Diagnose info collected:")
    for key, val in response.items():
        _logger.info(" - %s: %s", key, val)

    return json.dumps(response)

@app.post('/get_messages_by_path')
def _getMessagesByPath():
    "Get messages for a given projec_file/path pair"
    project_file = bottle.request.forms.get('project_file')
    path = bottle.request.forms.get('path')
    _logger.debug("Getting messages for '%s', '%s'", project_file, path)

    server = _getServerByProjectFile(project_file)
    response = {'error' : None}
    response['messages'] = []

    for msg in server.getMessagesByPath(path):
        response['messages'] += [msg]

    return json.dumps(response)

@app.post('/get_ui_messages')
def _getUiMessages():
    "Get messages for a given projec_file/path pair"
    project_file = bottle.request.forms.get('project_file')
    _logger.debug("Getting UI messages for '%s'", project_file)

    server = _getServerByProjectFile(project_file)

    ui_messages = list(server.getQueuedMessages())

    if not ui_messages:
        _logger.info("No UI messages")
    for msg in ui_messages:
        _logger.info(msg)

    response = {'error' : None,
                'ui_messages' : ui_messages}

    return json.dumps(response)

