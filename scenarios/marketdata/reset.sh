#!/bin/bash
# marketdata/reset.sh — Kill market data scenario processes and remove state
source "$(dirname "$0")/../_lib/common.sh"

banner "Market Data Scenario: Reset"

PIDS_BASE="$HOME/trading-support/pids/marketdata.pids"

for role in publisher normalizer; do
    PFILE="${PIDS_BASE}.${role}"
    if [ -f "$PFILE" ]; then
        PID=$(cat "$PFILE")
        if kill -0 "$PID" 2>/dev/null; then
            step "Stopping ${role}.py (PID $PID)..."
            kill "$PID" 2>/dev/null
            ok "${role}.py stopped"
        else
            warn "PID $PID for $role not running (already stopped)"
        fi
        rm -f "$PFILE"
    else
        warn "No PID file for $role at $PFILE"
    fi
done

# Belt-and-suspenders cleanup
pkill -f "trading-support/marketdata/publisher.py"  2>/dev/null || true
pkill -f "trading-support/marketdata/normalizer.py" 2>/dev/null || true

step "Removing $HOME/trading-support/marketdata/ ..."
rm -rf "$HOME/trading-support/marketdata"
ok "Market Data scenario reset."
