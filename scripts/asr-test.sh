#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p .asr-cache asr-results
if ! test -s .asr.env; then
  read -rsp 'Hugging Face READ token (hidden): ' asr_token
  printf '\n'
  if [[ ! "$asr_token" =~ ^hf_[A-Za-z0-9]+$ ]]; then echo 'Invalid token format'; exit 1; fi
  printf 'HF_TOKEN=%s\nASR_UID=%s\nASR_GID=%s\n' "$asr_token" "$(id -u)" "$(id -g)" > .asr.env
  unset asr_token
fi
chmod 600 .asr.env
docker compose -f compose.yml -f compose.asr.yml --profile asr build asr-test
docker compose -f compose.yml -f compose.asr.yml --profile asr run --rm --no-deps -it asr-test "$@"
