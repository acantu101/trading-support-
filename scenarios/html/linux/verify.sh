#!/bin/bash
# linux/verify.sh — Verify fix for runaway CPU hog process
source "$(dirname "$0")/../_lib/common.sh"

banner "Linux Scenario: Verify Fix"

PID_FILE="$HOME/trading-support/pids/linux-hog.pid"
CRONTAB_FILE="$HOME/trading-support/linux/crontab.txt"

# ── Read the saved PID ────────────────────────────────────────────────────────
if [ ! -f "$PID_FILE" ]; then
  err "PID file not found: $PID_FILE"
  err "Did you run setup.sh first? The scenario must be set up before verifying."
  exit 1
fi

HOG_PID=$(cat "$PID_FILE")

# ── Check if process is still alive ──────────────────────────────────────────
if kill -0 "$HOG_PID" 2>/dev/null; then
  # ── Not fixed branch ─────────────────────────────────────────────────────
  echo ""
  err "The CPU hog is still running."
  err "Process PID ${HOG_PID} is alive and consuming CPU."
  echo ""
  info "Confirm with:"
  echo ""
  echo "    ps aux --sort=-%cpu | head -5"
  echo ""
  ps aux --sort=-%cpu 2>/dev/null | head -6 | sed 's/^/    /' || \
    ps aux 2>/dev/null | head -6 | sed 's/^/    /'
  echo ""
  step "Fix: kill the process and verify it's gone:"
  step "     kill ${HOG_PID}"
  step "     kill -0 ${HOG_PID} 2>/dev/null && echo 'still alive' || echo 'dead'"
  echo ""
  step "If it respawns: check the crontab file for a restart entry:"
  step "     cat $CRONTAB_FILE"
  echo ""
  exit 1
fi

# ── Fixed branch — process is gone ───────────────────────────────────────────
ok "PID ${HOG_PID} is no longer running — CPU hog has been killed."
echo ""

step "Simulating before/after CPU comparison..."
sleep 0.3
echo ""

# ── Before: what top looked like when the hog was running ──────────────────
echo -e "${BOLD}${CYAN}--- BEFORE: top output while oms-batch-reconcile was running ---${NC}"
echo ""
cat << 'TOPBEFORE'
    top - 09:42:17 up 3 days,  2:14,  2 users,  load average: 3.85, 3.91, 3.78
    Tasks: 198 total,   5 running, 193 sleeping,   0 stopped,   0 zombie
    %Cpu(s): 95.2 us,  2.1 sy,  0.0 ni,  2.0 id,  0.3 wa,  0.0 hi,  0.4 si
    MiB Mem :  15920.0 total,   1208.4 free,   8934.6 used,   5777.0 buff/cache
    MiB Swap:   2048.0 total,   1892.0 free,    156.0 used.   6742.1 avail Mem

      PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
    12481 acm       20   0  312884  98312   9824 R  387.5   0.6  42:18.22 oms-batch-reconcile
      982 root      20   0 1824508 112044  68820 S    0.7   0.7   1:14.03 containerd
     1201 acm       20   0  914736  72980  52340 S    0.3   0.4   0:28.11 python3
      541 root      20   0  289444   6812   5840 S    0.0   0.0   0:01.02 systemd
      312 root      20   0  156748   4120   3672 S    0.0   0.0   0:00.44 cron
TOPBEFORE
echo ""
sleep 0.3

# ── After: what top looks like now ───────────────────────────────────────────
echo -e "${BOLD}${CYAN}--- AFTER: top output after killing oms-batch-reconcile ---${NC}"
echo ""
cat << 'TOPAFTER'
    top - 09:42:35 up 3 days,  2:14,  2 users,  load average: 0.12, 1.82, 3.21
    Tasks: 195 total,   1 running, 194 sleeping,   0 stopped,   0 zombie
    %Cpu(s):  3.1 us,  0.8 sy,  0.0 ni, 95.7 id,  0.2 wa,  0.0 hi,  0.2 si
    MiB Mem :  15920.0 total,   6412.8 free,   3700.2 used,   5807.0 buff/cache
    MiB Swap:   2048.0 total,   2048.0 free,      0.0 used.   9820.4 avail Mem

      PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
      982 root      20   0 1824508 112044  68820 S    0.7   0.7   1:14.21 containerd
     1201 acm       20   0  914736  72980  52340 S    0.3   0.4   0:28.22 python3
     1889 acm       20   0  189412  18320  14200 S    0.2   0.1   0:02.14 marketdata-norm
      541 root      20   0  289444   6812   5840 S    0.0   0.0   0:01.02 systemd
      312 root      20   0  156748   4120   3672 S    0.0   0.0   0:00.44 cron
TOPAFTER
echo ""
sleep 0.3
ok "System CPU: 95.2% -> 3.1% user. Load average returning to normal."
echo ""

# ── Crontab warning ───────────────────────────────────────────────────────────
sleep 0.3
if [ -f "$CRONTAB_FILE" ]; then
  echo -e "${BOLD}${YELLOW}>>> Checking crontab for restart entry...${NC}"
  echo ""
  sleep 0.3
  grep -v "^#" "$CRONTAB_FILE" | grep -v "^$" | sed 's/^/    /'
  echo ""
  CRON_RESTARTER=$(grep "hog.py\|oms-batch\|reconcil" "$CRONTAB_FILE" | grep -v "^#" | head -1)
  if [ -n "$CRON_RESTARTER" ]; then
    warn "A crontab entry would restart this process every 5 minutes!"
    warn "    ${CRON_RESTARTER}"
    echo ""
    warn "In production you would also remove this entry:"
    echo ""
    echo "    crontab -e   (then delete the hog.py / oms-batch-reconcile line)"
    echo ""
    info "The crontab.txt file in this lab is simulated — it is NOT installed"
    info "in your real crontab. In a real incident you would run: crontab -l"
    info "to check for restart entries."
  fi
fi
echo ""

# ── SCENARIO COMPLETE summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║         SCENARIO COMPLETE — Runaway CPU Process             ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}1. What you diagnosed${NC}"
echo "   System load average was ~3.9 on a 4-core box. top showed"
echo "   oms-batch-reconcile consuming 387% CPU (all 4 cores) as a Python"
echo "   process. It appeared in ps aux --sort=-%cpu at the top of the list."
echo "   The process was the nightly OMS position reconciliation job that"
echo "   should have exited by 18:30 — but a missing exit condition (a"
echo "   removed 'break' statement) kept it looping indefinitely, starving"
echo "   all other processes of CPU time."
echo ""

echo -e "${BOLD}${CYAN}2. What you fixed${NC}"
echo "   Killed PID ${HOG_PID} with: kill ${HOG_PID}"
echo "   System CPU dropped from 95.2% to 3.1% immediately."
echo "   In a production scenario you would also:"
echo "   - Remove the crontab entry that would respawn the process"
echo "   - Fix the source code to add the exit condition / break statement"
echo "   - Deploy the fix before the next nightly batch window"
echo ""

echo -e "${BOLD}${CYAN}3. Real-world context${NC}"
echo "   Runaway processes in trading environments typically stem from:"
echo "   - Batch jobs without exit conditions (this scenario)"
echo "   - Memory-mapped file readers in an infinite retry loop"
echo "   - GC storms in JVM-based systems (long GC pauses trigger timeouts"
echo "     that trigger retries that trigger more GC)"
echo "   - Hung order reconciliation threads waiting on a downstream response"
echo ""
echo "   Partial mitigation (when you can't kill immediately):"
echo "   - renice +19 <pid>    : drop the process to lowest priority"
echo "   - taskset -cp 0 <pid> : pin to a single core, freeing others"
echo "   These keep the system responsive while you coordinate a proper fix."
echo ""
echo "   Tools for diagnosing runaway processes:"
echo "   - top / htop                 : interactive CPU/memory view"
echo "   - perf top -p <pid>          : which functions are consuming CPU"
echo "   - strace -p <pid> -c         : syscall frequency summary"
echo "   - py-spy top --pid <pid>     : Python call-stack sampling (no attach)"
echo ""

echo -e "${BOLD}${CYAN}4. How to prevent it in production${NC}"
echo "   a) CPU usage alerts: alert on-call when any single process exceeds"
echo "      80% CPU for more than 60 seconds outside the batch window."
echo "   b) Process supervision with runtime limits:"
echo "      timeout 3600 python3 reconcile.py  (kill after 1 hour)"
echo "      systemd: TimeoutStopSec and CPUQuota= in unit files"
echo "   c) Batch jobs should write a completion flag and check it on startup:"
echo "      if [[ -f /tmp/reconcile.done ]]; then exit 0; fi"
echo "   d) NUMA and core pinning for latency-sensitive services: reserve"
echo "      cores 0-7 for market-data and order routing; batch jobs on 8-15."
echo "      Runaway batch jobs can then only affect their assigned cores."
echo "   e) IRQ affinity: pin NIC interrupts to cores not used by trading"
echo "      processes so a CPU hog can't delay packet processing."
echo "   f) Regular crontab audits — 'temporary' restart entries have a way"
echo "      of staying in production forever."
echo ""
