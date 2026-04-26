#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Networking Setup
==================================================
Replicates every scenario in the HTML challenge lab Networking section (N1-N5).

Run with: sudo python3 lab_networking.py [--scenario N] [--teardown]

NETWORKING SCENARIOS:
  1   N-01  No connectivity to exchange — dead port & simulated packet drop
  2   N-02  Capture and inspect traffic — real TCP server to sniff
  3   N-03  UDP multicast simulation — multicast sender + listener
  4   N-04  Broken DNS resolution — corrupt /etc/resolv.conf + hosts file
  5   N-05  Latency spike investigation — iptables delay rule + netem
  99        ALL — set up every networking fault simultaneously
"""

import os
import sys
import time
import signal
import shutil
import socket
import argparse
import threading
import subprocess
import multiprocessing
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────
#  LAB STRUCTURE
# ─────────────────────────────────────────────
LAB_ROOT   = Path("/tmp/lab_networking")
DIRS = {
    "pcaps":   LAB_ROOT / "captures",
    "logs":    LAB_ROOT / "logs",
    "configs": LAB_ROOT / "configs",
    "pids":    LAB_ROOT / "run",
}

from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    create_dirs as _create_dirs,
    save_pid as _save_pid, load_pids as _load_pids,
    spawn as _spawn, kill_pids, kill_strays, remove_lab_dir,
    show_status as _show_status,
)

# ══════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════

def create_dirs():  _create_dirs(DIRS)
def save_pid(n, p): _save_pid(DIRS["pids"], n, p)
def load_pids():    return _load_pids(DIRS["pids"])
def spawn(t, a, n): return _spawn(t, a, DIRS["pids"], n)

def run(cmd, check=False, capture=False):
    return subprocess.run(cmd, shell=True, check=check,
                          capture_output=capture, text=True)


# ══════════════════════════════════════════════
#  BACKGROUND WORKERS
# ══════════════════════════════════════════════

def _tcp_server(host: str, port: int, name: str):
    """Holds a TCP server on the given port — used as the 'exchange' endpoint."""
    try:
        import setproctitle; setproctitle.setproctitle(name)
    except ImportError:
        pass
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((host, port))
        srv.listen(10)
        srv.settimeout(1)
        while True:
            try:
                conn, addr = srv.accept()
                # Echo a fake FIX heartbeat then close
                conn.sendall(b"8=FIX.4.4\x019=50\x0135=0\x0149=EXCHANGE\x0156=FIRM\x0110=090\x01")
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break
    except Exception as e:
        print(f"[tcp_server] Error: {e}", flush=True)
    finally:
        srv.close()


def _udp_multicast_sender(group: str, port: int, interval: float = 0.5):
    """Sends fake market-data UDP multicast packets."""
    try:
        import setproctitle; setproctitle.setproctitle("mcast_sender")
    except ImportError:
        pass
    import struct
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    counter = 0
    while True:
        msg = f"TICK|AAPL|{185.50 + (counter % 10) * 0.01:.2f}|{counter}".encode()
        try:
            sock.sendto(msg, (group, port))
        except Exception:
            pass
        counter += 1
        time.sleep(interval)


def _slow_tcp_server(port: int, delay_ms: int = 200):
    """
    Accepts TCP connections but intentionally delays responses —
    simulates latency spike on exchange port.
    """
    try:
        import setproctitle; setproctitle.setproctitle("slow_exchange")
    except ImportError:
        pass
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
        srv.listen(10)
        srv.settimeout(1)
        while True:
            try:
                conn, _ = srv.accept()
                time.sleep(delay_ms / 1000.0)  # artificial delay
                conn.sendall(b"8=FIX.4.4\x019=50\x0135=0\x0110=090\x01")
                conn.close()
            except socket.timeout:
                continue
            except OSError:
                break
    finally:
        srv.close()


# ══════════════════════════════════════════════
#  SCENARIO LAUNCHERS
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario N-01 — No Connectivity to Exchange")
    print("  A trading application can't reach the exchange at")
    print("  localhost port 4001 (we'll simulate it here).\n")

    # Spin up a TCP server on 4001 so students CAN connect (and see it working),
    # then also set up a dead port 4002 (nothing listening) to practice failure.
    pid1 = spawn(_tcp_server, ("0.0.0.0", 4001, "exchange_sim"), "exchange_4001")
    ok(f"exchange_sim listening on port 4001  PID={pid1}")

    # Write a fake /etc/hosts override for the lab domain
    hosts_entry = "127.0.0.1  exchange-a.trading.internal\n"
    hosts_path  = DIRS["configs"] / "hosts.snippet"
    hosts_path.write_text(hosts_entry)
    ok(f"Written hosts snippet: {hosts_path}")

    # Write a broken resolv.conf for study
    resolv = DIRS["configs"] / "resolv.conf.broken"
    resolv.write_text("# broken — wrong DNS server\nnameserver 192.168.99.99\n")
    ok(f"Written broken resolv.conf: {resolv}")

    print(f"""
{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Ping the 'exchange' (localhost is fine in this lab)
{CYAN}       ping -c 4 127.0.0.1{RESET}

  2. Trace route (loopback will resolve immediately — concept drill)
{CYAN}       traceroute -n 127.0.0.1{RESET}

  3. Verify port 4001 is open (exchange is up)
{CYAN}       nc -zv 127.0.0.1 4001{RESET}

  4. Verify port 4002 is CLOSED (exchange port missing — like production fault)
{CYAN}       nc -zv 127.0.0.1 4002
       ss -tlnp | grep 4002{RESET}

  5. Test DNS for the fake internal hostname
{CYAN}       # Without the hosts entry:
       dig exchange-a.trading.internal
       # With the snippet applied:
       cat {hosts_path}    # shows what you'd add to /etc/hosts
       grep exchange-a /etc/hosts || echo "Not in hosts yet"{RESET}

  6. Check the local routing table
{CYAN}       ip route{RESET}

{BOLD}── Key concepts ────────────────────────────────────────{RESET}
  • port 4001 = OPEN  (exchange up) → nc exits 0
  • port 4002 = CLOSED (nothing listening) → nc exits 1
  • Use OSI bottom-up: L3 ping → L3 trace → L4 port → L7 DNS
""")


def launch_scenario_2():
    header("Scenario N-02 — Capture and Inspect Network Traffic")
    print("  Orders are being sent but the exchange isn't ACKing them.")
    print("  Verify packets are actually leaving the host.\n")

    # Spin up a real TCP server so students can generate traffic to capture
    pid = spawn(_tcp_server, ("0.0.0.0", 4001, "exchange_sim"), "exchange_4001_cap")
    ok(f"exchange_sim listening on port 4001  PID={pid}")

    cap_file = DIRS["pcaps"] / "capture.pcap"
    cap_file.touch()
    ok(f"Capture output target: {cap_file}")

    print(f"""
{BOLD}── Generate test traffic (in a second terminal) ────────{RESET}
{CYAN}       # Connect to the fake exchange — this creates real TCP traffic
       nc 127.0.0.1 4001
       # Then type anything and hit Enter{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Capture traffic on the loopback interface to port 4001
{CYAN}       sudo tcpdump -i lo port 4001 -n{RESET}

  2. Capture only TCP SYN packets (connection attempts)
{CYAN}       sudo tcpdump -i lo 'tcp[tcpflags] & tcp-syn != 0' -n{RESET}

  3. Save a capture to file for analysis
{CYAN}       sudo tcpdump -i lo port 4001 -w {cap_file} &
       # generate some traffic with: nc 127.0.0.1 4001
       # stop capture: kill %1
       # read it back:
       sudo tcpdump -r {cap_file} -n{RESET}

  4. Show current connection states for port 4001
{CYAN}       ss -tn dst 127.0.0.1
       ss -tn state established{RESET}

{BOLD}── Expected output when working correctly ──────────────{RESET}
  tcpdump should show: SYN, SYN-ACK, ACK, data, FIN
  If you only see SYN and no SYN-ACK → server not listening (wrong host/port)
  ss established → count should increase with each nc connection
""")


def launch_scenario_3():
    header("Scenario N-03 — UDP Multicast Simulation")
    print("  Market data feed uses UDP multicast. A trader stopped")
    print("  receiving prices. Investigate the multicast subscription.\n")

    MCAST_GROUP = "224.1.1.1"
    MCAST_PORT  = 5007

    pid = spawn(_udp_multicast_sender, (MCAST_GROUP, MCAST_PORT, 0.3), "mcast_sender")
    ok(f"Multicast sender spawned  PID={pid}  group={MCAST_GROUP}:{MCAST_PORT}")

    # Write a listener script for students to run
    listener_script = DIRS["configs"] / "mcast_listener.py"
    listener_script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"Lab multicast listener — run this to receive market-data ticks.\"\"\"
import socket, struct

GROUP = '{MCAST_GROUP}'
PORT  = {MCAST_PORT}

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('', PORT))

mreq = struct.pack('4sL', socket.inet_aton(GROUP), socket.INADDR_ANY)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

print(f"Joined multicast group {{GROUP}}:{{PORT}} — listening for ticks...")
while True:
    data, addr = sock.recvfrom(1024)
    print(f"TICK from {{addr[0]}}: {{data.decode()}}")
""")
    ok(f"Listener script: {listener_script}")

    print(f"""
{BOLD}── Multicast group: {MCAST_GROUP}:{MCAST_PORT} ─────────────────────{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Check multicast group memberships on this host
{CYAN}       ip maddr
       netstat -g{RESET}

  2. Capture multicast traffic to verify data is arriving
{CYAN}       sudo tcpdump -i lo multicast -n
       sudo tcpdump -i any 'dst host {MCAST_GROUP}' -n{RESET}

  3. Run the Python listener to receive ticks
{CYAN}       python3 {listener_script}{RESET}

  4. Check for dropped packets on the interface
{CYAN}       ip -s link show lo
       # Look for: RX dropped counter > 0{RESET}

{BOLD}── Why UDP Multicast in trading ─────────────────────────{RESET}
  UDP = no handshake, no retransmit. A 10ms TCP retransmit
  is WORSE than a missed tick. One sender → many receivers.
  TCP would require a separate connection per subscriber.
  UDP multicast scales to thousands of subscribers for free.
""")


def launch_scenario_4():
    header("Scenario N-04 — Broken DNS Resolution")
    print("  After a network change, apps can't resolve")
    print("  internal hostnames like db-primary.trading.internal.\n")

    # Write broken and fixed resolv.conf files for inspection
    broken_resolv = DIRS["configs"] / "resolv.conf.broken"
    broken_resolv.write_text("""\
# BROKEN — DNS server unreachable after network change
nameserver 192.168.99.99
# Missing: search domain for .trading.internal
""")
    ok(f"Broken resolv.conf written: {broken_resolv}")

    fixed_resolv = DIRS["configs"] / "resolv.conf.fixed"
    fixed_resolv.write_text("""\
# FIXED — internal DNS server
nameserver 10.0.0.53
nameserver 8.8.8.8
search trading.internal
""")
    ok(f"Fixed resolv.conf written:  {fixed_resolv}")

    hosts_snippet = DIRS["configs"] / "hosts.lab"
    hosts_snippet.write_text("""\
# Lab override entries (would live in /etc/hosts)
127.0.0.1  db-primary.trading.internal
127.0.0.1  kafka-broker-1.trading.internal
127.0.0.1  exchange-a.trading.internal
127.0.0.1  exchange-b.trading.internal
""")
    ok(f"Hosts snippet written:      {hosts_snippet}")

    nsswitch = DIRS["configs"] / "nsswitch.conf.example"
    nsswitch.write_text("""\
# /etc/nsswitch.conf — resolution order
# files  = /etc/hosts  (checked FIRST if listed before dns)
# dns    = DNS servers in /etc/resolv.conf
hosts: files dns
""")
    ok(f"nsswitch example written:   {nsswitch}")

    print(f"""
{BOLD}── Config files for inspection ─────────────────────────{RESET}
{CYAN}       cat {broken_resolv}
       cat {fixed_resolv}
       cat {hosts_snippet}
       cat {nsswitch}{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Test DNS resolution (will fail if nameserver is unreachable)
{CYAN}       nslookup db-primary.trading.internal
       dig db-primary.trading.internal{RESET}

  2. Find which DNS servers this host is using
{CYAN}       cat /etc/resolv.conf{RESET}

  3. Compare with the broken config above
{CYAN}       diff /etc/resolv.conf {broken_resolv}{RESET}

  4. Query a specific DNS server directly
{CYAN}       dig @8.8.8.8 google.com          # works (public)
       dig @192.168.99.99 google.com     # times out (dead server){RESET}

  5. Check /etc/hosts for manual overrides
{CYAN}       cat /etc/hosts
       grep "trading.internal" /etc/hosts || echo "Not overridden"{RESET}

  6. Check resolution order
{CYAN}       cat /etc/nsswitch.conf | grep hosts{RESET}

{BOLD}── Root cause ───────────────────────────────────────────{RESET}
  The broken resolv.conf points to 192.168.99.99 which is unreachable.
  Fix: update nameserver to 10.0.0.53 (internal DNS).
  Short-term workaround: add entries to /etc/hosts (see snippet).
""")


def launch_scenario_5():
    header("Scenario N-05 — Latency Spike Investigation")
    print("  Trader reports latency spikes every morning at market open.")
    print("  Normal RTT: ~200µs. Spike RTT: ~5ms.\n")

    # Spin up a deliberately slow TCP server on port 9100
    SLOW_PORT = 9100
    pid = spawn(_slow_tcp_server, (SLOW_PORT, 150), "slow_exchange")
    ok(f"slow_exchange listening on port {SLOW_PORT}  PID={pid}  (150ms artificial delay)")

    # Write a Python latency measurement script
    lat_script = DIRS["configs"] / "measure_latency.py"
    lat_script.write_text(f"""\
#!/usr/bin/env python3
\"\"\"
Measures TCP connection latency to the lab exchange simulator.
Run: python3 {lat_script}
\"\"\"
import socket, time, statistics

HOST = "127.0.0.1"
PORT = {SLOW_PORT}
SAMPLES = 20

latencies_ms = []
print(f"Measuring TCP connect latency to {{HOST}}:{{PORT}} ({{SAMPLES}} samples)...")

for i in range(SAMPLES):
    t0 = time.perf_counter()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect((HOST, PORT))
        s.recv(256)
        s.close()
    except Exception as e:
        print(f"  Sample {{i+1}}: ERROR {{e}}")
        continue
    elapsed_ms = (time.perf_counter() - t0) * 1000
    latencies_ms.append(elapsed_ms)
    print(f"  Sample {{i+1:2d}}: {{elapsed_ms:.2f}} ms")
    time.sleep(0.1)

if latencies_ms:
    print(f"\\nResults over {{len(latencies_ms)}} successful samples:")
    print(f"  Min  : {{min(latencies_ms):.2f}} ms")
    print(f"  Max  : {{max(latencies_ms):.2f}} ms")
    print(f"  Mean : {{statistics.mean(latencies_ms):.2f}} ms")
    print(f"  P99  : {{sorted(latencies_ms)[int(len(latencies_ms)*0.99)]:.2f}} ms")
    if max(latencies_ms) > 10:
        print("\\n  ⚠  SPIKE DETECTED — max latency >10ms!")
        print("     Investigate: CPU contention, GC pauses, NIC IRQ, switch queues.")
""")
    ok(f"Latency measurement script: {lat_script}")

    # Write a root-cause analysis guide
    rca_guide = DIRS["logs"] / "latency_rca_notes.txt"
    rca_guide.write_text("""\
LATENCY SPIKE ROOT CAUSE ANALYSIS NOTES
========================================
Observed: 200µs normal → 5ms spike at market open (09:30)

HYPOTHESIS 1 — CPU CONTENTION AT MARKET OPEN
  Evidence for: CPU load spikes when order burst hits at 09:30
  Check: sar -u 1 10 (between 09:28-09:32)
         top -b -n 1 -H | head -20
  Fix:   isolate trading threads to dedicated cores (taskset/cgroups)

HYPOTHESIS 2 — JVM GC PAUSE (if Java app)
  Evidence for: 5ms matches a minor GC pause duration
  Check: grep "GC" /var/log/oms/gc.log | grep "09:30"
         jstat -gcutil <PID> 1000 10
  Fix:   tune heap size, use G1GC, add -XX:MaxGCPauseMillis=1

HYPOTHESIS 3 — NIC INTERRUPT COALESCING
  Evidence for: NIC batches interrupts every 5ms by default
  Check: ethtool -c eth0     (shows coalescing settings)
         ethtool -S eth0 | grep -i "miss\|drop"
  Fix:   ethtool -C eth0 rx-usecs 0   (disable coalescing)
         Set IRQ affinity: echo 2 > /proc/irq/<N>/smp_affinity

HYPOTHESIS 4 — NETWORK SWITCH MICROBURST
  Evidence for: market open causes burst → switch port congestion
  Check: work with network team to pull switch port counters
         look for: ingress drops, egress queue depth
  Fix:   increase switch buffer, QoS queue priority for trading traffic

HYPOTHESIS 5 — OS SCHEDULER LATENCY
  Evidence for: Linux is not real-time; scheduler may delay wakeup
  Check: cyclictest -t1 -p80 -n -i200 -l100000
  Fix:   PREEMPT_RT kernel patch, tuned profile 'latency-performance'
         isolcpus=2,3 on kernel cmdline
""")
    ok(f"RCA notes written: {rca_guide}")

    print(f"""
{BOLD}── Lab server: slow_exchange on port {SLOW_PORT} (~150ms delay) ────{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Run the latency measurement script
{CYAN}       python3 {lat_script}{RESET}

  2. Measure RTT using ping (ICMP — baseline)
{CYAN}       ping -c 100 -i 0.1 127.0.0.1{RESET}

  3. Check NIC/interface error counters
{CYAN}       ip -s link show lo
       # look for: RX errors, TX errors, drops{RESET}

  4. Check CPU interrupts distribution
{CYAN}       cat /proc/interrupts | head -30{RESET}

  5. Read the RCA analysis notes
{CYAN}       cat {rca_guide}{RESET}

  6. Summarise as you would to a manager
{CYAN}       "RTT 200µs → 5ms spike at 09:30.
        Top suspects: CPU contention (burst orders),
        JVM GC pause, NIC interrupt coalescing.
        Next: pull sar CPU data and GC logs from 09:29-09:31."{RESET}
""")


def launch_scenario_99():
    header("Scenario 99 — ALL Networking Faults Simultaneously")
    launch_scenario_1()
    time.sleep(0.3)
    launch_scenario_2()
    time.sleep(0.3)
    launch_scenario_3()
    time.sleep(0.3)
    launch_scenario_4()
    time.sleep(0.3)
    launch_scenario_5()


# ══════════════════════════════════════════════
#  TEARDOWN
# ══════════════════════════════════════════════

def teardown():
    header("Tearing Down Networking Lab")
    kill_pids(DIRS["pids"])
    kill_strays(["exchange_sim", "slow_exchange", "mcast_sender"])
    remove_lab_dir(LAB_ROOT)


def show_status():
    _show_status(DIRS["pids"], "Networking Lab")


# ══════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════

SCENARIO_MAP = {
    1:  (launch_scenario_1, "N-01  No connectivity to exchange"),
    2:  (launch_scenario_2, "N-02  Capture and inspect network traffic"),
    3:  (launch_scenario_3, "N-03  UDP multicast simulation"),
    4:  (launch_scenario_4, "N-04  Broken DNS resolution"),
    5:  (launch_scenario_5, "N-05  Latency spike investigation"),
    99: (launch_scenario_99, "     ALL — every networking fault"),
}

def main():
    parser = argparse.ArgumentParser(
        description="Networking Challenge Lab Setup",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:<4} {v}" for k, (_, v) in SCENARIO_MAP.items())
    )
    parser.add_argument("--scenario", "-s", type=int, choices=list(SCENARIO_MAP.keys()))
    parser.add_argument("--teardown", "-t", action="store_true")
    parser.add_argument("--status",         action="store_true")
    args = parser.parse_args()

    if args.teardown: teardown(); return
    if args.status:   show_status(); return

    create_dirs()

    if args.scenario:
        fn, _ = SCENARIO_MAP[args.scenario]
        fn()
    else:
        header("Networking Challenge Lab")
        print("  Available scenarios:\n")
        for num, (_, desc) in SCENARIO_MAP.items():
            print(f"    {num:<4} {desc}")
        print()
        choice = input("  Enter scenario number (or q to quit): ").strip()
        if choice.lower() == "q": return
        try:
            fn, _ = SCENARIO_MAP[int(choice)]
            fn()
        except (KeyError, ValueError):
            err(f"Invalid choice: {choice}"); return

    lab_footer("lab_networking.py")

if __name__ == "__main__":
    main()
