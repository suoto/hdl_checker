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

FROM suoto/xsim:2018.3

ENV BUILDERS /builders

ENV DEBIAN_FRONTEND noninteractive
RUN dpkg --add-architecture i386

ENV PACKAGES="ca-certificates \
              g++-multilib    \
              gcc             \
              gcc-multilib    \
              git             \
              gnat            \
              lib32gcc1       \
              lib32stdc++6    \
              lib32z1         \
              libtcl8.6       \
              make            \
              python2.7       \
              python2.7-dev   \
              python3-pip     \
              python3.6       \
              python3.6-dev   \
              python3.7       \
              python3.7-dev   \
              python3.8       \
              python3.8-dev   \
              wget            \
              zlib1g-dev"

RUN apt-get update -qq            && \
    apt-get install -qq $PACKAGES && \
    apt-get clean                 && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install tox
RUN pip3 install coverage==4.1

WORKDIR $BUILDERS

# Build GHDL from source
WORKDIR /tmp/
RUN git clone --depth=1 --branch=v0.36 https://github.com/ghdl/ghdl
WORKDIR /tmp/ghdl
WORKDIR /tmp/ghdl/build

RUN ../configure --prefix=$BUILDERS/ghdl && \
    make -j                              && \
    make install

RUN apt-get purge -qq make zlib1g-dev && \
    apt-get clean                     && \
    apt-get autoclean
RUN rm -rf /tmp/ghdl

RUN $BUILDERS/ghdl/bin/ghdl --version

# ModelSim will be copied
COPY msim $BUILDERS/msim

# Test installations
RUN "$BUILDERS/ghdl/bin/ghdl" --version
RUN "$BUILDERS/msim/modelsim_ase/linuxaloem/vcom" -version
RUN "/xsim/bin/xvhdl" -version

VOLUME /hdl_checker
WORKDIR /hdl_checker
