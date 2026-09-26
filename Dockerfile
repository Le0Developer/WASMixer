FROM alpine:3.24

ENV USER=wasmixer \
    PASSWD=wasmixer \
    WORKDIR=WASMixer \
    PATH="/opt/venv/bin:$PATH"

ENV PYTHONPATH="/home/wasmixer:${PYTHONPATH}"

RUN apk add --no-cache \
      bash \
      bash-completion \
      boost-dev \
      build-base \
      cmake \
      curl \
      gdb \
      gdbserver \
      git \
      gnupg \
      linux-headers \
      net-tools \
      openssh-server \
      python3 \
      python3-dev \
      py3-pip \
      rsync \
      shadow \
      sudo \
      tar \
    && python3 -m venv /opt/venv \
    && python -m pip install --upgrade pip

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

RUN adduser -D -h "/home/${USER}" "${USER}" \
    && echo "${USER}:${PASSWD}" | chpasswd \
    && echo "${USER} ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers \
    && chmod 0440 /etc/sudoers \
    && mkdir -p "/home/${USER}/${WORKDIR}"

COPY WASMixer/ "/home/${USER}/${WORKDIR}/"
COPY start.sh /start.sh

RUN chmod +x /start.sh

WORKDIR "/home/${USER}/${WORKDIR}"
CMD ["/start.sh"]
