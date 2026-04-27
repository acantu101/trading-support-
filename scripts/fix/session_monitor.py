#!/usr/bin/env python3
"""
FIX Session Monitor
====================
Continuously monitors a FIX log file for sequence gaps, rejections,
missed heartbeats, and session restarts.

Usage:
    python3 session_monitor.py
    python3 session_monitor.py --log /var/log/fix/session.log
    python3 session_monitor.py --log /var/log/fix/session.log --interval 5
"""

import argparse
import time
from pathlib import Path
from datetime import datetime

SOH       = "\x01"
INTERVAL  = 10   # seconds between checks

MSG_TYPES = {
    "0": "Heartbeat",   "1": "TestRequest",  "2": "ResendRequest",
    "3": "Reject",      "5": "Logout",       "8": "ExecutionReport",
    "A": "Logon",       "D": "NewOrderSingle", "F": "OrderCancelRequest",
}

ORD_STATUS = {
    "0": "New", "1": "PartialFill", "2": "Filled",
    "4": "Cancelled", "8": "Rejected",
}


def parse_fix(line: str) -> dict:
    fields = {}
    start = line.find("8=FIX")
    if start == -1:
        return fields
    for pair in line[start:].split(SOH):
        if "=" in pair:
            t, v = pair.split("=", 1)
            fields[t.strip()] = v.strip()
    return fields


def ts():
    return datetime.now().strftime("%H:%M:%S")


def check(log_path: str):
    path = Path(log_path)
    if not path.exists():
        print(f"[{ts()}] WARN  Log file not found: {log_path}")
        return

    lines     = path.read_text(errors="replace").splitlines()
    fix_lines = [l for l in lines if "8=FIX" in l and "35=" in l]

    prev_seq  = {}
    rejects   = []
    gaps      = []
    logons    = []
    logouts   = []
    resends   = []

    for line in fix_lines:
        direction = "SEND" if "SEND" in line[:10] else "RECV"
        fields    = parse_fix(line)
        seq       = int(fields.get("34", 0))
        msg_type  = fields.get("35", "")

        # Sequence gap detection
        if direction in prev_seq and seq != prev_seq[direction] + 1:
            gaps.append(
                f"{direction} gap: expected seq={prev_seq[direction]+1} got {seq}"
            )
        prev_seq[direction] = seq

        if msg_type == "8" and fields.get("39") == "8":
            rejects.append(
                f"REJECT  ClOrdID={fields.get('11','?')}  "
                f"Symbol={fields.get('55','?')}  "
                f"Reason={fields.get('58','no reason given')}"
            )
        elif msg_type == "A":
            logons.append(f"seq={seq}  {fields.get('49','?')} → {fields.get('56','?')}")
        elif msg_type == "5":
            logouts.append(f"seq={seq}  reason={fields.get('58','none')}")
        elif msg_type == "2":
            resends.append(
                f"ResendRequest  BeginSeqNo={fields.get('7','?')}  "
                f"EndSeqNo={fields.get('16','?')}"
            )

    print(f"\n[{ts()}] ── FIX Session Health Check ──────────────────")
    print(f"  Log:      {log_path}")
    print(f"  Messages: {len(fix_lines)}")
    print(f"  Logons:   {len(logons)}   Logouts: {len(logouts)}")

    if gaps:
        print(f"\n  [ALERT] {len(gaps)} sequence gap(s):")
        for g in gaps:
            print(f"    ⚠  {g}")
        print("    Fix: send ResendRequest (35=2) for missing range")

    if rejects:
        print(f"\n  [ALERT] {len(rejects)} order rejection(s):")
        for r in rejects:
            print(f"    ✗  {r}")

    if resends:
        print(f"\n  [WARN] {len(resends)} ResendRequest(s) detected (gaps occurred):")
        for r in resends:
            print(f"    ↺  {r}")

    if not gaps and not rejects:
        print("  [OK]  No gaps or rejections found")


def main():
    parser = argparse.ArgumentParser(description="FIX Session Monitor")
    parser.add_argument("--log",      default="/var/log/fix/session.log",
                        help="Path to FIX session log file")
    parser.add_argument("--interval", type=int, default=INTERVAL,
                        help="Check interval in seconds (default: 10)")
    parser.add_argument("--once",     action="store_true",
                        help="Run once and exit instead of looping")
    args = parser.parse_args()

    print(f"FIX Session Monitor — watching {args.log}")
    print(f"Interval: {args.interval}s  |  Ctrl+C to stop\n")

    if args.once:
        check(args.log)
        return

    while True:
        check(args.log)
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
