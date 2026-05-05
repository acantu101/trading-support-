#!/bin/bash
# fix/reset.sh — Remove FIX scenario state
source "$(dirname "$0")/../_lib/common.sh"

banner "FIX Scenario: Reset"

step "Removing $HOME/trading-support/fix/ ..."
rm -rf "$HOME/trading-support/fix"
ok "FIX scenario reset."
