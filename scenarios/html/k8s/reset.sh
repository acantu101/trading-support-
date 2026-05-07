#!/bin/bash
# k8s/reset.sh — Remove K8s scenario state
source "$(dirname "$0")/../_lib/common.sh"

banner "K8s Scenario: Reset"

step "Removing $HOME/trading-support/k8s/ ..."
rm -rf "$HOME/trading-support/k8s"
ok "K8s scenario reset."
