#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Airflow & Pipelines Setup
===========================================================
Creates realistic Airflow DAG files, task logs, broken pipelines,
and a mock Airflow REST API for all Airflow scenarios (AF1-AF5).

No real Airflow install needed — DAG files are fully valid Python,
logs are realistic, and a lightweight mock API runs locally.

Run with: python3 lab_airflow.py [--scenario N] [--teardown]

SCENARIOS:
  1   AF-01  Debug a failed DAG — task logs + error analysis
  2   AF-02  SLA miss investigation — slow task + monitoring script
  3   AF-03  Write a pipeline health check — mock Airflow API + script
  4   AF-04  Sensor task never triggering — ExternalTaskSensor diagnosis
  5   AF-05  Behavioral — tell your Airflow/pipeline story
  99         ALL scenarios
"""

import os, shutil, json, argparse, signal, time, multiprocessing, subprocess
from pathlib import Path
from datetime import datetime, timedelta
from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    create_dirs as _create_dirs,
    save_pid as _save_pid, load_pids as _load_pids,
    spawn as _spawn, kill_pids, kill_strays, remove_lab_dir,
    show_status as _show_status,
)

LAB_ROOT = Path("/tmp/lab_airflow")
DIRS = {
    "dags":    LAB_ROOT / "dags",
    "logs":    LAB_ROOT / "logs",
    "scripts": LAB_ROOT / "scripts",
    "data":    LAB_ROOT / "data",
    "pids":    LAB_ROOT / "run",
}

def create_dirs():  _create_dirs(DIRS)
def save_pid(n, p): _save_pid(DIRS["pids"], n, p)
def load_pids():    return _load_pids(DIRS["pids"])
def spawn(t, a, n): return _spawn(t, a, DIRS["pids"], n)

def write(path: Path, text: str) -> Path:
    path.write_text(text)
    ok(str(path).replace(str(LAB_ROOT) + "/", ""))
    return path


# ══════════════════════════════════════════════
#  MOCK AIRFLOW REST API
# ══════════════════════════════════════════════

def _mock_airflow_api(port: int):
    """Minimal HTTP server mimicking the Airflow REST API v1."""
    try:
        import setproctitle; setproctitle.setproctitle("mock_airflow_api")
    except ImportError:
        pass
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import json, urllib.parse

    DAG_RUNS = {
        "market_data_ingestion": [
            {"dag_id": "market_data_ingestion", "dag_run_id": "scheduled__2024-01-15T09:00:00+00:00",
             "state": "success", "start_date": "2024-01-15T09:00:01Z",
             "end_date": "2024-01-15T09:04:22Z", "execution_date": "2024-01-15T09:00:00Z"},
        ],
        "risk_calculation": [
            {"dag_id": "risk_calculation", "dag_run_id": "scheduled__2024-01-15T09:05:00+00:00",
             "state": "failed", "start_date": "2024-01-15T09:05:01Z",
             "end_date": "2024-01-15T09:06:12Z", "execution_date": "2024-01-15T09:05:00Z"},
        ],
        "trade_reconciliation": [
            {"dag_id": "trade_reconciliation", "dag_run_id": "scheduled__2024-01-15T17:00:00+00:00",
             "state": "failed", "start_date": "2024-01-15T17:00:01Z",
             "end_date": None, "execution_date": "2024-01-15T17:00:00Z"},
        ],
        "pnl_report": [
            {"dag_id": "pnl_report", "dag_run_id": "scheduled__2024-01-15T17:30:00+00:00",
             "state": "success", "start_date": "2024-01-15T17:30:01Z",
             "end_date": "2024-01-15T17:31:45Z", "execution_date": "2024-01-15T17:30:00Z"},
        ],
    }

    DAGS = [
        {"dag_id": "market_data_ingestion", "is_paused": False, "is_active": True,
         "last_parsed_time": "2024-01-15T09:00:00Z", "schedule_interval": "0 9 * * *"},
        {"dag_id": "risk_calculation",      "is_paused": False, "is_active": True,
         "last_parsed_time": "2024-01-15T09:05:00Z", "schedule_interval": "5 9 * * *"},
        {"dag_id": "trade_reconciliation",  "is_paused": False, "is_active": True,
         "last_parsed_time": "2024-01-15T17:00:00Z", "schedule_interval": "0 17 * * *"},
        {"dag_id": "pnl_report",            "is_paused": False, "is_active": True,
         "last_parsed_time": "2024-01-15T17:30:00Z", "schedule_interval": "30 17 * * *"},
    ]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def send_json(self, data, code=200):
            body = json.dumps(data, indent=2).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            p = self.path.split("?")[0]
            # GET /api/v1/dags
            if p == "/api/v1/dags":
                self.send_json({"dags": DAGS, "total_entries": len(DAGS)})
            # GET /api/v1/dags/<dag_id>/dagRuns
            elif "/dagRuns" in p:
                dag_id = p.split("/dags/")[1].split("/")[0]
                runs = DAG_RUNS.get(dag_id, [])
                # filter by state if ?state=failed in query
                qs = self.path.split("?")[1] if "?" in self.path else ""
                params = urllib.parse.parse_qs(qs)
                if "state" in params:
                    runs = [r for r in runs if r["state"] == params["state"][0]]
                self.send_json({"dag_runs": runs, "total_entries": len(runs)})
            else:
                self.send_json({"detail": "Not found"}, 404)

    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


# ══════════════════════════════════════════════
#  SCENARIO 1 — Debug a Failed DAG
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario AF-01 — Debug a Failed DAG")
    print("  risk_calculation DAG failed at 09:06. Diagnose from logs.\n")

    # Write a realistic DAG file
    write(DIRS["dags"] / "risk_calculation.py", """\
\"\"\"
Risk Calculation DAG
Runs daily at 09:05 after market_data_ingestion completes.
Reads market data, applies risk models, writes positions to DB.
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor

default_args = {
    "owner": "risk-team",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": True,
    "email": ["risk-oncall@firm.com"],
    "sla": timedelta(minutes=10),
}

with DAG(
    dag_id="risk_calculation",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="5 9 * * *",
    catchup=False,
    tags=["risk", "production"],
) as dag:

    wait_for_market_data = ExternalTaskSensor(
        task_id="wait_for_market_data",
        external_dag_id="market_data_ingestion",
        external_task_id="validate_data",
        timeout=600,
        mode="reschedule",
    )

    load_positions = PythonOperator(
        task_id="load_positions",
        python_callable=lambda: None,  # loads from DB
    )

    calculate_var = PythonOperator(
        task_id="calculate_var",
        python_callable=lambda: None,  # value-at-risk calc
    )

    write_risk_report = PythonOperator(
        task_id="write_risk_report",
        python_callable=lambda: None,
    )

    wait_for_market_data >> load_positions >> calculate_var >> write_risk_report
""")

    # Realistic task logs
    log_dir = DIRS["logs"] / "risk_calculation" / "calculate_var" / "2024-01-15T09:05:00+00:00"
    log_dir.mkdir(parents=True, exist_ok=True)
    write(log_dir / "1.log", """\
[2024-01-15 09:05:01,001] {taskinstance.py:1165} INFO - Dependencies all met
[2024-01-15 09:05:01,002] {taskinstance.py:1166} INFO - Starting attempt 1 of 3
[2024-01-15 09:05:01,100] {calculate_var.py:15} INFO  - Loading positions from database...
[2024-01-15 09:05:01,800] {calculate_var.py:22} INFO  - Loaded 847 positions
[2024-01-15 09:05:01,801] {calculate_var.py:28} INFO  - Starting VaR calculation for 847 positions...
[2024-01-15 09:05:04,210] {calculate_var.py:45} INFO  - Fetching historical price data from S3...
[2024-01-15 09:05:10,001] {calculate_var.py:52} ERROR - Failed to fetch price data from S3
[2024-01-15 09:05:10,002] {calculate_var.py:53} ERROR - botocore.exceptions.ClientError: An error occurred
    (403) when calling the GetObject operation: Access Denied
    Key: s3://trading-market-data/prices/2024-01-15/prices.parquet
[2024-01-15 09:05:10,003] {calculate_var.py:60} ERROR - S3 access denied. Check IAM role for airflow-worker.
[2024-01-15 09:05:10,010] {taskinstance.py:1280} ERROR - Task failed with exception
Traceback (most recent call last):
  File "/opt/airflow/dags/risk_calculation.py", line 52, in calculate_var
    prices = s3_client.get_object(Bucket="trading-market-data", Key=key)
  File "/usr/local/lib/python3.10/site-packages/botocore/client.py", line 975, in _api_call
    return self._make_api_call(operation_name, kwargs)
botocore.exceptions.ClientError: An error occurred (403) when calling the GetObject operation: Access Denied
[2024-01-15 09:05:10,020] {taskinstance.py:1281} INFO - Marking task as FAILED
[2024-01-15 09:05:10,025] {local_task_job.py:102} INFO - Task exited with return code 1
""")

    write(DIRS["scripts"] / "af01_diagnose.sh", f"""\
#!/bin/bash
# AF-01: Failed DAG Diagnosis Playbook

echo "=== Step 1: Read the failing task's log ==="
cat "{log_dir}/1.log"

echo ""
echo "=== Step 2: Root cause from the log ==="
grep "ERROR\|Traceback\|ClientError" "{log_dir}/1.log"

echo ""
echo "=== On real Airflow ==="
echo "  # UI: DAGs → risk_calculation → Grid → click calculate_var (red) → Logs"
echo "  # CLI:"
echo "  airflow tasks logs risk_calculation calculate_var 2024-01-15T09:05:00+00:00"

echo ""
echo "=== Root cause ==="
echo "  S3 access denied: IAM role for airflow-worker lacks s3:GetObject"
echo "  on bucket trading-market-data"

echo ""
echo "=== Fix options ==="
echo "  1. Add s3:GetObject to the airflow-worker IAM role policy"
echo "  2. Check bucket policy — explicit deny overrides role allow"
echo "  3. Verify the S3 key path is correct (typo in path?)"
echo "  aws iam simulate-principal-policy --policy-source-arn <role_arn> \\"
echo "    --action-names s3:GetObject \\"
echo "    --resource-arns arn:aws:s3:::trading-market-data/prices/*"

echo ""
echo "=== After fixing IAM: clear and re-run the task ==="
echo "  # UI: click the failed task → Clear → Confirm"
echo "  # CLI:"
echo "  airflow tasks clear risk_calculation --task-id calculate_var \\"
echo "    --execution-date 2024-01-15T09:05:00+00:00 --yes"
""")

    print(f"""
{BOLD}── Artifacts ────────────────────────────────────────────{RESET}
{CYAN}  cat "{log_dir}/1.log"               # task failure log
  cat {DIRS["dags"]}/risk_calculation.py      # the DAG
  cat {DIRS["scripts"]}/af01_diagnose.sh      # diagnosis steps{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Read the log and find the root cause
{CYAN}       grep "ERROR\|ClientError" "{log_dir}/1.log"{RESET}

  2. Identify the exact failure
{CYAN}       grep -A3 "Traceback" "{log_dir}/1.log"{RESET}

  3. Walk through the fix
{CYAN}       cat {DIRS["scripts"]}/af01_diagnose.sh{RESET}

{BOLD}── Root cause ───────────────────────────────────────────{RESET}
  airflow-worker IAM role lacks s3:GetObject on trading-market-data.
  Fix: update IAM policy, then clear + rerun the failed task.
  NEVER rerun without diagnosing first — if the IAM issue isn't fixed,
  you'll burn through retries and still fail.
""")


# ══════════════════════════════════════════════
#  SCENARIO 2 — SLA Miss Investigation
# ══════════════════════════════════════════════

def launch_scenario_2():
    header("Scenario AF-02 — SLA Miss Investigation")
    print("  trade_reconciliation DAG is missing its 17:30 SLA.\n")

    write(DIRS["dags"] / "trade_reconciliation.py", """\
\"\"\"
Trade Reconciliation DAG
Must complete by 17:30 each day (SLA = 30 minutes from 17:00 start).
Fetches fills from exchange, matches against OMS records, flags breaks.
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "ops-team",
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
    "sla": timedelta(minutes=30),   # ← must finish 30min after scheduled start
    "email_on_failure": True,
    "email_on_sla_miss": True,
    "email": ["ops@firm.com", "risk@firm.com"],
}

with DAG(
    dag_id="trade_reconciliation",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 17 * * *",
    catchup=False,
) as dag:

    fetch_exchange_fills = PythonOperator(
        task_id="fetch_exchange_fills",
        python_callable=lambda: None,
        execution_timeout=timedelta(minutes=10),
    )
    match_oms_records = PythonOperator(
        task_id="match_oms_records",
        python_callable=lambda: None,
    )
    flag_breaks = PythonOperator(
        task_id="flag_breaks",
        python_callable=lambda: None,
    )
    send_report = PythonOperator(
        task_id="send_report",
        python_callable=lambda: None,
    )
    fetch_exchange_fills >> match_oms_records >> flag_breaks >> send_report
""")

    # Slow task log — exchange API timeout
    slow_log_dir = DIRS["logs"] / "trade_reconciliation" / "fetch_exchange_fills" / "2024-01-15T17:00:00+00:00"
    slow_log_dir.mkdir(parents=True, exist_ok=True)
    write(slow_log_dir / "1.log", """\
[2024-01-15 17:00:01,001] INFO  - Starting attempt 1 of 2
[2024-01-15 17:00:01,100] INFO  - Connecting to Exchange A REST API...
[2024-01-15 17:00:01,500] INFO  - Fetching fills since 09:30:00...
[2024-01-15 17:00:05,200] INFO  - Page 1: 500 fills received
[2024-01-15 17:00:10,800] INFO  - Page 2: 500 fills received
[2024-01-15 17:04:22,400] INFO  - Page 3: 500 fills received
[2024-01-15 17:09:10,100] INFO  - Page 4: 500 fills received
[2024-01-15 17:15:05,700] INFO  - Page 5: 500 fills received
[2024-01-15 17:22:01,300] INFO  - Page 6: 312 fills received
[2024-01-15 17:22:01,400] INFO  - Total fills fetched: 2812
[2024-01-15 17:22:01,500] INFO  - Writing to staging table...
[2024-01-15 17:22:03,100] INFO  - Task complete. Duration: 22m 02s
""")

    sla_notes = write(DIRS["data"] / "sla_analysis.md", """\
# SLA Miss Analysis — trade_reconciliation 2024-01-15
======================================================

## Timeline
  17:00:00  DAG scheduled start
  17:22:03  fetch_exchange_fills completes (22 min — should be <5 min)
  17:22:04  match_oms_records starts
  17:30:00  SLA deadline missed (DAG still running)
  17:35:18  DAG completes (35 min total — 5 min over SLA)

## Root Cause: Exchange API Pagination Slowdown
  The exchange REST API returns fills 500 records per page.
  Page 1 took 4s, Page 2 took 5s ... Page 6 took 7m.
  API rate-limiting or server-side slowdown at high-volume end-of-day.

## Options
  1. Parallel fetch: split by symbol groups, fetch concurrently
  2. Use exchange SFTP drop file instead of REST (available at 17:15)
  3. Add per-page timeout, fail fast if page >60s, retry with backoff
  4. Discuss SLA extension with risk team (17:30 → 18:00)

## How to Monitor SLA Misses in Airflow
  UI: Browse → SLA Misses
  CLI: airflow slas find --dag-id trade_reconciliation
  Alert email sent to: ops@firm.com, risk@firm.com (email_on_sla_miss=True)

## Triage Order for Any SLA Miss
  1. Which task was slowest? (check task duration in Grid view)
  2. Is it an external dependency (API, DB, S3)?
  3. Is it consistently slow or spiking today only?
  4. Can we parallelize or cache?
  5. Is the SLA itself realistic?
""")

    print(f"""
{BOLD}── Artifacts ────────────────────────────────────────────{RESET}
{CYAN}  cat "{slow_log_dir}/1.log"          # slow task log
  cat {DIRS["dags"]}/trade_reconciliation.py  # DAG with SLA config
  cat {sla_notes}                              # analysis notes{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Read the slow task log — how long did it take?
{CYAN}       head -3 "{slow_log_dir}/1.log"
       tail -3 "{slow_log_dir}/1.log"{RESET}

  2. Read the SLA analysis
{CYAN}       cat {sla_notes}{RESET}

  3. On real Airflow — find SLA misses:
{CYAN}       # UI: Browse → SLA Misses
       # CLI: airflow slas find --dag-id trade_reconciliation{RESET}

{BOLD}── Key concepts ─────────────────────────────────────────{RESET}
  SLA in Airflow = max time from scheduled start to completion.
  SLA miss does NOT fail the task — it fires an email alert only.
  Task still runs to completion unless execution_timeout is also set.
  execution_timeout DOES kill the task (raises AirflowTaskTimeout).
""")


# ══════════════════════════════════════════════
#  SCENARIO 3 — Pipeline Health Check Script
# ══════════════════════════════════════════════

def launch_scenario_3():
    header("Scenario AF-03 — Write a Pipeline Health Check")
    print("  A mock Airflow REST API is running. Write a Python script\n"
          "  that checks all critical DAGs and reports failures.\n")

    API_PORT = 8766
    pid = spawn(_mock_airflow_api, (API_PORT,), "mock_airflow_api")
    ok(f"Mock Airflow API started on port {API_PORT}  PID={pid}")
    time.sleep(0.5)

    health_check = write(DIRS["scripts"] / "af03_pipeline_health.py", f"""\
#!/usr/bin/env python3
\"\"\"
AF-03 Solution: Airflow pipeline health check script.
Queries the Airflow REST API for failed DAG runs and reports them.
Usage: python3 {DIRS["scripts"]}/af03_pipeline_health.py
\"\"\"
import urllib.request, json
from datetime import datetime

AIRFLOW_URL = "http://127.0.0.1:{API_PORT}/api/v1"

CRITICAL_DAGS = [
    "market_data_ingestion",
    "risk_calculation",
    "trade_reconciliation",
    "pnl_report",
]

def get_dag_runs(dag_id: str, state: str = "failed") -> list:
    url = f"{{AIRFLOW_URL}}/dags/{{dag_id}}/dagRuns?state={{state}}"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read()).get("dag_runs", [])
    except Exception as e:
        print(f"  ⚠ API error for {{dag_id}}: {{e}}")
        return []

def check_pipelines():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\\n[{{ts}}] Checking {{len(CRITICAL_DAGS)}} critical DAGs...\\n")
    alerts = 0
    for dag_id in CRITICAL_DAGS:
        runs = get_dag_runs(dag_id, "failed")
        if runs:
            alerts += 1
            for run in runs:
                start = run.get("start_date", "unknown")[:19]
                print(f"  🔴 FAILED: {{dag_id}}")
                print(f"     Run ID : {{run['dag_run_id']}}")
                print(f"     Started: {{start}}")
                print(f"     State  : {{run['state']}}\\n")
        else:
            print(f"  ✅ OK: {{dag_id}}")
    if alerts == 0:
        print("\\nAll pipelines healthy.")
    else:
        print(f"\\n⚠  {{alerts}} DAG(s) require attention.")

check_pipelines()
""")

    print(f"""
{BOLD}── Mock Airflow API: http://127.0.0.1:{API_PORT}/api/v1 ──────────────{RESET}
  GET /api/v1/dags
  GET /api/v1/dags/<dag_id>/dagRuns?state=failed

{BOLD}── Test with curl ───────────────────────────────────────{RESET}
{CYAN}       curl http://127.0.0.1:{API_PORT}/api/v1/dags
       curl "http://127.0.0.1:{API_PORT}/api/v1/dags/risk_calculation/dagRuns?state=failed"{RESET}

{BOLD}── Run the solution ─────────────────────────────────────{RESET}
{CYAN}       python3 {health_check}{RESET}

{BOLD}── Your Task: write it yourself first ──────────────────{RESET}
  Requirements:
  • Loop over CRITICAL_DAGS list
  • Query /dags/<id>/dagRuns?state=failed
  • Print alert for each failed run with dag_id, run_id, start_date
  • Print ✅ OK for healthy DAGs
  • Summary count at the end

{BOLD}── Key Python APIs ──────────────────────────────────────{RESET}
{CYAN}       import urllib.request, json
       with urllib.request.urlopen(url, timeout=5) as r:
           data = json.loads(r.read()){RESET}
""")


# ══════════════════════════════════════════════
#  SCENARIO 4 — Sensor Never Triggering
# ══════════════════════════════════════════════

def launch_scenario_4():
    header("Scenario AF-04 — Sensor Task Never Triggering")
    print("  risk_calculation DAG's ExternalTaskSensor has been waiting 2 hours.\n")

    write(DIRS["dags"] / "sensor_example.py", """\
\"\"\"
Example DAG showing ExternalTaskSensor configuration.
The sensor waits for 'market_data_ingestion' to complete before
risk_calculation can start.
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.sensors.external_task import ExternalTaskSensor
from airflow.operators.python import PythonOperator

with DAG(
    dag_id="risk_calculation_with_sensor",
    start_date=datetime(2024, 1, 1),
    schedule_interval="5 9 * * *",   # runs at 09:05
    catchup=False,
) as dag:

    # COMMON GOTCHA: execution_date must MATCH between DAGs.
    # market_data_ingestion runs at 09:00 → execution_date = 09:00.
    # risk_calculation runs at 09:05 → execution_date = 09:05.
    # ExternalTaskSensor by default looks for execution_date = 09:05
    # in market_data_ingestion → never finds it → blocks forever.
    # FIX: use execution_delta=timedelta(minutes=5) to look 5min back.

    wait_for_market_data_BROKEN = ExternalTaskSensor(
        task_id="wait_for_market_data_BROKEN",
        external_dag_id="market_data_ingestion",
        external_task_id="validate_data",
        # No execution_delta → looks for 09:05 run of upstream → never exists
        timeout=3600,
        mode="reschedule",
    )

    wait_for_market_data_FIXED = ExternalTaskSensor(
        task_id="wait_for_market_data_FIXED",
        external_dag_id="market_data_ingestion",
        external_task_id="validate_data",
        execution_delta=timedelta(minutes=5),  # upstream ran 5 min earlier
        timeout=3600,
        mode="reschedule",
        poke_interval=60,
    )

    calculate_risk = PythonOperator(
        task_id="calculate_risk",
        python_callable=lambda: print("Risk calculated"),
    )

    wait_for_market_data_FIXED >> calculate_risk
""")

    write(DIRS["scripts"] / "af04_sensor_diagnosis.sh", f"""\
#!/bin/bash
# AF-04: ExternalTaskSensor Diagnosis

echo "=== What ExternalTaskSensor does ==="
echo "  Waits until a specific task in ANOTHER DAG reaches 'success' state"
echo "  for the SAME execution_date."
echo ""
echo "  If upstream DAG execution_date never matches → polls forever until timeout."

echo ""
echo "=== MOST COMMON CAUSE: execution_date mismatch ==="
echo ""
echo "  market_data_ingestion: schedule=09:00 → execution_date=2024-01-15T09:00"
echo "  risk_calculation:      schedule=09:05 → execution_date=2024-01-15T09:05"
echo ""
echo "  ExternalTaskSensor without execution_delta looks for:"
echo "    market_data_ingestion run with execution_date=2024-01-15T09:05"
echo "    → doesn't exist → polls every 60s forever"
echo ""
echo "  FIX: execution_delta=timedelta(minutes=5)"
echo "    → looks for execution_date=2024-01-15T09:00 ← correct!"

echo ""
echo "=== Diagnose on real Airflow ==="
echo "  # Check if upstream DAG actually completed:"
echo "  airflow dags list-runs -d market_data_ingestion \\"
echo "    --start-date 2024-01-15 --end-date 2024-01-16"
echo ""
echo "  # Is upstream DAG paused?"
echo "  airflow dags list | grep market_data_ingestion"
echo "  airflow dags unpause market_data_ingestion"

echo ""
echo "=== Options to unblock WITHOUT fixing upstream ==="
echo ""
echo "  Option A: Manually mark upstream task success in UI"
echo "    → Tree View → click validate_data → Mark Success"
echo "    → Sensor detects success and unblocks"
echo ""
echo "  Option B: Skip the sensor (mark it success manually)"
echo "    → Grid View → click sensor task → Mark Success"
echo ""
echo "  Option C: Set timeout so it fails cleanly (not hangs forever)"
echo "    ExternalTaskSensor(poke_timeout=3600, mode='reschedule')"
echo "    After timeout → task FAILS → triggers email alert"
echo "    → prevents silent hangs"

echo ""
echo "=== DAG with correct sensor config ==="
cat {DIRS["dags"]}/sensor_example.py | grep -A8 "wait_for_market_data_FIXED"
""")

    print(f"""
{BOLD}── Artifacts ────────────────────────────────────────────{RESET}
{CYAN}  cat {DIRS["dags"]}/sensor_example.py          # broken + fixed sensor
  cat {DIRS["scripts"]}/af04_sensor_diagnosis.sh # diagnosis guide{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Read the sensor DAG — spot the broken config
{CYAN}       grep -A8 "BROKEN\|FIXED" {DIRS["dags"]}/sensor_example.py{RESET}

  2. Walk through the diagnosis
{CYAN}       cat {DIRS["scripts"]}/af04_sensor_diagnosis.sh{RESET}

{BOLD}── Root cause ───────────────────────────────────────────{RESET}
  execution_date mismatch — the most common ExternalTaskSensor trap.
  Upstream runs at 09:00, downstream at 09:05.
  Sensor looks for upstream run at 09:05 → never exists → blocks forever.
  Fix: execution_delta=timedelta(minutes=5) or execution_date_fn.

{BOLD}── poke vs reschedule mode ──────────────────────────────{RESET}
  mode="poke":        sensor holds a worker slot while it waits
                      → wastes worker capacity, can starve other tasks
  mode="reschedule":  sensor releases the worker between checks
                      → correct for production, long-running waits
""")


# ══════════════════════════════════════════════
#  SCENARIO 5 — Behavioral Story
# ══════════════════════════════════════════════

def launch_scenario_5():
    header("Scenario AF-05 — Tell Your Airflow / Pipeline Story")
    print("  Prepare: 'How do you monitor and troubleshoot data pipelines?'\n")

    story = write(DIRS["data"] / "af05_story_notes.md", """\
# AF-05: Airflow Behavioral Answer Notes
=========================================

## The Question
"Walk me through how you monitor and troubleshoot data pipelines
in your current role."

## Model Answer

"At Granite Point I monitor a set of production data pipelines that
power our quant trading strategy. These include market data ingestion,
forecasting model runs, and trade reconciliation workflows. A failure
in any of these directly impacts our traders' ability to act on signals.

My monitoring is split between proactive and reactive.

Proactively: I watch Airflow's Grid view for any DAGs that show red
or are running past their SLA window. I also monitor Kafka consumer lag
as an early signal that data isn't flowing through — lag building up
usually means a DAG upstream failed silently.

When a pipeline fails my triage order is:
  1. Which task failed — and what's the exact error in the logs?
     (I always read the full traceback, not just the last line)
  2. Is it a data issue — missing input, schema change, empty file?
     Or an infrastructure issue — DB connection, IAM permission, S3?
  3. Check recent commits and deployments near that pipeline
     — config changes are a common hidden cause
  4. Based on root cause: clear + rerun, fix the data, or escalate
     with a full diagnosis to the dev team

One thing I'm intentional about: I never clear a failed task without
reading the full error first. A blind rerun on a data integrity issue
can corrupt downstream outputs and create a much bigger problem
than the original failure.

This maps directly to 'operate key parts of a sophisticated data
analysis pipeline' — that's what I do every day, just in a trading
context."

## Key Phrases
→ "A failure directly impacts our traders' ability to act on signals"
→ "I never clear a failed task without reading the full error first"
→ "Kafka consumer lag as an early signal"
→ "Blind rerun on a data integrity issue can corrupt downstream outputs"

## Connect to Job Description
JD phrase: "monitor and troubleshoot production jobs"
Your answer: describe your proactive (Airflow UI + Kafka lag) +
             reactive (triage order: logs → root cause → fix) approach
""")

    print(f"""
{BOLD}── Study the model answer ───────────────────────────────{RESET}
{CYAN}       cat {story}{RESET}

{BOLD}── Key phrases to memorise ──────────────────────────────{RESET}
  "A failure directly impacts our traders' ability to act on signals."
  "I never clear a failed task without reading the full error first."
  "Kafka consumer lag as an early signal."
  "Blind rerun on a data issue can corrupt downstream outputs."

{BOLD}── Your triage order (say it out loud) ─────────────────{RESET}
  1. Which task failed + exact error in logs
  2. Data issue or infrastructure issue?
  3. Recent commits / deployments near the pipeline?
  4. Clear + rerun / fix data / escalate with diagnosis
""")


# ══════════════════════════════════════════════
#  TEARDOWN / MAIN
# ══════════════════════════════════════════════

def teardown():
    header("Tearing Down Airflow Lab")
    kill_pids(DIRS["pids"])
    kill_strays(["mock_airflow_api"])
    remove_lab_dir(LAB_ROOT)

def show_status():
    _show_status(DIRS["pids"], "Airflow Lab")

SCENARIO_MAP = {
    1:  (launch_scenario_1, "AF-01  Debug a failed DAG"),
    2:  (launch_scenario_2, "AF-02  SLA miss investigation"),
    3:  (launch_scenario_3, "AF-03  Pipeline health check script"),
    4:  (launch_scenario_4, "AF-04  Sensor task never triggering"),
    5:  (launch_scenario_5, "AF-05  Behavioral — pipeline story"),
    99: (None,               "      ALL scenarios"),
}

def main():
    parser = argparse.ArgumentParser(
        description="Airflow & Pipelines Challenge Lab",
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
        if args.scenario == 99:
            for k, (fn, _) in SCENARIO_MAP.items():
                if k != 99 and fn: fn()
        else:
            fn, _ = SCENARIO_MAP[args.scenario]; fn()
    else:
        header("Airflow & Pipelines Challenge Lab")
        for num, (_, desc) in SCENARIO_MAP.items():
            print(f"    {num:<4} {desc}")
        choice = input("\n  Enter scenario number (or q): ").strip()
        if choice.lower() == "q": return
        try:
            num = int(choice)
            if num == 99:
                for k, (fn, _) in SCENARIO_MAP.items():
                    if k != 99 and fn: fn()
            else:
                fn, _ = SCENARIO_MAP[num]; fn()
        except (KeyError, ValueError):
            print(f"{RED}  Invalid choice{RESET}")

    lab_footer("lab_airflow.py")

if __name__ == "__main__":
    main()
