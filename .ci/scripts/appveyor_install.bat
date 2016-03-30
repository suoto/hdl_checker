
REM  @echo off
@set PATH=%PROGRAMFILES%\7-Zip;%PATH%
REM  @set PATH=c:\Arquivos de Programas\7-Zip;%PATH%

@set APPVEYOR_BUILD_FOLDER=e:\vim-hdl\dependencies\hdlcc\
@set CACHE_PATH=%LOCALAPPDATA%\\cache
@set BUILDER_NAME=msim
@set BUILDER_PATH=%LOCALAPPDATA%\modelsim_ase\win32aloem
@set arch=32
@set URL=http://download.altera.com/akdlm/software/acdsinst/15.1/185/ib_installers/ModelSimSetup-15.1.0.185-windows.exe

pause

if "%BUILDER_NAME%" == "msim" call %APPVEYOR_BUILD_FOLDER%\\scripts\\setup_msim.bat
pause

REM  python %APPVEYOR_BUILD_FOLDER%\\run_tests.py -vv -F -B --log-capture

@echo on
