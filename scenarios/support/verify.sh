#!/bin/bash
# scenarios/support/verify.sh — Verify fix for silent exception swallowing NVDA quotes

source "$(dirname "$0")/../_lib/common.sh"

NORMALIZER="$HOME/trading-support/support/normalizer.py"
FEED_FILE="$HOME/trading-support/support/feed/normalized.jsonl"

banner "Support — NVDA Silent Exception Verify"

# ── Check 1: Does normalizer still have bare except: pass? ───────────────────
info "Inspecting normalizer.py for silent exception pattern..."
sleep 0.3

STILL_SILENT=false
if [[ -f "$NORMALIZER" ]]; then
    # Bare except with pass — the classic silent swallow
    if python3 -c "
import ast, sys

with open('$NORMALIZER') as f:
    src = f.read()

tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, (ast.Try,)):
        for handler in node.handlers:
            # bare except: (type is None) or except Exception with only Pass
            body_is_pass = (len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass))
            if body_is_pass:
                sys.exit(0)  # found silent handler
sys.exit(1)
" 2>/dev/null; then
        STILL_SILENT=true
    fi
fi

# ── Check 2: Has NVDA appeared in normalized feed recently? ──────────────────
NVDA_RECENT=false
if [[ -f "$FEED_FILE" ]]; then
    FILE_MTIME=$(stat -c %Y "$FEED_FILE" 2>/dev/null || stat -f %m "$FEED_FILE" 2>/dev/null)
    NOW_EPOCH=$(date +%s)
    AGE=$(( NOW_EPOCH - FILE_MTIME ))

    if [[ $AGE -lt 30 ]]; then
        if grep -q '"symbol":"NVDA"' "$FEED_FILE" 2>/dev/null || grep -q '"symbol": "NVDA"' "$FEED_FILE" 2>/dev/null; then
            NVDA_RECENT=true
        fi
    fi
fi

# ── Not fixed? ───────────────────────────────────────────────────────────────
if $STILL_SILENT || ! $NVDA_RECENT; then
    echo ""
    err "NOT FIXED"
    echo ""

    if $STILL_SILENT; then
        echo -e "${RED}NVDA is still dark. The normalizer is swallowing the exception silently.${NC}"
        echo ""
        echo -e "${YELLOW}Found a bare ${BOLD}except: pass${NC}${YELLOW} block in normalizer.py that is eating the error.${NC}"
        echo ""
        echo -e "${BOLD}Nudge:${NC} Find the except clause in normalizer.py that catches the"
        echo -e "  NVDA processing error. At minimum, add structured logging:"
        echo ""
        echo -e "  ${CYAN}except Exception as e:${NC}"
        echo -e "  ${CYAN}    logger.error(f'NVDA processing failed: {e}')${NC}"
        echo ""
        echo -e "  Then ${BOLD}fix the underlying ValueError${NC} — the silent except is hiding"
        echo -e "  a real bug in how NVDA's data is being parsed or normalized."
        echo -e "  Look for a field that differs between NVDA and the other symbols."
    elif ! $NVDA_RECENT; then
        echo -e "${YELLOW}NVDA has not appeared in normalized.jsonl within the last 30 seconds.${NC}"
        echo -e "${YELLOW}The normalizer may be running but NVDA quotes are still not flowing.${NC}"
        echo ""
        echo -e "${BOLD}Nudge:${NC} Check the normalizer logs for any NVDA-related errors."
        echo -e "  Ensure the underlying ValueError is fixed, not just the logging."
    fi
    echo ""
    exit 1
fi

# ── Fixed ────────────────────────────────────────────────────────────────────
ok "Silent exception removed and NVDA quotes are flowing."
echo ""

NOW=$(date +"%H:%M:%S")

info "Quote monitor — all symbols:"
sleep 0.3
echo ""
echo -e "    ${BOLD}Symbol   Last      Bid       Ask       Age    Status${NC}"
echo -e "    ─────────────────────────────────────────────────────────"
sleep 0.3
echo -e "    ${GREEN}AAPL     182.41    182.40    182.42    0.3s   ${BOLD}LIVE${NC}"
sleep 0.3
echo -e "    ${GREEN}MSFT     415.22    415.21    415.23    0.1s   ${BOLD}LIVE${NC}"
sleep 0.3
echo -e "    ${GREEN}GOOGL    175.08    175.07    175.09    0.2s   ${BOLD}LIVE${NC}"
sleep 0.3
echo -e "    ${GREEN}NVDA     875.60    875.58    875.62    0.4s   ${BOLD}LIVE${NC}  ← restored"
sleep 0.3
echo -e "    ${GREEN}TSLA     194.73    194.72    194.74    0.3s   ${BOLD}LIVE${NC}"
sleep 0.3
echo -e "    ${GREEN}SPY      523.15    523.14    523.16    0.1s   ${BOLD}LIVE${NC}"
sleep 0.3
echo ""
ok "All 6 symbols green and current."

echo ""
info "Normalizer log — error now visible (was previously swallowed):"
sleep 0.3
echo ""
echo -e "    ${YELLOW}[WARN]  2026-05-04 ${NOW}  normalizer  NVDA processing failed:${NC}"
echo -e "    ${YELLOW}        ValueError: could not convert string to float: 'N/A'${NC}"
echo -e "    ${YELLOW}        (field: 'last_sale_price', raw value from upstream feed)${NC}"
echo -e "    ${GREEN}[INFO]  2026-05-04 ${NOW}  normalizer  NVDA: applied fallback to prior_close${NC}"
echo -e "    ${GREEN}[INFO]  2026-05-04 ${NOW}  normalizer  NVDA quote emitted successfully${NC}"
sleep 0.3

echo ""
info "Client ticket update:"
sleep 0.3
echo ""
echo -e "    ${BOLD}Ticket #TKT-2847  |  Priority: P1  |  Client: Meridian Capital${NC}"
echo -e "    ─────────────────────────────────────────────────────────────────"
echo -e "    ${GREEN}Resolved:${NC} NVDA quotes restored at ${BOLD}${NOW}${NC}."
echo -e "    Root cause: silent exception in normalizer NVDA processing thread."
echo -e "    A ValueError ('N/A' in last_sale_price) was caught by a bare"
echo -e "    'except: pass' block, causing NVDA to silently drop without any"
echo -e "    log entry or alert."
echo -e "    Duration: ~17 minutes of missing NVDA data."
echo -e "    Fix: Added structured exception logging + 'N/A' → prior_close fallback."
echo -e "    Monitoring: NVDA publishing confirmed. All symbols green."

echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║            SCENARIO COMPLETE — SUPPORT                      ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}What you diagnosed${NC}"
echo -e "  NVDA quotes went dark while all other symbols kept publishing. The root"
echo -e "  cause was a bare 'except: pass' block in normalizer.py that silently"
echo -e "  swallowed a ValueError raised when the upstream feed sent 'N/A' in the"
echo -e "  last_sale_price field for NVDA — a field that only NVDA hit that day."
echo ""

echo -e "${BOLD}${CYAN}What you fixed${NC}"
echo -e "  Replaced the silent 'except: pass' with structured logging and a"
echo -e "  fallback strategy (use prior_close when last_sale_price is unparseable)."
echo -e "  The error is now visible in logs, alertable, and NVDA quotes flow."
echo ""

echo -e "${BOLD}${CYAN}Real-world context${NC}"
echo -e "  ${BOLD}The silent exception antipattern:${NC}"
echo -e "  'except: pass' is the most dangerous pattern in trading systems."
echo -e "  Errors disappear completely — no log, no metric, no alert. Data goes"
echo -e "  dark with no signal that anything is wrong. A client or a risk manager"
echo -e "  notices before the engineering team does."
echo ""
echo -e "  ${BOLD}Why NVDA and not the others?${NC}"
echo -e "  Per-symbol anomalies are common: corporate actions, trading halts, or"
echo -e "  upstream feed bugs can send malformed data for one ticker while all"
echo -e "  others are fine. Your normalizer must handle per-symbol exceptions"
echo -e "  without killing the entire pipeline."
echo ""
echo -e "  ${BOLD}Writing the incident timeline for the client:${NC}"
echo -e "  - HH:MM:SS  Last valid NVDA quote published"
echo -e "  - HH:MM:SS  Client alert raised (NVDA stale)"
echo -e "  - HH:MM:SS  Ticket opened"
echo -e "  - HH:MM:SS  Root cause identified (silent exception)"
echo -e "  - HH:MM:SS  Fix deployed"
echo -e "  - HH:MM:SS  NVDA quotes confirmed restored"
echo ""

echo -e "${BOLD}${CYAN}How to prevent it${NC}"
echo -e "  - Ban bare 'except: pass' via a linter rule (flake8-bugbear B001/B007)."
echo -e "  - Require at minimum: except Exception as e: logger.error(...)"
echo -e "  - Add a per-symbol staleness check: if any symbol hasn't published in"
echo -e "    N seconds, fire an alert. This catches silent failures immediately."
echo -e "  - Set an SLA for data quality: e.g., 99.9% of quotes within 500ms of"
echo -e "    upstream. Measure it. Alert on breach."
echo -e "  - Use structured logging (JSON) so exception fields are queryable in"
echo -e "    your observability stack (Splunk, Datadog, ELK)."
echo ""
