#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${RUNBOOK_DOCKER_SMOKE_MODE:-static}"
required=(
  "Dockerfile"
  ".dockerignore"
  "data/runbook_mock/scenarios/payment_503_spike.json"
  "skills/runbooks/payment-503-spike/SKILL.md"
  "web/static/app.js"
  "runbook_hermes/rag.py"
)
for path in "${required[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "missing required Docker context file: $path" >&2
    exit 2
  fi
done
if grep -Eq '^data/?$|^data/|^\*\.md$|^SKILL\.md$|^skills/' .dockerignore; then
  echo ".dockerignore appears to exclude required RunbookHermes data or skill markdown" >&2
  exit 3
fi
if [[ "$mode" == "build" ]]; then
  docker build -t runbookhermes-smoke:local .
fi
echo "runbook docker smoke ok ($mode)"
