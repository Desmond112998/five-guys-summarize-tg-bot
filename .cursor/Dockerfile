FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_BREAK_SYSTEM_PACKAGES=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    postgresql \
    postgresql-contrib \
    sudo \
    curl \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Allow passwordless sudo for the default ubuntu user used by cloud agents
RUN echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/ubuntu \
    && chmod 0440 /etc/sudoers.d/ubuntu

WORKDIR /workspace
