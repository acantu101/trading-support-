#!/bin/bash
# fix/verify.sh — confirms the seqnum fix and simulates a successful FIX reconnect
source "$(dirname "$0")/../_lib/common.sh"

FIX_DIR="$HOME/trading-support/fix"
SENDER="$FIX_DIR/sessions/PROD-OMS-EXCHANGE/sender.seq"
TARGET="$FIX_DIR/sessions/PROD-OMS-EXCHANGE/target.seq"

echo ""
step "Verifying FIX session state..."

# ── Check files exist ────────────────────────────────────────────────────────
if [[ ! -f "$SENDER" || ! -f "$TARGET" ]]; then
  err "Session files not found. Run setup.sh first."
  exit 1
fi

SENDER_VAL=$(cat "$SENDER" | tr -d '[:space:]')
TARGET_VAL=$(cat "$TARGET" | tr -d '[:space:]')

echo ""
echo -e "  sender.seq  →  ${BOLD}${SENDER_VAL}${NC}"
echo -e "  target.seq  →  ${BOLD}${TARGET_VAL}${NC}"
echo ""

# ── Evaluate ─────────────────────────────────────────────────────────────────
if [[ "$SENDER_VAL" != "$TARGET_VAL" ]]; then
  err "Sequence numbers still mismatched."
  echo ""
  echo -e "  Exchange expects : ${RED}${TARGET_VAL}${NC}"
  echo -e "  OMS would send   : ${RED}${SENDER_VAL}${NC}"
  echo ""
  warn "Fix: echo '${TARGET_VAL}' > $SENDER"
  echo ""
  exit 1
fi

# ── Simulate successful reconnect ─────────────────────────────────────────────
ok "Sequence numbers aligned — simulating reconnect..."
echo ""
sleep 0.4

NOW=$(date -u '+%Y%m%d-%H:%M:%S')

echo -e "${CYAN}  ── Simulated FIX Session Log ──────────────────────────────────────${NC}"
sleep 0.3
echo -e "  ${MUTED:-$'\033[90m'}$NOW [INFO]  TCP connection established to exchange-gw.prod.local:9878${NC}"
sleep 0.4
echo -e "  $NOW [SEND]  8=FIX.4.2|9=73|35=A|34=${SENDER_VAL}|49=PROD-OMS|52=${NOW}|56=EXCHANGE|98=0|108=30|10=214|"
sleep 0.5
echo -e "  $NOW [RECV]  8=FIX.4.2|9=68|35=A|34=${TARGET_VAL}|49=EXCHANGE|52=${NOW}|56=PROD-OMS|98=0|108=30|10=199|"
sleep 0.3
echo -e "  ${GREEN}$NOW [INFO]  Logon confirmed — session PROD-OMS->EXCHANGE established${NC}"
sleep 0.4
echo -e "  $NOW [SEND]  8=FIX.4.2|9=148|35=D|34=$((SENDER_VAL+1))|49=PROD-OMS|52=${NOW}|56=EXCHANGE|11=ORD-RECOVERY-001|21=1|38=1000|40=2|44=182.50|54=1|55=AAPL|10=143|"
sleep 0.3
echo -e "  ${GREEN}$NOW [RECV]  8=FIX.4.2|9=120|35=8|34=$((TARGET_VAL+1))|49=EXCHANGE|56=PROD-OMS|11=ORD-RECOVERY-001|39=0|150=0|54=1|55=AAPL|38=1000|44=182.50|10=201|${NC}"
sleep 0.2
echo -e "  ${GREEN}$NOW [INFO]  ExecutionReport: ORD-RECOVERY-001 → OrdStatus=New (39=0) ✓${NC}"
echo -e "  ${CYAN}──────────────────────────────────────────────────────────────────${NC}"
echo ""

# ── Success summary ───────────────────────────────────────────────────────────
echo -e "${GREEN}${BOLD}  ✓ SCENARIO COMPLETE${NC}"
echo ""
echo -e "  ${BOLD}What you diagnosed:${NC}"
echo -e "    The OMS rebooted with ${RED}ResetOnLogon=Y${NC} (or equivalent), resetting"
echo -e "    sender.seq to 1. The exchange's last known seqnum was ${BOLD}4892${NC}."
echo -e "    Every Logon attempt sent MsgSeqNum=1, which the exchange rejected"
echo -e "    as too low (tag 35=5, tag 58: MsgSeqNum too low)."
echo ""
echo -e "  ${BOLD}What you fixed:${NC}"
echo -e "    Set sender.seq to ${GREEN}4892${NC} so the OMS Logon matches the exchange's"
echo -e "    expected next inbound sequence number. Session re-established."
echo -e "    Queued orders now flowing — ExecutionReport confirms first fill."
echo ""
echo -e "  ${BOLD}Real-world options at this point:${NC}"
echo -e "    1. ${CYAN}Sync seqnums (what you did)${NC} — safest, no message gaps"
echo -e "    2. ${YELLOW}SequenceReset (35=4, GapFillFlag=N)${NC} — resets both sides to agreed num"
echo -e "    3. ${YELLOW}ResendRequest (35=2)${NC} — ask exchange to retransmit missed messages"
echo -e "    4. ${RED}ResetOnLogon=Y${NC} — forces both sides to 1; only safe if exchange agrees"
echo ""
echo -e "  ${BOLD}How to prevent this:${NC}"
echo -e "    Set ${CYAN}ResetOnLogon=N${NC} and ${CYAN}ResetOnLogout=N${NC} in fix.cfg (already correct"
echo -e "    in this scenario's config). The seqnum store persists across restarts."
echo -e "    Monitor for seqnum drift with alerting on tag 34 gaps in the log."
echo ""
