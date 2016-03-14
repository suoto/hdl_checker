@echo off
set APPVEYOR_BUILD_FOLDER=e:\hdlcc\

set PATH=C:\Python27;%PATH%

REM  set BUILDER_NAME=ghdl
REM  REM  set INSTALL_DIR=%LOCALAPPDATA%\\ghdl-0.31-mcode-win32
REM  set INSTALL_DIR=%LOCALAPPDATA%\\ghdl-0.33
REM  set BUILDER_PATH=%INSTALL_DIR%\\bin
REM  set GHDL_PREFIX=%INSTALL_DIR%\\lib

REM  echo "BUILDER_NAME is %BUILDER_NAME%"
REM  echo "BUILDER_PATH is %BUILDER_PATH%"

REM  python %APPVEYOR_BUILD_FOLDER%\\run_tests.py -vv -F --debug

REM  move tests.log ghdl.log

@set BUILDER_NAME=msim
@set BUILDER_PATH='%LOCALAPPDATA%\modelsim_ase\win32aloem'

@echo "BUILDER_NAME is %BUILDER_NAME%"
@echo "BUILDER_PATH is %BUILDER_PATH%"

python %APPVEYOR_BUILD_FOLDER%\\run_tests.py -vv --log-capture -F --debug
REM  move tests.log msim.log
