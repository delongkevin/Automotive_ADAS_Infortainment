FROM ubuntu:24.04 AS base

LABEL maintainer="James Oldiges <james.oldiges@magna.com>"
ARG USERNAME=default
ARG UID=1001
ARG GID=1001
ENV DEBIAN_FRONTEND=noninteractive TZ=America/New_York
WORKDIR /workspace

VOLUME /Windriver
VOLUME /QAC

# Base packages generically wanted and expected.
RUN apt-get update && apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends \
      ca-certificates gnupg apt-transport-https \
      file git git-lfs python3 python3-pip python3-venv \
      sudo wget curl rsync gnupg-agent software-properties-common && \
    rm -rf /var/lib/apt/lists/*


# Project tools and utilities
RUN apt-get update && apt-get dist-upgrade -y && \
    apt-get install -y --no-install-recommends \
      ninja-build openjdk-25-jdk p7zip && \
    rm -rf /var/lib/apt/lists/*


# 32-bit libs for WindRiver
RUN dpkg --add-architecture i386 && apt-get update && \
    apt-get install -y --no-install-recommends libc6:i386 libstdc++6:i386 zlib1g:i386 && \
    rm -rf /var/lib/apt/lists/*

# tzdata (properly configure timezone)
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && dpkg-reconfigure -f noninteractive tzdata && \
    rm -rf /var/lib/apt/lists/*

# Kitware CMake repo for latest versioning
RUN apt update && \
    apt install -y software-properties-common && \
    apt-add-repository 'deb https://apt.kitware.com/ubuntu/ noble main' && \
    wget -O - https://apt.kitware.com/keys/kitware-archive-latest.asc | apt-key add - && \
    apt update && apt install -y cmake

# PowerShell
RUN apt-get update && apt-get install -y --no-install-recommends wget && \
    . /etc/os-release && \
    wget -q https://packages.microsoft.com/config/ubuntu/$VERSION_ID/packages-microsoft-prod.deb && \
    dpkg -i packages-microsoft-prod.deb && rm packages-microsoft-prod.deb && \
    apt-get update && apt-get install -y --no-install-recommends powershell && \
    rm -rf /var/lib/apt/lists/*

# User
RUN groupadd -g "$GID" mygroup || true && \
    useradd --no-log-init -u "$UID" -g "$GID" -ms /bin/bash "$USERNAME" && \
    usermod -aG dialout "$USERNAME" && \
    install -d -o "$USERNAME" -g "$GID" /workspace && \
    echo "$USERNAME ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/$USERNAME

USER $USERNAME
ENV USER=$USERNAME

CMD ["bash","-l"]
