// ══════════════════════════════════════════════════════════
// SCENARIO LAB
// ══════════════════════════════════════════════════════════

const SCENARIOS = {
  fix: {
    title: 'Session Sequence Number Gap',
    deck: 'FIX Protocol', difficulty: 'intermediate', estimated: '20 min',
    description: 'The OMS dropped connectivity to the exchange gateway during a network blip. When the FIX session reconnected, the OMS sent Logon(A) with ResetOnLogon=Y, but the counterparty expects sequence number 4892. Orders are now being rejected with a MsgSeqNum Too Low error (tag 49 mismatch). Investigate the session state and restore normal order flow.',
    objectives: [
      'Identify the current vs. expected sequence numbers on both sides',
      'Determine whether to reset, retransmit, or send a SequenceReset(4)',
      'Verify recovery by confirming a test NewOrderSingle is accepted',
      'Document the incident steps for the trade desk'
    ]
  },
  kafka: {
    title: 'Consumer Lag Alert — Market Data Topic',
    deck: 'Kafka', difficulty: 'intermediate', estimated: '25 min',
    description: 'PagerDuty fired: consumer group md-normalizer on topic md.equities.raw has 280,000+ messages of lag across 6 partitions. The market data normalizer is falling behind, causing stale prices to propagate downstream to algos and risk systems. Real money is at risk.',
    objectives: [
      'Check per-partition lag using kafka-consumer-groups.sh',
      'Determine if lag is isolated to one partition or spread across all',
      'Check consumer instance count and resource utilisation',
      'Identify the bottleneck: deserialization, downstream write, or network',
      'Propose a remediation strategy (scale consumers, increase batch size, etc.)'
    ]
  },
  k8s: {
    title: 'Trading Pod CrashLoopBackOff',
    deck: 'Kubernetes', difficulty: 'intermediate', estimated: '20 min',
    description: 'The order router pod order-router-7f9d8b-xk2vp in namespace trading-ns is stuck in CrashLoopBackOff. The previous pod was healthy until a ConfigMap update was pushed 15 minutes ago. Traders on the floor report orders are piling up unrouted.',
    objectives: [
      'Retrieve crash logs from the current and previous container',
      'Inspect the ConfigMap change that triggered the issue',
      'Identify the misconfiguration causing the crash',
      'Roll back or patch the ConfigMap and confirm the pod stabilises',
      'Consider a PodDisruptionBudget to prevent future silent rollout outages'
    ]
  },
  marketdata: {
    title: 'Stale Quote Feed — AAPL NYSE',
    deck: 'Market Data', difficulty: 'beginner', estimated: '15 min',
    description: 'Risk monitoring alerted: AAPL bid/ask prices have not updated in 47 seconds. The NYSE feed normalizer is running but the symbol-level gap filter shows no recent messages for AAPL. All other NYSE symbols are updating normally. Algo strategies using AAPL quotes are trading on stale data.',
    objectives: [
      'Check the normalizer\'s per-symbol sequence number tracking for AAPL',
      'Inspect the raw feed handler for multicast group membership issues',
      'Verify the gap fill request / retransmission pipeline is operational',
      'Confirm recovery by observing AAPL timestamps returning to real-time',
      'File an incident report with the feed vendor'
    ]
  },
  sql: {
    title: 'Slow Trade Blotter Query',
    deck: 'SQL', difficulty: 'beginner', estimated: '15 min',
    description: 'The trade blotter web app is timing out for end-of-day reconciliation. The query SELECT * FROM trades WHERE symbol = ? AND trade_date = ? takes 28 seconds on a 40 million-row table. Compliance needs the report in 10 minutes.',
    objectives: [
      'Run EXPLAIN ANALYZE on the slow query',
      'Identify the missing composite index on (symbol, trade_date)',
      'Create the index without blocking writes (CREATE INDEX CONCURRENTLY)',
      'Re-run the query and confirm sub-second execution',
      'Add the index to the schema migration script'
    ]
  },
  airflow: {
    title: 'Settlement Pipeline DAG Failure',
    deck: 'Airflow', difficulty: 'intermediate', estimated: '25 min',
    description: 'The settlement_pipeline DAG has failed at the generate_settlement_files task for two consecutive runs. Settlement files were not delivered to DTCC by the T+1 deadline. Downstream reconciliation and fails reporting are blocked.',
    objectives: [
      'Retrieve task logs from the failed runs via CLI or UI',
      'Identify the root cause: data issue, dependency timeout, or permissions',
      'Fix the underlying issue and clear the failed task for backfill',
      'Confirm the DAG completes successfully on manual trigger',
      'Add an SLA miss alert to prevent silent failures going forward'
    ]
  },
  linux: {
    title: 'OMS Server High CPU — 95%',
    deck: 'Linux', difficulty: 'beginner', estimated: '15 min',
    description: 'Nagios alert: oms-server-01 CPU is at 95% for 8 minutes. OMS order response latency has spiked from 50µs to 12ms. The trading desk is reporting orders are slow to acknowledge. Market conditions are volatile — speed matters.',
    objectives: [
      'Use top/htop to identify the process consuming CPU',
      'Use perf or strace to determine what the process is spending time on',
      'Check for runaway threads, stuck GC, or an unexpected batch job',
      'Mitigate immediately (renice or kill the competing process)',
      'Determine whether the fix is temporary and schedule a proper remedy'
    ]
  },
  python: {
    title: 'Memory Leak in Quote Aggregator',
    deck: 'Python', difficulty: 'advanced', estimated: '30 min',
    description: 'The quote aggregation microservice has grown from 300 MB to 2.4 GB of heap over 24 hours — a clear leak. It aggregates NBBO quotes from 12 exchanges and publishes consolidated best bid/offer every 100 ms. OOM is projected in approximately 3 hours.',
    objectives: [
      'Attach to the running process with tracemalloc or memory_profiler',
      'Identify the object type accumulating (likely a dict/list not being evicted)',
      'Trace back to the code path that creates but never releases references',
      'Apply a fix (bounded cache, weak references, or explicit cleanup) and verify heap stabilises',
      'Expose a memory metric on the Prometheus endpoint to catch regressions'
    ]
  },
  aws: {
    title: 'S3 Trade Archive Upload Failure',
    deck: 'AWS', difficulty: 'intermediate', estimated: '20 min',
    description: 'The nightly batch job archive-trades is failing with AccessDenied when writing to s3://firm-trade-archive/daily/. This started after an IAM policy rotation last night. Three days of trade files are unarchived — a regulatory retention requirement is at risk.',
    objectives: [
      'Use aws sts get-caller-identity to confirm which role the job assumes',
      'Reproduce the AccessDenied with aws s3 ls or aws s3 cp',
      'Use IAM Policy Simulator or CloudTrail to trace the denial',
      'Identify the missing s3:PutObject permission or incorrect bucket condition',
      'Apply a least-privilege fix and confirm the upload succeeds'
    ]
  },
  networking: {
    title: 'Co-Location Packet Loss — Exchange Link',
    deck: 'Networking', difficulty: 'advanced', estimated: '30 min',
    description: 'Network monitoring shows 12% packet loss on the 10 GbE link from the co-location cage to the exchange gateway. FIX order latency has spiked from 45µs to 800µs. Some orders are timing out. The exchange has confirmed their side is healthy — the problem is in our equipment.',
    objectives: [
      'Run ping and traceroute to isolate which hop drops packets',
      'Check interface error counters (ip -s link) for CRC or overrun errors',
      'Inspect NIC driver logs for ring buffer drops or firmware faults',
      'Check IRQ affinity / NUMA topology for CPU saturation on the receive path',
      'Escalate to the co-location provider with a detailed fault report'
    ]
  },
  git: {
    title: 'Bad Merge in Trading Config Repo',
    deck: 'Git', difficulty: 'intermediate', estimated: '20 min',
    description: 'A developer merged a feature branch into main, overwriting the production FIX gateway config. SenderCompID changed from PROD-OMS to TEST-OMS. The push to prod went out 8 minutes ago — orders are now rejected by the exchange.',
    objectives: [
      'Use git log and git diff to identify exactly what changed and when',
      'Create a revert commit restoring the correct production configuration',
      'Push the revert following your emergency protocol',
      'Confirm exchange connectivity restores after deploy',
      'Add a branch protection rule requiring review before merges to main'
    ]
  },
  support: {
    title: 'Client Reporting Stale NVDA Prices',
    deck: 'Support Tickets', difficulty: 'beginner', estimated: '15 min',
    description: 'Priority-1 ticket: Portfolio manager at Meridian Capital reports NVDA bid/ask prices in their OMS have not refreshed since 10:14 AM EST. It is now 10:31 AM. They are trying to execute a 500 K share block and cannot trust the quotes.',
    objectives: [
      'Reproduce the issue by checking your internal NVDA quote display',
      'Trace the data chain: exchange feed → normalizer → distribution → client FIX drop copy',
      'Identify whether the issue is specific to NVDA, this client\'s feed, or systemic',
      'Apply or escalate the fix and confirm fresh quotes flow to the client',
      'Update the ticket with root cause, timeline, and resolution steps'
    ]
  },
  interview: {
    title: 'Design a Real-Time P&L System',
    deck: 'Interview Prep', difficulty: 'advanced', estimated: '45 min',
    description: 'System design interview: Design a real-time profit and loss calculation system for an equity trading desk. Requirements: 1 million trades per day, P&L updated within 500 ms of a fill arriving, 200 concurrent portfolio queries, single data centre failover without data loss.',
    objectives: [
      'Define the data model: positions, fills, market prices, P&L',
      'Design the ingestion path from FIX fill reports to P&L updates',
      'Choose an appropriate state store (Redis, Kafka Streams, etc.) for real-time positions',
      'Design the query API for portfolio managers and risk systems',
      'Address failover, consistency, and end-of-day reconciliation'
    ]
  },
  monitoring: {
    title: 'P99 Latency Cascade — JVM Heap Root Cause',
    deck: 'Monitoring', difficulty: 'intermediate', estimated: '20 min',
    description: 'PagerDuty fired four alarms within 90 seconds: order router P99 latency 4800ms, Kafka consumer lag 1900 messages, JVM heap 91%, and error rate 4.8%. The trading desk is seeing slow order acknowledgements. Your job is to determine the root cause from the cascade and identify the correct mitigation.',
    objectives: [
      'Read the PagerDuty alert and identify all co-firing alarms',
      'Determine breach order from the CloudWatch metrics timeline',
      'Identify the root cause metric vs. downstream cascade effects',
      'Propose the correct mitigation: restart pod, increase heap, or fix the leak',
      'Draft a post-incident summary with root cause, blast radius, and fix'
    ]
  },
  java: {
    title: 'Risk Engine JVM Triage — Stack Trace + GC + Deadlock',
    deck: 'Java / JVM', difficulty: 'intermediate', estimated: '25 min',
    description: 'The risk engine has three simultaneous problems logged at 09:31: (1) an NPE crash in the order router with a multi-level "Caused by:" chain, (2) a 4.8-second Full GC pause in the position service, and (3) a deadlock in the risk calculation thread. Analyse each artifact and identify the root cause of each.',
    objectives: [
      'Read the stack trace and identify the real root cause via the "Caused by:" chain',
      'Parse the GC log and find the stop-the-world event and its trigger',
      'Read the thread dump and identify the two deadlocked threads and the lock cycle',
      'For each problem: state the immediate mitigation and the permanent fix',
      'Explain which JVM flag would have written a heap dump on the OOM event'
    ]
  },
  darkpool: {
    title: 'ATS TRF Reporting Lag — Compliance Alert',
    deck: 'Dark Pools', difficulty: 'intermediate', estimated: '25 min',
    description: 'FINRA surveillance flagged your firm\'s ATS: 340 trades over the past 2 hours were reported to the Trade Reporting Facility with an average latency of 38 seconds — far beyond the 10-second window required by Rule 4552. Compliance needs immediate remediation. Failure to resolve within the hour triggers a mandatory self-report to FINRA.',
    objectives: [
      'Check the TRF gateway process status and its outbound queue depth',
      'Identify the bottleneck: serialization delay, network latency, or queue backup',
      'Inspect TRF submission logs for rejection codes or retransmission loops',
      'Fix the issue (restart gateway, clear queue, update endpoint config) and verify latency drops below 10 s',
      'Draft a compliance incident summary with timeline, root cause, and proof of remediation'
    ]
  }
};

// ── Per-scenario lab instructions (no spoilers) ───────────
const SCENARIO_LAB = {
  fix: {
    first_steps: [
      'Read the message log: cat ~/trading-support/fix/logs/*.log',
      'Inspect the sequence number files: ls ~/trading-support/fix/sessions/PROD-OMS-EXCHANGE/',
      'The error message tells you exactly what the exchange expected — compare that to what the OMS sent'
    ],
    tools: []
  },
  kafka: {
    first_steps: [
      'export PATH=~/trading-support/kafka/bin:$PATH — then check lag: kafka-consumer-groups.sh --bootstrap-server localhost:9092 --group md-normalizer --describe',
      'Review the consumer config: cat ~/trading-support/kafka/config/consumer.properties',
      'Watch the lag grow in real time — is it all partitions or just some?'
    ],
    tools: ['kafka-consumer-groups.sh'],
    hint: 'The problem is in a config value that controls how much work the consumer does per polling cycle. Think about the math: if the consumer polls once per second, what value do you need to keep pace with the producer\'s write rate?'
  },
  k8s: {
    first_steps: [
      'export PATH=~/trading-support/k8s/bin:$PATH — then: kubectl get pods -n trading-ns',
      'Pull the crash logs: kubectl logs order-router-7f9d8b-xk2vp -n trading-ns',
      'Read the ConfigMap the pod depends on: kubectl get configmap order-router-config -n trading-ns -o yaml'
    ],
    tools: ['kubectl (simulated)']
  },
  marketdata: {
    first_steps: [
      'export PATH=~/trading-support/marketdata/bin:$PATH — run: feedcheck',
      'Note which symbols are fresh and which are stale — is it random or a specific symbol?',
      'Check the normalizer log: cat ~/trading-support/marketdata/logs/normalizer.log — look for what is missing'
    ],
    tools: ['feedcheck']
  },
  sql: {
    first_steps: [
      'Open the DB: sqlite3 ~/trading-support/sql/trades.db',
      'Run the slow query with timing: .timer on  then paste slow_query.sql',
      'Use EXPLAIN QUERY PLAN to see why it\'s slow — check ~/trading-support/sql/explain_hint.txt for guidance'
    ],
    tools: []
  },
  airflow: {
    first_steps: [
      'export PATH=~/trading-support/airflow/bin:$PATH — trigger the DAG: airflow dags trigger settlement_pipeline',
      'Watch which task fails and read its error output carefully',
      'Look at the error log: cat ~/trading-support/airflow/logs/settlement_pipeline.log — what path does it try to write to?'
    ],
    tools: ['airflow (simulated)']
  },
  linux: {
    first_steps: [
      'Check overall CPU: top  or  htop',
      'Filter for the culprit: ps aux --sort=-%cpu | head -10',
      'Note the process name and PID — then check crontab.txt to understand how it got there'
    ],
    tools: []
  },
  python: {
    first_steps: [
      'Watch memory grow: watch -n5 "cat ~/trading-support/python/metrics.log | tail -3"',
      'Run the profiler to see what\'s allocating: python3 ~/trading-support/python/leak_profile.py',
      'Compare the broken and fixed service: diff ~/trading-support/python/service.py ~/trading-support/python/service_fixed.py'
    ],
    tools: []
  },
  aws: {
    first_steps: [
      'export PATH=~/trading-support/aws/bin:$PATH — confirm identity: aws sts get-caller-identity',
      'Reproduce the error: aws s3 cp ~/trading-support/aws/data/trades_20260505.csv s3://firm-trade-archive/daily/',
      'Inspect the role policy: aws iam get-role-policy --role-name TradingArchiveRole --policy-name ArchivePolicy'
    ],
    tools: ['aws (simulated)']
  },
  networking: {
    first_steps: [
      'Confirm packet loss: bash ~/trading-support/networking/check-loss.sh',
      'Check interface error counters: bash ~/trading-support/networking/bin/ifcheck',
      'Read the latency spike log: cat ~/trading-support/networking/logs/network-monitor.log'
    ],
    tools: ['ifcheck', 'ping-exchange', 'check-loss.sh']
  },
  git: {
    first_steps: [
      'cd ~/trading-support/git/trading-config  then: git log --oneline',
      'Find exactly what changed in the last commit: git show HEAD -- gateway.cfg',
      'Read the deploy log to understand the impact: cat ~/trading-support/git/deploy.log'
    ],
    tools: []
  },
  support: {
    first_steps: [
      'export PATH=~/trading-support/support/bin:$PATH — read the ticket: cat ~/trading-support/support/logs/client-ticket.txt',
      'Monitor all symbols live: quotemon — note which one goes dark and when',
      'Trace the chain: check publisher output, then normalizer output, then compare — where does NVDA disappear?'
    ],
    tools: ['quotemon']
  },
  interview: {
    first_steps: [
      'Read the requirements: cat ~/trading-support/interview/design/requirements.md',
      'Open the architecture template and fill in the [?] boxes: nano ~/trading-support/interview/design/architecture.txt',
      'Implement the class skeletons: nano ~/trading-support/interview/skeleton/pnl_engine.py'
    ],
    tools: []
  },
  darkpool: {
    first_steps: [
      'export PATH=~/trading-support/darkpool/bin:$PATH — check live stats: trf-status',
      'Read the compliance alert: cat ~/trading-support/darkpool/logs/compliance-alert.txt',
      'Find the misconfigured value: cat ~/trading-support/darkpool/config/trf-reporter.conf — the comment is a clue'
    ],
    tools: ['trf-status']
  },
  monitoring: {
    first_steps: [
      'Read the PagerDuty alert: cat ~/trading-support/monitoring/data/pagerduty_alert.json',
      'Check which alarms are co-firing and note the exact timestamps — which metric breached FIRST?',
      'Read the metrics snapshot: cat ~/trading-support/monitoring/data/cloudwatch_metrics.json — trace the cascade order'
    ],
    tools: [],
    hint: 'The breach order is the answer. Sort the alarms by their fire timestamp — the first metric to breach is the root cause. Everything else is a downstream effect of that one failure.'
  },
  java: {
    first_steps: [
      'Read the stack trace: cat ~/trading-support/java/logs/order_router_crash.log — find the "Caused by:" chain',
      'Check the GC log: cat ~/trading-support/java/logs/position_service_gc.log — identify the stop-the-world event',
      'Read the thread dump: cat ~/trading-support/java/dumps/risk_engine_threaddump.txt — look for the DEADLOCK DETECTED section'
    ],
    tools: [],
    hint: 'For stack traces: always read the "Caused by:" blocks bottom-up — the deepest one is the real root cause. For GC logs: look for "Pause Full" entries — the millisecond value tells you how long all threads were frozen.'
  }
};