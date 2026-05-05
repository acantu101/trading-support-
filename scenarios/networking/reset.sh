#!/bin/bash
# Reset: Networking packet loss scenario
source "$(dirname "$0")/../_lib/common.sh"

sudo tc qdisc del dev lo root 2>/dev/null || true
rm -rf ~/trading-support/networking/
echo "Networking scenario reset."
