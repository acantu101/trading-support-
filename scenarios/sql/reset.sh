#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Resetting SQL scenario..."
rm -rf ~/trading-support/sql/
ok "SQL scenario reset."
