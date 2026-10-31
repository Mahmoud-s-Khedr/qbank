#!/usr/bin/env bash
# Dispatch a task to a coding agent in its own git worktree.
#
#   scripts/agent.sh codex T01 [effort]        # effort: low|medium|high (default medium)
#   scripts/agent.sh agy   T02 [model]         # model: gemini-4-argon-high (default)
#   scripts/agent.sh quota                     # print remaining Codex + agy quota
#
# Worktrees live in ../Qbank-wt/<task>, on branch task/<task>. Logs go to .agent-logs/.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WT_BASE="$(dirname "$ROOT")/Qbank-wt"
LOGS="$ROOT/.agent-logs"
mkdir -p "$LOGS"

quota() {
  echo "== Codex (codex-personal)"
  local f
  f=$(find "$HOME/.codex-personal/sessions" -name '*.jsonl' -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2)
  if [[ -n "$f" ]]; then
    grep -o '"primary":{[^}]*},"secondary":{[^}]*}' "$f" | tail -1 | python3 -c '
import json, sys, datetime
d = json.loads("{" + sys.stdin.read().strip() + "}")
for k, name in (("primary", "5h"), ("secondary", "weekly")):
    v = d[k]
    reset = datetime.datetime.fromtimestamp(v["resets_at"]).strftime("%a %d %b %H:%M")
    pct = v["used_percent"]
    print(f"  {name:6s} used {pct:5.1f}%  resets {reset}")'
  fi
  echo "== agy"
  (cd "$ROOT" && timeout 90 agy -p "/usage" 2>/dev/null | sed 's/^/  /') || echo "  (unavailable)"
}

prompt_for() {
  local task="$1" file
  file=$(ls "$ROOT"/docs/tasks/"$task"-*.md 2>/dev/null | head -1)
  [[ -n "$file" ]] || { echo "no task file for $task in docs/tasks/" >&2; exit 1; }
  cat <<EOF
You are implementing task $task in this repository.
Read AGENTS.md first, then ${file#"$ROOT"/}, and follow both exactly.
Work only in the current directory (a git worktree on branch task/$task).
When finished: make sure the Definition of Done in AGENTS.md holds, commit on branch task/$task,
and print the final report in the format AGENTS.md specifies.
EOF
}

worktree() {
  local task="$1" dir="$WT_BASE/$1"
  if [[ ! -d "$dir" ]]; then
    git -C "$ROOT" worktree add -q -b "task/$task" "$dir" main
  fi
  echo "$dir"
}

case "${1:-}" in
  quota) quota ;;
  codex)
    task="$2"; effort="${3:-medium}"; dir=$(worktree "$task")
    prompt_for "$task" | CODEX_HOME="$HOME/.codex-personal" codex exec \
      -C "$dir" -c model_reasoning_effort="$effort" \
      --output-last-message "$LOGS/$task.report.md" - 2>&1 | tee "$LOGS/$task.log"
    ;;
  agy)
    task="$2"; model="${3:-gemini-4-argon-high}"; dir=$(worktree "$task")
    (cd "$dir" && agy --dangerously-skip-permissions --model "$model" -p "$(prompt_for "$task")") \
      2>&1 | tee "$LOGS/$task.log"
    cp "$LOGS/$task.log" "$LOGS/$task.report.md"
    ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
