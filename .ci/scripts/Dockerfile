# This file is part of HDL Code Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
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

FROM ubuntu:19.04

ENV USERNAME user
ENV BUILDERS /builders

ENV DEBIAN_FRONTEND noninteractive
RUN dpkg --add-architecture i386

RUN apt-get update -qq
RUN apt-get install -qq python2 python3 python3-pip wget git
RUN apt-get install -qq gcc-multilib g++-multilib lib32z1 lib32stdc++6 lib32gcc1 libtcl8.6

RUN pip3 install tox

WORKDIR $BUILDERS

COPY ghdl $BUILDERS/ghdl
COPY msim $BUILDERS/msim

# Test installations
RUN $BUILDERS/ghdl/bin/ghdl --version
RUN $BUILDERS/msim/modelsim_ase/linuxaloem/vcom -version

VOLUME /hdlcc
ENTRYPOINT "/hdlcc/.ci/scripts/docker_entry_point.sh"
