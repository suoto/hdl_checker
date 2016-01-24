
from nose2.tools import such
from testfixtures import LogCapture
import logging
import os

import sys
sys.path.insert(0, os.path.join(os.path.abspath(os.path.dirname(__file__)), '..', 'python'))

from hdlcc.project_builder import ProjectBuilder
import hdlcc.config
#  hdlcc.config.Config.setupBuild()

class StandaloneProjectBuilder(ProjectBuilder):
    _ui_logger = logging.getLogger('UI')
    def handleUiInfo(self, message):
        self._ui_logger.info(message)

    def handleUiWarning(self, message):
        self._ui_logger.warning(message)

    def handleUiError(self, message):
        self._ui_logger.error(message)

_logger = logging.getLogger(__name__)

with LogCapture() as l:
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
                it.project.setProjectFile(os.path.expanduser('~/HDL Code Checker-examples/ghdl.prj'))

            @it.should('read project file and build by dependency')
            def test(case):
                it.project.setup()

            @it.should('mark the project file as valid')
            def test(case):
                it.assertTrue(it.project._project_file['valid'])

            @it.should('get messages by path')
            def test(case):
                records = it.project.getMessagesByPath(\
                    os.path.expanduser('~/HDL Code Checker-examples/another_library/foo.vhd'))
                it.assertNotEqual(len(records), 0)

            @it.should('recover from cache')
            def test(case):
                it.project = StandaloneProjectBuilder()
                it.project.setProjectFile(os.path.expanduser('~/HDL Code Checker-examples/ghdl.prj'))
                it.project.setup()

#          with it.having('an invalid project file'):
#              @it.should('not raise exception when running setup')
#              def test(case):
#                  it.project.setProjectFile('foo')
#                  it.project.setup()

#              @it.should('mark the project file as invalid')
#              def test(case):
#                  it.assertFalse(it.project._project_file['valid'])

it.createTests(globals())
