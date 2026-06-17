#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

docker build --no-cache \
  -f Dockerfile.harmonic \
  --build-arg http_proxy=$HTTP_PROXY \
  --build-arg https_proxy=$HTTPS_PROXY \
  --build-arg HTTP_PROXY=$HTTP_PROXY \
  --build-arg HTTPS_PROXY=$HTTPS_PROXY \
  --network=host \
  -t ardupilot-sim-harmonic \
  .
