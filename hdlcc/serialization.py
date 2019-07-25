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
"""Serialization specifics"""

import json
import logging

import hdlcc

_logger = logging.getLogger(__name__)

# Maps class names added by the decoder to the actual class on Python side to
# recreate an object
CLASS_MAP = {
    'ConfigParser': hdlcc.config_parser.ConfigParser,

    'DependencySpec': hdlcc.parsers.DependencySpec,
    'VerilogParser': hdlcc.parsers.VerilogParser,
    'VhdlParser': hdlcc.parsers.VhdlParser,

    'GHDL': hdlcc.builders.GHDL,
    'MSim': hdlcc.builders.MSim,
    'XVHDL': hdlcc.builders.XVHDL,
}

class StateEncoder(json.JSONEncoder):
    """
    Custom encoder that handles hdlcc classes
    """
    def default(self, o):  # pylint: disable=method-hidden
        if hasattr(o, '__jsonEncode__'):
            dct = o.__jsonEncode__()
            prev = dct.get('__class__', None)
            if prev is not None and o.__class__.__name__ != prev:
                _logger.warning("Class has been set to %s, overwriting it "
                                "to %s", prev, o.__class__.__name__)
            dct['__class__'] = o.__class__.__name__
            _logger.debug("Encoded output:\n%s", repr(dct))
            return dct
        # Let the base class default method raise the TypeError
        try:
            return json.JSONEncoder.default(self, o)
        except:
            _logger.fatal("object: %s", o)
            raise


def jsonObjectHook(dict_):
    """
    json hook for decoding entries added the StateEncoder back to Python
    objects
    """
    _logger.debug("Handling %s", dict_)
    if '__class__' not in dict_:
        return dict_

    cls_name = dict_['__class__']
    cls = CLASS_MAP.get(cls_name, None)
    assert cls is not None, "We should handle {}".format(cls_name)

    try:
        obj = cls.__jsonDecode__(dict_)
    except:  #pragma: no cover
        _logger.error("Something went wrong, cls_name: %s => %s", cls_name, cls)
        raise
    return obj
