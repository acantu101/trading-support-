#!/bin/bash
# scenarios/networking/verify.sh — Verify fix for tc netem packet loss on loopback

source "$(dirname "$0")/../_lib/common.sh"

SIM_FLAG="$HOME/trading-support/networking/.simulation_mode"
LOG_FILE="$HOME/trading-support/networking/logs/interface_errors.log"

banner "Networking — Packet Loss Verify"

# ── Check current tc state ────────────────────────────────────────────────────
info "Checking tc qdisc state on loopback..."
sleep 0.3

TC_OUTPUT=$(sudo tc qdisc show dev lo 2>/dev/null)
NETEM_ACTIVE=false

if echo "$TC_OUTPUT" | grep -qi "netem" && echo "$TC_OUTPUT" | grep -qi "loss"; then
    NETEM_ACTIVE=true
fi

if $NETEM_ACTIVE; then
    echo ""
    err "NOT FIXED"
    echo ""
    echo -e "${RED}Packet loss is still active on the loopback interface.${NC}"
    echo ""
    echo -e "${BOLD}Current tc state:${NC}"
    echo "$TC_OUTPUT" | sed 's/^/    /'
    echo ""
    LOSS_VAL=$(echo "$TC_OUTPUT" | grep -oP 'loss \K[^\s]+')
    echo -e "${YELLOW}Loss rate detected: ${BOLD}${LOSS_VAL:-unknown}${NC}"
    echo ""
    echo -e "${BOLD}Nudge:${NC} Remove the netem rule with:"
    echo -e "    ${CYAN}sudo tc qdisc del dev lo root${NC}"
    echo ""
    echo -e "Then confirm it's gone:"
    echo -e "    ${CYAN}sudo tc qdisc show dev lo${NC}"
    echo -e "    (should show only the default 'noqueue' or 'mq' qdisc)"
    echo ""
    exit 1
fi

# ── Fixed ────────────────────────────────────────────────────────────────────
ok "No netem qdisc found on lo — packet loss has been cleared."
echo ""

info "Running connectivity validation: ping -c 20 127.0.0.1"
echo ""
sleep 0.3

ping -c 20 127.0.0.1
PING_EXIT=$?

echo ""

if [[ $PING_EXIT -ne 0 ]]; then
    warn "ping returned non-zero — loopback may have other issues."
else
    ok "All 20 packets received — 0% loss confirmed."
fi

sleep 0.3
echo ""
info "Order latency telemetry (OMS → matching engine, via loopback):"
sleep 0.3
echo ""
echo -e "    ${GREEN}Order latency:   ${BOLD}47µs${NC}         ${GREEN}← baseline restored${NC}"
echo -e "    ${RED}During incident: ${BOLD}800µs${NC}${RED}+${NC}        ${RED}← TCP retransmit storm${NC}"
echo -e "    ${YELLOW}SLA threshold:   ${BOLD}200µs${NC}        ${YELLOW}← firm latency SLA${NC}"
sleep 0.3
echo ""

info "Interface error counters (captured at incident peak):"
sleep 0.3
echo ""

if [[ -f "$LOG_FILE" ]]; then
    cat "$LOG_FILE" | head -30 | sed 's/^/    /'
else
    echo -e "${BOLD}${CYAN}\$ ip -s link show lo${NC}"
    sleep 0.3
    cat <<'EOF'
    1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN
        link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
        RX: bytes  packets  errors  dropped  missed  mcast
            8421504   65536       0     1847       0      0
        TX: bytes  packets  errors  dropped  carrier  collsn
            8421504   65536       0       0        0       0
EOF
    echo ""
    echo -e "    ${YELLOW}RX dropped: 1847${NC} — injected by tc netem during simulation"
    echo -e "    ${GREEN}RX errors:  0${NC}    — no physical layer (CRC) errors; purely software-injected loss"
fi

sleep 0.3
echo ""
ok "Network baseline fully restored."

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║           SCENARIO COMPLETE — NETWORKING                    ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}What you diagnosed${NC}"
echo -e "  A tc netem rule was injecting 12% packet loss on the loopback interface,"
echo -e "  simulating a degraded network path between the OMS and the matching engine."
echo -e "  The symptom was latency spiking from 47µs to 800µs+ and FIX session"
echo -e "  timeouts, with no physical hardware fault."
echo ""

echo -e "${BOLD}${CYAN}What you fixed${NC}"
echo -e "  Removed the netem qdisc with: sudo tc qdisc del dev lo root"
echo -e "  The loopback interface reverted to its default noqueue discipline,"
echo -e "  eliminating all injected loss. Order latency returned to baseline."
echo ""

echo -e "${BOLD}${CYAN}Real-world context${NC}"
echo -e "  tc netem (Network Emulator) is the standard Linux tool for chaos"
echo -e "  engineering — it can inject loss, delay, jitter, duplication, and"
echo -e "  reordering. It's legitimate in staging; left on in production it's"
echo -e "  catastrophic. Real packet loss in trading co-location comes from:"
echo -e ""
echo -e "  - ${RED}CRC errors${NC}       → physical layer: bad cable, SFP, or NIC"
echo -e "  - ${YELLOW}RX drops${NC}         → buffer overflow: NIC ring buffer too small for burst"
echo -e "  - ${YELLOW}TX drops${NC}         → kernel socket buffer exhausted, CPU too slow to drain"
echo -e ""
echo -e "  12% loss is catastrophic for FIX: TCP retransmits fire, RTT triples,"
echo -e "  HeartBtInt breaches cause Logout, and position state becomes uncertain"
echo -e "  because you don't know which fills the exchange acknowledged."
echo -e "  Co-location networks use dedicated cross-connects and redundant paths"
echo -e "  (active/active bonding) precisely to avoid any packet loss."
echo ""

echo -e "${BOLD}${CYAN}How to prevent it${NC}"
echo -e "  - Never run chaos tooling (tc netem, toxiproxy, pumba) on production hosts."
echo -e "  - Gate netem usage behind a config flag that is explicitly absent in prod."
echo -e "  - Add a startup check: if tc qdisc show dev lo | grep netem → abort boot."
echo -e "  - Monitor RX/TX drop counters via SNMP or node_exporter; alert on any"
echo -e "    non-zero drops on the internal trading VLAN."
echo -e "  - Right-size NIC ring buffers: ethtool -G eth0 rx 4096 for high-throughput"
echo -e "    market data feeds to prevent software-side drops at burst."
echo ""
