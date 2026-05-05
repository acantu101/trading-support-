#!/usr/bin/env bash
# Triage script for trading-support issues.
# Usage:
#   ./scripts/triage.sh          — list open issues sorted by priority
#   ./scripts/triage.sh close 3  — close issue #3 with an optional commit ref

set -euo pipefail

GH="gh"
REPO="acantu101/trading-support"

list_issues() {
  echo ""
  echo "=== Open Issues (P1 first) ==="
  echo ""

  p1=$("$GH" issue list --repo "$REPO" --label "P1" --state open --json number,title,createdAt \
    --template '{{range .}}  [P1] #{{.number}} {{.title}}  (opened {{timeago .createdAt}}){{"\n"}}{{end}}' 2>/dev/null || echo "")

  p2=$("$GH" issue list --repo "$REPO" --label "P2" --state open --json number,title,createdAt \
    --template '{{range .}}  [P2] #{{.number}} {{.title}}  (opened {{timeago .createdAt}}){{"\n"}}{{end}}' 2>/dev/null || echo "")

  unlabeled=$("$GH" issue list --repo "$REPO" --state open --json number,title,labels,createdAt \
    --jq '.[] | select(.labels | length == 0) | "  [--] #\(.number) \(.title)"' 2>/dev/null || echo "")

  [[ -n "$p1" ]] && echo "$p1" || true
  [[ -n "$p2" ]] && echo "$p2" || true
  [[ -n "$unlabeled" ]] && echo "$unlabeled" || true

  echo ""
  echo "Run:  gh issue view <number>          — read full issue"
  echo "      gh issue comment <number> -b '' — add a note"
  echo "      ./scripts/triage.sh close <number> [commit-sha]"
  echo ""
}

close_issue() {
  local number="$1"
  local commit="${2:-}"

  body="Closing via triage script."
  [[ -n "$commit" ]] && body="Resolved in commit $commit."

  "$GH" issue comment "$number" --repo "$REPO" --body "$body"
  "$GH" issue close "$number" --repo "$REPO"
  echo "Issue #$number closed."
}

case "${1:-list}" in
  list)   list_issues ;;
  close)  [[ -z "${2:-}" ]] && { echo "Usage: triage.sh close <issue-number> [commit-sha]"; exit 1; }
          close_issue "$2" "${3:-}" ;;
  *)      echo "Unknown command: $1"; echo "Usage: triage.sh [list|close <number> [commit-sha]]"; exit 1 ;;
esac
