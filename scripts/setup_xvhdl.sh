#!/usr/bin/env bash
# This file is part of HDL Code Checker.
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

# 8.7 GB installer
FULL_INSTALLER_URL="http://xilinx-ax-dl.entitlenow.com/akdlm/dl/ul/2015/11/20/R209870202/Xilinx_Vivado_SDK_Lin_2015.4_1118_2.tar.gz/dfe5fd62964d9da3c1287781d8547c0c/56EB03B7/Xilinx_Vivado_SDK_Lin_2015.4_1118_2.tar.gz?akdm=1&filename=Xilinx_Vivado_SDK_Lin_2015.4_1118_2.tar.gz&fileExt=.gz"

# # 70 MB web installer
WEB_INSTALLER_URL="https://xilinx-ax-dl.entitlenow.com/dl/ul/2015/11/19/R209870197/Xilinx_Vivado_SDK_2015.4_1118_2_Lin64.bin/e8fe3803d3324af90f6f1d32a447c482/56EB1544?akdm=0&filename=Xilinx_Vivado_SDK_2015.4_1118_2_Lin64.bin"

CACHE_DIR="${HOME}/cache/"

INSTALLATION_DIR="${HOME}/builders/xvhdl/"

mkdir -p ${CACHE_DIR}
mkdir -p ${INSTALLATION_DIR}

if [ -n "${FULL_INSTALLER}" ]; then
  XVHDL_TAR_GZ="${CACHE_DIR}/xvhdl.tar.gz"

  if [ ! -f "${XVHDL_TAR_GZ}" ]; then
    wget ${FULL_INSTALLER_URL} -O ${XVHDL_TAR_GZ}
  fi

  if [ ! -d "${INSTALLATION_DIR}/bin" ]; then
    mkdir -p ${INSTALLATION_DIR}
    tar zxvf ${XVHDL_TAR_GZ} --directory ${INSTALLATION_DIR}
  fi

  ls ${INSTALLATION_DIR}

  ${INSTALLATION_DIR}/xsetup --agree XilinxEULA,3rdPartyEULA,WebTalkTerms \
    --batch Install \
    --location ~/builders/xvhdl/ \
    --edition "Vivado HL WebPACK" \
    -x

else

  XVHDL_RUN="${CACHE_DIR}/xvhdl.run"
  if [ ! -f "${XVHDL_RUN}" ]; then
    wget ${FULL_INSTALLER_URL} -O ${XVHDL_RUN}
    chmod +x ${XVHDL_RUN}
  fi

  ${XVHDL_RUN} --noexec --keep --target ~/xvhdl/

  # Vivado batch mode installer options
  # Running in batch mode...
  # Copyright (c) 1986-2016 Xilinx, Inc.  All rights reserved.

  # usage: xsetup [-a <arg>] [-b <arg>] [-c <arg>] [-e <arg>] [-h] [-l <arg>]
  #        [-x]
  # Xilinx Installer - Command line argument list.
  #  -a,--agree <arg>      Agree to the required terms and conditions.
  #                        [XilinxEULA,3rdPartyEULA,WebTalkTerms]
  #  -b,--batch <arg>      Runs installer in batch mode and executes the
  #                        specified action. [ConfigGen, Install, Uninstall,
  #                        Add, Update]
  #  -c,--config <arg>     Properties file defining install configuration
  #  -e,--edition <arg>    Name of the edition that should be installed.
  #  -h,--help             Display this help text.
  #  -l,--location <arg>   Specifies the destination location of the
  #                        installation.
  #  -x,--xdebug           Run installer in debug mode

  ~/xvhdl/xsetup --agree XilinxEULA,3rdPartyEULA,WebTalkTerms \
    --batch ConfigGen\
    --location ~/builders/xvhdl/ \
    --edition "Vivado HL WebPACK" \
    --config config.cfg \
    -x

fi

