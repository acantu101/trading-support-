#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Unified Entry Point
=====================================================
Presents a top-level menu of all challenge categories.
Select a category, then a scenario within it.

Usage:
  python3 lab.py                    # interactive menu
  python3 lab.py --category linux   # jump straight to Linux lab
  python3 lab.py -c l               # jump straight to Linux lab using alias
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
    "linux": {
        "module": "lab_linux",
        "label": "L   Linux & Systems",
        "aliases": ["l"],
    },
    "networking": {
        "module": "lab_networking",
        "label": "N   Networking",
        "aliases": ["n"],
    },
    "fix": {
        "module": "lab_fix",
        "label": "F   FIX Protocol",
        "aliases": ["f"],
    },
    "kafka": {
        "module": "lab_kafka",
        "label": "K   Kafka",
        "aliases": ["k"],
    },
    "k8s": {
        "module": "lab_k8s",
        "label": "K8  Kubernetes & ArgoCD",
        "aliases": ["k8"],
    },
    "sql": {
        "module": "lab_sql",
        "label": "S   SQL & Databases",
        "aliases": ["s"],
    },
    "git": {
        "module": "lab_git",
        "label": "G   Git",
        "aliases": ["g"],
    },
    "airflow": {
        "module": "lab_airflow",
        "label": "AF  Airflow",
        "aliases": ["af"],
    },
    "python": {
        "module": "lab_python",
        "label": "P   Python & Bash (+ OOP)",
        "aliases": ["p"],
    },
    "aws": {
        "module": "lab_aws",
        "label": "AW  AWS & Cloud",
        "aliases": ["aw"],
    },
    "java": {
        "module": "lab_java",
        "label": "J   Java / JVM",
        "aliases": ["j"],
    },
    "marketdata": {
        "module": "lab_marketdata",
        "label": "MD  Market Data & Protocols",
        "aliases": ["md"],
    },
    "monitoring": {
        "module": "lab_monitoring",
        "label": "M   Monitoring & Observability",
        "aliases": ["m"],
    },
    "incident": {
        "module": "lab_incident",
        "label": "I   Trading Incident (DRW-style cascade)",
        "aliases": ["i"],
    },
}


ALIAS_MAP = {}

for key, data in CATEGORIES.items():
    ALIAS_MAP[key] = key

    for alias in data["aliases"]:
        ALIAS_MAP[alias.lower()] = key


CATEGORY_KEYS = list(ALIAS_MAP.keys())


def _import_lab(module_name: str):
    """Import a lab module, returning it or None on error."""
    import importlib

    try:
        return importlib.import_module(module_name)
    except ImportError as e:
        err(f"Could not import {module_name}: {e}")
        return None


def run_category(choice: str):
    """Run a category by full name or alias."""
    key = ALIAS_MAP.get(choice.lower())

    if not key:
        err(f"Unknown category: '{choice}'")
        print(f"  Valid choices: {', '.join(CATEGORY_KEYS)}")
        return

    module_name = CATEGORIES[key]["module"]

    mod = _import_lab(module_name)
    if mod is None:
        return

    saved_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]

    try:
        if hasattr(mod, "main"):
            mod.main()
        else:
            err(f"{module_name} has no main()")
    finally:
        sys.argv = saved_argv


def teardown_all():
    header("Tearing Down ALL Labs")

    for key, data in CATEGORIES.items():
        module_name = data["module"]
        label = data["label"]

        mod = _import_lab(module_name)

        if mod and hasattr(mod, "teardown"):
            print(f"\n{CYAN}  → {label}{RESET}")
            mod.teardown()


def status_all():
    header("Status — All Labs")

    for key, data in CATEGORIES.items():
        module_name = data["module"]
        label = data["label"]

        mod = _import_lab(module_name)

        if mod and hasattr(mod, "show_status"):
            print(f"\n{CYAN}  ── {label} ──{RESET}")
            mod.show_status()


def interactive_menu():
    header("Support Engineer Challenge Lab")
    print(f"  {'KEY':<12} {'ALIAS':<8} CATEGORY\n")

    for key, data in CATEGORIES.items():
        aliases = ", ".join(data["aliases"])
        print(f"    {key:<12} {aliases:<8} {data['label']}")

    print(f"\n    {'teardown':<12} {'t':<8} Tear down all labs")
    print(f"    {'status':<12} {'':<8} Show all lab process status")
    print()

    choice = input("  Select category (or q to quit): ").strip().lower()

    if choice == "q":
        return

    if choice in ("teardown", "t"):
        teardown_all()
        return

    if choice == "status":
        status_all()
        return

    run_category(choice)


def main():
    parser = argparse.ArgumentParser(
        description="Support Engineer Challenge Lab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            f"  {key:<12} {', '.join(data['aliases']):<8} {data['label']}"
            for key, data in CATEGORIES.items()
        ),
    )

    parser.add_argument(
        "--category",
        "-c",
        help="Jump directly to a lab category or alias",
    )

    parser.add_argument(
        "--teardown",
        "-t",
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