#!/bin/bash
# k8s/setup.sh — Pod CrashLoopBackOff due to bad ConfigMap scenario
source "$(dirname "$0")/../_lib/common.sh"

banner "K8s Scenario: CrashLoopBackOff (Bad ConfigMap)"
ensure_dirs

K8S_DIR="$HOME/trading-support/k8s"

# ── Directories ──────────────────────────────────────────────────────────────
step "Creating K8s scenario directories..."
mkdir -p "$K8S_DIR/pods" "$K8S_DIR/configs" "$K8S_DIR/logs" "$K8S_DIR/bin"
ok "Directories ready: $K8S_DIR"

# ── Broken ConfigMap YAML ────────────────────────────────────────────────────
step "Writing broken ConfigMap (ORDER_GATEWAY_HOST is empty)..."
cat > "$K8S_DIR/configs/order-router-config.yaml" << 'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: order-router-config
  namespace: trading-ns
  labels:
    app: order-router
    env: prod
data:
  ORDER_GATEWAY_HOST: ""
  ORDER_GATEWAY_PORT: "9878"
  LOG_LEVEL: "DEBUG"
  MAX_RETRIES: "3"
  HEARTBEAT_INTERVAL: "30"
  SESSION_ID: "PROD-OMS"
EOF
ok "order-router-config.yaml written (ORDER_GATEWAY_HOST is empty)"

# ── Pod state JSON ────────────────────────────────────────────────────────────
step "Writing pod state JSON (CrashLoopBackOff, restartCount=5)..."
cat > "$K8S_DIR/pods/order-router-7f9d8b-xk2vp.json" << 'EOF'
{
  "apiVersion": "v1",
  "kind": "Pod",
  "metadata": {
    "name": "order-router-7f9d8b-xk2vp",
    "namespace": "trading-ns",
    "labels": {
      "app": "order-router",
      "pod-template-hash": "7f9d8b"
    },
    "annotations": {
      "kubectl.kubernetes.io/last-applied-configuration": ""
    }
  },
  "spec": {
    "containers": [
      {
        "name": "order-router",
        "image": "trading/order-router:2.4.1",
        "envFrom": [
          { "configMapRef": { "name": "order-router-config" } }
        ],
        "resources": {
          "requests": { "cpu": "250m", "memory": "256Mi" },
          "limits":   { "cpu": "500m", "memory": "512Mi" }
        }
      }
    ],
    "restartPolicy": "Always"
  },
  "status": {
    "phase": "Running",
    "conditions": [
      { "type": "Ready", "status": "False", "reason": "ContainersNotReady" }
    ],
    "containerStatuses": [
      {
        "name": "order-router",
        "ready": false,
        "restartCount": 5,
        "state": {
          "waiting": {
            "reason": "CrashLoopBackOff",
            "message": "back-off 5m0s restarting failed container=order-router"
          }
        },
        "lastState": {
          "terminated": {
            "exitCode": 1,
            "reason": "Error",
            "message": "FATAL: ORDER_GATEWAY_HOST is empty — cannot connect to exchange",
            "startedAt": "2026-05-04T08:00:00Z",
            "finishedAt": "2026-05-04T08:00:01Z"
          }
        },
        "image": "trading/order-router:2.4.1",
        "imageID": "docker-pullable://trading/order-router@sha256:a1b2c3d4e5f6"
      }
    ]
  }
}
EOF
ok "Pod state JSON written"

# ── Crash log ────────────────────────────────────────────────────────────────
step "Writing crash log (5 crash cycles)..."
cat > "$K8S_DIR/logs/order-router-crash.log" << 'EOF'
2026-05-04T07:55:00Z [INFO]  order-router v2.4.1 starting...
2026-05-04T07:55:00Z [INFO]  Loading configuration from ConfigMap: order-router-config
2026-05-04T07:55:00Z [INFO]  ORDER_GATEWAY_PORT=9878
2026-05-04T07:55:00Z [INFO]  LOG_LEVEL=DEBUG
2026-05-04T07:55:00Z [FATAL] ORDER_GATEWAY_HOST is empty — cannot connect to exchange
2026-05-04T07:55:00Z [FATAL] Process exited with code 1

2026-05-04T07:55:10Z [INFO]  order-router v2.4.1 starting... (restart #1)
2026-05-04T07:55:10Z [INFO]  Loading configuration from ConfigMap: order-router-config
2026-05-04T07:55:10Z [INFO]  ORDER_GATEWAY_PORT=9878
2026-05-04T07:55:10Z [INFO]  LOG_LEVEL=DEBUG
2026-05-04T07:55:10Z [FATAL] ORDER_GATEWAY_HOST is empty — cannot connect to exchange
2026-05-04T07:55:10Z [FATAL] Process exited with code 1

2026-05-04T07:55:30Z [INFO]  order-router v2.4.1 starting... (restart #2)
2026-05-04T07:55:30Z [INFO]  Loading configuration from ConfigMap: order-router-config
2026-05-04T07:55:30Z [INFO]  ORDER_GATEWAY_PORT=9878
2026-05-04T07:55:30Z [INFO]  LOG_LEVEL=DEBUG
2026-05-04T07:55:30Z [FATAL] ORDER_GATEWAY_HOST is empty — cannot connect to exchange
2026-05-04T07:55:30Z [FATAL] Process exited with code 1

2026-05-04T07:56:10Z [INFO]  order-router v2.4.1 starting... (restart #3)
2026-05-04T07:56:10Z [INFO]  Loading configuration from ConfigMap: order-router-config
2026-05-04T07:56:10Z [INFO]  ORDER_GATEWAY_PORT=9878
2026-05-04T07:56:10Z [INFO]  LOG_LEVEL=DEBUG
2026-05-04T07:56:10Z [FATAL] ORDER_GATEWAY_HOST is empty — cannot connect to exchange
2026-05-04T07:56:10Z [FATAL] Process exited with code 1

2026-05-04T07:57:30Z [INFO]  order-router v2.4.1 starting... (restart #4)
2026-05-04T07:57:30Z [INFO]  Loading configuration from ConfigMap: order-router-config
2026-05-04T07:57:30Z [INFO]  ORDER_GATEWAY_PORT=9878
2026-05-04T07:57:30Z [INFO]  LOG_LEVEL=DEBUG
2026-05-04T07:57:30Z [FATAL] ORDER_GATEWAY_HOST is empty — cannot connect to exchange
2026-05-04T07:57:30Z [FATAL] Process exited with code 1

2026-05-04T08:00:00Z [INFO]  order-router v2.4.1 starting... (restart #5)
2026-05-04T08:00:00Z [INFO]  Loading configuration from ConfigMap: order-router-config
2026-05-04T08:00:00Z [INFO]  ORDER_GATEWAY_PORT=9878
2026-05-04T08:00:00Z [INFO]  LOG_LEVEL=DEBUG
2026-05-04T08:00:00Z [FATAL] ORDER_GATEWAY_HOST is empty — cannot connect to exchange
2026-05-04T08:00:01Z [FATAL] Process exited with code 1
EOF
ok "order-router-crash.log written"

# ── Simulated kubectl wrapper ────────────────────────────────────────────────
step "Writing bin/kubectl wrapper..."
cat > "$K8S_DIR/bin/kubectl" << 'KUBECTLEOF'
#!/bin/bash
# Simulated kubectl — handles key trading-support K8s scenario commands.

K8S_DIR="$HOME/trading-support/k8s"
POD_NAME="order-router-7f9d8b-xk2vp"
POD_JSON="$K8S_DIR/pods/${POD_NAME}.json"
CONFIGMAP_FILE="$K8S_DIR/configs/order-router-config.yaml"
CRASH_LOG="$K8S_DIR/logs/order-router-crash.log"

# Determine current pod status by reading the configmap on disk
_pod_status() {
    local gw_host
    gw_host=$(grep "ORDER_GATEWAY_HOST:" "$CONFIGMAP_FILE" 2>/dev/null | awk -F'"' '{print $2}')
    if [ -n "$gw_host" ]; then
        echo "Running"
    else
        echo "CrashLoopBackOff"
    fi
}

_pod_restarts() {
    # Count how many times the scenario has been "fixed" vs initial 5
    grep -c "FATAL" "$CRASH_LOG" 2>/dev/null || echo "5"
}

CMD="$1"
SUBCMD="$2"

# ── kubectl get pods ─────────────────────────────────────────────────────────
if [ "$CMD" = "get" ] && [ "$SUBCMD" = "pods" ]; then
    STATUS=$(_pod_status)
    if [ "$STATUS" = "Running" ]; then
        READY="1/1"
        RESTARTS="5"
        STATUS_DISP="Running"
    else
        READY="0/1"
        RESTARTS="5 (back-off 5m)"
        STATUS_DISP="CrashLoopBackOff"
    fi
    printf "\n%-42s %-6s %-22s %-10s %s\n" "NAME" "READY" "STATUS" "RESTARTS" "AGE"
    printf "%-42s %-6s %-22s %-10s %s\n" \
        "$POD_NAME" "$READY" "$STATUS_DISP" "$RESTARTS" "12m"
    echo ""
    exit 0
fi

# ── kubectl logs <pod> ────────────────────────────────────────────────────────
if [ "$CMD" = "logs" ] && [ "$SUBCMD" = "$POD_NAME" ]; then
    cat "$CRASH_LOG"
    exit 0
fi

# ── kubectl describe pod <pod> ────────────────────────────────────────────────
if [ "$CMD" = "describe" ] && [ "$SUBCMD" = "pod" ]; then
    STATUS=$(_pod_status)
    cat << DESCEOF

Name:         $POD_NAME
Namespace:    trading-ns
Node:         worker-node-02/10.0.1.12
Start Time:   Mon, 04 May 2026 07:55:00 +0000
Labels:       app=order-router
              pod-template-hash=7f9d8b
Status:       Running
IP:           172.16.0.45

Containers:
  order-router:
    Image:      trading/order-router:2.4.1
    Port:       <none>
    State:      Waiting
      Reason:   CrashLoopBackOff
    Last State: Terminated
      Reason:   Error
      Exit Code: 1
      Started:   Mon, 04 May 2026 08:00:00 +0000
      Finished:  Mon, 04 May 2026 08:00:01 +0000
    Ready:      False
    Restart Count: 5
    Environment Variables from:
      order-router-config  ConfigMap  Optional: false
    Resource Limits:
      cpu:     500m
      memory:  512Mi

Conditions:
  Type           Status
  Ready          False
  ContainersReady False

Events:
  Type     Reason     Age                From               Message
  ----     ------     ----               ----               -------
  Warning  BackOff    2m (x5 over 12m)  kubelet            Back-off restarting failed container
  Normal   Pulled     12m               kubelet            Successfully pulled image "trading/order-router:2.4.1"
  Normal   Created    12m               kubelet            Created container order-router
  Normal   Started    12m               kubelet            Started container order-router

DESCEOF
    exit 0
fi

# ── kubectl get configmap ────────────────────────────────────────────────────
if [ "$CMD" = "get" ] && [ "$SUBCMD" = "configmap" ]; then
    cat "$CONFIGMAP_FILE"
    exit 0
fi

# ── kubectl apply -f <file> ──────────────────────────────────────────────────
if [ "$CMD" = "apply" ] && [ "$SUBCMD" = "-f" ]; then
    APPLY_FILE="$3"
    if [ ! -f "$APPLY_FILE" ]; then
        echo "error: the path \"$APPLY_FILE\" does not exist" >&2
        exit 1
    fi

    # Copy file into configs location
    cp "$APPLY_FILE" "$CONFIGMAP_FILE"

    # Check if the fix was applied
    GW_HOST=$(grep "ORDER_GATEWAY_HOST:" "$CONFIGMAP_FILE" | awk -F'"' '{print $2}')
    if [ -n "$GW_HOST" ]; then
        echo "configmap/order-router-config configured"
        echo ""
        echo "  Restarting pod with updated ConfigMap..."
        echo "  ORDER_GATEWAY_HOST=$GW_HOST — connection target set"
        echo ""
        # Update pod JSON status to Running
        python3 - "$POD_JSON" << 'PYEOF'
import json, sys
path = sys.argv[1]
with open(path) as f:
    pod = json.load(f)
pod["status"]["phase"] = "Running"
pod["status"]["conditions"][0]["status"] = "True"
pod["status"]["conditions"][0]["reason"] = "PodCompleted"
cs = pod["status"]["containerStatuses"][0]
cs["ready"] = True
cs["restartCount"] = 5
cs["state"] = {"running": {"startedAt": "2026-05-04T08:05:00Z"}}
with open(path, "w") as f:
    json.dump(pod, f, indent=2)
PYEOF
        echo "  Pod order-router-7f9d8b-xk2vp is now Running"
    else
        echo "configmap/order-router-config configured"
        echo ""
        echo "  WARNING: ORDER_GATEWAY_HOST is still empty — pod will remain in CrashLoopBackOff"
    fi
    exit 0
fi

# ── Fallback: real kubectl if available ──────────────────────────────────────
if command -v /usr/bin/kubectl &>/dev/null; then
    /usr/bin/kubectl "$@"
else
    echo "kubectl: command '$CMD $SUBCMD' not handled by scenario wrapper and real kubectl not found" >&2
    exit 1
fi
KUBECTLEOF
chmod +x "$K8S_DIR/bin/kubectl"
ok "bin/kubectl wrapper written and marked executable"

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  SCENARIO READY — K8s CrashLoopBackOff${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
info "Add the simulated kubectl to your PATH:"
echo -e "    ${BOLD}export PATH=\"$K8S_DIR/bin:\$PATH\"${NC}"
echo ""
info "Start investigating:"
echo -e "    ${BOLD}kubectl get pods -n trading-ns${NC}"
echo -e "    ${BOLD}kubectl logs $POD_NAME -n trading-ns${NC}"
echo -e "    ${BOLD}kubectl describe pod $POD_NAME -n trading-ns${NC}"
echo -e "    ${BOLD}kubectl get configmap order-router-config -n trading-ns -o yaml${NC}"
echo ""
info "Fix: edit the ConfigMap to set ORDER_GATEWAY_HOST=\"exchange-gw.prod.local\" and apply:"
echo -e "    ${BOLD}kubectl apply -f $K8S_DIR/configs/order-router-config.yaml${NC}"
echo ""
warn "Pod order-router-7f9d8b-xk2vp is in CrashLoopBackOff. Investigate the ConfigMap."
echo ""
