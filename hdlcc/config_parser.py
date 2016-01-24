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
"""Extended version of ConfigParser.SafeConfigParser to add a method to return
a list split at multiple whitespaces"""

import os
import re
import logging

import ConfigParser

from hdlcc.exceptions import UnknownConfigFileExtension

_RE_LEADING_AND_TRAILING_WHITESPACES = re.compile(r"^\s*|\s*$")
_RE_MULTIPLE_WHITESPACES = re.compile(r"\s+")

_logger = logging.getLogger(__name__)

class ExtendedConfigParser(ConfigParser.SafeConfigParser):
    def getlist(self, section, option):
        entry = self.get(section, option)
        return _extractList(entry)

def _extractList(entry):
    _entry = _RE_LEADING_AND_TRAILING_WHITESPACES.sub("", entry)
    if _entry:
        return set(_RE_MULTIPLE_WHITESPACES.split(_entry))
    else:
        return set()

def readConfigFile(fname):
    if fname.lower().endswith('.conf'):
        _logger.info("Parsing %s as conf file", fname)
        return parseConfFile(fname)
    elif fname.lower().endswith('.prj'):
        _logger.info("Parsing %s as prj file", fname)
        return parsePrjFile(fname)
    raise UnknownConfigFileExtension(fname)

def parseConfFile(fname):
    defaults = {'build_flags' : '',
                'global_build_flags' : '',
                'batch_build_flags' : '',
                'single_build_flags' : '',
                'prj_file' : ''}

    parser = ExtendedConfigParser(defaults=defaults)
    parser.read(fname)

    # Get the global build definitions
    build_flags = {
        'batch' : parser.getlist('global', 'batch_build_flags'),
        'single' : parser.getlist('global', 'single_build_flags'),
        'global' : parser.getlist('global', 'global_build_flags'),
        }

    builder_name = parser.get('global', 'builder')
    target_dir = os.path.expanduser(parser.get('global', 'target_dir'))

    _logger.info("Builder selected: %s at %s", builder_name, target_dir)

    source_list = []

    # Iterate over the sections to get sources and build flags.
    # Take care to don't recreate a library
    for section in parser.sections():
        if section == 'global':
            continue

        sources = parser.getlist(section, 'sources')
        flags = parser.getlist(section, 'build_flags')

        for source in sources:
            source_list += [(source, section, flags)]

    return target_dir, builder_name, build_flags, source_list

_COMMENTS = re.compile(r"\s*#.*")
_SCANNER = re.compile('|'.join([
    r"^\s*(?P<parameter>\w+)\s*=\s*(?P<value>.+)\s*$",
    r"^\s*(?P<lang>(vhdl|verilog))\s+"          \
        r"(?P<library>\w+)\s+"                  \
        r"(?P<path>[^\s]+)\s*(?P<flags>.*)\s*",
    ]), flags=re.I)

def parsePrjFile(fname):
    target_dir = None
    builder_name = None
    build_flags = {'global' : set(),
                   'batch'  : set(),
                   'single' : set()}
    fname_base_dir = os.path.dirname(os.path.abspath(fname))
    source_list = []
    for _line in open(fname, 'r').read().split('\n'):
        line = _COMMENTS.sub('', _line)
        for match in _SCANNER.finditer(line):
            _dict = match.groupdict()
            if _dict['parameter'] is not None:
                if _dict['parameter'] == 'builder':
                    builder_name = _dict['value']
                elif _dict['parameter'] == 'target_dir':
                    target_dir = _dict['value'] if os.path.isabs(_dict['value']) \
                        else os.path.join(fname_base_dir, _dict['value'])
                elif _dict['parameter'] == 'single_build_flags':
                    build_flags['single'] = _extractList(_dict['value'])
                elif _dict['parameter'] == 'batch_build_flags':
                    build_flags['batch'] = _extractList(_dict['value'])
                elif _dict['parameter'] == 'global_build_flags':
                    build_flags['global'] = _extractList(_dict['value'])
            else:
                if _dict['lang'].lower() != 'vhdl':
                    _logger.warning("Unsupported language: %s", _dict['lang'])
                if not os.path.isabs(_dict['path']):
                    _dict['path'] = os.path.join(fname_base_dir, _dict['path'])

                source_list += [(_dict['path'],
                                 _dict['library'],
                                 _extractList(_dict['flags']))]

    if target_dir is None:
        target_dir = '.' + builder_name

    return target_dir, builder_name, build_flags, source_list

