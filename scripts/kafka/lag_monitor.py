#!/usr/bin/env python3
"""
Kafka Consumer Lag Monitor
===========================
Reads a consumer group lag snapshot (JSON or kafka-consumer-groups.sh output)
and alerts on high lag or unassigned partitions.

Usage:
    python3 lag_monitor.py                              # reads default snapshot
    python3 lag_monitor.py --file /tmp/lag.json
    python3 lag_monitor.py --threshold 500

Production (requires kafka-python):
    python3 lag_monitor.py --broker localhost:9092 --group risk-engine-group --topic trade-executions
"""

import json
import argparse
import sys
from pathlib import Path

DEFAULT_FILE = "/tmp/lab_kafka/data/consumer_lag_snapshot.json"
THRESHOLD    = 100


def check_json(file_path: str, threshold: int):
    path = Path(file_path)
    if not path.exists():
        print(f"Snapshot file not found: {file_path}")
        sys.exit(1)

    data = json.load(open(path))
    print(f"Group    : {data.get('group', '?')}")
    print(f"Snapshot : {data.get('timestamp', '?')}")
    print(f"Threshold: {threshold}\n")

    print(f"  {'TOPIC':<25} {'PART':>5}  {'LAG':>8}  {'CONSUMER':<22}  STATUS")
    print(f"  {'-'*25} {'-'*5}  {'-'*8}  {'-'*22}  {'-'*10}")

    alerts = []
    for p in sorted(data.get("partitions", []), key=lambda x: -x["lag"]):
        consumer = p.get("consumer", "-")
        lag      = p.get("lag", 0)

        if consumer == "-":
            status = "NO CONSUMER"
            alerts.append(p)
        elif lag > threshold:
            status = "HIGH LAG"
            alerts.append(p)
        elif lag > threshold // 2:
            status = "ELEVATED"
        else:
            status = "OK"

        print(f"  {p['topic']:<25} {p['partition']:>5}  {lag:>8}  {consumer:<22}  {status}")

    print()
    if alerts:
        print(f"{len(alerts)} partition(s) need attention:")
        for a in alerts:
            if a.get("consumer") == "-":
                print(f"  partition {a['partition']}: NO CONSUMER — add worker instances")
            else:
                print(f"  partition {a['partition']}: lag={a['lag']} — consumer too slow or backed up")
    else:
        print("All partitions OK")


def check_live(broker: str, group: str, topic: str, threshold: int):
    try:
        from kafka import KafkaConsumer, TopicPartition
    except ImportError:
        print("kafka-python not installed.")
        print("Run: pip3 install kafka-python")
        sys.exit(1)

    consumer = KafkaConsumer(bootstrap_servers=[broker], group_id=group)
    partitions = consumer.partitions_for_topic(topic)
    if not partitions:
        print(f"Topic not found: {topic}")
        sys.exit(1)

    tps          = [TopicPartition(topic, p) for p in partitions]
    committed    = {tp: consumer.committed(tp) or 0 for tp in tps}
    end_offsets  = consumer.end_offsets(tps)
    consumer.close()

    print(f"Broker : {broker}")
    print(f"Group  : {group}")
    print(f"Topic  : {topic}\n")
    print(f"  {'PARTITION':>10}  {'COMMITTED':>12}  {'END':>12}  {'LAG':>8}  STATUS")
    print(f"  {'-'*10}  {'-'*12}  {'-'*12}  {'-'*8}  {'-'*8}")

    alerts = []
    for tp in sorted(tps, key=lambda x: x.partition):
        lag    = end_offsets[tp] - committed[tp]
        status = "HIGH LAG" if lag > threshold else ("ELEVATED" if lag > threshold // 2 else "OK")
        if lag > threshold:
            alerts.append((tp.partition, lag))
        print(f"  {tp.partition:>10}  {committed[tp]:>12}  {end_offsets[tp]:>12}  {lag:>8}  {status}")

    print()
    if alerts:
        print(f"{len(alerts)} high-lag partition(s):")
        for p, lag in alerts:
            print(f"  partition {p}: lag={lag}")
    else:
        print("All partitions OK")


def main():
    parser = argparse.ArgumentParser(description="Kafka Consumer Lag Monitor")
    parser.add_argument("--file",      default=DEFAULT_FILE,
                        help="Path to JSON lag snapshot file")
    parser.add_argument("--threshold", type=int, default=THRESHOLD,
                        help="Lag threshold for alerts (default: 100)")
    parser.add_argument("--broker",    help="Kafka broker (live mode): localhost:9092")
    parser.add_argument("--group",     help="Consumer group name (live mode)")
    parser.add_argument("--topic",     help="Topic name (live mode)")
    args = parser.parse_args()

    if args.broker and args.group and args.topic:
        check_live(args.broker, args.group, args.topic, args.threshold)
    else:
        check_json(args.file, args.threshold)


if __name__ == "__main__":
    main()
