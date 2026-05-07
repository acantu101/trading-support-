#!/bin/bash
# airflow/verify.sh — Verify fix for settlement pipeline DAG failure
source "$(dirname "$0")/../_lib/common.sh"

banner "Airflow Scenario: Verify Fix"

DAG_FILE="$HOME/trading-support/airflow/dags/settlement_pipeline.py"
RUN_DAG="$HOME/trading-support/airflow/run_dag.py"
AIRFLOW_OUTPUT_DIR="$HOME/trading-support/airflow/output"
OPT_OUTPUT_DIR="/opt/settlement/output"

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [ ! -f "$DAG_FILE" ]; then
  err "DAG file not found: $DAG_FILE"
  err "Did you run setup.sh first?"
  exit 1
fi

# ── Detect fix: path changed OR /opt dir now exists ──────────────────────────
CURRENT_OUTPUT_DIR=$(python3 -c "
import ast, sys

with open('$DAG_FILE') as f:
    src = f.read()

# Walk the AST to find OUTPUT_DIR assignment
try:
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == 'OUTPUT_DIR':
                    if isinstance(node.value, ast.Constant):
                        print(node.value.value)
                    elif isinstance(node.value, ast.Call):
                        # e.g. os.path.expanduser(...)
                        print('EXPANDUSER_CALL')
                    sys.exit(0)
except Exception:
    pass
" 2>/dev/null)

# Expand ~ if present in path
CURRENT_OUTPUT_DIR=$(python3 -c "
import os
p = '''$CURRENT_OUTPUT_DIR'''
print(os.path.expanduser(p))
" 2>/dev/null)

PATH_FIXED=false
OPT_DIR_EXISTS=false

# Check if path was changed away from the broken /opt/settlement/output
if [ "$CURRENT_OUTPUT_DIR" != "$OPT_OUTPUT_DIR" ] && [ -n "$CURRENT_OUTPUT_DIR" ]; then
  PATH_FIXED=true
fi

# Check if the directory actually exists (either changed path or /opt created)
if [ -d "$CURRENT_OUTPUT_DIR" ] 2>/dev/null; then
  PATH_FIXED=true
fi

if [ -d "$OPT_OUTPUT_DIR" ] 2>/dev/null; then
  OPT_DIR_EXISTS=true
  PATH_FIXED=true
fi

# ── Not fixed branch ──────────────────────────────────────────────────────────
if [ "$PATH_FIXED" = "false" ]; then
  echo ""
  err "The task will still fail — the output directory doesn't exist."
  echo ""
  info "Current OUTPUT_DIR in settlement_pipeline.py:"
  grep "OUTPUT_DIR" "$DAG_FILE" | grep -v "^#" | sed 's/^/    /'
  echo ""
  info "That directory exists:"
  if [ -d "$CURRENT_OUTPUT_DIR" ]; then
    echo "    YES — but permissions may block writes"
  else
    echo "    NO"
  fi
  echo ""
  step "Nudge: you have two valid fixes:"
  step ""
  step "  Option A — change the path in settlement_pipeline.py:"
  step "             OUTPUT_DIR = os.path.expanduser('~/trading-support/airflow/output')"
  step "             (that directory already exists from setup)"
  step ""
  step "  Option B — create the directory the DAG expects:"
  step "             sudo mkdir -p /opt/settlement/output"
  step "             sudo chown \$USER /opt/settlement/output"
  echo ""
  exit 1
fi

# ── Fixed branch — run the actual DAG ────────────────────────────────────────
ok "Output directory is reachable: ${CURRENT_OUTPUT_DIR}"
echo ""
step "Running the settlement pipeline DAG end-to-end..."
echo ""
sleep 0.3

# Run the DAG and capture output
DAG_OUTPUT=$(python3 "$RUN_DAG" 2>&1)
DAG_EXIT=$?

# Stream output with slight drama
while IFS= read -r line; do
  echo "$line"
  sleep 0.05
done <<< "$DAG_OUTPUT"

echo ""

if [ $DAG_EXIT -ne 0 ]; then
  err "DAG run failed. Output directory issue may still be present."
  err "Check the output above for details."
  exit 1
fi

# ── Find and display the output settlement file ───────────────────────────────
sleep 0.3
SETTLE_FILE=$(find "$CURRENT_OUTPUT_DIR" -name "settlement_*.csv" -newer "$DAG_FILE" 2>/dev/null | head -1)
if [ -z "$SETTLE_FILE" ]; then
  SETTLE_FILE=$(find "$CURRENT_OUTPUT_DIR" -name "settlement_*.csv" 2>/dev/null | sort | tail -1)
fi
if [ -z "$SETTLE_FILE" ] && [ -d "$OPT_OUTPUT_DIR" ]; then
  SETTLE_FILE=$(find "$OPT_OUTPUT_DIR" -name "settlement_*.csv" 2>/dev/null | sort | tail -1)
fi

if [ -n "$SETTLE_FILE" ]; then
  ok "Settlement file written: $SETTLE_FILE"
  echo ""
  echo -e "${BOLD}${CYAN}>>> head -5 $SETTLE_FILE${NC}"
  echo ""
  head -5 "$SETTLE_FILE" | sed 's/^/    /'
  echo "    ..."
  ROW_COUNT=$(( $(wc -l < "$SETTLE_FILE") - 1 ))
  echo ""
  info "${ROW_COUNT} settlement records written. Ready for DTCC submission."
fi

echo ""

# ── SCENARIO COMPLETE summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║      SCENARIO COMPLETE — Airflow Settlement Pipeline Fail   ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}1. What you diagnosed${NC}"
echo "   The settlement_pipeline DAG was failing at task generate_settlement_files"
echo "   every night at 02:00 UTC. The error: FileNotFoundError on the output"
echo "   path /opt/settlement/output/settlement_YYYYMMDD.csv."
echo "   Tasks extract_trades and validate_trades succeeded; notify_dtcc was"
echo "   skipped (upstream failure). The root cause was a hardcoded output path"
echo "   that does not exist in the current environment."
echo ""

echo -e "${BOLD}${CYAN}2. What you fixed${NC}"
if [ "$OPT_DIR_EXISTS" = "true" ]; then
  echo "   Created the expected directory: $OPT_OUTPUT_DIR"
  echo "   The DAG's hardcoded path now resolves to a writable location."
else
  echo "   Changed OUTPUT_DIR in settlement_pipeline.py from:"
  echo "     /opt/settlement/output  (does not exist)"
  echo "   to:"
  echo "     $CURRENT_OUTPUT_DIR  (writable, created by setup)"
  echo "   All 4 DAG tasks completed successfully. Settlement file written."
fi
echo ""

echo -e "${BOLD}${CYAN}3. Real-world context${NC}"
echo "   Hardcoded paths are a major reliability antipattern in Airflow DAGs."
echo "   /opt/settlement/output worked on the developer's machine but was never"
echo "   created in QA or production. The DAG succeeded in testing (wrong path"
echo "   existed there) and silently failed in production at the T+1 window."
echo ""
echo "   T+1 settlement implications:"
echo "   - Equity trades settle T+2 in the US (T+1 starting 2024)"
echo "   - The DTCC batch deadline is typically 02:30 ET"
echo "   - A silent DAG failure at 02:00 means trades aren't submitted"
echo "   - Result: settlement fails, potential fines, failed client deliveries"
echo ""
echo "   Idempotent tasks: each task should be safe to retry without side effects."
echo "   generate_settlement_files should overwrite the output file, not append,"
echo "   so a DAG re-run on the same date produces a clean result."
echo ""

echo -e "${BOLD}${CYAN}4. How to prevent it in production${NC}"
echo "   a) Use Airflow Variables or environment variables for all paths:"
echo "      OUTPUT_DIR = Variable.get('settlement_output_dir')"
echo "      Set per-environment in the Airflow UI — no code changes for deploys."
echo "   b) Add a task before generate_settlement_files that checks the output"
echo "      directory exists and is writable (PythonOperator with os.access check)."
echo "   c) SLA monitoring: configure dag.sla on each task so Airflow emails"
echo "      on-call when a task hasn't completed by the T+1 deadline."
echo "   d) Distinguish failure from success: notify_dtcc should only run if"
echo "      the settlement file exists and has non-zero rows — add a sensor."
echo "   e) Test DAG runs in CI using a fixture environment that mirrors"
echo "      production directory layout (Docker volume mounts work well)."
echo ""
