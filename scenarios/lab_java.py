#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Java / JVM
============================================
No Java installation needed. All scenarios use realistic log files
you read and analyze — exactly what app support does in production.

SCENARIOS:
  1   J-01  Stack trace analysis — read a Java exception, find the root cause
  2   J-02  GC log analysis — identify GC pauses causing latency spikes
  3   J-03  Thread dump — find deadlocked and stuck threads
  4   J-04  OutOfMemoryError — heap vs metaspace, diagnose OOM
  99        ALL scenarios
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

LAB_ROOT = Path("/tmp/lab_java")
DIRS = {
    "logs":    LAB_ROOT / "logs",
    "scripts": LAB_ROOT / "scripts",
    "dumps":   LAB_ROOT / "dumps",
}

sys.path.insert(0, str(Path(__file__).parent))
from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    create_dirs as _create_dirs,
    remove_lab_dir,
    show_status as _show_status,
    run_menu,
)

def create_dirs(): _create_dirs(DIRS)
def show_status(): _show_status(DIRS["scripts"], "Java Lab")


# ══════════════════════════════════════════════
#  SCENARIO LAUNCHERS
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario J-01 — Java Stack Trace Analysis")
    print("  The order router crashed. Read the stack trace and")
    print("  identify: exception type, root cause, and which class to fix.\n")

    stack_file = DIRS["logs"] / "order_router_crash.log"
    stack_file.write_text("""\
2026-04-28 09:31:42.881 ERROR [order-router] [main-thread] Unhandled exception — service terminating

java.lang.NullPointerException: Cannot invoke "com.hft.trading.market.Quote.getBidPrice()" because "quote" is null
    at com.hft.trading.router.OrderRouter.calculateSlippage(OrderRouter.java:287)
    at com.hft.trading.router.OrderRouter.routeOrder(OrderRouter.java:142)
    at com.hft.trading.router.OrderRouter.processNewOrder(OrderRouter.java:98)
    at com.hft.trading.fix.FIXSessionHandler.onMessage(FIXSessionHandler.java:201)
    at quickfix.Session.nextDataDictionary(Session.java:1847)
    at quickfix.Session.next(Session.java:762)
    at quickfix.ThreadedSocketAcceptor$AcceptorThread.run(ThreadedSocketAcceptor.java:204)
    at java.base/java.lang.Thread.run(Thread.java:833)

Caused by: com.hft.trading.market.MarketDataUnavailableException: No quote available for symbol AAPL
    at com.hft.trading.market.MarketDataCache.getQuote(MarketDataCache.java:156)
    at com.hft.trading.router.OrderRouter.calculateSlippage(OrderRouter.java:284)
    ... 7 more

2026-04-28 09:31:42.882 INFO  [order-router] Context: order=ORD-4821 symbol=AAPL side=BUY qty=500 price=185.50
2026-04-28 09:31:42.883 INFO  [order-router] MarketDataCache last updated: 09:29:11 (151 seconds ago)
2026-04-28 09:31:42.884 WARN  [order-router] Market data feed was down from 09:28:55 to 09:31:40
""")
    ok(f"Stack trace log: {stack_file}")

    analysis = DIRS["scripts"] / "j01_analysis.txt"
    analysis.write_text("""\
J-01 Stack Trace Analysis — Answers
=====================================

EXCEPTION TYPE:
  java.lang.NullPointerException

ROOT CAUSE (read from bottom of stack, work up):
  1. MarketDataCache.getQuote() returned null (no quote for AAPL)
     → MarketDataUnavailableException was thrown at MarketDataCache.java:156
  2. OrderRouter.calculateSlippage() called getBidPrice() on the null quote
     → NullPointerException at OrderRouter.java:287

WHICH CLASS TO FIX:
  OrderRouter.java line 287 — it must null-check the quote before calling getBidPrice()
  OR MarketDataCache.java line 156 — throw a clearer exception before returning null

CONTEXT CLUES IN THE LOG:
  - Market data feed was down for ~2.5 minutes (09:28:55 to 09:31:40)
  - The cache was stale (last updated 151 seconds before the crash)
  - The order arrived during the outage window (09:31:42)

ROOT CAUSE CHAIN:
  Market data feed down → stale cache → getQuote() returns null
  → calculateSlippage() NPE → order router crashes → orders lost

FIX:
  Short term: add null check in calculateSlippage() with a clear error
  Long term:  order router should reject orders when market data is stale
              (configurable staleness threshold, e.g. > 30 seconds)

HOW TO READ A JAVA STACK TRACE:
  - First line: exception type + message
  - "at" lines: call stack, most recent call FIRST
  - Read from top = where it crashed, bottom = where the code originated
  - "Caused by:" = the underlying exception that triggered the one above
  - Always find the FIRST "Caused by:" — that is the real root cause
""")
    ok(f"Analysis guide: {analysis}")

    print(f"""
{BOLD}── Stack trace: ────────────────────────────────────────{RESET}
{CYAN}       cat {stack_file}{RESET}

{BOLD}── Questions to answer: ────────────────────────────────{RESET}
  1. What type of exception was thrown?
  2. What is the root cause? (hint: read "Caused by:")
  3. Which class and line number caused it?
  4. What was the service context? (what order was being processed?)
  5. Why was market data unavailable?

{BOLD}── Read the analysis guide: ────────────────────────────{RESET}
{CYAN}       cat {analysis}{RESET}

{BOLD}── How to read Java stack traces ───────────────────────{RESET}
  Line 1      : Exception type + message — what crashed
  "at" lines  : call stack, top = crash site, bottom = entry point
  "Caused by" : the underlying exception — THIS is the real root cause
  Line numbers: go directly to the bug in source code
  Thread name : which thread crashed ([main-thread], [fix-handler-1], etc.)
""")


def launch_scenario_2():
    header("Scenario J-02 — GC Log Analysis")
    print("  The position service has intermittent latency spikes.")
    print("  The GC logs show why. Find the pause causing the spikes.\n")

    gc_log = DIRS["logs"] / "position_service_gc.log"
    gc_log.write_text("""\
# GC Log — position-service — JVM flags: -Xmx4g -Xms2g -XX:+UseG1GC -verbose:gc
# Format: [timestamp][gc-type] pause duration, heap before -> heap after (heap max)

[2026-04-28T09:30:00.123+0000][gc] GC(0) Pause Young (Normal) 512M->498M(4096M) 12.3ms
[2026-04-28T09:30:15.445+0000][gc] GC(1) Pause Young (Normal) 768M->701M(4096M) 18.7ms
[2026-04-28T09:30:30.891+0000][gc] GC(2) Pause Young (Normal) 1024M->956M(4096M) 22.1ms
[2026-04-28T09:30:45.002+0000][gc] GC(3) Pause Young (Concurrent Start) 1280M->1201M(4096M) 25.4ms
[2026-04-28T09:30:45.003+0000][gc] GC(4) Concurrent Mark Cycle — started (not a pause)
[2026-04-28T09:31:00.114+0000][gc] GC(5) Pause Young (Normal) 1536M->1489M(4096M) 28.9ms
[2026-04-28T09:31:15.223+0000][gc] GC(6) Pause Young (Normal) 1792M->1701M(4096M) 31.2ms
[2026-04-28T09:31:30.334+0000][gc] GC(7) Pause Young (Normal) 2048M->1987M(4096M) 34.6ms
[2026-04-28T09:31:42.001+0000][gc] GC(8) Pause Young (Prepare Mixed) 2304M->2198M(4096M) 38.1ms
[2026-04-28T09:31:45.882+0000][gc] GC(9) Pause Full (System.gc()) 3891M->312M(4096M) 4821.3ms  ← STOP THE WORLD
[2026-04-28T09:31:50.704+0000][gc] GC(10) Pause Young (Normal) 512M->498M(4096M) 11.8ms
[2026-04-28T09:31:51.002+0000][gc] GC(11) Pause Young (Normal) 600M->588M(4096M) 12.1ms

# Application log excerpt (same time window)
[2026-04-28T09:31:42.000+0000] INFO  [position-service] Processing fill batch — 47 fills
[2026-04-28T09:31:45.883+0000] WARN  [position-service] Health check missed response (4821ms pause)
[2026-04-28T09:31:45.884+0000] ERROR [order-router] Position service timeout after 5000ms
[2026-04-28T09:31:45.885+0000] WARN  [risk-engine] Stale position data — using cached values
""")
    ok(f"GC log: {gc_log}")

    analysis = DIRS["scripts"] / "j02_gc_analysis.py"
    analysis.write_text(f"""\
#!/usr/bin/env python3
\"\"\"J-02: Parse GC log and find stop-the-world pauses.\"\"\"

GC_LOG = "{gc_log}"

pauses = []
with open(GC_LOG) as f:
    for line in f:
        if "Pause" in line and "ms" in line and not line.startswith("#"):
            parts  = line.strip().split()
            ts     = parts[0].strip("[]")
            # Extract pause duration (last token before newline ending in ms)
            for token in reversed(parts):
                if token.endswith("ms"):
                    try:
                        ms = float(token.replace("ms",""))
                        gc_type = " ".join(parts[2:5])
                        pauses.append((ts, gc_type, ms))
                    except ValueError:
                        pass
                    break

print("=== All GC Pauses ===")
print(f"  {{' TIMESTAMP':<35}} {{' TYPE':<35}} {{' PAUSE_MS':>10}}")
print(f"  {{'-'*35}} {{'-'*35}} {{'-'*10}}")
for ts, gc_type, ms in pauses:
    flag = "  ← STOP THE WORLD" if ms > 1000 else ("  ← WARN" if ms > 100 else "")
    print(f"  {{ts:<35}} {{gc_type:<35}} {{ms:>10.1f}}{{flag}}")

stw = [p for p in pauses if p[2] > 1000]
print(f"\\n=== Stop-The-World Events (>1000ms) ===")
if stw:
    for ts, gc_type, ms in stw:
        print(f"  ✗ {{ts}}: {{ms:.0f}}ms pause — {{gc_type}}")
    print(f"\\n  Root cause: 'Pause Full (System.gc())' — a Full GC was triggered")
    print(f"  This happens when:")
    print(f"    1. Heap was nearly full (3891M / 4096M = 95%% before GC)")
    print(f"    2. G1GC could not keep up with allocation rate")
    print(f"    3. Something called System.gc() explicitly (check the code)")
    print(f"\\n  Impact: 4.8 second pause — all application threads frozen")
    print(f"  Fix options:")
    print(f"    - Increase heap: -Xmx8g (more headroom before Full GC)")
    print(f"    - Find memory leak (heap growing 512M→3891M in 90 seconds)")
    print(f"    - Remove explicit System.gc() calls")
    print(f"    - Switch to ZGC (-XX:+UseZGC) — sub-millisecond pauses even on large heaps")
else:
    print("  No stop-the-world events found.")
""")
    ok(f"GC analysis script: {analysis}")

    print(f"""
{BOLD}── GC log: ─────────────────────────────────────────────{RESET}
{CYAN}       cat {gc_log}{RESET}

{BOLD}── Questions to answer: ────────────────────────────────{RESET}
  1. Which GC event caused the 4.8 second pause?
  2. What is "Pause Full (System.gc())" and why is it bad?
  3. What was happening to heap size before the Full GC?
  4. What was the business impact (check the app log section)?
  5. How would you fix it?

{BOLD}── Run the analysis script: ─────────────────────────────{RESET}
{CYAN}       python3 {analysis}{RESET}

{BOLD}── GC concepts ─────────────────────────────────────────{RESET}
  Young GC    : fast (10-40ms), clears short-lived objects — normal
  Mixed GC    : clears young + some old generation — still fast
  Full GC     : clears everything — STOP THE WORLD, can take seconds
  G1GC        : default in Java 9+, targets predictable pause times
  ZGC         : Java 15+, concurrent GC, pauses < 1ms even at 100GB heap
  -Xmx        : max heap size (e.g. -Xmx4g = 4 GB max)
  -Xms        : initial heap size (set equal to -Xmx to avoid resizing)

{BOLD}── Why GC matters for trading ───────────────────────────{RESET}
  A 4.8s STW pause during market hours means:
  - All orders frozen for 4.8 seconds
  - Health checks miss → upstream services time out
  - Risk engine falls back to stale positions
  - Orders may be rejected or routed incorrectly
""")


def launch_scenario_3():
    header("Scenario J-03 — Thread Dump Analysis")
    print("  The risk engine is hanging — not processing messages.")
    print("  A thread dump was captured. Find the deadlock.\n")

    thread_dump = DIRS["dumps"] / "risk_engine_threaddump.txt"
    thread_dump.write_text("""\
# Thread dump — risk-engine — captured: 2026-04-28T09:31:55Z
# Generated with: kill -3 <pid>  OR  jstack <pid>
# Total threads: 47  |  Deadlocked threads: 2  |  Waiting: 18

=== DEADLOCK DETECTED ===
Java-level deadlock:
  "position-update-thread" is waiting to lock <0x00000007a1234abc> (PositionCache)
    which is held by "risk-calc-thread"
  "risk-calc-thread" is waiting to lock <0x00000007b5678def> (OrderBook)
    which is held by "position-update-thread"

=== Thread: position-update-thread (BLOCKED) ===
java.lang.Thread.State: BLOCKED (on object monitor)
    at com.hft.trading.risk.RiskCalculator.updatePosition(RiskCalculator.java:312)
    - waiting to lock <0x00000007a1234abc> (com.hft.trading.position.PositionCache)
    - locked <0x00000007b5678def> (com.hft.trading.market.OrderBook)
    at com.hft.trading.position.PositionUpdater.applyFill(PositionUpdater.java:89)
    at com.hft.trading.position.PositionUpdater.run(PositionUpdater.java:45)

=== Thread: risk-calc-thread (BLOCKED) ===
java.lang.Thread.State: BLOCKED (on object monitor)
    at com.hft.trading.risk.RiskEngine.calculateExposure(RiskEngine.java:198)
    - waiting to lock <0x00000007b5678def> (com.hft.trading.market.OrderBook)
    - locked <0x00000007a1234abc> (com.hft.trading.position.PositionCache)
    at com.hft.trading.risk.RiskEngine.run(RiskEngine.java:87)

=== Thread: kafka-consumer-0 (WAITING) ===
java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(Native Method)
    - waiting on <0x00000007c9012ghi> (com.hft.trading.queue.FillQueue)
    at com.hft.trading.queue.FillQueue.take(FillQueue.java:67)
    at com.hft.trading.kafka.FillConsumer.run(FillConsumer.java:112)
    # This thread is fine — it's waiting for the queue which is blocked by the deadlock

=== Thread: http-health-1 (RUNNABLE) ===
java.lang.Thread.State: RUNNABLE
    at sun.nio.ch.Net.poll(Native Method)
    at com.hft.trading.health.HealthServer.serve(HealthServer.java:43)
    # Health endpoint still responding — misleading, service IS deadlocked

=== Thread: ForkJoinPool-1-worker-3 (WAITING) ===
java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(Native Method)
    at java.util.concurrent.locks.LockSupport.park(LockSupport.java:341)
    # Normal worker thread waiting for work
""")
    ok(f"Thread dump: {thread_dump}")

    analysis = DIRS["scripts"] / "j03_threaddump_guide.txt"
    analysis.write_text("""\
J-03 Thread Dump Analysis — Answers
=====================================

DEADLOCK IDENTIFICATION:
  Two threads are stuck waiting on each other:

  position-update-thread:
    HOLDS:   OrderBook  (0x00000007b5678def)
    WAITING: PositionCache (0x00000007a1234abc)

  risk-calc-thread:
    HOLDS:   PositionCache (0x00000007a1234abc)
    WAITING: OrderBook     (0x00000007b5678def)

  Neither can proceed — classic deadlock.

ROOT CAUSE:
  Inconsistent lock ordering. Both classes need both locks but acquire them
  in different order:
    position-update-thread: acquires OrderBook first, then PositionCache
    risk-calc-thread:       acquires PositionCache first, then OrderBook

FIX:
  Enforce consistent lock ordering — always acquire PositionCache BEFORE OrderBook
  in BOTH threads. See S-06 SQL lab for the same concept applied to databases.

BUSINESS IMPACT:
  - kafka-consumer-0 is blocked waiting for the FillQueue
  - No fills are being processed
  - Risk calculations have stopped
  - Health endpoint still returns 200 (MISLEADING — service is functionally dead)

HOW TO READ A THREAD DUMP:
  Thread name    : meaningful if developers named threads ([position-update-thread])
  Thread state   : RUNNABLE (running), BLOCKED (waiting for a lock),
                   WAITING (waiting indefinitely), TIMED_WAITING (sleep/timeout)
  "locked"       : this thread HOLDS this monitor
  "waiting to lock": this thread is BLOCKED waiting for this monitor
  Object address : hex address (0x00000007...) identifies the specific lock object
  "DEADLOCK DETECTED" : JVM prints this at the top if it finds a cycle

IMMEDIATE REMEDIATION:
  kill -9 <pid>   (force kill — JVM will restart via watchdog/K8s)
  This loses in-flight fills — they will be reprocessed from Kafka (at-least-once)
  Root cause fix must go in the next release.
""")
    ok(f"Analysis guide: {analysis}")

    print(f"""
{BOLD}── Thread dump: ────────────────────────────────────────{RESET}
{CYAN}       cat {thread_dump}{RESET}

{BOLD}── Questions to answer: ────────────────────────────────{RESET}
  1. How many threads are deadlocked?
  2. Which two threads are involved?
  3. What lock does each thread hold? What is each waiting for?
  4. Why does the health endpoint still respond even though the service is stuck?
  5. How do you fix the deadlock in code?

{BOLD}── Read the analysis guide: ────────────────────────────{RESET}
{CYAN}       cat {analysis}{RESET}

{BOLD}── Thread states quick reference ───────────────────────{RESET}
  RUNNABLE      : thread is executing (or ready to execute)
  BLOCKED       : waiting for a synchronized lock held by another thread
  WAITING       : waiting indefinitely (Object.wait(), LockSupport.park())
  TIMED_WAITING : waiting with a timeout (Thread.sleep(), wait(timeout))

{BOLD}── How to capture a thread dump in production ───────────{RESET}
{CYAN}       kill -3 <pid>           # sends SIGQUIT — JVM prints dump to stdout/log
       jstack <pid>             # Java tool — formatted thread dump
       jstack <pid> > dump.txt  # save to file for analysis{RESET}
""")


def launch_scenario_4():
    header("Scenario J-04 — OutOfMemoryError Diagnosis")
    print("  The market data handler crashed with OutOfMemoryError.")
    print("  Understand what ran out, why, and how to fix it.\n")

    oom_log = DIRS["logs"] / "market_data_oom.log"
    oom_log.write_text("""\
2026-04-28 09:45:00.001 INFO  [market-data-handler] Starting tick processing — symbols: 450
2026-04-28 09:45:00.102 INFO  [market-data-handler] Cache initialized: 0 entries
2026-04-28 09:47:15.331 INFO  [market-data-handler] Cache size: 1,200,000 entries
2026-04-28 09:49:30.882 WARN  [market-data-handler] Cache size: 3,800,000 entries — approaching limit
2026-04-28 09:50:12.001 WARN  [market-data-handler] GC overhead limit exceeded — CPU spending >98% in GC
2026-04-28 09:50:13.441 ERROR [market-data-handler] FATAL ERROR — JVM terminating

java.lang.OutOfMemoryError: Java heap space
    at java.util.Arrays.copyOf(Arrays.java:3512)
    at java.util.ArrayList.grow(ArrayList.java:265)
    at java.util.ArrayList.add(ArrayList.java:456)
    at com.hft.trading.market.TickCache.store(TickCache.java:89)
    at com.hft.trading.market.TickProcessor.process(TickProcessor.java:134)
    at com.hft.trading.market.TickProcessor.run(TickProcessor.java:67)

# JVM flags at startup:
# -Xmx2g -Xms512m -XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError
# Heap dump written to: /tmp/market-data-handler-pid12847-20260428-094513.hprof (1.9GB)

# ----- Additional OOM types for reference -----

# Type 2: Metaspace OOM (class loading)
# java.lang.OutOfMemoryError: Metaspace
#   Cause: too many classes loaded (dynamic proxies, reflection, hot reload)
#   Fix:   -XX:MaxMetaspaceSize=512m  or find the class leak

# Type 3: GC Overhead Limit Exceeded
# java.lang.OutOfMemoryError: GC overhead limit exceeded
#   Cause: JVM spending >98% time in GC and recovering <2% heap
#   Fix:   same as heap space — more memory or fix the memory leak

# Type 4: Direct Buffer Memory (off-heap)
# java.lang.OutOfMemoryError: Direct buffer memory
#   Cause: NIO ByteBuffers (common in Kafka, Netty, FIX engines)
#   Fix:   -XX:MaxDirectMemorySize=1g  or fix buffer pooling
""")
    ok(f"OOM log: {oom_log}")

    analysis = DIRS["scripts"] / "j04_oom_guide.txt"
    analysis.write_text("""\
J-04 OutOfMemoryError Analysis — Answers
=========================================

OOM TYPE: Java heap space
  The JVM heap ran out of memory. All objects live here.

ROOT CAUSE (from log):
  TickCache was storing ALL tick data since startup — no eviction policy.
  Cache grew from 0 → 3,800,000 entries in under 5 minutes.
  At startup: 0 entries
  At 9:47:   1,200,000 entries (2 minutes in)
  At 9:49:   3,800,000 entries (4 minutes in) — growing 1M+ entries/minute
  At 9:50:   heap full → OOM

  450 symbols × ticks every ~100ms = ~4,500 ticks/second
  With no TTL/eviction the cache is an unbounded memory leak.

WHAT THE HEAP DUMP TELLS YOU:
  The .hprof file (1.9GB) can be opened with Eclipse MAT or JProfiler.
  It shows every object in heap — TickCache ArrayList would show millions of entries.
  In production: developers analyse this to confirm the root cause.

IMMEDIATE FIX:
  Restart the pod (watchdog/K8s will do this automatically)
  Increase heap temporarily: -Xmx4g to buy time

PERMANENT FIX:
  Add eviction to TickCache:
    - TTL: expire ticks older than 60 seconds
    - Max size: cap at 500,000 entries, evict oldest
  Use a bounded cache library (Caffeine, Guava Cache)

JVM FLAGS FOR PRODUCTION:
  -XX:+HeapDumpOnOutOfMemoryError    : write heap dump on OOM (already set)
  -XX:HeapDumpPath=/var/log/dumps/   : where to write it
  -XX:+ExitOnOutOfMemoryError        : crash fast instead of thrashing in GC
  -Xmx and -Xms equal                : avoid heap resizing pauses

OOM ERROR TYPES SUMMARY:
  Java heap space          : objects in heap — most common
  Metaspace                : class metadata — too many classes loaded
  GC overhead limit        : spending too much time in GC
  Direct buffer memory     : off-heap NIO buffers (Kafka, Netty)
  Unable to create thread  : OS ran out of threads (too many Thread objects)
""")
    ok(f"Analysis guide: {analysis}")

    print(f"""
{BOLD}── OOM log: ────────────────────────────────────────────{RESET}
{CYAN}       cat {oom_log}{RESET}

{BOLD}── Questions to answer: ────────────────────────────────{RESET}
  1. What type of OOM occurred?
  2. Which class caused the memory leak?
  3. What was growing in memory?
  4. How fast was memory growing? (calculate from the log timestamps)
  5. What JVM flag ensures a heap dump is written on OOM?

{BOLD}── Read the analysis guide: ────────────────────────────{RESET}
{CYAN}       cat {analysis}{RESET}

{BOLD}── OOM types at a glance ───────────────────────────────{RESET}
  Java heap space       : most common — objects not being garbage collected
  Metaspace             : class loading issue — dynamic proxies, frameworks
  GC overhead limit     : heap almost full — JVM can't keep up
  Direct buffer memory  : off-heap — Kafka consumers, Netty (FIX engines)

{BOLD}── JVM memory regions ──────────────────────────────────{RESET}
  Heap     : all Java objects live here (-Xmx controls max size)
  Metaspace: class definitions, method bytecode (outside heap in Java 8+)
  Stack    : each thread has its own stack (method calls, local vars)
  Direct   : off-heap NIO buffers (-XX:MaxDirectMemorySize controls max)
""")


def launch_scenario_99():
    header("Scenario 99 — ALL Java/JVM Scenarios")
    for fn in [launch_scenario_1, launch_scenario_2,
               launch_scenario_3, launch_scenario_4]:
        fn()
        time.sleep(0.2)


def teardown():
    header("Tearing Down Java Lab")
    remove_lab_dir(LAB_ROOT)


SCENARIO_MAP = {
    1:  (launch_scenario_1, "J-01  Stack trace analysis"),
    2:  (launch_scenario_2, "J-02  GC log analysis"),
    3:  (launch_scenario_3, "J-03  Thread dump — deadlock"),
    4:  (launch_scenario_4, "J-04  OutOfMemoryError"),
    99: (launch_scenario_99, "     ALL scenarios"),
}


def main():
    run_menu(SCENARIO_MAP, "Java / JVM Challenge Lab",
             setup_fn=create_dirs, teardown_fn=teardown, status_fn=show_status,
             script_name="lab_java.py")


if __name__ == "__main__":
    main()
