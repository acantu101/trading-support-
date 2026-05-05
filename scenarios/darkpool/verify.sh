#!/bin/bash
# scenarios/darkpool/verify.sh — Verify fix for TRF reporting delay exceeding 10-second window

source "$(dirname "$0")/../_lib/common.sh"

CONF_FILE="$HOME/trading-support/darkpool/config/trf-reporter.conf"

banner "Dark Pool — TRF Reporting Compliance Verify"

# ── Config exists? ─────────────────────────────────────────────────────────────
if [[ ! -f "$CONF_FILE" ]]; then
    err "Config not found: $CONF_FILE"
    err "Run setup.sh first."
    exit 1
fi

info "Reading trf-reporter.conf..."
sleep 0.3

# ── Parse REPORTING_DELAY_MS ──────────────────────────────────────────────────
DELAY_MS=$(grep -E '^REPORTING_DELAY_MS\s*=' "$CONF_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '[:space:]')

if [[ -z "$DELAY_MS" ]]; then
    err "REPORTING_DELAY_MS not found in $CONF_FILE"
    exit 1
fi

# ── Not fixed? ────────────────────────────────────────────────────────────────
if [[ "$DELAY_MS" -ge 10000 ]]; then
    echo ""
    err "NOT FIXED"
    echo ""
    echo -e "${RED}REPORTING_DELAY_MS=${BOLD}${DELAY_MS}ms${NC}${RED} still exceeds the 10-second regulatory window.${NC}"
    echo ""
    echo -e "${YELLOW}FINRA Rule 4552 requires TRF reporting within ${BOLD}10,000ms${NC}${YELLOW} of execution.${NC}"
    echo -e "${YELLOW}Every trade reported after 10 seconds is a ${BOLD}reportable violation${NC}${YELLOW}.${NC}"
    echo ""
    echo -e "${BOLD}Nudge:${NC} Edit ${BOLD}${CONF_FILE}${NC} and set:"
    echo -e "    ${CYAN}REPORTING_DELAY_MS=9000${NC}"
    echo ""
    echo -e "Then restart the reporter process to pick up the new config:"
    echo -e "    ${CYAN}pkill -HUP -f trf-reporter${NC}  (or your process restart method)"
    echo ""
    echo -e "Verify the running process is using the new value before calling this done."
    echo ""
    exit 1
fi

# ── Fixed ────────────────────────────────────────────────────────────────────
ok "REPORTING_DELAY_MS=${DELAY_MS}ms — within regulatory window."
echo ""

info "Querying TRF reporter status..."
sleep 0.3
echo ""

echo -e "${BOLD}${CYAN}\$ trf-status --last 50${NC}"
sleep 0.3
echo ""
echo -e "    TRF Reporter v2.4.1  |  Mode: PRODUCTION  |  Venue: FINRA TRF"
echo -e "    ─────────────────────────────────────────────────────────────────"
sleep 0.3
echo -e "    Config:         REPORTING_DELAY_MS=${DELAY_MS}"
sleep 0.3
echo -e "    Avg latency:    ${GREEN}${BOLD}8,712ms${NC}      ← within 10s window"
sleep 0.3
echo -e "    p99 latency:    ${GREEN}${BOLD}9,241ms${NC}      ← still within 10s window"
sleep 0.3
echo -e "    Max latency:    ${GREEN}${BOLD}9,618ms${NC}      ← within 10s window"
sleep 0.3
echo -e "    Violations:     ${GREEN}${BOLD}0${NC}  (last 50 trades)"
sleep 0.3
echo -e "    Queue depth:    ${GREEN}normal${NC}  (2 trades pending, <100ms old)"
sleep 0.3
echo -e "    Uptime:         14h 32m"
sleep 0.3
echo -e "    Trades today:   4,821  |  Reported: 4,821  |  Pending: 2"
echo ""

sleep 0.3
info "Simulating FINRA acknowledgement..."
sleep 0.5
echo ""

NOW=$(date +"%Y-%m-%d %H:%M:%S")
DATE=$(date +"%Y-%m-%d")

echo -e "${BOLD}${CYAN}┌─────────────────────────────────────────────────────────────┐${NC}"
echo -e "${BOLD}${CYAN}│  FINRA Market Operations — Acknowledgement                  │${NC}"
echo -e "${BOLD}${CYAN}└─────────────────────────────────────────────────────────────┘${NC}"
echo ""
sleep 0.3
echo -e "    From:     FINRA Market Operations <mops@finra.org>"
echo -e "    To:       Compliance Department — Dark Pool Venue ID: DP-7741"
echo -e "    Date:     ${NOW}"
echo -e "    Subject:  Self-Report Acknowledgement — Rule 4552 Latency"
echo ""
sleep 0.3
echo -e "    This message confirms receipt of your self-report submitted"
echo -e "    regarding REPORTING_DELAY_MS configuration in your TRF reporting"
echo -e "    pipeline (incident window: prior 72 hours)."
echo ""
sleep 0.3
echo -e "    ${GREEN}Remediation confirmed.${NC} Your updated configuration"
echo -e "    (REPORTING_DELAY_MS=${DELAY_MS}) has been logged. Compliance"
echo -e "    monitoring period: 90 days from ${DATE}."
echo ""
sleep 0.3
echo -e "    During the monitoring period, FINRA will review your TRF"
echo -e "    latency distribution biweekly. Maintain the remediated"
echo -e "    configuration and retain all documentation of root cause"
echo -e "    analysis and corrective actions taken."
echo ""
sleep 0.3
echo -e "    This is not a formal disciplinary action. Self-reporting"
echo -e "    demonstrates good-faith compliance and is weighted favorably"
echo -e "    in any subsequent review."
echo ""
echo -e "    — FINRA Market Operations"
echo ""

ok "Self-report acknowledged. 90-day monitoring period begins."

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║           SCENARIO COMPLETE — DARK POOL TRF                 ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}What you diagnosed${NC}"
echo -e "  The TRF reporter was configured with REPORTING_DELAY_MS=10500, placing"
echo -e "  every single dark pool trade report outside the 10-second window required"
echo -e "  by FINRA Rule 4552. A test/staging config value had leaked into production"
echo -e "  — a classic environment parity failure."
echo ""

echo -e "${BOLD}${CYAN}What you fixed${NC}"
echo -e "  Updated REPORTING_DELAY_MS to ${DELAY_MS}ms in trf-reporter.conf and"
echo -e "  restarted the reporter process to apply the change. All subsequent trades"
echo -e "  will be reported within the regulatory window with headroom to spare."
echo ""

echo -e "${BOLD}${CYAN}Real-world context${NC}"
echo -e "  ${BOLD}FINRA Rule 4552 — TRF Reporting:${NC}"
echo -e "  Trades executed in a dark pool (ATS) must be reported to a FINRA Trade"
echo -e "  Reporting Facility within 10 seconds of execution during market hours."
echo -e "  FINRA publishes aggregate dark pool volume biweekly. Late reports are"
echo -e "  individually logged and accrue as violations."
echo ""
echo -e "  ${BOLD}TRF reporting mechanics:${NC}"
echo -e "  Trade capture → internal queue → TRF gateway → FINRA TRF"
echo -e "  The 10-second clock starts at execution, not at queue entry."
echo -e "  Queue backup or gateway latency can cause violations even if the"
echo -e "  config is correct — monitor p99, not just average latency."
echo ""
echo -e "  ${BOLD}Self-report vs FINRA-initiated investigation:${NC}"
echo -e "  Self-reporting a violation is ${BOLD}strongly favored${NC} by FINRA. Firms that"
echo -e "  self-report typically receive reduced sanctions and monitoring-only"
echo -e "  outcomes. Firms caught by FINRA surveillance without self-reporting"
echo -e "  face formal disciplinary proceedings, fines, and reputational damage."
echo -e "  When in doubt, self-report early."
echo ""

echo -e "${BOLD}${CYAN}How to prevent it${NC}"
echo -e "  - Enforce environment parity: production configs must be generated from"
echo -e "    a separate prod config source, never copied from staging."
echo -e "  - Add a startup assertion in trf-reporter: if REPORTING_DELAY_MS >= 10000"
echo -e "    in PRODUCTION environment, refuse to start and page on-call."
echo -e "  - Monitor TRF latency in real-time: alert at p99 > 8,500ms (giving 1.5s"
echo -e "    of headroom before the regulatory breach threshold)."
echo -e "  - Compliance incident documentation checklist:"
echo -e "    [ ] Timeline (execution time → report time for each affected trade)"
echo -e "    [ ] Root cause (config value, how it got there)"
echo -e "    [ ] Scope (how many trades, what time window)"
echo -e "    [ ] Remediation (config fix + process restart timestamp)"
echo -e "    [ ] Prevention (what change prevents recurrence)"
echo -e "    [ ] Self-report submission confirmation"
echo ""
