#!/usr/bin/env bash
# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
#
# HDL Code Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Code Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.

set -x
set +e

URL=http://download.altera.com/akdlm/software/acdsinst/15.1/185/ib_installers/ModelSimSetup-15.1.0.185-linux.run
CACHE_DIR="${HOME}/cache/"
MSIM_INSTALLER="${CACHE_DIR}/modelsim.run"
INSTALLATION_DIR="${HOME}/builders/msim/"

mkdir -p "${CACHE_DIR}"

if [ ! -f "${MSIM_INSTALLER}" ]; then
  wget ${URL} -O "${MSIM_INSTALLER}" --quiet
  chmod +x "${MSIM_INSTALLER}"
  ${MSIM_INSTALLER} --help
fi

if [ ! -d "${INSTALLATION_DIR}" ]; then
  mkdir -p "${INSTALLATION_DIR}"
  ${MSIM_INSTALLER} --mode unattended \
    --modelsim_edition modelsim_ase \
    --installdir "${INSTALLATION_DIR}"
fi

"${INSTALLATION_DIR}/modelsim_ase/linuxaloem/vsim" -version
