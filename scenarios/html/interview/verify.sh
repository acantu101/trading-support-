#!/bin/bash
# scenarios/interview/verify.sh — Verify design challenge progress

source "$(dirname "$0")/../_lib/common.sh"

ARCH_FILE="$HOME/trading-support/interview/design/architecture.txt"
SKEL_FILE="$HOME/trading-support/interview/skeleton/pnl_engine.py"

banner "Interview — P&L System Design Verify"

# ── Helper: count pass-only function bodies in python file ────────────────────
count_pass_bodies() {
    local pyfile="$1"
    python3 - "$pyfile" <<'PYEOF' 2>/dev/null
import ast, sys

filename = sys.argv[1]
try:
    with open(filename) as f:
        src = f.read()
    tree = ast.parse(src)
except Exception:
    print(0)
    sys.exit(0)

pass_count = 0
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        body = [n for n in node.body if not isinstance(n, (ast.Expr,))]
        if all(isinstance(n, ast.Pass) for n in body) and body:
            pass_count += 1
        elif len(node.body) == 1 and isinstance(node.body[0], ast.Expr):
            # docstring-only body counts as pass-equivalent
            if isinstance(node.body[0].value, ast.Constant):
                pass_count += 1

print(pass_count)
PYEOF
}

info "Checking architecture.txt for unfilled placeholders..."
sleep 0.3

ARCH_INCOMPLETE=false
SKEL_INCOMPLETE=false
ARCH_PLACEHOLDER_COUNT=0
SKEL_PASS_COUNT=0

if [[ ! -f "$ARCH_FILE" ]]; then
    ARCH_INCOMPLETE=true
    ARCH_STATUS="${RED}NOT FOUND${NC}"
else
    ARCH_PLACEHOLDER_COUNT=$(grep -c '\[?\]' "$ARCH_FILE" 2>/dev/null || echo 0)
    if [[ "$ARCH_PLACEHOLDER_COUNT" -gt 0 ]]; then
        ARCH_INCOMPLETE=true
        ARCH_STATUS="${YELLOW}${ARCH_PLACEHOLDER_COUNT} placeholder(s) remaining${NC}"
    else
        ARCH_STATUS="${GREEN}Complete${NC}"
    fi
fi

info "Checking pnl_engine.py for unimplemented functions..."
sleep 0.3

if [[ ! -f "$SKEL_FILE" ]]; then
    SKEL_INCOMPLETE=true
    SKEL_STATUS="${RED}NOT FOUND${NC}"
else
    SKEL_PASS_COUNT=$(count_pass_bodies "$SKEL_FILE")
    if [[ "$SKEL_PASS_COUNT" -gt 0 ]]; then
        SKEL_INCOMPLETE=true
        SKEL_STATUS="${YELLOW}${SKEL_PASS_COUNT} function(s) still have pass bodies${NC}"
    else
        SKEL_STATUS="${GREEN}All functions implemented${NC}"
    fi
fi

# ── Not complete? ─────────────────────────────────────────────────────────────
if $ARCH_INCOMPLETE || $SKEL_INCOMPLETE; then
    echo ""
    warn "INCOMPLETE — keep going, you're making progress."
    echo ""

    echo -e "${BOLD}Progress checklist:${NC}"
    echo ""
    echo -e "  ${BOLD}architecture.txt${NC}"
    if $ARCH_INCOMPLETE; then
        echo -e "    ${RED}[✗]${NC} Still has [?] placeholders — $(echo -e "$ARCH_STATUS")"
        if [[ -f "$ARCH_FILE" ]]; then
            echo ""
            echo -e "    Unfilled sections:"
            grep -n '\[?\]' "$ARCH_FILE" 2>/dev/null | sed 's/^/      Line /' | head -10
        fi
    else
        echo -e "    ${GREEN}[✓]${NC} $(echo -e "$ARCH_STATUS")"
    fi
    echo ""

    echo -e "  ${BOLD}pnl_engine.py${NC}"
    if $SKEL_INCOMPLETE; then
        echo -e "    ${RED}[✗]${NC} $(echo -e "$SKEL_STATUS")"
        if [[ -f "$SKEL_FILE" ]]; then
            echo ""
            echo -e "    Functions still needing implementation:"
            python3 - "$SKEL_FILE" <<'PYEOF' 2>/dev/null | sed 's/^/      - /'
import ast, sys
filename = sys.argv[1]
with open(filename) as f:
    src = f.read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        body = [n for n in node.body if not isinstance(n, (ast.Expr,))]
        if all(isinstance(n, ast.Pass) for n in body) and body:
            print(f"{node.name}() — line {node.lineno}")
        elif len(node.body) == 1 and isinstance(node.body[0], ast.Expr):
            if isinstance(node.body[0].value, ast.Constant):
                print(f"{node.name}() — line {node.lineno}")
PYEOF
        fi
    else
        echo -e "    ${GREEN}[✓]${NC} $(echo -e "$SKEL_STATUS")"
    fi

    echo ""
    echo -e "${BOLD}${CYAN}Remember:${NC} Design challenges don't have one right answer — the goal is"
    echo -e "to show you can reason about trade-offs. Consider:"
    echo -e "  - ${BOLD}State store choice:${NC} Redis vs Kafka Streams vs in-memory — and why"
    echo -e "  - ${BOLD}Ingestion:${NC} How do fills arrive? FIX? Market data feed? Batch?"
    echo -e "  - ${BOLD}Failure modes:${NC} What happens if the state store goes down mid-day?"
    echo -e "  - ${BOLD}Latency vs consistency:${NC} Real-time P&L or end-of-day batch?"
    echo ""
    exit 1
fi

# ── Complete ─────────────────────────────────────────────────────────────────
ok "Architecture filled in and all skeleton functions implemented."
echo ""

info "Simulating interviewer review..."
sleep 0.5
echo ""

NOW=$(date +"%H:%M:%S")

echo -e "${BOLD}${CYAN}┌─────────────────────────────────────────────────────────────┐${NC}"
echo -e "${BOLD}${CYAN}│  Interviewer Feedback — Senior Infrastructure Engineer       │${NC}"
echo -e "${BOLD}${CYAN}└─────────────────────────────────────────────────────────────┘${NC}"
echo ""
sleep 0.3

echo -e "${BOLD}State store choice:${NC}"
sleep 0.3
echo -e "  Good. If you chose Redis for real-time position queries — that's the"
echo -e "  right instinct. O(1) reads matter when risk systems poll every 100ms."
echo -e "  If you chose Kafka Streams — also defensible: you get a durable changelog"
echo -e "  and replay capability at the cost of higher query latency. The key is"
echo -e "  that you can ${BOLD}articulate the trade-off${NC}, not just pick one."
sleep 0.3
echo ""

echo -e "${BOLD}Ingestion approach:${NC}"
sleep 0.3
echo -e "  FIX ExecutionReport (35=8) is the standard fill source. Good if you"
echo -e "  mentioned parsing Tag 39 (OrdStatus) and Tag 32 (LastShares)."
echo -e "  Bonus: you should handle partial fills (OrdStatus=1) vs full fills (2)"
echo -e "  correctly — running position updates per partial is important."
sleep 0.3
echo ""

echo -e "${BOLD}Failover strategy:${NC}"
sleep 0.3
echo -e "  The right answer here is: don't recover from memory, recover from the"
echo -e "  source of truth. Replay fills from Kafka or the OMS database. Never"
echo -e "  trust an in-memory state store as your only copy of position data."
echo -e "  Redis Sentinel or Cluster with AOF persistence is a reasonable middle"
echo -e "  ground for real-time needs."
sleep 0.3
echo ""

echo -e "${BOLD}Mark-to-market timing:${NC}"
sleep 0.3
echo -e "  Did you address this? MTM requires a price for every position at each"
echo -e "  calculation interval. Where does the price come from? NBBO? Last trade?"
echo -e "  What happens during a trading halt? These are the details that separate"
echo -e "  a solid design from a hand-wavy one."
sleep 0.3
echo ""

echo -e "${BOLD}Key trade-offs to articulate in a real interview:${NC}"
sleep 0.3
echo ""
echo -e "    ${BOLD}Consistency vs latency:${NC}"
echo -e "    Real-time P&L (every fill) vs periodic batch (every N seconds)."
echo -e "    Risk systems want real-time; it's harder to guarantee correctness."
echo ""
echo -e "    ${BOLD}State size:${NC}"
echo -e "    Positions grow linearly with symbols × accounts. At 5,000 symbols"
echo -e "    × 500 accounts = 2.5M position records. Fits in Redis easily."
echo ""
echo -e "    ${BOLD}Corporate actions:${NC}"
echo -e "    Stock splits, dividends, ticker changes. Your P&L engine must"
echo -e "    handle these or it will drift from the OMS reconciliation."
echo ""
echo -e "    ${BOLD}Currency:${NC}"
echo -e "    Multi-currency books require FX conversion at the time of each fill."
echo -e "    Stale FX rates = wrong P&L. Source FX from a real-time feed."

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║           SCENARIO COMPLETE — INTERVIEW DESIGN              ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}What you diagnosed${NC}"
echo -e "  This was a system design challenge, not a bug fix. You were asked to"
echo -e "  design a real-time P&L engine and reason through its architecture:"
echo -e "  state store, ingestion, failover, and correctness at scale."
echo ""

echo -e "${BOLD}${CYAN}What you fixed${NC}"
echo -e "  Filled in the architecture.txt with component choices and rationale."
echo -e "  Implemented the skeleton functions in pnl_engine.py, demonstrating"
echo -e "  how fills map to position updates and how MTM P&L is calculated."
echo ""

echo -e "${BOLD}${CYAN}Real-world context${NC}"
echo -e "  P&L engines are at the heart of every trading firm's risk infrastructure."
echo -e "  Systems in practice:"
echo -e "  - ${BOLD}Kafka Streams${NC}  — stateful stream processing with exactly-once semantics"
echo -e "  - ${BOLD}Redis${NC}           — sub-millisecond position queries for risk checks"
echo -e "  - ${BOLD}Flink${NC}           — complex event processing, windowed aggregations"
echo -e "  - ${BOLD}kdb+/q${NC}          — tick data + time-series P&L at ultra-low latency"
echo ""
echo -e "  Common P&L system gotchas:"
echo -e "  - Mark-to-market timing (use NBBO mid at calculation time, not last trade)"
echo -e "  - Corporate actions (splits, dividends must adjust cost basis)"
echo -e "  - Currency conversion (FX rates must be real-time, not daily)"
echo -e "  - Wash sales, short positions, options exercise — all require special logic"
echo ""

echo -e "${BOLD}${CYAN}How to prevent it${NC}"
echo -e "  What makes a strong system design answer:"
echo -e "  1. ${BOLD}Clarify requirements first${NC} — latency SLA, scale (fills/sec, symbols)"
echo -e "  2. ${BOLD}Back-of-envelope math${NC} — state size, throughput, storage needed"
echo -e "  3. ${BOLD}Component selection with rationale${NC} — not just 'use Kafka' but why"
echo -e "  4. ${BOLD}Failure modes${NC} — what breaks first, how do you recover"
echo -e "  5. ${BOLD}Observability${NC} — how do you know P&L is correct at 3pm on a volatile day"
echo ""
