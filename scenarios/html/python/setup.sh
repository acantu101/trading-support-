#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "Python Scenario: Memory leak in quote aggregation microservice"

step "Creating working directories..."
mkdir -p ~/trading-support/python
mkdir -p ~/trading-support/pids
ok "Directories created"

step "Writing service.py (leaking microservice)..."
cat > ~/trading-support/python/service.py << 'PYEOF'
#!/usr/bin/env python3
"""
NBBO Quote Aggregator Microservice
Aggregates National Best Bid/Offer quotes across 12 equity symbols.

# TODO: add cache eviction — never got around to it
# Bug: quote_cache grows without bound. Every quote is keyed by
#      (symbol, timestamp_ms) and nothing is ever removed.
#      Under normal market load (~10k quotes/sec across 12 symbols)
#      this consumes ~1 GB of RSS in under 10 minutes.
"""

import time
import os
import sys
import threading
import resource
import datetime

SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "GS", "BAC", "SPY", "QQQ",
]

# Bug: unbounded dict — keys are (symbol, timestamp_ms), never evicted
quote_cache: dict = {}

METRICS_FILE = os.path.expanduser("~/trading-support/python/metrics.log")


def simulate_nbbo_feed():
    """
    Simulates an NBBO market-data feed arriving at ~10ms intervals.
    Each tick adds one entry per symbol to quote_cache.
    Under real load this would be ~1200 entries/second accumulating forever.
    """
    import random
    prices = {s: round(random.uniform(50, 900), 2) for s in SYMBOLS}

    while True:
        ts_ms = int(time.time() * 1000)
        for sym in SYMBOLS:
            # Simulate mid-price walk
            prices[sym] += random.uniform(-0.05, 0.05)
            bid = round(prices[sym] - random.uniform(0.01, 0.05), 4)
            ask = round(prices[sym] + random.uniform(0.01, 0.05), 4)
            # Bug: (sym, ts_ms) key is never removed from quote_cache
            quote_cache[(sym, ts_ms)] = {
                "bid": bid,
                "ask": ask,
                "bid_size": random.randint(100, 5000),
                "ask_size": random.randint(100, 5000),
                "exchange": random.choice(["NASDAQ", "NYSE", "BATS", "IEX"]),
                "sequence": ts_ms,
                # Extra payload to make the leak grow faster in the lab
                "raw_payload": b"X" * 256,
            }
        time.sleep(0.01)  # 10ms = ~100 ticks/sec * 12 symbols = 1200 entries/sec


def report_metrics():
    """Print and log memory metrics every 5 seconds."""
    while True:
        time.sleep(5)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = usage.ru_maxrss / 1024  # Linux: kB -> MB
        entries = len(quote_cache)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] RSS: {rss_mb:.1f} MB, cache entries: {entries:,}"
        print(line, flush=True)
        try:
            with open(METRICS_FILE, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass


def main():
    print("NBBO Quote Aggregator starting...", flush=True)
    print(f"Symbols: {', '.join(SYMBOLS)}", flush=True)
    print("Metrics logged to:", METRICS_FILE, flush=True)
    print("", flush=True)

    feed_thread = threading.Thread(target=simulate_nbbo_feed, daemon=True)
    metrics_thread = threading.Thread(target=report_metrics, daemon=True)

    feed_thread.start()
    metrics_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down.", flush=True)


if __name__ == "__main__":
    main()
PYEOF
ok "service.py written"

step "Writing leak_profile.py (tracemalloc diagnostic tool)..."
cat > ~/trading-support/python/leak_profile.py << 'PYEOF'
#!/usr/bin/env python3
"""
Memory Leak Profiler — demonstrates how to use tracemalloc to find the leak
in the quote aggregator service.

Run this script to see tracemalloc in action on the same leaking pattern.
It reproduces the leak locally and shows you exactly which line is responsible.

Usage:
    python3 ~/trading-support/python/leak_profile.py
"""

import tracemalloc
import time
import linecache
import os
import random

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "JPM", "GS", "BAC", "SPY", "QQQ"]

def display_top(snapshot, key_type="lineno", limit=10):
    snapshot = snapshot.filter_traces((
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
        tracemalloc.Filter(False, "<unknown>"),
    ))
    top_stats = snapshot.statistics(key_type)

    print(f"\n{'='*60}")
    print(f"Top {limit} memory consumers (tracemalloc snapshot):")
    print(f"{'='*60}")
    for i, stat in enumerate(top_stats[:limit], 1):
        frame = stat.traceback[0]
        filename = os.path.basename(frame.filename)
        line = linecache.getline(frame.filename, frame.lineno).strip()
        print(f"  #{i:2d}  {stat.size / 1024:.1f} KB  {filename}:{frame.lineno}")
        if line:
            print(f"        -> {line}")
    total = sum(s.size for s in top_stats)
    print(f"\n  Total tracked: {total / 1024 / 1024:.2f} MB")

def leaking_aggregator_demo():
    """
    Reproduces the service.py leak pattern so tracemalloc can point at it.
    The key insight: every (symbol, timestamp_ms) pair is a NEW dict entry, never freed.
    """
    quote_cache = {}
    prices = {s: round(random.uniform(50, 900), 2) for s in SYMBOLS}

    print("Simulating 3 seconds of quote feed (10ms ticks)...")
    ticks = 0
    start = time.time()
    while time.time() - start < 3.0:
        ts_ms = int(time.time() * 1000)
        for sym in SYMBOLS:
            prices[sym] += random.uniform(-0.05, 0.05)
            # This is the leaking line:
            quote_cache[(sym, ts_ms)] = {
                "bid": round(prices[sym] - 0.02, 4),
                "ask": round(prices[sym] + 0.02, 4),
                "bid_size": random.randint(100, 5000),
                "ask_size": random.randint(100, 5000),
                "raw_payload": b"X" * 256,
            }
        ticks += 1
        time.sleep(0.01)

    return quote_cache, ticks

def main():
    print("Starting tracemalloc...")
    tracemalloc.start(10)  # store 10-frame tracebacks

    snap1 = tracemalloc.take_snapshot()
    cache, ticks = leaking_aggregator_demo()
    snap2 = tracemalloc.take_snapshot()

    print(f"\nAfter {ticks} ticks: {len(cache):,} cache entries")
    display_top(snap2, limit=10)

    # Show the diff — what grew between snapshots
    top_stats = snap2.compare_to(snap1, "lineno")
    print(f"\n{'='*60}")
    print("Memory growth between snapshots (diff):")
    print(f"{'='*60}")
    for stat in top_stats[:5]:
        if stat.size_diff > 0:
            print(f"  +{stat.size_diff/1024:.1f} KB  {stat.traceback[0]}")

    print(f"""
{'='*60}
DIAGNOSIS
{'='*60}
The leak is in: quote_cache[(sym, ts_ms)] = {{ ... }}

Every tick creates a new key (symbol, timestamp_ms).
With 12 symbols and 100 ticks/sec that is 1,200 new dict
entries per second — none are ever removed.

THE FIX (see service_fixed.py):
  Replace the unbounded dict with a bounded deque per symbol:

    from collections import deque
    quote_cache = {{sym: deque(maxlen=10_000) for sym in SYMBOLS}}

  Then append instead of assign:
    quote_cache[sym].append({{ "bid": ..., "ask": ..., ... }})

  maxlen=10_000 keeps the last 10k quotes per symbol and
  automatically evicts the oldest — memory stays constant.
""")

    tracemalloc.stop()

if __name__ == "__main__":
    main()
PYEOF
ok "leak_profile.py written"

step "Writing service_fixed.py (bounded deque solution)..."
cat > ~/trading-support/python/service_fixed.py << 'PYEOF'
#!/usr/bin/env python3
"""
NBBO Quote Aggregator Microservice — FIXED VERSION
Uses collections.deque(maxlen=10_000) to bound memory per symbol.

Diff from service.py:
  - quote_cache changed from dict to {symbol: deque(maxlen=10_000)}
  - Cache append uses deque.append() — oldest entry auto-evicted at maxlen
  - Memory stays ~constant regardless of runtime
"""

import time
import os
import threading
import resource
import datetime
import random
from collections import deque

SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "GS", "BAC", "SPY", "QQQ",
]

# Fix: bounded deque per symbol — maxlen caps memory usage
MAX_QUOTES_PER_SYMBOL = 10_000
quote_cache: dict[str, deque] = {sym: deque(maxlen=MAX_QUOTES_PER_SYMBOL) for sym in SYMBOLS}

METRICS_FILE = os.path.expanduser("~/trading-support/python/metrics_fixed.log")


def simulate_nbbo_feed():
    prices = {s: round(random.uniform(50, 900), 2) for s in SYMBOLS}
    while True:
        ts_ms = int(time.time() * 1000)
        for sym in SYMBOLS:
            prices[sym] += random.uniform(-0.05, 0.05)
            bid = round(prices[sym] - random.uniform(0.01, 0.05), 4)
            ask = round(prices[sym] + random.uniform(0.01, 0.05), 4)
            # Fix: append to bounded deque — oldest entry is auto-evicted
            quote_cache[sym].append({
                "ts_ms": ts_ms,
                "bid": bid,
                "ask": ask,
                "bid_size": random.randint(100, 5000),
                "ask_size": random.randint(100, 5000),
                "exchange": random.choice(["NASDAQ", "NYSE", "BATS", "IEX"]),
                "sequence": ts_ms,
                "raw_payload": b"X" * 256,
            })
        time.sleep(0.01)


def report_metrics():
    while True:
        time.sleep(5)
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss_mb = usage.ru_maxrss / 1024
        total_entries = sum(len(q) for q in quote_cache.values())
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] RSS: {rss_mb:.1f} MB, cache entries: {total_entries:,} (bounded, max {MAX_QUOTES_PER_SYMBOL * len(SYMBOLS):,})"
        print(line, flush=True)
        try:
            with open(METRICS_FILE, "a") as f:
                f.write(line + "\n")
        except Exception:
            pass


def main():
    print("NBBO Quote Aggregator (FIXED) starting...", flush=True)
    print(f"Symbols: {', '.join(SYMBOLS)}", flush=True)
    print(f"Max quotes per symbol: {MAX_QUOTES_PER_SYMBOL:,} (total cap: {MAX_QUOTES_PER_SYMBOL * len(SYMBOLS):,})", flush=True)
    print("Metrics logged to:", METRICS_FILE, flush=True)
    print("", flush=True)

    feed_thread = threading.Thread(target=simulate_nbbo_feed, daemon=True)
    metrics_thread = threading.Thread(target=report_metrics, daemon=True)
    feed_thread.start()
    metrics_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down.", flush=True)


if __name__ == "__main__":
    main()
PYEOF
ok "service_fixed.py written"

step "Starting service.py in background..."
python3 ~/trading-support/python/service.py > ~/trading-support/python/metrics.log 2>&1 &
SVC_PID=$!
echo "$SVC_PID" > ~/trading-support/pids/python-svc.pid
ok "service.py started with PID $SVC_PID"

info "Microservice is running. Watch memory grow: watch -n5 'tail -5 ~/trading-support/python/metrics.log'"
info "Diagnose with: python3 ~/trading-support/python/leak_profile.py"
info "Fix: compare service.py vs service_fixed.py — apply the fix and restart"
