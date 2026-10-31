#!/usr/bin/env bash
# Full-flow e2e: fresh DB, API + worker (scripted fake LLM, no network), built frontend, Playwright.
# Always tears everything down, even on failure. Safe to run next to a dev stack: it uses its own
# database (qbank_e2e), Redis db 7, a temp storage dir and the ports 18000 / 14173.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

API_PORT="${E2E_API_PORT:-18000}"
WEB_PORT="${E2E_WEB_PORT:-14173}"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/qbank-e2e.XXXXXX")"
PIDS=()

export QBANK_ENV=dev
export QBANK_DATABASE_URL="${E2E_DATABASE_URL:-postgresql+psycopg://qbank:qbank@localhost:25432/qbank_e2e}"
export QBANK_REDIS_URL="${E2E_REDIS_URL:-redis://localhost:26379/7}"
export QBANK_STORAGE_BACKEND=local
export QBANK_STORAGE_LOCAL_ROOT="$WORK/storage"
export QBANK_LLM_MODE=fake
export QBANK_LLM_FAKE_SCRIPT="$ROOT/scripts/e2e/fake_llm.json"
export QBANK_OPENROUTER_API_KEY=
export QBANK_COOKIE_SECURE=false
export QBANK_SSE_INTERVAL=0.5
export QBANK_API_PROXY_TARGET="http://127.0.0.1:$API_PORT"
export E2E_BASE_URL="http://127.0.0.1:$WEB_PORT"
export E2E_WORKBOOK="$ROOT/scripts/e2e/workbook.pdf"
export CI="${CI:-}"

cleanup() {
  local status=$?
  set +e
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill -TERM -- "-$pid" 2>/dev/null
  done
  sleep 1
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] && kill -KILL -- "-$pid" 2>/dev/null
  done
  uv run --directory backend python "$ROOT/scripts/e2e/reset_db.py" drop >/dev/null 2>&1
  rm -rf "$WORK"
  exit "$status"
}
trap cleanup EXIT INT TERM

start() { # start <name> <command...>: run in its own process group so cleanup can kill the tree
  local name="$1"
  shift
  setsid "$@" >"$WORK/$name.log" 2>&1 &
  PIDS+=("$!")
}

wait_for() { # wait_for <name> <url> <seconds>
  local deadline=$((SECONDS + $3))
  until curl -fs -o /dev/null "$2"; do
    if [ "$SECONDS" -ge "$deadline" ]; then
      echo "Timed out waiting for $1 at $2" >&2
      tail -n 40 "$WORK/$1.log" >&2 || true
      return 1
    fi
    sleep 1
  done
}

show_logs() {
  for name in api worker web; do
    echo "----- $name log (tail) -----" >&2
    tail -n 60 "$WORK/$name.log" >&2 2>/dev/null || true
  done
}

echo "==> Fresh database and seed data"
uv run --directory backend python "$ROOT/scripts/e2e/reset_db.py" reset
uv run --directory backend alembic -c alembic.ini upgrade head
uv run --directory backend python -m qbank.cli seed-dev

echo "==> Building the frontend"
pnpm -C frontend build

echo "==> Starting API, worker and preview server"
start api uv run --directory backend uvicorn qbank.api.main:app --host 127.0.0.1 --port "$API_PORT"
start worker uv run --directory backend dramatiq qbank.worker --processes 1 --threads 2
start web pnpm -C frontend exec vite preview --host 127.0.0.1 --port "$WEB_PORT" --strictPort
wait_for api "http://127.0.0.1:$API_PORT/api/v1/health" 90
wait_for web "$E2E_BASE_URL/" 60
wait_for web "$E2E_BASE_URL/api/v1/health" 30

if [ -n "${E2E_STACK_ONLY:-}" ]; then
  echo "==> Stack is up at $E2E_BASE_URL (E2E_STACK_ONLY): Ctrl-C to stop"
  wait
fi

echo "==> Playwright"
if pnpm -C frontend exec playwright test "$@"; then
  echo "==> e2e passed"
else
  status=$?
  show_logs
  exit "$status"
fi
