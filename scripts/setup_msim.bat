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
REM

if not exist "%CACHE_PATH%\\modelsim.exe" (
    appveyor AddMessage "Downloading %BUILDER_NAME% from %URL%"
    echo curl -fsS -o "%CACHE_PATH%\\modelsim.exe" "%URL%"
    curl -fsS -o "%CACHE_PATH%\\modelsim.exe" "%URL%"
    appveyor AddMessage "Download finished"
)

if not exist "%CACHE_PATH%\\modelsim.exe" (
    appveyor AddMessage "Error downloading %BUILDER_NAME% from %URL%" -Category Error
    exit -1
)

if not exist "%BUILDER_PATH%" (
    appveyor AddMessage "Installing %BUILDER_NAME% to %LOCALAPPDATA%"
    echo %CACHE_PATH%\\modelsim.exe --mode unattended --modelsim_edition modelsim_ase --installdir %LOCALAPPDATA%
    %CACHE_PATH%\\modelsim.exe --mode unattended --modelsim_edition modelsim_ase --installdir %LOCALAPPDATA%
    appveyor AddMessage "Testing installation"
    echo %BUILDER_PATH%\\vcom -version
    %BUILDER_PATH%\\vcom -version || exit -1
    appveyor AddMessage "Done here"
)

