#!/bin/bash
# Run this from Windows Git Bash to deploy HTML lab scenarios to the VM:
#   bash trading-support/scenarios/html/deploy.sh
VM_USER="acm"
VM_HOST="127.0.0.1"
VM_PORT="2222"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Deploying Trading Support Scenario Lab to ${VM_USER}@${VM_HOST}:${VM_PORT}..."

# Copy scenario contents (trailing slash = copy contents, not the directory itself)
scp -P "$VM_PORT" -o StrictHostKeyChecking=no -r "$SCRIPT_DIR/" "${VM_USER}@${VM_HOST}:~/trading-support/scenarios/"

# Make all scripts executable
ssh -p "$VM_PORT" -o StrictHostKeyChecking=no "${VM_USER}@${VM_HOST}" '
  find ~/trading-support/scenarios -name "*.sh" -exec chmod +x {} \;
  find ~/trading-support/scenarios -name "kubectl" -exec chmod +x {} \;
  find ~/trading-support/scenarios -name "aws" -exec chmod +x {} \;
  find ~/trading-support/scenarios -name "airflow" -exec chmod +x {} \;
  find ~/trading-support/scenarios/*/bin -type f -exec chmod +x {} \; 2>/dev/null || true
  mkdir -p ~/trading-support/pids ~/trading-support/logs
  echo "Setup complete. Run a scenario:"
  echo "  bash ~/trading-support/scenarios/fix/setup.sh"
'
echo "Done."
