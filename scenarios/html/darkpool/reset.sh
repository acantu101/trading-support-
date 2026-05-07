#!/bin/bash
# Reset: Dark pool TRF reporting violation scenario
source "$(dirname "$0")/../_lib/common.sh"

PID_DIR=~/trading-support/pids

# Kill trf-reporter
if [ -f "$PID_DIR/darkpool.pid" ]; then
    TRF_PID=$(cat "$PID_DIR/darkpool.pid")
    kill "$TRF_PID" 2>/dev/null && echo "Killed trf-reporter.py (PID $TRF_PID)" || echo "trf-reporter.py already stopped"
    rm -f "$PID_DIR/darkpool.pid"
fi

# Kill any stragglers
pkill -f "darkpool/trf-reporter.py" 2>/dev/null || true

rm -rf ~/trading-support/darkpool/
echo "Dark Pool scenario reset."
