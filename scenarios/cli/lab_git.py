#!/usr/bin/env python3
"""
Support Engineer Challenge Lab — Git & Regression Hunt Setup
============================================================
Creates a real Git repository with a meaningful commit history,
intentional regressions, config changes, and broken code — so every
scenario in the HTML challenge lab (G1-G5) can be practiced for real.

Run with: python3 lab_git.py [--scenario N] [--teardown]

SCENARIOS:
  1   G-01  git bisect — find the commit that broke the build
  2   G-02  git blame + log — who changed what and when
  3   G-03  Revert a bad deploy — git revert vs git reset
  4   G-04  Search commit history for a config change
  5   G-05  Behavioral — your GitHub commit review process
  99         ALL scenarios (builds full repo used by all)
"""

import os, shutil, subprocess, argparse
from pathlib import Path
from datetime import datetime
from common import (
    GREEN, YELLOW, RED, CYAN, BOLD, RESET, SEP,
    ok, warn, err, info, header, lab_footer,
    remove_lab_dir,
)

LAB_ROOT = Path("/tmp/lab_git")
REPO_DIR = LAB_ROOT / "trading-platform"

def git(*args, cwd=None):
    """Run a git command in the repo directory."""
    result = subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd or REPO_DIR),
        capture_output=True, text=True
    )
    return result.stdout.strip()

def git_commit(message: str, author: str = "Alice Chen <alice@firm.com>",
               date: str = None):
    """Stage all changes and make a commit."""
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"]     = author.split("<")[0].strip()
    env["GIT_AUTHOR_EMAIL"]    = author.split("<")[1].rstrip(">")
    env["GIT_COMMITTER_NAME"]  = env["GIT_AUTHOR_NAME"]
    env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
    if date:
        env["GIT_AUTHOR_DATE"]    = date
        env["GIT_COMMITTER_DATE"] = date
    subprocess.run(["git", "add", "-A"], cwd=str(REPO_DIR), env=env,
                   capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=str(REPO_DIR),
                   env=env, capture_output=True)

def setup_repo():
    """Build the full repo with a meaningful commit history."""
    if REPO_DIR.exists():
        shutil.rmtree(REPO_DIR)
    REPO_DIR.mkdir(parents=True)

    subprocess.run(["git", "init"], cwd=str(REPO_DIR), capture_output=True)
    subprocess.run(["git", "config", "user.email", "lab@trading.internal"],
                   cwd=str(REPO_DIR), capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lab Setup"],
                   cwd=str(REPO_DIR), capture_output=True)

    # ── Commit 1: initial project ──────────────────────────────
    (REPO_DIR / "README.md").write_text("# Trading Platform\nCore trading infrastructure.\n")

    (REPO_DIR / "config").mkdir(exist_ok=True)
    (REPO_DIR / "config" / "kafka-consumer.yml").write_text("""\
kafka:
  bootstrap_servers: kafka-broker-1:9092,kafka-broker-2:9092
  group_id: risk-engine-group
  max.poll.records: 500
  max.poll.interval.ms: 300000
  session.timeout.ms: 10000
  auto.offset.reset: earliest
""")
    (REPO_DIR / "config" / "oms.conf").write_text("""\
[oms]
host            = 10.0.1.50
port            = 8080
max_connections = 200
heartbeat_ms    = 500
""")

    (REPO_DIR / "src").mkdir(exist_ok=True)
    (REPO_DIR / "src" / "order_router.py").write_text("""\
\"\"\"Order router — routes orders to exchanges based on symbol.\"\"\"

VENUE_MAP = {
    "AAPL": "NYSE",
    "GOOGL": "NASDAQ",
    "MSFT": "NASDAQ",
    "TSLA": "NASDAQ",
}

def route_order(symbol: str, qty: int, price: float) -> dict:
    venue = VENUE_MAP.get(symbol, "NYSE")
    return {"symbol": symbol, "venue": venue, "qty": qty, "price": price}

def calculate_notional(qty: int, price: float) -> float:
    return qty * price
""")

    (REPO_DIR / "src" / "risk_check.py").write_text("""\
\"\"\"Risk checks — validates orders before routing.\"\"\"

MAX_POSITION = 10_000
MAX_NOTIONAL = 5_000_000.0

def check_position(current_qty: int, order_qty: int) -> bool:
    return (current_qty + order_qty) <= MAX_POSITION

def check_notional(qty: int, price: float) -> bool:
    return (qty * price) <= MAX_NOTIONAL

def check_order(symbol: str, qty: int, price: float, current_qty: int = 0) -> tuple:
    if not check_position(current_qty, qty):
        return False, f"Position limit exceeded: {current_qty + qty} > {MAX_POSITION}"
    if not check_notional(qty, price):
        return False, f"Notional limit exceeded: ${qty*price:,.0f} > ${MAX_NOTIONAL:,.0f}"
    return True, "OK"
""")

    (REPO_DIR / "tests").mkdir(exist_ok=True)
    (REPO_DIR / "tests" / "test_risk.py").write_text("""\
\"\"\"Tests for risk_check module.\"\"\"
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from risk_check import check_order

def test_normal_order():
    ok, msg = check_order("AAPL", 100, 185.50)
    assert ok, f"Expected OK, got: {msg}"

def test_position_limit():
    ok, msg = check_order("AAPL", 100, 185.50, current_qty=9950)
    assert not ok, "Should fail position check"

def test_notional_limit():
    ok, msg = check_order("AAPL", 30000, 185.50)
    assert not ok, "Should fail notional check"

if __name__ == "__main__":
    test_normal_order();  print("✓ test_normal_order")
    test_position_limit(); print("✓ test_position_limit")
    test_notional_limit(); print("✓ test_notional_limit")
    print("All tests passed.")
""")
    git_commit("Initial commit: order router, risk checks, config",
               "Alice Chen <alice@firm.com>", "2024-01-10 09:00:00 +0000")
    ok("Commit 1: initial project")

    # ── Commit 2: add FIX session handler ─────────────────────
    (REPO_DIR / "src" / "fix_session.py").write_text("""\
\"\"\"FIX session handler.\"\"\"

HEARTBEAT_INTERVAL = 30   # seconds

def build_logon(sender: str, target: str, seq: int) -> str:
    ts = "20240115-09:30:00"
    body = f"35=A\\x0149={sender}\\x0156={target}\\x0134={seq}\\x0152={ts}\\x0198=0\\x01108={HEARTBEAT_INTERVAL}\\x01"
    return f"8=FIX.4.4\\x019={len(body)}\\x01" + body + "10=000\\x01"

def is_valid_seq(expected: int, received: int) -> bool:
    return expected == received
""")
    git_commit("Add FIX session handler with heartbeat config",
               "Bob Singh <bob@firm.com>", "2024-01-11 10:15:00 +0000")
    ok("Commit 2: FIX session handler")

    # ── Commit 3: increase Kafka poll interval ─────────────────
    (REPO_DIR / "config" / "kafka-consumer.yml").write_text("""\
kafka:
  bootstrap_servers: kafka-broker-1:9092,kafka-broker-2:9092
  group_id: risk-engine-group
  max.poll.records: 500
  max.poll.interval.ms: 60000
  session.timeout.ms: 10000
  auto.offset.reset: earliest
""")
    # max.poll.interval.ms changed 300000 → 60000 — this causes consumer timeouts
    git_commit("Tune Kafka consumer: reduce max.poll.interval.ms to 60s",
               "Carol Wu <carol@firm.com>", "2024-01-12 14:30:00 +0000")
    ok("Commit 3: kafka poll interval change (the regression!)")

    # ── Commit 4: add monitoring ───────────────────────────────
    (REPO_DIR / "src" / "metrics.py").write_text("""\
\"\"\"Prometheus metrics exporter.\"\"\"

def record_fill(symbol: str, qty: int, latency_ms: float):
    # gauge: fill_count{symbol}
    # histogram: fill_latency_ms
    pass

def record_rejection(symbol: str, reason: str):
    # counter: rejection_count{symbol, reason}
    pass
""")
    git_commit("Add Prometheus metrics for fills and rejections",
               "Alice Chen <alice@firm.com>", "2024-01-13 09:00:00 +0000")
    ok("Commit 4: add metrics")

    # ── Commit 5: introduce the bug (calculate_notional broken) ──
    (REPO_DIR / "src" / "order_router.py").write_text("""\
\"\"\"Order router — routes orders to exchanges based on symbol.\"\"\"

VENUE_MAP = {
    "AAPL": "NYSE",
    "GOOGL": "NASDAQ",
    "MSFT": "NASDAQ",
    "TSLA": "NASDAQ",
}

def route_order(symbol: str, qty: int, price: float) -> dict:
    venue = VENUE_MAP.get(symbol, "NYSE")
    return {"symbol": symbol, "venue": venue, "qty": qty, "price": price}

def calculate_notional(qty: int, price: float) -> float:
    # BUG: should be qty * price, but accidentally only returns qty
    return float(qty)
""")
    git_commit("Refactor order_router: simplify notional calculation",
               "Dave Kim <dave@firm.com>", "2024-01-14 15:45:00 +0000")
    ok("Commit 5: BUG INTRODUCED — calculate_notional returns qty only")

    # ── Commit 6: unrelated change after the bug ───────────────
    (REPO_DIR / "config" / "oms.conf").write_text("""\
[oms]
host            = 10.0.1.50
port            = 8080
max_connections = 300
heartbeat_ms    = 500
reconnect_delay = 5
""")
    git_commit("Increase OMS max_connections from 200 to 300",
               "Alice Chen <alice@firm.com>", "2024-01-15 08:00:00 +0000")
    ok("Commit 6: OMS config change (unrelated)")

    # ── Tag the known-good and bad releases ────────────────────
    log = git("log", "--oneline")
    commits = log.strip().split("\n")
    # Tag commit 4 (add metrics) as v2.4.0 (last good)
    # Tag commit 5 (bug) as v2.5.0 (bad)
    if len(commits) >= 3:
        good_sha = commits[2].split()[0]   # 3rd from HEAD = add metrics
        bad_sha  = commits[1].split()[0]   # 2nd from HEAD = bug
        git("tag", "-a", "v2.4.0", good_sha, "-m", "Release v2.4.0 — known good")
        git("tag", "-a", "v2.5.0", bad_sha,  "-m", "Release v2.5.0 — introduced notional bug")

    # ── Create a feature branch ────────────────────────────────
    default_branch = git("symbolic-ref", "--short", "HEAD") or "master"
    git("checkout", "-b", "fix/notional-calculation")
    (REPO_DIR / "src" / "order_router.py").write_text("""\
\"\"\"Order router — routes orders to exchanges based on symbol.\"\"\"

VENUE_MAP = {
    "AAPL": "NYSE",
    "GOOGL": "NASDAQ",
    "MSFT": "NASDAQ",
    "TSLA": "NASDAQ",
}

def route_order(symbol: str, qty: int, price: float) -> dict:
    venue = VENUE_MAP.get(symbol, "NYSE")
    return {"symbol": symbol, "venue": venue, "qty": qty, "price": price}

def calculate_notional(qty: int, price: float) -> float:
    return qty * price   # FIXED
""")
    git_commit("Fix calculate_notional: restore qty * price",
               "Alice Chen <alice@firm.com>", "2024-01-15 11:00:00 +0000")
    git("checkout", default_branch)
    ok("Fix branch: fix/notional-calculation")

    ok(f"\nRepo ready at {REPO_DIR}")
    ok(f"Run: cd {REPO_DIR} && git log --oneline")


# ══════════════════════════════════════════════
#  SCENARIO 1 — git bisect
# ══════════════════════════════════════════════

def launch_scenario_1():
    header("Scenario G-01 — git bisect — Find the Regression")
    print("  calculate_notional() returns wrong values in v2.5.0.")
    print("  Use git bisect to find the exact commit that broke it.\n")

    setup_repo()

    # Write a test script bisect can use automatically
    test_script = REPO_DIR / "bisect_test.sh"
    test_script.write_text("""\
#!/bin/bash
# Bisect test: exits 0 (good) if calculate_notional is correct, 1 (bad) if not
python3 -c "
import sys, os
sys.path.insert(0, 'src')
try:
    from order_router import calculate_notional
    result = calculate_notional(100, 185.50)
    # Correct answer is 18550.0; bug returns 100.0
    if abs(result - 18550.0) < 0.01:
        sys.exit(0)   # GOOD
    else:
        sys.exit(1)   # BAD
except Exception:
    sys.exit(1)
"
""")
    test_script.chmod(0o755)

    print(f"""
{BOLD}── Repository: {REPO_DIR} ─────────────────{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Look at the commit history
{CYAN}       cd {REPO_DIR}
       git log --oneline{RESET}

  2. Confirm the bug exists on HEAD
{CYAN}       python3 -c "import sys; sys.path.insert(0,'src'); from order_router import calculate_notional; print(calculate_notional(100, 185.50))"
       # Bug: prints 100.0 instead of 18550.0{RESET}

  3. Start bisect (v2.4.0 is known good, HEAD is known bad)
{CYAN}       git bisect start
       git bisect bad                # HEAD is bad
       git bisect good v2.4.0        # v2.4.0 was good{RESET}

  4. Option A: Test each commit manually
{CYAN}       python3 -c "import sys; sys.path.insert(0,'src'); from order_router import calculate_notional; print(calculate_notional(100, 185.50))"
       git bisect good   # or: git bisect bad{RESET}

  5. Option B: Automate with the test script
{CYAN}       git bisect run ./bisect_test.sh
       # Git will binary-search and find the bad commit automatically{RESET}

  6. When bisect finishes, read the result
{CYAN}       git bisect reset   # return to HEAD when done{RESET}

{BOLD}── Expected answer ──────────────────────────────────────{RESET}
  Bisect will identify: "Refactor order_router: simplify notional calculation"
  by Dave Kim — the commit that changed qty*price to just qty.

{BOLD}── Why bisect? ───────────────────────────────────────────{RESET}
  git bisect does a binary search over N commits.
  N=100 commits → only 7 checks needed (log2(100)).
  Manual review of 100 commits → 100 checks.
""")


# ══════════════════════════════════════════════
#  SCENARIO 2 — git blame + log
# ══════════════════════════════════════════════

def launch_scenario_2():
    header("Scenario G-02 — git blame + log — Who Changed What?")
    print("  Find who last changed the Kafka poll interval and when.\n")

    if not REPO_DIR.exists():
        setup_repo()

    print(f"""
{BOLD}── Repository: {REPO_DIR} ─────────────────{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. See who last touched every line of the Kafka config
{CYAN}       cd {REPO_DIR}
       git blame config/kafka-consumer.yml{RESET}

  2. Show full history of just that file
{CYAN}       git log --oneline -- config/kafka-consumer.yml{RESET}

  3. Show the actual diff for each change to that file
{CYAN}       git log -p -- config/kafka-consumer.yml{RESET}

  4. Search all commits where max.poll.interval.ms was changed
{CYAN}       git log -S "max.poll.interval.ms" --oneline
       git log -S "max.poll.interval.ms" -p{RESET}
       # -S = 'pickaxe': finds commits that changed the count of this string

  5. Blame a specific line range
{CYAN}       git blame -L 4,7 config/kafka-consumer.yml{RESET}

  6. Show full details of the suspicious commit
{CYAN}       git show <commit-sha>{RESET}

{BOLD}── Expected answer ──────────────────────────────────────{RESET}
  Carol Wu changed max.poll.interval.ms from 300000 → 60000
  on 2024-01-12. A 60s poll interval is far too short for the
  risk engine's batch processing — consumers time out and
  trigger rebalances, causing lag spikes.

{BOLD}── Pickaxe (-S) vs grep (--grep) ───────────────────────{RESET}
  git log -S "string"     → commits where the COUNT of "string" changed
                            (i.e., it was added or removed)
  git log --grep="string" → commits where the MESSAGE contains "string"
  git log -G "regex"      → commits where the DIFF matches the regex
""")


# ══════════════════════════════════════════════
#  SCENARIO 3 — Revert a Bad Deploy
# ══════════════════════════════════════════════

def launch_scenario_3():
    header("Scenario G-03 — Revert a Bad Deploy")
    print("  The calculate_notional bug is in production. Revert it safely.\n")

    if not REPO_DIR.exists():
        setup_repo()

    print(f"""
{BOLD}── Repository: {REPO_DIR} ─────────────────{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Find the bad commit SHA
{CYAN}       cd {REPO_DIR}
       git log --oneline{RESET}
       # Look for: "Refactor order_router: simplify notional calculation"

  2. git revert — safe for shared/production branches
{CYAN}       git revert <bad-commit-sha>
       # Creates a NEW commit that undoes the change
       # Safe: does not rewrite history
       git log --oneline   # you'll see a new "Revert ..." commit on top{RESET}

  3. Verify the fix
{CYAN}       python3 -c "import sys; sys.path.insert(0,'src'); from order_router import calculate_notional; print(calculate_notional(100, 185.50))"
       # Should print 18550.0{RESET}

  4. Alternatively: cherry-pick the fix from the feature branch
{CYAN}       git log --oneline fix/notional-calculation
       git cherry-pick <fix-commit-sha>
       # Applies just that one commit onto master{RESET}

{BOLD}── git revert vs git reset ──────────────────────────────{RESET}
  git revert <sha>
    Creates a new commit that undoes <sha>.
    Safe for shared branches — does NOT rewrite history.
    Other developers' clones are unaffected.
    ✓ USE THIS for production hotfixes.

  git reset --hard <sha>
    Moves HEAD backward, DELETES commits after <sha>.
    Rewrites history — breaks anyone who pulled those commits.
    ✗ NEVER use on shared/main/production branches.
    ✓ OK for local cleanup before pushing.

  git reset --soft <sha>
    Moves HEAD backward but keeps changes staged.
    Useful for squashing commits before a PR.

{BOLD}── After reverting — deploy via ArgoCD ─────────────────{RESET}
  git push origin master
  # ArgoCD detects new commit → auto-syncs → deploys the revert
  # OR: argocd app sync oms-engine --force
""")


# ══════════════════════════════════════════════
#  SCENARIO 4 — Search Commit History
# ══════════════════════════════════════════════

def launch_scenario_4():
    header("Scenario G-04 — Search Commit History for a Config Change")
    print("  Kafka consumer timeouts started. Find when max.poll.interval.ms changed.\n")

    if not REPO_DIR.exists():
        setup_repo()

    print(f"""
{BOLD}── Repository: {REPO_DIR} ─────────────────{RESET}

{BOLD}── Your Tasks ─────────────────────────────────────────{RESET}
  1. Pickaxe search — find commits that changed the config value
{CYAN}       cd {REPO_DIR}
       git log -S "max.poll.interval.ms" --oneline
       git log -S "max.poll.interval.ms" -p{RESET}
       # -p shows the full diff: old value (- line) vs new value (+ line)

  2. Regex search — find all Kafka timeout-related changes
{CYAN}       git log -G "max\\.poll\\.(interval|records)" --oneline{RESET}

  3. Search commit messages
{CYAN}       git log --grep="kafka" --oneline -i
       git log --grep="Tune" --oneline -i{RESET}

  4. Blame to see current state of the file
{CYAN}       git blame config/kafka-consumer.yml{RESET}

  5. Show the before and after values
{CYAN}       git log -S "max.poll.interval.ms" -p -- config/kafka-consumer.yml{RESET}
       # Look for: -  max.poll.interval.ms: 300000
       #           +  max.poll.interval.ms: 60000

{BOLD}── Expected findings ────────────────────────────────────{RESET}
  Commit by Carol Wu: "Tune Kafka consumer: reduce max.poll.interval.ms to 60s"
  Change: 300000ms (5 min) → 60000ms (1 min)
  
  Impact: The risk engine's batch processing takes ~90s per batch.
  With max.poll.interval.ms=60s, the broker considers the consumer
  dead → triggers rebalance → lag spikes → exactly the symptom reported.
  
  Fix: revert to 300000 (or set to 600000 for safety margin).

{BOLD}── Search commands cheat sheet ──────────────────────────{RESET}
  git log -S "string"        find commits where string count changed
  git log -G "regex"         find commits where diff matches regex
  git log --grep="msg"       find commits where message contains msg
  git log --oneline -n 20    last 20 commits, compact
  git log --since="3 days"   commits in last 3 days
  git log --author="Carol"   commits by Carol
  git log -- path/to/file    commits touching that file
  git log --stat             show files changed per commit
""")


# ══════════════════════════════════════════════
#  SCENARIO 5 — Behavioral Story
# ══════════════════════════════════════════════

def launch_scenario_5():
    header("Scenario G-05 — Your GitHub Commit Review Process (Behavioral)")
    print("  Prepare: 'Tell me about finding a production issue in the code.'\n")

    story = LAB_ROOT / "g05_story_notes.md"
    story.write_text("""\
# G-05: GitHub Commit Review — Behavioral Answer
=================================================

## The Question
"Tell me about a time you identified a production issue by reviewing
code rather than just looking at logs or metrics."

## Model Answer

"One thing I've built into my incident workflow is checking GitHub
for recent commits as one of my FIRST steps — not as a last resort
after I've exhausted logs and metrics.

When an incident comes in, I filter commits to the affected service
in the 30-60 minutes before the issue started. I look for:
  • Config changes (thresholds, timeouts, connection pool sizes)
  • Dependency version bumps
  • Changes to the code path that's failing
  • Anything that touched the data pipeline or output paths

A concrete example: our risk engine started showing Kafka consumer lag
spikes. Logs showed the consumer was rebalancing repeatedly — but no
error, no exception, nothing obvious. I ran:

  git log -S 'max.poll.interval.ms' -p -- config/kafka-consumer.yml

And found that Carol had reduced max.poll.interval.ms from 300s to 60s
two days earlier. The risk engine's batch processing takes ~90s —
longer than the new timeout. Broker thought consumer was dead, triggered
rebalance, lag spiked. Root cause identified in under 3 minutes.
Without checking the diff I'd have spent 30 minutes chasing application logs.

Over time this habit reduced our mean time to identify root cause
by an estimated 40%."

## Key Phrases
→ "I treat recent code changes as a first-class signal, not a last resort"
→ "git log -S is a tool I reach for before Splunk for config issues"
→ "Root cause in under 3 minutes by reading the diff"
→ "40% reduction in MTTI"

## Connect to Job Description
JD phrase: "drilling into those requiring action, including looking into the code"
Your answer: "that's exactly the mindset — I look at the code changes
             before spending time on logs alone"
""")

    print(f"""
{BOLD}── Study your behavioral answer ────────────────────────{RESET}
{CYAN}       cat {story}{RESET}

{BOLD}── Practise the git commands from the story ────────────{RESET}
{CYAN}       cd {REPO_DIR}
       git log -S "max.poll.interval.ms" -p -- config/kafka-consumer.yml{RESET}

{BOLD}── Key interview phrases ────────────────────────────────{RESET}
  "I treat recent code changes as a first-class signal."
  "git log -S for config changes, git log --since for time windows."
  "Root cause in under 3 minutes by reading the diff."
  "40% reduction in MTTI from this habit."
""")


# ══════════════════════════════════════════════
#  TEARDOWN / MAIN
# ══════════════════════════════════════════════

def teardown():
    header("Tearing Down Git Lab")
    remove_lab_dir(LAB_ROOT)

def show_status():
    header("Git Lab Status")
    if REPO_DIR.exists():
        log = git("log", "--oneline")
        ok(f"Repo at {REPO_DIR}")
        for line in log.split("\n"):
            print(f"    {CYAN}{line}{RESET}")
    else:
        warn("Repo not initialised — run a scenario first")

SCENARIO_MAP = {
    1:  (launch_scenario_1, "G-01  git bisect — find the regression commit"),
    2:  (launch_scenario_2, "G-02  git blame + log — who changed what"),
    3:  (launch_scenario_3, "G-03  Revert a bad deploy safely"),
    4:  (launch_scenario_4, "G-04  Search commit history for config change"),
    5:  (launch_scenario_5, "G-05  Behavioral — commit review process"),
    99: (None,               "     ALL scenarios"),
}

def main():
    parser = argparse.ArgumentParser(
        description="Git & Regression Hunt Challenge Lab",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(f"  {k:<4} {v}" for k, (_, v) in SCENARIO_MAP.items()))
    parser.add_argument("--scenario", "-s", type=int, choices=list(SCENARIO_MAP.keys()))
    parser.add_argument("--teardown", "-t", action="store_true")
    parser.add_argument("--status",         action="store_true")
    args = parser.parse_args()

    if args.teardown: teardown(); return
    if args.status:   show_status(); return

    LAB_ROOT.mkdir(parents=True, exist_ok=True)

    if args.scenario:
        if args.scenario == 99:
            setup_repo()
            for k, (fn, _) in SCENARIO_MAP.items():
                if k != 99 and fn: fn()
        else:
            fn, _ = SCENARIO_MAP[args.scenario]; fn()
    else:
        header("Git & Regression Hunt Challenge Lab")
        for num, (_, desc) in SCENARIO_MAP.items():
            print(f"    {num:<4} {desc}")
        choice = input("\n  Enter scenario number (or q): ").strip()
        if choice.lower() == "q": return
        try:
            num = int(choice)
            if num == 99:
                setup_repo()
                for k, (fn, _) in SCENARIO_MAP.items():
                    if k != 99 and fn: fn()
            else:
                fn, _ = SCENARIO_MAP[num]; fn()
        except (KeyError, ValueError):
            print(f"{RED}  Invalid choice{RESET}")

    lab_footer("lab_git.py")

if __name__ == "__main__":
    main()
