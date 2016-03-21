@echo off
set APPVEYOR_BUILD_FOLDER=e:\vim-hdl\dependencies\hdlcc\

set PATH=C:\Python27;%PATH%

REM  @set BUILDER_NAME=msim
REM  @set BUILDER_PATH=%LOCALAPPDATA%\modelsim_ase\win32aloem

@set BUILDER_NAME=ghdl
@set BUILDER_PATH=%LOCALAPPDATA%\\ghdl-0.31-mcode-win32\\bin

@echo "BUILDER_NAME is %BUILDER_NAME%"
@echo "BUILDER_PATH is %BUILDER_PATH%"

python %APPVEYOR_BUILD_FOLDER%\\run_tests.py -vv --log-capture -F --debug
REM  move tests.log msim.log
