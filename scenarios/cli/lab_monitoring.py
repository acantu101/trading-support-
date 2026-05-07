#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Monitoring & Observability
============================================================
Covers latency percentiles, CloudWatch metrics, Prometheus/Grafana concepts,
alert triage workflows, and trading system KPIs.

SCENARIOS:
  1   M-01  Latency percentiles — p50/p95/p99, what they reveal
  2   M-02  CloudWatch metrics — read a dashboard, find an anomaly
  3   M-03  Prometheus & Grafana — metric types, PromQL basics
  4   M-04  Alert triage workflow — receive alert, trace root cause
  5   M-05  Trading system KPIs — what to monitor and alert thresholds
  99        ALL scenarios
"""

import sys
import json
import time
import math
import random
import argparse
from pathlib import Path
from datetime import datetime, timedelta

LAB_ROOT = Path("/tmp/lab_monitoring")
DIRS = {
    "logs":    LAB_ROOT / "logs",
    "scripts": LAB_ROOT / "scripts",
    "data":    LAB_ROOT / "data",
}

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    create_dirs as _create_dirs,
    remove_lab_dir,
    show_status as _show_status,
    run_menu,
)

def create_dirs(): _create_dirs(DIRS)
def show_status(): _show_status(DIRS["scripts"], "Monitoring Lab")


# ══════════════════════════════════════════════
#  SCENARIO LAUNCHERS
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario M-01 — Latency Percentiles")
    print("  The order router SLA is p99 < 200ms.")
    print("  Analyse a latency dataset and identify the problem.\n")

    # Generate a realistic latency distribution with a spike
    latency_file = DIRS["data"] / "order_router_latency.json"
    samples = []
    base_ts = datetime(2026, 4, 28, 9, 30, 0)

    # Normal period: 9:30 - 9:45
    for i in range(500):
        ts = base_ts + timedelta(seconds=i * 1.8)
        latency = max(1, random.gauss(45, 15))  # normal ~45ms
        samples.append({"timestamp": ts.isoformat() + "Z", "latency_ms": round(latency, 2), "period": "normal"})

    # Degraded period: 9:45 - 9:55 (GC pause / lock contention)
    base_degraded = base_ts + timedelta(minutes=15)
    for i in range(200):
        ts = base_degraded + timedelta(seconds=i * 3)
        # Bimodal: most requests normal, some very slow
        if random.random() < 0.15:
            latency = random.uniform(800, 4800)  # slow outliers
        else:
            latency = max(1, random.gauss(60, 20))
        samples.append({"timestamp": ts.isoformat() + "Z", "latency_ms": round(latency, 2), "period": "degraded"})

    # Recovery: 9:55+
    base_recovery = base_ts + timedelta(minutes=25)
    for i in range(200):
        ts = base_recovery + timedelta(seconds=i * 1.8)
        latency = max(1, random.gauss(48, 12))
        samples.append({"timestamp": ts.isoformat() + "Z", "latency_ms": round(latency, 2), "period": "recovery"})

    latency_file.write_text(json.dumps(samples, indent=2))
    ok(f"Latency data: {latency_file}  ({len(samples)} samples)")

    script = DIRS["scripts"] / "latency_analysis.py"
    script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"M-01: Analyse order router latency — percentiles, SLA breaches.\"\"\"
import json

LATENCY_FILE = "{latency_file}"
SLA_P99_MS   = 200.0

with open(LATENCY_FILE) as f:
    samples = json.load(f)

def percentile(data, p):
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= len(sorted_data):
        return sorted_data[-1]
    frac = idx - lower
    return sorted_data[lower] * (1 - frac) + sorted_data[upper] * frac

def analyse(label, data):
    latencies = [s["latency_ms"] for s in data]
    p50 = percentile(latencies, 50)
    p95 = percentile(latencies, 95)
    p99 = percentile(latencies, 99)
    p999 = percentile(latencies, 99.9)
    avg  = sum(latencies) / len(latencies)
    breaches = sum(1 for l in latencies if l > SLA_P99_MS)
    breach_pct = 100 * breaches / len(latencies)
    sla_flag = "✗ SLA BREACH" if p99 > SLA_P99_MS else "✓ SLA OK"
    print(f"  {{label:<12}} p50={{p50:>7.1f}}ms  p95={{p95:>7.1f}}ms  p99={{p99:>7.1f}}ms  p99.9={{p999:>8.1f}}ms  avg={{avg:>6.1f}}ms  {{sla_flag}}  ({{breach_pct:.1f}}% breaches)")

periods = {{}}
for s in samples:
    periods.setdefault(s["period"], []).append(s)

print(f"Latency Analysis — Order Router (SLA: p99 < {{SLA_P99_MS}}ms)")
print(f"  {{' PERIOD':<12}} {{' P50':>10}} {{' P95':>10}} {{' P99':>10}} {{' P99.9':>12}} {{' AVG':>9}}  STATUS")
print(f"  {{'-'*12}} {{'-'*10}} {{'-'*10}} {{'-'*10}} {{'-'*12}} {{'-'*9}}  {{'-'*20}}")
for period in ["normal", "degraded", "recovery"]:
    if period in periods:
        analyse(period, periods[period])

all_latencies = [s["latency_ms"] for s in samples]
print()
analyse("ALL PERIODS", samples)

print(f\"\"\"
What the percentiles tell you:
  p50 (median) : half of requests are faster than this. The "typical" experience.
  p95          : 95%% of requests are faster. 1 in 20 is slower.
  p99          : 99%% of requests are faster. 1 in 100 is slower. ← SLA is usually here
  p99.9        : 999 in 1000 are faster. Catches extreme outliers (GC pauses, etc.)

Why p99 matters more than average for trading:
  During "degraded" period:
    - Average might look acceptable (e.g. 80ms)
    - But p99 is 4000ms — 1 in 100 orders is taking 4 seconds
    - In a system processing 1000 orders/minute → 10 orders/minute hitting 4s latency
    - Those 10 orders miss fills, hit timeouts, cause risk check failures

The "degraded" period pattern (bimodal distribution):
  Most requests fast + some very slow = classic GC pause or lock contention signature
  During a GC stop-the-world pause, ALL threads freeze → spike in p99/p99.9
  After recovery, p99 returns to normal — confirms it was a transient pause, not degradation
\"\"\")
""")
    ok(f"Analysis script: {script}")

    print(f"""
{BOLD}── Run the latency analysis: ───────────────────────────{RESET}
{CYAN}       python3 {script}{RESET}

{BOLD}── Key concepts ────────────────────────────────────────{RESET}
  p50  : median — what a typical request experiences
  p95  : 1 in 20 is slower — early warning
  p99  : 1 in 100 is slower — SLA level for most trading systems
  p99.9: 1 in 1000 is slower — catches GC pauses, lock timeouts
  Average: MISLEADING for latency — hides outliers completely

{BOLD}── SLA conversation for your role ──────────────────────{RESET}
  "The service SLA is p99 < 200ms" means:
  99%% of requests complete in under 200ms.
  CloudWatch alarm: p99 > 200ms for 2 consecutive minutes → page on-call.
""")


def launch_scenario_2():
    header("Scenario M-02 — CloudWatch Metrics Dashboard")
    print("  Read a simulated CloudWatch metrics snapshot.")
    print("  Identify the anomaly and its business impact.\n")

    metrics_file = DIRS["data"] / "cloudwatch_metrics.json"
    base_ts = datetime(2026, 4, 28, 9, 0, 0)

    # Generate 90 minutes of metrics (1-minute resolution)
    datapoints = []
    for i in range(90):
        ts = base_ts + timedelta(minutes=i)
        is_degraded = 45 <= i <= 55  # 9:45 - 9:55 degradation

        datapoints.append({
            "timestamp": ts.isoformat() + "Z",
            "order_router_p99_ms":    round(random.gauss(4800 if is_degraded else 55, 200 if is_degraded else 8), 1),
            "order_router_rps":       round(random.gauss(180 if is_degraded else 320, 15), 0),
            "risk_engine_lag":        round(random.gauss(1900 if is_degraded else 12, 100 if is_degraded else 3), 0),
            "position_service_p99":   round(random.gauss(85 if is_degraded else 22, 10 if is_degraded else 4), 1),
            "kafka_consumer_lag":     int(random.gauss(1800 if is_degraded else 8, 200 if is_degraded else 3)),
            "jvm_heap_used_pct":      round(random.gauss(91 if is_degraded else 62, 3 if is_degraded else 5), 1),
            "error_rate_pct":         round(random.gauss(4.8 if is_degraded else 0.1, 0.5 if is_degraded else 0.05), 2),
        })

    metrics_file.write_text(json.dumps(datapoints, indent=2))
    ok(f"CloudWatch metrics: {metrics_file}  (90 minutes, 1-min resolution)")

    script = DIRS["scripts"] / "dashboard_analysis.py"
    script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"M-02: Analyse CloudWatch metrics — find anomaly and root cause.\"\"\"
import json
from datetime import datetime

METRICS_FILE = "{metrics_file}"
THRESHOLDS = {{
    "order_router_p99_ms":  200,
    "risk_engine_lag":      500,
    "kafka_consumer_lag":   100,
    "jvm_heap_used_pct":    85,
    "error_rate_pct":       1.0,
}}

with open(METRICS_FILE) as f:
    points = json.load(f)

# Find when each metric breached its threshold
print("=== Threshold Breach Timeline ===")
breaching = {{k: False for k in THRESHOLDS}}
for pt in points:
    ts = pt["timestamp"][11:16]  # HH:MM
    for metric, threshold in THRESHOLDS.items():
        value = pt.get(metric, 0)
        was_breaching = breaching[metric]
        now_breaching = value > threshold
        if now_breaching and not was_breaching:
            print(f"  {{ts}} ✗ BREACH START: {{metric}} = {{value}} (threshold={{threshold}})")
        elif not now_breaching and was_breaching:
            print(f"  {{ts}} ✓ RECOVERED:    {{metric}} = {{value}} (threshold={{threshold}})")
        breaching[metric] = now_breaching

print("\\n=== Peak Values During Incident ===")
degraded = [p for p in points if 45 <= points.index(p) <= 55]
for metric in THRESHOLDS:
    peak = max(p[metric] for p in degraded)
    normal_avg = sum(p[metric] for p in points[:40]) / 40
    print(f"  {{metric:<30}} normal_avg={{normal_avg:>8.1f}}  peak={{peak:>8.1f}}")

print(\"\"\"
=== Root Cause Analysis ===
Breach order:
  1. jvm_heap_used_pct crossed 85%  ← JVM approaching memory limit
  2. kafka_consumer_lag spiked      ← threads busy in GC, can't consume
  3. risk_engine_lag spiked         ← risk engine not getting fills from Kafka
  4. order_router_p99 spiked        ← orders queuing waiting for risk checks
  5. error_rate spiked              ← upstream timeouts from order router

Root cause: JVM heap pressure → GC overhead → cascading latency
Fix chain: Increase heap OR fix memory leak → GC normalizes → lag clears → latency recovers
\"\"\")
""")
    ok(f"Dashboard script: {script}")

    print(f"""
{BOLD}── Run the dashboard analysis: ─────────────────────────{RESET}
{CYAN}       python3 {script}{RESET}

{BOLD}── Reading a CloudWatch dashboard ──────────────────────{RESET}
  Look for: which metric breached FIRST? That is usually root cause.
  Cascades: one service's latency spike → upstream timeouts → their latency spikes
  Recovery: metrics should recover in reverse order of how they breached

{BOLD}── Key metrics for a trading system ────────────────────{RESET}
  p99 latency    : service health — breaching SLA?
  Kafka lag      : are consumers keeping up?
  JVM heap %     : approaching OOM?
  Error rate %   : how many requests are failing?
  Requests/sec   : traffic normal? (drop = upstream issue, spike = runaway)
""")


def launch_scenario_3():
    header("Scenario M-03 — Prometheus & Grafana Basics")
    print("  Prometheus collects metrics. Grafana visualises them.")
    print("  Understand metric types and write basic PromQL queries.\n")

    # Create mock Prometheus metrics export (text format)
    prom_file = DIRS["data"] / "prometheus_metrics.txt"
    prom_file.write_text("""\
# HELP order_router_request_duration_seconds Order router request latency
# TYPE order_router_request_duration_seconds histogram
order_router_request_duration_seconds_bucket{le="0.05",service="order-router"} 12450
order_router_request_duration_seconds_bucket{le="0.1",service="order-router"}  14820
order_router_request_duration_seconds_bucket{le="0.2",service="order-router"}  15100
order_router_request_duration_seconds_bucket{le="0.5",service="order-router"}  15180
order_router_request_duration_seconds_bucket{le="1.0",service="order-router"}  15195
order_router_request_duration_seconds_bucket{le="+Inf",service="order-router"} 15200
order_router_request_duration_seconds_sum{service="order-router"}   856.32
order_router_request_duration_seconds_count{service="order-router"} 15200

# HELP kafka_consumer_lag_records Current consumer lag in records
# TYPE kafka_consumer_lag_records gauge
kafka_consumer_lag_records{group="risk-engine-group",topic="trade-executions",partition="0"} 5
kafka_consumer_lag_records{group="risk-engine-group",topic="trade-executions",partition="1"} 847
kafka_consumer_lag_records{group="risk-engine-group",topic="trade-executions",partition="2"} 3
kafka_consumer_lag_records{group="risk-engine-group",topic="trade-executions",partition="3"} 1204

# HELP jvm_memory_used_bytes JVM memory used by area
# TYPE jvm_memory_used_bytes gauge
jvm_memory_used_bytes{area="heap",service="risk-engine"}     3221225472
jvm_memory_used_bytes{area="nonheap",service="risk-engine"}   201326592
jvm_memory_used_bytes{area="heap",service="position-service"} 1073741824

# HELP trade_fills_total Total number of trade fills processed
# TYPE trade_fills_total counter
trade_fills_total{service="order-router",symbol="AAPL",status="filled"}    4821
trade_fills_total{service="order-router",symbol="AAPL",status="rejected"}    42
trade_fills_total{service="order-router",symbol="GOOGL",status="filled"}   3104
trade_fills_total{service="order-router",symbol="MSFT",status="filled"}    2987

# HELP fix_session_connected FIX session connected (1=yes, 0=no)
# TYPE fix_session_connected gauge
fix_session_connected{session="FIRM_OMS-EXCHANGE_A"} 1
fix_session_connected{session="FIRM_OMS-EXCHANGE_B"} 0
fix_session_connected{session="FIRM_OMS-EXCHANGE_C"} 1
""")
    ok(f"Prometheus metrics: {prom_file}")

    guide = DIRS["scripts"] / "m03_promql_guide.txt"
    guide.write_text("""\
M-03 Prometheus & PromQL Guide
================================

METRIC TYPES:
  Counter   : always increases (total fills, total errors, total bytes)
              Reset to 0 on restart. Use rate() to get per-second rate.
              Example: trade_fills_total

  Gauge     : can go up or down (current lag, heap usage, connections)
              Snapshot at a point in time.
              Example: kafka_consumer_lag_records, jvm_memory_used_bytes

  Histogram : samples observations into buckets (latency distributions)
              Gives you _bucket, _sum, _count — used to calculate percentiles.
              Example: order_router_request_duration_seconds

  Summary   : pre-calculated percentiles (less flexible than histogram)

KEY PROMQL QUERIES:

  1. Current Kafka consumer lag per partition:
       kafka_consumer_lag_records{group="risk-engine-group"}

  2. Total lag across all partitions:
       sum(kafka_consumer_lag_records{group="risk-engine-group"})

  3. Fill rate per second (5-minute window):
       rate(trade_fills_total{status="filled"}[5m])

  4. Rejection rate as % of total:
       rate(trade_fills_total{status="rejected"}[5m])
       /
       rate(trade_fills_total[5m]) * 100

  5. p99 latency from histogram:
       histogram_quantile(0.99, rate(order_router_request_duration_seconds_bucket[5m]))

  6. JVM heap used in GB:
       jvm_memory_used_bytes{area="heap"} / 1024 / 1024 / 1024

  7. FIX sessions that are DOWN:
       fix_session_connected == 0

  8. Alert: lag > 500 on any partition:
       kafka_consumer_lag_records > 500

READING THE PROMETHEUS TEXT FORMAT:
  # HELP  : metric description
  # TYPE  : metric type (counter, gauge, histogram, summary)
  metric_name{label="value"} numeric_value  timestamp(optional)

  Labels: key-value pairs that differentiate instances of the same metric
  e.g. {service="risk-engine"} vs {service="order-router"} are separate series

GRAFANA DASHBOARD PANELS:
  Time Series : latency, lag, rates over time — most common
  Gauge       : current value with thresholds (heap %, error rate)
  Stat        : single big number (total fills today, uptime)
  Table       : multi-column data (per-partition lag)
  Alert       : threshold line on a time series — turns red when breached
""")
    ok(f"PromQL guide: {guide}")

    print(f"""
{BOLD}── Prometheus metrics export: ──────────────────────────{RESET}
{CYAN}       cat {prom_file}{RESET}

{BOLD}── PromQL guide: ───────────────────────────────────────{RESET}
{CYAN}       cat {guide}{RESET}

{BOLD}── Metric types at a glance ────────────────────────────{RESET}
  Counter   : always goes up — use rate() to get per-second rate
  Gauge     : current snapshot — heap %, lag, active connections
  Histogram : latency buckets — use histogram_quantile() for p99

{BOLD}── What you'll see in your role ─────────────────────────{RESET}
  Grafana dashboards with these exact metrics during incidents.
  When you get paged: open the dashboard, check which panels are red,
  find the metric that breached first — that is your root cause starting point.
""")


def launch_scenario_4():
    header("Scenario M-04 — Alert Triage Workflow")
    print("  PagerDuty just fired. Walk through the triage workflow")
    print("  from alert receipt to root cause.\n")

    alert_file = DIRS["data"] / "pagerduty_alert.json"
    alert_file.write_text(json.dumps({
        "incident_id": "INC-20260428-0042",
        "title": "CRITICAL: order-router P99 latency > 200ms",
        "fired_at": "2026-04-28T09:46:02Z",
        "service": "order-router",
        "alert_source": "CloudWatch",
        "metric": "P99Latency",
        "threshold": 200,
        "current_value": 4821,
        "unit": "Milliseconds",
        "runbook_url": "https://wiki.internal/runbooks/order-router-latency",
        "dashboard_url": "https://grafana.internal/d/trading-overview",
        "logs_url": "https://cloudwatch.internal/logs/order-router",
        "context": {
            "related_alarms_firing": [
                "RiskEngine-ConsumerLag-High",
                "JVM-HeapUsage-High (risk-engine)"
            ],
            "recent_deployments": [],
            "on_call_engineer": "you"
        }
    }, indent=2))
    ok(f"Alert: {alert_file}")

    workflow = DIRS["scripts"] / "m04_triage_workflow.txt"
    workflow.write_text("""\
M-04 Alert Triage Workflow
===========================

STEP 1 — Acknowledge the alert (within SLA, usually 5 minutes)
  - Acknowledge in PagerDuty so the team knows it is being worked
  - Note the exact time you started investigating

STEP 2 — Read the alert (30 seconds)
  - What is the metric? P99Latency = 4821ms (threshold 200ms)
  - What service? order-router
  - When did it fire? 09:46:02
  - What else is firing? risk-engine consumer lag, JVM heap high

STEP 3 — Check related alarms (1 minute)
  The alert says two related alarms are also firing:
  - RiskEngine-ConsumerLag-High
  - JVM-HeapUsage-High (risk-engine)

  Key question: which alarm fired FIRST?
  Timeline tells you the root cause direction:
    09:45:xx  JVM heap high on risk-engine        ← likely root cause
    09:45:xx  Kafka consumer lag (risk-engine)    ← GC pauses → can't consume
    09:46:02  Order router P99 high               ← waiting for risk checks

STEP 4 — Check logs (2-3 minutes)
  Go to CloudWatch logs for risk-engine:
    grep for: "GC" or "heap" or "OutOfMemory"
    Look at the timestamp window: 09:44 - 09:46
  Expected finding: Full GC event or GC overhead warning

STEP 5 — Determine blast radius (1 minute)
  Is this affecting live trading?
    - Order router p99 = 4.8 seconds → orders taking 5x normal time
    - Kafka lag = 1900 messages → risk engine 1900 fills behind
    - Are orders being rejected? Check error_rate metric
  Who is affected? All traders routing through this order-router

STEP 6 — Immediate mitigation
  Option A (less disruptive): increase JVM heap in pod config
    → kubectl edit deployment risk-engine → change -Xmx4g to -Xmx8g
    → rolling restart → heap pressure relieves → GC normalizes
  Option B (faster but disruptive): restart the risk-engine pod
    → kubectl rollout restart deployment/risk-engine
    → pod restarts, fresh heap, GC normalizes in ~30s
  Choose based on trading hours and urgency.

STEP 7 — Verify recovery
  Watch the CloudWatch dashboard:
    - JVM heap % should drop to <70% after restart
    - Kafka lag should drain within 1-2 minutes
    - Order router p99 should return to <100ms
  Confirm with the trading desk that orders are flowing normally.

STEP 8 — Post-incident
  - Write a brief summary: what fired, what you found, what you did
  - Identify permanent fix: find the memory leak or resize the pod spec
  - Open a ticket for the dev team

COMMUNICATION TEMPLATE:
  "INC-20260428-0042 UPDATE: Root cause identified as JVM heap pressure
  on risk-engine causing GC pauses. Restarted risk-engine pod at 09:52.
  P99 latency recovering, consumer lag clearing. Monitoring."
""")
    ok(f"Triage workflow: {workflow}")

    print(f"""
{BOLD}── Alert received: ─────────────────────────────────────{RESET}
{CYAN}       cat {alert_file}{RESET}

{BOLD}── Triage workflow: ────────────────────────────────────{RESET}
{CYAN}       cat {workflow}{RESET}

{BOLD}── The 8-step triage process ───────────────────────────{RESET}
  1. Acknowledge (within SLA)
  2. Read the alert
  3. Check related alarms — which fired FIRST?
  4. Check logs at the time window
  5. Assess blast radius
  6. Mitigate
  7. Verify recovery
  8. Write post-incident summary
""")


def launch_scenario_5():
    header("Scenario M-05 — Trading System KPIs & Thresholds")
    print("  Know what to monitor and what thresholds to set")
    print("  for a trading system support role.\n")

    kpis_file = DIRS["data"] / "trading_kpis.json"
    kpis_file.write_text(json.dumps({
        "order_routing": [
            {"metric": "P99 Order Latency",      "unit": "ms",    "warn": 100,   "critical": 200,   "notes": "End-to-end: FIX in → exchange out"},
            {"metric": "Order Error Rate",        "unit": "%",     "warn": 0.5,   "critical": 2.0,   "notes": "% of orders rejected or errored"},
            {"metric": "Orders Per Second",       "unit": "rps",   "warn": None,  "critical": None,  "notes": "Alert on unusual drops or spikes"},
            {"metric": "FIX Session Connected",   "unit": "bool",  "warn": None,  "critical": 0,     "notes": "0 = disconnected = immediate alert"},
        ],
        "market_data": [
            {"metric": "Feed Gap Count",          "unit": "count", "warn": 1,     "critical": 5,     "notes": "Any gap = investigate; >5/min = escalate"},
            {"metric": "Book Staleness",          "unit": "s",     "warn": 5,     "critical": 30,    "notes": "Seconds since last update per symbol"},
            {"metric": "Tick Rate",               "unit": "ticks/s","warn": None, "critical": None,  "notes": "Alert on drop to 0 (feed disconnected)"},
        ],
        "risk_and_positions": [
            {"metric": "Position Calc Lag",       "unit": "ms",    "warn": 100,   "critical": 500,   "notes": "How stale position data is"},
            {"metric": "Risk Check P99",          "unit": "ms",    "warn": 50,    "critical": 100,   "notes": "Pre-trade risk check latency"},
            {"metric": "Margin Utilization",      "unit": "%",     "warn": 80,    "critical": 95,    "notes": "% of margin limit used"},
        ],
        "infrastructure": [
            {"metric": "JVM Heap Used",           "unit": "%",     "warn": 75,    "critical": 85,    "notes": "Alert before OOM; >85% = GC pressure imminent"},
            {"metric": "Kafka Consumer Lag",      "unit": "msgs",  "warn": 100,   "critical": 500,   "notes": "Per partition; unassigned partition = critical"},
            {"metric": "DB Query P99",            "unit": "ms",    "warn": 500,   "critical": 2000,  "notes": "Slow queries = missing index or lock contention"},
            {"metric": "CPU Utilization",         "unit": "%",     "warn": 70,    "critical": 90,    "notes": "Sustained >90% = runaway process or undersized"},
            {"metric": "Disk Used",               "unit": "%",     "warn": 75,    "critical": 90,    "notes": "Logs fill disk fast — monitor and rotate"},
        ]
    }, indent=2))
    ok(f"KPI reference: {kpis_file}")

    script = DIRS["scripts"] / "kpi_dashboard.py"
    script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"M-05: Print a trading system KPI reference dashboard.\"\"\"
import json

KPIS_FILE = "{kpis_file}"

with open(KPIS_FILE) as f:
    categories = json.load(f)

for category, kpis in categories.items():
    print(f"\\n=== {{category.upper().replace('_',' ')}} ===")
    print(f"  {{' METRIC':<30}} {{' WARN':>10}} {{' CRITICAL':>10}} {{' UNIT':<10}}  NOTES")
    print(f"  {{'-'*30}} {{'-'*10}} {{'-'*10}} {{'-'*10}}  {{'-'*40}}")
    for kpi in kpis:
        warn = str(kpi['warn']) if kpi['warn'] is not None else "—"
        crit = str(kpi['critical']) if kpi['critical'] is not None else "—"
        print(f"  {{kpi['metric']:<30}} {{warn:>10}} {{crit:>10}} {{kpi['unit']:<10}}  {{kpi['notes']}}")

print(\"\"\"
Monitoring Philosophy for Trading Systems:
  Alert on SYMPTOMS (latency, error rate) not just causes (CPU, memory).
  Cause metrics (heap %, CPU) help root cause analysis but don't always page.
  Symptom metrics (p99 > SLA, FIX session down, fill count = 0) should always page.

Runbook link in every alert:
  Every CloudWatch alarm should have a runbook URL in the description.
  The runbook tells on-call exactly what to check and how to mitigate.

Dashboard hierarchy:
  Top level  : is the system working? (fills flowing, FIX sessions up, no alerts)
  Service    : latency, error rate, throughput per service
  Infra      : JVM, Kafka, DB per service
  Drill-down : logs, thread dumps, GC logs when you need root cause
\"\"\")
""")
    ok(f"KPI dashboard script: {script}")

    print(f"""
{BOLD}── Run the KPI dashboard: ──────────────────────────────{RESET}
{CYAN}       python3 {script}{RESET}

{BOLD}── The most important metrics to know ──────────────────{RESET}
  FIX session connected   : 0 = trading is DOWN, page immediately
  Order p99 latency       : >200ms = SLA breach, investigate now
  Kafka consumer lag      : >500 = service falling behind, check GC/CPU
  JVM heap >85%%           : GC pressure, OOM imminent
  Feed gap count          : any gap = stale order book risk

{BOLD}── When you get paged ───────────────────────────────────{RESET}
  1. What metric triggered? (symptom)
  2. What else is firing? (find the root cause in the cascade)
  3. When did it start? (correlate with deployments, market events)
  4. What is the blast radius? (how many traders/orders affected?)
  5. Mitigate first, root cause second
""")


def launch_scenario_99():
    header("Scenario 99 — ALL Monitoring Scenarios")
    for fn in [launch_scenario_1, launch_scenario_2, launch_scenario_3,
               launch_scenario_4, launch_scenario_5]:
        fn()
        time.sleep(0.2)


def teardown():
    header("Tearing Down Monitoring Lab")
    remove_lab_dir(LAB_ROOT)


SCENARIO_MAP = {
    1:  (launch_scenario_1, "M-01  Latency percentiles p50/p95/p99"),
    2:  (launch_scenario_2, "M-02  CloudWatch metrics dashboard"),
    3:  (launch_scenario_3, "M-03  Prometheus & Grafana basics"),
    4:  (launch_scenario_4, "M-04  Alert triage workflow"),
    5:  (launch_scenario_5, "M-05  Trading system KPIs & thresholds"),
    99: (launch_scenario_99, "     ALL scenarios"),
}


def main():
    run_menu(SCENARIO_MAP, "Monitoring & Observability Challenge Lab",
             setup_fn=create_dirs, teardown_fn=teardown, status_fn=show_status,
             script_name="lab_monitoring.py")


if __name__ == "__main__":
    main()
