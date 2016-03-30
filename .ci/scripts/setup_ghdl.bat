REM  This file is part of HDL Code Checker.

REM  HDL Code Checker is free software: you can redistribute it and/or modify
REM  it under the terms of the GNU General Public License as published by
REM  the Free Software Foundation, either version 3 of the License, or
REM  (at your option) any later version.

REM  HDL Code Checker is distributed in the hope that it will be useful,
REM  but WITHOUT ANY WARRANTY; without even the implied warranty of
REM  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
REM  GNU General Public License for more details.

REM  You should have received a copy of the GNU General Public License
REM  along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.

@echo on
set BUILDER_PATH=%INSTALL_DIR%\\bin
set GHDL_PREFIX=%INSTALL_DIR%\\lib

if not exist "%CACHE_PATH%\\ghdl.zip" (
    appveyor AddMessage "Downloading %BUILDER_NAME% from %URL%"
    curl -fsS -o "%CACHE_PATH%\\ghdl.zip" "%URL%"
    appveyor AddMessage "Download finished"
)

if not exist "%BUILDER_PATH%" (
    appveyor AddMessage "Installing %BUILDER_NAME% to %LOCALAPPDATA%"
    7z x "%CACHE_PATH%\\ghdl.zip" -o"%LOCALAPPDATA%" -y

    if "%INSTALL_DIR%" == "%LOCALAPPDATA%\\ghdl-0.31-mcode-win32" (
        echo "Current dir: %CD%"
        cd /d "%INSTALL_DIR%"
        echo "Current dir: %CD%"

        ghdl --dispconfig

        call set_ghdl_path.bat
        call reanalyze_libs.bat

        ghdl --dispconfig
        cd /d "%APPVEYOR_BUILD_FOLDER%"
    )

    if "%INSTALL_DIR%" == "%LOCALAPPDATA%\\ghdl-0.33" (
        echo "Current dir: %CD%"
        cd /d "%INSTALL_DIR%\\bin"
        echo "Current dir: %CD%"
        ghdl --dispconfig
        cd /d "%APPVEYOR_BUILD_FOLDER%"
    )

)

@echo off
