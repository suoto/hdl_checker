FROM ubuntu:18.04
# RUN dpkg --add-architecture i686
RUN apt-get update
RUN apt-get install wget -y
RUN dpkg --add-architecture i386
RUN apt-get install -qq build-essential
RUN apt-get install -qq gcc-multilib g++-multilib lib32z1 lib32stdc++6 lib32gcc1 
ARG FREETYPE
ENV FREETYPE_URL=http://download.savannah.gnu.org/releases/freetype/$FREETYPE.tar.bz2
WORKDIR /cache
RUN wget --quiet $FREETYPE_URL -O "${FREETYPE}.tar.bz2"
RUN tar xjvf "${FREETYPE}.tar.bz2"
WORKDIR "$FREETYPE"
RUN ./configure --build=i686-pc-linux-gnu "CFLAGS=-m32" "CXXFLAGS=-m32" "LDFLAGS=-m32"
RUN make -j
ENV LD_LIBRARY_PATH=/cache/freetype-2.4.12/objs/.libs
WORKDIR /cache
ARG MODELSIM_URL
ARG GHDL_URL
RUN wget --quiet $MODELSIM_URL -O modelsim.run
RUN wget --quiet $GHDL_URL     -O ghdl.tar.gz
RUN ls -la
RUN chmod +x modelsim.run
RUN mkdir -p /builders
RUN ./modelsim.run --mode unattended  \
      --modelsim_edition modelsim_ase \
      --installdir "/builders"
