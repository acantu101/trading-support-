#!/bin/bash
# k8s/verify.sh — Verify fix for CrashLoopBackOff / empty ConfigMap scenario
source "$(dirname "$0")/../_lib/common.sh"

banner "K8s Scenario: Verify Fix"

CONFIGMAP="$HOME/trading-support/k8s/configs/order-router-config.yaml"

# ── Check the ConfigMap ───────────────────────────────────────────────────────
if [ ! -f "$CONFIGMAP" ]; then
  err "ConfigMap file not found: $CONFIGMAP"
  err "Did you run setup.sh first?"
  exit 1
fi

# Extract ORDER_GATEWAY_HOST value — handles both quoted and unquoted forms
GW_HOST=$(python3 -c "
import sys, re
text = open('$CONFIGMAP').read()
# Match:  ORDER_GATEWAY_HOST: \"value\"  or  ORDER_GATEWAY_HOST: value
m = re.search(r'ORDER_GATEWAY_HOST:\s*[\"\'']?([^\"\''\n]+)[\"\'']?', text)
if m:
    val = m.group(1).strip().strip('\"').strip(\"'\")
    print(val)
" 2>/dev/null)

# ── Not fixed branch ──────────────────────────────────────────────────────────
if [ -z "$GW_HOST" ]; then
  echo ""
  err "Pod will keep crashing — ORDER_GATEWAY_HOST is still empty."
  err "The container process exits immediately when it can't resolve"
  err "the gateway address."
  echo ""
  info "Current ConfigMap value:"
  grep "ORDER_GATEWAY_HOST" "$CONFIGMAP" | sed 's/^/    /'
  echo ""
  step "Nudge: the pod log says 'FATAL: ORDER_GATEWAY_HOST is empty'."
  step "       Edit $CONFIGMAP and set ORDER_GATEWAY_HOST to a"
  step "       non-empty hostname (e.g. exchange-gw.prod.local), then"
  step "       apply it with: kubectl apply -f $CONFIGMAP"
  echo ""
  exit 1
fi

# ── Fixed branch — simulate pod recovery ────────────────────────────────────
ok "ORDER_GATEWAY_HOST=\"${GW_HOST}\" — ConfigMap is populated."
echo ""

POD="order-router-7f9d8b-xk2vp"
NS="trading-ns"

step "Applying updated ConfigMap to cluster..."
sleep 0.3
echo -e "    ${CYAN}configmap/order-router-config configured${NC}"
sleep 0.3

# ── kubectl get pods: 3 state transitions ────────────────────────────────────
_kubectl_table() {
  local name="$1" ready="$2" status="$3" restarts="$4" age="$5"
  echo ""
  echo -e "${BOLD}${CYAN}>>> kubectl get pods -n ${NS}${NC}"
  echo ""
  printf "${BOLD}%-42s %-6s %-22s %-10s %s${NC}\n" \
    "NAME" "READY" "STATUS" "RESTARTS" "AGE"
  printf "%-42s %-6s %-22s %-10s %s\n" \
    "$name" "$ready" "$status" "$restarts" "$age"
  echo ""
}

step "Pod transitioning: Terminating..."
sleep 0.3
_kubectl_table "$POD" "0/1" "Terminating" "5" "14m"
sleep 0.3

step "Pod transitioning: ContainerCreating..."
sleep 0.3
_kubectl_table "$POD" "0/1" "ContainerCreating" "0" "4s"
sleep 0.3

step "Pod transitioning: Running..."
sleep 0.3
_kubectl_table "$POD" "1/1" "Running" "0" "8s"
sleep 0.3

ok "Pod is Running and Ready (1/1)."
echo ""

# ── kubectl logs showing healthy startup ──────────────────────────────────────
NOW=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
echo -e "${BOLD}${CYAN}>>> kubectl logs ${POD} -n ${NS}${NC}"
echo ""
sleep 0.3
echo "2026-05-04T08:10:00Z [INFO]  order-router v2.4.1 starting..."
sleep 0.3
echo "2026-05-04T08:10:00Z [INFO]  Loading configuration from ConfigMap: order-router-config"
sleep 0.3
echo "2026-05-04T08:10:00Z [INFO]  ORDER_GATEWAY_HOST=${GW_HOST}"
sleep 0.3
echo "2026-05-04T08:10:00Z [INFO]  ORDER_GATEWAY_PORT=9878"
sleep 0.3
echo "2026-05-04T08:10:00Z [INFO]  LOG_LEVEL=DEBUG"
sleep 0.3
echo "2026-05-04T08:10:00Z [INFO]  MAX_RETRIES=3"
sleep 0.3
echo "2026-05-04T08:10:00Z [INFO]  Connecting to ${GW_HOST}:9878..."
sleep 0.3
echo "2026-05-04T08:10:01Z [INFO]  TCP connection established"
sleep 0.3
echo "2026-05-04T08:10:01Z [INFO]  Connected."
sleep 0.3
echo "2026-05-04T08:10:01Z [INFO]  FIX session established. SenderCompID=PROD-OMS TargetCompID=EXCHANGE"
sleep 0.3
echo "2026-05-04T08:10:01Z [INFO]  Logon sent. Awaiting acknowledgment..."
sleep 0.3
echo "2026-05-04T08:10:01Z [INFO]  Logon ACK received. Session active."
sleep 0.3
echo "2026-05-04T08:10:01Z [INFO]  Heartbeat interval: 30s. Ready to route orders."
sleep 0.3
echo ""
ok "FIX session established. Order router is healthy."
echo ""

# ── SCENARIO COMPLETE summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${GREEN}║          SCENARIO COMPLETE — K8s CrashLoopBackOff           ║${NC}"
echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}${CYAN}1. What you diagnosed${NC}"
echo "   The order-router pod was stuck in CrashLoopBackOff with restartCount=5."
echo "   kubectl logs revealed: 'FATAL: ORDER_GATEWAY_HOST is empty'."
echo "   kubectl get configmap showed the ConfigMap had ORDER_GATEWAY_HOST: \"\""
echo "   — an empty string. The container tried to resolve an empty hostname,"
echo "   failed immediately, and exited with code 1. Kubernetes kept restarting"
echo "   it with exponential back-off (10s → 20s → 40s → 5m)."
echo ""

echo -e "${BOLD}${CYAN}2. What you fixed${NC}"
echo "   Set ORDER_GATEWAY_HOST=\"${GW_HOST}\" in:"
echo "   $CONFIGMAP"
echo "   Applied via: kubectl apply -f <configmap>"
echo "   The pod restarted, resolved the gateway hostname, established a FIX"
echo "   session, and entered Running/Ready state."
echo ""

echo -e "${BOLD}${CYAN}3. Real-world context${NC}"
echo "   CrashLoopBackOff from bad configuration is one of the most common"
echo "   Kubernetes incidents in trading environments. The failure pattern is:"
echo "     1. ConfigMap deployed with a missing or wrong value"
echo "     2. Container process validates config on startup and exits"
echo "     3. Kubernetes retries with back-off, masking the fast failure"
echo "     4. By the time someone notices, the pod is 5-minute back-off"
echo "   In trading, a crashed order router during market hours = no order flow."
echo ""
echo "   Rollback strategies:"
echo "   - kubectl rollout undo deployment/order-router  (rolls back pod spec)"
echo "   - kubectl apply -f <previous-configmap.yaml>   (fixes config directly)"
echo "   - GitOps: revert the ConfigMap commit in git and let ArgoCD sync"
echo ""

echo -e "${BOLD}${CYAN}4. How to prevent it in production${NC}"
echo "   a) Readiness probes: configure a readinessProbe that checks gateway"
echo "      reachability. Kubernetes won't route traffic until the probe passes,"
echo "      and a failing probe triggers alerts before orders are affected."
echo "   b) Config validation CI: add a job that renders ConfigMaps and checks"
echo "      for empty required fields before merge."
echo "   c) Use Kubernetes Secrets or external secret managers (Vault, AWS SSM)"
echo "      for hostnames that differ per environment — makes empty-string"
echo "      mistakes more visible."
echo "   d) Set terminationMessagePolicy: FallbackToLogsOnError so crash"
echo "      messages appear in 'kubectl describe pod' without needing logs."
echo "   e) Alert on restartCount > 2 for any trading-critical pod."
echo ""
