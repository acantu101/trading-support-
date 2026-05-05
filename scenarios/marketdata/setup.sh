#!/bin/bash
# marketdata/setup.sh — AAPL quote feed stale (stuck normalizer thread) scenario
source "$(dirname "$0")/../_lib/common.sh"

banner "Market Data Scenario: Stale AAPL Feed"
ensure_dirs

MD_DIR="$HOME/trading-support/marketdata"
PIDS_BASE="$HOME/trading-support/pids/marketdata.pids"

# ── Directories ──────────────────────────────────────────────────────────────
step "Creating market data scenario directories..."
mkdir -p "$MD_DIR/feed" "$MD_DIR/logs" "$MD_DIR/bin"
ok "Directories ready: $MD_DIR"

# ── publisher.py ─────────────────────────────────────────────────────────────
step "Writing publisher.py (all 10 symbols, 50ms interval)..."
cat > "$MD_DIR/publisher.py" << 'PYEOF'
#!/usr/bin/env python3
"""
publisher.py — Market data publisher.
Writes bid/ask quotes for 10 symbols to feed/quotes.jsonl every 50ms.
All symbols update continuously.
"""
import json
import time
import random
import os
import signal

QUOTES_FILE = os.path.expanduser("~/trading-support/marketdata/feed/quotes.jsonl")
LOG_FILE    = os.path.expanduser("~/trading-support/marketdata/logs/publisher.log")

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX", "JPM", "GS"]
BASE_PRICES = {
    "AAPL": 182.50, "MSFT": 415.75, "GOOGL": 175.20, "AMZN": 185.90,
    "TSLA": 248.10, "NVDA": 875.30, "META": 510.60, "NFLX": 625.80,
    "JPM": 198.40, "GS": 412.25
}

running = True
def _stop(sig, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

os.makedirs(os.path.dirname(QUOTES_FILE), exist_ok=True)

seq = 0
with open(QUOTES_FILE, "a") as qf, open(LOG_FILE, "w") as lf:
    lf.write(f"publisher started pid={os.getpid()}\n")
    lf.flush()
    while running:
        for sym in SYMBOLS:
            base = BASE_PRICES[sym]
            bid = round(base + random.uniform(-1.00, 1.00), 2)
            ask = round(bid + random.uniform(0.01, 0.08), 2)
            msg = {
                "symbol": sym,
                "bid": bid,
                "ask": ask,
                "bid_size": random.randint(100, 50000),
                "ask_size": random.randint(100, 50000),
                "exchange": random.choice(["NASDAQ", "NYSE", "ARCA"]),
                "timestamp": time.time(),
                "seq": seq
            }
            qf.write(json.dumps(msg) + "\n")
            seq += 1
        qf.flush()
        time.sleep(0.05)  # 50ms → ~200 quotes/sec across all symbols

lf.write(f"publisher stopped. seq={seq}\n")
PYEOF
ok "publisher.py written"

# ── normalizer.py ────────────────────────────────────────────────────────────
step "Writing normalizer.py (AAPL thread stuck in while True: pass)..."
cat > "$MD_DIR/normalizer.py" << 'PYEOF'
#!/usr/bin/env python3
"""
normalizer.py — Market data normalizer.
Reads quotes.jsonl and normalizes each symbol in a dedicated thread.
BUG: AAPL processing function contains an infinite loop — that thread
     spins forever, so AAPL never appears in normalized.jsonl.
All other symbol threads operate normally.
"""
import json
import time
import os
import signal
import threading
import random

QUOTES_FILE     = os.path.expanduser("~/trading-support/marketdata/feed/quotes.jsonl")
NORMALIZED_FILE = os.path.expanduser("~/trading-support/marketdata/feed/normalized.jsonl")
LOG_FILE        = os.path.expanduser("~/trading-support/marketdata/logs/normalizer.log")

# Per-symbol last-update timestamp (written to a state file for feedcheck)
STATE_DIR = os.path.expanduser("~/trading-support/marketdata/feed/state")
os.makedirs(STATE_DIR, exist_ok=True)

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX", "JPM", "GS"]

running = True
norm_lock = threading.Lock()
log_lock  = threading.Lock()

def _stop(sig, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

def log(msg):
    with log_lock:
        with open(LOG_FILE, "a") as lf:
            lf.write(f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}\n")
            lf.flush()

def write_normalized(record):
    with norm_lock:
        with open(NORMALIZED_FILE, "a") as nf:
            nf.write(json.dumps(record) + "\n")

def update_state(symbol):
    with open(os.path.join(STATE_DIR, symbol + ".ts"), "w") as sf:
        sf.write(str(time.time()))

# ── Per-symbol processing functions ──────────────────────────────────────────

def process_aapl(quote):
    # BUG: infinite loop — this thread will spin here forever
    # Simulates a deadlock / infinite loop in AAPL processing logic
    while True:
        pass  # noqa: intentional bug for lab scenario

def process_generic(quote):
    """Standard normalization: add mid price, round, tag source."""
    normalized = {
        "symbol":    quote["symbol"],
        "bid":       quote["bid"],
        "ask":       quote["ask"],
        "mid":       round((quote["bid"] + quote["ask"]) / 2, 4),
        "bid_size":  quote["bid_size"],
        "ask_size":  quote["ask_size"],
        "exchange":  quote.get("exchange", "UNKNOWN"),
        "normalized_at": time.time(),
        "source_seq":    quote.get("seq", -1)
    }
    write_normalized(normalized)
    update_state(quote["symbol"])

PROCESSORS = {sym: process_generic for sym in SYMBOLS}
PROCESSORS["AAPL"] = process_aapl   # override with buggy version

# ── Per-symbol worker threads ─────────────────────────────────────────────────
queues = {sym: [] for sym in SYMBOLS}
queue_locks = {sym: threading.Lock() for sym in SYMBOLS}

def symbol_worker(sym):
    log(f"thread started for symbol={sym}")
    while running or queues[sym]:
        with queue_locks[sym]:
            if queues[sym]:
                quote = queues[sym].pop(0)
            else:
                quote = None
        if quote:
            PROCESSORS[sym](quote)  # AAPL will block here indefinitely
        else:
            time.sleep(0.01)
    log(f"thread stopped for symbol={sym}")

threads = {}
for sym in SYMBOLS:
    t = threading.Thread(target=symbol_worker, args=(sym,), daemon=True, name=f"norm-{sym}")
    t.start()
    threads[sym] = t

# ── Reader loop: dispatch quotes to per-symbol queues ────────────────────────
log(f"normalizer started pid={os.getpid()}")
read_pos = 0

while running:
    if not os.path.exists(QUOTES_FILE):
        time.sleep(0.1)
        continue

    with open(QUOTES_FILE) as qf:
        lines = qf.readlines()

    new_lines = lines[read_pos:]
    for line in new_lines:
        line = line.strip()
        if not line:
            continue
        try:
            quote = json.loads(line)
            sym = quote.get("symbol")
            if sym in queues:
                with queue_locks[sym]:
                    queues[sym].append(quote)
        except json.JSONDecodeError:
            pass
        read_pos += 1

    time.sleep(0.05)

log("normalizer reader loop stopped")
PYEOF
ok "normalizer.py written (AAPL thread has intentional while True: pass bug)"

# ── feedcheck script ─────────────────────────────────────────────────────────
step "Writing bin/feedcheck..."
cat > "$MD_DIR/bin/feedcheck" << 'BEOF'
#!/bin/bash
# feedcheck — Show per-symbol quote freshness
# AAPL will show as stale; all others show fresh.

STATE_DIR="$HOME/trading-support/marketdata/feed/state"
SYMBOLS=(AAPL MSFT GOOGL AMZN TSLA NVDA META NFLX JPM GS)
NOW=$(date +%s)

printf "\n"
printf "%-8s  %-12s  %s\n" "SYMBOL" "LAST UPDATE" "STATUS"
printf "%-8s  %-12s  %s\n" "────────" "────────────" "──────────────────"

for sym in "${SYMBOLS[@]}"; do
    TS_FILE="$STATE_DIR/${sym}.ts"
    if [ -f "$TS_FILE" ]; then
        LAST_TS=$(python3 -c "import math; print(int(math.floor(float(open('$TS_FILE').read().strip()))))" 2>/dev/null)
        AGE=$(( NOW - LAST_TS ))
        if [ "$sym" = "AAPL" ]; then
            # AAPL thread is stuck — override age for realism
            printf "%-8s  %-12s  %s\n" "$sym" "${AGE}s ago" "STALE  <-- investigate"
        elif [ "$AGE" -gt 5 ]; then
            printf "%-8s  %-12s  %s\n" "$sym" "${AGE}s ago" "WARN"
        else
            printf "%-8s  %-12s  %s\n" "$sym" "<1s ago" "OK"
        fi
    else
        if [ "$sym" = "AAPL" ]; then
            printf "%-8s  %-12s  %s\n" "$sym" "47s ago" "STALE  <-- investigate"
        else
            printf "%-8s  %-12s  %s\n" "$sym" "<1s ago" "OK"
        fi
    fi
done
printf "\n"
printf "Hint: a STALE symbol means its normalizer thread has not produced output recently.\n"
printf "      Check: ~/trading-support/marketdata/logs/normalizer.log\n"
printf "             ~/trading-support/marketdata/normalizer.py\n"
printf "\n"
BEOF
chmod +x "$MD_DIR/bin/feedcheck"
ok "bin/feedcheck written and marked executable"

# ── Normalizer log seed ───────────────────────────────────────────────────────
step "Writing initial normalizer.log (showing AAPL thread started but silent)..."
cat > "$MD_DIR/logs/normalizer.log" << 'EOF'
2026-05-04T07:59:58Z normalizer started pid=PENDING
2026-05-04T07:59:58Z thread started for symbol=AAPL
2026-05-04T07:59:58Z thread started for symbol=MSFT
2026-05-04T07:59:58Z thread started for symbol=GOOGL
2026-05-04T07:59:58Z thread started for symbol=AMZN
2026-05-04T07:59:58Z thread started for symbol=TSLA
2026-05-04T07:59:58Z thread started for symbol=NVDA
2026-05-04T07:59:58Z thread started for symbol=META
2026-05-04T07:59:58Z thread started for symbol=NFLX
2026-05-04T07:59:58Z thread started for symbol=JPM
2026-05-04T07:59:58Z thread started for symbol=GS
EOF
# (Note: after real start the log file will be overwritten with the actual PID)
ok "normalizer.log seeded"

# ── Start processes ───────────────────────────────────────────────────────────
step "Starting publisher.py in background..."
python3 "$MD_DIR/publisher.py" &
PUB_PID=$!
ok "publisher.py started (PID $PUB_PID)"

step "Starting normalizer.py in background..."
python3 "$MD_DIR/normalizer.py" &
NORM_PID=$!
ok "normalizer.py started (PID $NORM_PID)"

mkdir -p "$HOME/trading-support/pids"
echo "$PUB_PID"  > "${PIDS_BASE}.publisher"
echo "$NORM_PID" > "${PIDS_BASE}.normalizer"
ok "PIDs saved to ${PIDS_BASE}.{publisher,normalizer}"

# Brief pause so logs populate before printing hints
sleep 1

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  SCENARIO READY — Stale AAPL Feed${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
info "Add feedcheck to your PATH:"
echo -e "    ${BOLD}export PATH=\"$MD_DIR/bin:\$PATH\"${NC}"
echo ""
info "Then check symbol freshness:"
echo -e "    ${BOLD}feedcheck${NC}"
echo ""
info "Investigate the normalizer:"
echo -e "    cat $MD_DIR/logs/normalizer.log"
echo -e "    less $MD_DIR/normalizer.py"
echo ""
warn "AAPL quotes are stale. Use feedcheck to see per-symbol latency. Investigate normalizer.py"
echo ""
