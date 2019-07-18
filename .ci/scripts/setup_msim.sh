#!/usr/bin/env bash
# This file is part of HDL Code Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
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

FREETYPE=freetype-2.4.12
FREETYPE_FILE=${FREETYPE}.tar.bz2
FREETYPE_URL=http://download.savannah.gnu.org/releases/freetype/${FREETYPE_FILE}
URL=http://download.altera.com/akdlm/software/acdsinst/16.1/196/ib_installers/ModelSimSetup-16.1.0.196-linux.run

CACHE_DIR="${HOME}/cache/"
MSIM_INSTALLER="${CACHE_DIR}/modelsim.run"
BUILDERS="${HOME}/builders/"
INSTALLATION_DIR="${BUILDERS}/msim/"

mkdir -p "${CACHE_DIR}"

if [ ! -d "${INSTALLATION_DIR}" ]; then

  if [ ! -f "${MSIM_INSTALLER}" ]; then
    wget ${URL} -O "${MSIM_INSTALLER}" --quiet
    chmod +x "${MSIM_INSTALLER}"
    ${MSIM_INSTALLER} --help
  fi

  mkdir -p "${INSTALLATION_DIR}"
  ${MSIM_INSTALLER} --mode unattended \
    --modelsim_edition modelsim_ase \
    --installdir "${INSTALLATION_DIR}"
fi

ls "${INSTALLATION_DIR}/modelsim_ase/"

if [ ! -d "${BUILDERS}/${FREETYPE}/objs/.libs/" ]; then
  if [ ! -f "${BUILDERS}/${FREETYPE_FILE}" ]; then
    wget "${FREETYPE_URL}" -O "${BUILDERS}/${FREETYPE_FILE}"
  fi

  tar xjvf "${BUILDERS}/${FREETYPE_FILE}" --directory="${BUILDERS}"
  pushd "${BUILDERS}/${FREETYPE}" || exit 1

  ./configure --build=i686-pc-linux-gnu "CFLAGS=-m32" "CXXFLAGS=-m32" "LDFLAGS=-m32"
  make -j

  popd || exit 1

fi

export LD_LIBRARY_PATH=$PWD/objs/.libs

set +x

"${INSTALLATION_DIR}/modelsim_ase/linuxaloem/vsim" -version
