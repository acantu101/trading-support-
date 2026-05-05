#!/bin/bash
# Scenario: System design challenge — real-time P&L system
source "$(dirname "$0")/../_lib/common.sh"

LAB_DIR=~/trading-support/interview

echo "=== Interview Scenario: Real-Time P&L System Design ==="
echo ""

# Step 1: Create directories
mkdir -p "$LAB_DIR"/{design,skeleton,reference}

# Step 2: Write requirements.md
cat > "$LAB_DIR/design/requirements.md" << 'EOF'
# Real-Time P&L System — Requirements

## Overview
Design a production-grade real-time Profit & Loss (P&L) calculation system
for an equity trading desk.

## Functional Requirements

### Ingestion
- Ingest FIX fill reports (ExecutionReport, MsgType=8) at 1,000,000 trades/day
- Source: FIX gateway (TCP sessions, multiple venues)
- Each fill contains: symbol, side, qty, price, timestamp, order_id, exec_id

### P&L Calculation
- P&L must be updated within 500ms of fill receipt (end-to-end SLA)
- P&L types required:
  - Realized P&L: profit/loss from closed positions
  - Unrealized P&L: mark-to-market on open positions
  - Total P&L: realized + unrealized
- Position types: long, short, flat
- Cost basis methods: FIFO (primary), LIFO (configurable per portfolio)

### Market Data
- Consume real-time price feed for mark-to-market
- 5,000 equity symbols
- Price update frequency: up to 1,000 updates/second across all symbols

### Query API
- Support 200 concurrent portfolio queries
- Query types:
  - Get P&L for a single portfolio (by portfolio_id)
  - Get P&L for a single symbol across all portfolios
  - Get aggregate firm-wide P&L
- Response time SLA: < 50ms at p99

### Portfolios
- Up to 500 portfolios
- Each portfolio may hold positions in any subset of 5,000 symbols

## Non-Functional Requirements

### Reliability
- Single datacenter failover (active/passive)
- Zero data loss on failover (fills must be persisted before ack)
- RTO: < 30 seconds
- RPO: 0 (no fills lost)

### Scalability
- Handle 2x peak load without degradation
- Designed for horizontal scaling of stateless components

### Reconciliation
- End-of-day reconciliation job: compare calculated P&L vs prime broker statement
- Alert on discrepancies > $1,000

## Out of Scope
- Multi-currency FX conversion (USD only for this design)
- Options / futures (equities only)
- Tax lot accounting
EOF

# Step 3: Write architecture.txt
cat > "$LAB_DIR/design/architecture.txt" << 'EOF'
Real-Time P&L System — Architecture Template
=============================================
Fill in the [?] boxes with your component choices and justifications.

                    INGESTION LAYER
                    ───────────────
[FIX Fill Reports] ──→ [? Ingestor] ──→ [? Message Bus / Queue]
(venue A, B, C)         (protocol      (e.g., Kafka, Pulsar, RabbitMQ?)
                         translation,   Topic: fills.raw
                         validation)    Partitioned by: ?
                              │
                              ↓ (persisted before ack — why?)
                         [? Durable Store]
                         (fills journal)

                    CALCULATION LAYER
                    ─────────────────
[? Message Bus] ──→ [? Position Calculator]
                         │
                         │  reads positions, writes updates
                         ↓
                    [? Position Store]      ←──── [Market Price Feed]
                    (e.g., Redis, DB?)              │
                    Key: portfolio+symbol            ↓
                    Value: qty, avg_cost       [? Price Consumer]
                         │                    (5,000 symbols,
                         │                     1K updates/sec)
                         ↓
                    [? P&L Calculator]
                    (realized + unrealized)
                         │
                         ↓
                    [? P&L Store / Cache]
                    (serves query API)

                    QUERY LAYER
                    ───────────
                    [? Query API] ←──── [200 concurrent clients]
                    (REST? gRPC?         (risk systems, dashboards,
                     WebSocket?)          trader terminals)
                         │
                    [? Read Cache]
                    (optional — why?)

                    FAILOVER LAYER
                    ──────────────
  DC-PRIMARY                              DC-SECONDARY (passive)
  ──────────                              ──────────────────────
  [All above] ──→ [? Replication] ──→    [? Standby components]
                  (sync? async?)          Failover trigger: ?
                                          Failover time target: <30s

                    RECONCILIATION
                    ──────────────
  [? EOD Recon Job] ←── [Prime Broker Statement (FTP/SFTP)]
        │
        ↓
  [? Alert if discrepancy > $1,000]

=============================================
QUESTIONS TO ANSWER:
1. Why partition the fills topic by symbol (or portfolio)?
2. How do you ensure zero data loss on failover?
3. What happens if the price feed goes down — how does P&L degrade?
4. How do you handle a fill arriving out of order?
5. FIFO cost basis: describe the data structure for a position.
6. What's your bottleneck at 1M fills/day? How do you scale it?
EOF

# Step 4: Write component-checklist.md
cat > "$LAB_DIR/design/component-checklist.md" << 'EOF'
# P&L System — Component Design Checklist

Work through each component. For each, answer: technology choice, justification,
data model, failure mode, and scaling strategy.

## [ ] 1. FIX Fill Ingestor
- Technology choice:
- How do you parse FIX ExecutionReport (tag 35=8)?
- How do you handle duplicate fills (idempotency)?
- How do you handle dropped FIX session / sequence gap?

## [ ] 2. Message Bus / Fill Queue
- Technology choice (Kafka? Pulsar? Redis Streams?):
- Partition key:
- Consumer group strategy:
- Retention policy:
- At-least-once vs exactly-once delivery — which do you need and why?

## [ ] 3. Position Calculator
- Stateful or stateless? Why?
- How do you load initial positions on startup?
- FIFO implementation — describe the data structure:
- How do you handle a cancel/replace on a previously filled order?

## [ ] 4. Market Price Consumer
- Technology: (direct UDP multicast? Kafka? REST poll?)
- How often do you update unrealized P&L per symbol?
- What if price is stale (feed down)? Mark with what timestamp?

## [ ] 5. Position / P&L Store
- Technology choice:
- Schema / key design:
- Consistency model (strong? eventual?):
- Read path vs write path:

## [ ] 6. Query API
- Protocol (REST / gRPC / WebSocket):
- How do you serve 200 concurrent clients at <50ms p99?
- Do you cache? Cache invalidation strategy?
- Authentication/authorization model:

## [ ] 7. Failover Strategy
- Active/passive — what is replicated?
- Replication: synchronous or asynchronous? Trade-offs?
- How does the secondary know when to take over?
- How do clients discover the failover endpoint?

## [ ] 8. EOD Reconciliation Job
- How do you obtain the prime broker statement?
- Matching logic: by exec_id? by order_id?
- How do you handle timing differences (fills near midnight)?
- Alert routing: PagerDuty? email?

## [ ] 9. Observability
- Key metrics to emit (latency, fill lag, P&L freshness):
- How do you alert on SLA breach (>500ms fill-to-PnL)?
- Distributed tracing: trace a fill from FIX session to P&L update
EOF

# Step 5: Write pnl_engine.py skeleton
cat > "$LAB_DIR/skeleton/pnl_engine.py" << 'EOF'
#!/usr/bin/env python3
"""
P&L Engine Skeleton
===================
Implement the stubs below. Each class has a docstring describing
the expected behavior. Focus on correctness first, then efficiency.

Run with: python3 pnl_engine.py
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque
import time


# ---------------------------------------------------------------------------
# Data Types
# ---------------------------------------------------------------------------

@dataclass
class Fill:
    """A single trade fill from a FIX ExecutionReport."""
    exec_id: str
    order_id: str
    portfolio_id: str
    symbol: str
    side: str        # "BUY" or "SELL"
    qty: float
    price: float
    timestamp: float  # unix epoch seconds


@dataclass
class Position:
    """Current position for a (portfolio, symbol) pair."""
    portfolio_id: str
    symbol: str
    qty: float = 0.0           # positive = long, negative = short
    avg_cost: float = 0.0      # average cost per share
    realized_pnl: float = 0.0
    # FIFO lot queue: each entry is (qty, cost_per_share)
    lots: deque = field(default_factory=deque)


@dataclass
class PnLSnapshot:
    """Point-in-time P&L for a (portfolio, symbol) pair."""
    portfolio_id: str
    symbol: str
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    position_qty: float
    last_price: float
    as_of: float  # unix epoch


# ---------------------------------------------------------------------------
# Class Stubs
# ---------------------------------------------------------------------------

class FillIngestor:
    """
    Consumes FIX ExecutionReport messages and produces Fill objects.

    Responsibilities:
    - Parse FIX tag-value pairs from raw message string
    - Validate required fields (exec_id, symbol, side, qty, price)
    - Deduplicate fills by exec_id (idempotency)
    - Publish valid, unique fills to the downstream calculator

    Usage:
        ingestor = FillIngestor()
        fill = ingestor.parse_fix_message(raw_fix_str)
        if fill:
            calculator.process_fill(fill)
    """

    def __init__(self):
        self.seen_exec_ids: set = set()

    def parse_fix_message(self, raw: str) -> Optional[Fill]:
        """
        Parse a raw FIX ExecutionReport string into a Fill.

        Args:
            raw: FIX message as tag=value pairs separated by SOH (\x01)
                 Example: "35=8\x0149=EXCHANGE\x0156=PROD-OMS\x0117=EXEC001..."

        Returns:
            Fill object if valid and not a duplicate, else None.
        """
        pass

    def is_duplicate(self, exec_id: str) -> bool:
        """Return True if this exec_id has already been processed."""
        pass


class PositionCalculator:
    """
    Maintains positions for all (portfolio, symbol) pairs.
    Applies fills using FIFO cost basis to compute realized P&L.

    FIFO rule:
        When selling, consume the oldest lots first.
        Realized P&L per lot = (sell_price - lot_cost) * lot_qty

    Usage:
        calc = PositionCalculator()
        calc.process_fill(fill)
        pos = calc.get_position("PORT-1", "NVDA")
    """

    def __init__(self):
        # Key: (portfolio_id, symbol) -> Position
        self.positions: Dict[Tuple[str, str], Position] = {}

    def process_fill(self, fill: Fill) -> Position:
        """
        Apply a fill to the position for (fill.portfolio_id, fill.symbol).

        For a BUY: add a lot (qty, price) to the FIFO queue, update avg_cost.
        For a SELL: consume lots FIFO, compute realized P&L for each consumed lot.

        Returns the updated Position.
        """
        pass

    def get_position(self, portfolio_id: str, symbol: str) -> Optional[Position]:
        """Return current position, or None if no fills yet."""
        pass

    def _apply_buy(self, position: Position, qty: float, price: float) -> None:
        """Add a lot to the position. Update avg_cost."""
        pass

    def _apply_sell(self, position: Position, qty: float, price: float) -> float:
        """Consume lots FIFO. Return realized P&L for this sell."""
        pass


class MarketPriceConsumer:
    """
    Maintains the latest market price for each symbol.
    In production: subscribes to a price feed (multicast UDP, Kafka, etc.)

    Usage:
        price_consumer = MarketPriceConsumer()
        price_consumer.update_price("NVDA", 875.50)
        price = price_consumer.get_price("NVDA")
    """

    def __init__(self):
        # Key: symbol -> (price, timestamp)
        self._prices: Dict[str, Tuple[float, float]] = {}
        self.staleness_threshold_sec: float = 5.0

    def update_price(self, symbol: str, price: float) -> None:
        """Store the latest price and timestamp for a symbol."""
        pass

    def get_price(self, symbol: str) -> Optional[float]:
        """
        Return the latest price for a symbol, or None if unknown.
        If the price is stale (older than staleness_threshold_sec), log a warning.
        """
        pass

    def is_stale(self, symbol: str) -> bool:
        """Return True if price is missing or older than staleness_threshold_sec."""
        pass


class PnLStore:
    """
    Persists and retrieves P&L snapshots.
    In production: backed by Redis, a time-series DB, or an in-memory grid.

    For this skeleton: use an in-memory dict.

    Usage:
        store = PnLStore()
        store.write(snapshot)
        snap = store.get("PORT-1", "NVDA")
    """

    def __init__(self):
        # Key: (portfolio_id, symbol) -> PnLSnapshot
        self._store: Dict[Tuple[str, str], PnLSnapshot] = {}

    def write(self, snapshot: PnLSnapshot) -> None:
        """Upsert a P&L snapshot."""
        pass

    def get(self, portfolio_id: str, symbol: str) -> Optional[PnLSnapshot]:
        """Retrieve the latest P&L snapshot for a (portfolio, symbol) pair."""
        pass

    def get_portfolio_pnl(self, portfolio_id: str) -> List[PnLSnapshot]:
        """Return all P&L snapshots for a given portfolio."""
        pass

    def get_firm_pnl(self) -> dict:
        """
        Return aggregate firm-wide P&L:
        {
          "total_realized": float,
          "total_unrealized": float,
          "total_pnl": float,
          "as_of": float
        }
        """
        pass


class PnLQueryAPI:
    """
    HTTP/gRPC query layer that serves P&L data to 200 concurrent clients.

    In production: FastAPI or gRPC server backed by PnLStore.
    For this skeleton: implement the query methods directly.

    Usage:
        api = PnLQueryAPI(store, price_consumer)
        result = api.query_portfolio("PORT-1")
        result = api.query_symbol("NVDA")
        result = api.query_firm()
    """

    def __init__(self, store: PnLStore, price_consumer: MarketPriceConsumer):
        self.store = store
        self.price_consumer = price_consumer

    def query_portfolio(self, portfolio_id: str) -> dict:
        """
        Return P&L summary for a portfolio.
        Recompute unrealized P&L using latest prices from price_consumer.
        SLA: <50ms response time.
        """
        pass

    def query_symbol(self, symbol: str) -> dict:
        """
        Return aggregate P&L across all portfolios for a given symbol.
        """
        pass

    def query_firm(self) -> dict:
        """Return firm-wide P&L totals."""
        pass


# ---------------------------------------------------------------------------
# Wiring Example (implement above, then run this)
# ---------------------------------------------------------------------------

def main():
    print("P&L Engine Skeleton — implement the stubs above, then run this.")
    print("")

    # Wire components
    ingestor   = FillIngestor()
    calculator = PositionCalculator()
    prices     = MarketPriceConsumer()
    store      = PnLStore()
    api        = PnLQueryAPI(store, prices)

    # Example fill
    sample_fix = (
        "35=8\x0117=EXEC-001\x0111=ORD-001\x011=PORT-1"
        "\x0155=NVDA\x0154=1\x0138=100\x0144=875.50\x0160=1746403200"
    )

    fill = ingestor.parse_fix_message(sample_fix)
    if fill:
        pos = calculator.process_fill(fill)
        prices.update_price("NVDA", 880.00)
        # TODO: compute unrealized P&L and write to store
        print(f"Position after fill: qty={pos.qty}, avg_cost={pos.avg_cost}")
    else:
        print("Fill parsing not yet implemented — fill in parse_fix_message()")


if __name__ == "__main__":
    main()
EOF

# Step 6: Write reference/key-concepts.md
cat > "$LAB_DIR/reference/key-concepts.md" << 'EOF'
# P&L System — Key Concepts Reference

## Mark-to-Market P&L Formula

    Unrealized P&L = (current_market_price - avg_cost_per_share) × quantity

    For a long position  (qty > 0): profit when price > avg_cost
    For a short position (qty < 0): profit when price < avg_cost

    Realized P&L  = sum of P&L locked in by closing trades
    Total P&L     = Realized P&L + Unrealized P&L

## FIFO Cost Basis

FIFO (First In, First Out) — oldest shares are sold first.

Example:
    Buy  100 shares @ $10.00  → lot: (100, 10.00)
    Buy  200 shares @ $12.00  → lot: (200, 12.00)
    Sell 150 shares @ $13.00

    FIFO consumption:
      - Sell 100 from first lot:  realized = (13.00 - 10.00) × 100 = $300
      - Sell  50 from second lot: realized = (13.00 - 12.00) ×  50 = $50
      Total realized = $350

    Remaining position: 150 shares @ $12.00 (the remaining second lot)

## LIFO Cost Basis

LIFO (Last In, First Out) — most recently purchased shares are sold first.

Same example with LIFO:
    Sell 150 from second lot (most recent):
      - 150 × (13.00 - 12.00) = $150 realized
    Remaining: 100 shares @ $10.00 + 50 shares @ $12.00

## Position Netting

When a new fill is in the opposite direction and crosses flat:
    Position: SHORT 100 shares
    Fill: BUY 150 shares

    Net result:
      - First 100 shares close the short → realize P&L on 100 shares
      - Remaining 50 shares open a new LONG position

## Average Cost Method (alternative to FIFO/LIFO)

    avg_cost = total_cost_basis / total_shares

    On each buy: avg_cost = (prev_cost_basis + new_qty × new_price) / (prev_qty + new_qty)
    On each sell: realized = (sell_price - avg_cost) × sell_qty

## Key FIX Tags for Fills (ExecutionReport, MsgType=8)

    Tag 17  ExecID          — unique execution identifier
    Tag 11  ClOrdID         — client order ID
    Tag 55  Symbol          — instrument symbol
    Tag 54  Side            — 1=Buy, 2=Sell
    Tag 38  OrderQty        — order quantity
    Tag 32  LastQty         — fill quantity (this execution)
    Tag 31  LastPx          — fill price (this execution)
    Tag 151 LeavesQty       — remaining unfilled quantity
    Tag 14  CumQty          — cumulative filled quantity
    Tag 1   Account         — portfolio/account identifier
    Tag 60  TransactTime    — fill timestamp

## Idempotency

    Every fill has a unique ExecID (tag 17).
    A robust ingestor deduplicates by ExecID to handle:
    - FIX retransmissions after sequence gap recovery
    - At-least-once message bus delivery

## Failover Considerations

    Active/Passive setup:
    - Primary handles all writes
    - Secondary replicates state (positions, fills journal)
    - On failover: secondary promotes, clients reconnect

    RPO=0 requires synchronous replication of fills before ACK.
    This adds latency — trade-off: durability vs. speed.

## Reconciliation

    EOD recon compares:
      Calculated position × closing price = our unrealized P&L
      vs. prime broker's mark = their statement P&L

    Discrepancies arise from:
    - Fills processed after market close
    - Corporate actions (splits, dividends) not applied
    - Price source differences
EOF

# Steps 7-9: Print instructions
echo "Design challenge ready. Start with:"
echo "  cat ~/trading-support/interview/design/requirements.md"
echo ""
echo "Then fill in ~/trading-support/interview/design/architecture.txt"
echo ""
echo "Implement skeletons in ~/trading-support/interview/skeleton/"
echo "  python3 ~/trading-support/interview/skeleton/pnl_engine.py"
echo ""
echo "Reference material: ~/trading-support/interview/reference/key-concepts.md"
