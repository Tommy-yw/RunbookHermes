#!/usr/bin/env bash
set -euo pipefail
PROFILE_ROOT="${HERMES_HOME:-$HOME/.hermes}/profiles/runbook-hermes"
mkdir -p "$PROFILE_ROOT"
cp profiles/runbook-hermes/config.yaml "$PROFILE_ROOT/config.yaml"
cp profiles/runbook-hermes/SOUL.md "$PROFILE_ROOT/SOUL.md"
if [ ! -f "$PROFILE_ROOT/.env" ]; then
  cp profiles/runbook-hermes/.env.example "$PROFILE_ROOT/.env"
fi
mkdir -p "$PROFILE_ROOT/skills"
echo "Installed RunbookHermes profile to $PROFILE_ROOT"
