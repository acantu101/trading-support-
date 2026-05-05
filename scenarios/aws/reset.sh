#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Resetting AWS scenario..."
rm -rf ~/trading-support/aws/
ok "AWS scenario reset."
