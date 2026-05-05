#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Airflow Scenario: Settlement pipeline DAG failing at generate_settlement_files"

step "Creating directory structure..."
mkdir -p ~/trading-support/airflow/{dags,logs,data,output,bin}
ok "Directories created"

step "Writing dags/settlement_pipeline.py..."
cat > ~/trading-support/airflow/dags/settlement_pipeline.py << 'PYEOF'
#!/usr/bin/env python3
"""
Settlement Pipeline DAG — simulated lightweight runner (no real Airflow required).

Tasks:
  1. extract_trades          -> SUCCESS  (writes trades_raw.csv)
  2. validate_trades         -> SUCCESS  (validates rows)
  3. generate_settlement_files -> FAIL  (hardcoded broken output path)
  4. notify_dtcc             -> NEVER REACHED

BUG: generate_settlement_files writes to /opt/settlement/output/ which does not
     exist and the process user lacks permission to create it.

FIX (option A): Change OUTPUT_DIR in this file to ~/trading-support/airflow/output/
FIX (option B): sudo mkdir -p /opt/settlement/output && sudo chown $USER /opt/settlement/output
"""

import os
import csv
import sys
import random
import datetime
import logging

logging.basicConfig(
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO,
)
logger = logging.getLogger("settlement_pipeline")

# ── BUG IS HERE ──────────────────────────────────────────────────────────────
OUTPUT_DIR = "/opt/settlement/output"          # does not exist
# FIX: OUTPUT_DIR = os.path.expanduser("~/trading-support/airflow/output")
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR   = os.path.expanduser("~/trading-support/airflow/data")
RAW_CSV    = os.path.join(DATA_DIR, "trades_raw.csv")
RUN_DATE   = datetime.date.today().strftime("%Y%m%d")

SYMBOLS  = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
SIDES    = ["BUY", "SELL"]
ACCOUNTS = [f"ACC{i:04d}" for i in range(1, 21)]


def task_extract_trades():
    logger.info("Connecting to trade store (simulated)...")
    os.makedirs(DATA_DIR, exist_ok=True)
    rows = []
    for i in range(1, 201):
        sym  = random.choice(SYMBOLS)
        side = random.choice(SIDES)
        qty  = random.randint(100, 5000)
        px   = round(random.uniform(100, 900), 4)
        acct = random.choice(ACCOUNTS)
        rows.append({
            "trade_id": f"TRD{i:06d}",
            "symbol":   sym,
            "side":     side,
            "quantity": qty,
            "price":    px,
            "account":  acct,
            "trade_date": str(datetime.date.today()),
        })
    with open(RAW_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    logger.info(f"Extracted {len(rows)} trades -> {RAW_CSV}")
    return True


def task_validate_trades():
    if not os.path.exists(RAW_CSV):
        raise FileNotFoundError(f"Raw CSV not found: {RAW_CSV}")
    with open(RAW_CSV) as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    errors = [r for r in rows if float(r["price"]) <= 0 or int(r["quantity"]) <= 0]
    if errors:
        raise ValueError(f"Validation failed: {len(errors)} invalid rows")
    logger.info(f"Validated {len(rows)} trades — all checks passed")
    return True


def task_generate_settlement_files():
    if not os.path.exists(RAW_CSV):
        raise FileNotFoundError(f"Raw CSV not found: {RAW_CSV}")

    out_file = os.path.join(OUTPUT_DIR, f"settlement_{RUN_DATE}.csv")
    logger.info(f"Writing settlement file to {out_file} ...")

    # This will raise FileNotFoundError because OUTPUT_DIR doesn't exist
    with open(out_file, "w", newline="") as f:
        f.write("trade_id,symbol,side,quantity,price,account,settlement_date,status\n")
        with open(RAW_CSV) as raw:
            reader = csv.DictReader(raw)
            for row in reader:
                settle_date = (datetime.date.today() + datetime.timedelta(days=2)).isoformat()
                f.write(f"{row['trade_id']},{row['symbol']},{row['side']},"
                        f"{row['quantity']},{row['price']},{row['account']},"
                        f"{settle_date},PENDING\n")
    logger.info(f"Settlement file written: {out_file}")
    return True


def task_notify_dtcc():
    logger.info("Sending settlement notification to DTCC (simulated)...")
    logger.info("DTCC notification sent — batch acknowledged")
    return True


TASKS = [
    ("extract_trades",            task_extract_trades),
    ("validate_trades",           task_validate_trades),
    ("generate_settlement_files", task_generate_settlement_files),
    ("notify_dtcc",               task_notify_dtcc),
]

if __name__ == "__main__":
    # Allow running a single task: python3 settlement_pipeline.py <task_name>
    target = sys.argv[1] if len(sys.argv) > 1 else None
    if target:
        func = dict(TASKS).get(target)
        if not func:
            print(f"Unknown task: {target}", file=sys.stderr)
            sys.exit(1)
        try:
            func()
        except Exception as e:
            logger.error(f"{type(e).__name__}: {e}")
            sys.exit(1)
    else:
        # Run all tasks in order (used by run_dag.py)
        for name, func in TASKS:
            try:
                func()
            except Exception as e:
                logger.error(f"{type(e).__name__}: {e}")
                sys.exit(f"TASK_FAILED:{name}")
PYEOF
ok "dags/settlement_pipeline.py written"

step "Writing run_dag.py..."
cat > ~/trading-support/airflow/run_dag.py << 'PYEOF'
#!/usr/bin/env python3
"""
Lightweight DAG runner — simulates `airflow dags trigger` output.
Runs settlement_pipeline tasks in order and prints colored status.
"""

import subprocess
import sys
import os
import datetime
import importlib.util

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

DAG_ID   = "settlement_pipeline"
RUN_ID   = f"manual__{datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
DAG_FILE = os.path.expanduser(f"~/trading-support/airflow/dags/{DAG_ID}.py")
LOG_FILE = os.path.expanduser(f"~/trading-support/airflow/logs/{DAG_ID}.log")

TASKS = [
    "extract_trades",
    "validate_trades",
    "generate_settlement_files",
    "notify_dtcc",
]

def banner(msg):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}{msg}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}\n")

def task_header(task_id, state):
    if state == "running":
        print(f"  {YELLOW}[RUNNING]{RESET}  {task_id}")
    elif state == "success":
        print(f"  {GREEN}[SUCCESS]{RESET}  {task_id}")
    elif state == "failed":
        print(f"  {RED}[FAILED ]{RESET}  {task_id}")
    elif state == "skipped":
        print(f"  {YELLOW}[SKIPPED]{RESET}  {task_id}  (upstream failed)")

def run_task(task_id):
    result = subprocess.run(
        [sys.executable, DAG_FILE, task_id],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr

def main():
    banner(f"DAG Run: {DAG_ID}  |  Run ID: {RUN_ID}")
    print(f"  {BOLD}Execution date:{RESET} {datetime.date.today()}")
    print(f"  {BOLD}Tasks:{RESET}         {len(TASKS)}\n")

    failed_at = None
    logs = []

    for task_id in TASKS:
        if failed_at:
            task_header(task_id, "skipped")
            logs.append(f"[{datetime.datetime.now()}] SKIPPED  {task_id}  (upstream: {failed_at} failed)\n")
            continue

        task_header(task_id, "running")
        rc, stdout, stderr = run_task(task_id)

        combined_log = stdout + stderr
        log_lines = combined_log.strip().splitlines()
        for line in log_lines:
            print(f"    {line}")

        if rc == 0:
            task_header(task_id, "success")
            logs.append(f"[{datetime.datetime.now()}] SUCCESS  {task_id}\n")
            for line in log_lines:
                logs.append(f"  {line}\n")
        else:
            task_header(task_id, "failed")
            failed_at = task_id
            logs.append(f"[{datetime.datetime.now()}] FAILED   {task_id}\n")
            for line in log_lines:
                logs.append(f"  {line}\n")
        print()

    # Write consolidated log
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"RUN_ID: {RUN_ID}\n")
        f.writelines(logs)

    if failed_at:
        print(f"\n{RED}{BOLD}DAG FAILED at task: {failed_at}{RESET}")
        print(f"  Log: {LOG_FILE}")
        print(f"\n  {YELLOW}Hint:{RESET} Check OUTPUT_DIR in {DAG_FILE}")
        print(f"  The task tried to write to /opt/settlement/output/ (does not exist).")
        sys.exit(1)
    else:
        print(f"\n{GREEN}{BOLD}DAG SUCCEEDED{RESET}")

if __name__ == "__main__":
    main()
PYEOF
ok "run_dag.py written"

step "Seeding logs/settlement_pipeline.log with error example..."
mkdir -p ~/trading-support/airflow/logs
cat > ~/trading-support/airflow/logs/settlement_pipeline.log << 'LOGEOF'
============================================================
RUN_ID: scheduled__2026-05-04T02:00:00
[2026-05-04 02:00:01] SUCCESS  extract_trades
  [2026-05-04 02:00:01] {settlement_pipeline.py:68} INFO - Extracted 200 trades -> /home/acm/trading-support/airflow/data/trades_raw.csv
[2026-05-04 02:00:02] SUCCESS  validate_trades
  [2026-05-04 02:00:02] {settlement_pipeline.py:82} INFO - Validated 200 trades — all checks passed
[2026-05-04 02:00:02] FAILED   generate_settlement_files
  [2026-05-04 02:00:02] {settlement_pipeline.py:97} INFO - Writing settlement file to /opt/settlement/output/settlement_20260504.csv ...
  [ERROR] FileNotFoundError: [Errno 2] No such file or directory: '/opt/settlement/output/settlement_20260505.csv'
[2026-05-04 02:00:02] SKIPPED  notify_dtcc  (upstream: generate_settlement_files failed)
LOGEOF
ok "logs/settlement_pipeline.log written"

step "Writing airflow CLI wrapper..."
cat > ~/trading-support/airflow/bin/airflow << 'BASHEOF'
#!/bin/bash
# Lightweight airflow CLI wrapper for the settlement pipeline scenario.
# Place ~/trading-support/airflow/bin on your PATH:
#   export PATH=~/trading-support/airflow/bin:$PATH

DAG_ID="settlement_pipeline"
DAGS_DIR=~/trading-support/airflow/dags
RUN_DAG=~/trading-support/airflow/run_dag.py

CMD="${1:-}"
shift || true

case "$CMD" in
  dags)
    sub="${1:-}"
    case "$sub" in
      list)
        echo "---"
        echo "dag_id             | filepath                                             | owner   | paused"
        echo "===================+======================================================+=========+======="
        echo "settlement_pipeline| ~/trading-support/airflow/dags/settlement_pipeline.py| airflow | False"
        ;;
      trigger)
        dag="${2:-$DAG_ID}"
        echo "Created <DagRun settlement_pipeline @ $(date -Iseconds): manual__$(date -Iseconds), externally triggered: True>"
        python3 "$RUN_DAG"
        ;;
      *)
        echo "airflow dags [list|trigger]"
        ;;
    esac
    ;;
  tasks)
    sub="${1:-}"
    case "$sub" in
      list)
        dag="${2:-$DAG_ID}"
        echo "extract_trades"
        echo "validate_trades"
        echo "generate_settlement_files"
        echo "notify_dtcc"
        ;;
      run)
        dag="$2"
        task="$3"
        run_date="${4:-$(date +%Y-%m-%d)}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] {taskinstance.py} INFO - Running task: $task"
        python3 "$DAGS_DIR/settlement_pipeline.py" "$task"
        if [ $? -eq 0 ]; then
          echo "[$(date '+%Y-%m-%d %H:%M:%S')] {taskinstance.py} INFO - Task $task finished with state: success"
        else
          echo "[$(date '+%Y-%m-%d %H:%M:%S')] {taskinstance.py} ERROR - Task $task finished with state: failed"
          exit 1
        fi
        ;;
      *)
        echo "airflow tasks [list|run]"
        ;;
    esac
    ;;
  *)
    echo "Usage: airflow <dags|tasks> <subcommand> [args]"
    echo ""
    echo "Available commands:"
    echo "  airflow dags list"
    echo "  airflow dags trigger settlement_pipeline"
    echo "  airflow tasks list settlement_pipeline"
    echo "  airflow tasks run settlement_pipeline <task_id> <execution_date>"
    ;;
esac
BASHEOF
chmod +x ~/trading-support/airflow/bin/airflow
ok "airflow wrapper written and chmod +x"

info "DAG is failing. Run: airflow dags trigger settlement_pipeline"
info "First add to PATH: export PATH=~/trading-support/airflow/bin:\$PATH"
