#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Kubernetes & ArgoCD Setup
==========================================================
Creates realistic K8s manifests, pod logs, ArgoCD configs, and
diagnostic scripts for all K8s/ArgoCD scenarios (K8-01 to K8-06).
No real cluster needed — all manifests and logs are file-based.

Run with: python3 lab_k8s.py [--scenario N] [--teardown]

SCENARIOS:
  1   K8-01  CrashLoopBackOff — pod logs + missing secret
  2   K8-02  Rolling deployment rollback — manifests + history
  3   K8-03  Pod stuck Pending / ImagePullBackOff
  4   K8-04  ArgoCD rollback + disable auto-sync
  5   K8-05  Validate a release before syncing to prod
  6   K8-06  Behavioral — K8s story + stats
  99         ALL scenarios
"""

import os, shutil, argparse
from pathlib import Path
from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    create_dirs as _create_dirs, remove_lab_dir,
)

LAB_ROOT = Path("/tmp/lab_k8s")
DIRS = {
    "manifests": LAB_ROOT / "manifests",
    "logs":      LAB_ROOT / "logs",
    "scripts":   LAB_ROOT / "scripts",
    "argocd":    LAB_ROOT / "argocd",
}

def create_dirs(): _create_dirs(DIRS)

def write(path: Path, text: str) -> Path:
    path.write_text(text)
    ok(str(path).replace(str(LAB_ROOT) + "/", ""))
    return path


# ══════════════════════════════════════════════
#  SCENARIO 1 — CrashLoopBackOff
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario K8-01 — CrashLoopBackOff")
    print("  risk-engine pod is in CrashLoopBackOff after a deploy.\n")

    write(DIRS["logs"] / "pod-describe.txt", """\
Name:         risk-engine-7d9b8c-xk2p9
Namespace:    trading
Node:         k8s-worker-2/10.0.1.52
Status:       Running

Containers:
  risk-engine:
    Image:        trading-registry.internal/risk-engine:2.5.1
    State:        Waiting
      Reason:     CrashLoopBackOff
    Last State:   Terminated
      Reason:     Error
      Exit Code:  1
    Restart Count: 5
    Environment:
      DB_HOST:      db-primary.trading.internal
      DB_PASSWORD:  <set to key 'password' in secret 'risk-engine-db-secret'>  Optional: false

Events:
  Warning  BackOff  5m  kubelet  Back-off restarting failed container
  Warning  BackOff  3m  kubelet  Back-off restarting failed container
  Warning  BackOff  1m  kubelet  Back-off restarting failed container
""")

    write(DIRS["logs"] / "pod-logs-previous.txt", """\
2024-01-15T09:35:42Z INFO  Risk Engine v2.5.1 starting...
2024-01-15T09:35:42Z INFO  Loading config from /etc/risk-engine/config.yaml
2024-01-15T09:35:42Z INFO  Connecting to PostgreSQL db-primary.trading.internal:5432
2024-01-15T09:35:42Z ERROR Failed to retrieve secret 'risk-engine-db-secret': secret not found in namespace 'trading'
2024-01-15T09:35:42Z ERROR Cannot load DB_PASSWORD — refusing to start without credentials
2024-01-15T09:35:43Z FATAL Startup failed. Exit code 1.
""")

    write(DIRS["scripts"] / "k8s01_fix_crashloop.sh", f"""\
#!/bin/bash
# K8-01: CrashLoopBackOff Diagnosis & Fix

echo "=== Step 1: Check pod status ==="
# kubectl get pods -n trading
# Look for: STATUS=CrashLoopBackOff, RESTARTS > 0

echo "=== Step 2: Read crash logs (--previous is critical) ==="
cat {DIRS["logs"]}/pod-logs-previous.txt
# On real cluster:
# kubectl logs -n trading <pod-name> --previous

echo "=== Step 3: Describe pod ==="
cat {DIRS["logs"]}/pod-describe.txt
# kubectl describe pod -n trading <pod-name>
# Check: State, Exit Code, Events, Environment vars

echo ""
echo "=== ROOT CAUSE: Missing Kubernetes Secret ==="
echo "  Error: 'risk-engine-db-secret' not found in namespace trading"
echo "  Pod can't read DB_PASSWORD → refuses to start"

echo ""
echo "=== FIX ==="
echo "  # Create the missing secret:"
echo "  kubectl create secret generic risk-engine-db-secret \\"
echo "    --from-literal=password='<db_password>' \\"
echo "    -n trading"
echo ""
echo "  # Verify it exists:"
echo "  kubectl get secret -n trading | grep risk-engine"
echo ""
echo "  # Delete pod so deployment recreates it:"
echo "  kubectl delete pod -n trading <pod-name>"
echo "  kubectl get pods -n trading -w"

echo ""
echo "=== Exit code cheat sheet ==="
echo "  Exit 1   = application error (check logs)"
echo "  Exit 137 = OOMKilled (increase memory limit)"
echo "  Exit 139 = SIGSEGV / segfault (app bug)"
""")

    print(f"""
{BOLD}── Artifacts ────────────────────────────────────────────{RESET}
{CYAN}  cat {DIRS["logs"]}/pod-logs-previous.txt    # crash reason
  cat {DIRS["logs"]}/pod-describe.txt          # full pod state
  cat {DIRS["scripts"]}/k8s01_fix_crashloop.sh # fix playbook{RESET}

{BOLD}── Root cause ───────────────────────────────────────────{RESET}
  Missing Secret 'risk-engine-db-secret'.
  Always read --previous logs first — current container may not
  have output yet when CrashLoopBackOff is active.

{BOLD}── Triage checklist ─────────────────────────────────────{RESET}
  1. kubectl logs --previous          (crash message)
  2. kubectl describe pod             (events + env vars)
  3. Exit 1 = app error   137 = OOM   139 = SIGSEGV
  4. Check: missing Secret, missing ConfigMap, wrong image tag
""")


# ══════════════════════════════════════════════
#  SCENARIO 2 — Rolling Deployment Rollback
# ══════════════════════════════════════════════

def launch_scenario_2():
    header("Scenario K8-02 — Rolling Deployment Rollback")
    print("  Bad deploy causing errors. Roll back to last good version.\n")

    write(DIRS["manifests"] / "market-data-processor.yaml", """\
apiVersion: apps/v1
kind: Deployment
metadata:
  name: market-data-processor
  namespace: trading
  annotations:
    deployment.kubernetes.io/revision: "4"
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    spec:
      containers:
      - name: market-data-processor
        image: trading-registry.internal/market-data-processor:2.6.0-BAD
        resources:
          requests:
            cpu: 200m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 512Mi
        livenessProbe:
          httpGet:
            path: /healthz
            port: 8080
          initialDelaySeconds: 30
""")

    write(DIRS["logs"] / "rollout-history.txt", """\
# kubectl rollout history deployment/market-data-processor -n trading
REVISION  CHANGE-CAUSE
1         Deploy v2.4.0 — initial release
2         Deploy v2.5.0 — add latency metrics
3         Deploy v2.5.1 — hotfix AAPL price feed   ← LAST KNOWN GOOD
4         Deploy v2.6.0 — new routing algorithm     ← CURRENT (BAD)
""")

    write(DIRS["scripts"] / "k8s02_rollback.sh", f"""\
#!/bin/bash
# K8-02: Rolling Deployment Rollback

NAMESPACE="trading"
DEPLOYMENT="market-data-processor"

echo "=== Current rollout history ==="
cat {DIRS["logs"]}/rollout-history.txt

echo ""
echo "=== Option A: Roll back one step (to revision 3) ==="
echo "  kubectl rollout undo deployment/$DEPLOYMENT -n $NAMESPACE"

echo ""
echo "=== Option B: Roll back to a specific revision ==="
echo "  kubectl rollout undo deployment/$DEPLOYMENT -n $NAMESPACE --to-revision=3"

echo ""
echo "=== Watch the rollback ==="
echo "  kubectl rollout status deployment/$DEPLOYMENT -n $NAMESPACE --watch"
echo "  # Wait for: 'successfully rolled out'"

echo ""
echo "=== Verify ==="
echo "  kubectl get pods -n $NAMESPACE"
echo "  # All pods: Running, RESTARTS=0"
echo "  kubectl describe deployment/$DEPLOYMENT -n $NAMESPACE | grep Image:"
echo "  # Should show :2.5.1 not :2.6.0-BAD"

echo ""
echo "⚠  CRITICAL FOR ARGOCD CLUSTERS:"
echo "  kubectl rollout undo is OVERWRITTEN by ArgoCD on next sync."
echo "  In ArgoCD clusters → always use 'argocd app rollback' (see K8-04)."
""")

    print(f"""
{BOLD}── Artifacts ────────────────────────────────────────────{RESET}
{CYAN}  cat {DIRS["logs"]}/rollout-history.txt           # revision history
  cat {DIRS["manifests"]}/market-data-processor.yaml # bad deployment
  cat {DIRS["scripts"]}/k8s02_rollback.sh           # rollback steps{RESET}

{BOLD}── Key commands (real cluster) ─────────────────────────{RESET}
{CYAN}  kubectl rollout history deployment/market-data-processor -n trading
  kubectl rollout undo deployment/market-data-processor -n trading
  kubectl rollout undo deployment/market-data-processor -n trading --to-revision=3
  kubectl rollout status deployment/market-data-processor -n trading --watch{RESET}
""")


# ══════════════════════════════════════════════
#  SCENARIO 3 — Pod Stuck Pending
# ══════════════════════════════════════════════

def launch_scenario_3():
    header("Scenario K8-03 — Pod Stuck Pending / ImagePullBackOff")
    print("  New service stuck. Never reaches Running. Three failure modes.\n")

    write(DIRS["logs"] / "pending-no-resources.txt", """\
# kubectl describe pod new-service-abc -n trading — Events section:

Events:
  Warning  FailedScheduling  5m  default-scheduler
    0/3 nodes are available: 1 Insufficient cpu, 2 Insufficient memory.
    preemption: 0/3 nodes are available: 3 No preemption victims found.

ROOT CAUSE: Nodes exhausted. Pod resource requests exceed available capacity.
FIX:
  Option 1: Reduce resource requests in deployment spec
  Option 2: Scale up the node pool (add nodes)
  Option 3: kubectl top nodes  →  kubectl describe nodes | grep -A5 "Allocated"
""")

    write(DIRS["logs"] / "pending-imagepull.txt", """\
# kubectl describe pod new-service-def -n trading

State: Waiting
  Reason: ImagePullBackOff

Events:
  Normal   Pulling  3m  kubelet  Pulling image "trading-registry.internal/new-service:1.2.3"
  Warning  Failed   3m  kubelet  Failed to pull image: 401 Unauthorized
  Warning  BackOff  2m  kubelet  Back-off pulling image

ROOT CAUSE: Registry authentication failure.
FIX:
  kubectl create secret docker-registry regcred \\
    --docker-server=trading-registry.internal \\
    --docker-username=svc-k8s \\
    --docker-password=<token> \\
    -n trading
  Then add to deployment: imagePullSecrets: [{name: regcred}]
""")

    write(DIRS["logs"] / "pending-missing-configmap.txt", """\
# kubectl describe pod new-service-ghi -n trading

State: Waiting
  Reason: CreateContainerConfigError

Events:
  Warning  Failed  30s  kubelet  Error: configmap "new-service-config" not found

ROOT CAUSE: Deployment references a ConfigMap that was never created.
FIX:
  kubectl get configmap -n trading               # check what exists
  kubectl apply -f new-service-config.yaml       # create the missing CM
  kubectl delete pod <pod-name> -n trading       # pod recreates using CM
""")

    write(DIRS["scripts"] / "k8s03_triage.sh", f"""\
#!/bin/bash
# K8-03: Pending / ImagePull triage

echo "The Events section of 'kubectl describe pod' tells you everything."
echo "Read it BEFORE touching anything else."
echo ""

echo "=== Failure Mode 1: Insufficient Resources ==="
cat {DIRS["logs"]}/pending-no-resources.txt

echo ""
echo "=== Failure Mode 2: ImagePullBackOff (auth) ==="
cat {DIRS["logs"]}/pending-imagepull.txt

echo ""
echo "=== Failure Mode 3: Missing ConfigMap ==="
cat {DIRS["logs"]}/pending-missing-configmap.txt

echo ""
echo "=== Triage commands ==="
echo "  kubectl get pods -n trading                              # see status"
echo "  kubectl describe pod <name> -n trading                  # read Events"
echo "  kubectl top nodes                                        # resource headroom"
echo "  kubectl get pod <name> -n trading -o jsonpath='...image' # image name"
echo "  kubectl get configmap,secret -n trading                 # check dependencies"
""")

    print(f"""
{BOLD}── Three Pending failure modes ─────────────────────────{RESET}
{CYAN}  cat {DIRS["logs"]}/pending-no-resources.txt    # CPU/memory exhausted
  cat {DIRS["logs"]}/pending-imagepull.txt        # registry 401
  cat {DIRS["logs"]}/pending-missing-configmap.txt # missing ConfigMap
  cat {DIRS["scripts"]}/k8s03_triage.sh          # full triage guide{RESET}

{BOLD}── Pattern ──────────────────────────────────────────────{RESET}
  State: Pending                → scheduling (resources/taints/affinity)
  State: ImagePullBackOff       → image not found or registry auth
  State: CreateContainerConfig  → missing ConfigMap or Secret
  State: CrashLoopBackOff       → starts but exits immediately
""")


# ══════════════════════════════════════════════
#  SCENARIO 4 — ArgoCD Rollback
# ══════════════════════════════════════════════

def launch_scenario_4():
    header("Scenario K8-04 — ArgoCD Rollback + Sync Management")
    print("  Bad release via ArgoCD. App is Degraded. Roll back and\n"
          "  prevent ArgoCD from re-syncing back to the bad commit.\n")

    write(DIRS["argocd"] / "oms-engine-app.yaml", """\
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: oms-engine
  namespace: argocd
spec:
  project: trading
  source:
    repoURL: https://github.com/trading-firm/k8s-manifests
    targetRevision: HEAD
    path: apps/oms-engine
  destination:
    server: https://kubernetes.default.svc
    namespace: trading
  syncPolicy:
    automated:
      prune: true
      selfHeal: true    # ← ArgoCD will fight any kubectl rollback
""")

    write(DIRS["argocd"] / "oms-engine-history.txt", """\
# argocd app history oms-engine
ID   DATE                           REVISION
0    2024-01-10 09:00:12 +0000 UTC  a3f2c91  v2.4.0 — known good
1    2024-01-12 14:30:00 +0000 UTC  b7e4d82  v2.4.1 — patch
2    2024-01-15 09:15:00 +0000 UTC  c9a1e55  v2.5.0 — BAD DEPLOY ← current
""")

    write(DIRS["scripts"] / "k8s04_argocd_rollback.sh", f"""\
#!/bin/bash
# K8-04: ArgoCD Rollback + Sync Management
# ==========================================
# DO NOT use 'kubectl rollout undo' in ArgoCD-managed clusters.
# ArgoCD's selfHeal will re-sync back to bad Git HEAD in seconds.
# ALWAYS use ArgoCD to roll back.

APP="oms-engine"

echo "=== Step 1: Check app status ==="
echo "  argocd app get $APP"
echo "  # Look for: Health=Degraded, Sync=Synced (synced to bad commit)"
echo ""
echo "  argocd app list   # see all managed apps"

echo ""
echo "=== View revision history ==="
cat {DIRS["argocd"]}/oms-engine-history.txt

echo ""
echo "=== CRITICAL Step 2: Disable auto-sync FIRST ==="
echo "  argocd app set $APP --sync-policy none"
echo ""
echo "  Without this: ArgoCD detects drift → re-syncs → undoes your rollback."
echo "  Verify disabled:"
echo "  argocd app get $APP | grep 'Sync Policy'"

echo ""
echo "=== Step 3: Roll back ==="
echo "  # Roll back one step (to revision 1 = b7e4d82):"
echo "  argocd app rollback $APP"
echo ""
echo "  # Roll back to specific known-good revision:"
echo "  argocd app rollback $APP 0   # → a3f2c91 (v2.4.0)"

echo ""
echo "=== Step 4: Watch and verify ==="
echo "  argocd app wait $APP --health"
echo "  kubectl get pods -n trading"
echo "  kubectl describe deployment oms-engine -n trading | grep Image:"
echo "  # Should show old tag, not v2.5.0"

echo ""
echo "=== Step 5: Re-enable auto-sync after devs push a fix ==="
echo "  argocd app set $APP --sync-policy automated --auto-prune --self-heal"
echo "  argocd app sync $APP"
""")

    print(f"""
{BOLD}── Artifacts ────────────────────────────────────────────{RESET}
{CYAN}  cat {DIRS["argocd"]}/oms-engine-app.yaml       # app definition
  cat {DIRS["argocd"]}/oms-engine-history.txt    # revision history
  cat {DIRS["scripts"]}/k8s04_argocd_rollback.sh # rollback playbook{RESET}

{BOLD}── The most important rule ──────────────────────────────{RESET}
  DISABLE AUTO-SYNC BEFORE ROLLBACK.
  selfHeal=true means ArgoCD fights kubectl rollout undo immediately.
  argocd app rollback is git-aware and durable.

{BOLD}── UI approach (same steps) ─────────────────────────────{RESET}
  App Details → Summary → Sync Policy → Disable Auto-Sync
  History and Rollback → pick last good revision → Rollback
  Monitor pods → once healthy → re-enable Auto-Sync
""")


# ══════════════════════════════════════════════
#  SCENARIO 5 — Validate Before Prod Sync
# ══════════════════════════════════════════════

def launch_scenario_5():
    header("Scenario K8-05 — Validate a Release Before Syncing to Prod")
    print("  Developer asks you to release a new version. What do you check?\n")

    write(DIRS["argocd"] / "risk-engine-diff.txt", """\
# argocd app diff risk-engine
# Shows what WILL change if you sync now

===== Deployment/risk-engine (trading) =====
  spec.template.spec.containers[0]:
-   image: trading-registry.internal/risk-engine:2.5.1
+   image: trading-registry.internal/risk-engine:2.6.0
    resources.requests:
-     cpu: 500m
+     cpu: 750m       ← 50% increase — verify cluster headroom
-     memory: 512Mi
+     memory: 768Mi   ← 50% increase

# OBSERVATIONS BEFORE SYNCING:
# 1. Image 2.5.1 → 2.6.0 — matches the approved PR ticket
# 2. CPU +50%, memory +50% — run 'kubectl top nodes' to verify headroom
# 3. No config or secret changes — good, nothing else unexpected
""")

    write(DIRS["scripts"] / "k8s05_release_checklist.sh", f"""\
#!/bin/bash
# K8-05: Release Validation Checklist

APP="risk-engine"
NAMESPACE="trading"

echo "=== Pre-Release Checks ==="

echo "1. Review the diff"
cat {DIRS["argocd"]}/risk-engine-diff.txt
echo "   argocd app diff $APP   (on real cluster)"

echo ""
echo "2. Confirm image tag matches approved PR"
echo "   argocd app get $APP | grep 'Target Revision'"

echo ""
echo "3. Check cluster resource headroom (resource requests are increasing)"
echo "   kubectl top nodes"
echo "   kubectl describe nodes | grep -A5 'Allocated resources'"

echo ""
echo "4. Dry-run sync to validate manifests"
echo "   argocd app sync $APP --dry-run"

echo ""
echo "=== Sync & Monitor ==="
echo "5. Sync to prod"
echo "   argocd app sync $APP"

echo ""
echo "6. Watch progress"
echo "   argocd app wait $APP --health --timeout 120"
echo "   kubectl rollout status deployment/$APP -n $NAMESPACE"

echo ""
cat << 'EOF'
=== GO / NO-GO (2-minute window) ===

GO ✅ — all of these must be true:
  - All pods Running, RESTARTS=0 after 2 minutes
  - ArgoCD: Health=Healthy, Sync=Synced
  - kubectl top pods: CPU/memory within expected range
  - No error logs at startup
  - Liveness/readiness probes passing

NO-GO 🚫 — rollback immediately if any of these:
  - Any pod in CrashLoopBackOff
  - OOMKilled in Events (kubectl describe pod)
  - ArgoCD Health=Degraded
  - Trader-facing alerts triggered within 2 minutes
  - Latency spike in monitoring dashboard
EOF
""")

    print(f"""
{BOLD}── Artifacts ────────────────────────────────────────────{RESET}
{CYAN}  cat {DIRS["argocd"]}/risk-engine-diff.txt         # what will change
  cat {DIRS["scripts"]}/k8s05_release_checklist.sh   # full checklist{RESET}

{BOLD}── Key interview phrases ────────────────────────────────{RESET}
  "I always read the diff — not just the image tag.
   I caught an accidental config change this way once."

  "I use --dry-run to validate manifests before every prod sync."

  "My go/no-go window is 2 minutes. A bad deploy at 9:35
   is a live P&L incident."
""")


# ══════════════════════════════════════════════
#  SCENARIO 6 — Behavioral Story
# ══════════════════════════════════════════════

def launch_scenario_6():
    header("Scenario K8-06 — Tell Your K8s Story (Behavioral)")
    print("  Prepare your answer for 'Walk me through your K8s experience.'\n")

    write(DIRS["scripts"] / "k8s06_story_notes.md", """\
# K8-06: K8s Behavioral Answer Notes
======================================

## The Question
"Walk me through how you use Kubernetes and ArgoCD in your current role.
What's the most impactful deployment issue you've handled?"

## Model Answer

"At Granite Point I manage Kubernetes deployments for 60+ production
trading applications using ArgoCD. These include the OMS, risk engine,
market data processors, and FIX session handlers — services where
a bad deploy during market hours directly costs money.

My release process:
  1. Review the ArgoCD diff — confirm only expected changes are going out
  2. Validate image tag matches the approved commit / PR
  3. --dry-run sync to catch manifest errors before they hit prod
  4. Sync and monitor: argocd app wait, kubectl rollout status
  5. 2-minute go/no-go window — CrashLoopBackOff or Degraded → rollback

The most important lesson I learned: kubectl rollout undo doesn't work
in ArgoCD clusters. ArgoCD's selfHeal re-syncs to Git HEAD in seconds,
undoing your rollback. The correct procedure is:
  1. Disable auto-sync FIRST (argocd app set --sync-policy none)
  2. Use argocd app rollback, not kubectl
  3. Re-enable auto-sync only after devs push a clean fix to Git.

Over the past year that disciplined process reduced deployment-related
incidents by about 25%. We hold 99.4% uptime across 60+ apps during
a 27.5-hour/week zero-tolerance market window."

## Numbers to Say Out Loud
  → 60+ production trading applications
  → 25% reduction in deployment incidents
  → 99.4% uptime
  → 2-minute go/no-go window

## Traps to Avoid
  ✗ "I just click sync in the UI" (too passive — no process)
  ✗ "kubectl rollout undo" in ArgoCD context (shows you don't know ArgoCD)
  ✓ "I review the diff before every sync"
  ✓ "I disable auto-sync before rolling back"
  ✓ Connect every decision to trading P&L impact
""")

    print(f"""
{BOLD}── Study the model answer ───────────────────────────────{RESET}
{CYAN}  cat {DIRS["scripts"]}/k8s06_story_notes.md{RESET}

{BOLD}── Numbers to memorise ──────────────────────────────────{RESET}
  60+ production apps  |  25% fewer incidents  |  99.4% uptime
  2-minute go/no-go   |  27.5h/week market window

{BOLD}── Practice saying out loud ─────────────────────────────{RESET}
  "Disable auto-sync FIRST — otherwise ArgoCD fights your rollback."
  "I treat every market-hours release as high-stakes, even small changes."
  "The diff tells you more than the image tag alone."
""")


# ══════════════════════════════════════════════
#  TEARDOWN / MAIN
# ══════════════════════════════════════════════

def teardown():
    header("Tearing Down K8s Lab")
    remove_lab_dir(LAB_ROOT)

def show_status():
    header("K8s Lab Status")
    for d in DIRS.values():
        if d.exists():
            ok(f"{d.name}/: {len(list(d.glob('*')))} files")
        else:
            warn(f"{d.name}/ not found")

def launch_scenario_99():
    for fn in [launch_scenario_1, launch_scenario_2, launch_scenario_3,
               launch_scenario_4, launch_scenario_5, launch_scenario_6]:
        fn()

SCENARIO_MAP = {
    1:  (launch_scenario_1,  "K8-01  CrashLoopBackOff diagnosis"),
    2:  (launch_scenario_2,  "K8-02  Rolling deployment rollback"),
    3:  (launch_scenario_3,  "K8-03  Pod stuck Pending / ImagePull"),
    4:  (launch_scenario_4,  "K8-04  ArgoCD rollback + disable auto-sync"),
    5:  (launch_scenario_5,  "K8-05  Validate release before prod sync"),
    6:  (launch_scenario_6,  "K8-06  Behavioral — K8s story"),
    99: (launch_scenario_99, "      ALL scenarios"),
}

def main():
    parser = argparse.ArgumentParser(
        description="Kubernetes & ArgoCD Challenge Lab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:<4} {v}" for k, (_, v) in SCENARIO_MAP.items()))
    parser.add_argument("--scenario", "-s", type=int, choices=list(SCENARIO_MAP.keys()))
    parser.add_argument("--teardown", "-t", action="store_true")
    parser.add_argument("--status",         action="store_true")
    args = parser.parse_args()

    if args.teardown: teardown(); return
    if args.status:   show_status(); return

    create_dirs()

    if args.scenario:
        if args.scenario == 99:
            for fn, _ in list(SCENARIO_MAP.values())[:-1]:
                fn()
        else:
            fn, _ = SCENARIO_MAP[args.scenario]; fn()
    else:
        header("Kubernetes & ArgoCD Challenge Lab")
        for num, (_, desc) in SCENARIO_MAP.items():
            print(f"    {num:<4} {desc}")
        choice = input("\n  Enter scenario number (or q): ").strip()
        if choice.lower() == "q": return
        try:
            if int(choice) == 99:
                for fn, _ in list(SCENARIO_MAP.values())[:-1]: fn()
            else:
                fn, _ = SCENARIO_MAP[int(choice)]; fn()
        except (KeyError, ValueError):
            print(f"{RED}  Invalid choice{RESET}")

    print(f"\n{BOLD}{SEP}{RESET}\n{GREEN}{BOLD}  Lab is live.{RESET}\n"
          f"{CYAN}    python3 lab_k8s.py --status\n"
          f"    python3 lab_k8s.py --teardown{RESET}\n{BOLD}{SEP}{RESET}\n")

if __name__ == "__main__":
    main()
