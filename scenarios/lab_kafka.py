#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Kafka Setup
============================================
Creates the environment for all Kafka challenge scenarios (K1-K6).
Since a real Kafka cluster requires significant infrastructure, this lab
provides realistic simulation: mock brokers, consumer-group snapshots,
working kafka-python producer/consumer scripts, and config files to inspect.

Run with: python3 lab_kafka.py [--scenario N] [--teardown]

SCENARIOS:
  1   K-01  Kafka concepts quiz — config files + reference sheet
  2   K-02  Consumer group lag — snapshot file + analysis scripts
  3   K-03  Topic operations — CLI command reference + mock topic config
  4   K-04  Broker down incident — simulated broker failure logs + response guide
  5   K-05  Python producer + consumer — working kafka-python scripts
  6   K-06  At-least-once vs exactly-once — config examples + explainer
  99        ALL scenarios
"""

import os, sys, time, signal, shutil, json, argparse, subprocess, multiprocessing
from pathlib import Path
from datetime import datetime, timedelta
import random

LAB_ROOT = Path("/tmp/lab_kafka")
DIRS = {
    "config":   LAB_ROOT / "config",
    "logs":     LAB_ROOT / "logs",
    "scripts":  LAB_ROOT / "scripts",
    "data":     LAB_ROOT / "data",
    "pids":     LAB_ROOT / "run",
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
#  SCENARIO 1 — Concepts & Config Files
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario K-01 — Kafka Architecture & Key Concepts")
    print("  Core Kafka concepts every support engineer must know.\n")

    ref = DIRS["config"] / "kafka_reference.md"
    ref.write_text("""\
# Kafka Architecture Reference
=================================

## Core Concepts

TOPIC
  Logical stream of records. Think: a named queue that persists.
  Topics are split into PARTITIONS for parallelism.

PARTITION
  Ordered, immutable sequence of records. Each record has an OFFSET.
  A topic with 12 partitions allows 12 consumers to read in parallel.
  Records with the same KEY always land on the same partition → ordering per key.

OFFSET
  A record's position within a partition. Consumers commit their offset
  to track how far they've read.

BROKER
  A single Kafka server. A cluster has 3+ brokers for HA.
  Each partition has 1 LEADER and N-1 FOLLOWERS (replicas).

REPLICATION FACTOR
  How many copies of each partition exist across brokers.
  RF=3 tolerates 2 broker failures without data loss.

ISR (In-Sync Replicas)
  Replicas that are fully caught up to the leader.
  Producer acks=all means: wait for ALL ISR to confirm write.

CONSUMER GROUP
  A set of consumer instances that together consume a topic.
  Each partition is assigned to exactly ONE consumer in the group.
  Rule: if consumers > partitions, some consumers sit idle.

## Producer Key Settings
  acks=0             Fire and forget. Fast but may lose data.
  acks=1             Leader acknowledges. Lost if leader dies before replica sync.
  acks=all (-1)      All ISR acknowledge. Safest. Required for trading.
  enable.idempotence=true   Deduplicates retried messages (exactly-once per partition).
  retries=3          Retry on transient failure.
  max.in.flight.requests.per.connection=1   Preserves ordering with retries.

## Consumer Key Settings
  auto.offset.reset=earliest   Start from oldest record if no committed offset.
  auto.offset.reset=latest     Start from newest (may miss records during downtime).
  enable.auto.commit=false     Commit offsets manually after processing (safer).
  max.poll.records=500         Batch size per poll().
  max.poll.interval.ms=300000  If consumer doesn't poll within 5min → kicked from group.
  session.timeout.ms=10000     Heartbeat timeout. Broker removes consumer after 10s silence.

## Trading-Specific Patterns
  Symbol-keyed messages:  key=symbol → AAPL always → same partition → ordered fills per symbol
  RF=3, min.insync.replicas=2: tolerates 1 broker down AND guarantees 2 replicas confirm write
  retention.ms=604800000: 7-day replay window for trade reconciliation
""")
    ok(f"Kafka reference sheet: {ref}")

    broker_cfg = DIRS["config"] / "server.properties"
    broker_cfg.write_text("""\
# Kafka Broker Configuration (server.properties)
# ================================================

# Broker identity
broker.id=1
listeners=PLAINTEXT://0.0.0.0:9092
advertised.listeners=PLAINTEXT://kafka-broker-1.trading.internal:9092

# Storage
log.dirs=/var/kafka/logs
num.partitions=12
default.replication.factor=3
min.insync.replicas=2

# Retention
log.retention.hours=168
log.retention.bytes=107374182400
log.segment.bytes=1073741824

# Performance
num.network.threads=8
num.io.threads=16
socket.send.buffer.bytes=102400
socket.receive.buffer.bytes=102400
socket.request.max.bytes=104857600

# ZooKeeper / KRaft
# Old: zookeeper.connect=zk-1:2181,zk-2:2181,zk-3:2181
# New KRaft mode: process.roles=broker,controller
""")
    ok(f"Broker config: {broker_cfg}")

    print(f"""
{BOLD}── Reference files ─────────────────────────────────────{RESET}
{CYAN}       cat {ref}
       cat {broker_cfg}{RESET}

{BOLD}── Key concepts to know cold ────────────────────────────{RESET}
  Q: Why use symbol as message key?
  A: Same key → same partition → ordered fills per symbol.
     Without key → round-robin → AAPL fills interleaved, unordered.

  Q: RF=3 with min.insync.replicas=2 — what does it mean?
  A: 3 copies of data. Producer acks=all waits for 2 ISR to confirm.
     Tolerates 1 broker failure with zero data loss.

  Q: Consumers > partitions — what happens?
  A: Some consumers sit idle (each partition → exactly 1 consumer).
     Fix: increase partition count (cannot decrease without recreating topic).

  Q: What is consumer lag?
  A: LOG-END-OFFSET - CURRENT-OFFSET per partition.
     High lag = consumer not keeping up with producer throughput.
""")


# ══════════════════════════════════════════════
#  SCENARIO 2 — Consumer Group Lag
# ══════════════════════════════════════════════

def launch_scenario_2():
    header("Scenario K-02 — Consumer Group Lag Investigation")
    print("  risk-engine-group is falling behind. Investigate lag.\n")

    # Build a realistic consumer-group snapshot
    lag_data = DIRS["data"] / "consumer_group_describe.txt"
    lag_data.write_text("""\
GROUP              TOPIC             PARTITION  CURRENT-OFFSET  LOG-END-OFFSET  LAG   CONSUMER-ID                       HOST       CLIENT-ID
risk-engine-group  trade-executions  0          10420           10425           5     risk-worker-1-abc123-0            /10.0.1.10  risk-worker-1
risk-engine-group  trade-executions  1          9800            10200           400   risk-worker-2-def456-1            /10.0.1.11  risk-worker-2
risk-engine-group  trade-executions  2          11000           11002           2     risk-worker-1-abc123-0            /10.0.1.10  risk-worker-1
risk-engine-group  trade-executions  3          8500            10300           1800  -                                 -          -
risk-engine-group  trade-executions  4          9100            9105            5     risk-worker-3-ghi789-2            /10.0.1.12  risk-worker-3
risk-engine-group  trade-executions  5          8800            10200           1400  -                                 -          -
""")
    ok(f"Consumer group snapshot: {lag_data}")

    # Analysis script
    analyze = DIRS["scripts"] / "analyze_lag.py"
    analyze.write_text(f"""\
#!/usr/bin/env python3
\"\"\"Analyze Kafka consumer group lag snapshot.\"\"\"

LAG_FILE  = "{lag_data}"
THRESHOLD = 100

print(f"Analyzing: {{LAG_FILE}}\\n")

total_lag = 0
issues = []

with open(LAG_FILE) as f:
    for i, line in enumerate(f):
        if i == 0: continue  # header
        parts = line.split()
        if len(parts) < 6: continue
        topic, partition, cur, end, lag_str = parts[1], parts[2], parts[3], parts[4], parts[5]
        consumer = parts[6] if len(parts) > 6 else "-"
        try:
            lag = int(lag_str)
        except ValueError:
            continue
        total_lag += lag
        flag = ""
        if consumer == "-":
            flag = "🔴 NO CONSUMER"
            issues.append((partition, lag, "unassigned partition — add consumer instance"))
        elif lag > THRESHOLD:
            flag = "⚠  HIGH LAG"
            issues.append((partition, lag, f"consumer {{consumer}} falling behind"))
        elif lag > 50:
            flag = "⚠  ELEVATED"
        else:
            flag = "✅ OK"
        print(f"  Partition {{partition:>2}}  lag={{lag:>6}}  {{consumer[:30]:<30}}  {{flag}}")

print(f"\\nTotal lag across all partitions: {{total_lag}}")
if issues:
    print(f"\\n⚠  {{len(issues)}} issues found:")
    for p, lag, reason in issues:
        print(f"   partition {{p}}: {{reason}} (lag={{lag}})")
    print("\\nRoot cause analysis:")
    print("  Partitions 3,5 have NO CONSUMER (-): group has 3 workers but 6 partitions.")
    print("  Fix: add 3 more consumer instances to risk-engine-group.")
    print("  Partition 1 lagging 400: consumer-2 is slow — check CPU/processing time.")
""")
    ok(f"Analysis script: {analyze}")

    print(f"""
{BOLD}── Consumer group output (simulated): ──────────────────{RESET}
{CYAN}       cat {lag_data}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Read the snapshot and identify issues
{CYAN}       cat {lag_data}{RESET}

  2. Analyse with the Python script
{CYAN}       python3 {analyze}{RESET}

  3. On a real cluster you'd run:
{CYAN}       kafka-consumer-groups.sh \\
         --bootstrap-server localhost:9092 \\
         --group risk-engine-group \\
         --describe{RESET}

{BOLD}── Root causes in this snapshot ────────────────────────{RESET}
  Partitions 3 & 5: CONSUMER = "-" → unassigned. Only 3 workers for 6 partitions.
  Partition 1: lag=400, growing → consumer-2 too slow.
  Fix: add 3 more consumer instances to match partition count.
""")


# ══════════════════════════════════════════════
#  SCENARIO 3 — Topic Operations
# ══════════════════════════════════════════════

def launch_scenario_3():
    header("Scenario K-03 — Kafka Topic Operations")
    print("  Create and inspect a trading topic correctly.\n")

    topic_cfg = DIRS["config"] / "trade_executions_topic.properties"
    topic_cfg.write_text("""\
# Topic configuration for trade-executions
# ==========================================
# Applied at creation:
#   kafka-topics.sh --create --topic trade-executions
#     --partitions 12 --replication-factor 3
#     --config retention.ms=604800000
#     --config min.insync.replicas=2

# Why these values:
# partitions=12: 12 consumers can process in parallel.
#   Partition by symbol prefix → AAPL always → partition 0 (ordering per symbol).
# RF=3: tolerates 2 broker failures. Never lose a trade event.
# min.insync.replicas=2: with acks=all, producer only succeeds if 2+ replicas confirm.
#   Prevents silent data loss when 1 broker is temporarily down.
# retention.ms=604800000 (7 days): downstream systems can replay up to 7 days of trades.

# Topic describe output (what you'd see after creation):
#
# Topic: trade-executions  PartitionCount: 12  ReplicationFactor: 3  Configs: ...
#   Topic: trade-executions  Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,2,3
#   Topic: trade-executions  Partition: 1  Leader: 2  Replicas: 2,3,1  Isr: 2,3,1
#   ... (12 partitions)
""")
    ok(f"Topic config reference: {topic_cfg}")

    cli_ref = DIRS["scripts"] / "kafka_cli_commands.sh"
    cli_ref.write_text("""\
#!/bin/bash
# Kafka CLI commands reference for the challenge lab
# Run these against a real Kafka cluster at localhost:9092

BROKER="localhost:9092"
TOPIC="trade-executions"

# ── Create topic ──────────────────────────────────────────
kafka-topics.sh \\
  --bootstrap-server $BROKER \\
  --create \\
  --topic $TOPIC \\
  --partitions 12 \\
  --replication-factor 3 \\
  --config retention.ms=604800000 \\
  --config min.insync.replicas=2

# ── Describe topic ────────────────────────────────────────
kafka-topics.sh --bootstrap-server $BROKER --describe --topic $TOPIC

# ── List all topics ───────────────────────────────────────
kafka-topics.sh --bootstrap-server $BROKER --list

# ── Produce a test message ────────────────────────────────
echo '{"symbol":"AAPL","qty":100,"side":"BUY","price":185.50}' | \\
  kafka-console-producer.sh \\
    --bootstrap-server $BROKER \\
    --topic $TOPIC \\
    --property "key.separator=:" \\
    --property "parse.key=true"

# ── Consume from beginning ────────────────────────────────
kafka-console-consumer.sh \\
  --bootstrap-server $BROKER \\
  --topic $TOPIC \\
  --from-beginning \\
  --group test-group \\
  --max-messages 10

# ── Check under-replicated partitions ─────────────────────
kafka-topics.sh --bootstrap-server $BROKER --describe --under-replicated-partitions

# ── Delete a topic (CAREFUL in prod!) ─────────────────────
# kafka-topics.sh --bootstrap-server $BROKER --delete --topic $TOPIC
""")
    ok(f"CLI commands reference: {cli_ref}")

    print(f"""
{BOLD}── Config and CLI reference files ──────────────────────{RESET}
{CYAN}       cat {topic_cfg}
       cat {cli_ref}{RESET}

{BOLD}── Study the CLI commands (no Kafka needed to read them) {RESET}
{CYAN}       bash {cli_ref}   # will fail without Kafka — read instead
       cat {cli_ref}{RESET}

{BOLD}── If you have Kafka running locally ───────────────────{RESET}
{CYAN}       # Start ZooKeeper + Kafka (binary install):
       bin/zookeeper-server-start.sh config/zookeeper.properties &
       bin/kafka-server-start.sh config/server.properties &
       # Then run the commands in {cli_ref}{RESET}

{BOLD}── Key interview answers ────────────────────────────────{RESET}
  Q: Why 12 partitions?   → 12 consumers can read in parallel
  Q: Why RF=3?            → Tolerates 2 broker failures, no data loss
  Q: Why acks=all?        → All ISR must confirm → no silent write loss
  Q: Why symbol as key?   → Same symbol → same partition → ordered fills
""")


# ══════════════════════════════════════════════
#  SCENARIO 4 — Broker Down Incident
# ══════════════════════════════════════════════

def launch_scenario_4():
    header("Scenario K-04 — Kafka Broker Down Incident Response")
    print("  broker-2 has gone down. Producers throwing exceptions.\n")

    # Simulate broker logs
    broker2_log = DIRS["logs"] / "kafka-broker-2.log"
    broker2_log.write_text("""\
[2024-01-15 09:28:00,001] INFO  Kafka version: 3.5.0 (kafka.Kafka$)
[2024-01-15 09:28:00,201] INFO  Kafka commitId: abc1234def5678 (kafka.Kafka$)
[2024-01-15 09:28:01,102] INFO  [KafkaServer id=2] started (kafka.server.KafkaServer)
[2024-01-15 09:29:00,010] INFO  [GroupCoordinator 2]: Loading offsets...
[2024-01-15 09:30:00,000] INFO  [ReplicaManager broker=2] Market open — high throughput expected
[2024-01-15 09:30:47,312] WARN  [Log partition=trade-executions-3] Slow log flush: 180ms
[2024-01-15 09:30:48,100] WARN  [Log partition=trade-executions-5] Slow log flush: 240ms
[2024-01-15 09:30:55,444] ERROR [ReplicaFetcherThread-0-1] Error fetching from broker 1: Connection reset
[2024-01-15 09:30:55,450] WARN  [ReplicaManager] broker-2 disk I/O at 95% utilisation
[2024-01-15 09:30:56,001] FATAL [KafkaServer id=2] Fatal error during KafkaServer startup. Prepare to shutdown
[2024-01-15 09:30:56,002] ERROR java.io.IOException: No space left on device
[2024-01-15 09:30:56,003]   at sun.nio.ch.FileDispatcherImpl.write0(Native Method)
[2024-01-15 09:30:56,010] INFO  [KafkaServer id=2] shutting down (kafka.server.KafkaServer)
""")
    ok(f"Broker-2 crash log: {broker2_log}")

    urp_output = DIRS["data"] / "under_replicated_partitions.txt"
    urp_output.write_text("""\
# Output of: kafka-topics.sh --describe --under-replicated-partitions
# Captured 30 seconds after broker-2 crashed
#
# Topic: trade-executions  Partition: 1  Leader: 1  Replicas: 1,2,3  Isr: 1,3
# Topic: trade-executions  Partition: 3  Leader: 3  Replicas: 3,2,1  Isr: 3,1
# Topic: trade-executions  Partition: 5  Leader: 1  Replicas: 1,2,3  Isr: 1,3
# Topic: trade-executions  Partition: 7  Leader: 3  Replicas: 3,2,1  Isr: 3,1
# Topic: market-data        Partition: 0  Leader: 1  Replicas: 1,2,3  Isr: 1,3
# Topic: market-data        Partition: 2  Leader: 3  Replicas: 3,2,1  Isr: 3,1
#
# ISR is now 2 replicas (broker-2 absent). min.insync.replicas=2 still met.
# Producers can still write (acks=all will wait for 2 ISR).
# Consumers can still read from brokers 1 and 3.
# Broker-2 partitions have been reassigned to brokers 1 and 3 as leaders.
""")
    ok(f"URP snapshot: {urp_output}")

    response_guide = DIRS["scripts"] / "broker_down_response.sh"
    response_guide.write_text(f"""\
#!/bin/bash
# K-04 Incident Response: Broker Down
# =====================================

BROKER="localhost:9092"   # use a surviving broker

echo "=== Step 1: Confirm broker is down ==="
systemctl status kafka      # on the broker host
ss -tlnp | grep 9092        # check port
journalctl -u kafka -n 100  # last 100 log lines

echo "=== Step 2: Check under-replicated partitions ==="
# Non-empty = broker-2 replicas are offline
kafka-topics.sh \\
  --bootstrap-server $BROKER \\
  --describe \\
  --under-replicated-partitions
# Reference output:
cat {urp_output}

echo "=== Step 3: Verify producers still working (RF=3, min.isr=2) ==="
# With 2 remaining brokers and min.insync.replicas=2, producers with acks=all
# will still succeed (2 ISR available). Check producer error rate in monitoring.

echo "=== Step 4: Root cause from broker-2 log ==="
cat {broker2_log}
# Root cause: 'No space left on device' — disk full on broker-2
# Fix before restart: clear old log segments or expand disk

echo "=== Step 5: Clear disk then restart ==="
# df -h /var/kafka                              # check disk
# find /var/kafka/logs -name '*.log' -mtime +7 -delete  # remove old segments
# systemctl restart kafka                        # restart broker
# journalctl -u kafka -f                        # watch startup

echo "=== Step 6: Verify URPs clear after restart ==="
# watch -n 5 "kafka-topics.sh --bootstrap-server $BROKER --describe --under-replicated-partitions"
# Should return empty within a few minutes (broker catching up)

echo "=== Step 7: Trigger preferred replica election (rebalance) ==="
# kafka-preferred-replica-election.sh --bootstrap-server $BROKER
""")
    ok(f"Response guide: {response_guide}")

    print(f"""
{BOLD}── Incident artifacts ──────────────────────────────────{RESET}
{CYAN}       cat {broker2_log}          # broker-2 crash log
       cat {urp_output}    # under-replicated partitions
       cat {response_guide}  # full response playbook{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Read the broker log — what caused the crash?
{CYAN}       grep "ERROR\|FATAL" {broker2_log}{RESET}

  2. Understand the URP output
{CYAN}       cat {urp_output}{RESET}

  3. Walk through the response guide
{CYAN}       cat {response_guide}{RESET}

{BOLD}── Key insight from this scenario ──────────────────────{RESET}
  Root cause: disk full ('No space left on device')
  RF=3, min.isr=2 → cluster survived: 2 brokers still serving reads+writes
  Fix: clear old log segments on broker-2 FIRST, then restart
  Blind restart on a full disk = immediate re-crash
""")


# ══════════════════════════════════════════════
#  SCENARIO 5 — Python Producer + Consumer
# ══════════════════════════════════════════════

def launch_scenario_5():
    header("Scenario K-05 — Python Kafka Producer & Consumer")
    print("  Write working producer/consumer scripts using kafka-python.\n")

    producer_script = DIRS["scripts"] / "kafka_producer.py"
    producer_script.write_text("""\
#!/usr/bin/env python3
\"\"\"
K-05: Kafka producer — sends trade events to trade-executions topic.
Install: pip3 install kafka-python --break-system-packages

NOTE: Requires a running Kafka broker at localhost:9092.
To test without Kafka, set DRY_RUN=True below.
\"\"\"

DRY_RUN = True   # set False when you have a real Kafka broker

TOPIC  = "trade-executions"
BROKER = "localhost:9092"

trades = [
    {"symbol": "AAPL",  "qty": 100, "side": "BUY",  "price": 185.50},
    {"symbol": "GOOGL", "qty":  50, "side": "SELL", "price": 141.20},
    {"symbol": "AAPL",  "qty": 200, "side": "SELL", "price": 185.55},
    {"symbol": "MSFT",  "qty":  75, "side": "BUY",  "price": 380.10},
    {"symbol": "TSLA",  "qty":  30, "side": "BUY",  "price": 248.00},
]

if DRY_RUN:
    import json
    print(f"[DRY RUN] Would produce to topic={TOPIC} broker={BROKER}")
    for i, trade in enumerate(trades):
        # Simulate partition assignment: hash(symbol) % 12
        partition = hash(trade["symbol"]) % 12
        print(f"  [{i}] key={trade['symbol']:<5} → partition {partition}  "
              f"value={json.dumps(trade)}")
    print("\\nKey insight: using symbol as key guarantees all AAPL trades")
    print("land on the same partition → strict ordering per symbol.")
else:
    from kafka import KafkaProducer
    import json
    try:
        producer = KafkaProducer(
            bootstrap_servers=[BROKER],
            value_serializer=lambda v: json.dumps(v).encode(),
            key_serializer=lambda k: k.encode(),
            acks="all",          # wait for all ISR replicas
            enable_idempotence=True,
            retries=3,
        )
        for trade in trades:
            future = producer.send(
                TOPIC,
                key=trade["symbol"],   # same symbol → same partition → ordered
                value=trade,
            )
            meta = future.get(timeout=5)
            print(f"Sent {trade['symbol']} → partition {meta.partition} offset {meta.offset}")
        producer.flush()
        print("\\nAll messages sent successfully.")
    except Exception as e:
        print(f"Producer error: {e}")
        print("Is Kafka running? pip3 install kafka-python?")
""")
    ok(f"Producer script: {producer_script}")

    consumer_script = DIRS["scripts"] / "kafka_consumer.py"
    consumer_script.write_text("""\
#!/usr/bin/env python3
\"\"\"
K-05: Kafka consumer — reads from trade-executions, prints summary.
Install: pip3 install kafka-python --break-system-packages

NOTE: Requires a running Kafka broker at localhost:9092.
\"\"\"

TOPIC  = "trade-executions"
BROKER = "localhost:9092"
GROUP  = "risk-engine"

try:
    from kafka import KafkaConsumer
    import json

    consumer = KafkaConsumer(
        TOPIC,
        bootstrap_servers=[BROKER],
        group_id=GROUP,
        value_deserializer=lambda m: json.loads(m.decode()),
        key_deserializer=lambda k: k.decode() if k else None,
        auto_offset_reset="earliest",       # start from beginning
        enable_auto_commit=False,           # manual commit — safer for trading
        consumer_timeout_ms=5000,           # stop after 5s of no messages
    )

    print(f"Consuming from {TOPIC} as group {GROUP}...\\n")
    count = 0
    for msg in consumer:
        t = msg.value
        print(f"  [p{msg.partition:02d}@{msg.offset:05d}] key={msg.key:5}  "
              f"{t['side']:4} {t['qty']:4} {t['symbol']:5} @ ${t['price']}")
        consumer.commit()   # manual commit after processing
        count += 1

    print(f"\\nConsumed {count} messages.")
    consumer.close()

except ImportError:
    print("kafka-python not installed.")
    print("Run: pip3 install kafka-python --break-system-packages")
except Exception as e:
    print(f"Consumer error: {e}")
""")
    ok(f"Consumer script: {consumer_script}")

    print(f"""
{BOLD}── Scripts ─────────────────────────────────────────────{RESET}
{CYAN}       python3 {producer_script}
       python3 {consumer_script}{RESET}

{BOLD}── Producer runs in DRY_RUN mode (no Kafka needed) ─────{RESET}
  Shows partition routing by symbol key.
  Set DRY_RUN=False to send to a real Kafka broker.

{BOLD}── To set up a local Kafka for real testing ────────────{RESET}
{CYAN}       # Option 1: Docker (easiest)
       docker run -d -p 9092:9092 \\
         -e KAFKA_CFG_NODE_ID=1 \\
         -e KAFKA_CFG_PROCESS_ROLES=broker,controller \\
         -e KAFKA_CFG_LISTENERS=PLAINTEXT://:9092,CONTROLLER://:9093 \\
         bitnami/kafka:latest

       pip3 install kafka-python --break-system-packages
       python3 {producer_script}   # set DRY_RUN=False
       python3 {consumer_script}{RESET}

{BOLD}── Key interview point ──────────────────────────────────{RESET}
  Using symbol as key → same symbol → same partition → ordered.
  Without key → round-robin → AAPL fills interleaved → can't guarantee order.
  enable_auto_commit=False → commit AFTER processing → no data loss on crash.
""")


# ══════════════════════════════════════════════
#  SCENARIO 6 — Delivery Semantics
# ══════════════════════════════════════════════

def launch_scenario_6():
    header("Scenario K-06 — Delivery Semantics in Trading")
    print("  At-most-once vs at-least-once vs exactly-once.\n")

    semantics_guide = DIRS["config"] / "delivery_semantics.md"
    semantics_guide.write_text("""\
# Kafka Delivery Semantics for Trading
=======================================

## The Three Semantics

AT-MOST-ONCE
  Message sent once. If the broker doesn't ACK, it's dropped — NOT retried.
  Producer config: acks=0, retries=0
  Risk in trading: SILENT DATA LOSS. A trade event vanishes. P&L is wrong.
  Use case: non-critical metrics, heartbeats.

AT-LEAST-ONCE
  Message retried until the broker ACKs it. May be delivered 2+ times.
  Producer config: acks=all, retries=3
  Risk in trading: DUPLICATE FILLS. A 100-share BUY processed twice = 200 shares.
  If your consumer crashes after processing but before committing the offset,
  it will reprocess the message on restart.

EXACTLY-ONCE
  Message delivered and processed precisely once, even with failures.
  Requires both idempotent producer AND transactional consume-transform-produce.
  Use case: trade execution, P&L calculation, position updates.

## How Kafka Achieves Exactly-Once

STEP 1 — IDEMPOTENT PRODUCER (per-partition exactly-once)
  enable.idempotence=true
  max.in.flight.requests.per.connection=1
  
  Each message gets a (ProducerID, SequenceNumber). The broker deduplicates
  any retry with the same sequence number. Safe to retry — no duplicates.

STEP 2 — TRANSACTIONS (cross-partition, consume-transform-produce)
  producer.initTransactions()
  producer.beginTransaction()
    → consume from input topic
    → process the message
    → produce to output topic
    producer.sendOffsetsToTransaction(offsets, consumerGroupMetadata)
  producer.commitTransaction()
  
  If the producer crashes mid-transaction, the transaction is aborted.
  Consumers with isolation.level=read_committed skip uncommitted records.

## Trading Config Examples

SAFE PRODUCER (at-least-once, good for most trading use cases):
  acks=all
  enable.idempotence=true
  retries=3
  max.in.flight.requests.per.connection=5

TRANSACTIONAL PRODUCER (exactly-once, trade execution + position updates):
  transactional.id=risk-engine-1
  enable.idempotence=true   (automatically set when transactional.id is set)

SAFE CONSUMER (prevents duplicate processing):
  enable.auto.commit=false
  isolation.level=read_committed
  → commit offsets ONLY after successful processing + DB write
""")
    ok(f"Semantics guide: {semantics_guide}")

    idempotent_example = DIRS["scripts"] / "idempotent_producer_example.py"
    idempotent_example.write_text("""\
#!/usr/bin/env python3
\"\"\"
K-06 Example: Idempotent producer configuration.
This script DOES NOT require Kafka — it shows the correct config pattern.
\"\"\"
# WRONG — at-most-once (dangerous for trading)
WRONG_CONFIG = {
    "acks": 0,
    "retries": 0,
}
print("WRONG (at-most-once):", WRONG_CONFIG)
print("  Risk: silent data loss — broker doesn't ACK, message dropped")

# BETTER — at-least-once with idempotent producer (safe for most cases)
BETTER_CONFIG = {
    "acks": "all",
    "enable_idempotence": True,
    "retries": 3,
    "max_in_flight_requests_per_connection": 5,
}
print("\\nBETTER (idempotent, at-least-once → effectively once per partition):", BETTER_CONFIG)
print("  Broker deduplicates retried messages using sequence numbers")
print("  Safe for trade events as long as consumer is also idempotent")

# BEST — transactional (true exactly-once across partitions)
BEST_CONFIG = {
    "transactional_id": "risk-engine-producer-1",
    # enable_idempotence is automatically True with transactional_id
}
print("\\nBEST (transactional, exactly-once):", BEST_CONFIG)
print("  Use for consume-transform-produce pipelines")
print("  Consumer must use isolation_level=read_committed")
print("\\nIn practice: idempotent producer + manual offset commit covers 90%% of trading needs.")
""")
    ok(f"Idempotent example: {idempotent_example}")

    print(f"""
{BOLD}── Reference files ─────────────────────────────────────{RESET}
{CYAN}       cat {semantics_guide}
       python3 {idempotent_example}{RESET}

{BOLD}── Model interview answer ──────────────────────────────{RESET}
  "At-most-once is unacceptable for trade events — silent loss means
   wrong P&L. At-least-once with idempotent producer covers most cases:
   the broker deduplicates retries using sequence numbers. For position
   updates that span multiple partitions, we use Kafka transactions to
   get true exactly-once across the consume-transform-produce pipeline."
""")


def launch_scenario_99():
    header("Scenario 99 — ALL Kafka Scenarios")
    for fn in [launch_scenario_1, launch_scenario_2, launch_scenario_3,
               launch_scenario_4, launch_scenario_5, launch_scenario_6]:
        fn(); time.sleep(0.3)


# ══════════════════════════════════════════════
#  TEARDOWN / STATUS / MAIN
# ══════════════════════════════════════════════

def teardown():
    header("Tearing Down Kafka Lab")
    kill_pids(DIRS["pids"])
    kill_strays(["mock_broker"])
    remove_lab_dir(LAB_ROOT)

def show_status():
    _show_status(DIRS["pids"], "Kafka Lab")

SCENARIO_MAP = {
    1:  (launch_scenario_1, "K-01  Kafka architecture & concepts"),
    2:  (launch_scenario_2, "K-02  Consumer group lag investigation"),
    3:  (launch_scenario_3, "K-03  Topic operations & CLI reference"),
    4:  (launch_scenario_4, "K-04  Broker down incident response"),
    5:  (launch_scenario_5, "K-05  Python producer + consumer"),
    6:  (launch_scenario_6, "K-06  Delivery semantics — exactly-once"),
    99: (launch_scenario_99, "     ALL scenarios"),
}

def main():
    parser = argparse.ArgumentParser(description="Kafka Challenge Lab Setup",
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
        header("Kafka Challenge Lab")
        for num, (_, desc) in SCENARIO_MAP.items():
            print(f"    {num:<4} {desc}")
        choice = input("\n  Enter scenario number (or q): ").strip()
        if choice.lower() == "q": return
        try:
            fn, _ = SCENARIO_MAP[int(choice)]; fn()
        except (KeyError, ValueError): err(f"Invalid: {choice}")
    lab_footer("lab_kafka.py")

if __name__ == "__main__":
    main()
