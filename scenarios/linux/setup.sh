#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Linux Scenario: Runaway OMS batch job burning CPU"

step "Creating working directories..."
mkdir -p ~/trading-support/linux
mkdir -p ~/trading-support/pids
ok "Directories created"

step "Writing hog.py (rogue OMS process)..."
cat > ~/trading-support/linux/hog.py << 'PYEOF'
#!/usr/bin/env python3
"""
oms-batch-reconcile — post-market position reconciliation job.

# Bug: missing exit condition — runs forever after reconciliation completes.
# The loop below should have checked a completion flag and exited, but a
# developer removed the break statement during a refactor and it was never caught.
# The process stays alive burning CPU long after the nightly batch window closes.
"""

import sys
import os
import threading
import hashlib
import time

# Rename process so it shows up realistically in ps/top
sys.argv[0] = "oms-batch-reconcile"

# Try to set proctitle if available (pip install setproctitle)
try:
    import setproctitle
    setproctitle.setproctitle("oms-batch-reconcile")
except ImportError:
    pass


def cpu_burn(thread_id: int):
    """
    Simulates reconciliation work that was supposed to finish at 18:30
    but has no exit condition. Each thread hammers SHA-256 in a tight loop.
    """
    data = f"oms-reconcile-thread-{thread_id}-".encode()
    counter = 0
    while True:  # Bug: should be `while not reconciliation_complete()`
        # Simulate hashing trade IDs for reconciliation
        h = hashlib.sha256(data + str(counter).encode()).hexdigest()
        counter += 1
        # Missing: check a completion flag or timestamp boundary


def main():
    NUM_THREADS = 4
    threads = []
    for i in range(NUM_THREADS):
        t = threading.Thread(target=cpu_burn, args=(i,), daemon=True)
        t.start()
        threads.append(t)

    # Keep main thread alive (daemon threads die when main exits)
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
PYEOF
ok "hog.py written"

step "Writing suspicious crontab simulation..."
cat > ~/trading-support/linux/crontab.txt << 'CRONEOF'
# Trading system crontab (acm) — recovered from cron.d backup
# This entry restarts the OMS reconciliation job every 5 minutes.
# It was added as a "temporary fix" during an incident and never removed.
# Result: even after you kill the process, it comes back in <5 minutes.

*/5 * * * * python3 ~/trading-support/linux/hog.py

# Other legitimate entries:
0  18 * * 1-5  /opt/oms/bin/eod-position-snapshot.sh >> /var/log/oms/snapshot.log 2>&1
30 17 * * 1-5  /opt/oms/bin/pnl-report.py --date today --output /var/reports/pnl/
0   6 * * 1-5  /opt/market-data/bin/refresh-symbology.sh
CRONEOF
ok "crontab.txt written"

step "Launching hog.py in background..."
python3 ~/trading-support/linux/hog.py &
HOG_PID=$!
echo "$HOG_PID" > ~/trading-support/pids/linux-hog.pid
ok "hog.py started with PID $HOG_PID"

info "CPU hog is running. Use top, ps aux, or htop to identify the runaway process."
info "Hint: look for a Python process consuming multiple CPU cores"
info "Fix: kill the process, then ensure it won't restart (check crontab -l)"
warn "Simulated crontab: cat ~/trading-support/linux/crontab.txt  (not installed in real cron)"
