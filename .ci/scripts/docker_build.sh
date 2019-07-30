#!/usr/bin/env bash

set -xe

CONTEXT=~/context/
# CONTEXT=.
PATH_TO_THIS_SCRIPT=$(realpath "$(dirname "$0")")
DOCKERFILE=$PATH_TO_THIS_SCRIPT/Dockerfile

docker build -t suoto/hdlcc:v0.5.1 -f "$DOCKERFILE" "$CONTEXT"

