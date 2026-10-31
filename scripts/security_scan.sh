#!/usr/bin/env bash
# Local dependency vulnerability scan -- the same checks .github/workflows/security-scan.yml
# runs in CI, runnable on demand without waiting for a push.
#
# Requires: pip-audit (`pip install pip-audit`), node/npm.
#
# Usage: ./scripts/security_scan.sh
# Exits non-zero if any high/critical npm finding or any pip-audit finding turns up,
# matching the CI workflow's own pass/fail bar.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAILED=0

echo "=============================================="
echo " DealerOS dependency security scan"
echo "=============================================="

if ! command -v pip-audit >/dev/null 2>&1; then
  echo ""
  echo "!! pip-audit not found -- skipping Python checks."
  echo "   Install with: pip install pip-audit"
  FAILED=1
else
  for target in backend hub; do
    echo ""
    echo "--- pip-audit: ${target}/requirements.txt ---"
    if ! pip-audit -r "${target}/requirements.txt" --strict; then
      FAILED=1
    fi
  done
fi

if ! command -v npm >/dev/null 2>&1; then
  echo ""
  echo "!! npm not found -- skipping JS/TS checks."
  FAILED=1
else
  for target in frontend dealeros-ui; do
    echo ""
    echo "--- npm audit: ${target} ---"
    (
      cd "$target" || exit 1
      if [ ! -d node_modules ]; then
        echo "(no node_modules -- running npm ci first)"
        npm ci --silent
      fi
      npm audit --audit-level=high
    )
    # shellcheck disable=SC2181
    if [ $? -ne 0 ]; then
      FAILED=1
    fi
  done
fi

echo ""
echo "=============================================="
if [ "$FAILED" -ne 0 ]; then
  echo " Scan found something worth a human look. See output above."
  echo " Moderate/low findings with no fix available yet are expected and tracked"
  echo " in docs/SECURITY_ARCHITECTURE.md -- only high/critical or an unresolved"
  echo " pip-audit finding should be new."
else
  echo " Clean -- no high/critical findings."
fi
echo "=============================================="

exit "$FAILED"
