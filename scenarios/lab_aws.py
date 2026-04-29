#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — AWS
=====================================
Covers CloudWatch logs, S3 market data, IAM permissions, EKS health,
and alarm triage. All scenarios use mock data — no AWS credentials needed.

SCENARIOS:
  1   A-01  CloudWatch Log Insights — query logs, find errors
  2   A-02  S3 market data — list, download, process tick files
  3   A-03  IAM & permissions — understand roles, policies, access errors
  4   A-04  CloudWatch alarm triage — read metrics, identify the incident
  5   A-05  EKS node health — node groups, pod scheduling on AWS
  99        ALL scenarios
"""

import os
import sys
import json
import time
import argparse
import random
from pathlib import Path
from datetime import datetime, timedelta

LAB_ROOT = Path("/tmp/lab_aws")
DIRS = {
    "logs":    LAB_ROOT / "logs",
    "scripts": LAB_ROOT / "scripts",
    "data":    LAB_ROOT / "data",
    "mock":    LAB_ROOT / "mock_aws",
}

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    create_dirs as _create_dirs,
    save_pid, load_pids, kill_pids, kill_strays, remove_lab_dir,
    show_status as _show_status,
)

def create_dirs(): _create_dirs(DIRS)
def show_status(): _show_status(DIRS["logs"], "AWS Lab")


# ══════════════════════════════════════════════
#  SCENARIO LAUNCHERS
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario A-01 — CloudWatch Log Insights")
    print("  A trading service is logging to CloudWatch.")
    print("  Find errors, slow queries, and connection failures.\n")

    # Generate realistic CloudWatch log export (JSON lines format)
    log_file = DIRS["logs"] / "cloudwatch_export.json"
    services = ["order-router", "risk-engine", "position-service", "market-data-feed"]
    levels   = ["INFO"] * 12 + ["WARN"] * 3 + ["ERROR"] * 2
    symbols  = ["AAPL", "GOOGL", "MSFT", "TSLA", "NVDA"]

    entries = []
    base_ts = datetime(2026, 4, 28, 9, 30, 0)
    for i in range(120):
        ts = base_ts + timedelta(seconds=i * 15)
        svc = random.choice(services)
        lvl = random.choice(levels)
        msg = ""
        if lvl == "ERROR":
            msg = random.choice([
                f"Connection refused: redis://prod-redis-01:6379 — timeout after 5000ms",
                f"Failed to publish fill for order ORD-{1000+i} to Kafka topic trade-executions",
                f"NullPointerException in PositionUpdater.apply() line 142",
                f"Database query exceeded SLA: 3420ms (threshold 500ms) SELECT * FROM positions",
            ])
        elif lvl == "WARN":
            msg = random.choice([
                f"Consumer lag on trade-executions partition 2: 847 messages",
                f"Slow upstream: exchange-feed latency 280ms (p99 threshold 200ms)",
                f"Memory usage at 82%% — GC overhead increasing",
            ])
        else:
            sym = random.choice(symbols)
            msg = random.choice([
                f"Order FILLED: {sym} qty={random.randint(100,1000)} price={round(random.uniform(100,500),2)}",
                f"Heartbeat OK — connected to EXCHANGE_A seq={1000+i}",
                f"Position reconciled: {sym} net_qty={random.randint(-500,500)}",
                f"Health check passed — uptime {i*15}s",
            ])
        entries.append({
            "timestamp": int(ts.timestamp() * 1000),
            "logStreamName": f"{svc}/app/{svc}-pod-{random.randint(1,3)}",
            "message": f"{ts.strftime('%Y-%m-%dT%H:%M:%S.000Z')} {lvl} [{svc}] {msg}"
        })

    log_file.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
    ok(f"CloudWatch log export: {log_file}  ({len(entries)} entries)")

    # Solution script
    script = DIRS["scripts"] / "cw_log_query.py"
    script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"A-01: Query a CloudWatch log export — find errors and slow queries.\"\"\"
import json, sys
from collections import defaultdict

LOG_FILE = "{log_file}"

errors   = []
warns    = []
services = defaultdict(lambda: {{"ERROR": 0, "WARN": 0, "INFO": 0}})

with open(LOG_FILE) as f:
    for line in f:
        entry = json.loads(line.strip())
        msg   = entry["message"]
        svc   = entry["logStreamName"].split("/")[0]

        for level in ("ERROR", "WARN", "INFO"):
            if f" {{level}} " in msg:
                services[svc][level] += 1
                if level == "ERROR":
                    errors.append(msg)
                elif level == "WARN":
                    warns.append(msg)
                break

print("=== Error Summary ===")
for e in errors:
    print(f"  ✗ {{e.split('] ', 1)[-1]}}")

print("\\n=== Warnings ===")
for w in warns:
    print(f"  ⚠ {{w.split('] ', 1)[-1]}}")

print("\\n=== Log counts per service ===")
for svc, counts in sorted(services.items()):
    print(f"  {{svc:<25}}  ERROR={{counts['ERROR']}}  WARN={{counts['WARN']}}  INFO={{counts['INFO']}}")

print("\\n=== Slow DB queries (>500ms) ===")
with open(LOG_FILE) as f:
    for line in f:
        msg = json.loads(line)["message"]
        if "exceeded SLA" in msg or "ms)" in msg:
            print(f"  {{msg.split('] ', 1)[-1]}}")
""")
    ok(f"Query script: {script}")

    print(f"""
{BOLD}── CloudWatch log export (JSON lines): ─────────────────{RESET}
{CYAN}       cat {log_file} | python3 -m json.tool | head -20{RESET}

{BOLD}── Tasks ───────────────────────────────────────────────{RESET}
  1. Count errors per service
  2. Find all ERROR messages
  3. Find slow DB queries (>500ms)
  4. Which service has the most warnings?

{BOLD}── Run the solution script ──────────────────────────────{RESET}
{CYAN}       python3 {script}{RESET}

{BOLD}── In real AWS (CloudWatch Log Insights query): ─────────{RESET}
{CYAN}       fields @timestamp, @message
       | filter @message like /ERROR/
       | sort @timestamp desc
       | limit 50{RESET}

{BOLD}── Key CloudWatch concepts ──────────────────────────────{RESET}
  Log Group  : one per service  (e.g. /trading/order-router)
  Log Stream : one per pod/instance inside the group
  Log Insights: SQL-like query language for searching across groups
  Metric Filter: turn log patterns into CloudWatch metrics/alarms
  Retention: logs expire after N days (cost control)
""")


def launch_scenario_2():
    header("Scenario A-02 — S3 Market Data Operations")
    print("  Historical tick data is stored in S3.")
    print("  Understand the bucket layout, list objects, and process a file.\n")

    # Mock S3 listing (aws s3 ls output)
    s3_listing = DIRS["mock"] / "s3_listing.txt"
    s3_listing.write_text("""\
# Output of: aws s3 ls s3://drw-market-data/ticks/ --recursive
2026-04-27 18:00:01    2457600  ticks/2026/04/27/AAPL_20260427.csv.gz
2026-04-27 18:00:03    1843200  ticks/2026/04/27/GOOGL_20260427.csv.gz
2026-04-27 18:00:05    3112960  ticks/2026/04/27/MSFT_20260427.csv.gz
2026-04-27 18:00:07    1228800  ticks/2026/04/27/TSLA_20260427.csv.gz
2026-04-27 18:00:09    2867200  ticks/2026/04/27/NVDA_20260427.csv.gz
2026-04-28 18:00:01    2560000  ticks/2026/04/28/AAPL_20260428.csv.gz
2026-04-28 18:00:03    1920000  ticks/2026/04/28/GOOGL_20260428.csv.gz
2026-04-28 18:00:05    3276800  ticks/2026/04/28/MSFT_20260428.csv.gz
2026-04-28 18:00:07    1310720  ticks/2026/04/28/TSLA_20260428.csv.gz
2026-04-28 18:00:09    2990080  ticks/2026/04/28/NVDA_20260428.csv.gz

# Processed parquet files (Athena-queryable)
2026-04-28 18:30:00   12582912  processed/2026/04/28/trades_partitioned.parquet
2026-04-28 18:31:00    4194304  processed/2026/04/28/positions_eod.parquet

# Reports (Regulatory)
2026-04-28 19:00:00     245760  reports/2026/04/28/regulatory_report_20260428.json
2026-04-28 19:00:05      81920  reports/2026/04/28/pnl_summary_20260428.json
""")
    ok(f"S3 listing mock: {s3_listing}")

    # Simulate a downloaded tick CSV
    tick_file = DIRS["data"] / "AAPL_20260428_sample.csv"
    lines = ["timestamp,symbol,bid,ask,bid_size,ask_size,last_price,last_size,exchange"]
    base = datetime(2026, 4, 28, 9, 30, 0)
    price = 185.50
    for i in range(200):
        ts = base + timedelta(milliseconds=i * 500)
        price += random.gauss(0, 0.05)
        bid = round(price - 0.01, 2)
        ask = round(price + 0.01, 2)
        lines.append(
            f"{ts.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]}Z,"
            f"AAPL,{bid},{ask},"
            f"{random.randint(100,1000)},{random.randint(100,1000)},"
            f"{round(price,2)},{random.randint(100,500)},"
            f"{random.choice(['NASDAQ','NYSE','BATS'])}"
        )
    tick_file.write_text("\n".join(lines) + "\n")
    ok(f"Sample tick data: {tick_file}  (200 ticks, ~100 seconds)")

    script = DIRS["scripts"] / "s3_tick_analysis.py"
    script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"A-02: Process S3 tick data — VWAP, spread, exchange breakdown.\"\"\"
import csv
from collections import defaultdict

TICK_FILE = "{tick_file}"
S3_LIST   = "{s3_listing}"

# S3 listing analysis
print("=== S3 Bucket Analysis ===")
total_size = 0
file_count = 0
with open(S3_LIST) as f:
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[2].isdigit():
            total_size += int(parts[2])
            file_count += 1
print(f"  Files: {{file_count}}")
print(f"  Total size: {{total_size / 1024 / 1024:.1f}} MB")

# Tick data analysis
print("\\n=== Tick Data Analysis (AAPL sample) ===")
ticks   = []
by_exch = defaultdict(list)
with open(TICK_FILE) as f:
    reader = csv.DictReader(f)
    for row in reader:
        price  = float(row["last_price"])
        size   = int(row["last_size"])
        spread = float(row["ask"]) - float(row["bid"])
        ticks.append((price, size, spread))
        by_exch[row["exchange"]].append(price)

prices  = [t[0] for t in ticks]
sizes   = [t[1] for t in ticks]
spreads = [t[2] for t in ticks]

vwap = sum(p * s for p, s in zip(prices, sizes)) / sum(sizes)
print(f"  Ticks:      {{len(ticks)}}")
print(f"  Price range: ${{min(prices):.2f}} — ${{max(prices):.2f}}")
print(f"  VWAP:        ${{vwap:.4f}}")
print(f"  Avg spread:  ${{sum(spreads)/len(spreads):.4f}}")

print("\\n  Exchange breakdown:")
for exch, prices_e in sorted(by_exch.items()):
    print(f"    {{exch:<10}} {{len(prices_e):4}} ticks  avg=${{sum(prices_e)/len(prices_e):.2f}}")

print("\\n=== AWS CLI equivalents (for reference) ===")
print("  aws s3 ls s3://drw-market-data/ticks/2026/04/28/")
print("  aws s3 cp s3://drw-market-data/ticks/2026/04/28/AAPL_20260428.csv.gz .")
print("  aws s3api get-object-attributes --bucket drw-market-data --key ticks/...")
""")
    ok(f"Analysis script: {script}")

    print(f"""
{BOLD}── S3 bucket layout: ───────────────────────────────────{RESET}
{CYAN}       cat {s3_listing}{RESET}

{BOLD}── Tick data sample: ───────────────────────────────────{RESET}
{CYAN}       head -5 {tick_file}{RESET}

{BOLD}── Run the analysis script ──────────────────────────────{RESET}
{CYAN}       python3 {script}{RESET}

{BOLD}── Key S3 concepts for trading ─────────────────────────{RESET}
  Bucket layout  : s3://bucket/prefix/year/month/day/file
  Partitioning   : Athena/Glue can query by partition without full scan
  Lifecycle rules: auto-archive to Glacier after 90 days (cost saving)
  Versioning     : keep history of regulatory reports
  Presigned URLs : give quants temp access to download data without IAM keys
  Storage classes: Standard (hot), IA (warm), Glacier (cold/archive)

{BOLD}── AWS CLI commands you will use ────────────────────────{RESET}
{CYAN}       aws s3 ls s3://bucket/prefix/                    # list
       aws s3 cp s3://bucket/key ./local_file             # download
       aws s3 sync s3://bucket/prefix/ ./local_dir/       # sync folder
       aws s3api list-objects-v2 --bucket NAME --prefix P  # programmatic list{RESET}
""")


def launch_scenario_3():
    header("Scenario A-03 — IAM & Permissions")
    print("  A service pod can't access S3. Diagnose the IAM issue.\n")

    # Mock IAM policy and error
    error_log = DIRS["logs"] / "iam_access_denied.log"
    error_log.write_text("""\
2026-04-28T09:31:05Z ERROR [market-data-feed] Failed to download tick file
  Exception: com.amazonaws.services.s3.model.AmazonS3Exception:
    Access Denied (Service: Amazon S3; Status Code: 403; Error Code: AccessDenied)
    Request ID: 7B4C2E8F1A3D9B0E
    Bucket: drw-market-data
    Key: ticks/2026/04/28/AAPL_20260428.csv.gz

2026-04-28T09:31:06Z ERROR [market-data-feed] Retrying in 5s (attempt 1/3)
2026-04-28T09:31:11Z ERROR [market-data-feed] Retrying in 10s (attempt 2/3)
2026-04-28T09:31:21Z ERROR [market-data-feed] All retries exhausted — market data unavailable
2026-04-28T09:31:21Z CRITICAL [risk-engine] Cannot compute risk: market data feed down
""")
    ok(f"Access denied log: {error_log}")

    # Mock IAM policy (what the role has)
    current_policy = DIRS["mock"] / "iam_current_policy.json"
    current_policy.write_text(json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3ReadInternal",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    "arn:aws:s3:::drw-internal-data",
                    "arn:aws:s3:::drw-internal-data/*"
                ]
            },
            {
                "Sid": "CloudWatchLogs",
                "Effect": "Allow",
                "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": "arn:aws:logs:us-east-1:123456789012:log-group:/trading/*"
            }
        ]
    }, indent=2))
    ok(f"Current IAM policy: {current_policy}")

    # What it should have
    fixed_policy = DIRS["mock"] / "iam_fixed_policy.json"
    fixed_policy.write_text(json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3ReadInternal",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    "arn:aws:s3:::drw-internal-data",
                    "arn:aws:s3:::drw-internal-data/*"
                ]
            },
            {
                "Sid": "S3ReadMarketData",
                "Effect": "Allow",
                "Action": ["s3:GetObject", "s3:ListBucket"],
                "Resource": [
                    "arn:aws:s3:::drw-market-data",
                    "arn:aws:s3:::drw-market-data/*"
                ]
            },
            {
                "Sid": "CloudWatchLogs",
                "Effect": "Allow",
                "Action": ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                "Resource": "arn:aws:logs:us-east-1:123456789012:log-group:/trading/*"
            }
        ]
    }, indent=2))
    ok(f"Fixed IAM policy:   {fixed_policy}")

    print(f"""
{BOLD}── Error log: ──────────────────────────────────────────{RESET}
{CYAN}       cat {error_log}{RESET}

{BOLD}── Diagnose the issue: ─────────────────────────────────{RESET}
{CYAN}       cat {current_policy}{RESET}

  What bucket does the policy give access to?
  What bucket is the service trying to access?
  What is missing?

{BOLD}── Fixed policy (solution): ────────────────────────────{RESET}
{CYAN}       cat {fixed_policy}{RESET}

{BOLD}── Key IAM concepts ────────────────────────────────────{RESET}
  IAM Role     : identity attached to a pod/service (not a user)
  Policy       : JSON document listing allowed/denied actions + resources
  ARN          : Amazon Resource Name — uniquely identifies any AWS resource
                 arn:aws:s3:::bucket-name      ← the bucket
                 arn:aws:s3:::bucket-name/*    ← everything inside it
  Effect       : Allow or Deny (Deny always wins)
  Action       : what you can do (s3:GetObject, s3:ListBucket, etc.)
  Resource     : which ARN the action applies to
  IRSA         : IAM Roles for Service Accounts — how K8s pods get IAM roles

{BOLD}── AWS CLI to check a role (for reference) ─────────────{RESET}
{CYAN}       aws iam get-role --role-name market-data-feed-role
       aws iam list-attached-role-policies --role-name market-data-feed-role
       aws iam get-policy-version --policy-arn ARN --version-id v1{RESET}

{BOLD}── Triage steps for AccessDenied ───────────────────────{RESET}
  1. Note the bucket/key from the error
  2. Find the IAM role attached to the pod (kubectl describe pod → serviceAccountName)
  3. Check the role's policies for that bucket ARN
  4. Add missing s3:GetObject + s3:ListBucket on the bucket + bucket/* ARN
  5. Wait ~30s for propagation, then redeploy/restart the pod
""")


def launch_scenario_4():
    header("Scenario A-04 — CloudWatch Alarm Triage")
    print("  Three alarms just fired. Triage and identify root cause.\n")

    # Mock CloudWatch alarm states
    alarms = DIRS["mock"] / "cw_alarms.json"
    alarms.write_text(json.dumps([
        {
            "AlarmName": "OrderRouter-P99Latency-High",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 1 out of the last 1 datapoints [487.3 (28/04/26 09:31:00)] was greater than the threshold (200.0).",
            "MetricName": "P99Latency",
            "Namespace": "Trading/OrderRouter",
            "Threshold": 200.0,
            "ActualValue": 487.3,
            "Unit": "Milliseconds",
            "StateUpdatedTimestamp": "2026-04-28T09:31:05Z"
        },
        {
            "AlarmName": "RiskEngine-ConsumerLag-High",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 1 out of the last 1 datapoints [1842 (28/04/26 09:31:00)] was greater than the threshold (500.0).",
            "MetricName": "ConsumerLag",
            "Namespace": "Trading/Kafka",
            "Threshold": 500.0,
            "ActualValue": 1842.0,
            "Unit": "Count",
            "StateUpdatedTimestamp": "2026-04-28T09:31:03Z"
        },
        {
            "AlarmName": "MarketDataFeed-S3AccessErrors",
            "StateValue": "ALARM",
            "StateReason": "Threshold Crossed: 3 out of the last 3 datapoints were greater than threshold (0).",
            "MetricName": "S3ErrorCount",
            "Namespace": "Trading/MarketData",
            "Threshold": 0.0,
            "ActualValue": 3.0,
            "Unit": "Count",
            "StateUpdatedTimestamp": "2026-04-28T09:31:01Z"
        },
        {
            "AlarmName": "PositionService-HeapUsage",
            "StateValue": "OK",
            "StateReason": "Threshold Crossed: datapoint [68.2] was not greater than threshold (85.0)",
            "MetricName": "HeapUsedPercent",
            "Namespace": "Trading/JVM",
            "Threshold": 85.0,
            "ActualValue": 68.2,
            "Unit": "Percent",
            "StateUpdatedTimestamp": "2026-04-28T09:30:00Z"
        }
    ], indent=2))
    ok(f"CloudWatch alarms: {alarms}")

    script = DIRS["scripts"] / "triage_alarms.py"
    script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"A-04: Triage CloudWatch alarms — find root cause and priority order.\"\"\"
import json

ALARMS_FILE = "{alarms}"

with open(ALARMS_FILE) as f:
    alarms = json.load(f)

firing   = [a for a in alarms if a["StateValue"] == "ALARM"]
ok_alarms = [a for a in alarms if a["StateValue"] == "OK"]

print("=== FIRING ALARMS ===")
for a in sorted(firing, key=lambda x: x["StateUpdatedTimestamp"]):
    print(f"  ✗ [{{a['StateUpdatedTimestamp']}}] {{a['AlarmName']}}")
    print(f"      Metric:    {{a['MetricName']}} = {{a['ActualValue']}} {{a['Unit']}}")
    print(f"      Threshold: {{a['Threshold']}} {{a['Unit']}}")
    print()

print("=== ROOT CAUSE ANALYSIS ===")
print(\"\"\"
  Timeline (by StateUpdatedTimestamp):
  09:31:01  MarketDataFeed-S3AccessErrors   ← FIRST — S3 access denied (IAM issue)
  09:31:03  RiskEngine-ConsumerLag-High     ← SECOND — no market data = lag builds up
  09:31:05  OrderRouter-P99Latency-High     ← THIRD — risk checks slow = orders queue up

  Root cause: IAM permissions missing on drw-market-data bucket (see A-03)
  The S3 failure cascaded → no market data → risk engine stalled → order latency spike

  Fix order:
  1. Fix IAM policy on market-data-feed role (immediate)
  2. Restart market-data-feed pod
  3. Verify consumer lag recovers
  4. Verify order router latency returns to normal
\"\"\")

print("=== OK ALARMS ===")
for a in ok_alarms:
    print(f"  ✓ {{a['AlarmName']}}  ({{a['MetricName']}} = {{a['ActualValue']}})")
""")
    ok(f"Triage script: {script}")

    print(f"""
{BOLD}── CloudWatch alarms: ──────────────────────────────────{RESET}
{CYAN}       cat {alarms}{RESET}

{BOLD}── Tasks ───────────────────────────────────────────────{RESET}
  1. Which alarms are firing?
  2. What fired first? (look at StateUpdatedTimestamp)
  3. Is there a cascade? (one failure causing others?)
  4. What is the root cause?

{BOLD}── Run the triage script ─────────────────────────────{RESET}
{CYAN}       python3 {script}{RESET}

{BOLD}── Key CloudWatch alarm concepts ───────────────────────{RESET}
  Namespace  : logical grouping of metrics (Trading/OrderRouter)
  MetricName : the specific measurement (P99Latency, ConsumerLag)
  Threshold  : the value that triggers the alarm
  Period     : how often the metric is evaluated (60s, 300s)
  Datapoints : how many periods must breach before alarm fires
  Actions    : what happens on ALARM (SNS → PagerDuty/Slack/email)

{BOLD}── AWS CLI (for reference) ──────────────────────────────{RESET}
{CYAN}       aws cloudwatch describe-alarms --state-value ALARM
       aws cloudwatch get-metric-statistics --namespace Trading/OrderRouter \\
         --metric-name P99Latency --period 60 --statistics Average \\
         --start-time 2026-04-28T09:00:00Z --end-time 2026-04-28T09:35:00Z{RESET}
""")


def launch_scenario_5():
    header("Scenario A-05 — EKS Node Health")
    print("  The Kubernetes cluster runs on EKS. A node group is")
    print("  degraded and pods are not scheduling. Diagnose.\n")

    # Mock kubectl get nodes output for EKS
    nodes_file = DIRS["mock"] / "eks_nodes.txt"
    nodes_file.write_text("""\
# kubectl get nodes -o wide
NAME                                         STATUS     ROLES    AGE   VERSION    INTERNAL-IP    INSTANCE-TYPE    NODE-GROUP
ip-10-0-1-101.us-east-1.compute.internal    Ready      <none>   12d   v1.29.3   10.0.1.101     m5.2xlarge       trading-workers
ip-10-0-1-102.us-east-1.compute.internal    Ready      <none>   12d   v1.29.3   10.0.1.102     m5.2xlarge       trading-workers
ip-10-0-1-103.us-east-1.compute.internal    NotReady   <none>   12d   v1.29.3   10.0.1.103     m5.2xlarge       trading-workers
ip-10-0-2-201.us-east-1.compute.internal    Ready      <none>    3d   v1.29.3   10.0.2.201     c5.4xlarge       latency-critical
ip-10-0-2-202.us-east-1.compute.internal    Ready      <none>    3d   v1.29.3   10.0.2.202     c5.4xlarge       latency-critical
""")
    ok(f"EKS nodes: {nodes_file}")

    # Mock kubectl describe node for the NotReady node
    node_describe = DIRS["mock"] / "eks_node_notready.txt"
    node_describe.write_text("""\
# kubectl describe node ip-10-0-1-103.us-east-1.compute.internal
Name:               ip-10-0-1-103.us-east-1.compute.internal
Labels:             eks.amazonaws.com/nodegroup=trading-workers
                    node.kubernetes.io/instance-type=m5.2xlarge
                    topology.kubernetes.io/zone=us-east-1c
Conditions:
  Type                 Status  Reason
  ----                 ------  ------
  MemoryPressure       False   KubeletHasSufficientMemory
  DiskPressure         False   KubeletHasNoDiskPressure
  PIDPressure          False   KubeletHasSufficientPID
  Ready                False   KubeletNotReady  ← NODE IS NOT READY

  Message: container runtime network not ready:
    NetworkReady=false reason:NetworkPluginNotReady
    message:Network plugin returns error: cni plugin not initialized

Events:
  Type     Reason                   Age   Message
  ----     ------                   ---   -------
  Warning  NodeNotReady             5m    Node ip-10-0-1-103 status is now: NodeNotReady
  Warning  FailedCreatePodSandBox   4m    Failed to create pod sandbox: rpc error:
                                          code = Unknown desc = failed to setup network for sandbox:
                                          plugin type="aws-node" failed (add): add cmd: Error
                                          received from AddNetwork gRPC call: rpc error:
                                          code = DeadlineExceeded

Allocated resources:
  Resource           Requests   Limits
  cpu                1850m/8    3200m/8
  memory             6Gi/32Gi   12Gi/32Gi

# Pods stuck Pending because this node is NotReady:
# kubectl get pods --all-namespaces --field-selector spec.nodeName=ip-10-0-1-103...
NAMESPACE    NAME                           READY   STATUS    RESTARTS
trading      position-service-7d4f9-xk2p8  0/1     Pending   0
trading      risk-engine-6c8b4-mn9q1        0/1     Pending   0
""")
    ok(f"NotReady node details: {node_describe}")

    print(f"""
{BOLD}── EKS node status: ────────────────────────────────────{RESET}
{CYAN}       cat {nodes_file}{RESET}

{BOLD}── NotReady node details: ──────────────────────────────{RESET}
{CYAN}       cat {node_describe}{RESET}

{BOLD}── Diagnosis ────────────────────────────────────────────{RESET}
  Problem: CNI (Container Network Interface) plugin not initialized
  Plugin:  aws-node (AWS VPC CNI) — the plugin that assigns pod IPs
  Effect:  Node cannot create network sandboxes for pods → NotReady
           2 pods stuck Pending because they can't schedule elsewhere
           (node group only has 3 nodes, 1 is down)

{BOLD}── Resolution steps ─────────────────────────────────────{RESET}
  1. Check aws-node DaemonSet on the bad node:
{CYAN}       kubectl get pod -n kube-system -o wide | grep ip-10-0-1-103
       kubectl logs -n kube-system aws-node-XXXXX{RESET}

  2. Restart the aws-node pod on that node:
{CYAN}       kubectl delete pod -n kube-system aws-node-XXXXX{RESET}

  3. If CNI still fails → drain and terminate the node:
{CYAN}       kubectl drain ip-10-0-1-103... --ignore-daemonsets --delete-emptydir-data
       aws ec2 terminate-instances --instance-ids i-XXXXX{RESET}
     EKS Auto Scaling Group will replace the node automatically.

{BOLD}── Key EKS concepts ────────────────────────────────────{RESET}
  Node Group    : pool of EC2 instances (m5.2xlarge = 8 vCPU, 32GB)
  aws-node      : DaemonSet that runs on every node, manages pod networking
  CNI           : Container Network Interface — assigns IPs to pods from VPC subnet
  IRSA          : how pods get AWS credentials without hardcoded keys
  Node drain    : evict all pods gracefully before terminating a node
  Managed nodes : AWS handles patching; unmanaged = you handle OS updates
""")


def launch_scenario_99():
    header("Scenario 99 — ALL AWS Scenarios")
    for fn in [launch_scenario_1, launch_scenario_2, launch_scenario_3,
               launch_scenario_4, launch_scenario_5]:
        fn()
        time.sleep(0.2)


def teardown():
    header("Tearing Down AWS Lab")
    remove_lab_dir(LAB_ROOT)


SCENARIO_MAP = {
    1:  (launch_scenario_1, "A-01  CloudWatch Log Insights"),
    2:  (launch_scenario_2, "A-02  S3 market data operations"),
    3:  (launch_scenario_3, "A-03  IAM & permissions"),
    4:  (launch_scenario_4, "A-04  CloudWatch alarm triage"),
    5:  (launch_scenario_5, "A-05  EKS node health"),
    99: (launch_scenario_99, "     ALL scenarios"),
}


def main():
    parser = argparse.ArgumentParser(description="AWS Challenge Lab",
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
        header("AWS Challenge Lab")
        for num, (_, desc) in SCENARIO_MAP.items():
            print(f"    {num:<4} {desc}")
        choice = input("\n  Enter scenario number (or q): ").strip()
        if choice.lower() == "q": return
        try:
            fn, _ = SCENARIO_MAP[int(choice)]; fn()
        except (KeyError, ValueError): err(f"Invalid: {choice}")
    lab_footer("lab_aws.py")


if __name__ == "__main__":
    main()
