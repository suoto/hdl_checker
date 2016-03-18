#!/usr/bin/env bash
# This file is part of hdlcc.
#
# hdlcc is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# hdlcc is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with hdlcc.  If not, see <http://www.gnu.org/licenses/>.

ARGS=

CLEAN=0

while [ -n "$1" ]; do
  if [ "$1" == "ghdl" ]; then
    GHDL=1
  elif [ "$1" == "msim" ]; then
    MSIM=1
  elif [ "$1" == "xvhdl" ]; then
    XVHDL=1
  elif [ "$1" == "fallback" ]; then
    FALLBACK=1
  elif [ "$1" == "clean" ]; then
    CLEAN=1
  elif [ "$1" == "standalone" ]; then
    STANDALONE=1
  else
    ARGS+=" $1"
  fi

  shift
done

if [ -z "${GHDL}${MSIM}${FALLBACK}${STANDALONE}${XVHDL}" ]; then
  GHDL=1
  MSIM=1
  FALLBACK=1
  STANDALONE=1
fi

if [ "${CLEAN}" == "1" ]; then
  git clean -fdx && git submodule foreach --recursive git clean -fdx
  cd .ci/hdl_lib && git reset HEAD --hard
  cd -
fi

set -x
set +e

RESULT=0

if [ -n "${STANDALONE}" ]; then
  ./run_tests.py $ARGS hdlcc.tests.test_config_parser hdlcc.tests.test_source_file
  RESULT=$(($? || ${RESULT}))
fi

if [ -n "${FALLBACK}" ]; then
  ./run_tests.py $ARGS hdlcc.tests.test_project_builder hdlcc.tests.test_standalone_hdlcc
  RESULT=$(($? || ${RESULT}))
fi

if [ -n "${MSIM}" ]; then
  export BUILDER_NAME=msim
  export BUILDER_PATH=${HOME}/builders/msim/modelsim_ase/linux/

  ./run_tests.py $ARGS
  RESULT=$(($? || ${RESULT}))
fi

if [ -n "${XVHDL}" ]; then
  export BUILDER_NAME=xvhdl
  export BUILDER_PATH=${HOME}/dev/xvhdl/bin
  # export BUILDER_PATH=/opt/Xilinx/Vivado/2015.4/bin
  # if [ ! -d "${BUILDER_PATH}" ]; then
  #   export BUILDER_PATH=${HOME}/dev/xvhdl/bin
  # fi

  ./run_tests.py $ARGS
  RESULT=$(($? || ${RESULT}))
fi

if [ -n "${GHDL}" ]; then
  export BUILDER_NAME=ghdl
  if [ "${CI}" == "true" ]; then
    export BUILDER_PATH=${HOME}/builders/ghdl/bin/
  else
    if [ -f "${HOME}/.local/bin/ghdl" ]; then
      export BUILDER_PATH=${HOME}/.local/bin/ghdl
    else
      export BUILDER_PATH=${HOME}/builders/ghdl/bin/
    fi
  fi

  echo "BUILDER_PATH=$BUILDER_PATH"

  ./run_tests.py $ARGS
  RESULT=$(($? || ${RESULT}))
fi

coverage combine
coverage html

exit "${RESULT}"

