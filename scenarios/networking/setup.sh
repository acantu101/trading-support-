#!/bin/bash
# Scenario: 12% packet loss on loopback/network link via tc netem
source "$(dirname "$0")/../_lib/common.sh"

LAB_DIR=~/trading-support/networking

echo "=== Networking Scenario: Packet Loss ==="
echo ""

# Step 1: Create directory structure
mkdir -p "$LAB_DIR"/{logs,bin}

# Step 2: Try to apply real tc netem packet loss
TC_APPLIED=false
if sudo tc qdisc add dev lo root netem loss 12% 2>/dev/null; then
    TC_APPLIED=true
    echo "[OK] tc netem applied: 12% packet loss on loopback (lo)"
else
    echo "[INFO] tc netem unavailable (no sudo or tc not present) — entering simulation mode"
fi

# Step 3: If tc failed, create fake ping wrapper
if [ "$TC_APPLIED" = "false" ]; then
    cat > "$LAB_DIR/bin/ping-exchange" << 'PINGSCRIPT'
#!/bin/bash
# Simulated ping to 127.0.0.2 showing ~12% packet loss
TARGET="127.0.0.2"
COUNT=100
INTERVAL=0.02
LOSS_PERCENT=12

echo "PING $TARGET ($TARGET) 56(84) bytes of data."

received=0
transmitted=0
total_time=0

for i in $(seq 1 $COUNT); do
    transmitted=$((transmitted + 1))
    rtt=$(awk "BEGIN { printf \"%.3f\", 0.1 + ($i % 7) * 0.05 }")
    # Simulate ~12% loss: drop every ~8th packet
    if [ $((i % 8)) -eq 0 ] && [ $i -le 96 ]; then
        : # dropped
    else
        received=$((received + 1))
        echo "64 bytes from $TARGET: icmp_seq=$i ttl=64 time=${rtt} ms"
    fi
    sleep "$INTERVAL" 2>/dev/null || true
done

lost=$((transmitted - received))
loss_pct=$(awk "BEGIN { printf \"%.0f\", ($lost / $transmitted) * 100 }")
echo ""
echo "--- $TARGET ping statistics ---"
echo "$transmitted packets transmitted, $received received, ${loss_pct}% packet loss, time $((COUNT * 20))ms"
echo "rtt min/avg/max/mdev = 0.100/0.275/0.450/0.082 ms"
PINGSCRIPT
    chmod +x "$LAB_DIR/bin/ping-exchange"
    echo "[SIM] Created ping-exchange wrapper at $LAB_DIR/bin/ping-exchange"
fi

# Step 4: Write network-monitor.log
cat > "$LAB_DIR/logs/network-monitor.log" << 'LOGEOF'
2026-05-04 09:42:01.003 [NET-MON] Interface eth0 up, speed=1000Mb/s, duplex=full
2026-05-04 09:42:15.114 [NET-MON] eth0 RX bytes=1482938201 TX bytes=987234110
2026-05-04 09:43:01.227 [NET-MON] WARNING: eth0 CRC errors detected: 14 new errors (total: 247)
2026-05-04 09:43:01.228 [NET-MON] WARNING: eth0 frame errors: 3 new (total: 58)
2026-05-04 09:43:15.301 [FIX-GW ] FIX session PROD-OMS->EXCHANGE latency: 45µs (normal)
2026-05-04 09:43:45.388 [FIX-GW ] FIX session PROD-OMS->EXCHANGE latency: 52µs (normal)
2026-05-04 09:44:01.442 [NET-MON] WARNING: eth0 CRC errors detected: 31 new errors (total: 278)
2026-05-04 09:44:01.443 [NET-MON] WARNING: eth0 dropped RX packets: 12 new (total: 892)
2026-05-04 09:44:15.501 [FIX-GW ] FIX session PROD-OMS->EXCHANGE latency: 210µs (elevated)
2026-05-04 09:44:30.612 [FIX-GW ] FIX session PROD-OMS->EXCHANGE latency: 490µs (WARN: >200µs threshold)
2026-05-04 09:44:45.703 [FIX-GW ] FIX order 7842001 retransmit requested (seq gap detected)
2026-05-04 09:44:45.704 [FIX-GW ] FIX order 7842001 retransmit requested (seq gap detected)
2026-05-04 09:45:00.801 [NET-MON] ERROR: eth0 overrun counter: 0 (ok), dropped: 892 (CRITICAL)
2026-05-04 09:45:00.802 [NET-MON] ERROR: eth0 RX errors: 1247 — NIC driver reporting hardware errors
2026-05-04 09:45:01.010 [FIX-GW ] FIX session PROD-OMS->EXCHANGE latency: 800µs (CRITICAL: >500µs SLA breach)
2026-05-04 09:45:01.011 [FIX-GW ] ALERT: Order fill rate degraded — 38% of orders experiencing retransmit
2026-05-04 09:45:15.112 [NET-MON] Checking NIC firmware... eth0 driver: igb version 5.4.0-k
2026-05-04 09:45:15.113 [NET-MON] HINT: CRC errors may indicate faulty cable or SFP module on eth0
2026-05-04 09:45:30.201 [FIX-GW ] FIX session PROD-OMS->EXCHANGE latency: 820µs (CRITICAL)
2026-05-04 09:45:45.302 [NET-MON] Packet loss on lo detected: 12.0% (tc netem active or physical link degraded)
2026-05-04 09:46:00.401 [NET-MON] Recommendation: replace eth0 cable / SFP, check switch port error counters
LOGEOF

# Step 5: Create ifcheck script
cat > "$LAB_DIR/bin/ifcheck" << 'IFCHECK'
#!/bin/bash
# Shows ip -s link style output with realistic error counters
echo "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000"
echo "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00"
echo "    RX: bytes  packets  errors  dropped overrun mcast"
echo "    2847291038 9284710  0       0       0       0"
echo "    TX: bytes  packets  errors  dropped carrier collsns"
echo "    2847291038 9284710  0       0       0       0"
echo ""
echo "2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000"
echo "    link/ether 52:54:00:ab:cd:ef brd ff:ff:ff:ff:ff:ff"
echo "    RX: bytes  packets  errors  dropped overrun mcast"
echo "    1482938201 7394821  1247    892     0       142"
echo "    TX: bytes  packets  errors  dropped carrier collsns"
echo "    987234110  6102938  3       0       0       0"
echo ""
echo "  RX errors: 1247  (CRC: 989, frame: 258)"
echo "  RX dropped: 892  (ring buffer overflow)"
echo "  RX overruns: 0"
echo ""
echo "NOTE: High RX error and drop counts on eth0 — investigate physical layer (cable, SFP, switch port)"
IFCHECK
chmod +x "$LAB_DIR/bin/ifcheck"

# Step 6: Create check-loss.sh
cat > "$LAB_DIR/check-loss.sh" << CHECKLOSS
#!/bin/bash
echo "=== Packet Loss Check ==="
if [ "$TC_APPLIED" = "true" ]; then
    echo "Using real ping with tc netem active on lo..."
    RESULT=\$(ping -c 100 -i 0.02 127.0.0.1 2>&1)
    echo "\$RESULT" | tail -3
    LOSS=\$(echo "\$RESULT" | grep -oP '\d+(?=% packet loss)')
    echo ""
    echo "Measured packet loss: \${LOSS}%  (expected: ~12%)"
else
    echo "Simulation mode: running ping-exchange wrapper..."
    RESULT=\$($LAB_DIR/bin/ping-exchange 2>&1)
    echo "\$RESULT" | grep -E "packet loss|statistics"
    LOSS=\$(echo "\$RESULT" | grep -oP '\d+(?=% packet loss)')
    echo ""
    echo "Simulated packet loss: \${LOSS}%  (target: ~12%)"
fi
CHECKLOSS
chmod +x "$LAB_DIR/check-loss.sh"

# Step 7: Report mode
echo ""
if [ "$TC_APPLIED" = "true" ]; then
    echo "[STATUS] tc netem successfully applied — real 12% packet loss active on lo"
else
    echo "[STATUS] Simulation mode active — fake packet loss artifacts in place"
fi

# Step 8 & 9: Instructions
echo ""
echo "Investigate: ping the gateway, check interface errors, look at NIC driver logs"
echo "  $LAB_DIR/bin/ifcheck"
echo "  $LAB_DIR/bin/ping-exchange   (or: ping -c 50 127.0.0.1)"
echo "  cat $LAB_DIR/logs/network-monitor.log"
echo "  $LAB_DIR/check-loss.sh"
echo ""
echo "Fix (if tc): sudo tc qdisc del dev lo root"
