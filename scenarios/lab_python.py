#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Python & Bash Scripting Setup
==============================================================
Creates the environment for all Python & Bash scripting challenges (P1-P6).

Run with: python3 lab_python.py [--scenario N] [--teardown]

SCENARIOS:
  1   P-01  Log monitor bash script — creates log file + injects CRITICAL events
  2   P-02  awk log parsing  — creates rich structured trading log
  3   P-03  Python process watchdog — creates a "crashing" target process
  4   P-04  REST API client — spins up a mock trading REST API server
  5   P-05  FIX message parser — creates raw FIX message sample files
  6   P-06  Kafka lag monitor — creates a mock lag-data source
  99        ALL scenarios
"""

import os
import sys
import time
import signal
import shutil
import socket
import random
import argparse
import threading
import subprocess
import multiprocessing
from pathlib import Path
from datetime import datetime, timedelta

LAB_ROOT = Path("/tmp/lab_python")
DIRS = {
    "logs":    LAB_ROOT / "logs",
    "scripts": LAB_ROOT / "scripts",
    "data":    LAB_ROOT / "data",
    "pids":    LAB_ROOT / "run",
    "api":     LAB_ROOT / "api",
}

from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    create_dirs as _create_dirs,
    save_pid as _save_pid, load_pids as _load_pids,
    spawn as _spawn, kill_pids, kill_strays, remove_lab_dir,
    show_status as _show_status,
)

def create_dirs():  _create_dirs(DIRS)
def save_pid(n, p): _save_pid(DIRS["pids"], n, p)
def load_pids():    return _load_pids(DIRS["pids"])
def spawn(t, a, n): return _spawn(t, a, DIRS["pids"], n)


# ══════════════════════════════════════════════
#  BACKGROUND WORKERS
# ══════════════════════════════════════════════

def _log_injector(log_path: str, interval: float = 2.0):
    """Continuously writes log lines, injecting CRITICAL bursts every ~30s."""
    try:
        import setproctitle; setproctitle.setproctitle("log_injector")
    except ImportError:
        pass
    symbols = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]
    counter = 0
    burst_countdown = 30
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sym = random.choice(symbols)
        price = round(185.0 + random.gauss(0, 1), 2)

        if burst_countdown <= 0:
            # Write 7 CRITICAL lines to trigger the alert
            for _ in range(7):
                with open(log_path, "a") as f:
                    f.write(f"{now} CRITICAL order_router connection lost to EXCHANGE_A\n")
            burst_countdown = 30
        else:
            level = random.choice(["INFO"] * 8 + ["WARN"] * 1)
            with open(log_path, "a") as f:
                f.write(f"{now} {level} ORDER FILLED symbol={sym} qty={random.randint(50,500)} price={price}\n")

        burst_countdown -= 1
        counter += 1
        time.sleep(interval)


def _crashy_process(name: str):
    """A process that starts and crashes every ~10 seconds — for watchdog exercise."""
    try:
        import setproctitle; setproctitle.setproctitle(name)
    except ImportError:
        pass
    while True:
        time.sleep(8 + random.uniform(0, 4))
        # Simulate crash
        os._exit(1)


def _mock_rest_api(port: int):
    """
    Minimal HTTP REST server returning trading data as JSON.
    Supports: GET /api/orders, GET /api/positions, GET /api/health
    """
    try:
        import setproctitle; setproctitle.setproctitle("mock_rest_api")
    except ImportError:
        pass
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json

    ORDERS = [
        {"id": "ORD-001", "symbol": "AAPL", "side": "BUY",  "qty": 100, "price": 185.50, "status": "FILLED"},
        {"id": "ORD-002", "symbol": "GOOGL", "side": "SELL", "qty":  50, "price": 141.20, "status": "FILLED"},
        {"id": "ORD-003", "symbol": "TSLA",  "side": "BUY",  "qty": 200, "price": 248.00, "status": "REJECTED"},
        {"id": "ORD-004", "symbol": "MSFT",  "side": "BUY",  "qty":  75, "price": 380.10, "status": "PENDING"},
        {"id": "ORD-005", "symbol": "NVDA",  "side": "BUY",  "qty":  60, "price": 495.00, "status": "FILLED"},
    ]
    POSITIONS = [
        {"trader": "T001", "symbol": "AAPL",  "net_qty":  450, "avg_price": 185.45},
        {"trader": "T001", "symbol": "NVDA",  "net_qty":   60, "avg_price": 495.00},
        {"trader": "T002", "symbol": "TSLA",  "net_qty":    0, "avg_price": 0},
        {"trader": "T003", "symbol": "GOOGL", "net_qty":  -75, "avg_price": 141.20},
    ]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass  # silence access log

        def do_GET(self):
            routes = {
                "/api/orders":    ORDERS,
                "/api/positions": POSITIONS,
                "/api/health":    {"status": "ok", "uptime_s": int(time.time() % 86400)},
                "/api/orders?status=REJECTED": [o for o in ORDERS if o["status"] == "REJECTED"],
            }
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'{"error":"not found"}')
                return
            data = json.dumps(body, indent=2).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    srv = HTTPServer(("0.0.0.0", port), Handler)
    srv.serve_forever()


# ══════════════════════════════════════════════
#  SCENARIO LAUNCHERS
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario P-01 — Write a Log Monitor Script")
    print("  Write a Bash script that watches a log file and alerts")
    print("  when 'CRITICAL' appears more than 5 times.\n")

    log_path = DIRS["logs"] / "trading_app.log"
    # Seed with some initial lines
    log_path.write_text(
        "\n".join(
            f"{(datetime.now() - timedelta(seconds=i)).strftime('%Y-%m-%d %H:%M:%S')} "
            f"INFO ORDER FILLED symbol=AAPL qty=100 price=185.50"
            for i in range(30, 0, -1)
        ) + "\n"
    )
    ok(f"Log file created: {log_path}")

    # Start the live injector
    pid = spawn(_log_injector, (str(log_path), 1.5), "log_injector_p01")
    ok(f"Log injector started  PID={pid}  (CRITICAL burst every ~30 lines)")

    # Write the solution script for reference
    solution = DIRS["scripts"] / "monitor.sh"
    solution.write_text(f"""\
#!/bin/bash
# P-01 Solution: Log monitor — alert when CRITICAL > threshold
# Usage: bash {solution} {log_path}

LOG_FILE="${{1:- {log_path}}}"
THRESHOLD=5
INTERVAL=10

if [ -z "$LOG_FILE" ]; then
    echo "Usage: $0 <log_file>"
    exit 1
fi

echo "Monitoring $LOG_FILE for CRITICAL events (threshold=$THRESHOLD)..."

while true; do
    COUNT=$(tail -n 200 "$LOG_FILE" | grep "CRITICAL" | wc -l)
    if [ "$COUNT" -gt "$THRESHOLD" ]; then
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
        echo "[$TIMESTAMP] ⚠ ALERT: $COUNT CRITICAL events in recent log lines!"
    fi
    sleep $INTERVAL
done
""")
    ok(f"Reference solution:    {solution}")

    print(f"""
{BOLD}── Log file (live, injector running): ──────────────────{RESET}
{CYAN}       {log_path}{RESET}

{BOLD}── Your Task: write monitor.sh from scratch ────────────{RESET}
  Requirements:
  • Accept log file path as $1
  • Loop every 10 seconds
  • Count CRITICAL in recent lines
  • Alert (echo) if count > 5

{BOLD}── Test it immediately ─────────────────────────────────{RESET}
{CYAN}       tail -f {log_path}              # watch the live log
       bash {solution} {log_path}  # run the solution to verify{RESET}

{BOLD}── Key commands ────────────────────────────────────────{RESET}
{CYAN}       tail -n 200 {log_path} | grep "CRITICAL" | wc -l
       date '+%Y-%m-%d %H:%M:%S'
       while true; do ...; sleep 10; done{RESET}
""")


def launch_scenario_2():
    header("Scenario P-02 — Parse Log with awk and Summarize")
    print("  Structured trading log with symbol/qty/price fields.")
    print("  Extract insights using awk and bash.\n")

    log_path = DIRS["logs"] / "structured_trades.log"
    symbols   = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA", "AMZN"]
    sides     = ["BUY", "SELL"]
    lines = []
    base_ts = datetime(2024, 1, 15, 9, 30, 0)
    for i in range(80):
        ts  = (base_ts + timedelta(seconds=i * 30)).strftime("%Y-%m-%d %H:%M:%S")
        sym = random.choice(symbols)
        side = random.choice(sides)
        qty  = random.choice([50, 100, 200, 500, 1000])
        price = round(random.uniform(100, 500), 2)
        level = random.choice(["INFO"] * 6 + ["WARN"] * 2 + ["ERROR"] * 1)
        lines.append(f"{ts} {level} ORDER {random.choice(['FILLED','REJECTED','PARTIAL'])} "
                     f"symbol={sym} qty={qty} price={price} side={side}")
    log_path.write_text("\n".join(lines) + "\n")
    ok(f"Structured log created: {log_path}  ({len(lines)} lines)")

    solution = DIRS["scripts"] / "parse_log.sh"
    solution.write_text(f"""\
#!/bin/bash
# P-02 Solution: awk log analysis
LOG="{log_path}"

echo "=== Total fills per symbol ==="
grep "FILLED" "$LOG" | awk -F'symbol=' '{{print $2}}' | awk '{{print $1}}' \\
  | sort | uniq -c | sort -rn

echo ""
echo "=== Total volume (qty) per symbol ==="
grep "FILLED" "$LOG" | awk '{{
    for(i=1;i<=NF;i++) {{
        if ($i ~ /^symbol=/) sym=substr($i,8)
        if ($i ~ /^qty=/)    qty=substr($i,5)+0
    }}
    vol[sym]+=qty
}}
END {{ for (s in vol) printf "%8d  %s\\n", vol[s], s }}' | sort -rn

echo ""
echo "=== Log level counts ==="
awk '{{print $3}}' "$LOG" | sort | uniq -c | sort -rn

echo ""
echo "=== Total notional (qty*price) across all fills ==="
grep "FILLED" "$LOG" | awk '{{
    for(i=1;i<=NF;i++) {{
        if ($i ~ /^qty=/)   qty=substr($i,5)+0
        if ($i ~ /^price=/) price=substr($i,7)+0
    }}
    total += qty * price
}}
END {{ printf "Total notional: $%.2f\\n", total }}'
""")
    ok(f"Reference solution: {solution}")

    print(f"""
{BOLD}── Log file: {log_path} ───{RESET}
{CYAN}       head -5 {log_path}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Count total filled orders per symbol
{CYAN}       grep "FILLED" {log_path} | awk -F'symbol=' '{{print $2}}' \\
         | awk '{{print $1}}' | sort | uniq -c | sort -rn{RESET}

  2. Calculate total volume (qty) per symbol for fills
{CYAN}       grep "FILLED" {log_path} | awk '{{
         for(i=1;i<=NF;i++) {{
           if ($i ~ /^symbol=/) sym=substr($i,8)
           if ($i ~ /^qty=/)    qty=substr($i,5)+0
         }}
         vol[sym]+=qty
       }} END {{for (s in vol) print vol[s], s}}' | sort -rn{RESET}

  3. Count log level distribution
{CYAN}       awk '{{print $3}}' {log_path} | sort | uniq -c | sort -rn{RESET}

  4. Calculate total notional across all fills
{CYAN}       bash {solution}{RESET}
""")


def launch_scenario_3():
    header("Scenario P-03 — Python Process Watchdog")
    print("  Write a Python watchdog that monitors a process and")
    print("  restarts it if it crashes.\n")

    # Write the target "crashy" process
    crashy = DIRS["scripts"] / "crashy_oms.py"
    crashy.write_text("""\
#!/usr/bin/env python3
\"\"\"Simulated OMS process — crashes after 8-12 seconds.\"\"\"
import time, random, sys, os

print(f"[{os.getpid()}] oms_client started", flush=True)
sleep_time = random.uniform(8, 12)
time.sleep(sleep_time)
print(f"[{os.getpid()}] FATAL: connection lost — exiting", flush=True)
sys.exit(1)
""")
    ok(f"Crashy process script: {crashy}")

    watchdog = DIRS["scripts"] / "watchdog.py"
    watchdog.write_text(f"""\
#!/usr/bin/env python3
\"\"\"
P-03 Solution: Process watchdog — monitors and auto-restarts a process.
Usage: python3 {watchdog}
\"\"\"
import subprocess, time, sys
from datetime import datetime

COMMAND     = [sys.executable, "{crashy}"]
MAX_RETRIES = 5
RESTART_DELAY = 2   # seconds to wait before restarting

def ts():
    return datetime.now().strftime("%H:%M:%S")

restart_count = 0
while restart_count < MAX_RETRIES:
    print(f"[{{ts()}}] Starting process (attempt {{restart_count + 1}}/{{MAX_RETRIES}})...")
    proc = subprocess.Popen(COMMAND)
    exit_code = proc.wait()
    restart_count += 1
    print(f"[{{ts()}}] Process exited with code {{exit_code}}")
    if exit_code == 0:
        print(f"[{{ts()}}] Clean exit — watchdog stopping.")
        break
    if restart_count < MAX_RETRIES:
        print(f"[{{ts()}}] Restarting in {{RESTART_DELAY}}s...")
        time.sleep(RESTART_DELAY)
    else:
        print(f"[{{ts()}}] ✗ Max retries ({MAX_RETRIES}) reached — giving up. Page on-call!")
""")
    ok(f"Watchdog solution:     {watchdog}")

    print(f"""
{BOLD}── Target process (crashes every 8-12s): ───────────────{RESET}
{CYAN}       python3 {crashy}{RESET}

{BOLD}── Your Task: write a Python watchdog ──────────────────{RESET}
  Requirements:
  • Launch the crashy_oms.py process as a subprocess
  • Detect when it exits (non-zero exit code = crash)
  • Restart it automatically
  • Give up after MAX_RETRIES (5) and alert

{BOLD}── Run the reference solution ───────────────────────────{RESET}
{CYAN}       python3 {watchdog}{RESET}

{BOLD}── Key Python APIs ─────────────────────────────────────{RESET}
{CYAN}       import subprocess
       proc = subprocess.Popen([sys.executable, "script.py"])
       exit_code = proc.wait()     # blocks until process exits
       proc.poll()                 # non-blocking check (None = still running){RESET}
""")


def launch_scenario_4():
    header("Scenario P-04 — REST API Client")
    print("  A mock Trading REST API is running locally.")
    print("  Write a Python client to query orders and report rejections.\n")

    API_PORT = 8765
    pid = spawn(_mock_rest_api, (API_PORT,), "mock_rest_api")
    ok(f"Mock REST API started on port {API_PORT}  PID={pid}")

    # Verify it's up
    time.sleep(0.5)

    client = DIRS["scripts"] / "api_client.py"
    client.write_text(f"""\
#!/usr/bin/env python3
\"\"\"
P-04 Solution: REST API client for trading system.
Queries orders and prints rejection summary.
\"\"\"
import urllib.request, json

BASE_URL = "http://127.0.0.1:{API_PORT}"

def get(endpoint):
    url = BASE_URL + endpoint
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"  ✗ Error fetching {{endpoint}}: {{e}}")
        return []

print("=== Health Check ===")
health = get("/api/health")
print(f"  Status: {{health.get('status')}}, uptime: {{health.get('uptime_s')}}s")

print("\\n=== All Orders ===")
orders = get("/api/orders")
for o in orders:
    flag = "⚠" if o["status"] == "REJECTED" else " "
    print(f"  {{flag}} {{o['id']}} {{o['symbol']:5}} {{o['side']:4}} {{o['qty']:4}} @ ${{o['price']}}  [{{o['status']}}]")

print("\\n=== Rejected Orders ===")
rejected = [o for o in orders if o["status"] == "REJECTED"]
if rejected:
    for o in rejected:
        print(f"  ✗ {{o['id']}} {{o['symbol']}} {{o['side']}} {{o['qty']}} — likely cause: margin/position limit")
else:
    print("  None.")

print("\\n=== Positions ===")
positions = get("/api/positions")
for p in positions:
    print(f"  {{p['trader']}} {{p['symbol']:6}} net_qty={{p['net_qty']:6}}  avg={{p['avg_price']}}")
""")
    ok(f"Reference client:  {client}")

    print(f"""
{BOLD}── Mock REST API: http://127.0.0.1:{API_PORT} ──────────────────{RESET}
  GET /api/health
  GET /api/orders
  GET /api/positions

{BOLD}── Quick test with curl ─────────────────────────────────{RESET}
{CYAN}       curl http://127.0.0.1:{API_PORT}/api/health
       curl http://127.0.0.1:{API_PORT}/api/orders
       curl http://127.0.0.1:{API_PORT}/api/positions{RESET}

{BOLD}── Your Task: write a Python client ────────────────────{RESET}
  Requirements:
  • Use urllib.request (no third-party libs needed)
  • Fetch all orders, print count per status
  • Print a rejection report (symbol, qty, estimated cause)
  • Handle connection errors gracefully

{BOLD}── Run the reference solution ───────────────────────────{RESET}
{CYAN}       python3 {client}{RESET}

{BOLD}── Key Python APIs ─────────────────────────────────────{RESET}
{CYAN}       import urllib.request, json
       with urllib.request.urlopen("http://...", timeout=5) as r:
           data = json.loads(r.read()){RESET}
""")


def launch_scenario_5():
    header("Scenario P-05 — FIX Message Parser")
    print("  Write a Python script that parses raw FIX 4.4 messages")
    print("  and extracts key fields.\n")

    # Write sample FIX messages
    fix_file = DIRS["data"] / "fix_messages.txt"
    fix_messages = [
        # Logon
        "8=FIX.4.4\x019=65\x0135=A\x0149=FIRM_OMS\x0156=EXCHANGE_A\x0134=1\x0152=20240115-09:30:00\x0198=0\x01108=30\x0110=120\x01",
        # New Order Single - BUY AAPL
        "8=FIX.4.4\x019=148\x0135=D\x0149=FIRM_OMS\x0156=EXCHANGE_A\x0134=2\x0152=20240115-09:30:01\x0111=ORD-001\x0155=AAPL\x0154=1\x0160=20240115-09:30:01\x0138=100\x0140=2\x0144=185.50\x0159=0\x0110=222\x01",
        # Execution Report - Fill
        "8=FIX.4.4\x019=160\x0135=8\x0149=EXCHANGE_A\x0156=FIRM_OMS\x0134=3\x0152=20240115-09:30:01\x0117=EXEC-001\x0137=ORD-001\x0139=2\x0155=AAPL\x0154=1\x0138=100\x0132=100\x0131=185.50\x016=185.50\x0114=100\x0110=189\x01",
        # New Order Single - SELL GOOGL
        "8=FIX.4.4\x019=150\x0135=D\x0149=FIRM_OMS\x0156=EXCHANGE_A\x0134=4\x0152=20240115-09:31:00\x0111=ORD-002\x0155=GOOGL\x0154=2\x0160=20240115-09:31:00\x0138=50\x0140=1\x0159=0\x0110=201\x01",
        # Order Cancel Request
        "8=FIX.4.4\x019=120\x0135=F\x0149=FIRM_OMS\x0156=EXCHANGE_A\x0134=5\x0152=20240115-09:32:00\x0141=ORD-002\x0111=ORD-003\x0155=GOOGL\x0154=2\x0138=50\x0110=098\x01",
        # Heartbeat
        "8=FIX.4.4\x019=52\x0135=0\x0149=FIRM_OMS\x0156=EXCHANGE_A\x0134=6\x0152=20240115-09:35:00\x0110=077\x01",
    ]
    fix_file.write_text("\n".join(fix_messages) + "\n")
    ok(f"FIX message file: {fix_file}")

    # Write the parser solution
    parser_script = DIRS["scripts"] / "fix_parser.py"
    parser_script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"
P-05 Solution: FIX 4.4 message parser.
Parses raw FIX messages and extracts key fields.
\"\"\"

FIX_TAGS = {{
    "8":  "BeginString",   "9":  "BodyLength",    "35": "MsgType",
    "49": "SenderCompID",  "56": "TargetCompID",  "34": "MsgSeqNum",
    "52": "SendingTime",   "11": "ClOrdID",        "37": "OrderID",
    "17": "ExecID",        "39": "OrdStatus",     "55": "Symbol",
    "54": "Side",          "38": "OrderQty",       "40": "OrdType",
    "44": "Price",         "31": "LastPx",         "32": "LastQty",
    "14": "CumQty",        "6":  "AvgPx",          "59": "TimeInForce",
    "41": "OrigClOrdID",   "98": "EncryptMethod",  "108":"HeartBtInt",
    "10": "CheckSum",
}}

MSG_TYPES = {{
    "0": "Heartbeat",     "A": "Logon",       "5": "Logout",
    "D": "NewOrderSingle","8": "ExecutionReport", "F": "OrderCancelRequest",
    "9": "OrderCancelReject",
}}

SIDES      = {{"1": "BUY", "2": "SELL"}}
ORD_STATUS = {{"0": "New", "1": "PartialFill", "2": "Filled", "4": "Cancelled", "8": "Rejected"}}
ORD_TYPES  = {{"1": "Market", "2": "Limit", "3": "Stop"}}

def parse_fix(raw: str) -> dict:
    \"\"\"Parse a FIX message string into a dict of tag→value.\"\"\"
    fields = {{}}
    for pair in raw.split("\\x01"):
        if "=" in pair:
            tag, val = pair.split("=", 1)
            fields[tag.strip()] = val.strip()
    return fields

def describe(fields: dict) -> None:
    msg_type = fields.get("35", "?")
    type_name = MSG_TYPES.get(msg_type, f"Unknown({msg_type})")
    print(f"  ┌─ MsgType={msg_type} ({type_name})")
    print(f"  │  Seq={fields.get('34','?')}  From={fields.get('49','?')} → {fields.get('56','?')}")
    print(f"  │  Time={fields.get('52','?')}")

    if msg_type == "D":  # NewOrderSingle
        side = SIDES.get(fields.get("54",""), fields.get("54","?"))
        ot   = ORD_TYPES.get(fields.get("40",""), fields.get("40","?"))
        print(f"  │  ORDER: {{side}} {{fields.get('38','?')}} {{fields.get('55','?')}} "
              f"@ ${{fields.get('44','MARKET')}} [{{ot}}]")
        print(f"  │  ClOrdID={{fields.get('11','?')}}")

    elif msg_type == "8":  # ExecutionReport
        status = ORD_STATUS.get(fields.get("39",""), fields.get("39","?"))
        print(f"  │  EXEC: status={{status}} LastPx={{fields.get('31','?')}} "
              f"LastQty={{fields.get('32','?')}} CumQty={{fields.get('14','?')}}")
        print(f"  │  OrderID={{fields.get('37','?')}}  ClOrdID={{fields.get('11','?')}}")

    elif msg_type == "F":  # Cancel
        print(f"  │  CANCEL: Symbol={{fields.get('55','?')}} OrigClOrdID={{fields.get('41','?')}}")

    print(f"  └─ Checksum={{fields.get('10','?')}}")

# ── Main ──
print(f"Parsing FIX messages from: {fix_file}\\n")
with open("{fix_file}") as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line: continue
        fields = parse_fix(line)
        print(f"Message #{{i}}:")
        describe(fields)
        print()
""")
    ok(f"Parser solution:  {parser_script}")

    print(f"""
{BOLD}── FIX message file: {fix_file} ────{RESET}
{CYAN}       cat {fix_file} | tr '\\001' '|'{RESET}

{BOLD}── Your Task: write a FIX parser ───────────────────────{RESET}
  Requirements:
  • Split on SOH (\\x01) delimiter
  • Split each field on first '=' to get tag=value
  • Decode tag 35 (MsgType): D=NewOrder, 8=ExecReport, 0=Heartbeat
  • For NewOrder: print symbol, side (1=BUY, 2=SELL), qty, price
  • For ExecReport: print status (39), lastPx (31), cumQty (14)

{BOLD}── Run the reference solution ───────────────────────────{RESET}
{CYAN}       python3 {parser_script}{RESET}

{BOLD}── Key FIX tags to know ─────────────────────────────────{RESET}
  8=BeginString  9=BodyLength  35=MsgType  49=Sender  56=Target
  34=SeqNum  11=ClOrdID  55=Symbol  54=Side  38=Qty  44=Price
  35=D → NewOrderSingle   35=8 → ExecutionReport   35=0 → Heartbeat
""")


def launch_scenario_6():
    header("Scenario P-06 — Kafka Consumer Lag Monitor")
    print("  Write a Python script that queries Kafka consumer lag")
    print("  and alerts when any partition exceeds threshold.\n")

    # Write a mock lag data file (simulate kafka-consumer-groups output)
    lag_data = DIRS["data"] / "consumer_lag_snapshot.json"
    import json
    snapshot = {
        "group": "risk-engine-group",
        "timestamp": datetime.now().isoformat(),
        "partitions": [
            {"topic": "trade-executions", "partition": 0, "current_offset": 10420, "log_end_offset": 10425, "lag": 5,    "consumer": "risk-worker-1"},
            {"topic": "trade-executions", "partition": 1, "current_offset": 9800,  "log_end_offset": 10200, "lag": 400,  "consumer": "risk-worker-2"},
            {"topic": "trade-executions", "partition": 2, "current_offset": 11000, "log_end_offset": 11002, "lag": 2,    "consumer": "risk-worker-1"},
            {"topic": "trade-executions", "partition": 3, "current_offset": 8500,  "log_end_offset": 10300, "lag": 1800, "consumer": "-"},
            {"topic": "market-data",      "partition": 0, "current_offset": 50001, "log_end_offset": 50010, "lag": 9,    "consumer": "md-consumer-1"},
            {"topic": "market-data",      "partition": 1, "current_offset": 49900, "log_end_offset": 50010, "lag": 110,  "consumer": "md-consumer-2"},
        ]
    }
    lag_data.write_text(json.dumps(snapshot, indent=2))
    ok(f"Lag snapshot: {lag_data}")

    lag_monitor = DIRS["scripts"] / "kafka_lag_monitor.py"
    lag_monitor.write_text(f"""\
#!/usr/bin/env python3
\"\"\"
P-06 Solution: Kafka consumer lag monitor.
Reads a lag snapshot and alerts on high-lag partitions.

In production you would use:
  kafka-python: AdminClient.list_consumer_group_offsets()
  confluent_kafka: Consumer.committed() vs watermark_offsets()
Here we read from a pre-built snapshot file.
\"\"\"
import json, sys

LAG_FILE  = "{lag_data}"
THRESHOLD = 100  # alert if any partition lag > 100

with open(LAG_FILE) as f:
    data = json.load(f)

group = data["group"]
parts = data["partitions"]

print(f"Consumer Group: {{group}}")
print(f"Snapshot:       {{data['timestamp']}}")
print(f"Alert threshold: LAG > {{THRESHOLD}}\\n")
print(f"  {{' TOPIC':<25}} {{' PART':>5}}  {{' LAG':>8}}  {{'CONSUMER':<20}}  STATUS")
print(f"  {{'-'*25}} {{'-'*5}}  {{'-'*8}}  {{'-'*20}}  {{'-'*8}}")

alerts = []
for p in sorted(parts, key=lambda x: -x["lag"]):
    status = "🔴 HIGH" if p["lag"] > THRESHOLD else ("⚠ WARN" if p["lag"] > 50 else "✅ OK")
    if p["consumer"] == "-":
        status = "🔴 NO CONSUMER"
    print(f"  {{p['topic']:<25}} {{p['partition']:>5}}  {{p['lag']:>8}}  {{p['consumer']:<20}}  {{status}}")
    if p["lag"] > THRESHOLD or p["consumer"] == "-":
        alerts.append(p)

print()
if alerts:
    print(f"⚠  {{len(alerts)}} partition(s) require attention:")
    for a in alerts:
        if a["consumer"] == "-":
            print(f"   partition {{a['partition']}} has NO CONSUMER (unassigned) — add consumer instances")
        else:
            print(f"   partition {{a['partition']}} lag={{a['lag']}} — consumer too slow or broker overloaded")
else:
    print("All partitions within threshold. ✅")
""")
    ok(f"Lag monitor solution: {lag_monitor}")

    print(f"""
{BOLD}── Lag snapshot file: {lag_data} ────{RESET}
{CYAN}       cat {lag_data}{RESET}

{BOLD}── Your Task: write a lag monitor in Python ────────────{RESET}
  Requirements:
  • Read the JSON snapshot
  • Print a table: topic, partition, lag, consumer
  • Highlight partitions with lag > 100 (WARNING)
  • Flag partitions with no consumer assigned ("-")
  • Print a summary of issues found

{BOLD}── Run the reference solution ───────────────────────────{RESET}
{CYAN}       python3 {lag_monitor}{RESET}

{BOLD}── In production, check real lag with: ─────────────────{RESET}
{CYAN}       kafka-consumer-groups.sh \\
         --bootstrap-server localhost:9092 \\
         --group risk-engine-group \\
         --describe{RESET}
""")


def launch_scenario_99():
    header("Scenario 99 — ALL Python & Bash Scenarios")
    for fn in [launch_scenario_1, launch_scenario_2, launch_scenario_3,
               launch_scenario_4, launch_scenario_5, launch_scenario_6]:
        fn()
        time.sleep(0.3)


# ══════════════════════════════════════════════
#  TEARDOWN
# ══════════════════════════════════════════════

def teardown():
    header("Tearing Down Python Lab")
    kill_pids(DIRS["pids"])
    kill_strays(["log_injector", "mock_rest_api"])
    remove_lab_dir(LAB_ROOT)


def show_status():
    _show_status(DIRS["pids"], "Python Lab")


SCENARIO_MAP = {
    1:  (launch_scenario_1, "P-01  Log monitor bash script"),
    2:  (launch_scenario_2, "P-02  awk log parsing"),
    3:  (launch_scenario_3, "P-03  Python process watchdog"),
    4:  (launch_scenario_4, "P-04  REST API client"),
    5:  (launch_scenario_5, "P-05  FIX message parser"),
    6:  (launch_scenario_6, "P-06  Kafka lag monitor"),
    99: (launch_scenario_99, "     ALL scenarios"),
}

def main():
    parser = argparse.ArgumentParser(description="Python & Bash Challenge Lab Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:<4} {v}" for k, (_, v) in SCENARIO_MAP.items()))
    parser.add_argument("--scenario", "-s", type=int, choices=list(SCENARIO_MAP.keys()))
    parser.add_argument("--teardown", "-t", action="store_true")
    parser.add_argument("--status",         action="store_true")
    args = parser.parse_args()
    if args.teardown: teardown(); return
    if args.status:   show_status(); return
    create_dirs()
    if args.scenario:
        fn, _ = SCENARIO_MAP[args.scenario]; fn()
    else:
        header("Python & Bash Challenge Lab")
        for num, (_, desc) in SCENARIO_MAP.items():
            print(f"    {num:<4} {desc}")
        choice = input("\n  Enter scenario number (or q): ").strip()
        if choice.lower() == "q": return
        try:
            fn, _ = SCENARIO_MAP[int(choice)]; fn()
        except (KeyError, ValueError): err(f"Invalid: {choice}")
    lab_footer("lab_python.py")

if __name__ == "__main__":
    main()
