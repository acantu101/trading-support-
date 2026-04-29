#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Unified Entry Point
=====================================================
Presents a top-level menu of all challenge categories.
Select a category, then a scenario within it.

Usage:
  python3 lab.py                    # interactive menu
  python3 lab.py --category linux   # jump straight to Linux lab
  python3 lab.py --teardown         # tear down all labs
  python3 lab.py --status           # status of all labs
"""

import sys
import argparse
from pathlib import Path

# Ensure the scenarios directory is on the path so common.py is importable
sys.path.insert(0, str(Path(__file__).parent))

from common import GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP, ok, warn, err, header


CATEGORIES = {
    "linux":      ("lab_linux",       "L   Linux & Systems"),
    "networking": ("lab_networking",  "N   Networking"),
    "fix":        ("lab_fix",         "F   FIX Protocol"),
    "kafka":      ("lab_kafka",       "K   Kafka"),
    "k8s":        ("lab_k8s",         "K8  Kubernetes & ArgoCD"),
    "sql":        ("lab_sql",         "S   SQL & Databases"),
    "git":        ("lab_git",         "G   Git"),
    "airflow":    ("lab_airflow",     "AF  Airflow"),
    "python":     ("lab_python",      "P   Python & Bash (+ OOP)"),
    "aws":        ("lab_aws",         "AW  AWS & Cloud"),
    "java":       ("lab_java",        "J   Java / JVM"),
    "marketdata": ("lab_marketdata",  "MD  Market Data & Protocols"),
    "monitoring": ("lab_monitoring",  "M   Monitoring & Observability"),
}

CATEGORY_KEYS = list(CATEGORIES.keys())


def _import_lab(module_name: str):
    """Import a lab module, returning it (or None on error)."""
    import importlib
    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        err(f"Could not import {module_name}: {e}")
        return None


def run_category(key: str):
    module_name, label = CATEGORIES[key]
    mod = _import_lab(module_name)
    if mod is None:
        return

    # All lab modules expose SCENARIO_MAP and main(); use run_menu if available
    if hasattr(mod, "run_menu"):
        mod.run_menu(mod.SCENARIO_MAP, label)
    elif hasattr(mod, "main"):
        mod.main()
    else:
        err(f"{module_name} has no main() or run_menu()")


def teardown_all():
    header("Tearing Down ALL Labs")
    for key, (module_name, label) in CATEGORIES.items():
        mod = _import_lab(module_name)
        if mod and hasattr(mod, "teardown"):
            print(f"\n{CYAN}  → {label}{RESET}")
            mod.teardown()


def status_all():
    header("Status — All Labs")
    for key, (module_name, label) in CATEGORIES.items():
        mod = _import_lab(module_name)
        if mod and hasattr(mod, "show_status"):
            print(f"\n{CYAN}  ── {label} ──{RESET}")
            mod.show_status()


def interactive_menu():
    header("Support Engineer Challenge Lab")
    print(f"  {'KEY':<12} CATEGORY\n")
    for key, (_, label) in CATEGORIES.items():
        print(f"    {key:<12} {label}")
    print(f"\n    {'teardown':<12} Tear down all labs")
    print(f"    {'status':<12} Show all lab process status")
    print()
    choice = input("  Select category (or q to quit): ").strip().lower()
    if choice == "q":
        return
    if choice == "teardown":
        teardown_all()
        return
    if choice == "status":
        status_all()
        return
    if choice in CATEGORIES:
        run_category(choice)
    else:
        err(f"Unknown category: '{choice}'")
        print(f"  Valid choices: {', '.join(CATEGORY_KEYS)}")


def main():
    parser = argparse.ArgumentParser(
        description="Support Engineer Challenge Lab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:<12} {v}" for k, (_, v) in CATEGORIES.items()),
    )
    parser.add_argument(
        "--category", "-c",
        choices=CATEGORY_KEYS,
        help="Jump directly to a lab category",
    )
    parser.add_argument(
        "--teardown", "-t",
        action="store_true",
        help="Tear down all running labs",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show status of all lab processes",
    )
    args = parser.parse_args()

    if args.teardown:
        teardown_all()
        return

    if args.status:
        status_all()
        return

    if args.category:
        run_category(args.category)
        return

    interactive_menu()


if __name__ == "__main__":
    main()
