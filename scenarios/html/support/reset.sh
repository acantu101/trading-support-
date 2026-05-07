#!/bin/bash
# Reset: Support stale NVDA quotes scenario
source "$(dirname "$0")/../_lib/common.sh"

PID_DIR=~/trading-support/pids

# Kill publisher
if [ -f "$PID_DIR/support-publisher.pid" ]; then
    PUB_PID=$(cat "$PID_DIR/support-publisher.pid")
    kill "$PUB_PID" 2>/dev/null && echo "Killed publisher.py (PID $PUB_PID)" || echo "publisher.py already stopped"
    rm -f "$PID_DIR/support-publisher.pid"
fi

# Kill normalizer
if [ -f "$PID_DIR/support-normalizer.pid" ]; then
    NORM_PID=$(cat "$PID_DIR/support-normalizer.pid")
    kill "$NORM_PID" 2>/dev/null && echo "Killed normalizer.py (PID $NORM_PID)" || echo "normalizer.py already stopped"
    rm -f "$PID_DIR/support-normalizer.pid"
fi

# Also kill any stragglers by name
pkill -f "support/publisher.py" 2>/dev/null || true
pkill -f "support/normalizer.py" 2>/dev/null || true

rm -rf ~/trading-support/support/
echo "Support scenario reset."
