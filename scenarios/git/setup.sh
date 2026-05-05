#!/bin/bash
# Scenario: Bad merge overwrote SenderCompID from PROD-OMS to TEST-OMS in FIX gateway config
source "$(dirname "$0")/../_lib/common.sh"

LAB_DIR=~/trading-support/git
REPO_DIR="$LAB_DIR/trading-config"

echo "=== Git Scenario: Bad Merge / Wrong SenderCompID ==="
echo ""

# Step 1: Create directory and git repo
mkdir -p "$LAB_DIR"
mkdir -p "$REPO_DIR"
cd "$REPO_DIR"
git init -q
git config user.email "ops@tradingfirm.local"
git config user.name "Ops Bot"

# Step 2: Initial commit with PROD-OMS config
cat > gateway.cfg << 'EOF'
[FIX_SESSION]
SenderCompID=PROD-OMS
TargetCompID=EXCHANGE
SocketConnectHost=exchange-gw.prod.local
SocketConnectPort=4200
HeartBtInt=30
ResetOnLogon=Y
FileStorePath=./store
FileLogPath=./logs
EOF

git add gateway.cfg
git commit -q -m "Initial production FIX gateway configuration"

# Step 3 & 4: Feature branch — add debug logging
git checkout -q -b feature/add-debug-logging

cat > gateway.cfg << 'EOF'
[FIX_SESSION]
SenderCompID=TEST-OMS
TargetCompID=EXCHANGE
SocketConnectHost=exchange-gw.prod.local
SocketConnectPort=4200
HeartBtInt=30
ResetOnLogon=Y
FileStorePath=./store
FileLogPath=./logs
LogLevel=DEBUG
EOF

cat > debug-settings.cfg << 'EOF'
[DEBUG]
LogLevel=DEBUG
LogHeartBeats=Y
LogIncomingMessages=Y
LogOutgoingMessages=Y
ScreenLogShowIncoming=Y
ScreenLogShowOutgoing=Y
EOF

git add gateway.cfg debug-settings.cfg
git commit -q -m "Add debug logging for troubleshooting session"

# Step 7 & 8: Back to main — update HeartBtInt
git checkout -q main 2>/dev/null || git checkout -q master

# Rename branch to main if needed
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" = "master" ]; then
    git branch -m master main
fi

cat > gateway.cfg << 'EOF'
[FIX_SESSION]
SenderCompID=PROD-OMS
TargetCompID=EXCHANGE
SocketConnectHost=exchange-gw.prod.local
SocketConnectPort=4200
HeartBtInt=60
ResetOnLogon=Y
FileStorePath=./store
FileLogPath=./logs
EOF

git add gateway.cfg
git commit -q -m "Increase heartbeat interval per exchange recommendation"

# Step 9: Merge feature branch — simulate bad conflict resolution
# Merge without committing first
git merge --no-commit --no-ff feature/add-debug-logging -q 2>/dev/null || true

# Manually apply the "bad" resolution: take the feature branch's SenderCompID=TEST-OMS
# (as if the dev incorrectly resolved the conflict by accepting the feature branch version)
cat > gateway.cfg << 'EOF'
[FIX_SESSION]
SenderCompID=TEST-OMS
TargetCompID=EXCHANGE
SocketConnectHost=exchange-gw.prod.local
SocketConnectPort=4200
HeartBtInt=60
ResetOnLogon=Y
FileStorePath=./store
FileLogPath=./logs
LogLevel=DEBUG
EOF

git add gateway.cfg debug-settings.cfg
git commit -q -m "Merge branch 'feature/add-debug-logging' into main

Merged debug logging feature. Resolved conflict in gateway.cfg."

# Step 10: Write deploy log
cat > "$LAB_DIR/deploy.log" << 'EOF'
2026-05-04 09:45:10 [DEPLOY] Starting deployment pipeline for FIX gateway v2.4.1
2026-05-04 09:45:18 [DEPLOY] Artifact validated: gateway-2.4.1.tar.gz sha256=a3f9c...
2026-05-04 09:45:22 [DEPLOY] Copying config files to prod-gw-01.prod.local
2026-05-04 09:45:24 [DEPLOY] Config deployed: gateway.cfg, debug-settings.cfg
2026-05-04 09:46:01 [DEPLOY] Deployed to prod at 09:47:22 — FIX gateway restarted
2026-05-04 09:47:22 [FIX-GW ] Session initiated: SenderCompID=TEST-OMS -> EXCHANGE
2026-05-04 09:47:23 [FIX-GW ] Logon sent to EXCHANGE
2026-05-04 09:47:23 [FIX-GW ] REJECT received from EXCHANGE: "Unknown SenderCompID TEST-OMS"
2026-05-04 09:47:24 [FIX-GW ] Logon retry 1/3...
2026-05-04 09:47:25 [FIX-GW ] REJECT received from EXCHANGE: "Unknown SenderCompID TEST-OMS"
2026-05-04 09:47:26 [FIX-GW ] Logon retry 2/3...
2026-05-04 09:47:27 [FIX-GW ] REJECT received from EXCHANGE: "Unknown SenderCompID TEST-OMS"
2026-05-04 09:47:28 [FIX-GW ] FATAL: All logon attempts failed — exchange rejecting orders: Unknown SenderCompID TEST-OMS
2026-05-04 09:47:28 [DEPLOY] INCIDENT: FIX gateway unable to connect — P1 declared
2026-05-04 09:47:30 [DEPLOY] On-call engineer paged: ops-oncall@tradingfirm.local
EOF

# Step 11-13: Print instructions
echo "Repo is at ~/trading-support/git/trading-config"
echo ""
echo "Investigate:"
echo "  cd ~/trading-support/git/trading-config"
echo "  git log --oneline"
echo "  git diff HEAD~1 HEAD -- gateway.cfg"
echo "  cat ~/trading-support/git/deploy.log"
echo ""
echo "Fix: git revert HEAD"
echo "  or: git revert -n <commit-hash>"
echo "  Then: update SenderCompID back to PROD-OMS and commit"
