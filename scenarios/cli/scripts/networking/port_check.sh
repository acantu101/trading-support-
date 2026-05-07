#!/bin/bash
# Trading Infrastructure Port Checker
# =====================================
# Checks connectivity to all critical trading endpoints.
# Run this first during any connectivity incident.
#
# Usage:
#   bash port_check.sh
#   bash port_check.sh exchange-a.trading.internal 4001

PASS=0
FAIL=0

check_port() {
    local host="$1"
    local port="$2"
    local label="$3"
    local timeout=3

    if nc -zw "$timeout" "$host" "$port" 2>/dev/null; then
        echo "  [OK]   $label ($host:$port)"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $label ($host:$port) — connection refused or timeout"
        FAIL=$((FAIL + 1))
    fi
}

check_dns() {
    local host="$1"
    if getent hosts "$host" &>/dev/null; then
        local ip
        ip=$(getent hosts "$host" | awk '{print $1}')
        echo "  [OK]   DNS $host → $ip"
    else
        echo "  [FAIL] DNS $host — cannot resolve"
        FAIL=$((FAIL + 1))
    fi
}

# ── If specific host/port passed as args ─────────────────────
if [ -n "$1" ] && [ -n "$2" ]; then
    check_port "$1" "$2" "custom"
    exit 0
fi

# ── Standard trading infrastructure checks ───────────────────
echo "Trading Infrastructure Connectivity Check"
echo "$(date '+%Y-%m-%d %H:%M:%S')"
echo ""

echo "── DNS Resolution ───────────────────────────────────────"
check_dns "exchange-a.trading.internal"
check_dns "exchange-b.trading.internal"
check_dns "kafka-broker-1.trading.internal"
check_dns "db-primary.trading.internal"

echo ""
echo "── Exchange Connectivity ────────────────────────────────"
check_port "127.0.0.1" "4001" "Exchange-A FIX (primary)"
check_port "127.0.0.1" "4002" "Exchange-B FIX (backup)"
check_port "127.0.0.1" "9878" "FIX Acceptor (lab)"

echo ""
echo "── Infrastructure Ports ─────────────────────────────────"
check_port "127.0.0.1" "9092" "Kafka broker"
check_port "127.0.0.1" "5432" "PostgreSQL"
check_port "127.0.0.1" "6379" "Redis"

echo ""
echo "── REST APIs ────────────────────────────────────────────"
check_port "127.0.0.1" "8765" "OMS REST API (lab)"
check_port "127.0.0.1" "8080" "Risk Engine API"

echo ""
echo "── Summary ──────────────────────────────────────────────"
echo "  PASS: $PASS   FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "  Next steps for failed ports:"
    echo "    1. ping <host>            — is the host reachable at L3?"
    echo "    2. traceroute <host>      — where does the path break?"
    echo "    3. ss -tlnp | grep <port> — is the service listening?"
    echo "    4. cat /etc/resolv.conf   — is DNS configured correctly?"
fi
