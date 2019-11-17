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

FROM ubuntu:19.04

ENV BUILDERS /builders

ENV DEBIAN_FRONTEND noninteractive
RUN dpkg --add-architecture i386

ENV PACKAGES="python2      \
              python2-dev  \
              python3.7    \
              python3.8    \
              python3-pip  \
              wget         \
              git          \
              gcc-multilib \
              g++-multilib \
              lib32z1      \
              lib32stdc++6 \
              lib32gcc1    \
              libtcl8.6    \
              libtinfo5"

RUN apt-get update -qq            && \
    apt-get install -qq $PACKAGES && \
    apt-get clean                 && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install tox
RUN pip3 install coverage==4.1
WORKDIR $BUILDERS

COPY ghdl $BUILDERS/ghdl
COPY msim $BUILDERS/msim
COPY xvhdl $BUILDERS/xvhdl

# Test installations
RUN "$BUILDERS/ghdl/bin/ghdl" --version
RUN "$BUILDERS/msim/modelsim_ase/linuxaloem/vcom" -version
RUN "$BUILDERS/xvhdl/bin/xvhdl" -version

VOLUME /hdl_checker
WORKDIR /hdl_checker
