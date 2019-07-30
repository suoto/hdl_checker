FROM ubuntu:19.04

RUN apt-get update
RUN apt-get install python3 python3-pip -y
RUN pip3 install tox

ARG UID=1000
ARG GID=1001
ENV USER user
ENV HOME /home/user
# ...
RUN addgroup --system $USER --gid $GID \
       && adduser --system --gid $GID --uid $UID --home $HOME $USER
# ...
USER $USER
WORKDIR $HOME/builders
COPY * ./
WORKDIR $HOME/hdlcc
ENTRYPOINT ["ls -la"]
