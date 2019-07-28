#!/usr/bin/env bash

set -xe

CONTEXT=~/context
PATH_TO_THIS_SCRIPT=$(realpath "$(dirname "$0")")
DOCKERFILE=$PATH_TO_THIS_SCRIPT/Dockerfile

FREETYPE=freetype-2.4.12

MODELSIM_URL=http://download.altera.com/akdlm/software/acdsinst/16.1/196/ib_installers/ModelSimSetup-16.1.0.196-linux.run
GHDL_URL=http://downloads.sourceforge.net/project/ghdl-updates/Builds/ghdl-0.33/ghdl-0.33-x86_64-linux.tgz

docker build -t suoto/hdlcc:v0.5.1 -f "$DOCKERFILE" \
  --build-arg FREETYPE=$FREETYPE                    \
  --build-arg MODELSIM_URL=$MODELSIM_URL            \
  --build-arg GHDL_URL=$GHDL_URL                    \
  "$CONTEXT"

