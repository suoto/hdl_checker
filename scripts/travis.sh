#!/usr/bin/env bash

set -x
set +e

RESULT=0


./run_tests.py $*
RESULT=$(($? || ${RESULT}))


export BUILDER_NAME=msim
export BUILDER_PATH=${HOME}/builders/msim/modelsim_ase/linux/

./run_tests.py $*
RESULT=$(($? || ${RESULT}))

export BUILDER_NAME=ghdl
export BUILDER_PATH=${HOME}/builders/ghdl/bin/
# export BUILDER_PATH=${HOME}/.local/bin/ghdl
./run_tests.py $*
RESULT=$(($? || ${RESULT}))

coverage combine
coverage html

exit ${RESULT}

