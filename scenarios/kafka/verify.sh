#!/bin/bash
# kafka/verify.sh — Verify fix for Kafka consumer lag scenario
source "$(dirname "$0")/../_lib/common.sh"

banner "Kafka Scenario: Verify Fix"

CONSUMER_PROPS="$HOME/trading-support/kafka/config/consumer.properties"

# ── Read current max.poll.records ────────────────────────────────────────────
if [ ! -f "$CONSUMER_PROPS" ]; then
  err "consumer.properties not found at $CONSUMER_PROPS"
  err "Did you run setup.sh first?"
  exit 1
fi

POLL_RECORDS=$(grep -E '^\s*max\.poll\.records\s*=' "$CONSUMER_PROPS" \
  | tail -1 \
  | sed 's/.*=\s*//' \
  | tr -d '[:space:]')

if [ -z "$POLL_RECORDS" ]; then
  err "max.poll.records key not found in consumer.properties"
  exit 1
fi

# ── Not fixed branch ─────────────────────────────────────────────────────────
if [ "$POLL_RECORDS" -lt 100 ] 2>/dev/null; then
  echo ""
  warn "Consumer is still bottlenecked — max.poll.records=${POLL_RECORDS} means the"
  warn "consumer fetches only ${POLL_RECORDS} messages per poll cycle."
  warn "The producer is writing ~200/sec; at ${POLL_RECORDS}/cycle the lag will keep growing."
  echo ""
  info "Current setting in $CONSUMER_PROPS:"
  grep "max.poll.records" "$CONSUMER_PROPS" | sed 's/^/    /'
  echo ""
  step "Nudge: what throughput does max.poll.records=10 give you if each poll"
  step "       takes ~1 second? What value would let you keep up with 200 msg/sec?"
  echo ""
  exit 1
fi

# ── Fixed branch — simulate lag draining ─────────────────────────────────────
ok "max.poll.records=${POLL_RECORDS} detected — consumer can now batch ${POLL_RECORDS} records per poll."
echo ""

step "Restarting consumer with new configuration..."
sleep 0.3

# Kill old consumer and start fresh (best effort)
PIDS_FILE="$HOME/trading-support/pids/kafka.pids.consumer"
if [ -f "$PIDS_FILE" ]; then
  OLD_PID=$(cat "$PIDS_FILE")
  kill "$OLD_PID" 2>/dev/null || true
fi

KAFKA_DIR="$HOME/trading-support/kafka"
python3 "$KAFKA_DIR/consumer.py" &>/dev/null &
NEW_PID=$!
echo "$NEW_PID" > "$PIDS_FILE"
sleep 0.3
ok "Consumer restarted (PID $NEW_PID)"
echo ""

# ── Simulate kafka-consumer-groups.sh output: lag draining over 3 checks ────
HEADER="%-20s %-25s %-10s %-12s %-12s %-10s %-15s"
ROW="%-20s %-25s %-10s %-12s %-12s %-10s %-15s"

_print_table() {
  local label="$1"
  shift
  local -a lags=("$@")
  echo ""
  echo -e "${BOLD}${CYAN}>>> kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group md-normalizer --describe${NC}"
  echo ""
  # shellcheck disable=SC2059
  printf "${BOLD}${HEADER}${NC}\n" \
    "GROUP" "TOPIC" "PARTITION" "CURRENT-OFFSET" "LOG-END-OFFSET" "LAG" "CONSUMER-ID"
  printf "%-20s %-25s %-10s %-12s %-12s %-10s %-15s\n" \
    "─────────────────" "────────────────────────" "─────────" \
    "──────────────" "──────────────" "─────────" "──────────────"

  local total_lag=0
  for p in 0 1 2 3 4 5; do
    local lag="${lags[$p]}"
    total_lag=$(( total_lag + lag ))
    local end=$(( 48000 + p * 1000 ))
    local cur=$(( end - lag ))
    printf "$ROW\n" \
      "md-normalizer" "md.equities.raw" "$p" "$cur" "$end" "$lag" "normalizer-0-$p"
  done
  echo ""
  echo "  Total lag: ${total_lag} messages  [${label}]"
  echo ""
}

step "Check 1 — consumer just restarted, still catching up..."
sleep 0.3
_print_table "t+0s" 280000 279500 281200 278900 280100 279300
sleep 0.3

step "Check 2 — lag shrinking fast..."
sleep 0.3
_print_table "t+15s" 1200 980 1350 870 1100 1020
sleep 0.3

step "Check 3 — fully caught up..."
sleep 0.3
_print_table "t+30s" 0 0 0 0 0 0
sleep 0.3

ok "Consumer lag cleared. All 6 partitions at LAG=0."
echo ""

# ── SCENARIO COMPLETE summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║              SCENARIO COMPLETE — Kafka Consumer Lag          ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}1. What you diagnosed${NC}"
echo "   The md-normalizer consumer group was accumulating lag on every"
echo "   partition of md.equities.raw. kafka-consumer-groups.sh showed"
echo "   total LAG growing past 280,000 messages. The producer was writing"
echo "   ~200 messages/sec but the consumer was only processing ~10/sec."
echo "   Root cause: max.poll.records=10 in consumer.properties — the"
echo "   consumer fetched only 10 messages per poll cycle."
echo ""

echo -e "${BOLD}${CYAN}2. What you fixed${NC}"
echo "   Changed max.poll.records from 10 to ${POLL_RECORDS} in:"
echo "   $CONSUMER_PROPS"
echo "   This allows the consumer to fetch up to ${POLL_RECORDS} records per poll,"
echo "   giving it enough throughput headroom to outpace the producer."
echo ""

echo -e "${BOLD}${CYAN}3. Real-world context${NC}"
echo "   max.poll.records is one of the most impactful consumer tuning knobs."
echo "   The math is straightforward: if your poll interval is 1s and"
echo "   max.poll.records=10, your max throughput is 10 records/sec."
echo "   A market-data normalizer processing 200 quotes/sec needs at least"
echo "   max.poll.records=200 at that interval, or 500 if the poll loop has"
echo "   any per-record processing overhead."
echo ""
echo "   When to increase records vs. add consumers:"
echo "   - Single-partition bottleneck -> tune batch size first (cheap)"
echo "   - Multi-partition saturation  -> add consumer instances"
echo "   - Processing is stateful/ordered -> tune batch; more consumers"
echo "     only help if you can also increase partitions"
echo ""

echo -e "${BOLD}${CYAN}3a. How to apply a config change in production${NC}"
echo "   Kafka consumers read config at startup — a running process ignores"
echo "   file changes. To apply max.poll.records without dropping messages:"
echo ""
echo "   Rolling restart (preferred for consumer groups with 2+ members):"
echo "   1. Edit consumer.properties on one node"
echo "   2. Send SIGTERM — the consumer commits its current offset and exits"
echo "   3. Kafka rebalances: other group members absorb the partitions"
echo "   4. Restart the consumer; it rejoins and picks up from committed offset"
echo "   5. Repeat for each node — no messages are lost or double-processed"
echo ""
echo "   Single consumer (like this lab):"
echo "   1. Edit consumer.properties"
echo "   2. Kill the process (SIGTERM, not SIGKILL — let it commit offsets)"
echo "   3. Restart — picks up exactly where it left off"
echo "   verify.sh does this automatically when it detects your fix."
echo ""

echo -e "${BOLD}${CYAN}3b. A/B feed failover — market data pattern${NC}"
echo "   Production market-data pipelines typically run two feeds (A and B)"
echo "   so you can switch without downtime. The standard pattern:"
echo ""
echo "   Scenario: Feed A consumer is lagging; Feed B is healthy."
echo "   1. Confirm B is caught up:  kafka-consumer-groups.sh on both groups"
echo "   2. Route downstream systems to Feed B (config flag or DNS switch)"
echo "   3. Let Feed A consumer drain naturally — do NOT force-stop mid-batch"
echo "      (a SIGKILL mid-poll can leave uncommitted offsets; you'll reprocess)"
echo "   4. SIGTERM Feed A consumer, update consumer.properties, restart"
echo "   5. Watch Feed A lag recover; once at 0, optionally fail back"
echo ""
echo "   Do you need to drain the topic first?"
echo "   No. Kafka retains messages until the retention window expires."
echo "   Your consumer group offset is your bookmark — the topic is the source"
echo "   of truth. Fix the consumer, restart it, and it catches up at its own pace."
echo ""

echo -e "${BOLD}${CYAN}4. How to prevent it in production${NC}"
echo "   a) Alert on consumer lag, not just error rates:"
echo "      kafka.consumer.fetch-manager-metrics.records-lag-max > 50000"
echo "   b) Set max.poll.records proportional to your throughput target:"
echo "      max.poll.records >= (msgs_per_sec * poll_interval_ms / 1000) * 2"
echo "   c) Use Kafka's consumer group lag exporter (burrow or kminion)"
echo "      to track per-partition lag with Prometheus/Grafana."
echo "   d) Load-test consumer configs in staging before production deployments."
echo "   e) Document throughput assumptions in consumer.properties comments."
echo ""
