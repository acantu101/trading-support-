#!/bin/bash
# kafka/setup.sh — Consumer lag scenario (producer faster than consumer)
source "$(dirname "$0")/../_lib/common.sh"

banner "Kafka Scenario: Consumer Lag"
ensure_dirs

KAFKA_DIR="$HOME/trading-support/kafka"
PIDS_FILE="$HOME/trading-support/pids/kafka.pids"

# ── Directories ──────────────────────────────────────────────────────────────
step "Creating Kafka scenario directories..."
mkdir -p "$KAFKA_DIR/queue" "$KAFKA_DIR/logs" "$KAFKA_DIR/config" "$KAFKA_DIR/bin"
ok "Directories ready: $KAFKA_DIR"

# ── Install kafka-python (best effort, simulation works without it) ───────────
step "Ensuring Python deps (kafka-python)..."
python3 -m pip install --quiet --user kafka-python 2>/dev/null || true
ok "Dep check done (simulation mode does not require real Kafka)"

# ── consumer.properties (the bottleneck config) ──────────────────────────────
step "Writing consumer.properties (max.poll.records=10 — bottleneck)..."
cat > "$KAFKA_DIR/config/consumer.properties" << 'EOF'
# Kafka consumer config — md-normalizer group
bootstrap.servers=localhost:9092
group.id=md-normalizer
auto.offset.reset=earliest
enable.auto.commit=true
auto.commit.interval.ms=1000

# BOTTLENECK: too low — should be 500 for this throughput
max.poll.records=10

fetch.min.bytes=1
fetch.max.wait.ms=500
session.timeout.ms=10000
heartbeat.interval.ms=3000
EOF
ok "consumer.properties written"

# ── producer.py ─────────────────────────────────────────────────────────────
step "Writing producer.py (~200 msg/sec)..."
cat > "$KAFKA_DIR/producer.py" << 'PYEOF'
#!/usr/bin/env python3
"""
producer.py — Simulated market-data producer.
Writes JSON quote messages to queue/md.equities.raw.jsonl at ~200 msg/sec.
Tracks total messages written in queue/producer.offset for the lag checker.
"""
import json
import time
import random
import os
import signal
import sys

QUEUE_FILE = os.path.expanduser("~/trading-support/kafka/queue/md.equities.raw.jsonl")
OFFSET_FILE = os.path.expanduser("~/trading-support/kafka/queue/producer.offset")
LOG_FILE    = os.path.expanduser("~/trading-support/kafka/logs/producer.log")

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "NFLX", "JPM", "GS"]
BASE_PRICES = {
    "AAPL": 182.50, "MSFT": 415.75, "GOOGL": 175.20, "AMZN": 185.90,
    "TSLA": 248.10, "NVDA": 875.30, "META": 510.60, "NFLX": 625.80,
    "JPM": 198.40, "GS": 412.25
}

running = True
def _stop(sig, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

os.makedirs(os.path.dirname(QUEUE_FILE), exist_ok=True)

total = 0
with open(QUEUE_FILE, "a") as qf, open(LOG_FILE, "w") as lf:
    lf.write(f"producer started pid={os.getpid()}\n")
    lf.flush()
    while running:
        sym = random.choice(SYMBOLS)
        base = BASE_PRICES[sym]
        bid = round(base + random.uniform(-0.50, 0.50), 2)
        ask = round(bid + random.uniform(0.01, 0.05), 2)
        msg = {
            "symbol": sym,
            "bid": bid,
            "ask": ask,
            "bid_size": random.randint(100, 10000),
            "ask_size": random.randint(100, 10000),
            "timestamp": time.time(),
            "seq": total
        }
        qf.write(json.dumps(msg) + "\n")
        qf.flush()
        total += 1
        # Write producer offset so lag-checker can compute lag
        with open(OFFSET_FILE, "w") as off:
            off.write(str(total))
        time.sleep(0.005)   # ~200 msg/sec

lf.write(f"producer stopped. total={total}\n")
PYEOF
ok "producer.py written"

# ── consumer.py ─────────────────────────────────────────────────────────────
step "Writing consumer.py (~10 msg/sec — lagging)..."
cat > "$KAFKA_DIR/consumer.py" << 'PYEOF'
#!/usr/bin/env python3
"""
consumer.py — Simulated market-data consumer (md-normalizer).
Reads from queue/md.equities.raw.jsonl but processes at only ~10 msg/sec
due to max.poll.records=10 with a 100ms sleep — simulating consumer lag.
Tracks consumed offset in queue/consumer.offset.
"""
import json
import time
import os
import signal
import sys

QUEUE_FILE    = os.path.expanduser("~/trading-support/kafka/queue/md.equities.raw.jsonl")
OFFSET_FILE   = os.path.expanduser("~/trading-support/kafka/queue/consumer.offset")
LOG_FILE      = os.path.expanduser("~/trading-support/kafka/logs/consumer.log")
CONFIG_FILE   = os.path.expanduser("~/trading-support/kafka/config/consumer.properties")

running = True
def _stop(sig, frame):
    global running
    running = False

signal.signal(signal.SIGTERM, _stop)
signal.signal(signal.SIGINT, _stop)

# Parse max.poll.records from config
max_poll = 10
if os.path.exists(CONFIG_FILE):
    with open(CONFIG_FILE) as cf:
        for line in cf:
            line = line.strip()
            if line.startswith("max.poll.records"):
                try:
                    max_poll = int(line.split("=")[1].strip())
                except Exception:
                    pass

consumed = 0
with open(LOG_FILE, "w") as lf:
    lf.write(f"consumer started pid={os.getpid()} max.poll.records={max_poll}\n")
    lf.flush()

    while running:
        if not os.path.exists(QUEUE_FILE):
            time.sleep(0.5)
            continue

        with open(QUEUE_FILE) as qf:
            lines = qf.readlines()

        available = len(lines)
        if consumed >= available:
            time.sleep(1.0)
            continue

        # Only process max_poll records per "poll"
        batch = lines[consumed: consumed + max_poll]
        for line in batch:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                _ = msg  # simulate processing (discard output for speed)
            except json.JSONDecodeError:
                pass
            consumed += 1

        with open(OFFSET_FILE, "w") as off:
            off.write(str(consumed))

        # 1s poll interval -> ~10 msg/sec when max_poll=10
        time.sleep(1.0)

lf.write(f"consumer stopped. consumed={consumed}\n")
PYEOF
ok "consumer.py written"

# ── kafka-consumer-groups.sh wrapper ────────────────────────────────────────
step "Writing bin/kafka-consumer-groups.sh..."
cat > "$KAFKA_DIR/bin/kafka-consumer-groups.sh" << 'BEOF'
#!/bin/bash
# kafka-consumer-groups.sh — simulated Kafka CLI wrapper
# Reads state files to compute live LAG and outputs realistic describe output.

QUEUE_FILE="$HOME/trading-support/kafka/queue/md.equities.raw.jsonl"
PROD_OFF="$HOME/trading-support/kafka/queue/producer.offset"
CONS_OFF="$HOME/trading-support/kafka/queue/consumer.offset"

# Read offsets
if [ -f "$PROD_OFF" ]; then
    PROD_TOTAL=$(cat "$PROD_OFF")
else
    PROD_TOTAL=0
fi
if [ -f "$CONS_OFF" ]; then
    CONS_TOTAL=$(cat "$CONS_OFF")
else
    CONS_TOTAL=0
fi

TOTAL_LAG=$(( PROD_TOTAL - CONS_TOTAL ))
[ "$TOTAL_LAG" -lt 0 ] && TOTAL_LAG=0

# Distribute lag and offsets across 6 simulated partitions
distribute() {
    local total=$1
    local parts=$2
    local base=$(( total / parts ))
    local rem=$(( total % parts ))
    for (( i=0; i<parts; i++ )); do
        if [ $i -lt $rem ]; then
            echo $(( base + 1 ))
        else
            echo $base
        fi
    done
}

PARTITIONS=6
mapfile -t PROD_PARTS < <(distribute "$PROD_TOTAL" "$PARTITIONS")
mapfile -t CONS_PARTS < <(distribute "$CONS_TOTAL" "$PARTITIONS")

# Handle --describe flag (show table regardless of other flags for simplicity)
if [[ "$*" == *"--describe"* ]] || [[ "$*" == *"-describe"* ]]; then
    printf "\n"
    printf "%-20s %-25s %-10s %-12s %-12s %-10s %-15s\n" \
        "GROUP" "TOPIC" "PARTITION" "CURRENT-OFFSET" "LOG-END-OFFSET" "LAG" "CONSUMER-ID"
    printf "%-20s %-25s %-10s %-12s %-12s %-10s %-15s\n" \
        "─────────────────" "────────────────────────" "─────────" "──────────────" "──────────────" "─────────" "──────────────"

    for (( p=0; p<PARTITIONS; p++ )); do
        cur=${CONS_PARTS[$p]}
        end=${PROD_PARTS[$p]}
        lag=$(( end - cur ))
        [ "$lag" -lt 0 ] && lag=0
        printf "%-20s %-25s %-10s %-12s %-12s %-10s %-15s\n" \
            "md-normalizer" "md.equities.raw" "$p" "$cur" "$end" "$lag" "normalizer-0-$p"
    done

    printf "\n"
    printf "  Total lag: %s messages\n" "$TOTAL_LAG"
    printf "  Hint: consumer is processing ~10 msg/sec; producer writes ~200 msg/sec\n"
    printf "        Check ~/trading-support/kafka/config/consumer.properties\n"
    printf "\n"
else
    echo "Usage: kafka-consumer-groups.sh --bootstrap-server <host:port> --group <group> --describe"
fi
BEOF
chmod +x "$KAFKA_DIR/bin/kafka-consumer-groups.sh"
ok "bin/kafka-consumer-groups.sh written and marked executable"

# ── Clear stale state so lag starts from zero on every run ───────────────────
step "Cleaning up stale state files..."
rm -f "$KAFKA_DIR/queue/md.equities.raw.jsonl"
rm -f "$KAFKA_DIR/queue/producer.offset"
rm -f "$KAFKA_DIR/queue/consumer.offset"
ok "State cleared — fresh run"

# ── Start producer and consumer in background ────────────────────────────────
step "Starting producer.py in background..."
python3 "$KAFKA_DIR/producer.py" &
PROD_PID=$!
ok "producer.py started (PID $PROD_PID)"

step "Starting consumer.py in background..."
python3 "$KAFKA_DIR/consumer.py" &
CONS_PID=$!
ok "consumer.py started (PID $CONS_PID)"

# Save PIDs
mkdir -p "$HOME/trading-support/pids"
echo "$PROD_PID" > "$PIDS_FILE.producer"
echo "$CONS_PID" > "$PIDS_FILE.consumer"
ok "PIDs saved to $PIDS_FILE.{producer,consumer}"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  SCENARIO READY — Kafka Consumer Lag${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
info "Add the simulated CLI to your PATH:"
echo -e "    ${BOLD}export PATH=\"$KAFKA_DIR/bin:\$PATH\"${NC}"
echo ""
info "Then investigate the lag:"
echo -e "    ${BOLD}kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group md-normalizer --describe${NC}"
echo ""
info "Root cause is in:"
echo -e "    $KAFKA_DIR/config/consumer.properties  (max.poll.records=10)"
echo ""
info "When you've identified and applied the fix, verify it with:"
echo -e "    ${BOLD}bash ~/trading-support/scenarios/kafka/verify.sh${NC}"
echo ""
warn "Consumer lag building. Check with: kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group md-normalizer --describe"
echo ""
