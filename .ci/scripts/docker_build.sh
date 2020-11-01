#!/usr/bin/env bash
# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.

set -xe

DOCKER_TAG="${DOCKER_TAG:-latest}"
PATH_TO_THIS_SCRIPT=$(readlink -f "$(dirname "$0")")
DOCKERFILE=$PATH_TO_THIS_SCRIPT/Dockerfile
CONTEXT=$HOME/context
DOWNLOAD_DIR=$HOME/Downloads

mkdir -p "$CONTEXT"

# $1 Test filename
# $2 URL
function download_if_needed {
  filename=$1
  url=$2

  if [ ! -f "$filename" ]; then
    wget "$url" -O "$filename"
  fi
}

function setup_msim {

  pushd "$CONTEXT" || exit 1

  URL_MAIN=http://download.altera.com/akdlm/software/acdsinst/19.2/57/ib_installers/ModelSimProSetup-19.2.0.57-linux.run
  URL_PART_2=http://download.altera.com/akdlm/software/acdsinst/19.2/57/ib_installers/modelsim-part2-19.2.0.57-linux.qdz

  installer=$(basename $URL_MAIN)

  download_if_needed "$DOWNLOAD_DIR/$installer" $URL_MAIN
  download_if_needed "$DOWNLOAD_DIR/$(basename $URL_PART_2)" $URL_PART_2

  if [ ! -f "$CONTEXT/msim/modelsim_ase/linuxaloem/vsim" ]; then
    chmod +x "$DOWNLOAD_DIR/$installer"
    "$DOWNLOAD_DIR/$installer" --mode unattended \
          --modelsim_edition modelsim_ase        \
          --accept_eula 1                        \
          --installdir "$CONTEXT"/msim

    rm -rf "$CONTEXT"/msim/modelsim_ase/altera
  fi

  popd || exit 1

}

setup_msim

"$CONTEXT"/msim/modelsim_ase/linuxaloem/vsim -version

docker build -t suoto/hdl_checker_test:"$DOCKER_TAG" -f "$DOCKERFILE" "$CONTEXT"

