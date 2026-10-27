#!/usr/bin/env bash
# GCE startup script for an OPTIFLOW-X VM (Ubuntu 22.04). Idempotent: runs
# on every boot, installs Docker once, and keeps a checkout in /opt/optiflow-x.
set -euo pipefail

REPO_URL="${OPTIFLOW_REPO_URL:-$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/repo-url || true)}"

if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y ca-certificates curl git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi

# perf counters for the (trusted) baseline profiler; candidates never get CAP_PERFMON.
sysctl -w kernel.perf_event_paranoid=1 || true

# Shared work dir: same path on host and in the app container (see docker-compose.yml).
mkdir -p /var/optiflow/work
chown 10001:10001 /var/optiflow/work

if [ -n "$REPO_URL" ] && [ ! -d /opt/optiflow-x/.git ]; then
  git clone "$REPO_URL" /opt/optiflow-x
fi
if [ -d /opt/optiflow-x ]; then
  mkdir -p /opt/optiflow-x/results
  chown -R 10001:10001 /opt/optiflow-x/results
fi
