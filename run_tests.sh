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

VIRTUAL_ENV_DEST=~/dev/hdlcc_venv

ARGS=()

CLEAN_PIP=1

while [ -n "$1" ]; do
  if [ "$1" == "-h" ]; then
    HELP=1
  elif [ "$1" == "ghdl" ]; then
    GHDL=1
  elif [ "$1" == "msim" ]; then
    MSIM=1
  elif [ "$1" == "xvhdl" ]; then
    XVHDL=1
  elif [ "$1" == "fallback" ]; then
    FALLBACK=1
  elif [ "$1" == "reuse-pip" ]; then
    CLEAN_PIP=0
  elif [ "$1" == "standalone" ]; then
    STANDALONE=1
  elif [ -f "$1" ]; then
    NEW_ARG="$(echo "$1" | sed -e 's/\//./g' -e 's/\.py$//')"
    echo "Changed argument \"$1\" to \"$NEW_ARG\""
    ARGS+=($NEW_ARG)
  else
    if [ "$1" == "-F" ]; then
      FAILFAST=1
    fi
    ARGS+=($1)
  fi

  shift
done

if [ -n "${HELP}" ]; then
  echo "Usage: $0 [ghdl|msim|xvhdl|fallback] [reuse-pip] [standalone]"
  exit 0
fi


if [ -z "${GHDL}${MSIM}${FALLBACK}${STANDALONE}${XVHDL}" ]; then
  GHDL=1
  MSIM=1
  FALLBACK=1
  XVHDL=1
  STANDALONE=1
  CLEAN_PIP=1
fi

git clean -fdx && git submodule foreach --recursive git clean -fdx

set -x
set +e

RESULT=0

# # If we're not running on a CI server, create a virtual env to mimic
# # its behaviour
# if [ "${CLEAN_PIP}" == "1" -a -z "${CI}" ]; then
#   if [ -d "${VIRTUAL_ENV_DEST}" ]; then
#     rm -rf ${VIRTUAL_ENV_DEST}
#   fi
# fi

# if [ -z "${CI}" ]; then
#   virtualenv ${VIRTUAL_ENV_DEST}
#   . ${VIRTUAL_ENV_DEST}/bin/activate

#   pip install -r requirements.txt
#   pip install git+https://github.com/suoto/rainbow_logging_handler
# fi

# . ${VIRTUAL_ENV_DEST}/bin/activate

pip uninstall hdlcc -y
pip install -e .

RESULT=$(($? || RESULT))
[ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}

hdlcc -h
RESULT=$(($? || RESULT))
[ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}


if [ "${RESULT}" != "0" ]; then
  exit ${RESULT}
fi

TEST_RUNNER="./.ci/scripts/run_tests.py"

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

# ${TEST_RUNNER} "${ARGS[@]}"

if [ -n "${STANDALONE}" ]; then
  ${TEST_RUNNER} "${ARGS[@]}" hdlcc.tests.test_config_parser \
                              hdlcc.tests.test_vhdl_parser \
                              hdlcc.tests.test_verilog_parser \
                              hdlcc.tests.test_misc

  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

if [ -n "${FALLBACK}" ]; then
  ${TEST_RUNNER} "${ARGS[@]}" hdlcc.tests.test_builders \
                              hdlcc.tests.test_hdlcc_base \
                              hdlcc.tests.test_server_handlers \
                              hdlcc.tests.test_standalone

  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

if [ -n "${MSIM}" ]; then
  export BUILDER_NAME=msim
  export BUILDER_PATH=${HOME}/builders/msim/modelsim_ase/linux/

  ${TEST_RUNNER} "${ARGS[@]}" hdlcc.tests.test_builders \
                              hdlcc.tests.test_hdlcc_base \
                              hdlcc.tests.test_persistency \
                              hdlcc.tests.test_server_handlers \
                              hdlcc.tests.test_standalone
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

if [ -n "${XVHDL}" ]; then
  export BUILDER_NAME=xvhdl
  export BUILDER_PATH=${HOME}/builders/xvhdl/bin
  if [ ! -d "${BUILDER_PATH}" ]; then
    export BUILDER_PATH=${HOME}/dev/xvhdl/bin
  fi

  VUNIT_VHDL_STANDARD=93 ${TEST_RUNNER} "${ARGS[@]}" hdlcc.tests.test_builders \
                                                     hdlcc.tests.test_hdlcc_base \
                                                     hdlcc.tests.test_persistency \
                                                     hdlcc.tests.test_server_handlers \
                                                     hdlcc.tests.test_standalone
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
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

  ${TEST_RUNNER} "${ARGS[@]}" hdlcc.tests.test_builders \
                              hdlcc.tests.test_hdlcc_base \
                              hdlcc.tests.test_persistency \
                              hdlcc.tests.test_server_handlers \
                              hdlcc.tests.test_standalone
  RESULT=$(($? || RESULT))
  [ -n "${FAILFAST}" ] && [ "${RESULT}" != "0" ] && exit ${RESULT}
fi

coverage combine
coverage html
# coverage report

exit "${RESULT}"

