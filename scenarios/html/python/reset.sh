#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Resetting Python memory-leak scenario..."

PID_FILE=~/trading-support/pids/python-svc.pid

if [ -f "$PID_FILE" ]; then
    SVC_PID=$(cat "$PID_FILE")
    if kill -0 "$SVC_PID" 2>/dev/null; then
        kill "$SVC_PID" 2>/dev/null && ok "Killed service.py (PID $SVC_PID)" || warn "Could not kill PID $SVC_PID"
    else
        warn "PID $SVC_PID not running (already stopped)"
    fi
    rm -f "$PID_FILE"
else
    warn "No PID file found at $PID_FILE"
fi

step "Running pkill -f service.py as backup..."
pkill -f "service.py" 2>/dev/null && ok "pkill cleanup done" || ok "No remaining service.py processes"

step "Removing ~/trading-support/python/..."
rm -rf ~/trading-support/python/
ok "Python scenario reset."
