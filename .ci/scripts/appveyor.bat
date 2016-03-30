@echo off
set APPVEYOR_BUILD_FOLDER=e:\vim-hdl\dependencies\hdlcc\

set PATH=C:\Python27;%PATH%

REM  @set BUILDER_NAME=msim
REM  @set BUILDER_PATH=%LOCALAPPDATA%\modelsim_ase\win32aloem

@set BUILDER_NAME=ghdl
@set BUILDER_PATH=%LOCALAPPDATA%\\ghdl-0.31-mcode-win32\\bin

@echo "BUILDER_NAME is %BUILDER_NAME%"
@echo "BUILDER_PATH is %BUILDER_PATH%"

REM  @set TESTS=hdlcc.tests.test_builders
REM  @set TESTS=hdlcc.tests.test_config_parser
REM  @set TESTS=hdlcc.tests.test_persistency
REM  @set TESTS=hdlcc.tests.test_project_builder
REM  @set TESTS=hdlcc.tests.test_source_file
REM  @set TESTS=hdlcc.tests.test_standalone_hdlcc

@set RUNNER_ARGS=-vv --log-capture -F --debug

python %APPVEYOR_BUILD_FOLDER%\\.ci\\scripts\\run_tests.py %RUNNER_ARGS% %TESTS%

REM  move tests.log msim.log
