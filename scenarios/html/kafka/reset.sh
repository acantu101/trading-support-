#!/bin/bash
# kafka/reset.sh — Kill Kafka scenario processes and remove state
source "$(dirname "$0")/../_lib/common.sh"

banner "Kafka Scenario: Reset"

PIDS_BASE="$HOME/trading-support/pids/kafka.pids"

for role in producer consumer; do
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

# Belt-and-suspenders: kill any stray producer/consumer by name
pkill -f "trading-support/kafka/producer.py" 2>/dev/null || true
pkill -f "trading-support/kafka/consumer.py" 2>/dev/null || true

step "Removing $HOME/trading-support/kafka/ ..."
rm -rf "$HOME/trading-support/kafka"
ok "Kafka scenario reset."
