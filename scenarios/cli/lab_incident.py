#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — HFT-Style Trading Incident
============================================================
A realistic market-open cascade failure modelled on the skills tested in the
HFT Application Support Engineer role (equities / data pipelines / order routing).

Technologies exercised: Kafka, FIX protocol, Kubernetes, Argo Workflows,
                        HDF5 tick data, AWS CloudWatch, Java stack traces,
                        Python scripting, SQL position validation, Linux triage.

SCENARIO:
  1   TI-01  09:30 cascade — Kafka disk → stale MD → risk crash → FIX gap → fills missing
  99        same as 1
"""

import os, sys, json, shutil, sqlite3
from pathlib import Path
from datetime import datetime, timedelta

LAB_ROOT = Path("/tmp/lab_incident")
DIRS = {
    "logs":    LAB_ROOT / "logs",
    "kafka":   LAB_ROOT / "kafka",
    "k8s":     LAB_ROOT / "k8s",
    "aws":     LAB_ROOT / "aws",
    "hdf5":    LAB_ROOT / "hdf5",
    "db":      LAB_ROOT / "db",
    "scripts": LAB_ROOT / "scripts",
    "pids":    LAB_ROOT / "run",
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

def create_dirs():  _create_dirs(DIRS)
def show_status():  _show_status(DIRS["scripts"], "Incident Lab")
def teardown():
    header("Tearing Down Incident Lab")
    remove_lab_dir(LAB_ROOT)


# ══════════════════════════════════════════════
#  FILE WRITERS
# ══════════════════════════════════════════════

def _write_incident_timeline():
    p = DIRS["logs"] / "incident_timeline.log"
    p.write_text("""\
09:29:45 [INFO]  market-data-feed  Starting up — loading reference ticks from HDF5 /data/ticks/2026-05-04.h5
09:29:47 [WARN]  market-data-feed  HDF5 /data/ticks/2026-05-04.h5 NOT FOUND — falling back to stale cache 2026-05-03.h5
09:29:48 [INFO]  market-data-feed  Stale cache loaded: 3,847 symbols. MISSING: NVTK, RDDT (IPO today)
09:29:58 [INFO]  oms-gateway       FIX session EXCHANGE_A connected SeqNum=8841
09:29:59 [INFO]  oms-gateway       FIX session EXCHANGE_B connected SeqNum=3204
09:30:00 [INFO]  market-open       Bell — activating real-time risk checks
09:30:01 [ERROR] kafka-producer    broker-0:9092 REFUSED produce — disk 98.7% full (NotEnoughReplicasException)
09:30:01 [ERROR] kafka-producer    broker-0:9092 REFUSED produce — disk 98.7% full (NotEnoughReplicasException)
09:30:02 [WARN]  kafka-producer    Retrying produce to broker-1 (fallback)
09:30:03 [ERROR] oms-gateway       SIGABRT — core dumped PID=18822 (triggered by risk-engine null cascade)
09:30:03 [INFO]  oms-gateway       Restart initiated PID=18901 SeqNum reset to 1
09:30:04 [WARN]  fix-session       EXCHANGE_A: expected SeqNum=8842 received 1 — sending ResendRequest 8842-0
09:30:05 [ERROR] fix-session       EXCHANGE_A: Order ORD-20415 REJECTED — session not established
09:30:05 [ERROR] fix-session       EXCHANGE_A: Order ORD-20416 REJECTED — session not established
09:30:06 [ERROR] fix-session       EXCHANGE_A: Order ORD-20417 REJECTED — session not established
09:30:07 [ERROR] risk-engine       java.lang.NullPointerException: reference price null for symbol NVTK
09:30:07 [ERROR] risk-engine       java.lang.NullPointerException: reference price null for symbol RDDT
09:30:08 [WARN]  kafka-consumer    group=md-feed-handler topic=market-data.equities lag=51,234
09:30:09 [ERROR] k8s               risk-engine pod CrashLoopBackOff (exit code 1, 3rd restart)
09:30:10 [ALARM] cloudwatch        OrderRoutingLatency_p99 = 847 ms  [threshold 200 ms]
09:30:12 [ERROR] argo-workflows    hdf5-tick-backfill FAILED — OOMKilled (limit=512Mi actual=1.2Gi)
09:30:15 [ALARM] cloudwatch        KafkaConsumerLag > 50,000 on market-data.equities
09:30:20 [ALARM] pagerduty         P1 — TRADING HALT: 0 fills in last 90 s. Escalation chain notified.
09:30:22 [INFO]  on-call           YOU picked up the PagerDuty alert. Good luck.
""")
    ok(f"Written {p.name}  (master timeline — read this first)")


def _write_market_data_feed_log():
    p = DIRS["logs"] / "market_data_feed.log"
    p.write_text("""\
2026-05-04 09:29:45.001 INFO  [MDFeedHandler] Initializing HDF5 tick store reader
2026-05-04 09:29:45.102 INFO  [HDF5Reader    ] Opening /data/ticks/2026-05-04.h5
2026-05-04 09:29:45.205 ERROR [HDF5Reader    ] FileNotFoundError: /data/ticks/2026-05-04.h5
2026-05-04 09:29:45.206 WARN  [MDFeedHandler ] Falling back to previous session: /data/ticks/2026-05-03.h5
2026-05-04 09:29:47.841 INFO  [HDF5Reader    ] Loaded 3,847 symbols from stale cache (session: 2026-05-03)
2026-05-04 09:29:47.842 WARN  [MDFeedHandler ] 2 symbols NOT in stale cache: [NVTK, RDDT]
2026-05-04 09:29:47.843 WARN  [MDFeedHandler ] Reference prices for NVTK, RDDT will be NULL
2026-05-04 09:29:58.001 INFO  [MDFeedHandler ] Kafka producer connected to cluster (broker-1, broker-2)
2026-05-04 09:30:00.000 INFO  [MDFeedHandler ] Market open — streaming ticks to market-data.equities
2026-05-04 09:30:01.003 ERROR [KafkaProducer ] NotEnoughReplicasException: broker-0 disk full (98.7%)
2026-05-04 09:30:01.005 WARN  [KafkaProducer ] Produce retry 1/3 — waiting 100ms
2026-05-04 09:30:01.107 ERROR [KafkaProducer ] NotEnoughReplicasException: broker-0 disk full (98.7%)
2026-05-04 09:30:01.110 ERROR [KafkaProducer ] Max retries exceeded for partition market-data.equities-3
2026-05-04 09:30:01.112 ERROR [KafkaProducer ] Dropping tick: AAPL  bid=189.51 ask=189.53 (partition 3, broker-0)
2026-05-04 09:30:08.004 WARN  [MDFeedHandler ] Consumer group md-feed-handler lag=51234 — downstream slow
2026-05-04 09:30:08.006 WARN  [MDFeedHandler ] Downstream consumers may be processing stale ticks
""")
    ok(f"Written {p.name}")


def _write_risk_engine_java_log():
    p = DIRS["logs"] / "risk_engine_java.log"
    p.write_text("""\
2026-05-04 09:30:06.999 INFO  [RiskEngine    ] Market open received — enabling live risk checks
2026-05-04 09:30:07.002 ERROR [PriceValidator] Null reference price for symbol NVTK
java.lang.NullPointerException: Cannot invoke "Double.doubleValue()" because "refPrice" is null
        at com.hft.risk.PriceValidator.validatePrice(PriceValidator.java:142)
        at com.hft.risk.RiskCheckService.runPreTradeChecks(RiskCheckService.java:87)
        at com.hft.risk.RiskEngine.onOrder(RiskEngine.java:203)
        at com.hft.oms.OrderRouter.routeOrder(OrderRouter.java:55)
        at java.base/java.util.concurrent.ThreadPoolExecutor.runWorker(Unknown Source)

2026-05-04 09:30:07.003 ERROR [PriceValidator] Null reference price for symbol RDDT
java.lang.NullPointerException: Cannot invoke "Double.doubleValue()" because "refPrice" is null
        at com.hft.risk.PriceValidator.validatePrice(PriceValidator.java:142)
        at com.hft.risk.RiskCheckService.runPreTradeChecks(RiskCheckService.java:87)
        at com.hft.risk.RiskEngine.onOrder(RiskEngine.java:203)
        at com.hft.oms.OrderRouter.routeOrder(OrderRouter.java:55)

2026-05-04 09:30:07.004 FATAL [RiskEngine    ] Uncaught exception in order handler thread — shutting down
2026-05-04 09:30:07.005 INFO  [RiskEngine    ] Flushing in-flight orders to dead-letter queue...
2026-05-04 09:30:07.006 INFO  [RiskEngine    ] 6 orders written to dead-letter topic: risk-engine.dlq
2026-05-04 09:30:07.010 INFO  [RiskEngine    ] JVM exit code 1
""")
    ok(f"Written {p.name}  (Java stack trace — NPE on null reference prices)")


def _write_fix_session_log():
    SOH = "|"  # use pipe for readability instead of actual SOH \x01
    p = DIRS["logs"] / "fix_session_EXCHANGE_A.log"
    lines = [
        "# FIX 4.4 Session Log — FIRM_OMS → EXCHANGE_A",
        "# Format: DIRECTION TIMESTAMP  RAW_MESSAGE (| substituted for SOH)",
        "",
        f"IN  09:29:58.001  8=FIX.4.4|9=73|35=A|49=EXCHANGE_A|56=FIRM_OMS|34=8841|52=20260504-09:29:58|98=0|108=30|10=042|",
        f"OUT 09:29:58.002  8=FIX.4.4|9=73|35=A|49=FIRM_OMS|56=EXCHANGE_A|34=8841|52=20260504-09:29:58|98=0|108=30|10=039|",
        f"",
        f"# ... 13 orders sent, all acked (SeqNum 8842 through 8854) ...",
        f"",
        f"# oms-gateway crashed at 09:30:03 — restarted with SeqNum=1",
        f"",
        f"OUT 09:30:03.412  8=FIX.4.4|9=73|35=A|49=FIRM_OMS|56=EXCHANGE_A|34=1|52=20260504-09:30:03|98=0|108=30|10=044|",
        f"IN  09:30:04.001  8=FIX.4.4|9=85|35=2|49=EXCHANGE_A|56=FIRM_OMS|34=8842|52=20260504-09:30:04|7=8842|16=0|10=188|",
        f"# ^ tag 35=2 ResendRequest: BeginSeqNo=8842 EndSeqNo=0 (request all missing)",
        f"",
        f"# oms-gateway has NO store of sent messages — cannot replay SeqNum 8842-8854",
        f"",
        f"OUT 09:30:04.100  8=FIX.4.4|9=68|35=D|49=FIRM_OMS|56=EXCHANGE_A|34=2|11=ORD-20415|55=AAPL|54=1|38=500|40=2|44=189.51|10=077|",
        f"IN  09:30:05.001  8=FIX.4.4|9=95|35=3|49=EXCHANGE_A|56=FIRM_OMS|34=8843|52=20260504-09:30:05|45=2|58=MsgSeqNum too low|10=201|",
        f"# ^ tag 35=3 Reject: RefSeqNum=2 Text='MsgSeqNum too low, expected 8855'",
        f"",
        f"OUT 09:30:05.101  8=FIX.4.4|9=68|35=D|49=FIRM_OMS|56=EXCHANGE_A|34=3|11=ORD-20416|55=TSLA|54=2|38=200|40=1|10=091|",
        f"IN  09:30:05.201  8=FIX.4.4|9=95|35=3|49=EXCHANGE_A|56=FIRM_OMS|34=8844|52=20260504-09:30:05|45=3|58=MsgSeqNum too low|10=211|",
        f"",
        f"# Session recovered at 09:32:47 after SeqNum reset negotiation with EXCHANGE_A",
        f"OUT 09:32:47.001  8=FIX.4.4|9=85|35=4|49=FIRM_OMS|56=EXCHANGE_A|34=4|52=20260504-09:32:47|123=Y|36=8855|10=088|",
        f"# ^ tag 35=4 SequenceReset GapFill: NewSeqNo=8855 (fill the gap — no replay possible)",
        f"IN  09:32:47.500  8=FIX.4.4|9=45|35=0|49=EXCHANGE_A|56=FIRM_OMS|34=8855|52=20260504-09:32:47|10=099|",
        f"# ^ Heartbeat — session re-established at SeqNum 8855",
        f"",
        f"# 14 orders (ORD-20415 through ORD-20428) were rejected during the 2m42s gap.",
        f"# These orders were NOT filled. Check positions DB for exposure gaps.",
    ]
    p.write_text("\n".join(lines) + "\n")
    ok(f"Written {p.name}  (FIX log — sequence gap 8842-8854, 14 rejected orders)")


def _write_kafka_snapshot():
    data = {
        "snapshot_time": "2026-05-04T09:30:08",
        "note": "Captured by monitoring agent. lag=0 for risk-engine means pod is DOWN, not caught up.",
        "consumer_groups": [
            {
                "group": "md-feed-handler",
                "topic": "market-data.equities",
                "partitions": 12,
                "lag_total": 51234,
                "lag_per_partition": [4287, 4301, 4388, 4292, 4341, 4299, 4287, 4408, 4273, 4289, 4301, 4268],
                "last_committed_offset": 8824501,
                "log_end_offset": 8875735,
                "consumer_host": "md-feed-handler-7d9f4b-xkp2m"
            },
            {
                "group": "risk-engine",
                "topic": "market-data.equities",
                "partitions": 12,
                "lag_total": 0,
                "note": "WARNING: lag=0 because consumer is INACTIVE (pod down) — offsets frozen",
                "last_committed_offset": 8820014,
                "log_end_offset": 8875735,
                "consumer_host": None
            },
            {
                "group": "order-router",
                "topic": "order-events",
                "partitions": 4,
                "lag_total": 847,
                "lag_per_partition": [203, 198, 221, 225],
                "last_committed_offset": 204112,
                "log_end_offset": 204959,
                "consumer_host": "order-router-6c8d7f-bnq91"
            }
        ],
        "broker_health": {
            "broker-0": {
                "status": "DEGRADED",
                "disk_used_pct": 98.7,
                "disk_used_gb": 987,
                "disk_total_gb": 1000,
                "leader_partitions": 4,
                "issue": "Disk full — refusing new produce requests. Old segment logs not purged."
            },
            "broker-1": {
                "status": "healthy",
                "disk_used_pct": 41.2,
                "disk_used_gb": 412,
                "disk_total_gb": 1000,
                "leader_partitions": 4
            },
            "broker-2": {
                "status": "healthy",
                "disk_used_pct": 39.8,
                "disk_used_gb": 398,
                "disk_total_gb": 1000,
                "leader_partitions": 4
            }
        },
        "topic_retention": {
            "market-data.equities": {
                "retention_ms": 604800000,
                "note": "7-day retention set. broker-0 has 6.8 days of uncompacted segments — DELETE THESE."
            },
            "order-events": {"retention_ms": 86400000},
            "risk-engine.dlq": {"retention_ms": 2592000000, "note": "Dead-letter queue — check this!"}
        }
    }
    p = DIRS["kafka"] / "consumer_lag_snapshot.json"
    p.write_text(json.dumps(data, indent=2))
    ok(f"Written {p.name}  (lag=51k on md-feed-handler, broker-0 disk 98.7%)")


def _write_k8s_output():
    pods = DIRS["k8s"] / "kubectl_get_pods.txt"
    pods.write_text("""\
NAMESPACE   NAME                              READY   STATUS             RESTARTS   AGE
trading     risk-engine-7f8b9d-x4pq2          0/1     CrashLoopBackOff   5          4m32s
trading     oms-gateway-6c7d8f-bnq91           1/1     Running            1          4m29s
trading     md-feed-handler-7d9f4b-xkp2m       1/1     Running            0          6h12m
trading     order-router-6c8d7f-bnq91          1/1     Running            0          6h12m
trading     position-service-5b6c7d-mnp34      1/1     Running            0          6h12m
argo        hdf5-tick-backfill-wf-z9xk2        0/1     OOMKilled          0          8m14s
argo        hdf5-tick-backfill-wf-retry-1       0/1     Pending            0          1m05s
monitoring  prometheus-0                        1/1     Running            0          2d14h
""")
    ok(f"Written {pods.name}  (risk-engine CrashLoopBackOff, Argo OOMKilled)")

    describe = DIRS["k8s"] / "risk_engine_pod_describe.txt"
    describe.write_text("""\
Name:             risk-engine-7f8b9d-x4pq2
Namespace:        trading
Node:             node-3 / 10.0.1.43
Status:           Running (CrashLoopBackOff)
Image:            registry.hft.internal/risk-engine:v4.17.2
Java Version:     17.0.10 (Eclipse Temurin)

Limits:
  cpu:     2000m
  memory:  4Gi
Requests:
  cpu:     500m
  memory:  2Gi

Environment:
  HDF5_TICK_PATH:        /data/ticks/2026-05-04.h5
  KAFKA_BOOTSTRAP:       broker-0:9092,broker-1:9092,broker-2:9092
  RISK_LEVEL:            LIVE
  REFERENCE_DATA_SOURCE: hdf5

Last State:
  State:      Terminated
  Reason:     Error
  Exit Code:  1
  Started:    Mon, 04 May 2026 09:30:07 UTC
  Finished:   Mon, 04 May 2026 09:30:07 UTC

Events:
  Type     Reason     Age    Message
  ----     ------     ---    -------
  Warning  BackOff    4m32s  Back-off restarting failed container
  Normal   Pulled     4m32s  Container image already present
  Warning  Failed     4m32s  Error: failed to start — exit code 1
  Warning  Failed     3m28s  Error: failed to start — exit code 1
  Warning  Failed     2m24s  Error: failed to start — exit code 1
  Warning  Failed     1m18s  Error: failed to start — exit code 1
  Warning  Failed     12s    Error: failed to start — exit code 1

Hint: risk-engine exits immediately because HDF5_TICK_PATH does not exist.
      Once hdf5-tick-backfill Workflow succeeds and writes the file, this pod
      will start cleanly. Delete the pod to force an immediate restart attempt.
""")
    ok(f"Written {describe.name}")

    argo_wf = DIRS["k8s"] / "argo_workflow_hdf5_backfill.yaml"
    argo_wf.write_text("""\
apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  name: hdf5-tick-backfill-wf-z9xk2
  namespace: argo
  labels:
    workflow-type: daily-backfill
    schedule: "09:00 ET"
spec:
  entrypoint: backfill-ticks
  templates:
  - name: backfill-ticks
    container:
      image: registry.hft.internal/hdf5-backfill:v2.3.1
      command: [python3, backfill.py, --date, "2026-05-04", --symbols, ALL]
      resources:
        limits:
          memory: 512Mi    # <── ROOT CAUSE: 3 days of ALL symbols requires ~1.4 Gi
          cpu: 1000m
        requests:
          memory: 256Mi
          cpu: 500m
      env:
      - name: OUTPUT_PATH
        value: /data/ticks/2026-05-04.h5
      - name: SOURCE_BUCKET
        value: s3://hft-market-data-prod/equities/ticks/

status:
  phase: Failed
  message: "OOMKilled"
  startedAt: "2026-05-04T09:22:00Z"
  finishedAt: "2026-05-04T09:30:12Z"
  nodes:
    hdf5-tick-backfill-wf-z9xk2:
      phase: Failed
      message: "OOMKilled: container exceeded memory limit 512Mi (actual usage: 1.2Gi)"

# FIX: Increase memory limit to 2Gi and re-submit
# kubectl patch workflow hdf5-tick-backfill-wf-z9xk2 -n argo ...
# OR: argo submit hdf5-tick-backfill.yaml --parameter memory=2Gi
""")
    ok(f"Written {argo_wf.name}  (OOM limit 512Mi, needed 1.2Gi)")


def _write_cloudwatch_alarms():
    alarms = DIRS["aws"] / "cloudwatch_active_alarms.json"
    alarms.write_text(json.dumps({
        "MetricAlarms": [
            {
                "AlarmName": "OrderRoutingLatency-p99",
                "AlarmDescription": "Order routing end-to-end latency p99 > 200ms",
                "StateValue": "ALARM",
                "StateReason": "Threshold Crossed: 1 data point (847ms) > 200ms",
                "MetricName": "OrderRoutingLatency",
                "Namespace": "HFT/Trading",
                "Statistic": "p99",
                "Threshold": 200.0,
                "ActualValue": 847.0,
                "Unit": "Milliseconds",
                "StateUpdatedTimestamp": "2026-05-04T09:30:10Z",
                "AlarmActions": ["arn:aws:sns:us-east-1:123456789:trading-pagerduty"],
                "Hint": "High latency caused by order-router retrying rejected orders."
            },
            {
                "AlarmName": "KafkaConsumerLag-md-feed-handler",
                "AlarmDescription": "Consumer group md-feed-handler lag on market-data.equities > 10000",
                "StateValue": "ALARM",
                "StateReason": "Threshold Crossed: lag=51234 > 10000",
                "MetricName": "KafkaConsumerLag",
                "Namespace": "HFT/Kafka",
                "Threshold": 10000,
                "ActualValue": 51234,
                "StateUpdatedTimestamp": "2026-05-04T09:30:15Z",
                "AlarmActions": ["arn:aws:sns:us-east-1:123456789:trading-pagerduty"]
            },
            {
                "AlarmName": "RiskEnginePodRestarts",
                "AlarmDescription": "risk-engine pod restart count > 2 in 5 minutes",
                "StateValue": "ALARM",
                "StateReason": "CrashLoopBackOff — 5 restarts in 4m32s",
                "MetricName": "PodRestartCount",
                "Namespace": "HFT/Kubernetes",
                "Threshold": 2,
                "ActualValue": 5,
                "StateUpdatedTimestamp": "2026-05-04T09:30:09Z"
            },
            {
                "AlarmName": "FillRate-Equities",
                "AlarmDescription": "Equity fill rate < 80% of submitted orders",
                "StateValue": "ALARM",
                "StateReason": "Fill rate = 0% (0/14 orders filled since 09:30:03)",
                "MetricName": "FillRate",
                "Namespace": "HFT/Trading",
                "Threshold": 80.0,
                "ActualValue": 0.0,
                "StateUpdatedTimestamp": "2026-05-04T09:30:20Z"
            }
        ]
    }, indent=2))
    ok(f"Written {alarms.name}  (4 active alarms — latency, Kafka lag, pod restarts, fill rate)")

    metrics = DIRS["aws"] / "latency_metrics_last_10min.json"
    metrics.write_text(json.dumps({
        "MetricDataResults": [
            {
                "Label": "OrderRoutingLatency p50",
                "Timestamps": ["09:20", "09:21", "09:22", "09:23", "09:24",
                               "09:25", "09:26", "09:27", "09:28", "09:29",
                               "09:30", "09:31", "09:32"],
                "Values":     [18, 19, 17, 22, 18, 20, 21, 19, 18, 20, 312, 589, 421],
                "Unit": "Milliseconds"
            },
            {
                "Label": "OrderRoutingLatency p99",
                "Timestamps": ["09:20", "09:21", "09:22", "09:23", "09:24",
                               "09:25", "09:26", "09:27", "09:28", "09:29",
                               "09:30", "09:31", "09:32"],
                "Values":     [42, 45, 39, 51, 44, 47, 48, 43, 41, 46, 847, 934, 712],
                "Unit": "Milliseconds",
                "Hint": "Spike at 09:30 — caused by order-router retrying rejected FIX orders."
            }
        ]
    }, indent=2))
    ok(f"Written {metrics.name}")


def _write_hdf5_marker():
    marker = DIRS["hdf5"] / "2026-05-04.h5.MISSING"
    marker.write_text("""\
This file marks that the HDF5 tick store for 2026-05-04 was NOT produced.

The Argo Workflow hdf5-tick-backfill-wf-z9xk2 OOMKilled before writing the output.
The risk-engine pod reads from this path at startup and exits (code 1) if absent.

Root cause: memory limit 512Mi is too low for --symbols ALL (~3,849 symbols × 1 day).
Fix:        Resubmit the workflow with memory=2Gi.

Expected output path:  /data/ticks/2026-05-04.h5
S3 source bucket:      s3://hft-market-data-prod/equities/ticks/2026-05-04/

Command to resubmit (once you have kubectl/argo access):
  argo submit /argo/workflows/hdf5-tick-backfill.yaml \\
       -p date=2026-05-04 \\
       -p memory=2Gi \\
       -n argo
""")
    ok(f"Written {marker.name}  (explains missing HDF5 file)")


def _write_positions_db():
    db_path = DIRS["db"] / "positions.db"
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id     TEXT PRIMARY KEY,
            symbol       TEXT NOT NULL,
            side         TEXT NOT NULL,
            quantity     INTEGER NOT NULL,
            price        REAL,
            order_type   TEXT NOT NULL,
            status       TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            filled_at    TEXT,
            fill_price   REAL,
            reject_reason TEXT,
            exchange     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS positions (
            symbol       TEXT PRIMARY KEY,
            quantity     INTEGER NOT NULL,
            avg_cost     REAL NOT NULL,
            last_updated TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS fills (
            fill_id      TEXT PRIMARY KEY,
            order_id     TEXT NOT NULL,
            symbol       TEXT NOT NULL,
            side         TEXT NOT NULL,
            quantity     INTEGER NOT NULL,
            fill_price   REAL NOT NULL,
            filled_at    TEXT NOT NULL,
            exchange     TEXT NOT NULL
        );
    """)

    # Pre-market positions
    positions = [
        ("AAPL",  5000, 187.32, "2026-05-03 16:00:00"),
        ("GOOGL", 1200, 174.88, "2026-05-03 16:00:00"),
        ("MSFT",  3000, 378.45, "2026-05-03 16:00:00"),
        ("TSLA",  2500, 246.70, "2026-05-03 16:00:00"),
        ("NVDA",  4000, 502.14, "2026-05-03 16:00:00"),
        ("SPY",   8000,  521.88, "2026-05-03 16:00:00"),
        ("NVTK",     0,   0.00, "2026-05-03 16:00:00"),  # IPO today — no position
        ("RDDT",     0,   0.00, "2026-05-03 16:00:00"),  # IPO today — no position
    ]
    c.executemany("INSERT OR REPLACE INTO positions VALUES (?,?,?,?)", positions)

    # Orders — mix of good fills and gap-period rejections
    orders = [
        # Pre-incident fills (all good)
        ("ORD-20400", "AAPL",  "BUY",  500, 189.51, "LIMIT",  "FILLED",  "09:29:48", "09:29:49", 189.51, None,         "EXCHANGE_A"),
        ("ORD-20401", "GOOGL", "SELL", 200, 175.10, "LIMIT",  "FILLED",  "09:29:50", "09:29:51", 175.09, None,         "EXCHANGE_A"),
        ("ORD-20402", "MSFT",  "BUY",  300, 380.00, "LIMIT",  "FILLED",  "09:29:52", "09:29:53", 379.98, None,         "EXCHANGE_B"),
        ("ORD-20403", "SPY",   "SELL", 1000, 521.50, "LIMIT", "FILLED",  "09:29:55", "09:29:56", 521.48, None,         "EXCHANGE_A"),
        # Gap-period rejections (09:30:03 — 09:32:47)
        ("ORD-20415", "AAPL",  "BUY",  500, 189.51, "LIMIT",  "REJECTED","09:30:05", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20416", "TSLA",  "SELL", 200, None,   "MARKET", "REJECTED","09:30:05", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20417", "NVDA",  "BUY",  400, 503.00, "LIMIT",  "REJECTED","09:30:06", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20418", "GOOGL", "BUY",  300, 175.20, "LIMIT",  "REJECTED","09:30:07", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20419", "MSFT",  "SELL", 200, 380.50, "LIMIT",  "REJECTED","09:30:08", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20420", "SPY",   "BUY",  2000,521.90, "LIMIT",  "REJECTED","09:30:09", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20421", "NVTK",  "BUY",  5000, 48.50, "LIMIT",  "REJECTED","09:30:10", None,        None,  "MsgSeqNum too low + no reference price", "EXCHANGE_A"),
        ("ORD-20422", "RDDT",  "BUY",  3000, 72.10, "LIMIT",  "REJECTED","09:30:11", None,        None,  "MsgSeqNum too low + no reference price", "EXCHANGE_A"),
        ("ORD-20423", "AAPL",  "SELL", 1000,190.00, "LIMIT",  "REJECTED","09:30:15", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20424", "TSLA",  "BUY",  500, 247.00, "LIMIT",  "REJECTED","09:30:18", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20425", "GOOGL", "SELL", 400, 175.80, "LIMIT",  "REJECTED","09:30:21", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20426", "MSFT",  "BUY",  600, 379.50, "LIMIT",  "REJECTED","09:30:25", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20427", "NVDA",  "SELL", 300, 504.00, "LIMIT",  "REJECTED","09:30:30", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        ("ORD-20428", "SPY",   "SELL", 1500,522.00, "LIMIT",  "REJECTED","09:30:35", None,        None,  "MsgSeqNum too low", "EXCHANGE_A"),
        # Post-recovery fills (session restored at 09:32:47)
        ("ORD-20440", "AAPL",  "BUY",  500, 189.75, "LIMIT",  "FILLED",  "09:33:00", "09:33:01", 189.75, None,         "EXCHANGE_A"),
        ("ORD-20441", "TSLA",  "SELL", 200, None,   "MARKET", "FILLED",  "09:33:02", "09:33:03", 247.30, None,         "EXCHANGE_A"),
    ]
    c.executemany(
        "INSERT OR REPLACE INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", orders)

    # Fills table
    fills = [
        ("FILL-1001", "ORD-20400", "AAPL",  "BUY",  500,  189.51, "09:29:49", "EXCHANGE_A"),
        ("FILL-1002", "ORD-20401", "GOOGL", "SELL", 200,  175.09, "09:29:51", "EXCHANGE_A"),
        ("FILL-1003", "ORD-20402", "MSFT",  "BUY",  300,  379.98, "09:29:53", "EXCHANGE_B"),
        ("FILL-1004", "ORD-20403", "SPY",   "SELL", 1000, 521.48, "09:29:56", "EXCHANGE_A"),
        ("FILL-1005", "ORD-20440", "AAPL",  "BUY",  500,  189.75, "09:33:01", "EXCHANGE_A"),
        ("FILL-1006", "ORD-20441", "TSLA",  "SELL", 200,  247.30, "09:33:03", "EXCHANGE_A"),
    ]
    c.executemany("INSERT OR REPLACE INTO fills VALUES (?,?,?,?,?,?,?,?)", fills)

    conn.commit()
    conn.close()
    ok(f"Written {db_path.name}  (orders, positions, fills tables — 14 rejected orders in gap)")


def _write_scripts():
    # Investigation helper 1: Kafka lag checker
    s1 = DIRS["scripts"] / "check_kafka_lag.py"
    s1.write_text("""\
#!/usr/bin/env python3
\"\"\"
Check consumer lag from the snapshot file.
Usage: python3 check_kafka_lag.py
\"\"\"
import json
from pathlib import Path

snap = json.loads((Path(__file__).parent.parent / "kafka" / "consumer_lag_snapshot.json").read_text())

print("\\n=== Kafka Consumer Lag Summary ===\\n")
for cg in snap["consumer_groups"]:
    lag = cg["lag_total"]
    status = "OK" if lag < 10000 else ("WARN" if lag < 50000 else "CRITICAL")
    host = cg.get("consumer_host") or "INACTIVE"
    print(f"  [{status:<8}] {cg['group']:<25} topic={cg['topic']:<28} lag={lag:>6,}  host={host}")
    if "note" in cg:
        print(f"             NOTE: {cg['note']}")

print("\\n=== Broker Health ===\\n")
for broker, info in snap["broker_health"].items():
    status = "OK" if info["disk_used_pct"] < 80 else ("WARN" if info["disk_used_pct"] < 95 else "CRITICAL")
    print(f"  [{status:<8}] {broker}  disk={info['disk_used_pct']}%  leaders={info['leader_partitions']}")
    if "issue" in info:
        print(f"             ISSUE: {info['issue']}")

print("\\n=== Topic Retention ===\\n")
for topic, cfg in snap["topic_retention"].items():
    ms = cfg["retention_ms"]
    days = ms / 86400000
    print(f"  {topic:<35} retention={days:.1f} days")
    if "note" in cfg:
        print(f"             NOTE: {cfg['note']}")
""")
    ok(f"Written scripts/{s1.name}")

    # Investigation helper 2: Position reconciliation SQL
    s2 = DIRS["scripts"] / "validate_positions.sql"
    s2.write_text("""\
-- Position validation queries for the 09:30 incident
-- Connect with: sqlite3 /tmp/lab_incident/db/positions.db
-- Then: .read /tmp/lab_incident/scripts/validate_positions.sql

-- 1. How many orders were rejected during the gap period (09:30:03 — 09:32:47)?
SELECT COUNT(*) AS rejected_count, SUM(quantity) AS total_qty_missed
FROM orders
WHERE status = 'REJECTED'
  AND submitted_at BETWEEN '09:30:03' AND '09:32:47';

-- 2. Which symbols had the most rejected order volume?
SELECT symbol, side, COUNT(*) AS num_orders, SUM(quantity) AS total_qty
FROM orders
WHERE status = 'REJECTED'
GROUP BY symbol, side
ORDER BY total_qty DESC;

-- 3. Are there positions we intended to change but couldn't?
--    (Compare rejected BUY/SELL quantities vs current position)
SELECT
    p.symbol,
    p.quantity AS current_position,
    COALESCE(SUM(CASE WHEN o.side='BUY'  THEN o.quantity ELSE 0 END), 0) AS intended_buy,
    COALESCE(SUM(CASE WHEN o.side='SELL' THEN o.quantity ELSE 0 END), 0) AS intended_sell,
    p.quantity
      + COALESCE(SUM(CASE WHEN o.side='BUY'  THEN o.quantity ELSE 0 END), 0)
      - COALESCE(SUM(CASE WHEN o.side='SELL' THEN o.quantity ELSE 0 END), 0) AS intended_final
FROM positions p
LEFT JOIN orders o ON p.symbol = o.symbol AND o.status = 'REJECTED'
GROUP BY p.symbol
HAVING intended_buy > 0 OR intended_sell > 0
ORDER BY ABS(intended_buy - intended_sell) DESC;

-- 4. Are fills in the fills table consistent with filled orders?
SELECT
    o.order_id,
    o.symbol,
    o.side,
    o.quantity AS order_qty,
    f.quantity AS fill_qty,
    o.status,
    CASE WHEN f.fill_id IS NULL THEN 'FILL MISSING' ELSE 'OK' END AS reconcile
FROM orders o
LEFT JOIN fills f ON o.order_id = f.order_id
WHERE o.status = 'FILLED';

-- 5. Summary: total P&L exposure from missed fills (use last fill price as proxy)
SELECT
    o.symbol,
    o.side,
    SUM(o.quantity) AS missed_qty,
    ROUND(AVG(f_last.fill_price), 2) AS reference_price,
    ROUND(SUM(o.quantity) * AVG(f_last.fill_price), 2) AS gross_exposure_usd
FROM orders o
JOIN (
    SELECT symbol, AVG(fill_price) AS fill_price FROM fills GROUP BY symbol
) f_last ON o.symbol = f_last.symbol
WHERE o.status = 'REJECTED'
GROUP BY o.symbol, o.side
ORDER BY ABS(gross_exposure_usd) DESC;
""")
    ok(f"Written scripts/{s2.name}  (5 SQL queries for position reconciliation)")

    # Investigation helper 3: FIX session decoder
    s3 = DIRS["scripts"] / "decode_fix_gap.py"
    s3.write_text("""\
#!/usr/bin/env python3
\"\"\"
Parse the FIX session log and summarise the sequence gap and rejected orders.
Usage: python3 decode_fix_gap.py
\"\"\"
from pathlib import Path
import re

log = (Path(__file__).parent.parent / "logs" / "fix_session_EXCHANGE_A.log").read_text()

print("\\n=== FIX Session Gap Analysis — EXCHANGE_A ===\\n")

# Find all rejected lines
rejections = re.findall(r'ORD-\\d+', log)
print(f"  Orders rejected during gap: {len(rejections)}")
for o in rejections:
    print(f"    {o}")

# Find the gap
seq_reset = re.search(r'SeqNum reset to 1', log)
recovery  = re.search(r'SequenceReset GapFill.*?NewSeqNo=(\\d+)', log)
if seq_reset and recovery:
    new_seq = recovery.group(1)
    print(f"\\n  OMS restarted with SeqNum=1 at 09:30:03")
    print(f"  EXCHANGE_A sent ResendRequest for 8842-0 (all missing)")
    print(f"  OMS cannot replay — sent GapFill SequenceReset NewSeqNo={new_seq}")
    print(f"  Session re-established at SeqNum {new_seq} (09:32:47)")

print("\\n  Recommended action:")
print("  1. All rejected orders (ORD-20415..ORD-20428) need manual review")
print("  2. Re-submit any hedges that were not replaced post-recovery")
print("  3. Escalate to dev team: OMS should persist FIX message store across restarts")
print("  4. JIRA ticket: add persistent FIX message store (QuickFIX/J FileStore)")
""")
    ok(f"Written scripts/{s3.name}  (FIX gap analysis script)")


def _write_incident_report_template():
    p = DIRS["logs"] / "INCIDENT_REPORT_TEMPLATE.md"
    p.write_text("""\
# Incident Report — Trading Halt 09:30:03 — 09:32:47 ET

**Date:** 2026-05-04
**Severity:** P1
**Duration:** ~2m44s (09:30:03 — 09:32:47)
**Reporter:**
**Responder(s):**

---

## Summary

_One sentence: what broke, what the user impact was._

> TODO

---

## Timeline

| Time (ET)    | Event                                  | Who        |
|--------------|----------------------------------------|------------|
| 09:29:47     | HDF5 file missing — stale cache used   | automated  |
| 09:30:01     | Kafka broker-0 disk full, produce fails | automated  |
| 09:30:03     | OMS gateway crash, FIX SeqNum reset    | automated  |
| 09:30:05     | Orders rejected (ORD-20415+)           | automated  |
| 09:30:07     | Risk engine NPE on null reference price | automated  |
| 09:30:09     | risk-engine pod CrashLoopBackOff       | automated  |
| 09:30:20     | PagerDuty P1 alert fired               | automated  |
| 09:30:22     | On-call engineer picked up             | YOU        |
| _TODO_       | Kafka disk remediation                 |            |
| _TODO_       | Argo Workflow resubmitted              |            |
| _TODO_       | risk-engine pod restarted              |            |
| _TODO_       | FIX session recovered                  |            |
| _TODO_       | Position reconciliation complete       |            |
| _TODO_       | All alarms cleared                     |            |

---

## Root Cause

_Describe the root cause chain (max 5 bullets)._

> TODO — complete after your investigation.
>
> Hint: trace from the first WARN in incident_timeline.log backward.

---

## Impact

- Orders rejected: **?** (fill in after running validate_positions.sql)
- Symbols affected: **?**
- Duration of trading halt: **2m44s**
- Gross exposure gap (USD): **?** (fill in from SQL query 5)

---

## Remediation Steps Taken

1.
2.
3.
4.

---

## Follow-Up Action Items

| Action                                         | Owner      | Due        |
|------------------------------------------------|------------|------------|
| Increase Argo hdf5-backfill memory limit to 2Gi | Infra/Dev  | 2026-05-05 |
| Add FIX persistent message store (FileStore)   | OMS team   | 2026-05-07 |
| Add pre-market HDF5 availability check to runbook | Support | 2026-05-05 |
| Set Kafka broker-0 retention alert at 80% disk | Platform   | 2026-05-05 |
| Add reference-price null guard in PriceValidator | Java dev | 2026-05-10 |

---

## Lessons Learned

> TODO
""")
    ok(f"Written {p.name}  (fill in during/after the scenario)")


# ══════════════════════════════════════════════
#  SCENARIO LAUNCHER
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario TI-01 — 09:30 Market-Open Cascade Failure")
    print(
        "  You just picked up a P1 PagerDuty alert at 09:30:22 ET.\n"
        "  Zero fills in the last 90 seconds. Trading is halted.\n"
        "  Multiple alarms firing simultaneously. You have 10 minutes\n"
        "  before the trading desk escalates to the CTO.\n"
    )

    create_dirs()
    _write_incident_timeline()
    _write_market_data_feed_log()
    _write_risk_engine_java_log()
    _write_fix_session_log()
    _write_kafka_snapshot()
    _write_k8s_output()
    _write_cloudwatch_alarms()
    _write_hdf5_marker()
    _write_positions_db()
    _write_scripts()
    _write_incident_report_template()

    print(f"""
{BOLD}── Environment ─────────────────────────────────────────{RESET}
{CYAN}  Lab root:    {LAB_ROOT}
  Logs:        {DIRS["logs"]}
  Kafka data:  {DIRS["kafka"]}
  K8s output:  {DIRS["k8s"]}
  AWS alarms:  {DIRS["aws"]}
  Positions:   {DIRS["db"]}/positions.db
  Scripts:     {DIRS["scripts"]}{RESET}

{BOLD}── PHASE 1 — Initial Triage (2 min) ────────────────────{RESET}
  Step 1. Read the master timeline — identify the first failure
{CYAN}       cat {DIRS["logs"]}/incident_timeline.log{RESET}

  Step 2. What CloudWatch alarms are firing?
{CYAN}       python3 -c "import json; [print(a['AlarmName'], a['StateValue'], a['StateReason'][:60]) for a in json.load(open('{DIRS["aws"]}/cloudwatch_active_alarms.json'))['MetricAlarms']]"{RESET}

  Step 3. Check Kubernetes pod status
{CYAN}       cat {DIRS["k8s"]}/kubectl_get_pods.txt{RESET}

  Step 4. Check Kafka consumer lag
{CYAN}       python3 {DIRS["scripts"]}/check_kafka_lag.py{RESET}

{BOLD}── PHASE 2 — Root Cause Investigation ──────────────────{RESET}
  Step 5. Why is HDF5 missing? What failed before market open?
{CYAN}       cat {DIRS["k8s"]}/argo_workflow_hdf5_backfill.yaml
       cat {DIRS["hdf5"]}/2026-05-04.h5.MISSING{RESET}

  Step 6. Why is the risk engine crashing? Read the Java log.
{CYAN}       cat {DIRS["logs"]}/risk_engine_java.log{RESET}

  Step 7. Why is Kafka lag so high? What is wrong with broker-0?
{CYAN}       python3 {DIRS["scripts"]}/check_kafka_lag.py   # look at broker health{RESET}

  Step 8. Read the FIX session log — what happened at 09:30:03?
{CYAN}       cat {DIRS["logs"]}/fix_session_EXCHANGE_A.log
       python3 {DIRS["scripts"]}/decode_fix_gap.py{RESET}

{BOLD}── PHASE 3 — Remediation (in order of priority) ────────{RESET}
  A. Kafka — reduce broker-0 retention to free disk space
{CYAN}       # Real system:
       kafka-configs.sh --bootstrap-server broker-0:9092 \\
         --entity-type topics --entity-name market-data.equities \\
         --alter --add-config retention.ms=3600000
       # Then verify:
       kafka-configs.sh --bootstrap-server broker-0:9092 \\
         --entity-type topics --entity-name market-data.equities --describe{RESET}

  B. Argo Workflow — resubmit with higher memory limit
{CYAN}       # Real system:
       argo submit /argo/workflows/hdf5-tick-backfill.yaml \\
         -p date=2026-05-04 -p memory=2Gi -n argo
       # Monitor:
       argo watch hdf5-tick-backfill-wf-<new-id> -n argo{RESET}

  C. Kubernetes — once HDF5 file exists, restart risk-engine
{CYAN}       # Real system:
       kubectl delete pod risk-engine-7f8b9d-x4pq2 -n trading
       kubectl get pods -n trading -w   # watch it come up{RESET}

  D. FIX session — session auto-recovered via GapFill at 09:32:47
{CYAN}       cat {DIRS["logs"]}/fix_session_EXCHANGE_A.log | grep -A2 "GapFill"{RESET}

{BOLD}── PHASE 4 — Position Validation ───────────────────────{RESET}
  Step 9. Find all rejected orders during the outage window
{CYAN}       sqlite3 {DIRS["db"]}/positions.db < {DIRS["scripts"]}/validate_positions.sql{RESET}

  Step 10. Identify gross exposure gap — do you need to escalate to the desk?
{CYAN}       # Query 5 in validate_positions.sql shows USD exposure by symbol{RESET}

  Step 11. Check the dead-letter queue in Kafka (risk-engine.dlq)
{CYAN}       # Real system:
       kafka-console-consumer.sh --bootstrap-server broker-1:9092 \\
         --topic risk-engine.dlq --from-beginning --max-messages 20{RESET}

{BOLD}── PHASE 5 — Incident Report ────────────────────────────{RESET}
  Step 12. Fill in the incident report template
{CYAN}       $EDITOR {DIRS["logs"]}/INCIDENT_REPORT_TEMPLATE.md{RESET}

{BOLD}── Key diagnostic questions to answer ─────────────────{RESET}
  1. What is the TRUE root cause? (Hint: trace backward from timeline)
  2. Which remediation step unblocks everything else?
  3. Should you wake up the Java dev for the NPE, or is there a workaround?
  4. What guard rails were missing that let this cascade happen?
  5. How would you prevent this from happening tomorrow morning?

{BOLD}── Escalation decision points ───────────────────────────{RESET}
  L1 (you own):   Kafka retention config, pod restart, FIX session, SQL queries
  L2 → Dev team:  Add null guard in PriceValidator.java (NPE fix)
  L2 → Infra:     Argo Workflow memory limits, broker disk alert threshold
  L3 → OMS team:  Persistent FIX message store (QuickFIX/J FileStore)

{BOLD}── Reference commands cheat sheet ──────────────────────{RESET}
{CYAN}  # Kubernetes
  kubectl get pods -n trading
  kubectl describe pod <pod> -n trading
  kubectl logs <pod> -n trading --previous
  kubectl delete pod <pod> -n trading          # force restart

  # Argo Workflows
  argo list -n argo
  argo get <workflow-name> -n argo
  argo logs <workflow-name> -n argo

  # Kafka
  kafka-consumer-groups.sh --bootstrap-server broker-1:9092 --list
  kafka-consumer-groups.sh --bootstrap-server broker-1:9092 \\
      --group md-feed-handler --describe
  kafka-topics.sh --bootstrap-server broker-1:9092 \\
      --topic market-data.equities --describe

  # FIX
  grep "35=3" {DIRS["logs"]}/fix_session_EXCHANGE_A.log   # Rejects
  grep "35=2" {DIRS["logs"]}/fix_session_EXCHANGE_A.log   # ResendRequests

  # SQL
  sqlite3 {DIRS["db"]}/positions.db ".tables"
  sqlite3 {DIRS["db"]}/positions.db "SELECT * FROM orders WHERE status='REJECTED';"

  # AWS CloudWatch
  # Real: aws cloudwatch describe-alarms --state-value ALARM
  cat {DIRS["aws"]}/cloudwatch_active_alarms.json | python3 -m json.tool{RESET}
""")


def launch_scenario_99():
    launch_scenario_1()


# ══════════════════════════════════════════════
#  WIRING
# ══════════════════════════════════════════════

SCENARIO_MAP = {
    1:  (launch_scenario_1,  "TI-01  09:30 cascade — Kafka→HDF5→risk→FIX→positions (HFT-style)"),
    99: (launch_scenario_99, "       same as TI-01"),
}


def main():
    run_menu(SCENARIO_MAP, "Trading Incident Challenge Lab",
             setup_fn=create_dirs, teardown_fn=teardown, status_fn=show_status,
             script_name="lab_incident.py")


if __name__ == "__main__":
    main()
