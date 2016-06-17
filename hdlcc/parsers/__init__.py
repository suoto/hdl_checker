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
import logging
from multiprocessing import Pool
_logger = logging.getLogger(__name__)

from hdlcc.parsers.vhdl_source_file import VhdlSourceFile
from hdlcc.parsers.verilog_source_file import VerilogSourceFile


def _isVhdl(p):
    if p.lower().endswith('.vhd'):
        return True
    if p.lower().endswith('.vhdl'):
        return True
    return False

def _isVerilog(p):
    if p.lower().endswith('.v'):
        return True
    if p.lower().endswith('.sv'):
        return True
    return False


def getSourceFileObjects(kwargs, workers=1):
    "Reads files from <fnames> list using up to <workers> threads"

    pool = Pool(workers)

    try:
        if len(kwargs) == 1:
            kwargs = kwargs[0]
            if _isVhdl(kwargs['filename']):
                cls = VhdlSourceFile
            elif _isVerilog(kwargs['filename']):
                cls = VerilogSourceFile
            else:
                assert False
            return [cls(**kwargs)]
        else:
            results = []

            for _kwargs in kwargs:
                if _isVhdl(_kwargs['filename']):
                    cls = VhdlSourceFile
                elif _isVerilog(_kwargs['filename']):
                    cls = VerilogSourceFile
                else:
                    assert False
                results += [pool.apply_async(cls, kwds=_kwargs)]
            return [res.get() for res in results]
    finally:
        pool.close()
        pool.terminate()

