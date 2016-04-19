# This file is part of HDL Code Checker.

# HDL Code Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# HDL Code Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.

write-host "Setting up GHDL..."

$env:GHDL_PREFIX="$env:INSTALL_DIR\\lib"

if (!(Test-Path "$env:CACHE_PATH\\ghdl.zip")) {
    write-host "Downloading $env:BUILDER_NAME from $env:URL to $env:CACHE_PATH\\ghdl.zip"
    if ($env:APPVEYOR -eq "True") {
      curl -fsS "$env:URL" --output "$env:CACHE_PATH\\ghdl.zip"
    } else {
      "curl -fS `"$env:URL`" --output `"$env:CACHE_PATH\\ghdl.zip`""
      curl -fS "$env:URL" --output "$env:CACHE_PATH\\ghdl.zip"
    }
    if (!$?) {write-error "Something went wrong, exiting"; exit -1}
    write-host "Download finished"
}

if (!(Test-Path "$env:BUILDER_PATH")) {
    write-host "Installing $env:BUILDER_NAME to $env:CI_WORK_PATH"
    cmd /c "7z x `"$env:CACHE_PATH\\ghdl.zip`" -o`"$env:CI_WORK_PATH`" -y"

    if ("$env:INSTALL_DIR" -eq "$env:CI_WORK_PATH\\ghdl-0.31-mcode-win32") {
        write-host "Current dir: $(get-location)"
        set-location "$env:INSTALL_DIR"
        write-host "Current dir: $(get-location)"

        write-host "Testing GHDL before library update"
        cmd /c "$env:BUILDER_PATH\\ghdl --dispconfig"
        cmd /c "set_ghdl_path.bat"
        cmd /c "reanalyze_libs.bat"
        write-host "Testing GHDL after library update"
        cmd /c "$env:BUILDER_PATH\\ghdl --dispconfig"

        set-location "$env:APPVEYOR_BUILD_FOLDER"
    }

    if ("$env:INSTALL_DIR" -eq "$env:CI_WORK_PATH\\ghdl-0.33") {
        write-host "Current dir: $(get-location)"
        set-location "$env:INSTALL_DIR\\bin"
        write-host "Current dir: $(get-location)"
        cmd /c "$env:BUILDER_PATH\\ghdl --dispconfig"
        set-location "$env:APPVEYOR_BUILD_FOLDER"
    }
}

