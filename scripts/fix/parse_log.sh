#!/bin/bash
# FIX Log Parser — common one-liners for incident diagnosis
# Usage: bash parse_log.sh [log_file]

LOG="${1:-/var/log/fix/session.log}"

echo "FIX Log: $LOG"
echo "========================================"

# ── Is the log file there and recent? ────────────────────────
echo ""
echo "── Last modified ────────────────────────────────────────"
stat "$LOG" 2>/dev/null | grep Modify || echo "File not found: $LOG"

# ── Message type breakdown ────────────────────────────────────
echo ""
echo "── Message type counts ──────────────────────────────────"
grep -oP "35=\K[^\x01 ]+" "$LOG" | sort | uniq -c | sort -rn | \
  awk '{
    types["0"]="Heartbeat"; types["1"]="TestRequest"; types["2"]="ResendRequest";
    types["3"]="Reject";    types["5"]="Logout";      types["8"]="ExecReport";
    types["A"]="Logon";     types["D"]="NewOrderSingle"; types["F"]="CancelRequest";
    label = types[$2] ? types[$2] : "Unknown"
    printf "  %5d  35=%-2s  %s\n", $1, $2, label
  }'

# ── Sequence numbers — detect gaps ───────────────────────────
echo ""
echo "── Sequence gaps (RECV direction) ──────────────────────"
grep "^RECV" "$LOG" | grep -oP "34=\K[0-9]+" | \
  awk 'NR>1 && $1 != prev+1 {
    print "  GAP: expected " prev+1 " got " $1 " (missing " $1-prev-1 " message(s))"
  } {prev=$1}'
echo "  (no output = no gaps)"

# ── All rejections ────────────────────────────────────────────
echo ""
echo "── Order rejections (39=8) ──────────────────────────────"
grep "39=8" "$LOG" | while read -r line; do
  clord=$(echo "$line" | grep -oP "11=\K[^\x01 ]+")
  sym=$(echo "$line"   | grep -oP "55=\K[^\x01 ]+")
  reason=$(echo "$line" | grep -oP "58=\K[^\x01]+")
  echo "  ✗  ClOrdID=$clord  Symbol=$sym  Reason=$reason"
done

# ── ResendRequests — gaps were detected ───────────────────────
echo ""
echo "── ResendRequests (35=2) — indicates gaps occurred ─────"
grep "35=2" "$LOG" | while read -r line; do
  begin=$(echo "$line" | grep -oP "7=\K[0-9]+")
  end=$(echo "$line"   | grep -oP "16=\K[0-9]+")
  echo "  ↺  Requested retransmit: seq $begin → $end"
done

# ── Session restarts ──────────────────────────────────────────
echo ""
echo "── Session events (Logon/Logout) ────────────────────────"
grep -E "35=[A5]" "$LOG" | while read -r line; do
  mtype=$(echo "$line" | grep -oP "35=\K[^\x01 ]+")
  seq=$(echo "$line"   | grep -oP "34=\K[0-9]+")
  sender=$(echo "$line" | grep -oP "49=\K[^\x01 ]+")
  label="Logon"
  [ "$mtype" = "5" ] && label="Logout"
  echo "  $label  seq=$seq  from=$sender"
done

# ── Last 5 minutes activity ───────────────────────────────────
echo ""
echo "── Messages in last 5 minutes ───────────────────────────"
FIVE_AGO=$(date -d '5 minutes ago' '+%Y%m%d-%H:%M' 2>/dev/null || \
           date -v-5M '+%Y%m%d-%H:%M')
COUNT=$(awk -v t="$FIVE_AGO" '$0 > t' "$LOG" | grep "35=" | wc -l)
echo "  $COUNT messages since $FIVE_AGO"

echo ""
echo "Done."
