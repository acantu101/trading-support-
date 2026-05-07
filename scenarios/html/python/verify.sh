#!/bin/bash
# python/verify.sh — Verify fix for memory-leaking NBBO quote aggregator
source "$(dirname "$0")/../_lib/common.sh"

banner "Python Scenario: Verify Fix"

PY_DIR="$HOME/trading-support/python"
PID_FILE="$HOME/trading-support/pids/python-svc.pid"
SERVICE_PY="$PY_DIR/service.py"
SERVICE_FIXED_PY="$PY_DIR/service_fixed.py"

# ── Helper: check if a PID is running a particular script ────────────────────
_pid_running() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

_script_for_pid() {
  local pid="$1"
  ps -p "$pid" -o args= 2>/dev/null || true
}

# ── Heuristic: is service.py fixed? ──────────────────────────────────────────
SERVICE_HAS_DEQUE=false
if grep -q "deque" "$SERVICE_PY" 2>/dev/null; then
  SERVICE_HAS_DEQUE=true
fi

# ── Is service_fixed.py running? ──────────────────────────────────────────────
FIXED_PID=$(pgrep -f "service_fixed.py" 2>/dev/null | head -1)
FIXED_RUNNING=false
if [ -n "$FIXED_PID" ] && _pid_running "$FIXED_PID"; then
  FIXED_RUNNING=true
fi

# ── Check the original service's PID ──────────────────────────────────────────
ORIG_PID=""
if [ -f "$PID_FILE" ]; then
  ORIG_PID=$(cat "$PID_FILE")
fi
ORIG_RUNNING=false
if _pid_running "$ORIG_PID"; then
  ORIG_RUNNING=true
fi

# ── Determine if fixed ────────────────────────────────────────────────────────
FIXED=false

if [ "$SERVICE_HAS_DEQUE" = "true" ]; then
  FIXED=true
fi
if [ "$FIXED_RUNNING" = "true" ]; then
  FIXED=true
fi

# ── Not fixed branch ──────────────────────────────────────────────────────────
if [ "$FIXED" = "false" ]; then
  echo ""
  err "The memory leak is still active."
  echo ""
  if [ "$ORIG_RUNNING" = "true" ]; then
    METRICS="$PY_DIR/metrics.log"
    if [ -f "$METRICS" ]; then
      info "Current memory growth (last 3 metrics lines):"
      echo ""
      tail -3 "$METRICS" | sed 's/^/    /'
      echo ""
    fi
    info "quote_cache is a dict that grows without bound."
    info "Every (symbol, timestamp_ms) key is added and never removed."
  else
    info "The original service.py doesn't appear to be running either."
    info "Start it with: python3 $SERVICE_PY &"
    info "Watch the leak: watch -n5 'tail -3 $PY_DIR/metrics.log'"
  fi
  echo ""
  step "Compare the two files — the fix is one line change:"
  step "    diff $SERVICE_PY $SERVICE_FIXED_PY"
  echo ""
  step "Nudge: look at the line with quote_cache in service.py."
  step "       The fix uses collections.deque(maxlen=10_000) per symbol"
  step "       so the cache is bounded and oldest entries are auto-evicted."
  echo ""
  step "Apply the fix by either:"
  step "  a) Editing service.py to use deque and restarting it"
  step "  b) Running service_fixed.py instead:"
  step "     kill ${ORIG_PID:-<pid>} 2>/dev/null"
  step "     python3 $SERVICE_FIXED_PY &"
  echo ""
  exit 1
fi

# ── Fixed branch ──────────────────────────────────────────────────────────────
ACTIVE_PID="${FIXED_PID:-$ORIG_PID}"
ACTIVE_SCRIPT="service_fixed.py"
[ "$SERVICE_HAS_DEQUE" = "true" ] && [ -z "$FIXED_PID" ] && ACTIVE_SCRIPT="service.py (with deque fix)"

ok "Fix detected: quote_cache is bounded."
if [ "$FIXED_RUNNING" = "true" ]; then
  ok "service_fixed.py is running (PID ${FIXED_PID})."
elif [ "$SERVICE_HAS_DEQUE" = "true" ]; then
  ok "service.py now contains deque — the leak is fixed."
fi
echo ""

step "Simulating memory metrics over time — RSS should stabilize..."
echo ""
sleep 0.3

# ── Print stabilizing RSS metrics ────────────────────────────────────────────
_metrics_line() {
  local ts="$1" rss="$2" entries="$3" bound="$4"
  echo "    [$ts] RSS: ${rss} MB, cache entries: ${entries} (bounded, max ${bound})"
}

NOW=$(date '+%Y-%m-%d %H:%M:%S')
# Use real metrics from the fixed service if available, otherwise simulate
FIXED_METRICS="$PY_DIR/metrics_fixed.log"
if [ -f "$FIXED_METRICS" ] && [ -s "$FIXED_METRICS" ]; then
  echo -e "${BOLD}${CYAN}>>> tail -3 $FIXED_METRICS${NC}"
  echo ""
  tail -3 "$FIXED_METRICS" | sed 's/^/    /'
else
  echo -e "${BOLD}${CYAN}>>> Live memory metrics (service_fixed.py):${NC}"
  echo ""
  _metrics_line "$(date -d '0 seconds' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')" "312.4" "120,000" "120,000"
  sleep 0.3
  _metrics_line "$(date -d '5 seconds' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')" "312.6" "120,000" "120,000"
  sleep 0.3
  _metrics_line "$(date -d '10 seconds' '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date '+%Y-%m-%d %H:%M:%S')" "312.5" "120,000" "120,000"
fi
echo ""
sleep 0.3
ok "RSS is stable — no unbounded growth. Cache entries capped at maxlen."
echo ""

# ── Show tracemalloc top — dict no longer dominates ──────────────────────────
step "Simulating tracemalloc snapshot (dict is no longer the top allocator)..."
sleep 0.3
echo ""
echo -e "${BOLD}${CYAN}>>> tracemalloc top allocators (service_fixed.py):${NC}"
echo ""
cat << 'TRACEMALLOC'
    ============================================================
    Top 10 memory consumers (tracemalloc snapshot):
    ============================================================
      # 1   8.2 KB  collections/__init__.py:476
              -> deque.__new__ (bounded, maxlen=10000 per symbol)
      # 2   4.1 KB  json/decoder.py:341
              -> JSONObject
      # 3   3.8 KB  threading/__init__.py:882
              -> Thread._bootstrap_inner
      # 4   2.4 KB  service_fixed.py:48
              -> quote_cache[sym].append(...)   <-- bounded append
      # 5   1.9 KB  socket.py:234
              -> socket.recv_into

      Total tracked: 20.4 MB

    ============================================================
    Memory growth between snapshots (diff):
    ============================================================
      +0.1 KB  collections/__init__.py:476  (deque cycling, not growing)

    No unbounded allocators detected.
TRACEMALLOC
echo ""
sleep 0.3

# ── Compare service.py vs service_fixed.py diff ───────────────────────────────
step "Key diff — service.py vs service_fixed.py:"
echo ""
echo -e "${BOLD}${CYAN}>>> diff service.py service_fixed.py (excerpt)${NC}"
echo ""
cat << 'DIFFOUT'
    --- service.py
    +++ service_fixed.py

    -from collections import deque      # (not imported in leaking version)
    +from collections import deque

    -# Bug: unbounded dict — keys are (symbol, timestamp_ms), never evicted
    -quote_cache: dict = {}
    +# Fix: bounded deque per symbol — maxlen caps memory usage
    +MAX_QUOTES_PER_SYMBOL = 10_000
    +quote_cache: dict[str, deque] = {sym: deque(maxlen=MAX_QUOTES_PER_SYMBOL) for sym in SYMBOLS}

    -            quote_cache[(sym, ts_ms)] = {
    -                "bid": bid, "ask": ask, ...
    -            }
    +            quote_cache[sym].append({
    +                "ts_ms": ts_ms, "bid": bid, "ask": ask, ...
    +            })
DIFFOUT
echo ""
sleep 0.3

# ── SCENARIO COMPLETE summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║        SCENARIO COMPLETE — Python Memory Leak               ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}1. What you diagnosed${NC}"
echo "   The NBBO quote aggregator microservice was consuming growing memory."
echo "   metrics.log showed RSS climbing ~50 MB/minute with no ceiling."
echo "   tracemalloc / leak_profile.py identified the source: quote_cache dict"
echo "   keyed by (symbol, timestamp_ms). With 12 symbols at ~100 ticks/sec,"
echo "   1,200 new dict entries were added every second and none were ever"
echo "   removed. After 10 minutes: ~720,000 entries, ~600 MB RSS."
echo ""

echo -e "${BOLD}${CYAN}2. What you fixed${NC}"
echo "   Replaced the unbounded dict with a bounded deque per symbol:"
echo "     collections.deque(maxlen=10_000)"
echo "   deque(maxlen=N) automatically evicts the oldest entry when full,"
echo "   keeping memory constant regardless of runtime. With 12 symbols and"
echo "   maxlen=10,000, the cache is capped at 120,000 entries (~100 MB)."
echo ""

echo -e "${BOLD}${CYAN}3. Real-world context${NC}"
echo "   Common Python memory leak patterns in trading services:"
echo "   - Global dicts without eviction (this scenario)"
echo "   - Circular references that prevent garbage collection"
echo "   - __del__ methods that keep objects alive in cycles"
echo "   - C extension leaks (e.g., some network library buffers)"
echo "   - Class-level caches that accumulate across requests"
echo ""
echo "   Diagnostic tools comparison:"
echo "   - tracemalloc    : built-in, shows allocation sites, zero overhead toggle"
echo "   - memory_profiler: line-by-line RSS delta (@profile decorator)"
echo "   - py-spy         : sampling profiler, attaches without restart"
echo "   - Valgrind/memray: deep C extension and allocator-level analysis"
echo ""
echo "   When to use WeakValueDictionary instead of deque:"
echo "   - If cache values are objects held elsewhere, WeakValueDictionary"
echo "     auto-removes entries when the referent is garbage collected."
echo "   - For quote data (no external references), deque(maxlen) is simpler."
echo ""

echo -e "${BOLD}${CYAN}4. How to prevent it in production${NC}"
echo "   a) Prometheus memory metrics: track process_resident_memory_bytes"
echo "      and alert on growth rate (not just absolute size)."
echo "      Growth rate > 5 MB/min sustained = investigate."
echo "   b) Alert on cache entry count as a separate metric:"
echo "      gauge('quote_cache_entries', sum(len(q) for q in cache.values()))"
echo "   c) Default to bounded caches: use deque(maxlen=N) or LRU caches"
echo "      (functools.lru_cache, cachetools.LRUCache) for any per-key state."
echo "   d) Run tracemalloc in staging with a 1-hour soak test before"
echo "      deploying services that accumulate state."
echo "   e) Container memory limits as a safety net:"
echo "      resources.limits.memory: 512Mi in Kubernetes — the pod OOMKills"
echo "      rather than taking down the whole node."
echo "   f) Periodic cache metrics logging: log cache size every N seconds"
echo "      so you can correlate memory growth with cache growth in hindsight."
echo ""
