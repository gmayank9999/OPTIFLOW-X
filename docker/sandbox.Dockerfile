FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ clang make valgrind time \
    linux-tools-generic linux-tools-common \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m runner
USER runner
WORKDIR /work
