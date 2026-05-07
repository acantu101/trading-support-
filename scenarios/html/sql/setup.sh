#!/bin/bash
source "$(dirname "$0")/../_lib/common.sh"

step "SQL Scenario: Slow trade blotter query (missing composite index)"

step "Installing sqlite3 if missing..."
sudo apt-get install -y sqlite3 2>/dev/null || true
ok "sqlite3 ready"

step "Creating SQL working directory..."
mkdir -p ~/trading-support/sql
ok "Directory ~/trading-support/sql created"

step "Writing build_db.py..."
cat > ~/trading-support/sql/build_db.py << 'PYEOF'
#!/usr/bin/env python3
"""
Build a SQLite trade database with 500,000 rows.
Scenario: no composite index on (symbol, trade_date) — queries will be slow.
"""
import sqlite3
import random
import datetime
import os
import sys

DB_PATH = os.path.expanduser("~/trading-support/sql/trades.db")

SYMBOLS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'JPM', 'GS', 'BAC']
SIDES   = ['BUY', 'SELL']
VENUES  = ['NASDAQ', 'NYSE', 'BATS', 'IEX', 'ARCA']
TRADERS = [f'T{i:04d}' for i in range(1, 51)]

PRICE_RANGES = {
    'AAPL':  (160, 230),
    'MSFT':  (370, 450),
    'GOOGL': (140, 200),
    'AMZN':  (170, 220),
    'TSLA':  (170, 280),
    'NVDA':  (450, 950),
    'META':  (440, 600),
    'JPM':   (180, 230),
    'GS':    (430, 520),
    'BAC':   (34,  46),
}

def random_date():
    start = datetime.date(2024, 1, 1)
    end   = datetime.date(2025, 12, 31)
    delta = (end - start).days
    return str(start + datetime.timedelta(days=random.randint(0, delta)))

def random_timestamp(date_str):
    # Market hours: 09:30–16:00
    h = random.randint(9, 15)
    m = random.randint(0, 59)
    s = random.randint(0, 59)
    ms = random.randint(0, 999)
    return f"{date_str}T{h:02d}:{m:02d}:{s:02d}.{ms:03d}Z"

def main():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE trades (
            id         INTEGER PRIMARY KEY,
            symbol     TEXT,
            trade_date TEXT,
            quantity   INTEGER,
            price      REAL,
            side       TEXT,
            trader_id  TEXT,
            venue      TEXT,
            timestamp  TEXT
        )
    """)
    # NOTE: No index created here — that is the bug to diagnose.

    TOTAL  = 500_000
    BATCH  = 10_000
    rows   = []

    print(f"Inserting {TOTAL:,} rows in batches of {BATCH:,}...")
    for i in range(1, TOTAL + 1):
        sym   = random.choice(SYMBOLS)
        lo, hi = PRICE_RANGES[sym]
        date  = random_date()
        qty   = random.randint(100, 10_000)
        price = round(random.uniform(lo, hi), 4)
        side  = random.choice(SIDES)
        trader = random.choice(TRADERS)
        venue  = random.choice(VENUES)
        ts     = random_timestamp(date)
        rows.append((sym, date, qty, price, side, trader, venue, ts))

        if len(rows) == BATCH:
            cur.executemany(
                "INSERT INTO trades (symbol, trade_date, quantity, price, side, trader_id, venue, timestamp) "
                "VALUES (?,?,?,?,?,?,?,?)",
                rows
            )
            conn.commit()
            rows = []
            pct = (i / TOTAL) * 100
            print(f"  {i:>7,} / {TOTAL:,}  ({pct:.1f}%)", end='\r', flush=True)

    if rows:
        cur.executemany(
            "INSERT INTO trades (symbol, trade_date, quantity, price, side, trader_id, venue, timestamp) "
            "VALUES (?,?,?,?,?,?,?,?)",
            rows
        )
        conn.commit()

    count = cur.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    print(f"\nDone. {count:,} rows inserted into {DB_PATH}")
    conn.close()

if __name__ == "__main__":
    main()
PYEOF
ok "build_db.py written"

step "Building trades.db (500,000 rows — this takes ~30-60 seconds)..."
python3 ~/trading-support/sql/build_db.py
ok "trades.db built"

step "Writing slow_query.sql..."
cat > ~/trading-support/sql/slow_query.sql << 'SQLEOF'
-- Slow blotter query: no index on (symbol, trade_date)
-- Run with:  sqlite3 ~/trading-support/sql/trades.db < slow_query.sql
-- Enable timer first inside sqlite3:  .timer on

SELECT
    symbol,
    SUM(quantity * price) AS notional,
    COUNT(*)              AS trades
FROM trades
WHERE symbol     = 'AAPL'
  AND trade_date = '2024-11-15'
ORDER BY timestamp;
SQLEOF
ok "slow_query.sql written"

step "Writing explain_hint.txt..."
cat > ~/trading-support/sql/explain_hint.txt << 'HINTEOF'
=== DIAGNOSING THE SLOW QUERY ===

1. Open the database:
   sqlite3 ~/trading-support/sql/trades.db

2. Enable timing:
   .timer on

3. Run the slow query:
   .read ~/trading-support/sql/slow_query.sql

4. Inspect the query plan:
   EXPLAIN QUERY PLAN
   SELECT symbol, SUM(quantity*price) AS notional, COUNT(*) AS trades
   FROM trades
   WHERE symbol = 'AAPL' AND trade_date = '2024-11-15'
   ORDER BY timestamp;

=== READING EXPLAIN QUERY PLAN OUTPUT ===

Without an index you will see something like:
  SCAN TABLE trades          <-- full table scan: reads all 500,000 rows

With the correct index you should see:
  SEARCH TABLE trades USING INDEX idx_trades_symbol_date (symbol=? AND trade_date=?)

=== THE FIX ===

Create a composite index on the two filter columns:

  CREATE INDEX idx_trades_symbol_date ON trades (symbol, trade_date);

Column order matters: put the equality-filter columns first (symbol, trade_date),
and if you also need to sort by timestamp without a second scan, extend it:

  CREATE INDEX idx_trades_symbol_date_ts ON trades (symbol, trade_date, timestamp);

After creating the index, re-run EXPLAIN QUERY PLAN and .timer to confirm the speedup.

=== WHY A COMPOSITE INDEX? ===

A single-column index on just `symbol` would still require scanning all AAPL rows
to filter by trade_date.  A composite index (symbol, trade_date) lets SQLite jump
directly to the matching rows — reducing I/O from O(N) to O(log N + k) where k is
the result set size.
HINTEOF
ok "explain_hint.txt written"

info "Run the slow query: sqlite3 ~/trading-support/sql/trades.db < ~/trading-support/sql/slow_query.sql"
info "Use .timer on and EXPLAIN QUERY PLAN to diagnose. Fix with CREATE INDEX."
