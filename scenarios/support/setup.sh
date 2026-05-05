#!/bin/bash
# Scenario: NVDA prices go stale — silent exception in normalizer swallows the error
source "$(dirname "$0")/../_lib/common.sh"

LAB_DIR=~/trading-support/support
PID_DIR=~/trading-support/pids

echo "=== Support Scenario: Stale NVDA Quotes ==="
echo ""

mkdir -p "$LAB_DIR"/{feed,logs,bin}
mkdir -p "$PID_DIR"

# Step 2: Write publisher.py
cat > "$LAB_DIR/publisher.py" << 'PUBEOF'
#!/usr/bin/env python3
"""
Market data publisher — emits bid/ask for 6 symbols every 200ms.
Writes JSON lines to ~/trading-support/support/feed/raw.jsonl
"""
import json
import time
import random
import os
import signal
import sys

FEED_FILE = os.path.expanduser("~/trading-support/support/feed/raw.jsonl")
SYMBOLS = {
    "AAPL":  {"mid": 189.42, "spread": 0.02},
    "MSFT":  {"mid": 415.87, "spread": 0.03},
    "GOOGL": {"mid": 175.31, "spread": 0.04},
    "NVDA":  {"mid": 875.50, "spread": 0.10},
    "TSLA":  {"mid": 172.18, "spread": 0.05},
    "JPM":   {"mid": 201.33, "spread": 0.02},
}

def handle_signal(sig, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

os.makedirs(os.path.dirname(FEED_FILE), exist_ok=True)

with open(FEED_FILE, "a", buffering=1) as f:
    while True:
        ts = time.time()
        for sym, info in SYMBOLS.items():
            mid = info["mid"] + random.uniform(-0.5, 0.5)
            half = info["spread"] / 2
            record = {
                "ts": ts,
                "symbol": sym,
                "bid": round(mid - half, 4),
                "ask": round(mid + half, 4),
                "sequence": int(ts * 1000),
            }
            f.write(json.dumps(record) + "\n")
        time.sleep(0.2)
PUBEOF

# Step 3: Write normalizer.py
cat > "$LAB_DIR/normalizer.py" << 'NORMEOF'
#!/usr/bin/env python3
"""
Market data normalizer — reads raw.jsonl, normalizes each tick.
BUG: For NVDA, after 60 seconds, int("bad_tick") throws ValueError
     which is silently caught — NVDA disappears from output with no log entry.
"""
import json
import time
import os
import signal
import sys

RAW_FILE   = os.path.expanduser("~/trading-support/support/feed/raw.jsonl")
NORM_FILE  = os.path.expanduser("~/trading-support/support/feed/normalized.jsonl")
LOG_FILE   = os.path.expanduser("~/trading-support/support/logs/normalizer.log")

start_time = time.time()
nvda_broken = False

def handle_signal(sig, frame):
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

os.makedirs(os.path.dirname(NORM_FILE), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

def normalize(record):
    """Normalize a raw tick. Raises for NVDA after 60s."""
    global nvda_broken
    sym = record["symbol"]

    # BUG: after 60 seconds, inject a bad conversion for NVDA
    if sym == "NVDA" and (time.time() - start_time) > 60:
        nvda_broken = True
        # This silently kills NVDA processing — no log, no alert
        multiplier = int("bad_tick")   # <-- ValueError swallowed below

    return {
        "ts":     record["ts"],
        "symbol": sym,
        "bid":    record["bid"],
        "ask":    record["ask"],
        "mid":    round((record["bid"] + record["ask"]) / 2, 4),
        "spread": round(record["ask"] - record["bid"], 4),
        "norm_ts": time.time(),
    }

with open(LOG_FILE, "a", buffering=1) as logf:
    logf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [NORM] Normalizer started\n")
    logf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [NORM] Watching: {RAW_FILE}\n")
    logf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [NORM] Output:   {NORM_FILE}\n")
    logf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [NORM] Symbols: AAPL MSFT GOOGL NVDA TSLA JPM\n")

    raw_pos = 0
    with open(NORM_FILE, "a", buffering=1) as outf:
        while True:
            try:
                with open(RAW_FILE, "r") as rf:
                    rf.seek(raw_pos)
                    for line in rf:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            try:
                                normalized = normalize(record)
                                outf.write(json.dumps(normalized) + "\n")
                                logf.write(
                                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} [NORM] OK {record['symbol']} "
                                    f"bid={record['bid']} ask={record['ask']}\n"
                                )
                            except:
                                pass  # BUG: silently swallow ALL exceptions including NVDA ValueError
                        except json.JSONDecodeError:
                            pass
                    raw_pos = rf.tell()
            except FileNotFoundError:
                pass
            time.sleep(0.1)
NORMEOF

# Step 4: Write quotemon
cat > "$LAB_DIR/bin/quotemon" << 'QMEOF'
#!/bin/bash
# Shows last-update timestamp per symbol from normalized.jsonl
# NVDA will show a stale timestamp after ~60 seconds

NORM_FILE=~/trading-support/support/feed/normalized.jsonl

clear_screen() { printf '\033[2J\033[H'; }

while true; do
    clear_screen
    echo "=== Quote Monitor === $(date '+%H:%M:%S') ==="
    echo ""
    printf "%-8s %-10s %-10s %-10s %-20s %-8s\n" "SYMBOL" "BID" "ASK" "MID" "LAST UPDATE" "AGE(s)"
    echo "------------------------------------------------------------------------"

    if [ ! -f "$NORM_FILE" ]; then
        echo "Waiting for feed..."
        sleep 1
        continue
    fi

    NOW=$(date +%s%N | cut -c1-10)  # unix seconds

    for SYM in AAPL MSFT GOOGL NVDA TSLA JPM; do
        LINE=$(grep "\"symbol\": *\"$SYM\"" "$NORM_FILE" 2>/dev/null | tail -1)
        if [ -z "$LINE" ]; then
            printf "%-8s %-10s %-10s %-10s %-20s %-8s\n" "$SYM" "---" "---" "---" "no data" "???"
            continue
        fi
        BID=$(echo "$LINE"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['bid'])" 2>/dev/null <<< "$LINE")
        ASK=$(echo "$LINE"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['ask'])" 2>/dev/null <<< "$LINE")
        MID=$(echo "$LINE"  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['mid'])" 2>/dev/null <<< "$LINE")
        TS=$(echo "$LINE"   | python3 -c "import sys,json; d=json.load(sys.stdin); print(int(d['norm_ts']))" 2>/dev/null <<< "$LINE")
        AGE=$(( NOW - TS ))
        LAST=$(date -d "@$TS" '+%H:%M:%S' 2>/dev/null || date -r "$TS" '+%H:%M:%S' 2>/dev/null || echo "??:??:??")

        if [ "$AGE" -gt 30 ] 2>/dev/null; then
            printf "\033[31m%-8s %-10s %-10s %-10s %-20s %-8s STALE!\033[0m\n" "$SYM" "$BID" "$ASK" "$MID" "$LAST" "${AGE}s"
        else
            printf "\033[32m%-8s %-10s %-10s %-10s %-20s %-8s\033[0m\n" "$SYM" "$BID" "$ASK" "$MID" "$LAST" "${AGE}s"
        fi
    done

    echo ""
    echo "Press Ctrl+C to exit"
    sleep 2
done
QMEOF
chmod +x "$LAB_DIR/bin/quotemon"

# Step 5: Write normalizer.log (pre-populated clean log — no errors visible)
cat > "$LAB_DIR/logs/normalizer.log" << 'LOGEOF'
2026-05-04 10:14:00 [NORM] Normalizer started
2026-05-04 10:14:00 [NORM] Watching: ~/trading-support/support/feed/raw.jsonl
2026-05-04 10:14:00 [NORM] Output:   ~/trading-support/support/feed/normalized.jsonl
2026-05-04 10:14:00 [NORM] Symbols: AAPL MSFT GOOGL NVDA TSLA JPM
2026-05-04 10:14:00 [NORM] OK AAPL bid=189.41 ask=189.43
2026-05-04 10:14:00 [NORM] OK MSFT bid=415.85 ask=415.88
2026-05-04 10:14:00 [NORM] OK GOOGL bid=175.29 ask=175.33
2026-05-04 10:14:00 [NORM] OK NVDA bid=875.45 ask=875.55
2026-05-04 10:14:00 [NORM] OK TSLA bid=172.15 ask=172.20
2026-05-04 10:14:00 [NORM] OK JPM bid=201.31 ask=201.34
2026-05-04 10:14:00 [NORM] OK AAPL bid=189.43 ask=189.45
2026-05-04 10:14:00 [NORM] OK MSFT bid=415.87 ask=415.90
2026-05-04 10:14:00 [NORM] OK GOOGL bid=175.30 ask=175.34
2026-05-04 10:14:00 [NORM] OK NVDA bid=875.50 ask=875.60
2026-05-04 10:14:00 [NORM] OK TSLA bid=172.16 ask=172.21
2026-05-04 10:14:00 [NORM] OK JPM bid=201.32 ask=201.35
2026-05-04 10:14:02 [NORM] OK AAPL bid=189.40 ask=189.42
2026-05-04 10:14:02 [NORM] OK MSFT bid=415.86 ask=415.89
2026-05-04 10:14:02 [NORM] OK GOOGL bid=175.28 ask=175.32
2026-05-04 10:14:02 [NORM] OK NVDA bid=875.48 ask=875.58
2026-05-04 10:14:02 [NORM] OK TSLA bid=172.14 ask=172.19
2026-05-04 10:14:02 [NORM] OK JPM bid=201.30 ask=201.33
[... entries continue normally ...]
2026-05-04 10:15:00 [NORM] OK AAPL bid=189.44 ask=189.46
2026-05-04 10:15:00 [NORM] OK MSFT bid=415.89 ask=415.92
2026-05-04 10:15:00 [NORM] OK GOOGL bid=175.33 ask=175.37
2026-05-04 10:15:00 [NORM] OK TSLA bid=172.18 ask=172.23
2026-05-04 10:15:00 [NORM] OK JPM bid=201.33 ask=201.36
[NOTE: No NVDA entries after 10:14:00 — but no error logged either]
LOGEOF

# Step 6: Write client ticket
cat > "$LAB_DIR/logs/client-ticket.txt" << 'TICKETEOF'
============================================================
SUPPORT TICKET — PRIORITY P1
============================================================
Ticket ID  : SUP-20260504-00847
Priority   : P1
Client     : Meridian Capital Management
Contact    : James Whitfield <j.whitfield@meridiancap.com>
Time Filed : 10:31 AM EST
Assigned To: Trading Infrastructure Support

------------------------------------------------------------
ISSUE DESCRIPTION
------------------------------------------------------------
NVDA bid/ask quotes have not been updating since approximately
10:14 AM EST. All other symbols (AAPL, MSFT, GOOGL, TSLA, JPM)
appear to be updating normally.

We are attempting to execute a 500,000 share block in NVDA and
cannot do so without a current market price. This is a
time-sensitive execution — NVDA is trading actively.

Last seen quote:
  NVDA bid: 875.48 / ask: 875.58 @ 10:14:00 AM

Current time: 10:31 AM — quote is 17 minutes stale.

We have already:
  - Restarted our internal feed consumer (no change)
  - Verified AAPL/MSFT are updating fine on the same feed
  - Confirmed NVDA is actively trading on exchange (per Bloomberg)

------------------------------------------------------------
BUSINESS IMPACT
------------------------------------------------------------
- 500K share execution blocked
- Estimated market exposure: ~$437M notional
- Portfolio manager escalating to CIO in 10 minutes if unresolved

------------------------------------------------------------
REQUESTED ACTION
------------------------------------------------------------
Immediate investigation and resolution. Please confirm receipt
and provide ETA for fix.

============================================================
TICKETEOF

# Step 7: Start publisher and normalizer in background
echo "Starting publisher.py..."
python3 "$LAB_DIR/publisher.py" &
PUB_PID=$!
echo "$PUB_PID" > "$PID_DIR/support-publisher.pid"
echo "[OK] publisher.py started (PID $PUB_PID)"

echo "Starting normalizer.py..."
python3 "$LAB_DIR/normalizer.py" &
NORM_PID=$!
echo "$NORM_PID" > "$PID_DIR/support-normalizer.pid"
echo "[OK] normalizer.py started (PID $NORM_PID)"

echo ""
echo "Waiting 3 seconds for feed to initialize..."
sleep 3

# Steps 8-10: Print instructions
echo ""
echo "Ticket logged at ~/trading-support/support/logs/client-ticket.txt"
echo "Monitor quotes: ~/trading-support/support/bin/quotemon"
echo ""
echo "Trace the chain: publisher → normalizer → client feed. NVDA went dark silently."
echo ""
echo "Hints:"
echo "  1. Watch quotemon — NVDA will go stale ~60s after setup"
echo "  2. Check normalizer.log — notice anything missing?"
echo "  3. Read normalizer.py — find the silent exception"
echo "  4. Fix: add proper logging in the except block, re-raise or handle the error"
