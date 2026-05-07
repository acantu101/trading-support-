#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Resetting Airflow scenario..."

step "Killing any running airflow or dag processes..."
pkill -f "settlement_pipeline" 2>/dev/null || true
pkill -f "run_dag.py"          2>/dev/null || true
ok "Processes killed (or none were running)"

step "Removing ~/trading-support/airflow/..."
rm -rf ~/trading-support/airflow/
ok "Airflow scenario reset."
