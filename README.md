# ⚙️ Support Engineer Challenge Lab

A self-contained Linux lab environment that simulates real trading infrastructure failures for **support engineering interview preparation**. Includes an interactive browser-based challenge guide covering Linux, Networking, Python, Kafka, FIX Protocol, Kubernetes, SQL, Airflow, and more.

> Spin up realistic broken environments, triage them with real Linux tools, and tear everything down cleanly when you're done.

---

## 📋 Table of Contents

- [What's Included](#whats-included)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [The Interactive Lab (HTML)](#the-interactive-lab-html)
- [The Lab Setup Script (Python)](#the-lab-setup-script-python)
- [Scenarios](#scenarios)
- [Directory Structure](#directory-structure)
- [Command Reference](#command-reference)
- [Interview Tips](#interview-tips)
- [Teardown](#teardown)

---

## What's Included

| File | Purpose |
|------|---------|
| `challenge-lab.html` | Interactive browser guide — 60+ challenges across 12 categories with hints, solutions, and progress tracking |
| `lab_setup.py` | Python script that spawns real broken processes on your Linux machine to practice against |

---

## Prerequisites

- Linux or macOS (tested on Ubuntu 20.04+)
- Python 3.7+
- A modern browser (for the HTML lab)
- Standard Unix utilities: `ps`, `pgrep`, `kill`, `top`, `lsof`, `du`, `df`
- Optional but recommended: `htop`, `stress`

No third-party Python packages required. `setproctitle` is used opportunistically if installed — it improves process naming in `ps` output:

```bash
pip install setproctitle   # optional
```

---

## Installation

```bash
git clone https://github.com/<your-username>/support-engineer-lab.git
cd support-engineer-lab
chmod +x lab_setup.py
```

---

## The Interactive Lab (HTML)

Open `challenge-lab.html` in your browser — no server required.

```bash
# macOS
open challenge-lab.html

# Linux
xdg-open challenge-lab.html

# Or just drag the file into your browser
```

### What's inside

The lab has **12 categories** with **60+ challenges**, each with a realistic scenario, task checklist, optional hints, and a full solution:

| Category | Challenges | Topics |
|----------|-----------|--------|
| 🐧 Linux & Systems | 8 | Process management, log analysis, disk/memory |
| 🌐 Networking | 5 | TCP/IP, DNS, port debugging, packet capture |
| 🐍 Python & Bash | 6 | Scripting, automation, log parsing |
| 📈 Trading Scenarios | 4 | Market making, latency, order flow |
| ☁️ AWS | 4 | EC2, S3, CloudWatch, IAM |
| 📨 Kafka | 6 | Consumer lag, partition rebalancing, producer issues |
| 📡 FIX Protocol | 5 | Session management, message types, tag debugging |
| ⚡ Native / C++ / Perf | 5 | Core dumps, perf profiling, memory layout |
| 🗄️ SQL | 6 | Query optimisation, slow queries, deadlocks |
| ☸️ Kubernetes & ArgoCD | 6 | Pod debugging, rolling deployments, CrashLoopBackOff |
| 🔀 Git & Regression Hunt | 5 | Bisect, blame, reverting bad deploys |
| 🔄 Airflow & Pipelines | 5 | DAG failures, sensor blocks, SLA misses |

**Features:**
- ✅ Click-to-check task progress per challenge
- 💡 Hint system — reveals progressively without spoiling the solution
- 👁️ Collapsible solutions with syntax-highlighted commands
- 📊 Per-category progress bars
- ⌨️ Quick-launch link to an in-browser Linux terminal ([copy.sh/v2](https://copy.sh/v2))

---

## The Lab Setup Script (Python)

`lab_setup.py` creates a realistic fake trading file system under `/tmp/lab/` and spawns real background processes you can practice triaging with actual Linux tools.

```bash
# Interactive menu — choose your scenario
python3 lab_setup.py

# Launch a specific scenario directly
python3 lab_setup.py --scenario 1

# Check what lab processes are currently running
python3 lab_setup.py --status

# Print the command cheat sheet
python3 lab_setup.py --cheatsheet

# Tear everything down and clean up
python3 lab_setup.py --teardown
```

---

## Scenarios

### Scenario 1 — Hung `oms_client` (CPU Spike)
> *A trader reports their order management system is unresponsive.*

Launches two `oms_client` processes burning 100% CPU each — simulating a hung thread that won't respond to heartbeats.

**Tasks:**
1. Find all processes named `oms_client` and their PIDs
2. Check CPU and memory usage of those PIDs
3. Kill gracefully (SIGTERM), then forcefully (SIGKILL) if needed
4. Verify the process is gone

---

### Scenario 2 — Memory Leak in `mdf_feed_handler`
> *Market data latency is spiking. The feed handler isn't releasing memory.*

Launches a process that allocates ~10 MB of RAM every 300ms and never frees it. Watch RSS grow in real time.

**Tasks:**
1. Find the process and its memory footprint
2. Watch memory grow with `watch` + `ps`
3. Inspect `/proc/<PID>/status` for VM stats
4. Terminate the leaking process and confirm memory is reclaimed

---

### Scenario 3 — Zombie Processes from `risk_engine`
> *The risk calculation engine crashed mid-session. Worker PIDs are stuck as zombies.*

Launches a parent process that forks 5 children, ignores `SIGCHLD`, and lets them die — producing real zombie entries in the process table.

**Tasks:**
1. Find zombie processes (`ps aux | awk '$8=="Z"'`)
2. Identify the parent PID
3. Understand why zombies exist and what resources they hold
4. Reap them by killing the parent or sending `SIGCHLD`

---

### Scenario 4 — Runaway Log File / Disk Pressure
> *Ops alert: the trading log directory is filling up fast.*

Launches a `fix_engine` process that writes thousands of debug log lines per second, simulating misconfigured log levels in production.

**Tasks:**
1. Check disk usage of the log directory (`du`, `df`)
2. Identify the process writing to the file (`lsof`, `fuser`)
3. Stop the runaway logger
4. Truncate the log file without deleting it
5. Verify disk pressure is cleared

---

### Scenario 5 — Full Incident (All Faults Simultaneously)
> *Trading desk escalation: OMS down, MD feed lagging, risk engine crashed, disk alert firing.*

Launches all four fault scenarios at once. Triage by business impact and work through them in priority order — just like a real production incident.

**Recommended triage order:**
1. Kill `oms_client` CPU hogs → trading unblocked
2. Free memory from `mdf_feed_handler` → MD latency drops
3. Reap `risk_engine` zombies → PID table cleaned
4. Stop log spammer + truncate log → disk alert clears

---

## Directory Structure

The script creates the following structure under `/tmp/lab/`:

```
/tmp/lab/
├── oms/
│   ├── bin/
│   ├── config/
│   │   └── oms.conf              # OMS config (host, DB pool, heartbeat)
│   └── logs/
│       └── oms.log               # Pre-populated with realistic error entries
├── mdf/
│   ├── bin/
│   └── logs/
├── fix_engine/
│   ├── bin/
│   │   └── fix_sessions.cfg      # FIX 4.4 session definitions
│   └── logs/
│       └── fix_engine_debug.log  # Grows rapidly during Scenario 4
├── risk/
│   ├── bin/
│   └── logs/
├── var/
│   └── log/
│       └── trading/
│           ├── trading.log.1     # Rotated logs (disk pressure simulation)
│           ├── trading.log.2
│           └── trading.log.3
└── run/
    ├── oms_client_0.pid
    ├── oms_client_1.pid
    ├── mdf_feed_handler.pid
    ├── risk_engine.pid
    └── fix_engine_logger.pid
```

---

## Command Reference

Run the built-in cheat sheet at any time:

```bash
python3 lab_setup.py --cheatsheet
```

| Task | Command |
|------|---------|
| Find process by name | `pgrep -la <name>` |
| Snapshot with stats | `ps aux \| grep <name>` |
| Detailed PID stats | `ps -p <PID> -o pid,ppid,%cpu,%mem,stat,cmd` |
| Watch PID live | `top -p <PID>` |
| Memory from /proc | `cat /proc/<PID>/status \| grep -i vm` |
| Find zombies | `ps aux \| awk '$8=="Z"'` |
| Who has file open | `lsof <file>` |
| All files a PID has | `lsof -p <PID>` |
| Graceful kill | `kill -15 <PID>` |
| Force kill | `kill -9 <PID>` |
| Truncate log | `truncate -s 0 <logfile>` |
| Disk usage | `du -sh <dir>` / `df -h` |
| Process tree | `ps auxf` or `pstree -p <PID>` |

---

## Interview Tips

**Structure your answers around this flow:**

1. **Identify** — find the process, confirm it's the culprit
2. **Inspect** — check CPU, memory, open files, parent/child relationships
3. **Intervene** — graceful signal first, force only if needed
4. **Verify** — confirm the problem is resolved, check for side effects
5. **Explain** — be ready to explain *why* the issue happened, not just how you fixed it

**Things interviewers listen for:**

- You try `SIGTERM` before `SIGKILL` — shows you understand graceful shutdown
- You know the difference between RSS and VSZ for memory
- You can explain *why* zombies exist (parent hasn't called `wait()`) not just how to remove them
- You think about business impact when prioritising multiple issues
- You verify your fix worked rather than assuming

**Pro tip:** Run Scenario 5 (full incident) and practice triaging in priority order. That's exactly what a real on-call engineer would do and it shows structured thinking under pressure.

---

## Teardown

All lab processes and files are cleaned up with a single command:

```bash
python3 lab_setup.py --teardown
```

This sends `SIGTERM` then `SIGKILL` to all tracked processes, sweeps for any strays by name, and removes the entire `/tmp/lab/` directory tree.

---

## License

MIT — use freely for interview prep, learning, or teaching Linux process management.
