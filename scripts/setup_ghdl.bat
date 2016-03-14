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

set BUILDER_PATH=%INSTALL_DIR%\\bin
set GHDL_PREFIX=%INSTALL_DIR%\\lib

echo "INSTALL_DIR : %INSTALL_DIR%"
echo "BUILDER_PATH : %BUILDER_PATH%"
echo "GHDL_PREFIX : %GHDL_PREFIX%"

if not exist "%CACHE_PATH%\\ghdl.zip" (
    appveyor AddMessage "Downloading %BUILDER_NAME% from %URL%"
    curl -fsS -o "%CACHE_PATH%\\ghdl.zip" "%URL%"
    appveyor AddMessage "Download finished"
)

if not exist "%BUILDER_PATH%" (
    if not exist "%LOCALAPPDATA%\\ghdl" mkdir "%LOCALAPPDATA%\\ghdl"
    appveyor AddMessage "Installing %BUILDER_NAME% to %LOCALAPPDATA%"
    echo 7z x "%CACHE_PATH%\\ghdl.zip" -o"%LOCALAPPDATA%" -y
    7z x "%CACHE_PATH%\\ghdl.zip" -o"%LOCALAPPDATA%" -y

    if "%INSTALL_DIR%" == "%LOCALAPPDATA%\\ghdl-0.31-mcode-win32" (
        echo "Current dir: %CD%"
        cd /d "%INSTALL_DIR%"
        echo "Current dir: %CD%"

        echo ghdl --dispconfig
        ghdl --dispconfig

        echo set_ghdl_path.bat
        call set_ghdl_path.bat

        echo reanalyze_libs.bat
        call reanalyze_libs.bat

        echo ghdl --dispconfig
        ghdl --dispconfig
        cd /d "%APPVEYOR_BUILD_FOLDER%"
    )

    if "%INSTALL_DIR%" == "%LOCALAPPDATA%\\ghdl-0.33" (
        set OLDPATH=%PATH%
        set PATH=%BUILDER_PATH%;%PATH
        ghdl --dispconfig
        set PATH=%OLDPATH%
    )

)

