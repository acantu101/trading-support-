#!/bin/bash
# Scenario: ATS TRF reporter has REPORTING_DELAY_MS=38000 — far beyond 10s regulatory window
source "$(dirname "$0")/../_lib/common.sh"

LAB_DIR=~/trading-support/darkpool
PID_DIR=~/trading-support/pids

echo "=== Dark Pool Scenario: TRF Reporting Delay Violation ==="
echo ""

# Step 1: Create directories
mkdir -p "$LAB_DIR"/{config,logs,bin,queue}
mkdir -p "$PID_DIR"

# Step 2: Write trf-reporter.conf
cat > "$LAB_DIR/config/trf-reporter.conf" << 'EOF'
[TRF_GATEWAY]
HOST=trf.finra.org
PORT=9443
VENUE_CODE=D

[REPORTING]
REPORTING_DELAY_MS=38000   # BUG: was set to 9000 for testing, never reverted
MAX_QUEUE_DEPTH=10000
BATCH_SIZE=50
RETRY_ATTEMPTS=3

[COMPLIANCE]
REGULATORY_WINDOW_MS=10000
ALERT_THRESHOLD_MS=9500
RULE=FINRA_4552
EOF

# Step 3: Write trf-reporter.py
cat > "$LAB_DIR/trf-reporter.py" << 'TRFEOF'
#!/usr/bin/env python3
"""
TRF Reporter — Submits dark pool trade reports to FINRA TRF.

BUG: REPORTING_DELAY_MS is 38000 (38 seconds) — was set to 9000 for
     testing and never reverted to the production value of 9000.
     Regulatory window is 10 seconds (FINRA Rule 4552).
     Every report is a compliance violation.
"""
import configparser
import time
import random
import string
import os
import signal
import sys
import json
from datetime import datetime

CONFIG_FILE = os.path.expanduser("~/trading-support/darkpool/config/trf-reporter.conf")
LOG_FILE    = os.path.expanduser("~/trading-support/darkpool/logs/trf-reporter.log")
QUEUE_DIR   = os.path.expanduser("~/trading-support/darkpool/queue")
STATS_FILE  = os.path.expanduser("~/trading-support/darkpool/logs/trf-stats.json")

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    return cfg

def random_trade_id():
    return "TMF-" + "".join(random.choices(string.digits, k=8))

def random_symbol():
    symbols = ["NVDA","AAPL","MSFT","GOOGL","META","AMZN","TSLA","JPM","GS","MS"]
    return random.choice(symbols)

def generate_trade():
    return {
        "trade_id":  random_trade_id(),
        "symbol":    random_symbol(),
        "qty":       random.randint(100, 50000),
        "price":     round(random.uniform(50, 900), 2),
        "side":      random.choice(["BUY", "SELL"]),
        "timestamp": time.time(),
    }

class TRFReporter:
    def __init__(self):
        self.cfg = load_config()
        self.delay_ms    = int(self.cfg["REPORTING"]["REPORTING_DELAY_MS"])
        self.reg_window  = int(self.cfg["COMPLIANCE"]["REGULATORY_WINDOW_MS"])
        self.alert_thresh = int(self.cfg["COMPLIANCE"]["ALERT_THRESHOLD_MS"])
        self.rule        = self.cfg["COMPLIANCE"]["RULE"]

        self.total_reported  = 0
        self.violations      = 0
        self.latencies_ms    = []
        self.running         = True

        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        os.makedirs(QUEUE_DIR, exist_ok=True)

        self.logf = open(LOG_FILE, "a", buffering=1)
        self._log(f"TRF Reporter started — REPORTING_DELAY_MS={self.delay_ms}")
        self._log(f"Regulatory window: {self.reg_window}ms ({self.rule})")
        if self.delay_ms > self.reg_window:
            self._log(f"WARNING: configured delay {self.delay_ms}ms EXCEEDS regulatory window {self.reg_window}ms!")

        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT,  self._handle_signal)

    def _handle_signal(self, sig, frame):
        self.running = False
        self.logf.close()
        sys.exit(0)

    def _log(self, msg):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{ts} [TRF] {msg}"
        print(line, flush=True)
        self.logf.write(line + "\n")

    def _write_stats(self):
        avg = (sum(self.latencies_ms) / len(self.latencies_ms)) if self.latencies_ms else 0
        stats = {
            "total_reported": self.total_reported,
            "violations": self.violations,
            "avg_latency_ms": round(avg, 1),
            "violation_rate_pct": round(self.violations / max(self.total_reported, 1) * 100, 1),
            "queue_depth": len(os.listdir(QUEUE_DIR)),
            "as_of": datetime.now().isoformat(),
        }
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=2)

    def run(self):
        last_stats = time.time()
        trade_interval = 0.5  # new trade every 500ms

        while self.running:
            # Generate a new trade execution
            trade = generate_trade()
            qfile = os.path.join(QUEUE_DIR, trade["trade_id"] + ".json")
            with open(qfile, "w") as f:
                json.dump(trade, f)

            self._log(
                f"Trade queued: {trade['trade_id']} {trade['symbol']} "
                f"{trade['side']} {trade['qty']}@{trade['price']}"
            )

            # Simulate the configured reporting delay
            time.sleep(self.delay_ms / 1000.0)

            # "Report" the trade (mock TRF submission)
            actual_latency_ms = self.delay_ms + random.uniform(-200, 200)
            self.total_reported += 1
            self.latencies_ms.append(actual_latency_ms)

            is_violation = actual_latency_ms > self.reg_window
            if is_violation:
                self.violations += 1
                status = f"VIOLATION: exceeds {self.reg_window/1000:.0f}s window ({self.rule})"
            else:
                status = "OK"

            self._log(
                f"Trade {trade['trade_id']} reported in {actual_latency_ms/1000:.1f}s "
                f"({status})"
            )

            # Remove from queue
            try:
                os.remove(qfile)
            except FileNotFoundError:
                pass

            # Print stats summary every 10 seconds
            if time.time() - last_stats >= 10:
                avg = sum(self.latencies_ms[-20:]) / len(self.latencies_ms[-20:])
                self._log(
                    f"STATS — reported={self.total_reported} "
                    f"violations={self.violations} "
                    f"avg_latency={avg/1000:.1f}s "
                    f"queue_depth={len(os.listdir(QUEUE_DIR))}"
                )
                self._write_stats()
                last_stats = time.time()

            time.sleep(trade_interval)

if __name__ == "__main__":
    reporter = TRFReporter()
    reporter.run()
TRFEOF

# Step 4: Write pre-populated trf-reporter.log with 20 violations
cat > "$LAB_DIR/logs/trf-reporter.log" << 'LOGEOF'
2026-05-04 09:30:00.001 [TRF] TRF Reporter started — REPORTING_DELAY_MS=38000
2026-05-04 09:30:00.002 [TRF] Regulatory window: 10000ms (FINRA_4552)
2026-05-04 09:30:00.003 [TRF] WARNING: configured delay 38000ms EXCEEDS regulatory window 10000ms!
2026-05-04 09:30:00.100 [TRF] Trade queued: TMF-10000001 NVDA BUY 15000@875.50
2026-05-04 09:30:38.211 [TRF] Trade TMF-10000001 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:30:38.712 [TRF] Trade queued: TMF-10000002 AAPL SELL 8200@189.42
2026-05-04 09:31:16.891 [TRF] Trade TMF-10000002 reported in 38.2s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:31:17.391 [TRF] Trade queued: TMF-10000003 MSFT BUY 3100@415.87
2026-05-04 09:31:55.502 [TRF] Trade TMF-10000003 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:31:56.002 [TRF] Trade queued: TMF-10000004 GOOGL SELL 2200@175.31
2026-05-04 09:32:34.123 [TRF] Trade TMF-10000004 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:32:34.623 [TRF] Trade queued: TMF-10000005 META BUY 9800@512.77
2026-05-04 09:33:12.744 [TRF] Trade TMF-10000005 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:33:13.244 [TRF] Trade queued: TMF-10000006 AMZN SELL 4100@183.92
2026-05-04 09:33:51.365 [TRF] Trade TMF-10000006 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:33:51.865 [TRF] STATS — reported=6 violations=6 avg_latency=38.1s queue_depth=0
2026-05-04 09:33:52.365 [TRF] Trade queued: TMF-10000007 TSLA BUY 6600@172.18
2026-05-04 09:34:30.486 [TRF] Trade TMF-10000007 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:34:30.986 [TRF] Trade queued: TMF-10000008 JPM SELL 12000@201.33
2026-05-04 09:35:09.107 [TRF] Trade TMF-10000008 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:35:09.607 [TRF] Trade queued: TMF-10000009 GS BUY 800@482.11
2026-05-04 09:35:47.728 [TRF] Trade TMF-10000009 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:35:48.228 [TRF] Trade queued: TMF-10000010 MS SELL 3300@108.77
2026-05-04 09:36:26.349 [TRF] Trade TMF-10000010 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:36:26.849 [TRF] Trade queued: TMF-10000011 NVDA SELL 22000@876.00
2026-05-04 09:37:04.970 [TRF] Trade TMF-10000011 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:37:04.970 [TRF] STATS — reported=11 violations=11 avg_latency=38.1s queue_depth=0
2026-05-04 09:37:05.470 [TRF] Trade queued: TMF-10000012 AAPL BUY 5500@189.55
2026-05-04 09:37:43.591 [TRF] Trade TMF-10000012 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:37:44.091 [TRF] Trade queued: TMF-10000013 MSFT SELL 1900@416.02
2026-05-04 09:38:22.212 [TRF] Trade TMF-10000013 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:38:22.712 [TRF] Trade queued: TMF-10000014 GOOGL BUY 3400@175.48
2026-05-04 09:39:00.833 [TRF] Trade TMF-10000014 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:39:01.333 [TRF] Trade queued: TMF-10000015 META SELL 7100@513.22
2026-05-04 09:39:39.454 [TRF] Trade TMF-10000015 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:39:39.954 [TRF] Trade queued: TMF-10000016 AMZN BUY 2800@184.07
2026-05-04 09:40:18.075 [TRF] Trade TMF-10000016 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:40:18.075 [TRF] STATS — reported=16 violations=16 avg_latency=38.1s queue_depth=0
2026-05-04 09:40:18.575 [TRF] Trade queued: TMF-10000017 TSLA SELL 4200@172.05
2026-05-04 09:40:56.696 [TRF] Trade TMF-10000017 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:40:57.196 [TRF] Trade queued: TMF-10000018 JPM BUY 9700@201.18
2026-05-04 09:41:35.317 [TRF] Trade TMF-10000018 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:41:35.817 [TRF] Trade queued: TMF-10000019 GS SELL 1100@481.99
2026-05-04 09:42:13.938 [TRF] Trade TMF-10000019 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:42:14.438 [TRF] Trade queued: TMF-10000020 MS BUY 6600@109.03
2026-05-04 09:42:52.559 [TRF] Trade TMF-10000020 reported in 38.1s (VIOLATION: exceeds 10s window (FINRA_4552))
2026-05-04 09:42:52.559 [TRF] STATS — reported=20 violations=20 avg_latency=38.1s queue_depth=0
LOGEOF

# Step 5: Write compliance-alert.txt
cat > "$LAB_DIR/logs/compliance-alert.txt" << 'ALERTEOF'
============================================================
FINRA SURVEILLANCE ALERT — AUTOMATED NOTIFICATION
============================================================
Alert ID   : FINRA-SURV-20260504-00391
Rule       : FINRA Rule 4552 (ATS Reporting)
Firm       : [YOUR FIRM NAME]
ATS ID     : [YOUR ATS ID]
Date       : 2026-05-04
Time       : 09:45:00 EST

VIOLATION SUMMARY
-----------------
Total trades reported today : 20
Trades within 10s window    : 0
Trades OUTSIDE 10s window   : 20
Violation rate              : 100%
Average reporting latency   : 38.1 seconds

REGULATORY REQUIREMENT
-----------------------
FINRA Rule 4552 requires ATS members to report transactions
to FINRA's Trade Reporting Facility (TRF) within 10 seconds
of execution.

Observed reporting delay: ~38 seconds (3.8x the regulatory limit)

REQUIRED ACTION
---------------
1. Immediately investigate TRF reporter configuration
2. Reduce REPORTING_DELAY_MS to < 9500ms (alert threshold)
3. Submit corrective action plan to FINRA within 5 business days
4. Ensure all historical violations are captured in your CAP

CONTACT
-------
FINRA Market Regulation: marketregulation@finra.org
Reference: Alert FINRA-SURV-20260504-00391

This is an automated surveillance alert. Failure to respond
may result in formal disciplinary action.
============================================================
ALERTEOF

# Step 6: Write trf-status script
cat > "$LAB_DIR/bin/trf-status" << 'STATUSEOF'
#!/bin/bash
# Show TRF reporter status: queue depth, avg latency, violation count

STATS_FILE=~/trading-support/darkpool/logs/trf-stats.json
LOG_FILE=~/trading-support/darkpool/logs/trf-reporter.log
QUEUE_DIR=~/trading-support/darkpool/queue
CONFIG_FILE=~/trading-support/darkpool/config/trf-reporter.conf

echo "=== TRF Reporter Status === $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

# Show config values
echo "--- Configuration ---"
grep "REPORTING_DELAY_MS\|REGULATORY_WINDOW_MS\|RULE" "$CONFIG_FILE" | sed 's/^/  /'
echo ""

# Show live stats if available
if [ -f "$STATS_FILE" ]; then
    echo "--- Live Stats ---"
    python3 -c "
import json
with open('$STATS_FILE') as f:
    d = json.load(f)
print(f'  Total Reported   : {d[\"total_reported\"]}')
print(f'  Violations       : {d[\"violations\"]} ({d[\"violation_rate_pct\"]}%)')
print(f'  Avg Latency      : {d[\"avg_latency_ms\"]/1000:.1f}s')
print(f'  Queue Depth      : {d[\"queue_depth\"]}')
print(f'  As Of            : {d[\"as_of\"]}')
" 2>/dev/null || echo "  (stats file not yet updated — reporter may just be starting)"
else
    echo "--- Live Stats ---"
    echo "  (no stats yet — check back in ~10 seconds)"
fi
echo ""

# Show queue
QUEUE_DEPTH=$(ls "$QUEUE_DIR" 2>/dev/null | wc -l)
echo "--- Queue ---"
echo "  Pending trades: $QUEUE_DEPTH"
if [ "$QUEUE_DEPTH" -gt 0 ]; then
    ls "$QUEUE_DIR" | head -5 | sed 's/^/  /'
fi
echo ""

# Show last 5 log lines
echo "--- Recent Log (last 5 entries) ---"
tail -5 "$LOG_FILE" 2>/dev/null | sed 's/^/  /' || echo "  (log not found)"
echo ""

# Show alert status
VIOLATIONS=$(grep -c "VIOLATION" "$LOG_FILE" 2>/dev/null || echo "0")
echo "--- Compliance ---"
echo "  Total VIOLATION entries in log: $VIOLATIONS"
if [ "$VIOLATIONS" -gt 0 ]; then
    echo "  STATUS: NON-COMPLIANT — FINRA_4552 violations detected"
else
    echo "  STATUS: OK"
fi
STATUSEOF
chmod +x "$LAB_DIR/bin/trf-status"

# Step 7: Start trf-reporter.py
echo "Starting trf-reporter.py..."
python3 "$LAB_DIR/trf-reporter.py" &
TRF_PID=$!
echo "$TRF_PID" > "$PID_DIR/darkpool.pid"
echo "[OK] trf-reporter.py started (PID $TRF_PID)"

# Steps 8-11: Print instructions
echo ""
echo "TRF reporter running with REPORTING_DELAY_MS=38000"
echo ""
echo "Check violations: ~/trading-support/darkpool/bin/trf-status"
echo "  cat ~/trading-support/darkpool/logs/trf-reporter.log"
echo "  cat ~/trading-support/darkpool/logs/compliance-alert.txt"
echo ""
echo "Fix: edit config/trf-reporter.conf, change REPORTING_DELAY_MS to 9000, restart the reporter"
echo ""
echo "Restart: kill \$(cat ~/trading-support/pids/darkpool.pid) && python3 ~/trading-support/darkpool/trf-reporter.py &"
