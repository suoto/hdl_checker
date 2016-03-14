
@echo off
@set PATH=%PROGRAMFILES%\7-Zip;%PATH%
REM  @set PATH=c:\Arquivos de Programas\7-Zip;%PATH%

@set APPVEYOR_BUILD_FOLDER=e:\hdlcc\
@set CACHE_PATH=%LOCALAPPDATA%\\cache
@set BUILDER_NAME=ghdl
REM  @set INSTALL_DIR="%LOCALAPPDATA%\\ghdl-0.31-mcode-win32"
@set INSTALL_DIR=%LOCALAPPDATA%\\ghdl-0.33

echo "INSTALL_DIR %INSTALL_DIR%"

REM  pip install -r requirements.txt

if "%BUILDER_NAME%" == "ghdl" call %APPVEYOR_BUILD_FOLDER%\\scripts\\setup_ghdl.bat

REM  rmdir /s /q %INSTALL_DIR%

@echo on
