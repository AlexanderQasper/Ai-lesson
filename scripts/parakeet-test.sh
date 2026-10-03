#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p .asr-cache asr-results
docker compose -f compose.yml -f compose.asr.yml -f compose.parakeet.yml --profile asr build asr-test
docker compose -f compose.yml -f compose.asr.yml -f compose.parakeet.yml --profile asr run --rm --no-deps -T asr-test
