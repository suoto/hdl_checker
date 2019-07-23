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
"Top of the hdlcc.parsers submodule"

import logging
#  from multiprocessing import Pool
from multiprocessing.pool import ThreadPool as Pool

from hdlcc.parsers.dependency_spec import DependencySpec
from hdlcc.parsers.verilog_parser import VerilogParser
from hdlcc.parsers.vhdl_parser import VhdlParser

_logger = logging.getLogger(__name__)

def _isVhdl(path): # pragma: no cover
    "Uses the file extension to check if the given path is a VHDL file"
    if path.lower().endswith('.vhd'):
        return True
    if path.lower().endswith('.vhdl'):
        return True
    return False

def _isVerilog(path): # pragma: no cover
    """Uses the file extension to check if the given path is a Verilog
    or SystemVerilog file"""
    if path.lower().endswith('.v'):
        return True
    if path.lower().endswith('.sv'):
        return True
    return False

def getSourceFileObjects(kwargs_list, workers=None):
    """
    Gets source file objects by applying each item on kwargs_list as
    kwargs on the source parser class. Uses kwargs['filename'] to
    determine if the source is VHDL or Verilog/SystemVerilog
    """

    pool = Pool(workers)
    async_results = []

    for kwargs in kwargs_list:
        if _isVhdl(kwargs['filename']):
            cls = VhdlParser
        else:
            cls = VerilogParser
        async_results += [pool.apply_async(cls, kwds=kwargs)]

    pool.close()
    pool.join()
    results = [x.get() for x in async_results]

    return results
