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
'Configuration file parser'

import os
import re
import logging

import hdlcc.exceptions

_RE_LEADING_AND_TRAILING_WHITESPACES = re.compile(r"^\s*|\s*$")
_RE_MULTIPLE_WHITESPACES = re.compile(r"\s+")

_logger = logging.getLogger(__name__)

def _extractList(entry):
    _entry = _RE_LEADING_AND_TRAILING_WHITESPACES.sub("", entry)
    if _entry:
        return set(_RE_MULTIPLE_WHITESPACES.split(_entry))
    else:
        return set()

_COMMENTS = re.compile(r"\s*#.*")
_SCANNER = re.compile('|'.join([
    r"^\s*(?P<parameter>\w+)\s*=\s*(?P<value>.+)\s*$",
    r"^\s*(?P<lang>(vhdl|verilog))\s+"          \
        r"(?P<library>\w+)\s+"                  \
        r"(?P<path>[^\s]+)\s*(?P<flags>.*)\s*",
    ]), flags=re.I)

def readConfigFile(fname):
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
                    raise hdlcc.exceptions.UnknownParameterError(_dict['parameter'])
            else:
                if not os.path.isabs(_dict['path']):
                    _dict['path'] = os.path.join(fname_base_dir, _dict['path'])
                if _dict['lang'].lower() != 'vhdl':
                    _logger.warning("Unsupported language: %s", _dict['lang'])
                else:
                    source_list += [(os.path.normpath(_dict['path']),
                                     _dict['library'],
                                     _extractList(_dict['flags']))]

    if target_dir is None:
        target_dir = '.' + builder_name

    return target_dir, builder_name, build_flags, source_list

