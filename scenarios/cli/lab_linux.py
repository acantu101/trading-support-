#!/usr/bin/env python3
"""
Support Engineer Challenge Lab - Environment Setup
===================================================
Replicates every scenario in the HTML challenge lab with real files,
directories, logs, services, and processes on your Linux VM.

Run with: sudo python3 lab_setup.py [--scenario N] [--teardown]

LINUX & SYSTEMS SCENARIOS (match HTML lab L1-L8):
  1   L-01  Hung oms_client consuming CPU
  2   L-02  Memory leak in mdf_feed_handler
  3   L-03  Log file with errors — grep/awk analysis
  4   L-04  Port 8080 already in use — find the process
  5   L-05  Broken file permissions on trading app
  6   L-06  Large files eating disk space
  7   L-07  Failed systemd service (riskengine)
  8   L-08  Full one-box performance triage
  9         Zombie processes from risk_engine
  10        Runaway log file / disk pressure
  99        FULL INCIDENT — all faults simultaneously
"""

import os
import sys
import time
import signal
import shutil
import socket
import resource
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
import random
from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    save_pid as _sp, load_pids as _lp, spawn as _spwn,
    kill_pids, kill_strays, remove_lab_dir,
    show_status as _show_status,
    run_menu,
)

# ─────────────────────────────────────────────
#  RESOURCE LIMITS — keeps VM stable
# ─────────────────────────────────────────────
CPU_LIMIT_PERCENT = 50    # oms_client: 50% of one core
MEM_LIMIT_MB      = 256   # mdf_feed_handler: max 256 MB
LOG_LIMIT_MB      = 50    # fix_engine log: max 50 MB

# ─────────────────────────────────────────────
#  LAB DIRECTORY STRUCTURE
# ─────────────────────────────────────────────
LAB_ROOT = Path("/tmp/lab")
DIRS = {
    "oms":          LAB_ROOT / "oms"          / "bin",
    "oms_logs":     LAB_ROOT / "oms"          / "logs",
    "oms_config":   LAB_ROOT / "oms"          / "config",
    "mdf":          LAB_ROOT / "mdf"          / "bin",
    "mdf_logs":     LAB_ROOT / "mdf"          / "logs",
    "fix":          LAB_ROOT / "fix_engine"   / "bin",
    "fix_logs":     LAB_ROOT / "fix_engine"   / "logs",
    "risk":         LAB_ROOT / "risk"         / "bin",
    "risk_logs":    LAB_ROOT / "risk"         / "logs",
    "opt_trading":  LAB_ROOT / "opt"          / "trading",
    "var_log":      LAB_ROOT / "var"          / "log" / "trading",
    "archive":      LAB_ROOT / "var"          / "log" / "archive",
    "pids":         LAB_ROOT / "run",
}


# ══════════════════════════════════════════════
#  FILESYSTEM SETUP  (always runs first)
# ══════════════════════════════════════════════

def create_directory_structure():
    header("Creating Lab Directory Structure")
    for name, path in DIRS.items():
        path.mkdir(parents=True, exist_ok=True)
        ok(f"Created {path}")


def write_base_configs():
    """Write config files shared across all scenarios."""
    header("Writing Config & Service Files")

    # OMS config
    cfg = DIRS["oms_config"] / "oms.conf"
    cfg.write_text("""\
[oms]
host            = 10.0.1.50
port            = 8080
max_connections = 200
heartbeat_ms    = 500
reconnect_delay = 5

[database]
host     = db-primary.trading.internal
port     = 5432
name     = oms_prod
pool_min = 5
pool_max = 20

[logging]
level = INFO
file  = /tmp/lab/oms/logs/oms.log
""")
    ok(f"Written {cfg}")

    # FIX session config
    fix_cfg = DIRS["fix"] / "fix_sessions.cfg"
    fix_cfg.write_text("""\
[SESSION]
BeginString=FIX.4.4
SenderCompID=FIRM_OMS
TargetCompID=EXCHANGE_A
HeartBtInt=30
StartTime=08:00:00
EndTime=17:30:00
ResetOnLogon=Y

[SESSION]
BeginString=FIX.4.4
SenderCompID=FIRM_OMS
TargetCompID=EXCHANGE_B
HeartBtInt=30
StartTime=08:00:00
EndTime=17:30:00
""")
    ok(f"Written {fix_cfg}")

    # Trading app files for the permission scenario (L-05)
    opt = DIRS["opt_trading"]
    config_yml = opt / "config.yml"
    start_sh   = opt / "start.sh"

    config_yml.write_text("""\
database:
  host: db-primary.trading.internal
  port: 5432
  name: oms_prod
  user: trader
  password: s3cr3t_p@ssword

api_keys:
  exchange_a: EXCH-A-KEY-12345
  exchange_b: EXCH-B-KEY-67890
""")
    start_sh.write_text("""\
#!/bin/bash
set -e
echo "Starting trading application..."
cd /opt/trading
python3 app.py --config config.yml
""")
    # Intentionally break permissions so student must fix them
    os.chmod(str(config_yml), 0o777)   # too open  → student fixes to 640
    os.chmod(str(start_sh),   0o644)   # not executable → student fixes to 700
    ok(f"Written {config_yml}  (permissions intentionally broken: 777)")
    ok(f"Written {start_sh}  (permissions intentionally broken: 644 / not executable)")


def write_trading_log():
    """
    Write a realistic trading app log with mixed INFO/WARN/ERROR entries.
    Used by L-03 (log analysis with grep/awk).
    """
    log_path = DIRS["var_log"] / "app.log"
    templates = [
        ("INFO",  "08:01:00", "OMS started, listening on port 8080"),
        ("INFO",  "08:01:01", "Connected to database pool (5 connections)"),
        ("INFO",  "08:01:02", "FIX session established with EXCHANGE_A SeqNum=1"),
        ("INFO",  "08:15:33", "Order received: AAPL BUY 5000 @ LIMIT 189.50 (OrderID=TRD-0001)"),
        ("INFO",  "08:15:33", "Order routed to EXCHANGE_A"),
        ("INFO",  "08:15:34", "Execution report: AAPL BUY 5000 FILLED @ 189.50"),
        ("INFO",  "09:00:11", "Order received: GOOGL SELL 200 @ MARKET (OrderID=TRD-0002)"),
        ("WARN",  "09:02:11", "Heartbeat missed from TargetCompID=EXCHANGE_B (attempt 1/3)"),
        ("WARN",  "09:02:41", "Heartbeat missed from TargetCompID=EXCHANGE_B (attempt 2/3)"),
        ("INFO",  "09:02:44", "Reconnected to EXCHANGE_B SeqNum=1043"),
        ("INFO",  "09:28:50", "Order received: TSLA BUY 1000 @ LIMIT 248.00 (OrderID=TRD-0003)"),
        ("ERROR", "09:30:01", "Order rejected: insufficient margin (OrderID=TRD-0003)"),
        ("INFO",  "09:30:02", "Order received: MSFT BUY 300 @ LIMIT 380.10 (OrderID=TRD-0004)"),
        ("ERROR", "09:30:05", "Database connection timeout after 30s (pool exhausted)"),
        ("ERROR", "09:30:06", "Database connection timeout after 30s (pool exhausted)"),
        ("WARN",  "09:30:07", "CPU usage above 80% threshold — load avg 3.2"),
        ("ERROR", "09:30:08", "oms_client thread not responding to heartbeat (attempt 1)"),
        ("ERROR", "09:30:13", "oms_client thread not responding to heartbeat (attempt 2)"),
        ("ERROR", "09:30:18", "oms_client HUNG — no response in 10s, initiating restart"),
        ("ERROR", "09:30:20", "Database connection timeout after 30s (pool exhausted)"),
        ("ERROR", "09:30:22", "FIX session disconnected from EXCHANGE_A: SeqNum gap detected"),
        ("WARN",  "09:30:30", "Order queue depth: 847 (threshold: 500)"),
        ("ERROR", "09:30:45", "Order rejected: symbol not found NVDA2 (OrderID=TRD-0042)"),
        ("ERROR", "09:30:50", "Database connection timeout after 30s (pool exhausted)"),
        ("INFO",  "09:31:10", "oms_client restarted successfully PID=9182"),
        ("INFO",  "09:32:00", "Order queue draining: 423 remaining"),
        ("INFO",  "09:33:00", "Order queue draining: 201 remaining"),
        ("INFO",  "09:34:00", "Order queue cleared"),
        ("INFO",  "10:00:00", "All systems nominal"),
    ]
    lines = [f"{level:<5} [{ts}] {msg}" for level, ts, msg in templates]
    log_path.write_text("\n".join(lines) + "\n")
    ok(f"Written {log_path}  ({len(lines)} lines, mix of INFO/WARN/ERROR)")
    return log_path


def write_large_log_files():
    """Write large rotated log files to simulate disk pressure (L-06)."""
    sizes = [
        ("trading.log",   200_000),
        ("trading.log.1", 500_000),
        ("trading.log.2", 800_000),
        ("trading.log.3", 150_000),
    ]
    for name, lines in sizes:
        p = DIRS["var_log"] / name
        p.write_text(
            "INFO  [09:30:00] trade event tick data price=189.50 symbol=AAPL\n" * lines
        )
        size_mb = p.stat().st_size / 1_048_576
        ok(f"Written {p.name}  ({size_mb:.1f} MB)")

    for i in range(1, 4):
        p = DIRS["archive"] / f"oms_{i}.log.gz.bak"
        p.write_text("X" * 1_000_000)
        ok(f"Written archive/{p.name}")


def write_systemd_files():
    """Write fake systemd unit + journal log for L-07."""
    systemd_dir = LAB_ROOT / "systemd"
    systemd_dir.mkdir(parents=True, exist_ok=True)

    unit_file = systemd_dir / "riskengine.service"
    unit_file.write_text("""\
[Unit]
Description=Trading Risk Engine
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=trader
WorkingDirectory=/opt/trading
ExecStart=/opt/trading/bin/risk_engine --config /opt/trading/config.yml
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
""")
    ok(f"Written {unit_file}")

    journal_log = DIRS["risk_logs"] / "riskengine_journal.log"
    journal_log.write_text("""\
Jan 15 09:14:01 trading-server systemd[1]: Starting Trading Risk Engine...
Jan 15 09:14:01 trading-server risk_engine[3421]: INFO  Loading config from /opt/trading/config.yml
Jan 15 09:14:02 trading-server risk_engine[3421]: INFO  Connecting to PostgreSQL db-primary.trading.internal:5432
Jan 15 09:14:02 trading-server risk_engine[3421]: INFO  Connected. Pool size: 10
Jan 15 09:14:02 trading-server risk_engine[3421]: INFO  Loading risk parameters from database
Jan 15 09:14:03 trading-server risk_engine[3421]: INFO  Risk engine initialised. Listening on port 9090
Jan 15 09:14:03 trading-server systemd[1]: Started Trading Risk Engine.
Jan 15 09:28:44 trading-server risk_engine[3421]: WARN  Position limit approaching for TSLA (85% of max)
Jan 15 09:30:01 trading-server risk_engine[3421]: INFO  Market open — activating real-time risk checks
Jan 15 09:30:47 trading-server risk_engine[3421]: ERROR Segmentation fault (core dumped)
Jan 15 09:30:47 trading-server systemd[1]: riskengine.service: Main process exited, code=dumped, status=11/SEGV
Jan 15 09:30:47 trading-server systemd[1]: riskengine.service: Failed with result 'core-dump'.
Jan 15 09:30:47 trading-server systemd[1]: Failed to start Trading Risk Engine.
Jan 15 09:30:52 trading-server systemd[1]: riskengine.service: Scheduled restart job, restart counter is at 1.
Jan 15 09:30:52 trading-server systemd[1]: Starting Trading Risk Engine...
Jan 15 09:30:52 trading-server risk_engine[3445]: ERROR Failed to connect to PostgreSQL: FATAL: too many connections
Jan 15 09:30:52 trading-server systemd[1]: riskengine.service: Main process exited, code=exited, status=1/FAILURE
Jan 15 09:30:52 trading-server systemd[1]: riskengine.service: Failed with result 'exit-code'.
Jan 15 09:30:57 trading-server systemd[1]: riskengine.service: Scheduled restart job, restart counter is at 2.
Jan 15 09:30:57 trading-server risk_engine[3461]: ERROR Failed to connect to PostgreSQL: FATAL: too many connections
Jan 15 09:30:57 trading-server systemd[1]: riskengine.service: Failed with result 'exit-code'.
Jan 15 09:31:02 trading-server systemd[1]: riskengine.service: Start request repeated too quickly.
Jan 15 09:31:02 trading-server systemd[1]: riskengine.service: Failed with result 'exit-code'.
Jan 15 09:31:02 trading-server systemd[1]: Failed to start Trading Risk Engine.
""")
    ok(f"Written {journal_log}")
    return unit_file, journal_log


# ══════════════════════════════════════════════
#  BACKGROUND PROCESS WORKERS
# ══════════════════════════════════════════════

def _cpu_spin(name: str, limit_percent: int = CPU_LIMIT_PERCENT):
    """Throttled CPU burn — simulates hung oms_client."""
    try:
        import setproctitle; setproctitle.setproctitle(name)
    except ImportError:
        pass
    burn  = limit_percent / 100
    cycle = 0.1
    while True:
        deadline = time.time() + cycle * burn
        while time.time() < deadline:
            pass
        time.sleep(cycle * (1.0 - burn))


def _memory_leak(name: str, chunk_mb: int = 2, interval: float = 0.5,
                 limit_mb: int = MEM_LIMIT_MB):
    """Capped memory leak — simulates leaking mdf_feed_handler."""
    try:
        import setproctitle; setproctitle.setproctitle(name)
    except ImportError:
        pass
    limit_bytes = limit_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes * 2, limit_bytes * 2))
    except Exception:
        pass
    held = []
    total = 0
    while True:
        if total + chunk_mb <= limit_mb:
            held.append(b"X" * (chunk_mb * 1024 * 1024))
            total += chunk_mb
        time.sleep(interval)


def _zombie_factory(name: str, count: int = 5):
    """
    Creates real zombie processes.
    SIG_DFL on SIGCHLD = children stay in Z state until parent calls wait().
    SIG_IGN would auto-reap them — no zombies visible.
    """
    try:
        import setproctitle; setproctitle.setproctitle(name)
    except ImportError:
        pass
    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    for _ in range(count):
        pid = os.fork()
        if pid == 0:
            os._exit(0)
        time.sleep(0.5)
    while True:
        time.sleep(60)


def _log_spammer(name: str, path: str, interval: float = 0.02,
                 limit_mb: int = LOG_LIMIT_MB):
    """Size-capped log spammer — simulates runaway fix_engine logger."""
    try:
        import setproctitle; setproctitle.setproctitle(name)
    except ImportError:
        pass
    limit_bytes = limit_mb * 1024 * 1024
    counter = 0
    while True:
        try:
            if os.path.getsize(path) < limit_bytes:
                with open(path, "a") as f:
                    f.write(
                        f"[{datetime.now().isoformat()}] DEBUG market tick "
                        f"#{counter}: AAPL=189.{counter % 100:02d} "
                        f"GOOGL=175.{counter % 100:02d}\n"
                    )
                counter += 1
                time.sleep(interval)
            else:
                time.sleep(1)
        except FileNotFoundError:
            time.sleep(1)


def _port_holder(name: str, port: int = 8080):
    """Binds to a port and holds it — simulates a process blocking port 8080."""
    try:
        import setproctitle; setproctitle.setproctitle(name)
    except ImportError:
        pass
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("0.0.0.0", port))
        sock.listen(5)
    except OSError as e:
        print(f"  [port_holder] Could not bind port {port}: {e}", flush=True)
    while True:
        time.sleep(60)


# ══════════════════════════════════════════════
#  PID FILE HELPERS  (thin wrappers over common.py)
# ══════════════════════════════════════════════

def _save_pid(name: str, pid: int):   _sp(DIRS["pids"], name, pid)
def _load_pids() -> dict:             return _lp(DIRS["pids"])
def _spawn(target, args, pid_name):   return _spwn(target, args, DIRS["pids"], pid_name)


# ══════════════════════════════════════════════
#  SCENARIO LAUNCHERS
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario L-01 — Hung oms_client (CPU Spike)")
    print("  A trader reports their OMS is unresponsive.")
    print(f"  Suspected: oms_client has hung, pegging CPU at ~{CPU_LIMIT_PERCENT}%.\n")

    for i in range(2):
        pid = _spawn(_cpu_spin, ("oms_client", CPU_LIMIT_PERCENT), f"oms_client_{i}")
        ok(f"oms_client spawned  PID={pid}  (capped at {CPU_LIMIT_PERCENT}% CPU)")

    print(f"""
{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Find all processes named oms_client and their PIDs
{CYAN}       pgrep -la oms_client
       ps aux | grep oms_client{RESET}

  2. Check CPU and memory usage of those PIDs
{CYAN}       top -p $(pgrep -d, oms_client)
       ps -p <PID> -o pid,ppid,%cpu,%mem,stat,cmd{RESET}

  3. Kill gracefully first, then forcefully if needed
{CYAN}       sudo kill -15 <PID>
       sudo kill -9  <PID>   # if still alive after 5s{RESET}

  4. Verify the process is gone
{CYAN}       pgrep oms_client || echo "All clear"
       ps aux | grep [o]ms_client{RESET}
""")


def launch_scenario_2():
    header("Scenario L-02 — Memory Leak in mdf_feed_handler")
    print("  Market data latency is spiking. Engineers suspect")
    print("  mdf_feed_handler is not releasing memory between sessions.\n")

    pid = _spawn(_memory_leak, ("mdf_feed_handler", 2, 0.3, MEM_LIMIT_MB), "mdf_feed_handler")
    ok(f"mdf_feed_handler spawned  PID={pid}  (grows to {MEM_LIMIT_MB}MB then holds)")

    print(f"""
{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Find the process and its memory footprint
{CYAN}       pgrep -la mdf_feed_handler
       ps -p <PID> -o pid,%mem,rss,vsz,cmd{RESET}

  2. Watch memory grow in real time
{CYAN}       watch -n 1 'ps -p <PID> -o pid,%mem,rss,vsz'{RESET}

  3. Check system-wide memory pressure + /proc details
{CYAN}       free -h
       vmstat 1 5
       awk '/Vm/ {{printf "%-12s %8.2f GB\\n", $1, $2/1024/1024}}' /proc/<PID>/status{RESET}

  4. Terminate the leaking process
{CYAN}       sudo kill -15 <PID>{RESET}

  5. Confirm memory is reclaimed
{CYAN}       free -h{RESET}
""")


def launch_scenario_3():
    header("Scenario L-03 — Analyze a Log File for Errors")
    print("  The trading system log is reporting errors.")
    print("  Understand frequency and type before escalating.\n")

    log_path = write_trading_log()

    print(f"""
{BOLD}── Log file:{RESET}  {CYAN}{log_path}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Count total lines containing ERROR
{CYAN}       grep -c "ERROR" {log_path}{RESET}

  2. Show the last 50 lines in real time
{CYAN}       tail -f -n 50 {log_path}{RESET}

  3. Extract unique error messages ranked by frequency
{CYAN}       grep "ERROR" {log_path} | sort | uniq -c | sort -rn{RESET}

  4. Find all errors between 09:30 and 09:31 (market open)
{CYAN}       grep "09:3[01]" {log_path} | grep "ERROR"
       grep -A2 -B1 "ERROR" {log_path}{RESET}

{BOLD}── Bonus ──────────────────────────────────────────────{RESET}
{CYAN}       # Count each log level
       awk '{{print $1}}' {log_path} | sort | uniq -c | sort -rn

       # Extract all OrderIDs that appear in errors
       grep "ERROR" {log_path} | grep -oP 'OrderID=\\K\\S+'{RESET}
""")


def launch_scenario_4():
    header("Scenario L-04 — Port 8080 Already In Use")
    print("  A deployment failed because port 8080 is already bound.")
    print("  Identify what's using it and decide whether to kill it.\n")

    pid = _spawn(_port_holder, ("oms_server", 8080), "oms_server_port8080")
    ok(f"oms_server spawned  PID={pid}  (holding port 8080)")

    print(f"""
{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Identify which process is listening on port 8080
{CYAN}       ss -tlnp | grep :8080
       lsof -i :8080{RESET}

  2. Find the PID and process name
{CYAN}       ss -tlnp | grep :8080   # look for pid= in output{RESET}

  3. Check how long that process has been running
{CYAN}       ps -p <PID> -o pid,etime,cmd{RESET}

  4. List ALL open ports on the system
{CYAN}       ss -tlnp
       netstat -tlnp{RESET}

  5. Kill it to free the port
{CYAN}       sudo kill -15 <PID>
       ss -tlnp | grep :8080   # verify it's gone{RESET}
""")


def launch_scenario_5():
    header("Scenario L-05 — Fix Broken File Permissions")
    print("  A trading application won't start.")
    print("  'Permission denied' reading config.yml and executing start.sh.\n")

    opt      = DIRS["opt_trading"]
    cfg      = opt / "config.yml"
    start    = opt / "start.sh"

    def perms(p):
        return oct(os.stat(str(p)).st_mode)[-3:]

    ok(f"Files ready at {opt}/")
    warn(f"config.yml current permissions: {perms(cfg)}  (target: 640)")
    warn(f"start.sh   current permissions: {perms(start)}  (target: 700 + executable)")

    print(f"""
{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Check current permissions on both files
{CYAN}       ls -la {opt}/{RESET}

  2. Make config.yml readable by owner+group only (640)
{CYAN}       chmod 640 {cfg}{RESET}

  3. Make start.sh executable by owner only (700)
{CYAN}       chmod 700 {start}{RESET}

  4. Change ownership to user 'trader' and group 'trading'
{CYAN}       sudo useradd -m trader 2>/dev/null; sudo groupadd trading 2>/dev/null
       sudo chown trader:trading {cfg}
       sudo chown trader:trading {start}{RESET}

  5. Verify
{CYAN}       ls -la {opt}/{RESET}

{BOLD}── Permission number cheat sheet ───────────────────────{RESET}
  640 = rw-r-----   owner: rw,  group: r,   others: none
  700 = rwx------   owner: rwx, group: none, others: none
  755 = rwxr-xr-x   owner: all, others: read+execute
  644 = rw-r--r--   owner: rw,  others: read only
""")


def launch_scenario_6():
    header("Scenario L-06 — Find Large Files Eating Disk Space")
    print("  Disk alert fired. /tmp/lab/var/log is filling up.")
    print("  Trading logs are likely the culprit. Find them fast.\n")

    write_large_log_files()

    log_dir = DIRS["var_log"]
    archive = DIRS["archive"]

    print(f"""
{BOLD}── Files created under:{RESET}
{CYAN}       {log_dir}
       {archive}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Find the top 10 largest files under the lab log dir
{CYAN}       find {LAB_ROOT}/var -type f -printf '%s %p\\n' | sort -rn | head -10{RESET}

  2. Find directories consuming the most space
{CYAN}       du -sh {LAB_ROOT}/var/log/* | sort -rh | head -10{RESET}

  3. Find all .log files larger than 1 MB
{CYAN}       find {LAB_ROOT}/var -name "*.log" -size +1M -type f
       find {LAB_ROOT}/var -name "*.log" -size +1M -exec ls -lh {{}} \\;{RESET}

  4. Show human-readable sizes for everything in the log dir
{CYAN}       du -sh {log_dir}/*
       ls -lh {log_dir}/{RESET}

{BOLD}── Bonus ──────────────────────────────────────────────{RESET}
{CYAN}       du -sh {LAB_ROOT}/      # total lab size
       df -i /tmp               # inode usage (can fill before disk space){RESET}
""")


def launch_scenario_7():
    header("Scenario L-07 — Diagnose a Failed systemd Service")
    print("  riskengine.service crashed after a deployment.")
    print("  Diagnose it without restarting blindly.\n")

    unit_file, journal_log = write_systemd_files()

    print(f"""
{BOLD}── Files created:{RESET}
{CYAN}       {unit_file}       ← unit file to inspect
       {journal_log}  ← simulated journal output{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Check the current status of the service
{CYAN}       # Real system: sudo systemctl status riskengine.service
       # Lab — read the simulated journal:
       cat {journal_log}{RESET}

  2. View the last 100 lines of its logs
{CYAN}       # Real system: journalctl -u riskengine.service -n 100
       tail -100 {journal_log}{RESET}

  3. Check if it's set to restart automatically
{CYAN}       grep -i "restart" {unit_file}
       cat {unit_file}{RESET}

  4. Identify the TWO separate failure modes in the log
{CYAN}       # Failure 1: what signal killed PID 3421?
       grep "status=" {journal_log}
       # Failure 2: why did restart fail?
       grep "too many" {journal_log}{RESET}

  5. What would you fix before restarting?
     → Fix root cause FIRST (DB connection pool)
     → Only then: sudo systemctl restart riskengine.service
     → Watch: journalctl -u riskengine.service -f

{BOLD}── Root causes hidden in the log ───────────────────────{RESET}
  • PID 3421 → SIGSEGV (signal 11) — segfault in trading code
  • Restart attempts → "too many connections" — DB pool exhausted
  • Key lesson: blind restart loops without fixing root cause = more failures
""")


def launch_scenario_8():
    header("Scenario L-08 — Full One-Box Performance Triage")
    print("  A trader calls at 09:35: 'everything is slow.'")
    print("  You have 5 minutes to diagnose before escalating.\n")
    print("  Launching CPU spike + memory pressure + log spam simultaneously.\n")

    pid1 = _spawn(_cpu_spin, ("oms_client", CPU_LIMIT_PERCENT), "triage_oms_client")
    ok(f"oms_client  (CPU spike)  PID={pid1}")

    pid2 = _spawn(_memory_leak, ("mdf_feed_handler", 2, 0.3, MEM_LIMIT_MB), "triage_mdf")
    ok(f"mdf_feed_handler (memory) PID={pid2}")

    log_path = str(DIRS["fix_logs"] / "fix_engine_debug.log")
    Path(log_path).touch()
    pid3 = _spawn(_log_spammer, ("fix_engine", log_path, 0.02, LOG_LIMIT_MB), "triage_fix_logger")
    ok(f"fix_engine  (log spam)   PID={pid3}")

    write_trading_log()

    print(f"""
{BOLD}── Your Tasks (triage in order) ───────────────────────{RESET}
  1. Check uptime and load averages
{CYAN}       uptime{RESET}

  2. Identify the bottleneck: CPU vs memory vs I/O wait
{CYAN}       top -b -n 1 | head -20
       # %us = user CPU   %sy = kernel   %wa = I/O wait (high = disk issue){RESET}

  3. Find the top CPU-consuming processes
{CYAN}       ps aux --sort=-%cpu | head -10{RESET}

  4. Check for disk I/O issues
{CYAN}       iostat -x 1 3
       # await (ms) = avg I/O wait,  %util = disk busy %{RESET}

  5. Check for network errors on interfaces
{CYAN}       ip -s link
       netstat -i
       # RX-ERR / TX-ERR columns — non-zero = network problem{RESET}

  6. Summarise findings as you would to a manager
       "Server shows load avg X vs Y cores.
        Top process is Z consuming X% CPU.
        IO wait is X% — disk/no disk issue.
        Recommend: kill Z / investigate disk / escalate."

{BOLD}── Triage priority ─────────────────────────────────────{RESET}
  1. Kill oms_client   → CPU freed, trading unblocked
  2. Kill mdf_feed     → memory freed, latency drops
  3. Stop fix_engine   → disk alert clears
""")


def launch_scenario_9():
    header("Scenario — Zombie Processes from risk_engine")
    print("  The risk calculation engine crashed mid-session.")
    print("  Child worker processes are now zombies.\n")

    pid = _spawn(_zombie_factory, ("risk_engine", 5), "risk_engine")
    ok(f"risk_engine (zombie factory) spawned  PID={pid}")
    info("Waiting 3s for zombies to appear...")
    time.sleep(3)

    print(f"""
{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Find all zombie processes
{CYAN}       ps aux | awk '$8 == "Z"'
       ps -eo pid,ppid,stat,cmd | grep ' Z '{RESET}

  2. Identify the parent process (risk_engine)
{CYAN}       ps -p <ZOMBIE_PID> -o ppid=
       pgrep -la risk_engine{RESET}

  3. Understand why zombies exist
       A zombie = child exited but parent never called wait()
       Holds a PID slot but uses ZERO memory or CPU

  4. Reap the zombies by killing the parent
{CYAN}       sudo kill -15 {pid}      # SIGTERM the parent
       sudo kill -17 {pid}      # OR: SIGCHLD to trigger wait(){RESET}

  5. Verify zombies are gone
{CYAN}       ps aux | awk '$8 == "Z"'
       pgrep risk_engine || echo "All clear"{RESET}

{BOLD}── Why zombies matter ──────────────────────────────────{RESET}
  Linux has a finite PID table (~32768 slots by default).
  Enough zombies = system can't fork new processes
  = trading engine can't spawn order handler threads.
""")


def launch_scenario_10():
    header("Scenario — Runaway Log File (Disk Pressure)")
    print(f"  Ops alert: {LAB_ROOT}/fix_engine/logs is filling fast.")
    print("  A fix_engine process is spamming debug logs.\n")

    log_path = str(DIRS["fix_logs"] / "fix_engine_debug.log")
    Path(log_path).touch()

    pid = _spawn(_log_spammer, ("fix_engine", log_path, 0.01, LOG_LIMIT_MB), "fix_engine_logger")
    ok(f"fix_engine log spammer  PID={pid}  (capped at {LOG_LIMIT_MB}MB)")
    ok(f"Log file: {log_path}")

    print(f"""
{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Check disk usage of the log directory
{CYAN}       du -sh {LAB_ROOT}/
       du -sh {DIRS["fix_logs"]}/
       df -h /tmp{RESET}

  2. Identify the process writing to the file
{CYAN}       lsof {log_path}
       fuser {log_path}{RESET}

  3. Watch the file grow in real time
{CYAN}       watch -n 1 'du -sh {log_path}'
       tail -f {log_path}{RESET}

  4. Stop the runaway logger
{CYAN}       sudo kill -15 {pid}{RESET}

  5. Truncate the log without deleting it
{CYAN}       truncate -s 0 {log_path}
       > {log_path}               # bash shorthand{RESET}

  6. Verify disk is recovered
{CYAN}       du -sh {DIRS["fix_logs"]}/
       ls -lh {log_path}{RESET}

{BOLD}── Why truncate instead of rm? ─────────────────────────{RESET}
  The running process holds an open file descriptor.
  rm removes the filename but the process keeps writing to the
  deleted inode — disk usage NEVER drops.
  truncate zeros the contents while keeping the same inode —
  the process seamlessly continues writing to the same fd.
  The file fills again if the process isn't also stopped.
""")


def launch_scenario_99():
    header("Scenario 99 — FULL INCIDENT (All Faults Simultaneously)")
    print("  Trading desk escalation: OMS down, MD feed lagging,")
    print("  risk engine zombies, port conflict, disk alert firing.\n")

    launch_scenario_1()
    time.sleep(0.5)
    launch_scenario_2()
    time.sleep(0.5)
    launch_scenario_9()
    time.sleep(0.5)
    launch_scenario_10()

    print(f"""
{BOLD}── Recommended Triage Order ────────────────────────────{RESET}
  Priority 1: CPU     → kill oms_client         → trading unblocked
  Priority 2: MEM     → kill mdf_feed_handler   → MD latency drops
  Priority 3: ZOMBIES → kill risk_engine parent  → PID table cleaned
  Priority 4: DISK    → stop fix_engine, truncate log → alert clears

{BOLD}── Key One-Liners ───────────────────────────────────────{RESET}
{CYAN}       ps auxf                              # full process tree
       ps aux --sort=-%cpu | head -15      # top CPU processes
       ps aux --sort=-%mem | head -15      # top MEM processes
       ps aux | awk '$8 == "Z"'           # find zombies
       top   # press P=CPU sort, M=MEM sort, q=quit{RESET}
""")


# ══════════════════════════════════════════════
#  TEARDOWN
# ══════════════════════════════════════════════

def teardown():
    header("Tearing Down Lab")
    kill_pids(DIRS["pids"])
    kill_strays(["oms_client", "mdf_feed_handler", "risk_engine", "fix_engine", "oms_server"])
    remove_lab_dir(LAB_ROOT)


# ══════════════════════════════════════════════
#  STATUS
# ══════════════════════════════════════════════

def show_status():
    _show_status(DIRS["pids"], "Linux Lab")


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

SCENARIO_MAP = {
    1:  (launch_scenario_1,  "L-01  Hung oms_client — CPU spike"),
    2:  (launch_scenario_2,  "L-02  Memory leak in mdf_feed_handler"),
    3:  (launch_scenario_3,  "L-03  Log file analysis (grep/awk/uniq)"),
    4:  (launch_scenario_4,  "L-04  Port 8080 already in use"),
    5:  (launch_scenario_5,  "L-05  Broken file permissions"),
    6:  (launch_scenario_6,  "L-06  Large files eating disk space"),
    7:  (launch_scenario_7,  "L-07  Failed systemd service (riskengine)"),
    8:  (launch_scenario_8,  "L-08  Full one-box performance triage"),
    9:  (launch_scenario_9,  "      Zombie processes from risk_engine"),
    10: (launch_scenario_10, "      Runaway log file / disk pressure"),
    99: (launch_scenario_99, "      FULL INCIDENT — all faults simultaneously"),
}


def _setup():
    create_directory_structure()
    write_base_configs()


def main():
    run_menu(SCENARIO_MAP, "Linux & Systems Challenge Lab",
             setup_fn=_setup, teardown_fn=teardown, status_fn=show_status,
             script_name="lab_linux.py")


if __name__ == "__main__":
    main()
