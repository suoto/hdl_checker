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
"VHDL static checking to find unused signals, ports and constants."

import re
import logging

__logger__ = logging.getLogger(__name__)

__AREA_SCANNER__ = re.compile('|'.join([
    r"^\s*entity\s+(?P<entity_name>\w+)\s+is\b",
    r"^\s*architecture\s+(?P<architecture_name>\w+)\s+of\s+(?P<arch_entity>\w+)",
    r"^\s*package\s+(?P<package_name>\w+)\s+is\b",
    r"^\s*package\s+body\s+(?P<package_body_name>\w+)\s+is\b",
    ]), flags=re.I)

__NO_AREA_SCANNER__ = re.compile('|'.join([
    r"^\s*library\s+(?P<library>[\w\s,]+)",
    r"^\s*attribute\s+(?P<attribute>[\w\s,]+)\s*:",
    ]), flags=re.I)

__ENTITY_SCANNER__ = re.compile('|'.join([
    r"^\s*(?P<port>[\w\s,]+)\s*:\s*(in|out|inout|buffer|linkage)\s+\w+",
    r"^\s*(?P<generic>[\w\s,]+)\s*:\s*\w+",
    ]), flags=re.I)

__ARCH_SCANNER__ = re.compile('|'.join([
    r"^\s*constant\s+(?P<constant>[\w\s,]+)\s*:",
    r"^\s*signal\s+(?P<signal>[\w,\s]+)\s*:",
    r"^\s*type\s+(?P<type>\w+)\s*:",
    r"^\s*shared\s+variable\s+(?P<shared_variable>[\w\s,]+)\s*:",
    ]), flags=re.I)

__END_OF_SCAN__ = re.compile('|'.join([
    r"\bport\s+map",
    r"\bgenerate\b",
    r"\w+\s*:\s*entity",
    r"\bprocess\b",
    ]))

def _getObjectsFromText(vbuffer):
    """Returns a dict containing the objects found at the given text
    buffer"""
    objects = {}
    lnum = 0
    area = None
    for _line in vbuffer:
        line = re.sub(r"\s*--.*", "", _line)
        for match in __AREA_SCANNER__.finditer(line):
            _dict = match.groupdict()
            if _dict['entity_name'] is not None:
                area = 'entity'
            elif _dict['architecture_name'] is not None:
                area = 'architecture'
            elif _dict['package_name'] is not None:
                area = 'package'
            elif _dict['package_body_name'] is not None:
                area = 'package_body'

        matches = []
        if area is None:
            matches += __NO_AREA_SCANNER__.finditer(line)
        elif area == 'entity':
            matches += __ENTITY_SCANNER__.finditer(line)
        elif area == 'architecture':
            matches += __ARCH_SCANNER__.finditer(line)

        for match in matches:
            for key, value in match.groupdict().items():
                if value is None: continue
                _group_d = match.groupdict()
                index = match.lastindex
                if 'port' in _group_d.keys() and _group_d['port'] is not None:
                    index -= 1
                start = match.start(index)
                end = match.end(index)

                # More than 1 declaration can be done in a single line.
                # Must strip white spaces and commas properly
                for submatch in re.finditer(r"(\w+)", value):
                    # Need to decrement the last index because we have a group that
                    # catches the port type (in, out, inout, etc)
                    text = submatch.group(submatch.lastindex)
                    if text not in objects.keys():
                        objects[text] = {}
                    objects[text]['lnum'] = lnum
                    objects[text]['start'] = start + submatch.start(submatch.lastindex)
                    objects[text]['end'] = end + submatch.start(submatch.lastindex)
                    objects[text]['type'] = key
        lnum += 1
        if __END_OF_SCAN__.search(line):
            break

    #  if objects:
    #      __logger__.debug("Objects found:")
    #      for _name, _object in objects.items():
    #          __logger__.debug("%s => %s", _name, str(_object))
    #  else:
    #      __logger__.debug("No objects found")
    return objects

def _getUnusedObjects(vbuffer, objects):
    """Generator that yields objects that are only found once at the
    given buffer and thus are considered unused (i.e., we only found
    its declaration"""

    text = ''
    for line in vbuffer:
        text += re.sub(r"\s*--.*", "", line) + ' '

    for _object in objects:
        r_len = 0
        single = True
        for _ in re.finditer(r"\b%s\b" % _object, text, flags=re.I):
            r_len += 1
            if r_len > 1:
                single = False
                break
        if single:
            yield _object

__COMMENT_TAG_SCANNER__ = re.compile('|'.join([
    r"\s*--\s*(?P<tag>TODO|FIXME|XXX)\s*:\s*(?P<text>.*)",
    ]))

def _getCommentTags(vbuffer):
    result = []
    lnum = 0
    for line in vbuffer:
        lnum += 1
        line_lc = line.lower()
        skip_line = True
        for tag in ('todo', 'fixme', 'xxx'):
            if tag in line_lc:
                skip_line = False
                break
        if skip_line:
            continue

        for match in __COMMENT_TAG_SCANNER__.finditer(line):
            _dict = match.groupdict()
            message = {
                'checker'        : 'HDL Code Checker/static',
                'line_number'    : lnum,
                'column'         : match.start(match.lastindex - 1) + 1,
                'filename'       : None,
                'error_number'   : '0',
                'error_type'     : 'W',
                'error_subtype'  : '',
                'error_message'  : "%s: %s" % (_dict['tag'].upper(), _dict['text'])
                }
            result += [message]
    return result

def getStaticMessages(vbuffer=None):
    "VHDL static checking"
    objects = _getObjectsFromText(vbuffer)

    result = []

    for _object in _getUnusedObjects(vbuffer, objects.keys()):
        obj_dict = objects[_object]
        message = {
            'checker'        : 'HDL Code Checker/static',
            'line_number'    : obj_dict['lnum'] + 1,
            'column'         : obj_dict['start'] + 1,
            'filename'       : None,
            'error_number'   : '0',
            'error_type'     : 'W',
            'error_subtype'  : 'Style',
            'error_message'  : "{obj_type} '{obj_name}' is never used".format(
                obj_type=obj_dict['type'], obj_name=_object),
            }

        result.append(message)
    return result + _getCommentTags(vbuffer)

def standalone(): # pragma: no cover
    import sys
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    for arg in sys.argv[1:]:
        print arg
        for message in getStaticMessages(open(arg, 'r').read().split('\n')):
            print message
        print "="*10

if __name__ == '__main__':
    standalone()


