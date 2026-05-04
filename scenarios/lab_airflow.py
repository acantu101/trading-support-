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
  6   AF-06  Market data ingestion DAG — feed handler → Kafka → HDF5
  7   AF-07  Historical tick replay & data website — on-demand DAG, 3-tier storage
  8   AF-08  End-of-day risk report DAG — ExternalTaskSensor, VaR, limits
  9   AF-09  Regulatory reporting pipeline — FINRA/SEC/CFTC, T+1, retries
  10  AF-10  Airflow best practices — idempotency, sensors, anti-patterns
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
#  SCENARIO 6 — Market Data Ingestion DAG
# ══════════════════════════════════════════════

def launch_scenario_6():
    header("Scenario AF-06 — Market Data Ingestion DAG")
    print("  The full market data pipeline orchestrated by Airflow.")
    print("  Feed handler → Kafka → tick storage → quality checks.\n")

    dag_file = write(DIRS["dags"] / "market_data_ingestion.py", """\
\"\"\"
Market Data Ingestion DAG
=========================
Orchestrates the daily market data pipeline:
  1. Validate feed handler is alive and publishing to Kafka
  2. Confirm Kafka consumer lag is below threshold (ticks flowing)
  3. Trigger tick storage job (Kafka → HDF5/TimescaleDB)
  4. Run data quality checks (gaps, crossed books, coverage)
  5. Update the tick replay index (powers the data replay website)
  6. Alert if any symbol is missing data for the session

Schedule: runs at 16:15 (after market close at 16:00)
SLA: must complete by 17:00 (before EOD risk report starts)
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.bash import BashOperator
from airflow.sensors.external_task import ExternalTaskSensor

default_args = {
    "owner":            "market-data-team",
    "retries":          2,
    "retry_delay":      timedelta(minutes=3),
    "email_on_failure": True,
    "email_on_retry":   False,
    "email":            ["market-data-oncall@firm.com", "ops@firm.com"],
    "sla":              timedelta(minutes=45),   # must finish by 17:00
}

with DAG(
    dag_id="market_data_ingestion",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="15 16 * * 1-5",   # weekdays only, 16:15
    catchup=False,
    tags=["market-data", "production", "critical"],
) as dag:

    # ── Task 1: Check feed handler health ─────────────────────────────────
    check_feed_handler = PythonOperator(
        task_id="check_feed_handler",
        python_callable=lambda: None,   # checks PID, last heartbeat timestamp
        doc_md="""
        Verify the feed handler process is alive and has published
        ticks within the last 60 seconds. If stale, alert immediately —
        the rest of the pipeline will have no data to process.
        """,
    )

    # ── Task 2: Validate Kafka lag ────────────────────────────────────────
    validate_kafka_lag = PythonOperator(
        task_id="validate_kafka_lag",
        python_callable=lambda: None,
        doc_md="""
        Query Kafka for tick-storage-group consumer lag on market-data.ticks.
        Threshold: lag < 10,000 (approx 50 seconds at 200 ticks/sec).
        If lag > threshold: tick storage is behind → incomplete data for EOD.
        """,
    )

    # ── Task 3: Run tick storage job ──────────────────────────────────────
    run_tick_storage = BashOperator(
        task_id="run_tick_storage",
        bash_command="python3 /opt/pipelines/tick_storage_pipeline.py --date {{ ds }}",
        doc_md="""
        Reads remaining ticks from Kafka market-data.ticks topic and
        writes to HDF5 files partitioned by symbol and date.
        Output: /data/ticks/{{ ds }}/AAPL.h5, MSFT.h5, etc.
        Idempotent: uses UPSERT by (symbol, timestamp) — safe to rerun.
        """,
    )

    # ── Task 4: Data quality checks ───────────────────────────────────────
    run_quality_checks = PythonOperator(
        task_id="run_quality_checks",
        python_callable=lambda: None,
        doc_md="""
        For each symbol, verify:
          - Tick count > 0 (data arrived at all)
          - No sequence gaps > 100 messages (feed gaps)
          - No crossed books in stored data
          - Price range within ± 20% of previous close (sanity check)
          - Coverage: data exists for all scheduled trading hours
        Failures here go to DLQ and alert; do NOT block downstream.
        """,
    )

    # ── Task 5: Update replay index ───────────────────────────────────────
    update_replay_index = PythonOperator(
        task_id="update_replay_index",
        python_callable=lambda: None,
        doc_md="""
        Updates the PostgreSQL replay index table used by the
        data replay website. For each symbol + date:
          INSERT INTO replay_index (symbol, date, hdf5_path, tick_count,
            first_ts, last_ts, quality_status)
        Powers the symbol search and availability check on the website.
        """,
    )

    # ── Task 6: Alert on missing symbols ──────────────────────────────────
    check_symbol_coverage = PythonOperator(
        task_id="check_symbol_coverage",
        python_callable=lambda: None,
        doc_md="""
        Compare ticks received against the expected symbol universe.
        Alert if any S&P 500 constituent has zero ticks for the session.
        Common causes: exchange halted trading, feed subscription lapsed,
        symbol delisted (check corporate actions calendar).
        """,
    )

    # ── DAG dependencies ──────────────────────────────────────────────────
    check_feed_handler >> validate_kafka_lag >> run_tick_storage
    run_tick_storage >> [run_quality_checks, update_replay_index]
    run_quality_checks >> check_symbol_coverage
""")

    notes = write(DIRS["data"] / "af06_pipeline_notes.md", """\
# Market Data Ingestion DAG — Operations Notes
================================================

## Triage Order When DAG Fails

1. check_feed_handler fails
   → Feed handler process is down or stale
   → Check PID: pgrep -la feed_handler
   → Check last log: tail -f /var/log/market-data/feed_handler.log
   → Restart feed handler, then clear task and rerun

2. validate_kafka_lag fails
   → tick-storage-group is behind (lag > threshold)
   → Check: kafka-consumer-groups.sh --group tick-storage-group --describe
   → If lag is growing: tick storage process may be down or slow
   → Scale up tick storage consumers, then rerun

3. run_tick_storage fails
   → Check task log for: disk full, DB connection, schema error
   → Disk: df -h /data/ticks
   → DB: psql -c "SELECT 1" — connection test
   → Rerun is safe — pipeline is idempotent (UPSERT)

4. run_quality_checks fails
   → Data arrived but has quality issues
   → Check quality report: cat /data/quality/{{ date }}_report.json
   → DOES NOT block downstream unless configured to
   → Alert market-data team, investigate root cause

5. update_replay_index fails
   → Tick data is stored but replay website won't find it
   → Check DB: psql -c "SELECT COUNT(*) FROM replay_index WHERE date='{{ date }}'"
   → Fix: clear task, rerun — idempotent INSERT OR REPLACE

## Key Idempotency Rules
  - run_tick_storage: UPSERT by (symbol, timestamp) — safe to rerun N times
  - update_replay_index: INSERT OR REPLACE — safe to rerun
  - run_quality_checks: deletes old report then rewrites — safe to rerun
  - NEVER: append-only writes without deduplication → rerun = duplicate data

## Backfill Strategy
  When a past date is missing:
    airflow dags backfill market_data_ingestion \\
      --start-date 2024-01-10 --end-date 2024-01-15
  Backfill replays ticks from Kafka (if within retention window: 1 hour)
  OR from archive storage (S3/GCS cold storage for older dates)

## Monitoring
  - SLA alert if not complete by 17:00
  - Kafka lag dashboard: Grafana → market-data-consumer-lag
  - Quality report emailed to market-data-team@firm.com daily
  - Replay index health: SELECT date, COUNT(*) FROM replay_index GROUP BY date
""")

    print(f"""
{BOLD}── DAG file ─────────────────────────────────────────────{RESET}
{CYAN}       cat {dag_file}{RESET}

{BOLD}── Operations notes ─────────────────────────────────────{RESET}
{CYAN}       cat {notes}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Trace the DAG dependency chain
{CYAN}       grep ">>" {dag_file}{RESET}

  2. Find which task is the SLA gate (blocks EOD risk report)
{CYAN}       grep "sla\|SLA" {dag_file}{RESET}

  3. Given this error — which task failed and what's the fix?
     "botocore.exceptions.NoCredentialsError: Unable to locate credentials"
{CYAN}       # Answer: check_feed_handler or run_tick_storage
       # Fix: IAM role on worker node is missing S3 permissions
       # Same as AF-01 pattern — read full traceback first{RESET}

{BOLD}── Best Practices in this DAG ─────────────────────────{RESET}
  • doc_md on every task → team knows what each task does without reading code
  • Idempotent tasks → safe to clear + rerun without data corruption
  • SLA configured → alert fires before EOD risk report starts
  • Weekdays only (1-5) → no weekend runs for equity market pipelines
  • Retries=2 with delay → handles transient failures without paging
  • Parallel branches → quality checks and replay index update in parallel
""")


# ══════════════════════════════════════════════
#  SCENARIO 7 — Historical Tick Replay Pipeline
# ══════════════════════════════════════════════

def launch_scenario_7():
    header("Scenario AF-07 — Historical Tick Replay & Data Website")
    print("  The data replay website lets users search a symbol and")
    print("  replay tick data going back 10 years. You support it.\n")

    # Simulate the replay index database
    import json as _json
    replay_index = DIRS["data"] / "replay_index.json"
    index_entries = []
    symbols = ["AAPL", "MSFT", "GOOG", "AMZN", "SPY", "TSLA"]
    from datetime import date as dt_date
    base = datetime(2024, 1, 15)
    for i in range(30):
        d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
        for sym in symbols:
            if i % 7 in (5, 6):   # no weekend data
                continue
            index_entries.append({
                "symbol":   sym,
                "date":     d,
                "hdf5_path": f"/data/ticks/{d}/{sym}.h5",
                "tick_count": 18000 + (i * 100) % 5000,
                "first_ts": f"{d}T09:30:00",
                "last_ts":  f"{d}T16:00:00",
                "quality":  "GOOD" if i != 7 else "DEGRADED",   # one bad day
            })
    replay_index.write_text(_json.dumps(index_entries, indent=2))
    ok(f"Replay index ({len(index_entries)} entries): {replay_index}")

    # The replay DAG
    replay_dag = write(DIRS["dags"] / "tick_replay.py", """\
\"\"\"
Tick Replay DAG
===============
Triggered by the data replay website when a user requests historical ticks.
Searches the tick store (HDF5 / S3 archive), assembles the result set,
and writes to a temp location the website reads.

Triggered via Airflow REST API:
  POST /api/v1/dags/tick_replay/dagRuns
  {
    "conf": {
      "symbol":     "AAPL",
      "start_date": "2015-01-01",
      "end_date":   "2015-01-31",
      "requestor":  "user@firm.com"
    }
  }
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator

default_args = {
    "owner":            "platform-team",
    "retries":          1,
    "retry_delay":      timedelta(minutes=1),
    "email_on_failure": True,
}

with DAG(
    dag_id="tick_replay",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval=None,       # triggered on-demand ONLY, never scheduled
    catchup=False,
    max_active_runs=10,           # allow 10 concurrent user requests
    tags=["replay", "on-demand"],
) as dag:

    # ── Step 1: Validate request ───────────────────────────────────────────
    validate_request = ShortCircuitOperator(
        task_id="validate_request",
        python_callable=lambda **ctx: True,   # checks symbol in universe, date range valid
        doc_md="""
        Validates: symbol is in the known universe, dates are within 10-year window,
        end_date > start_date, not a future date.
        ShortCircuitOperator: if validation fails → skips ALL downstream tasks cleanly.
        """,
    )

    # ── Step 2: Check replay index ────────────────────────────────────────
    check_availability = PythonOperator(
        task_id="check_availability",
        python_callable=lambda **ctx: None,
        doc_md="""
        Queries replay_index table in PostgreSQL.
        Identifies which dates in the range have data (GOOD/DEGRADED/MISSING).
        Writes availability report to DAG conf output so user sees data gaps.
        """,
    )

    # ── Step 3: Fetch from hot/cold storage ───────────────────────────────
    fetch_ticks = PythonOperator(
        task_id="fetch_ticks",
        python_callable=lambda **ctx: None,
        doc_md="""
        HOT  storage (< 90 days):  read directly from HDF5 on local disk
        WARM storage (90d - 2yr):  read from S3 Parquet (boto3, ~2-5s per file)
        COLD storage (2yr - 10yr): read from S3 Glacier (restore first, 1-5min delay)

        For cold storage: triggers a restore job and returns a 'pending' status.
        Website polls /api/v1/dags/tick_replay/dagRuns/{run_id} for completion.
        """,
    )

    # ── Step 4: Assemble and write output ─────────────────────────────────
    write_output = PythonOperator(
        task_id="write_output",
        python_callable=lambda **ctx: None,
        doc_md="""
        Concatenates tick files, applies filters (time range within day),
        writes to /tmp/replay/{run_id}.csv or .parquet.
        Also writes metadata: symbol, date_range, tick_count, quality_flags.
        TTL: output deleted after 24 hours (cron cleanup job).
        """,
    )

    # ── Step 5: Notify user ───────────────────────────────────────────────
    notify_requestor = PythonOperator(
        task_id="notify_requestor",
        python_callable=lambda **ctx: None,
        doc_md="""
        Sends email/Slack to requestor with download link.
        Link: https://replay.firm.com/download/{run_id}
        """,
    )

    validate_request >> check_availability >> fetch_ticks >> write_output >> notify_requestor
""")

    # Troubleshooting guide for the replay website
    replay_guide = write(DIRS["data"] / "af07_replay_troubleshooting.md", """\
# Data Replay Website — Support Troubleshooting Guide
======================================================

## Architecture
  User enters: symbol=AAPL, start=2015-01-01, end=2015-01-31
      ↓
  Website (Flask/Django) → POST /api/v1/dags/tick_replay/dagRuns
      ↓
  Airflow triggers tick_replay DAG with conf={symbol, start_date, end_date}
      ↓
  DAG: validate → check_availability → fetch_ticks → write_output → notify
      ↓
  Website polls DAG run status → shows progress
      ↓
  User downloads /tmp/replay/{run_id}.csv

## Common Issues and Fixes

ISSUE: "No data found for AAPL 2015-01-05"
  Cause 1: Market was closed (holiday) → expected, not a bug
  Cause 2: Data never ingested → market_data_ingestion DAG failed that day
  Diagnosis:
    SELECT * FROM replay_index WHERE symbol='AAPL' AND date='2015-01-05';
    airflow dags list-runs -d market_data_ingestion --start-date 2015-01-05
  Fix: backfill from S3 archive if data exists there

ISSUE: "Request is taking very long" (>5 minutes)
  Cause 1: Cold storage restore (S3 Glacier, 1-5 min per file)
    → expected for data older than 2 years
    → website should show "Restoring from cold storage... (estimated 3 min)"
  Cause 2: Large date range + high-volume symbol (AAPL 10yr = ~45M ticks)
    → fetch_ticks task is reading and concatenating many files
    → check task log for slow progress
  Fix: add progress logging, show estimated completion on website

ISSUE: "Data looks wrong / prices seem off"
  Cause 1: Corporate action not applied (split, dividend)
    AAPL 7:1 split in 2014 → pre-split prices appear 7x higher
    Fix: replay pipeline should apply split adjustment factors
  Cause 2: quality=DEGRADED in replay_index for that date
    SELECT quality, tick_count FROM replay_index WHERE symbol='AAPL' AND date='2015-01-05'
  Fix: investigate original feed data, re-ingest if source data exists

ISSUE: "Replay DAG failed — check_availability task error"
  Cause: replay_index table is missing entries (market_data_ingestion never ran)
  Diagnosis: SELECT COUNT(*) FROM replay_index WHERE date='2015-01-05'
  Fix: run market_data_ingestion backfill, then replay request will succeed

ISSUE: Too many concurrent replay requests slowing the system
  Check: airflow dags list-runs -d tick_replay --state running
  Throttle: max_active_runs=10 in DAG config limits concurrent requests
  Fix: increase worker count or add queue priority for replay tasks

## Storage Tiers and Latency

  Tier        | Age         | Storage      | Fetch time
  ------------|-------------|--------------|------------
  HOT         | < 90 days   | Local HDF5   | < 1 second
  WARM        | 90d - 2yr   | S3 Parquet   | 2-10 seconds
  COLD        | 2yr - 10yr  | S3 Glacier   | 1-5 minutes (restore)
  VERY COLD   | > 10yr      | Tape/Glacier | Hours (request needed)

## Replay Index Query Examples
  -- What dates are available for AAPL?
  SELECT date, tick_count, quality FROM replay_index
  WHERE symbol='AAPL' ORDER BY date DESC LIMIT 10;

  -- Find all dates with DEGRADED data quality
  SELECT symbol, date, tick_count FROM replay_index
  WHERE quality='DEGRADED' ORDER BY date DESC;

  -- Check if a specific date has full coverage
  SELECT COUNT(DISTINCT symbol) FROM replay_index
  WHERE date='2024-01-15' AND quality='GOOD';
""")

    print(f"""
{BOLD}── DAG file ─────────────────────────────────────────────{RESET}
{CYAN}       cat {replay_dag}{RESET}

{BOLD}── Replay index (simulated DB) ─────────────────────────{RESET}
{CYAN}       python3 -c "import json; data=json.load(open('{replay_index}')); \\
           [print(d['symbol'], d['date'], d['tick_count'], d['quality']) \\
            for d in data[:10]]"{RESET}

{BOLD}── Troubleshooting guide ────────────────────────────────{RESET}
{CYAN}       cat {replay_guide}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Find all DEGRADED quality dates in the index
{CYAN}       python3 -c "import json; \\
           [print(d) for d in json.load(open('{replay_index}')) \\
            if d['quality']!='GOOD']"{RESET}

  2. A user reports "no data for AAPL 2015-01-05" — walk through your triage
{CYAN}       cat {replay_guide} | grep -A8 "No data found"{RESET}

{BOLD}── Key Interview Points ───────────────────────────────{RESET}
  • schedule_interval=None → DAG is triggered on-demand by the website, never scheduled
  • ShortCircuitOperator → skips downstream cleanly on validation failure
  • max_active_runs=10 → rate-limit concurrent user requests
  • Storage tiering: hot/warm/cold determines fetch latency
  • Corporate action adjustments → pre-split prices need adj factor applied
  • Replay index = metadata table that powers the search/availability UI
""")


# ══════════════════════════════════════════════
#  SCENARIO 8 — End-of-Day Risk Report DAG
# ══════════════════════════════════════════════

def launch_scenario_8():
    header("Scenario AF-08 — End-of-Day Risk Report DAG")
    print("  Generates daily P&L, VaR, and position report after market close.")
    print("  Depends on market data ingestion completing first.\n")

    risk_dag = write(DIRS["dags"] / "eod_risk_report.py", """\
\"\"\"
End-of-Day Risk Report DAG
==========================
Runs after market close and after market_data_ingestion completes.
Generates: P&L report, VaR, Greeks, position summary, limit utilization.
Must complete by 17:30 for risk manager review before US close.
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor

default_args = {
    "owner":            "risk-team",
    "retries":          1,
    "retry_delay":      timedelta(minutes=5),
    "email_on_failure": True,
    "email":            ["risk-manager@firm.com", "risk-oncall@firm.com"],
    "sla":              timedelta(minutes=30),   # complete by 17:30
}

with DAG(
    dag_id="eod_risk_report",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 17 * * 1-5",    # 17:00 weekdays
    catchup=False,
    tags=["risk", "eod", "critical"],
) as dag:

    # Gate: wait for market data to be fully ingested
    wait_for_market_data = ExternalTaskSensor(
        task_id="wait_for_market_data",
        external_dag_id="market_data_ingestion",
        external_task_id="update_replay_index",   # final task of that DAG
        execution_delta=timedelta(minutes=45),     # market_data_ingestion runs at 16:15
        timeout=3600,
        mode="reschedule",
        poke_interval=60,
        doc_md="Blocks until market_data_ingestion has completed for today.",
    )

    # Load all positions from OMS/trade DB
    load_positions = PythonOperator(
        task_id="load_positions",
        python_callable=lambda **ctx: None,
        doc_md="Load all open positions for the trading date from the OMS database.",
    )

    # Apply today's closing prices to positions
    mark_to_market = PythonOperator(
        task_id="mark_to_market",
        python_callable=lambda **ctx: None,
        doc_md="""
        Apply EOD closing prices from market data store to all positions.
        P&L = (close_price - avg_entry_price) * quantity * direction
        Writes MTM P&L per position to risk_pnl table.
        """,
    )

    # Calculate Value-at-Risk
    calculate_var = PythonOperator(
        task_id="calculate_var",
        python_callable=lambda **ctx: None,
        doc_md="""
        Historical simulation VaR using 10yr daily returns (from HDF5 tick store).
        VaR(95%, 1-day) = loss exceeded in 5% of historical scenarios.
        VaR(99%, 10-day) = regulatory capital requirement metric.
        """,
    )

    # Check limit utilization
    check_limits = PythonOperator(
        task_id="check_limits",
        python_callable=lambda **ctx: None,
        doc_md="""
        Compare P&L and VaR against trader/desk/firm limits.
        BREACH: position_pnl < -limit → alert risk manager immediately.
        WARN:   position_pnl < -0.8 * limit → yellow flag.
        Results written to limit_utilization table.
        """,
    )

    # Generate the PDF/HTML report
    generate_report = PythonOperator(
        task_id="generate_report",
        python_callable=lambda **ctx: None,
        doc_md="""
        Assembles P&L, VaR, Greeks, limit utilization into a report.
        Output: /reports/risk/{{ ds }}/eod_risk_report.pdf
        Also writes JSON to reports API for web dashboard.
        """,
    )

    # Distribute report
    distribute_report = PythonOperator(
        task_id="distribute_report",
        python_callable=lambda **ctx: None,
        doc_md="""
        Emails report to risk managers, senior traders, compliance.
        Posts summary to #risk-reports Slack channel.
        Uploads to SharePoint for regulatory records retention.
        """,
    )

    # DAG flow
    wait_for_market_data >> load_positions >> mark_to_market
    mark_to_market >> [calculate_var, check_limits]
    [calculate_var, check_limits] >> generate_report >> distribute_report
""")

    # Realistic failure log for this DAG
    fail_log_dir = DIRS["logs"] / "eod_risk_report" / "calculate_var" / "2024-01-15T17:00:00+00:00"
    fail_log_dir.mkdir(parents=True, exist_ok=True)
    write(fail_log_dir / "1.log", """\
[2024-01-15 17:21:01,001] INFO  - Starting VaR calculation
[2024-01-15 17:21:01,100] INFO  - Loading 10yr historical returns from HDF5...
[2024-01-15 17:21:03,200] INFO  - Loaded 2,520 trading days of data
[2024-01-15 17:21:03,201] INFO  - Running historical simulation for 847 positions...
[2024-01-15 17:21:15,400] INFO  - Scenario simulation complete (10,000 scenarios)
[2024-01-15 17:21:15,500] INFO  - Fetching AAPL options Greeks from pricing service...
[2024-01-15 17:21:15,600] ERROR - ConnectionRefusedError: [Errno 111] Connection refused
[2024-01-15 17:21:15,601] ERROR - Failed to connect to pricing service at pricing-svc:8080
[2024-01-15 17:21:15,602] INFO  - Retrying in 30s (attempt 1/3)
[2024-01-15 17:21:46,700] ERROR - ConnectionRefusedError: pricing-svc:8080 still down
[2024-01-15 17:22:17,800] ERROR - All retries exhausted. VaR calculation incomplete.
[2024-01-15 17:22:17,900] ERROR - Task failed with exception: ConnectionRefusedError
""")

    notes = write(DIRS["data"] / "af08_risk_dag_notes.md", """\
# EOD Risk Report DAG — Operations Notes
==========================================

## Task Dependency Rationale
  wait_for_market_data → ensures we use today's closing prices, not yesterday's
  load_positions before mark_to_market → can't MTM without knowing what we hold
  calculate_var + check_limits in PARALLEL → independent, no ordering needed
  generate_report AFTER both → needs VaR and limit breach data to be complete

## Common Failures

1. wait_for_market_data times out (sensor waiting >60 min)
   Cause: market_data_ingestion DAG failed or is still running
   Fix: check market_data_ingestion DAG run status first
        airflow dags list-runs -d market_data_ingestion --start-date {{ date }}
   Do NOT manually mark sensor success — the prices may not be ready yet

2. mark_to_market fails
   Cause A: OMS database connection refused
     → Check: psql -h oms-db -c "SELECT 1"
     → Fix: restart DB connection pool, rerun task
   Cause B: Missing price for a symbol
     → quality=MISSING in replay_index for that symbol/date
     → Fix: use previous close as fallback (with flag), alert market-data team

3. calculate_var fails (pricing service down — see log above)
   Cause: options pricing microservice at pricing-svc:8080 is down
   Fix: restart pricing service, then clear + rerun calculate_var
   Impact: VaR incomplete → generate_report blocked → report delayed
   Escalate if pricing service cannot restart within 15 min of SLA deadline

4. SLA miss (not complete by 17:30)
   Impact: risk managers don't have EOD numbers for senior trader meeting
   Triage: which task is slowest? (Grid view → task duration)
   Common culprit: calculate_var (historical simulation scales with portfolio size)

## Idempotency
  load_positions: read-only — always safe to rerun
  mark_to_market: writes to risk_pnl — uses UPSERT by (date, position_id)
  calculate_var:  writes to var_results — uses UPSERT by (date, calc_method)
  generate_report: overwrites /reports/risk/{{ date }}/eod_risk_report.pdf
  All tasks safe to clear + rerun

## The VaR Calculation Uses Historical Tick Data
  calculate_var reads 10yr of daily returns from the HDF5 tick store
  If market_data_ingestion was degraded → VaR uses incomplete price history
  quality=DEGRADED in replay_index → VaR results are flagged with a warning
  This is why market data quality directly affects risk accuracy
""")

    print(f"""
{BOLD}── DAG file ─────────────────────────────────────────────{RESET}
{CYAN}       cat {risk_dag}{RESET}

{BOLD}── Failure log (pricing service down) ──────────────────{RESET}
{CYAN}       cat "{fail_log_dir}/1.log"{RESET}

{BOLD}── Operations notes ─────────────────────────────────────{RESET}
{CYAN}       cat {notes}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Trace the full dependency chain including the external sensor
{CYAN}       grep ">>\|ExternalTask" {risk_dag}{RESET}

  2. From the failure log — what failed and what's the fix?
{CYAN}       grep "ERROR\|ConnectionRefused" "{fail_log_dir}/1.log"{RESET}

  3. Which two tasks run in parallel and why?
{CYAN}       grep "calculate_var\|check_limits" {risk_dag} | grep ">>"
       # Answer: independent — no data dependency between them{RESET}

{BOLD}── Key Interview Points ───────────────────────────────{RESET}
  • ExternalTaskSensor: gate on market_data_ingestion BEFORE running VaR
  • Parallel branches: calculate_var + check_limits have no dependency → run together
  • VaR uses 10yr historical tick data → market data quality directly affects risk
  • execution_delta in sensor: market_data runs at 16:15, risk at 17:00 → 45min delta
  • SLA=30min → must complete by 17:30 → page risk manager if breached
""")


# ══════════════════════════════════════════════
#  SCENARIO 9 — Regulatory Reporting DAG
# ══════════════════════════════════════════════

def launch_scenario_9():
    header("Scenario AF-09 — Regulatory Reporting Pipeline")
    print("  Trade reporting to regulators (FINRA, MiFID II, SEC).")
    print("  Strict deadlines — a missed submission is a regulatory breach.\n")

    reg_dag = write(DIRS["dags"] / "regulatory_reporting.py", """\
\"\"\"
Regulatory Reporting DAG
=========================
Prepares and submits daily trade reports to regulators.
Missing a submission deadline is a regulatory breach — treat this DAG
as the highest-priority production pipeline.

Reporting deadlines (US equities):
  FINRA TRACE: T+1 by 08:00 ET (bond trades)
  SEC CAT:     T+1 by 08:00 ET (equity/options trades)
  CFTC:        T+1 by 09:00 ET (futures/swaps)

SLA: DAG must complete by 07:30 to leave buffer before T+1 deadlines.
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator, BranchPythonOperator
from airflow.operators.dummy import DummyOperator

default_args = {
    "owner":            "compliance-team",
    "retries":          3,               # higher retries — submission MUST succeed
    "retry_delay":      timedelta(minutes=2),
    "email_on_failure": True,
    "email_on_retry":   True,            # notify on retry too — regulatory context
    "email":            ["compliance@firm.com", "legal@firm.com", "cto@firm.com"],
    "sla":              timedelta(hours=7, minutes=30),  # complete by 07:30 T+1
}

with DAG(
    dag_id="regulatory_reporting",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 5 * * 2-6",   # T+1: run at 05:00 Tuesday-Saturday
    catchup=False,
    tags=["regulatory", "compliance", "critical"],
) as dag:

    # ── Step 1: Fetch all fills for trade date ─────────────────────────────
    extract_trades = PythonOperator(
        task_id="extract_trades",
        python_callable=lambda **ctx: None,
        doc_md="""
        Pulls all FILLED orders from OMS for execution_date (T-1).
        Includes: symbol, qty, price, side, trader, account, venue, timestamp.
        Writes to staging table: reg_reporting_staging.
        """,
    )

    # ── Step 2: Validate completeness ─────────────────────────────────────
    validate_completeness = PythonOperator(
        task_id="validate_completeness",
        python_callable=lambda **ctx: None,
        doc_md="""
        Checks that all expected trade records are present.
        Compares against OMS trade count for that date.
        Validates required fields: no null account IDs, valid symbols,
        prices within reasonable range (vs EOD market data).
        Fails hard if count mismatch > 0 — better to fail than submit wrong data.
        """,
    )

    # ── Step 3: Apply regulatory format transformations ───────────────────
    format_finra = PythonOperator(
        task_id="format_finra",
        python_callable=lambda **ctx: None,
        doc_md="Transform trades into FINRA TRACE submission format (FIX-based).",
    )

    format_sec_cat = PythonOperator(
        task_id="format_sec_cat",
        python_callable=lambda **ctx: None,
        doc_md="Transform trades into SEC CAT (Consolidated Audit Trail) JSON format.",
    )

    format_cftc = PythonOperator(
        task_id="format_cftc",
        python_callable=lambda **ctx: None,
        doc_md="Transform futures/swaps into CFTC swap data repository format.",
    )

    # ── Step 4: Submit to regulators (parallel) ───────────────────────────
    submit_finra = PythonOperator(
        task_id="submit_finra",
        python_callable=lambda **ctx: None,
        doc_md="""
        Submits TRACE file to FINRA via SFTP.
        Records submission timestamp and confirmation ID.
        """,
    )

    submit_sec_cat = PythonOperator(
        task_id="submit_sec_cat",
        python_callable=lambda **ctx: None,
        doc_md="Submits CAT file to FINRA CAT reporting facility via REST API.",
    )

    submit_cftc = PythonOperator(
        task_id="submit_cftc",
        python_callable=lambda **ctx: None,
        doc_md="Submits swap data to DTCC SDR via SFTP.",
    )

    # ── Step 5: Confirm acknowledgements ─────────────────────────────────
    confirm_acks = PythonOperator(
        task_id="confirm_acks",
        python_callable=lambda **ctx: None,
        doc_md="""
        Polls regulator endpoints for submission acknowledgements.
        Fails if any submission is rejected or no ACK received within 30 min.
        Rejection → immediate page to compliance and legal.
        """,
    )

    # ── Step 6: Archive and audit trail ───────────────────────────────────
    archive_submission = PythonOperator(
        task_id="archive_submission",
        python_callable=lambda **ctx: None,
        doc_md="""
        Archives submission files, ACK IDs, and timestamps to S3.
        Retention: 7 years (SEC Rule 17a-4).
        Updates reg_submission_log table for compliance dashboard.
        """,
    )

    # ── DAG flow ──────────────────────────────────────────────────────────
    extract_trades >> validate_completeness
    validate_completeness >> [format_finra, format_sec_cat, format_cftc]
    format_finra   >> submit_finra
    format_sec_cat >> submit_sec_cat
    format_cftc    >> submit_cftc
    [submit_finra, submit_sec_cat, submit_cftc] >> confirm_acks >> archive_submission
""")

    notes = write(DIRS["data"] / "af09_regulatory_notes.md", """\
# Regulatory Reporting DAG — Critical Operations Notes
=======================================================

## Why This DAG Is Different From All Others
  A missed submission = regulatory breach = fines + investigation.
  Rule: NEVER skip, silence, or manually mark-success any task in this DAG
  without compliance team sign-off.

  Retries=3 (not 2): we try harder here than anywhere else.
  email_on_retry=True: compliance is notified on every retry, not just failure.
  SLA=07:30: 30-minute buffer before T+1 deadlines — allows manual intervention.

## Escalation Path (DO NOT DEVIATE)
  1. Any task fails after all retries → page compliance@firm.com immediately
  2. If cannot fix by 07:00 → compliance team notifies regulator proactively
     (proactive notification = much better outcome than missed deadline)
  3. Document EVERYTHING: what failed, when, what was tried, outcome
  4. Post-incident: root cause + controls review required within 5 business days

## Common Failures

1. validate_completeness fails — trade count mismatch
   Cause: OMS DB replication lag (read replica behind primary by N minutes)
   Fix: query primary DB, not replica, for regulatory extracts
   Do NOT skip validation — submitting wrong trade count is worse than being late

2. submit_finra fails — SFTP connection refused
   Cause: FINRA SFTP endpoint IP changed (they notify in advance)
   Check: FINRA technical alerts email (compliance team receives these)
   Fix: update SFTP host config, then clear + rerun submit_finra
   Timeline: you have ~2 hours before deadline if you catch it at 05:00

3. confirm_acks fails — rejection received
   Most critical failure: our submission was REJECTED by the regulator
   Cause: format error in submission file, wrong field, missing required value
   Action: page compliance immediately, do NOT auto-resubmit
   Fix: compliance reviews rejection code, corrects format, resubmits manually

4. DAG fails at 05:00 and cannot be fixed by 07:00
   → compliance team sends voluntary disclosure to regulator
   → much better than a missed deadline without notification
   → always prefer transparency with regulators over silence

## Data Quality → Regulatory Accuracy
  Bad market data (stale/gapped) → wrong price validation in validate_completeness
  If a fill price deviates significantly from EOD price: flagged for review
  This is why market_data_ingestion quality directly affects compliance

## Retention Requirements
  SEC Rule 17a-4: 7-year retention for trade records
  Submissions archived to S3 with immutable object lock enabled
  Never delete files from the reg-archive bucket without legal approval
""")

    print(f"""
{BOLD}── DAG file ─────────────────────────────────────────────{RESET}
{CYAN}       cat {reg_dag}{RESET}

{BOLD}── Critical operations notes ────────────────────────────{RESET}
{CYAN}       cat {notes}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Identify which tasks run in parallel and why
{CYAN}       grep ">>" {reg_dag}
       # format + submit steps are parallel — independent per regulator{RESET}

  2. Why retries=3 here vs retries=2 elsewhere?
{CYAN}       grep "retries" {reg_dag}
       # Answer: missing a deadline is a regulatory breach — we retry harder{RESET}

  3. Given this error: "SFTP connection refused at finra-sftp.finra.org"
     Walk through your response
{CYAN}       cat {notes} | grep -A8 "submit_finra fails"{RESET}

{BOLD}── Key Interview Points ───────────────────────────────{RESET}
  • schedule_interval="0 5 * * 2-6" → T+1: runs next morning (Tuesday-Saturday)
  • Parallel format + submit: FINRA/SEC/CFTC are independent → no need to serialize
  • validate_completeness fails hard: better late than wrong submission
  • Proactive regulator notification > missed deadline without notice
  • 7-year retention → S3 with object lock (immutable, cannot be deleted)
  • This DAG should NEVER be marked success manually without compliance sign-off
""")


# ══════════════════════════════════════════════
#  SCENARIO 10 — Airflow Best Practices
# ══════════════════════════════════════════════

def launch_scenario_10():
    header("Scenario AF-10 — Airflow Best Practices for Trading Pipelines")
    print("  Patterns, anti-patterns, and gotchas for production trading DAGs.\n")

    best_practices = write(DIRS["data"] / "af10_best_practices.md", """\
# Airflow Best Practices — Trading & Market Data Pipelines
===========================================================

## DAG Design

ALWAYS idempotent tasks
  A task that can be rerun without causing duplicate data or side effects.
  Use UPSERT (INSERT OR REPLACE / ON CONFLICT DO UPDATE) for DB writes.
  Use overwrite for file outputs (/reports/{{ ds }}/report.pdf overwrites itself).
  Test: "If I clear this task and rerun it 3 times, is the output the same?"

Keep tasks small and focused
  One task = one unit of work. Don't put the whole pipeline in one PythonOperator.
  Small tasks = faster failure detection, cleaner retries, better observability.

No business logic in DAG file scope
  Code at DAG file scope runs every 30 seconds (scheduler heartbeat parses all DAGs).
  WRONG:  df = pd.read_csv("huge_file.csv")  # at module level → runs constantly
  RIGHT:  put all logic inside the python_callable function

Use {{ ds }} template variable for dates
  {{ ds }} = execution_date as YYYY-MM-DD → safe for backfill and reruns
  Hardcoding datetime.now() in a task = broken backfills

doc_md on every task
  Critical for a trading firm: ops team needs to know what each task does
  without reading the full source code. Write it like a runbook entry.

## Scheduling

schedule_interval="0 9 * * 1-5"  ← weekdays only for equity market pipelines
catchup=False                     ← don't run missed historical runs on restart
max_active_runs=1                 ← prevent overlapping runs (most pipeline DAGs)
max_active_runs=10                ← allow concurrency for on-demand DAGs (replay)

## Sensors

ALWAYS use mode="reschedule"
  mode="poke" holds a worker slot while waiting → starves other tasks
  mode="reschedule" releases the worker between checks → efficient

ALWAYS set timeout
  Without timeout: sensor polls forever, worker slot held indefinitely
  timeout=3600 + mode=reschedule = polls every poke_interval, fails cleanly at 1hr

execution_delta gotcha
  ExternalTaskSensor looks for upstream run at SAME execution_date by default.
  If upstream runs at 09:00 and downstream at 09:05:
    execution_delta=timedelta(minutes=5) → look 5 minutes back → correct

## Error Handling

retries and retry_delay per task criticality
  Market data:  retries=2, retry_delay=3min
  Risk reports: retries=1, retry_delay=5min
  Regulatory:   retries=3, retry_delay=2min (MUST succeed)

email_on_failure for production DAGs
  Always set. Include oncall DL, not just individual.
  email=["team-oncall@firm.com"]  not  email=["john.smith@firm.com"]

execution_timeout on long-running tasks
  execution_timeout=timedelta(minutes=30)
  Without it: a hung task blocks the slot forever silently.
  With it: task is killed after timeout → retry logic takes over → alert fires

## Monitoring

Check these daily
  DAGs tab → any red (failed) or yellow (SLA miss)?
  Browse → SLA Misses → any DAGs consistently late?
  Grid view → task duration trends (getting slower over time = data growth issue)

Kafka lag as leading indicator
  If market_data.ticks consumer lag spikes → market_data_ingestion DAG will be slow
  Check lag BEFORE the DAG runs, not after it fails

## Backfill

airflow dags backfill <dag_id> --start-date YYYY-MM-DD --end-date YYYY-MM-DD
  Runs DAG for each day in the range (one run per execution_date)
  Tasks must be idempotent — backfill replays everything

When to backfill
  Feed was down for 3 days → backfill market_data_ingestion for those 3 days
  VaR calculation used wrong prices → backfill eod_risk_report
  Regulatory report had a bug → backfill regulatory_reporting (with compliance sign-off)

Backfill on market data
  If within Kafka retention (1 hour): replay from Kafka
  If outside retention: read from S3 archive (warm/cold tier)
  DAG must be aware of which storage tier to use based on date

## Anti-Patterns to Avoid

❌  datetime.now() in tasks → breaks backfill (always uses today's date)
    Use: context['ds'] or context['execution_date']

❌  Blind rerun without reading logs
    "It failed, let me clear it" → rerun on a data integrity issue = corruption

❌  Catching all exceptions silently
    try: ... except: pass  → task shows success but did nothing → hard to debug

❌  BashOperator for complex logic
    Long bash scripts are harder to test, version, and debug than Python

❌  Global state between tasks
    Tasks run in separate processes (possibly on different workers).
    Pass data between tasks via XCom (small data) or shared storage (large data).

❌  Storing credentials in DAG code
    Use Airflow Connections and Variables, or AWS Secrets Manager / Vault.
""")

    example_dag = write(DIRS["dags"] / "best_practice_example.py", """\
\"\"\"
Best Practice DAG Example
Shows all recommended patterns for a trading pipeline DAG.
\"\"\"
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.external_task import ExternalTaskSensor

# ✅ Default args at module level (no logic, just config)
default_args = {
    "owner":            "platform-team",
    "retries":          2,
    "retry_delay":      timedelta(minutes=3),
    "email_on_failure": True,
    "email":            ["platform-oncall@firm.com"],
    "sla":              timedelta(minutes=20),
    "execution_timeout": timedelta(minutes=10),   # kill hung tasks
}

with DAG(
    dag_id="best_practice_example",
    default_args=default_args,
    start_date=datetime(2024, 1, 1),
    schedule_interval="0 9 * * 1-5",   # weekdays only
    catchup=False,                      # don't backfill on restart
    max_active_runs=1,                  # no overlapping runs
    tags=["example"],
) as dag:

    # ✅ Use execution_date via context, not datetime.now()
    def load_data(**context):
        ds = context['ds']   # YYYY-MM-DD of the run
        print(f"Loading data for {ds}")   # safe for backfill

    # ✅ ExternalTaskSensor with reschedule mode + execution_delta + timeout
    wait_for_upstream = ExternalTaskSensor(
        task_id="wait_for_upstream",
        external_dag_id="market_data_ingestion",
        external_task_id="update_replay_index",
        execution_delta=timedelta(minutes=45),
        timeout=3600,
        mode="reschedule",    # ✅ releases worker while waiting
        poke_interval=60,
        doc_md="Waits for market_data_ingestion to complete.",
    )

    # ✅ Small, focused task with doc_md
    load_task = PythonOperator(
        task_id="load_data",
        python_callable=load_data,
        doc_md="Loads market data for {{ ds }} from the tick store.",
    )

    # ✅ Idempotent write — UPSERT, not INSERT
    def write_results(**context):
        ds = context['ds']
        # UPSERT: safe to rerun
        # cursor.execute(
        #   "INSERT INTO results (date, value) VALUES (%s, %s)
        #    ON CONFLICT (date) DO UPDATE SET value=EXCLUDED.value",
        #   [ds, result]
        # )
        print(f"UPSERT result for {ds}")

    write_task = PythonOperator(
        task_id="write_results",
        python_callable=write_results,
        doc_md="Writes results for {{ ds }} using UPSERT (idempotent, safe to rerun).",
    )

    wait_for_upstream >> load_task >> write_task
""")

    print(f"""
{BOLD}── Best practices guide ─────────────────────────────────{RESET}
{CYAN}       cat {best_practices}{RESET}

{BOLD}── Example DAG with all patterns ───────────────────────{RESET}
{CYAN}       cat {example_dag}{RESET}

{BOLD}── Key things to say in the interview ─────────────────{RESET}
  On idempotency:
    "Every task in our pipelines uses UPSERT — clearing and rerunning
     never creates duplicate data."

  On sensors:
    "We always use mode=reschedule and set a timeout — poke mode
     holds a worker slot and can starve the rest of the pipeline."

  On {{ ds }}:
    "We never use datetime.now() inside tasks — always context['ds'].
     That's what makes backfill work correctly."

  On regulatory DAGs:
    "Regulatory pipelines have retries=3 and email_on_retry=True.
     Missing a submission is worse than any other failure — we retry
     harder and notify compliance on every attempt, not just final failure."

  On blind reruns:
    "I never clear a failed task without reading the full traceback.
     On a data integrity issue, a blind rerun can corrupt downstream
     tables — which is a much bigger problem than the original failure."
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
    1:  (launch_scenario_1,  "AF-01  Debug a failed DAG"),
    2:  (launch_scenario_2,  "AF-02  SLA miss investigation"),
    3:  (launch_scenario_3,  "AF-03  Pipeline health check script"),
    4:  (launch_scenario_4,  "AF-04  Sensor task never triggering"),
    5:  (launch_scenario_5,  "AF-05  Behavioral — pipeline story"),
    6:  (launch_scenario_6,  "AF-06  Market data ingestion DAG"),
    7:  (launch_scenario_7,  "AF-07  Historical tick replay & data website"),
    8:  (launch_scenario_8,  "AF-08  End-of-day risk report DAG"),
    9:  (launch_scenario_9,  "AF-09  Regulatory reporting pipeline"),
    10: (launch_scenario_10, "AF-10  Airflow best practices"),
    99: (None,               "       ALL scenarios"),
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
