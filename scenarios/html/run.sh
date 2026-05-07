#!/bin/bash
# Trading Support Scenario Lab — Main Menu
# Runs ON the VM. Presents all scenarios with setup/reset options.

SCENARIOS_DIR="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# Scenario registry: "display_name:directory"
# ---------------------------------------------------------------------------
SCENARIO_LIST=(
    "FIX Session Drop (sequence gap / logon reject):fix"
    "Networking: 12% Packet Loss (tc netem):networking"
    "Git Bad Merge (SenderCompID overwritten):git"
    "Support: Stale NVDA Quotes (silent exception):support"
    "Interview: Real-Time P&L System Design:interview"
    "Dark Pool: TRF Reporting Delay Violation:darkpool"
    "Kubernetes: Pod CrashLoopBackOff (OOM):kubernetes"
    "Market Data: Feed Gap / Stale Prices:marketdata"
    "AWS: IAM Permission Denied on S3:aws"
    "Compliance: Pre-Trade Risk Limit Breach:compliance"
    "Airflow: DAG Failure in EOD Pipeline:airflow"
    "Database: Slow Query / Lock Contention:database"
    "Monitoring: Alert Storm (PagerDuty flood):monitoring"
    "CI/CD: Failed Deploy, Rollback Needed:cicd"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GRN='\033[0;32m'
YLW='\033[0;33m'
CYN='\033[0;36m'
BLD='\033[1m'
RST='\033[0m'

print_header() {
    clear
    echo -e "${BLD}${CYN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║         Trading Infrastructure Support — Scenario Lab        ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${RST}"
}

print_menu() {
    print_header
    echo -e "${BLD}Available Scenarios:${RST}"
    echo ""
    local i=1
    for entry in "${SCENARIO_LIST[@]}"; do
        name="${entry%%:*}"
        dir="${entry##*:}"
        # Check if the scenario directory exists and has a setup.sh
        if [ -f "$SCENARIOS_DIR/$dir/setup.sh" ]; then
            marker="${GRN}[available]${RST}"
        else
            marker="${YLW}[not deployed]${RST}"
        fi
        printf "  ${BLD}%2d.${RST} %-50s %b\n" "$i" "$name" "$marker"
        i=$((i + 1))
    done
    echo ""
    echo -e "   ${BLD}0.${RST} Exit"
    echo ""
}

action_menu() {
    local scenario_name="$1"
    local dir="$2"
    echo ""
    echo -e "${BLD}Scenario: ${CYN}${scenario_name}${RST}"
    echo ""
    echo "  1. Setup   — inject the broken state, start background services"
    echo "  2. Reset   — tear down and clean up"
    echo "  3. Back"
    echo ""
    printf "Choice [1/2/3]: "
}

run_scenario() {
    local action="$1"
    local dir="$2"
    local script="$SCENARIOS_DIR/$dir/${action}.sh"

    if [ ! -f "$script" ]; then
        echo -e "${RED}ERROR: $script not found.${RST}"
        echo "Has this scenario been deployed? Run deploy.sh from Windows Git Bash."
        echo ""
        printf "Press Enter to continue..."
        read -r
        return
    fi

    echo ""
    echo -e "${YLW}Running: bash $script${RST}"
    echo "────────────────────────────────────────────────────────────────"
    bash "$script"
    echo "────────────────────────────────────────────────────────────────"
    echo ""
    printf "Press Enter to return to menu..."
    read -r
}

# ---------------------------------------------------------------------------
# Try whiptail first; fall back to plain read
# ---------------------------------------------------------------------------
use_whiptail=false
if command -v whiptail &>/dev/null; then
    use_whiptail=true
fi

whiptail_main_menu() {
    local items=()
    local i=1
    for entry in "${SCENARIO_LIST[@]}"; do
        name="${entry%%:*}"
        items+=("$i" "$name")
        i=$((i + 1))
    done

    CHOICE=$(whiptail --title "Trading Support Lab" \
        --menu "Select a scenario:" 24 72 16 \
        "${items[@]}" \
        3>&1 1>&2 2>&3)

    echo "$CHOICE"
}

whiptail_action_menu() {
    local scenario_name="$1"
    ACTION=$(whiptail --title "$scenario_name" \
        --menu "Choose action:" 12 60 3 \
        "1" "Setup — inject broken state" \
        "2" "Reset — clean up" \
        3>&1 1>&2 2>&3)
    echo "$ACTION"
}

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
while true; do
    if [ "$use_whiptail" = "true" ]; then
        # Whiptail path
        CHOICE=$(whiptail_main_menu)
        if [ -z "$CHOICE" ] || [ "$CHOICE" = "0" ]; then
            echo "Goodbye."
            exit 0
        fi

        idx=$((CHOICE - 1))
        if [ "$idx" -lt 0 ] || [ "$idx" -ge "${#SCENARIO_LIST[@]}" ]; then
            continue
        fi

        entry="${SCENARIO_LIST[$idx]}"
        name="${entry%%:*}"
        dir="${entry##*:}"

        ACTION=$(whiptail_action_menu "$name")
        case "$ACTION" in
            1) run_scenario "setup" "$dir" ;;
            2) run_scenario "reset" "$dir" ;;
            *) continue ;;
        esac

    else
        # Plain terminal fallback
        print_menu
        printf "Select scenario [0-${#SCENARIO_LIST[@]}]: "
        read -r CHOICE

        if [ -z "$CHOICE" ] || [ "$CHOICE" = "0" ]; then
            echo "Goodbye."
            exit 0
        fi

        # Validate numeric input
        if ! [[ "$CHOICE" =~ ^[0-9]+$ ]]; then
            echo -e "${RED}Invalid choice.${RST}"
            sleep 1
            continue
        fi

        idx=$((CHOICE - 1))
        if [ "$idx" -lt 0 ] || [ "$idx" -ge "${#SCENARIO_LIST[@]}" ]; then
            echo -e "${RED}Invalid scenario number.${RST}"
            sleep 1
            continue
        fi

        entry="${SCENARIO_LIST[$idx]}"
        name="${entry%%:*}"
        dir="${entry##*:}"

        action_menu "$name" "$dir"
        read -r ACTION

        case "$ACTION" in
            1) run_scenario "setup" "$dir" ;;
            2) run_scenario "reset" "$dir" ;;
            3|*) continue ;;
        esac
    fi
done
