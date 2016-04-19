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

$env:APPVEYOR_BUILD_FOLDER=$(get-location)
$env:CACHE_PATH="$env:LOCALAPPDATA\\cache"
$env:HDLCC_CI="$env:LOCALAPPDATA\\hdlcc_ci"
$env:ARCH="32"
$env:PATH="C:\Program Files\7-zip;$env:PATH"

