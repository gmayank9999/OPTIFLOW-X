FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ clang make valgrind time binutils \
    linux-tools-generic linux-tools-common \
    && rm -rf /var/lib/apt/lists/*

# The `perf` wrapper in linux-tools-common refuses to run unless a tools
# package matching the *host* kernel is installed, which never exists for
# WSL2 or most cloud kernels. The versioned binary itself works fine
# against any recent kernel, so expose it directly.
RUN ln -sf "$(ls -d /usr/lib/linux-tools/*/perf | head -n1)" /usr/local/bin/perf-raw

# High-resolution, interleaving benchmark harness (see docker/hrtime.c).
COPY docker/hrtime.c /tmp/hrtime.c
RUN gcc -O2 -o /usr/local/bin/hrtime /tmp/hrtime.c && rm /tmp/hrtime.c

RUN useradd -m runner
USER runner
WORKDIR /work
