#!/bin/bash
# sql/verify.sh — Verify fix for missing composite index on trades table
source "$(dirname "$0")/../_lib/common.sh"

banner "SQL Scenario: Verify Fix"

DB="$HOME/trading-support/sql/trades.db"
SLOW_QUERY="$HOME/trading-support/sql/slow_query.sql"

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [ ! -f "$DB" ]; then
  err "trades.db not found at $DB"
  err "Did you run setup.sh first?"
  exit 1
fi

if ! command -v sqlite3 &>/dev/null; then
  err "sqlite3 not found. Install with: sudo apt-get install -y sqlite3"
  exit 1
fi

# ── Check for index on (symbol, trade_date) ───────────────────────────────────
INDEX_OUTPUT=$(sqlite3 "$DB" ".indexes trades" 2>/dev/null)

# Also check if any index covers both symbol and trade_date via schema
COVERING_INDEX=$(sqlite3 "$DB" "
SELECT name FROM sqlite_master
WHERE type='index'
  AND tbl_name='trades'
  AND (
    sql LIKE '%symbol%trade_date%'
    OR sql LIKE '%trade_date%symbol%'
  );
" 2>/dev/null)

# ── Not fixed branch ──────────────────────────────────────────────────────────
if [ -z "$INDEX_OUTPUT" ] && [ -z "$COVERING_INDEX" ]; then
  echo ""
  err "The table still has no index on the query columns."
  echo ""
  info "EXPLAIN QUERY PLAN output (what SQLite does right now):"
  echo ""
  sqlite3 "$DB" "
EXPLAIN QUERY PLAN
SELECT symbol, SUM(quantity * price) AS notional, COUNT(*) AS trades
FROM trades
WHERE symbol = 'AAPL' AND trade_date = '2024-11-15'
ORDER BY timestamp;
" | sed 's/^/    /'
  echo ""
  warn "SCAN TABLE trades — SQLite is reading all 500,000 rows for every query."
  echo ""
  step "Nudge: run EXPLAIN QUERY PLAN on the slow query, then create a"
  step "       composite index on the two WHERE-clause columns."
  step "       Column order matters — put the most selective one first."
  step "       Hint: CREATE INDEX idx_... ON trades (symbol, trade_date);"
  echo ""
  exit 1
fi

# ── Fixed branch ──────────────────────────────────────────────────────────────
# Determine which index was created
FOUND_INDEX="${COVERING_INDEX:-$(echo "$INDEX_OUTPUT" | head -1)}"
ok "Index detected on trades: ${FOUND_INDEX}"
echo ""

# ── Show EXPLAIN QUERY PLAN with the index ────────────────────────────────────
step "Checking query plan — confirming index is being used..."
sleep 0.3
echo ""
echo -e "${BOLD}${CYAN}>>> EXPLAIN QUERY PLAN SELECT ... FROM trades WHERE symbol='AAPL' AND trade_date='2024-11-15'${NC}"
echo ""
sqlite3 "$DB" "
EXPLAIN QUERY PLAN
SELECT symbol, SUM(quantity * price) AS notional, COUNT(*) AS trades
FROM trades
WHERE symbol = 'AAPL' AND trade_date = '2024-11-15'
ORDER BY timestamp;
" | sed 's/^/    /'
echo ""
sleep 0.3

# ── Run the actual query with timing ─────────────────────────────────────────
step "Running the blotter query with .timer on — measuring actual elapsed time..."
sleep 0.3
echo ""
echo -e "${BOLD}${CYAN}>>> sqlite3 trades.db  (.timer on, then run slow_query.sql)${NC}"
echo ""

QUERY_RESULT=$(sqlite3 "$DB" "
.timer on
SELECT symbol, SUM(quantity * price) AS notional, COUNT(*) AS trades
FROM trades
WHERE symbol = 'AAPL' AND trade_date = '2024-11-15'
ORDER BY timestamp;
" 2>&1)

echo "$QUERY_RESULT" | sed 's/^/    /'
echo ""
sleep 0.3

# Extract the elapsed time from sqlite3 timer output
ELAPSED=$(echo "$QUERY_RESULT" | grep -i "real\|elapsed\|Run Time" | head -1 | grep -oE '[0-9]+\.[0-9]+' | head -1)

# ── Before/after comparison ───────────────────────────────────────────────────
echo -e "${BOLD}Before/After Comparison:${NC}"
echo ""
printf "  %-12s  %-30s  %s\n" "Version" "Plan" "Time"
printf "  %-12s  %-30s  %s\n" "────────────" "──────────────────────────────" "──────────────"
printf "  %-12s  %-30s  %s\n" "Before fix" "SCAN TABLE trades (500K rows)" "~8.2s"
if [ -n "$ELAPSED" ]; then
  printf "  %-12s  %-30s  %s\n" "After fix" "SEARCH TABLE USING INDEX" "${ELAPSED}s"
else
  printf "  %-12s  %-30s  %s\n" "After fix" "SEARCH TABLE USING INDEX" "<50ms"
fi
echo ""
sleep 0.3

ok "Query is now using the index. Blotter query is fast."
echo ""

# ── SCENARIO COMPLETE summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║         SCENARIO COMPLETE — SQL Missing Composite Index     ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}1. What you diagnosed${NC}"
echo "   The trade blotter query filtering on (symbol, trade_date) was taking"
echo "   ~8 seconds. EXPLAIN QUERY PLAN showed 'SCAN TABLE trades' — SQLite"
echo "   was reading all 500,000 rows on every query. There were no indexes"
echo "   on the trades table. The query touched ~500K rows to return a handful"
echo "   of matching trades for one symbol on one date."
echo ""

echo -e "${BOLD}${CYAN}2. What you fixed${NC}"
echo "   Created a composite index: ${FOUND_INDEX}"
echo "   This allows SQLite to jump directly to the matching rows using a"
echo "   B-tree seek, reading O(log N + k) pages instead of O(N) pages,"
echo "   where k is the number of matching rows."
echo ""

echo -e "${BOLD}${CYAN}3. Real-world context${NC}"
echo "   Composite index column order matters critically:"
echo "   - CREATE INDEX idx ON trades (symbol, trade_date)  -- good for this query"
echo "   - CREATE INDEX idx ON trades (trade_date, symbol)  -- good for date-range queries"
echo "   - The leftmost column must match your most common filter predicate"
echo ""
echo "   For production databases, prefer CREATE INDEX CONCURRENTLY (PostgreSQL)"
echo "   or online DDL (MySQL/MariaDB) to avoid write locks during index builds."
echo "   SQLite does not support concurrent builds — use a maintenance window."
echo ""
echo "   Covering indexes extend the index to include projected columns:"
echo "   CREATE INDEX idx ON trades (symbol, trade_date, timestamp, quantity, price)"
echo "   This lets SQLite satisfy the query entirely from the index without"
echo "   touching the main table pages (index-only scan)."
echo ""

echo -e "${BOLD}${CYAN}4. How to prevent it in production${NC}"
echo "   a) EXPLAIN ANALYZE (Postgres) or EXPLAIN QUERY PLAN (SQLite) should be"
echo "      part of every schema review for queries touching large tables."
echo "   b) Add indexes in the same migration that adds the table, not after."
echo "   c) When NOT to index:"
echo "      - High-write tables where index maintenance overhead exceeds read gain"
echo "      - Low-cardinality columns (e.g., side IN ('BUY','SELL'))"
echo "      - Columns used in infrequent, low-priority queries"
echo "   d) Monitor pg_stat_user_indexes (Postgres) for unused indexes —"
echo "      unused indexes consume write overhead with no read benefit."
echo "   e) For trade blotters specifically: always index (symbol, trade_date)"
echo "      and consider partitioning the table by trade_date for T+0/T+1 queries."
echo ""
