#!/usr/bin/env bash
# The project's own checks, run by `bash .claude/tools/verify.sh --full`.
# Backend: lint, format, types, tests. Frontend: lint, types, tests, build.
# Integration tests run when Postgres is reachable (docker compose up -d db in repo/);
# set REQUIRE_DB=1 to make a missing database a failure instead of a skip.
set -u
root="$(cd "$(dirname "$0")/../.." && pwd)"
fail=0

run() { # $1 = label, rest = command
  local label="$1"; shift
  if "$@" >/tmp/verify-project.$$.log 2>&1; then
    echo "  PASS  $label"
  else
    echo "  FAIL  $label"; sed 's/^/        /' /tmp/verify-project.$$.log | tail -25; fail=1
  fi
}

if command -v uv >/dev/null 2>&1; then UV=(uv); else UV=(python -m uv); fi

echo "backend (repo/backend)"
cd "$root/repo/backend" || exit 1
run "uv sync"             "${UV[@]}" sync --quiet
run "ruff check"          "${UV[@]}" run ruff check .
run "ruff format --check" "${UV[@]}" run ruff format --check .
run "mypy"                "${UV[@]}" run mypy app
run "pytest"              "${UV[@]}" run pytest -q

echo "frontend (repo/frontend)"
cd "$root/repo/frontend" || exit 1
run "pnpm install"   pnpm install --frozen-lockfile --silent
run "pnpm lint"      pnpm lint
run "pnpm typecheck" pnpm typecheck
run "pnpm test"      pnpm test
run "pnpm build"     pnpm build

rm -f /tmp/verify-project.$$.log
exit "$fail"
