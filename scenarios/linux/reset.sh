#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Resetting Linux CPU-hog scenario..."

PID_FILE=~/trading-support/pids/linux-hog.pid

if [ -f "$PID_FILE" ]; then
    HOG_PID=$(cat "$PID_FILE")
    if kill -0 "$HOG_PID" 2>/dev/null; then
        kill "$HOG_PID" 2>/dev/null && ok "Killed hog.py (PID $HOG_PID)" || warn "Could not kill PID $HOG_PID"
    else
        warn "PID $HOG_PID not running (already stopped)"
    fi
    rm -f "$PID_FILE"
else
    warn "No PID file found at $PID_FILE"
fi

step "Running pkill -f hog.py as backup..."
pkill -f "hog.py" 2>/dev/null && ok "pkill cleanup done" || ok "No remaining hog.py processes"

step "Removing ~/trading-support/linux/..."
rm -rf ~/trading-support/linux/
ok "Linux scenario reset."
