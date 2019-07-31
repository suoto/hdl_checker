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

RUN apt-get update -qq

RUN apt-get install python3 python3-pip -y
ENV DEBIAN_FRONTEND noninteractive
RUN dpkg --add-architecture i386
RUN apt-get install -qq libtcl8.6
RUN apt-get install -qq wget
RUN apt-get install -qq gcc-multilib g++-multilib lib32z1 lib32stdc++6 lib32gcc1 libtcl8.6

RUN pip3 install tox

ENV USER root
ENV HOME /root
ENV CACHE_DIR $HOME/cache

WORKDIR $HOME

# Download files
RUN wget --quiet http://downloads.sourceforge.net/project/ghdl-updates/Builds/ghdl-0.33/ghdl-0.33-x86_64-linux.tgz
RUN wget --quiet http://download.altera.com/akdlm/software/acdsinst/19.2/57/ib_installers/ModelSimProSetup-19.2.0.57-linux.run
RUN wget --quiet http://download.altera.com/akdlm/software/acdsinst/19.2/57/ib_installers/modelsim-part2-19.2.0.57-linux.qdz

# Install GHDL
RUN mkdir -p $HOME/builders/ghdl
RUN tar zxvf ghdl-0.33-x86_64-linux.tgz --directory $HOME/builders/ghdl

# Install ModelSim
RUN chmod +x ModelSimProSetup-19.2.0.57-linux.run
RUN mkdir -p $HOME/builders
RUN ./ModelSimProSetup-19.2.0.57-linux.run --mode unattended \
        --modelsim_edition modelsim_ase                    \
        --accept_eula 1                                    \
        --installdir $HOME/builders/msim

# Test installations
RUN $HOME/builders/ghdl/bin/ghdl --version
RUN $HOME/builders/msim/modelsim_ase/linuxaloem/vcom -version
