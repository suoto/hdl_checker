# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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

# pylint: disable=function-redefined, missing-docstring, protected-access

import logging
logging.getLogger(__name__).fatal("Hey there")
import os
import os.path as p

from nose2.tools import such
import mock

from hdlcc.utils import patchPyls

try:
    patchPyls()
except:
    print("##############################################")
    print("##############################################")
    import traceback
    traceback.print_exc()
    print("##############################################")
    print("##############################################")
    raise

try:
    import hdlcc.lsp as lsp
    import pyls.lsp as defines
    from hdlcc.diagnostics import DiagType, CheckerDiagnostic
except ImportError as exc:
    import sys
    print("#################### path ####################")
    print('\n'.join(sys.path))
    print("##############################################")
    print(str(exc))
    import traceback
    traceback.print_exc()
    print("##############################################")
    raise

_logger = logging.getLogger(__name__)

#  import unittest

#  class TestDiagToLsp(unittest.TestCase):

#      def test_basic(self):
#          diag = CheckerDiagnostic(
#              checker='hdlcc test', text='some diag', filename='filename',
#              line_number=1, column=1, error_code='error code',
#              severity=DiagType.INFO)

#          self.assertEqual(
#              lsp.diagToLsp(diag),
#              {'source': 'hdlcc test',
#               'range': {
#                   'start': {
#                       'line': 1,
#                       'character': -1, },
#                   'end': {
#                       'line': -1,
#                       'character': -1, }},
#               'message': 'some diag',
#               'severity': defines.DiagnosticSeverity.Information,
#               'code': 'error code'})

with such.A("LSP") as it:
    @it.should
    def test():
        print("oi")
        #  it.fail("Hello!")


it.createTests(globals())
