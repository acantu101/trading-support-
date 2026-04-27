#!/usr/bin/env python3
"""
Process Watchdog
=================
Monitors a trading process and restarts it on crash with exponential backoff.
Alerts after max retries are exhausted.

Usage:
    python3 process_watchdog.py
    python3 process_watchdog.py --cmd "python3 /opt/oms/oms_client.py" --retries 5
"""

import subprocess
import time
import sys
import argparse
from datetime import datetime


def ts():
    return datetime.now().strftime('%H:%M:%S')


def main():
    parser = argparse.ArgumentParser(description="Process Watchdog")
    parser.add_argument("--cmd",     default="python3 /tmp/lab_python/scripts/crashy_oms.py",
                        help="Command to run and monitor")
    parser.add_argument("--retries", type=int, default=5,
                        help="Max restart attempts before giving up (default: 5)")
    parser.add_argument("--delay",   type=int, default=2,
                        help="Base delay in seconds for exponential backoff (default: 2)")
    args = parser.parse_args()

    command      = args.cmd.split()
    max_retries  = args.retries
    base_delay   = args.delay
    restart_count = 0

    print(f"[{ts()}] Watchdog started")
    print(f"[{ts()}] Command    : {args.cmd}")
    print(f"[{ts()}] Max retries: {max_retries}")
    print(f"[{ts()}] Base delay : {base_delay}s (exponential backoff)\n")

    while restart_count < max_retries:
        print(f"[{ts()}] Starting process (attempt {restart_count + 1}/{max_retries})...")
        proc = subprocess.Popen(command)
        exit_code = proc.wait()
        restart_count += 1

        print(f"[{ts()}] Process exited with code {exit_code}")

        if exit_code == 0:
            print(f"[{ts()}] Clean exit — stopping watchdog.")
            sys.exit(0)

        # Exponential backoff: 2, 4, 8, 16, 32...
        delay = base_delay * (2 ** (restart_count - 1))
        print(f"[{ts()}] Restarting in {delay}s...")
        time.sleep(delay)
    else:
        print(f"[{ts()}] Max retries ({max_retries}) reached — process cannot stay up.")
        print(f"[{ts()}] ACTION REQUIRED: page on-call, check logs for root cause.")
        sys.exit(1)


if __name__ == "__main__":
    main()
