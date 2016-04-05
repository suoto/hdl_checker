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
"GHDL builder implementation"

import os
import re
from .base_builder import BaseBuilder
from hdlcc.exceptions import SanityCheckError

class GHDL(BaseBuilder):
    '''Builder implementation of the GHDL compiler'''

    # Implementation of abstract class properties
    builder_name = 'ghdl'

    # GHDL specific class properties
    _stdout_message_parser = re.compile(
        r"^(?P<filename>[^:]+):"
        r"(?P<line_number>\d+):"
        r"(?P<column>\d+):"
        r"((?P<is_warning>warning:)\s*|\s*)"
        r"(?P<error_message>.*)", re.I).finditer

    _scan_library_paths = re.compile(
        r"^\s*(actual prefix|library directory):"
        r"\s*(?P<library_path>.*)\s*").search

    _should_ignore = re.compile('|'.join([
        r"^\s*$",
        r"ghdl: compilation error", ])).match

    _iter_rebuild_units = re.compile(
        r'(entity "(?P<unit_name>\w+)" is obsoleted by package "\w+"'
        r'|'
        r'file (?P<rebuild_path>.*)\s+has changed and must be reanalysed)',
        flags=re.I).finditer

    def __init__(self, target_folder):
        self._version = ''
        super(GHDL, self).__init__(target_folder)
        self._builtin_libraries = []
        self._parseBuiltinLibraries()

    def _shouldIgnoreLine(self, line):
        if self._should_ignore(line):
            return True
        return False

    def _makeMessageRecords(self, line):
        record = {
            'checker'       : self.builder_name,
            'line_number'   : None,
            'column'        : None,
            'filename'      : None,
            'error_number'  : None,
            'error_type'    : None,
            'error_message' : None,
            }

        for match in self._stdout_message_parser(line):
            _dict = match.groupdict()
            for key in record.keys():
                if key in _dict.keys():
                    record[key] = _dict[key]

            if _dict['is_warning']:
                record['error_type'] = 'W'
            else:
                record['error_type'] = 'E'

        return [record]

    def checkEnvironment(self):
        try:
            stdout = self._subprocessRunner(['ghdl', '--version'])
            self._version = \
                    re.findall(r"(?<=GHDL)\s+([\w\.]+)\s+", \
                    stdout[0])[0]
            self._logger.info("GHDL version string: '%s'. " + \
                    "Version number is '%s'", \
                    stdout[:-1], self._version)
        except Exception as exc:
            import traceback
            self._logger.warning("Sanity check failed:\n%s",
                                 traceback.format_exc())
            raise SanityCheckError(self.builder_name, str(exc))

    def getBuiltinLibraries(self):
        return self._builtin_libraries

    def _parseBuiltinLibraries(self):
        "Discovers libraries that exist regardless before we do anything"
        library_name_scan = None
        for line in self._subprocessRunner(['ghdl', '--dispconfig']):
            library_path_match = self._scan_library_paths(line)
            if library_path_match:
                library_path = \
                    repr(library_path_match.groupdict()['library_path'])[1:-1]

                # TODO: We should find a better way to parse this
                if os.name == 'posix':
                    library_name_scan = re.compile( \
                        r"^\s*" + library_path +
                        r"/(?P<vhdl_standard>\w+)/(?P<library_name>\w+).*")
                else:
                    library_name_scan = re.compile( \
                        r"^\s*" + library_path +
                        r"\\(?P<vhdl_standard>\w+)\\(?P<library_name>\w+).*")
                self._logger.info("Library path: %s",
                                  library_path_match.groupdict())
                self._logger.info("Library name scan: %s",
                                  library_name_scan.pattern)

            if library_name_scan is not None:
                for match in library_name_scan.finditer(line):
                    self._builtin_libraries.append(match.groupdict()['library_name'])

    def _getGhdlArgs(self, source, flags=None):
        "Return the GHDL arguments that are common to most calls"
        cmd = ['-P%s' % self._target_folder,
               '--work=%s' % source.library,
               '--workdir=%s' % self._target_folder]
        if flags:
            cmd += flags
        cmd += [source.filename]
        return cmd

    def _importSource(self, source):
        "Runs GHDL with import source switch"
        cmd = ['ghdl', '-i'] + self._getGhdlArgs(source)
        return self._subprocessRunner(cmd)

    def _analyzeSource(self, source, flags=None):
        "Runs GHDL with analyze source switch"
        return ['ghdl', '-a'] + self._getGhdlArgs(source, flags)

    def _checkSyntax(self, source, flags=None):
        "Runs GHDL with syntax check switch"
        return ['ghdl', '-s'] + self._getGhdlArgs(source, flags)

    def _buildSource(self, source, flags=None):
        stdout = []
        for cmd in (self._analyzeSource(source, flags),
                    self._checkSyntax(source, flags)):
            stdout += self._subprocessRunner(cmd)

        return stdout

    def _createLibrary(self, source):
        workdir = os.path.join(self._target_folder)
        if not os.path.exists(workdir):
            os.mkdir(workdir)
        self._importSource(source)

    def _getUnitsToRebuild(self, line):
        rebuilds = []

        for match in self._iter_rebuild_units(line):
            if not match:
                continue
            mdict = match.groupdict()
            # When compilers reports units out of date, they do this
            # by either
            #  1. Giving the path to the file that needs to be rebuilt
            #     when sources are from different libraries
            #  2. Reporting which design unit has been affected by a
            #     given change.
            if 'rebuild_path' in mdict and mdict['rebuild_path'] is not None:
                rebuilds.append(mdict)
            else:
                rebuilds.append({'library_name' : 'work',
                                 'unit_name' : mdict['unit_name']})

        return rebuilds

