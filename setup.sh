#!/usr/bin/env bash
# setup.sh — bootstrap the trading-support lab on a Linux VM
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SCENARIOS_DIR="$REPO_DIR/scenarios/cli"

# ── Python version check ─────────────────────────────────────────────────────
python_bin=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(sys.version_info[:2])")
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3,7) else 1)" 2>/dev/null; then
            python_bin="$cmd"
            break
        fi
    fi
done

if [[ -z "$python_bin" ]]; then
    echo "ERROR: Python 3.7+ is required but not found." >&2
    exit 1
fi
echo "✓  Python: $($python_bin --version)"

# ── Optional dependencies ────────────────────────────────────────────────────
echo ""
echo "Installing optional Python packages (setproctitle, h5py, kafka-python)..."
"$python_bin" -m pip install --quiet -r "$REPO_DIR/requirements.txt" || {
    echo "  ⚠  pip install failed — optional packages skipped (labs still work)"
}

# ── Verify common.py is importable from the scenarios directory ──────────────
cd "$SCENARIOS_DIR"
if "$python_bin" -c "import common" 2>/dev/null; then
    echo "✓  common.py importable"
else
    echo "ERROR: cannot import common.py from $SCENARIOS_DIR" >&2
    exit 1
fi

# ── Verify all lab modules import cleanly ────────────────────────────────────
echo ""
echo "Checking lab modules..."
failed=0
for lab in lab_linux lab_networking lab_fix lab_kafka lab_k8s \
           lab_sql lab_git lab_airflow lab_python lab_aws \
           lab_java lab_marketdata lab_monitoring; do
    if "$python_bin" -c "import $lab" 2>/dev/null; then
        echo "  ✓  $lab"
    else
        echo "  ✗  $lab  (import failed)"
        failed=1
    fi
done

if [[ $failed -eq 1 ]]; then
    echo ""
    echo "WARNING: some lab modules failed to import — check for syntax errors." >&2
fi

# ── Required system tools ────────────────────────────────────────────────────
echo ""
echo "Checking required system tools..."
missing_tools=()
for tool in ps top pgrep lsof ss du df find grep awk sort uniq git sqlite3; do
    if command -v "$tool" &>/dev/null; then
        echo "  ✓  $tool"
    else
        echo "  ✗  $tool  (not found)"
        missing_tools+=("$tool")
    fi
done

if [[ ${#missing_tools[@]} -gt 0 ]]; then
    echo ""
    echo "Install missing tools with: sudo apt-get install -y ${missing_tools[*]}"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "Setup complete. Run the lab:"
echo "  cd $SCENARIOS_DIR"
echo "  python3 lab.py                    # interactive top-level menu"
echo "  python3 lab.py --category linux   # jump to Linux scenarios"
echo "  python3 lab.py --teardown         # clean up all lab environments"
