# Support Engineer Challenge Lab

A self-contained Linux lab environment that simulates real trading infrastructure failures for **support engineering interview preparation**. Includes an interactive browser-based challenge guide and Python scripts that spawn real broken processes on your Linux VM.

> Spin up realistic broken environments, triage them with real Linux tools, and tear everything down cleanly when you're done.

---

## Table of Contents

- [What's Included](#whats-included)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [The Interactive Lab (HTML)](#the-interactive-lab-html)
- [Lab Scripts](#lab-scripts)
- [Challenge Categories](#challenge-categories)
- [Directory Structure](#directory-structure)
- [Command Reference](#command-reference)
- [Interview Tips](#interview-tips)
- [Teardown](#teardown)

---

## What's Included

| File | Purpose |
|------|---------|
| `challenge-lab.html` | Interactive browser guide — 60+ challenges with hints, solutions, and progress tracking |
| `scenarios/lab.py` | Unified entry point — top-level menu across all 9 challenge categories |
| `scenarios/common.py` | Shared utilities (colors, PID management, teardown helpers) |
| `scenarios/lab_linux.py` | Linux & Systems scenarios (L-01 to L-10) |
| `scenarios/lab_networking.py` | Networking scenarios (N-01 to N-05) |
| `scenarios/lab_fix.py` | FIX Protocol scenarios (FX-01 to FX-06) |
| `scenarios/lab_kafka.py` | Kafka scenarios (K-01 to K-06) |
| `scenarios/lab_k8s.py` | Kubernetes & ArgoCD scenarios (K8-01 to K8-06) |
| `scenarios/lab_sql.py` | SQL & Databases scenarios (S-01 to S-06) |
| `scenarios/lab_git.py` | Git scenarios (G-01 to G-05) |
| `scenarios/lab_airflow.py` | Airflow scenarios (AF-01 to AF-05) |
| `scenarios/lab_python.py` | Python & Bash scripting scenarios (P-01 to P-06) |

---

## Prerequisites

- Linux (tested on Ubuntu 20.04+) — run inside a VM or native
- Python 3.7+
- A modern browser (for the HTML lab)
- Standard Unix utilities: `ps`, `pgrep`, `kill`, `top`, `lsof`, `du`, `df`, `ss`
- Optional: `htop`, `setproctitle` (improves process naming in `ps` output)

```bash
pip install setproctitle   # optional — better process names in ps/top
```

No other third-party Python packages required for the lab scripts.

---

## Installation

```bash
git clone https://github.com/acantu101/trading-support.git
cd trading-support
```

---

## Quick Start

```bash
cd scenarios

# Launch the unified menu — choose a category then a scenario
python3 lab.py

# Jump straight to a category
python3 lab.py --category linux
python3 lab.py --category kafka
python3 lab.py --category sql

# Check status of all running lab processes
python3 lab.py --status

# Tear down everything at once
python3 lab.py --teardown
```

Each category script can also be run directly:

```bash
python3 lab_linux.py              # interactive menu
python3 lab_linux.py --scenario 1 # launch specific scenario
python3 lab_linux.py --status
python3 lab_linux.py --teardown
```

---

## The Interactive Lab (HTML)

Open `challenge-lab.html` in your browser — no server required.

```bash
# Linux
xdg-open challenge-lab.html

# Or drag the file into your browser
```

The lab has **12 categories** with **60+ challenges**, each with a realistic scenario, task checklist, optional hints, and a full solution.

**Features:**
- Click-to-check task progress per challenge
- Hint system — reveals progressively without spoiling the solution
- Collapsible solutions with syntax-highlighted commands
- Per-category progress bars

---

## Lab Scripts

### Unified Entry: `lab.py`

```
python3 lab.py
```

```
  KEY          CATEGORY

    linux        L  Linux & Systems
    networking   N  Networking
    fix          F  FIX Protocol
    kafka        K  Kafka
    k8s          K8 Kubernetes & ArgoCD
    sql          S  SQL & Databases
    git          G  Git
    airflow      A  Airflow
    python       P  Python & Bash

    teardown     Tear down all labs
    status       Show all lab process status
```

### Per-Category Usage

Every lab script accepts the same flags:

```bash
python3 lab_<name>.py                  # interactive scenario menu
python3 lab_<name>.py --scenario N     # launch scenario N directly
python3 lab_<name>.py --status         # show running processes
python3 lab_<name>.py --teardown       # kill processes + remove lab files
```

---

## Challenge Categories

### Linux & Systems (`lab_linux.py`)

Spawns real broken processes on your VM to practice with actual Linux tools.

| # | Scenario | What it creates |
|---|----------|----------------|
| L-01 | Hung `oms_client` — CPU spike | 2 processes burning ~50% CPU each |
| L-02 | Memory leak in `mdf_feed_handler` | Process allocating RAM until capped at 256 MB |
| L-03 | Log file with errors | Pre-seeded trading log with ERROR/WARN/INFO entries |
| L-04 | Port 8080 already in use | Process holding the port so deployment fails |
| L-05 | Broken file permissions | config.yml (777) and start.sh (644, not executable) |
| L-06 | Large files eating disk space | Rotated log files totalling ~1.5 GB |
| L-07 | Failed systemd service | Unit file + simulated crash journal |
| L-08 | Full one-box performance triage | CPU + memory + log spam simultaneously |
| 9 | Zombie processes | `risk_engine` parent with 5 zombie children |
| 10 | Runaway log file | `fix_engine` spamming debug lines until disk fills |
| 99 | **Full incident** | All faults at once — triage in priority order |

### Networking (`lab_networking.py`)

| # | Scenario |
|---|----------|
| N-01 | No connectivity to exchange — dead port & DNS |
| N-02 | Capture and inspect TCP traffic with tcpdump |
| N-03 | UDP multicast simulation — sender + listener |
| N-04 | Broken DNS — corrupt resolv.conf investigation |
| N-05 | Latency spike — slow TCP server + RCA notes |

### FIX Protocol (`lab_fix.py`)

| # | Scenario |
|---|----------|
| FX-01 | Decode and explain FIX message types |
| FX-02 | Sequence number gap — detect and reset |
| FX-03 | Session logon/logout flow debugging |
| FX-04 | Order routing and execution report parsing |
| FX-05 | Heartbeat timeout investigation |
| FX-06 | Fix acceptor process — connect and send messages |

### Kafka (`lab_kafka.py`)

| # | Scenario |
|---|----------|
| K-01 | Architecture concepts — config files + reference sheet |
| K-02 | Consumer group lag — snapshot + analysis script |
| K-03 | Topic operations — CLI command reference |
| K-04 | Broker down incident — crash log + response guide |
| K-05 | Python producer + consumer scripts |
| K-06 | At-least-once vs exactly-once delivery semantics |

### Kubernetes & ArgoCD (`lab_k8s.py`)

| # | Scenario |
|---|----------|
| K8-01 | CrashLoopBackOff — read logs and fix |
| K8-02 | Pod stuck in Pending — resource/node investigation |
| K8-03 | Failed rolling deployment — rollback procedure |
| K8-04 | ConfigMap and Secret misconfiguration |
| K8-05 | Service not routing traffic — selector mismatch |
| K8-06 | ArgoCD sync failure — drift detection |

### SQL & Databases (`lab_sql.py`)

Creates a SQLite trading database (`/tmp/lab_sql/db/trading.db`) with traders, trades, positions, and orders_audit tables.

| # | Scenario |
|---|----------|
| S-01 | Find all fills for a trader — basic SELECT + JOIN |
| S-02 | Rejected orders report — JOIN + audit log |
| S-03 | Net position calculation + discrepancy check — CTE |
| S-04 | Trader leaderboard — window functions (RANK, PARTITION BY) |
| S-05 | Slow query investigation — EXPLAIN + index creation |
| S-06 | Concurrent writes and locking — transactions + deadlock notes |

### Git (`lab_git.py`)

| # | Scenario |
|---|----------|
| G-01 | Bisect a broken notional calculation |
| G-02 | Amend and rebase a messy commit history |
| G-03 | Recover a deleted branch |
| G-04 | Cherry-pick a hotfix across branches |
| G-05 | Blame and annotate a regression |

### Airflow (`lab_airflow.py`)

| # | Scenario |
|---|----------|
| AF-01 | Debug a failed DAG — task logs + retry logic |
| AF-02 | SLA miss investigation |
| AF-03 | Sensor stuck blocking downstream tasks |
| AF-04 | Backfill a missed execution window |
| AF-05 | DAG dependency and trigger rule analysis |

### Python & Bash (`lab_python.py`)

| # | Scenario |
|---|----------|
| P-01 | Write a Bash log monitor — alert on CRITICAL events |
| P-02 | Parse structured log with `awk` — fill counts, volume, notional |
| P-03 | Python process watchdog — auto-restart a crashing process |
| P-04 | REST API client — query a live mock trading API |
| P-05 | FIX message parser — decode raw tag=value messages |
| P-06 | Kafka consumer lag monitor — read JSON snapshot, alert on lag |

---

## Directory Structure

Each lab creates an isolated directory under `/tmp/`:

```
/tmp/
├── lab/               ← Linux lab (lab_linux.py)
├── lab_networking/    ← Networking lab
├── lab_fix/           ← FIX Protocol lab
├── lab_kafka/         ← Kafka lab
├── lab_k8s/           ← Kubernetes lab
├── lab_sql/           ← SQL lab (includes trading.db)
├── lab_git/           ← Git lab (bare repo + working clone)
├── lab_airflow/       ← Airflow lab
└── lab_python/        ← Python & Bash lab
```

Each directory contains:
```
<lab_root>/
├── logs/        process and app logs
├── scripts/     solution scripts to study and run
├── data/        snapshots, configs, sample files
├── config/      app and service config files
└── run/         *.pid files for process tracking
```

---

## Command Reference

### Process Triage

| Task | Command |
|------|---------|
| Find process by name | `pgrep -la <name>` |
| Snapshot with stats | `ps aux \| grep <name>` |
| Detailed PID stats | `ps -p <PID> -o pid,ppid,%cpu,%mem,stat,cmd` |
| Watch PID live | `top -p <PID>` |
| Memory from /proc | `cat /proc/<PID>/status \| grep -i vm` |
| Find zombies | `ps aux \| awk '$8=="Z"'` |
| Process tree | `ps auxf` |
| Graceful kill | `kill -15 <PID>` |
| Force kill | `kill -9 <PID>` |

### Disk & Files

| Task | Command |
|------|---------|
| Who has file open | `lsof <file>` |
| All files a PID has | `lsof -p <PID>` |
| Largest files | `find /tmp/lab -type f -printf '%s %p\n' \| sort -rn \| head -10` |
| Disk usage by dir | `du -sh /tmp/lab/*` |
| Free space | `df -h /tmp` |
| Truncate log | `truncate -s 0 <logfile>` |

### Networking

| Task | Command |
|------|---------|
| Check open ports | `ss -tlnp` |
| Who owns a port | `ss -tlnp \| grep :<port>` |
| Capture traffic | `sudo tcpdump -i lo port <port> -n` |
| Test port reachable | `nc -zv 127.0.0.1 <port>` |
| DNS lookup | `dig <hostname>` / `nslookup <hostname>` |
| Multicast groups | `ip maddr` |

---

## Interview Tips

**Structure your answers around this flow:**

1. **Identify** — find the process or resource causing the issue
2. **Inspect** — check CPU, memory, open files, logs, relationships
3. **Intervene** — graceful signal first (`SIGTERM`), force only if needed
4. **Verify** — confirm the problem is resolved, check for side effects
5. **Explain** — articulate *why* the issue happened, not just how you fixed it

**Things interviewers listen for:**

- You try `SIGTERM` before `SIGKILL` — shows you understand graceful shutdown
- You know the difference between RSS and VSZ for memory analysis
- You can explain why zombies exist (parent hasn't called `wait()`) not just how to remove them
- You think about business impact when prioritising multiple simultaneous issues
- You verify your fix worked rather than assuming
- For SQL: you know when to use `EXPLAIN` and why index column order matters
- For Kafka: you understand the difference between at-least-once and exactly-once delivery
- For FIX: you can describe the logon/logout flow and sequence number gaps

**Pro tip:** Run the full incident scenarios (scenario 99 in Linux, or `python3 lab.py --category linux` then pick 99) and practice triaging multiple faults in priority order. That structured thinking under pressure is exactly what production on-call looks like.

---

## Teardown

Each lab script cleans up after itself:

```bash
# Tear down one lab
python3 scenarios/lab_linux.py --teardown

# Tear down all labs at once
python3 scenarios/lab.py --teardown
```

This sends `SIGTERM` then `SIGKILL` to all tracked processes, sweeps for any strays by name, and removes the entire lab directory tree under `/tmp/`.

---

## License

MIT — use freely for interview prep, learning, or teaching.
