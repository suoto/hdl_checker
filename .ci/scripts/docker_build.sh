#!/usr/bin/env bash

set -xe

DOCKER_TAG="${DOCKER_TAG:-latest}"

# CONTEXT=~/context/
# CONTEXT=.
PATH_TO_THIS_SCRIPT=$(realpath "$(dirname "$0")")
DOCKERFILE=$PATH_TO_THIS_SCRIPT/Dockerfile
CONTEXT=$(realpath "$PATH_TO_THIS_SCRIPT"/../../)

docker build -t suoto/hdlcc:"$DOCKER_TAG" -f "$DOCKERFILE" "$CONTEXT"

