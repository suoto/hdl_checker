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
"VHDL static checking to find unused signals, ports and constants."

import logging
import re
from typing import List, Tuple

#  from hdl_checker.path import Path
from hdl_checker.diagnostics import (
    DiagType,
    LibraryShouldBeOmited,
    ObjectIsNeverUsed,
    StaticCheckerDiag,
)

_logger = logging.getLogger(__name__)

_GET_SCOPE = re.compile(
    "|".join(
        [
            r"^\s*entity\s+(?P<entity_name>\w+)\s+is\b",
            r"^\s*architecture\s+(?P<architecture_name>\w+)\s+of\s+(?P<arch_entity>\w+)",
            r"^\s*package\s+(?P<package_name>\w+)\s+is\b",
            r"^\s*package\s+body\s+(?P<package_body_name>\w+)\s+is\b",
        ]
    ),
    flags=re.I,
).finditer

_NO_SCOPE_OBJECTS = re.compile(
    "|".join(
        [
            r"^\s*library\s+(?P<library>[\w\s,]+)",
            r"^\s*attribute\s+(?P<attribute>[\w\s,]+)\s*:",
        ]
    ),
    flags=re.I,
)

_ENTITY_OBJECTS = re.compile(
    "|".join(
        [
            r"^\s*(?P<port>[\w\s,]+)\s*:\s*(in|out|inout|buffer|linkage)\s+\w+",
            r"^\s*(?P<generic>[\w\s,]+)\s*:\s*\w+",
        ]
    ),
    flags=re.I,
).finditer

_ARCH_OBJECTS = re.compile(
    "|".join(
        [
            r"^\s*constant\s+(?P<constant>[\w\s,]+)\s*:",
            r"^\s*signal\s+(?P<signal>[\w,\s]+)\s*:",
            r"^\s*type\s+(?P<type>\w+)\s*:",
            r"^\s*shared\s+variable\s+(?P<shared_variable>[\w\s,]+)\s*:",
        ]
    ),
    flags=re.I,
).finditer

_SHOULD_END_SCAN = re.compile(
    "|".join(
        [
            r"\bgeneric\s+map",
            r"\bport\s+map",
            r"\bgenerate\b",
            r"\w+\s*:\s*entity",
            r"\bprocess\b",
        ]
    )
).search


def _getAreaFromMatch(dict_):  # pylint: disable=inconsistent-return-statements
    """
    Returns code area based on the match dict
    """
    if dict_["entity_name"] is not None:
        return "entity"
    if dict_["architecture_name"] is not None:
        return "architecture"
    if dict_["package_name"] is not None:
        return "package"
    if dict_["package_body_name"] is not None:
        return "package_body"

    assert False, "Can't determine area from {}".format(dict_)  # pragma: no cover


def _getObjectsFromText(lines):
    """
    Converts the iterator from _findObjects into a dict, whose key is the
    object's name and the value if the object's info
    """
    objects = {}
    for name, info in _findObjects(lines):
        if name not in objects:
            objects[name] = info

    return objects


def _findObjects(lines):
    """
    Returns an iterator with the object name and a dict with info about its
    location
    """
    lnum = 0
    area = None
    for _line in lines:
        line = re.sub(r"\s*--.*", "", _line)
        for match in _GET_SCOPE(line):
            area = _getAreaFromMatch(match.groupdict())

        matches = []
        if area is None:
            matches += _NO_SCOPE_OBJECTS.finditer(line)
        elif area == "entity":
            matches += _ENTITY_OBJECTS(line)
        elif area == "architecture":
            matches += _ARCH_OBJECTS(line)

        for match in matches:
            for key, value in match.groupdict().items():
                if value is None:
                    continue
                _group_d = match.groupdict()
                index = match.lastindex
                if "port" in _group_d.keys() and _group_d["port"] is not None:
                    index -= 1
                start = match.start(index)
                end = match.end(index)

                # More than 1 declaration can be done in a single line.
                # Must strip white spaces and commas properly
                for submatch in re.finditer(r"(\w+)", value):
                    # Need to decrement the last index because we have a group that
                    # catches the port type (in, out, inout, etc)
                    name = submatch.group(submatch.lastindex)
                    yield name, {
                        "lnum": lnum,
                        "start": start + submatch.start(submatch.lastindex),
                        "end": end + submatch.start(submatch.lastindex),
                        "type": key,
                    }
        lnum += 1
        if _SHOULD_END_SCAN(line):
            break


def _getUnusedObjects(lines, objects):
    """Generator that yields objects that are only found once at the
    given buffer and thus are considered unused (i.e., we only found
    its declaration"""

    text = ""
    for line in lines:
        text += re.sub(r"\s*--.*", "", line) + " "

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


__COMMENT_TAG_SCANNER__ = re.compile(
    "|".join([r"\s*--\s*(?P<tag>TODO|FIXME|XXX)\s*:\s*(?P<text>.*)"])
)


def _getCommentTags(lines):
    """
    Generates diags from 'TODO', 'FIXME' and 'XXX' tags
    """
    result = []
    lnum = 0
    for line in lines:
        lnum += 1
        line_lc = line.lower()
        skip_line = True
        for tag in ("todo", "fixme", "xxx"):
            if tag in line_lc:
                skip_line = False
                break
        if skip_line:
            continue

        for match in __COMMENT_TAG_SCANNER__.finditer(line):
            _dict = match.groupdict()
            result += [
                StaticCheckerDiag(
                    line_number=lnum - 1,
                    column_number=match.start(match.lastindex - 1),
                    severity=DiagType.STYLE_INFO,
                    text="%s: %s" % (_dict["tag"].upper(), _dict["text"]),
                )
            ]
    return result


def _getMiscChecks(objects):
    """
    Get generic code hints (or it should do that sometime in the future...)
    """
    if "library" not in [x["type"] for x in objects.values()]:
        return

    for library, obj in objects.items():
        if obj["type"] != "library":
            continue
        if library == "work":
            yield LibraryShouldBeOmited(
                line_number=obj["lnum"], column_number=obj["start"], library=library
            )


def getStaticMessages(lines):
    # type: (Tuple[str, ...]) -> List[StaticCheckerDiag]
    "VHDL static checking"
    objects = _getObjectsFromText(lines)

    result = []  # type: List[StaticCheckerDiag]

    for _object in _getUnusedObjects(lines, objects.keys()):
        obj_dict = objects[_object]
        result += [
            ObjectIsNeverUsed(
                line_number=obj_dict["lnum"],
                column_number=obj_dict["start"],
                object_type=obj_dict["type"],
                object_name=_object,
            )
        ]

    return result + _getCommentTags(lines) + list(_getMiscChecks(objects))


def standalone():  # pragma: no cover
    """
    Standalone entry point
    """
    import sys

    logging.basicConfig(stream=sys.stdout, level=logging.INFO)
    for arg in sys.argv[1:]:
        print(arg)
        lines = [x.decode(errors="ignore") for x in open(arg, mode="rb").readlines()]
        for message in getStaticMessages(lines):
            print(message)
        print("=" * 10)


if __name__ == "__main__":
    standalone()
