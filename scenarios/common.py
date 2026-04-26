#!/usr/bin/env python3
"""
Shared utilities for all Support Engineer Challenge Lab scenario scripts.
"""

import os
import sys
import signal
import shutil
import subprocess
import multiprocessing
from pathlib import Path

# ─────────────────────────────────────────────
#  COLOUR CONSTANTS
# ─────────────────────────────────────────────
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

SEP = "=" * 62


# ─────────────────────────────────────────────
#  PRINT HELPERS
# ─────────────────────────────────────────────
def ok(msg):    print(f"{GREEN}  ✓ {msg}{RESET}")
def warn(msg):  print(f"{YELLOW}  ⚠ {msg}{RESET}")
def err(msg):   print(f"{RED}  ✗ {msg}{RESET}")
def info(msg):  print(f"{CYAN}  → {msg}{RESET}")

def header(msg):
    print(f"\n{BOLD}{SEP}{RESET}")
    print(f"{BOLD}  {msg}{RESET}")
    print(f"{BOLD}{SEP}{RESET}")

def lab_footer(script_name: str):
    print(f"\n{BOLD}{SEP}{RESET}")
    print(f"{GREEN}{BOLD}  Lab is live. Work through the tasks above.{RESET}")
    print(f"{CYAN}    python3 {script_name} --status")
    print(f"    python3 {script_name} --teardown{RESET}")
    print(f"{BOLD}{SEP}{RESET}\n")


# ─────────────────────────────────────────────
#  DIRECTORY HELPERS
# ─────────────────────────────────────────────
def create_dirs(dirs: dict):
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────
#  PID FILE HELPERS
# ─────────────────────────────────────────────
def save_pid(pid_dir: Path, name: str, pid: int):
    (pid_dir / f"{name}.pid").write_text(str(pid))


def load_pids(pid_dir: Path) -> dict:
    pids = {}
    for p in pid_dir.glob("*.pid"):
        try:
            pids[p.stem] = int(p.read_text().strip())
        except Exception:
            pass
    return pids


def spawn(target, args: tuple, pid_dir: Path, name: str) -> int:
    p = multiprocessing.Process(target=target, args=args, daemon=False)
    p.start()
    save_pid(pid_dir, name, p.pid)
    return p.pid


# ─────────────────────────────────────────────
#  TEARDOWN HELPERS
# ─────────────────────────────────────────────
def kill_pids(pid_dir: Path):
    """Send SIGTERM then SIGKILL to all tracked PIDs."""
    for name, pid in load_pids(pid_dir).items():
        try:
            os.kill(pid, signal.SIGTERM)
            import time; time.sleep(0.2)
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            ok(f"Killed {name} (PID {pid})")
        except ProcessLookupError:
            warn(f"{name} (PID {pid}) already gone")
        except PermissionError:
            err(f"No permission to kill {name} (PID {pid}) — try sudo")


def kill_strays(names: list):
    """Force-kill any stray processes matching the given names."""
    for name in names:
        result = subprocess.run(["pgrep", "-f", name], capture_output=True, text=True)
        for pid_str in result.stdout.strip().splitlines():
            try:
                os.kill(int(pid_str), signal.SIGKILL)
                ok(f"Force-killed stray {name} PID {pid_str}")
            except Exception:
                pass


def remove_lab_dir(lab_root: Path):
    shutil.rmtree(lab_root, ignore_errors=True)
    ok(f"Removed {lab_root}")


# ─────────────────────────────────────────────
#  STATUS HELPER
# ─────────────────────────────────────────────
def show_status(pid_dir: Path, label: str = "Lab"):
    header(f"{label} Status")
    pids = load_pids(pid_dir)
    if not pids:
        warn("No lab processes running")
        return
    print(f"  {'NAME':<35} {'PID':<10} STATUS")
    print(f"  {'-'*35} {'-'*10} {'-'*10}")
    for name, pid in pids.items():
        try:
            os.kill(pid, 0)
            status = f"{GREEN}running{RESET}"
        except ProcessLookupError:
            status = f"{RED}dead{RESET}"
        print(f"  {name:<35} {pid:<10} {status}")
    print()


# ─────────────────────────────────────────────
#  MENU / ARG-PARSE RUNNER
# ─────────────────────────────────────────────
def run_menu(scenario_map: dict, title: str, setup_fn=None,
             teardown_fn=None, status_fn=None, args=None):
    """
    Generic interactive menu runner.

    scenario_map: {num: (fn, description)}  — 99 means ALL
    setup_fn:     called once before any scenario (e.g. create_dirs)
    teardown_fn:  called when --teardown is passed
    status_fn:    called when --status is passed
    args:         parsed argparse.Namespace
    """
    import argparse

    if args is None:
        parser = argparse.ArgumentParser(
            description=title,
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="\n".join(f"  {k:<4} {v}" for k, (_, v) in scenario_map.items()),
        )
        parser.add_argument("--scenario", "-s", type=int,
                            choices=list(scenario_map.keys()))
        parser.add_argument("--teardown", "-t", action="store_true")
        parser.add_argument("--status",         action="store_true")
        args = parser.parse_args()

    if args.teardown:
        if teardown_fn:
            teardown_fn()
        return

    if args.status:
        if status_fn:
            status_fn()
        return

    if setup_fn:
        setup_fn()

    if args.scenario:
        _run_scenario(scenario_map, args.scenario)
    else:
        header(title)
        print("  Select a scenario:\n")
        for num, (_, desc) in scenario_map.items():
            print(f"    {num:<4} {desc}")
        print()
        choice = input("  Enter scenario number (or q to quit): ").strip()
        if choice.lower() == "q":
            return
        try:
            _run_scenario(scenario_map, int(choice))
        except (KeyError, ValueError):
            err(f"Invalid choice: {choice}")


def _run_scenario(scenario_map: dict, num: int):
    if num == 99:
        for k, (fn, _) in scenario_map.items():
            if k != 99 and fn:
                fn()
    else:
        fn, _ = scenario_map.get(num, (None, None))
        if fn:
            fn()
        else:
            err(f"Scenario {num} not found")
