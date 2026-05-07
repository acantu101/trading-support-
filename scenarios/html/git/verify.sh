#!/bin/bash
# scenarios/git/verify.sh — Verify git revert of bad SenderCompID config

source "$(dirname "$0")/../_lib/common.sh"

REPO_DIR="$HOME/trading-support/git/trading-config"
GATEWAY_CFG="$REPO_DIR/gateway.cfg"

banner "Git — Trading Config Revert Verify"

# ── Repo exists? ─────────────────────────────────────────────────────────────
if [[ ! -d "$REPO_DIR/.git" ]]; then
    err "Git repo not found at $REPO_DIR"
    err "Run setup.sh first."
    exit 1
fi

if [[ ! -f "$GATEWAY_CFG" ]]; then
    err "gateway.cfg not found at $GATEWAY_CFG"
    exit 1
fi

info "Inspecting repo state..."
sleep 0.3

# ── Check SenderCompID value ─────────────────────────────────────────────────
SENDER=$(grep -i "SenderCompID" "$GATEWAY_CFG" 2>/dev/null | head -1 | cut -d= -f2 | tr -d '[:space:]')
LATEST_MSG=$(git -C "$REPO_DIR" log --oneline -1 2>/dev/null | tr '[:upper:]' '[:lower:]')
HAS_REVERT=false

if echo "$LATEST_MSG" | grep -qi "revert"; then
    HAS_REVERT=true
fi

# ── Not fixed? ───────────────────────────────────────────────────────────────
if [[ "$SENDER" != "PROD-OMS" ]] || ! $HAS_REVERT; then
    echo ""
    err "NOT FIXED"
    echo ""

    if [[ "$SENDER" == "TEST-OMS" ]]; then
        echo -e "${RED}gateway.cfg still has ${BOLD}SenderCompID=TEST-OMS${NC}${RED}.${NC}"
        echo -e "${YELLOW}The exchange will reject all logon attempts with this CompID.${NC}"
    elif [[ -z "$SENDER" ]]; then
        echo -e "${RED}SenderCompID not found in gateway.cfg.${NC}"
    else
        echo -e "${YELLOW}SenderCompID=${BOLD}${SENDER}${NC}${YELLOW} — expected PROD-OMS.${NC}"
    fi

    if ! $HAS_REVERT; then
        echo -e "${YELLOW}No revert commit found at HEAD.${NC}"
    fi

    echo ""
    echo -e "${BOLD}Nudge:${NC} Revert the bad commit and verify:"
    echo ""
    echo -e "    ${CYAN}cd $REPO_DIR${NC}"
    echo -e "    ${CYAN}git revert HEAD${NC}"
    echo -e "    ${CYAN}git log --oneline${NC}"
    echo -e "    ${CYAN}grep SenderCompID gateway.cfg${NC}"
    echo ""
    echo -e "${BOLD}Current git log:${NC}"
    git -C "$REPO_DIR" log --oneline -5 2>/dev/null | sed 's/^/    /'
    echo ""
    exit 1
fi

# ── Fixed ────────────────────────────────────────────────────────────────────
ok "Revert commit found and SenderCompID=PROD-OMS confirmed."
echo ""

info "Showing repository state..."
sleep 0.3
echo ""
echo -e "${BOLD}${CYAN}\$ git log --oneline${NC}"
sleep 0.3
git -C "$REPO_DIR" log --oneline -6 2>/dev/null | sed 's/^/    /'
sleep 0.3

echo ""
info "Verifying config diff (bad commit → current)..."
sleep 0.3
echo ""
echo -e "${BOLD}${CYAN}\$ git diff HEAD~1 HEAD -- gateway.cfg${NC}"
sleep 0.3

REVERT_HASH=$(git -C "$REPO_DIR" log --oneline -1 --format="%h" 2>/dev/null)
BAD_HASH=$(git -C "$REPO_DIR" log --oneline -2 --format="%h" 2>/dev/null | tail -1)

echo -e "    ${BOLD}--- a/gateway.cfg${NC}"
echo -e "    ${BOLD}+++ b/gateway.cfg${NC}"
echo -e "    ${RED}-SenderCompID=TEST-OMS${NC}"
echo -e "    ${GREEN}+SenderCompID=PROD-OMS${NC}"
sleep 0.3

echo ""
info "Deploying config to FIX gateway (simulation)..."
sleep 0.3
step "Pulling latest config from git..."
sleep 0.3
step "Rendering gateway.cfg → /etc/fix/gateway.cfg"
sleep 0.3
step "Sending SIGHUP to gateway process (PID 14823)..."
sleep 0.5
ok  "Gateway reloaded config without restart."
echo ""

info "Monitoring FIX logon sequence..."
sleep 0.3
echo ""
NOW=$(date +"%H:%M:%S")
sleep 0.3
echo -e "    ${CYAN}$NOW.001${NC}  [FIX] Initiating TCP connection to exchange-gateway:4321"
sleep 0.3
echo -e "    ${CYAN}$NOW.018${NC}  [FIX] TCP connected"
sleep 0.3
echo -e "    ${CYAN}$NOW.019${NC}  [FIX] Sending Logon (35=A): SenderCompID=PROD-OMS TargetCompID=EXCHANGE"
sleep 0.5
echo -e "    ${CYAN}$NOW.043${NC}  [FIX] Logon accepted — session established"
sleep 0.3
echo -e "    ${CYAN}$NOW.044${NC}  [FIX] ${GREEN}${BOLD}SESSION UP${NC} — ready to trade"
sleep 0.3
echo -e "    ${CYAN}$NOW.045${NC}  [FIX] Heartbeat interval: 30s"
echo ""
ok "FIX session established. Order flow is live."

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║              SCENARIO COMPLETE — GIT CONFIG                 ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}What you diagnosed${NC}"
echo -e "  A commit to trading-config changed SenderCompID from PROD-OMS to TEST-OMS"
echo -e "  in gateway.cfg. The exchange rejected every Logon attempt because the"
echo -e "  CompID didn't match the registered production session. All order flow"
echo -e "  was dead for the ~8-minute window before the config was reverted."
echo ""

echo -e "${BOLD}${CYAN}What you fixed${NC}"
echo -e "  Ran git revert HEAD to create a new commit that undoes the bad change."
echo -e "  The revert preserves full history — the bad commit remains visible"
echo -e "  in the log, which is critical for the post-incident audit trail."
echo ""

echo -e "${BOLD}${CYAN}Real-world context${NC}"
echo -e "  ${BOLD}git revert vs git reset:${NC}"
echo -e "  - revert creates a new commit that inverts changes → safe for shared"
echo -e "    branches; history is immutable; other engineers see what happened."
echo -e "  - reset --hard rewrites history → catastrophic on main; other engineers'"
echo -e "    branches diverge; you lose the audit trail."
echo -e "  Always revert on a shared production branch. Never reset."
echo ""
echo -e "  ${BOLD}The 8-minute blast radius:${NC}"
echo -e "  If the firm routes 4,000 orders/min at peak, 8 minutes of FIX downtime"
echo -e "  = ~32,000 missed order attempts. At \$0.01 avg commission each, that's"
echo -e "  \$320 in direct revenue — but the real cost is market-making spread loss"
echo -e "  and client trust."
echo ""
echo -e "  ${BOLD}GitOps for trading config:${NC}"
echo -e "  Git provides an immutable audit trail — every change has author, timestamp,"
echo -e "  and diff. Regulators and compliance teams love this. But it only works"
echo -e "  if you enforce it: no manual config edits on production hosts."
echo ""

echo -e "${BOLD}${CYAN}How to prevent it${NC}"
echo -e "  - Branch protection on main: require PR review + approval before merge."
echo -e "  - Add a pre-merge CI check: grep for TEST- CompIDs and fail the pipeline."
echo -e "  - Use environment-scoped config: prod/gateway.cfg and staging/gateway.cfg"
echo -e "    in separate directories — no manual environment switching."
echo -e "  - Deploy-time validation: the deploy script should assert"
echo -e "    SenderCompID matches the expected prod value before reloading."
echo -e "  - Set up an automated canary: post-deploy, verify FIX logon succeeds"
echo -e "    within 30 seconds or auto-rollback."
echo ""
