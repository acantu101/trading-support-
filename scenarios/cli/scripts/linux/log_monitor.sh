#!/bin/bash
# Trading Application Log Monitor
# =================================
# Monitors a log file and alerts when CRITICAL/ERROR count exceeds threshold.
# Includes alert-storm prevention (won't re-alert until count drops).
#
# Usage:
#   bash log_monitor.sh
#   bash log_monitor.sh /var/log/trading/app.log 10 30
#   bash log_monitor.sh [log_file] [threshold] [interval_seconds]

LOG_FILE="${1:-/var/log/trading/app.log}"
THRESHOLD="${2:-5}"
INTERVAL="${3:-10}"

ALERTED=0

echo "Monitoring : $LOG_FILE"
echo "Threshold  : $THRESHOLD CRITICAL/ERROR events in last 200 lines"
echo "Interval   : ${INTERVAL}s"
echo "Press Ctrl+C to stop"
echo ""

if [ ! -f "$LOG_FILE" ]; then
    echo "ERROR: Log file not found: $LOG_FILE"
    exit 1
fi

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

    # Count CRITICAL events in last 200 lines
    CRITICAL_COUNT=$(tail -n 200 "$LOG_FILE" | grep "CRITICAL" | wc -l)
    ERROR_COUNT=$(tail -n 200 "$LOG_FILE" | grep "ERROR" | wc -l)
    TOTAL=$((CRITICAL_COUNT + ERROR_COUNT))

    if [ "$TOTAL" -gt "$THRESHOLD" ] && [ "$ALERTED" -eq 0 ]; then
        echo "[$TIMESTAMP] ALERT: $TOTAL events in recent log lines (CRITICAL=$CRITICAL_COUNT ERROR=$ERROR_COUNT)"

        # Show the most recent unique errors
        echo "  Top errors:"
        tail -n 200 "$LOG_FILE" | awk '/ERROR|CRITICAL/ {$2=""; print}' \
            | sort | uniq -c | sort -rn | head -5 \
            | awk '{printf "    %dx %s\n", $1, substr($0, index($0,$3))}'

        ALERTED=1

        # Log to syslog if available
        logger -t trading-monitor "ALERT: $TOTAL error events in $LOG_FILE" 2>/dev/null

    elif [ "$TOTAL" -le "$THRESHOLD" ] && [ "$ALERTED" -eq 1 ]; then
        echo "[$TIMESTAMP] RESOLVED: event count dropped to $TOTAL (below threshold $THRESHOLD)"
        ALERTED=0
    fi

    sleep "$INTERVAL"
done
