#!/bin/bash
# fix/setup.sh — FIX session sequence number mismatch scenario
source "$(dirname "$0")/../_lib/common.sh"

banner "FIX Scenario: SeqNum Mismatch"
ensure_dirs

# ── Create FIX directory structure ──────────────────────────────────────────
FIX_DIR="$HOME/trading-support/fix"
step "Creating FIX session directories..."
mkdir -p "$FIX_DIR/sessions/PROD-OMS-EXCHANGE"
mkdir -p "$FIX_DIR/logs"
mkdir -p "$FIX_DIR/config"
ok "Directories created: $FIX_DIR"

# ── Sequence number files ────────────────────────────────────────────────────
step "Writing sequence number files (broken state)..."
echo "1"    > "$FIX_DIR/sessions/PROD-OMS-EXCHANGE/sender.seq"
echo "4892" > "$FIX_DIR/sessions/PROD-OMS-EXCHANGE/target.seq"
ok "sender.seq=1 (WRONG — should be 4892), target.seq=4892"

# ── QuickFIX-style config ────────────────────────────────────────────────────
step "Writing fix.cfg..."
cat > "$FIX_DIR/config/fix.cfg" << 'FIXCFG'
[DEFAULT]
ConnectionType=initiator
ReconnectInterval=30
FileStorePath=~/trading-support/fix/sessions
FileLogPath=~/trading-support/fix/logs
StartTime=00:00:00
EndTime=00:00:00
UseDataDictionary=Y
DataDictionary=FIX42.xml
ValidateUserDefinedFields=N

[SESSION]
BeginString=FIX.4.2
SenderCompID=PROD-OMS
TargetCompID=EXCHANGE
SocketConnectHost=exchange-gw.prod.local
SocketConnectPort=9878
HeartBtInt=30
ResetOnLogon=N
ResetOnLogout=N
ResetOnDisconnect=N
FIXCFG
ok "fix.cfg written"

# ── Realistic FIX message log ────────────────────────────────────────────────
step "Writing messages.log (shows seqnum mismatch exchange rejection)..."
cat > "$FIX_DIR/logs/messages.log" << 'FIXLOG'
2026-05-04 08:00:00.012 [INFO]  Session PROD-OMS->EXCHANGE: initiating connection to exchange-gw.prod.local:9878
2026-05-04 08:00:00.087 [INFO]  TCP connection established
2026-05-04 08:00:00.089 [SEND]  8=FIX.4.2|9=73|35=A|34=1|49=PROD-OMS|52=20260504-08:00:00.089|56=EXCHANGE|98=0|108=30|10=214|
2026-05-04 08:00:00.112 [RECV]  8=FIX.4.2|9=103|35=5|34=4892|49=EXCHANGE|52=20260504-08:00:00.112|56=PROD-OMS|58=MsgSeqNum too low, expected 4892 got 1|10=087|
2026-05-04 08:00:00.113 [ERROR] Received Logout (35=5) from EXCHANGE: MsgSeqNum too low, expected 4892 got 1
2026-05-04 08:00:00.113 [ERROR] Session terminated by counterparty
2026-05-04 08:00:00.114 [WARN]  Attempting reconnect in 30 seconds...

2026-05-04 08:00:30.201 [INFO]  TCP connection established (retry #1)
2026-05-04 08:00:30.202 [SEND]  8=FIX.4.2|9=73|35=A|34=1|49=PROD-OMS|52=20260504-08:00:30.202|56=EXCHANGE|98=0|108=30|10=219|
2026-05-04 08:00:30.220 [RECV]  8=FIX.4.2|9=103|35=5|34=4892|49=EXCHANGE|52=20260504-08:00:30.220|56=PROD-OMS|58=MsgSeqNum too low, expected 4892 got 1|10=092|
2026-05-04 08:00:30.221 [ERROR] Received Logout (35=5): MsgSeqNum too low, expected 4892 got 1

2026-05-04 08:01:00.305 [INFO]  TCP connection established (retry #2)
2026-05-04 08:01:00.306 [SEND]  8=FIX.4.2|9=73|35=A|34=1|49=PROD-OMS|52=20260504-08:01:00.306|56=EXCHANGE|98=0|108=30|10=221|
2026-05-04 08:01:00.329 [RECV]  8=FIX.4.2|9=103|35=5|34=4892|49=EXCHANGE|52=20260504-08:01:00.329|56=PROD-OMS|58=MsgSeqNum too low, expected 4892 got 1|10=089|
2026-05-04 08:01:00.330 [ERROR] Received Logout (35=5): MsgSeqNum too low, expected 4892 got 1

2026-05-04 08:01:00.331 [WARN]  OMS attempting to queue and send pending orders...
2026-05-04 08:01:00.332 [SEND]  8=FIX.4.2|9=148|35=D|34=2|49=PROD-OMS|52=20260504-08:01:00.332|56=EXCHANGE|11=ORD-20260504-001|21=1|38=1000|40=2|44=182.50|54=1|55=AAPL|60=20260504-08:01:00|10=143|
2026-05-04 08:01:00.350 [RECV]  8=FIX.4.2|9=103|35=5|34=4892|49=EXCHANGE|52=20260504-08:01:00.350|56=PROD-OMS|58=MsgSeqNum too low, expected 4892 got 2|10=091|
2026-05-04 08:01:00.351 [ERROR] NewOrderSingle ORD-20260504-001 rejected: session not established (seqnum mismatch)

2026-05-04 08:01:00.352 [SEND]  8=FIX.4.2|9=148|35=D|34=3|49=PROD-OMS|52=20260504-08:01:00.352|56=EXCHANGE|11=ORD-20260504-002|21=1|38=500|40=2|44=415.75|54=2|55=MSFT|60=20260504-08:01:00|10=156|
2026-05-04 08:01:00.371 [RECV]  8=FIX.4.2|9=103|35=5|34=4892|49=EXCHANGE|52=20260504-08:01:00.371|56=PROD-OMS|58=MsgSeqNum too low, expected 4892 got 3|10=093|
2026-05-04 08:01:00.372 [ERROR] NewOrderSingle ORD-20260504-002 rejected: session not established (seqnum mismatch)

2026-05-04 08:01:00.373 [SEND]  8=FIX.4.2|9=150|35=D|34=4|49=PROD-OMS|52=20260504-08:01:00.373|56=EXCHANGE|11=ORD-20260504-003|21=1|38=2000|40=2|44=98.10|54=1|55=AMZN|60=20260504-08:01:00|10=167|
2026-05-04 08:01:00.392 [RECV]  8=FIX.4.2|9=103|35=5|34=4892|49=EXCHANGE|52=20260504-08:01:00.392|56=PROD-OMS|58=MsgSeqNum too low, expected 4892 got 4|10=088|
2026-05-04 08:01:00.393 [ERROR] NewOrderSingle ORD-20260504-003 rejected: session not established (seqnum mismatch)

2026-05-04 08:01:00.394 [SEND]  8=FIX.4.2|9=149|35=D|34=5|49=PROD-OMS|52=20260504-08:01:00.394|56=EXCHANGE|11=ORD-20260504-004|21=1|38=750|40=1|54=2|55=TSLA|60=20260504-08:01:00|10=172|
2026-05-04 08:01:00.413 [RECV]  8=FIX.4.2|9=103|35=5|34=4892|49=EXCHANGE|52=20260504-08:01:00.413|56=PROD-OMS|58=MsgSeqNum too low, expected 4892 got 5|10=094|
2026-05-04 08:01:00.414 [ERROR] NewOrderSingle ORD-20260504-004 rejected: session not established (seqnum mismatch)

2026-05-04 08:01:00.415 [FATAL] Circuit breaker triggered: 4 consecutive session failures. OMS halted. Manual intervention required.
FIXLOG
ok "messages.log written (logon rejection + 4 order rejections)"

# ── Investigation hints ──────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  SCENARIO READY — FIX SeqNum Mismatch${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
info "The OMS rebooted overnight and reset its sequence numbers."
info "The exchange is rejecting all logon attempts."
echo ""
echo -e "  ${BOLD}Investigate:${NC}"
echo -e "    cat $FIX_DIR/logs/messages.log"
echo -e "    cat $FIX_DIR/sessions/PROD-OMS-EXCHANGE/sender.seq"
echo -e "    cat $FIX_DIR/sessions/PROD-OMS-EXCHANGE/target.seq"
echo ""
echo -e "  ${BOLD}Fix:${NC}"
echo -e "    echo '4892' > $FIX_DIR/sessions/PROD-OMS-EXCHANGE/sender.seq"
echo ""
warn "Check logs at $FIX_DIR/logs/ — find the seqnum mismatch and correct sender.seq"
echo ""
