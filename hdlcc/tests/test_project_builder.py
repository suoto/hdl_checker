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

from nose2.tools import such
import logging
import os

from hdlcc.project_builder import ProjectBuilder
_logger = logging.getLogger(__name__)

if os.environ.get('BUILDER', None) == 'msim':
    _PRJ_FILENAME = 'dependencies/vim-hdl-examples/project.prj'
else:
    _PRJ_FILENAME = 'dependencies/vim-hdl-examples/ghdl.prj'

class StandaloneProjectBuilder(ProjectBuilder):
    _ui_logger = logging.getLogger('UI')
    def handleUiInfo(self, message):
        self._ui_logger.info(message)

    def handleUiWarning(self, message):
        self._ui_logger.warning(message)

    def handleUiError(self, message):
        self._ui_logger.error(message)

with such.A('hdlcc test using HDL Code Checker-examples') as it:

    @it.has_setup
    def setup():
        it.project = StandaloneProjectBuilder()

    @it.has_teardown
    def teardown():
        del it.project

    with it.having('a valid project file'):

        @it.should('add a project file')
        def test(case):
            it.project.setProjectFile(_PRJ_FILENAME)

        @it.should('read project file and build by dependency')
        def test(case):
            it.project.setup()

        @it.should('mark the project file as valid')
        def test(case):
            it.assertTrue(it.project._project_file['valid'])

        @it.should('get messages by path')
        def test(case):
            records = it.project.getMessagesByPath(\
                os.path.expanduser('dependencies/vim-hdl-examples/another_library/foo.vhd'))
            it.assertNotEqual(len(records), 0)

        @it.should('recover from cache')
        def test(case):
            it.project = StandaloneProjectBuilder()
            it.project.setProjectFile(os.path.expanduser(_PRJ_FILENAME))
            it.project.setup()

        @it.should("warn when a source wasn't found in the project file")
        def test(case):
            test_path = os.path.abspath('file_outside_the_prj_file.vhd')
            expected_msg = 'Path "%s" not found in project file' % test_path
            if not os.path.exists(test_path):
                open(test_path, 'w').close()
            records = it.project.getMessagesByPath(\
                os.path.expanduser(test_path))

            found = False
            for record in records:
                if record['error_type'] == 'W' and record['error_message'] == expected_msg:
                    found = True
                    break

            it.assertTrue(found, "File not found error not found")

#          with it.having('an invalid project file'):
#              @it.should('not raise exception when running setup')
#              def test(case):
#                  it.project.setProjectFile('foo')
#                  it.project.setup()

#              @it.should('mark the project file as invalid')
#              def test(case):
#                  it.assertFalse(it.project._project_file['valid'])

it.createTests(globals())
