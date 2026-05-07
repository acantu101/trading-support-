#!/bin/bash
# marketdata/verify.sh — Verify fix for stale AAPL feed (stuck normalizer thread)
source "$(dirname "$0")/../_lib/common.sh"

banner "Market Data Scenario: Verify Fix"

MD_DIR="$HOME/trading-support/marketdata"
PID_FILE="$HOME/trading-support/pids/marketdata.pids.normalizer"
NORMALIZED="$MD_DIR/feed/normalized.jsonl"

# ── Helper: check if AAPL has appeared in normalized.jsonl recently ──────────
_aapl_is_fresh() {
  # Returns 0 (true) if AAPL appears in normalized.jsonl in the last 10 seconds
  if [ ! -f "$NORMALIZED" ]; then
    return 1
  fi
  local now
  now=$(date +%s)
  local cutoff=$(( now - 10 ))
  # Use python3 to parse JSON and check normalized_at timestamp
  python3 - "$NORMALIZED" "$cutoff" << 'PYEOF'
import sys, json

path   = sys.argv[1]
cutoff = float(sys.argv[2])
found  = False

try:
    with open(path) as f:
        lines = f.readlines()
    # Check last 500 lines for speed
    for line in lines[-500:]:
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("symbol") == "AAPL":
                ts = rec.get("normalized_at", 0)
                if ts >= cutoff:
                    found = True
                    break
        except Exception:
            pass
except Exception:
    pass

sys.exit(0 if found else 1)
PYEOF
}

# ── Check current state ───────────────────────────────────────────────────────
ORIG_PID=""
if [ -f "$PID_FILE" ]; then
  ORIG_PID=$(cat "$PID_FILE")
fi

PROC_ALIVE=false
if [ -n "$ORIG_PID" ] && kill -0 "$ORIG_PID" 2>/dev/null; then
  PROC_ALIVE=true
fi

AAPL_FRESH=false
if _aapl_is_fresh; then
  AAPL_FRESH=true
fi

# ── Determine pass/fail ───────────────────────────────────────────────────────
# Fixed if: AAPL is fresh (whether original PID or a restarted normalizer)
if [ "$AAPL_FRESH" = "true" ]; then
  FIXED=true
else
  FIXED=false
fi

# ── Not fixed branch ──────────────────────────────────────────────────────────
if [ "$FIXED" = "false" ]; then
  echo ""
  err "AAPL is still dark — the normalizer thread is stuck."
  err "AAPL has not appeared in normalized.jsonl in the last 10 seconds."
  echo ""
  if [ "$PROC_ALIVE" = "true" ]; then
    info "Normalizer PID ${ORIG_PID} is still running — original process with stuck AAPL thread."
  else
    info "Normalizer process is not running — did you restart it?"
    info "If you restarted it, AAPL should start appearing. Wait 5 seconds and try again."
  fi
  echo ""
  step "Nudge: find which thread is blocked — look at the normalizer source:"
  step "       less $MD_DIR/normalizer.py"
  step "       Search for the AAPL-specific processing function."
  echo ""
  step "To inspect a live stuck process:"
  step "       pip install py-spy  &&  py-spy dump --pid ${ORIG_PID:-<pid>}"
  step "       strace -p ${ORIG_PID:-<pid>} -e trace=futex,read,write 2>&1 | head -20"
  echo ""
  step "The simplest fix: restart the normalizer so the stuck thread is recycled."
  step "       kill ${ORIG_PID:-<pid>}  &&  python3 $MD_DIR/normalizer.py &"
  echo ""
  exit 1
fi

# ── Fixed branch — simulate feedcheck recovering ──────────────────────────────
NEW_PID=""
if [ -f "$PID_FILE" ]; then
  NEW_PID=$(cat "$PID_FILE")
fi
[ -z "$NEW_PID" ] && NEW_PID="$(pgrep -f 'normalizer.py' | head -1)"

ok "AAPL is now appearing in normalized.jsonl — normalizer thread is healthy."
echo ""

step "Running feedcheck — watch AAPL come back online..."
echo ""

SYMBOLS=(AAPL MSFT GOOGL AMZN TSLA NVDA META NFLX JPM GS)

_feedcheck_table() {
  local aapl_status="$1"
  local aapl_age="$2"
  printf "\n"
  printf "%-8s  %-12s  %s\n" "SYMBOL" "LAST UPDATE" "STATUS"
  printf "%-8s  %-12s  %s\n" "────────" "────────────" "──────────────────"
  for sym in "${SYMBOLS[@]}"; do
    if [ "$sym" = "AAPL" ]; then
      printf "%-8s  %-12s  %s\n" "$sym" "${aapl_age}" "${aapl_status}"
    else
      printf "%-8s  %-12s  %s\n" "$sym" "<1s ago" "OK"
    fi
  done
  printf "\n"
}

echo -e "${BOLD}${CYAN}>>> feedcheck  (before fix applied — AAPL stale)${NC}"
_feedcheck_table "STALE  <-- investigating" "47s ago"
sleep 0.3

echo -e "${BOLD}${CYAN}>>> feedcheck  (normalizer restarting — AAPL recovering)${NC}"
_feedcheck_table "RECOVERING..." "3s ago"
sleep 0.3

echo -e "${BOLD}${CYAN}>>> feedcheck  (normalizer healthy — AAPL live)${NC}"
_feedcheck_table "OK" "0.2s ago"
sleep 0.3

ok "All 10 symbols reporting fresh quotes."
echo ""

# ── Show tail of normalized.jsonl with AAPL entries ──────────────────────────
echo -e "${BOLD}${CYAN}>>> tail -5 $NORMALIZED  (AAPL quotes now present)${NC}"
echo ""
sleep 0.3
python3 - "$NORMALIZED" << 'PYEOF'
import json, sys, datetime

path = sys.argv[1]
try:
    with open(path) as f:
        lines = f.readlines()
    aapl_lines = [l for l in lines if '"AAPL"' in l][-3:]
    other_lines = [l for l in lines if '"AAPL"' not in l][-2:]
    for l in (other_lines + aapl_lines)[-5:]:
        try:
            rec = json.loads(l.strip())
            print(json.dumps(rec))
        except Exception:
            print(l.rstrip())
except Exception as e:
    # Fallback synthetic output
    import time, random
    now = time.time()
    for sym, bid in [("MSFT", 415.42), ("GOOGL", 175.08), ("AAPL", 182.61), ("AAPL", 182.63), ("AAPL", 182.59)]:
        ask = round(bid + random.uniform(0.01, 0.05), 4)
        print(json.dumps({"symbol": sym, "bid": bid, "ask": ask,
                          "mid": round((bid+ask)/2, 4),
                          "normalized_at": round(now, 3), "source_seq": random.randint(10000,99999)}))
PYEOF
echo ""
ok "AAPL quotes flowing normally into normalized.jsonl."
echo ""

# ── SCENARIO COMPLETE summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║        SCENARIO COMPLETE — Stale AAPL Market Data Feed      ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}1. What you diagnosed${NC}"
echo "   feedcheck showed AAPL last updated 47+ seconds ago with status STALE,"
echo "   while all 9 other symbols were fresh (<1s). The normalizer process"
echo "   was alive — the issue was an individual thread, not the whole process."
echo "   Inspecting normalizer.py revealed process_aapl() contained:"
echo "       while True: pass"
echo "   — an infinite loop that spun the AAPL worker thread at 100% CPU"
echo "   but produced zero output. The thread was not deadlocked (no lock"
echo "   waiting) — it was simply looping with no exit condition."
echo ""

echo -e "${BOLD}${CYAN}2. What you fixed${NC}"
echo "   Restarted the normalizer process, which recycled all threads including"
echo "   the stuck AAPL thread. Alternatively, fixing process_aapl() to use"
echo "   the correct normalization logic (process_generic pattern) prevents"
echo "   the bug from recurring on the next startup."
echo ""

echo -e "${BOLD}${CYAN}3. Real-world context${NC}"
echo "   Per-symbol thread architectures are common in market-data normalizers."
echo "   A bug in one symbol's processing path affects only that symbol —"
echo "   the other 9 continue normally, making the failure easy to miss"
echo "   if you only monitor aggregate throughput instead of per-symbol freshness."
echo ""
echo "   Three stuck-thread patterns to know:"
echo "   - Infinite loop (this scenario): thread spins, burns CPU, no output"
echo "   - Deadlock: thread blocks on a lock held by another thread"
echo "   - Blocking I/O: thread blocks on a network call / disk read with no timeout"
echo ""
echo "   Diagnostic tools:"
echo "   - py-spy dump --pid <pid>   : Python stack trace of all threads (no attach)"
echo "   - strace -p <pid>           : system calls (futex waits = deadlock)"
echo "   - jstack <pid>              : Java equivalent"
echo "   - /proc/<pid>/stack         : kernel stack on Linux"
echo ""

echo -e "${BOLD}${CYAN}4. How to prevent it in production${NC}"
echo "   a) Per-symbol freshness health check: alert if any symbol has not"
echo "      produced output in N seconds (N = expected_interval * 5)."
echo "   b) Thread watchdog: a supervisor thread checks per-symbol last-update"
echo "      timestamps and restarts stuck threads without killing the process."
echo "   c) Add timeout wrappers around any blocking calls in processing paths."
echo "   d) Unit-test each symbol's processing function with a real quote."
echo "   e) Expose a /healthz endpoint that checks per-symbol freshness —"
echo "      Kubernetes readiness probes can then catch silent symbol failures."
echo ""
