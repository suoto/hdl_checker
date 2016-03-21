@echo off
set APPVEYOR_BUILD_FOLDER=e:\vim-hdl\dependencies\hdlcc\

set PATH=C:\Python27;%PATH%

@set BUILDER_NAME=msim
@set BUILDER_PATH=%LOCALAPPDATA%\modelsim_ase\win32aloem

@echo "BUILDER_NAME is %BUILDER_NAME%"
@echo "BUILDER_PATH is %BUILDER_PATH%"

python %APPVEYOR_BUILD_FOLDER%\\run_tests.py -vv --log-capture -F --debug
REM  move tests.log msim.log
