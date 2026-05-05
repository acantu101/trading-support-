#!/bin/bash
# _lib/common.sh — Shared helpers for trading-support lab scenarios

# ── Color & formatting ──────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
ORANGE='\033[0;33m'   # terminal 256-color orange fallback
BOLD='\033[1m'
NC='\033[0m'          # No Color / reset

# ── Standard lab directories ────────────────────────────────────────────────
LAB_DIR="$HOME/trading-support"
LOG_DIR="$LAB_DIR/logs"
CONFIG_DIR="$LAB_DIR/config"
DATA_DIR="$LAB_DIR/data"
PIDS_DIR="$LAB_DIR/pids"

# ── Print helpers ────────────────────────────────────────────────────────────
ok()   { echo -e "${GREEN}${BOLD}[OK]${NC}    $*"; }
warn() { echo -e "${YELLOW}${BOLD}[WARN]${NC}  $*"; }
err()  { echo -e "${RED}${BOLD}[ERR]${NC}   $*" >&2; }
info() { echo -e "${CYAN}${BOLD}[INFO]${NC}  $*"; }
step() { echo -e "${BLUE}${BOLD}  -->  ${NC}$*"; }

# ── ASCII banner ─────────────────────────────────────────────────────────────
banner() {
    local title="${1:-Trading Support Lab}"
    local width=60
    local line
    line=$(printf '%*s' "$width" '' | tr ' ' '─')
    echo -e ""
    echo -e "${BOLD}${CYAN}┌${line}┐${NC}"
    printf "${BOLD}${CYAN}│${NC}${BOLD}  %-*s${CYAN}│${NC}\n" $((width - 2)) " $title"
    echo -e "${BOLD}${CYAN}└${line}┘${NC}"
    echo -e ""
}

# ── Ensure core lab dirs exist ───────────────────────────────────────────────
ensure_dirs() {
    local dirs=("$LAB_DIR" "$LOG_DIR" "$CONFIG_DIR" "$DATA_DIR" "$PIDS_DIR")
    for d in "${dirs[@]}"; do
        mkdir -p "$d"
    done
    ok "Lab directories ready under $LAB_DIR"
}
