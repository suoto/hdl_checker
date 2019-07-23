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


import logging
import hdlcc

_logger = logging.getLogger(__name__)

CLASS_MAP = {
    'VhdlParser': hdlcc.parsers.VhdlParser,
    'VerilogParser': hdlcc.parsers.VerilogParser,
    'DependencySpec': hdlcc.parsers.DependencySpec
}

def json_object_hook(dict_):
    _logger.warning("Handling %s", dict_)
    if '__class__' not in dict_:
        return dict_

    cls_name = dict_['__class__']
    cls = CLASS_MAP.get(cls_name, None)
    assert cls is not None, "We should handle {}".format(cls_name)
    if cls_name:
        try:
            obj = cls.__jsonDecode__(dict_)
        except:
            _logger.error("Something went wrong, cls_name: %s => %s", cls_name, cls)
            raise
        return obj

    return dict_
    #  return type(str(dict_['__class__']), (object, ), {'__dict__': dict_})()
    #  obj = object()
    #  obj.__dict__ = dict_
    #  return obj
