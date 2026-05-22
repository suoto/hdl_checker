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

FROM ubuntu:24.04

ENV BUILDERS /builders

ENV DEBIAN_FRONTEND noninteractive
RUN dpkg --add-architecture i386

# python3.12 ships with Ubuntu 24.04 main repos
ENV PACKAGES="ca-certificates    \
              ghdl-mcode         \
              git                \
              lib32stdc++6       \
              lib32z1            \
              libtcl8.6          \
              python3-pip        \
              python3.12         \
              python3.12-dev     \
              software-properties-common \
              wget"

RUN apt-get update -qq            && \
    apt-get install -qq $PACKAGES && \
    apt-get clean                 && \
    rm -rf /var/lib/apt/lists/*

# python3.11, python3.13 come from deadsnakes on Ubuntu 24.04
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update -qq                    && \
    apt-get install -qq python3.11 python3.11-dev python3.13 python3.13-dev && \
    apt-get clean                         && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install tox --break-system-packages
RUN pip3 install coverage>=7.2 --break-system-packages

RUN mkdir -p $BUILDERS/ghdl/bin && \
    ln -s /usr/bin/ghdl $BUILDERS/ghdl/bin/ghdl && \
    ln -s /usr/bin/ghdl-mcode $BUILDERS/ghdl/bin/ghdl-mcode

RUN $BUILDERS/ghdl/bin/ghdl --version

# ModelSim will be copied
COPY msim $BUILDERS/msim

# Test installations
RUN "$BUILDERS/ghdl/bin/ghdl" --version
RUN "$BUILDERS/msim/modelsim_ase/linuxaloem/vcom" -version
# RUN "/xsim/bin/xvhdl" -version

VOLUME /hdl_checker
WORKDIR /hdl_checker
