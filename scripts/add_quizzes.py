"""
add_quizzes.py — injects a 5-question multiple-choice quiz slide at the end
of every deck in challenge-lab.html, then updates slide counts and badges.
"""

import re
from pathlib import Path

SRC = Path(__file__).parent.parent / 'challenge-lab.html'

# ── Quiz CSS ──────────────────────────────────────────────────────────────────
QUIZ_CSS = """
  /* ── Quiz slides ── */
  .quiz-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
    margin-bottom: 14px;
  }
  .quiz-q { display: flex; flex-direction: column; gap: 7px; }
  .quiz-q-text {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    line-height: 1.4;
    margin-bottom: 2px;
  }
  .quiz-opts { display: flex; flex-direction: column; gap: 5px; }
  .quiz-opt {
    display: flex;
    align-items: flex-start;
    gap: 9px;
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 5px;
    cursor: pointer;
    font-size: 12px;
    line-height: 1.4;
    background: rgba(255,255,255,0.02);
    transition: border-color 0.12s, background 0.12s;
    user-select: none;
  }
  .quiz-opt:hover { border-color: var(--accent); background: rgba(232,107,26,0.06); }
  .quiz-opt input[type=radio] { position: absolute; opacity: 0; width: 0; height: 0; }
  .quiz-key {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 18px;
    height: 18px;
    border-radius: 3px;
    background: var(--border);
    color: var(--muted);
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 700;
    flex-shrink: 0;
    margin-top: 1px;
    transition: all 0.12s;
  }
  .quiz-opt.selected { border-color: var(--blue); background: rgba(128,200,255,0.08); }
  .quiz-opt.selected .quiz-key { background: var(--blue); color: #12121e; }
  .quiz-opt.correct { border-color: #22c55e; background: rgba(34,197,94,0.12); }
  .quiz-opt.correct .quiz-key { background: #22c55e; color: #052e0a; }
  .quiz-opt.wrong { border-color: var(--red); background: rgba(248,113,113,0.10); }
  .quiz-opt.wrong .quiz-key { background: var(--red); color: #3f0505; }
  .quiz-opt.reveal-correct { border-color: rgba(34,197,94,0.45); }
  .quiz-opt.reveal-correct .quiz-key { background: rgba(34,197,94,0.22); color: #22c55e; }
  .quiz-actions {
    display: flex;
    align-items: center;
    gap: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
  .quiz-submit-btn {
    background: rgba(232,107,26,0.14);
    border: 1px solid var(--accent);
    color: var(--accent);
    font-family: var(--mono);
    font-size: 12px;
    padding: 6px 18px;
    border-radius: 5px;
    cursor: pointer;
    transition: all 0.12s;
  }
  .quiz-submit-btn:hover:not(:disabled) { background: rgba(232,107,26,0.28); }
  .quiz-submit-btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .quiz-score-lbl { font-family: var(--mono); font-size: 14px; font-weight: 700; min-width: 60px; }
  .quiz-reset-btn {
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    color: var(--muted);
    font-family: var(--mono);
    font-size: 11px;
    padding: 5px 12px;
    border-radius: 5px;
    cursor: pointer;
    display: none;
    transition: all 0.12s;
  }
  .quiz-reset-btn:hover { border-color: var(--muted); color: var(--text); }
"""

# ── Quiz JS ───────────────────────────────────────────────────────────────────
QUIZ_JS = """
// ── Quiz ──
function checkQuiz(id) {
  const quiz = document.getElementById('quiz-' + id);
  const questions = quiz.querySelectorAll('.quiz-q');
  let correct = 0;
  questions.forEach(q => {
    const answer = q.dataset.answer;
    const selected = q.querySelector('input:checked');
    q.querySelectorAll('.quiz-opt').forEach(opt => {
      const val = opt.querySelector('input').value;
      if (val === answer) {
        if (selected && selected.value === answer) { opt.classList.add('correct'); correct++; }
        else opt.classList.add('reveal-correct');
      } else if (selected && val === selected.value) {
        opt.classList.add('wrong');
      }
    });
  });
  const lbl = document.getElementById('score-' + id);
  lbl.textContent = correct + ' / ' + questions.length;
  lbl.style.color = correct === questions.length ? '#22c55e'
    : correct >= Math.ceil(questions.length * 0.6) ? '#e8c860' : '#f87171';
  quiz.querySelector('.quiz-submit-btn').disabled = true;
  quiz.querySelectorAll('input[type=radio]').forEach(i => i.disabled = true);
  document.getElementById('reset-' + id).style.display = 'inline-block';
}

function resetQuiz(id) {
  const quiz = document.getElementById('quiz-' + id);
  quiz.querySelectorAll('.quiz-opt').forEach(o =>
    o.classList.remove('selected','correct','wrong','reveal-correct'));
  quiz.querySelectorAll('input[type=radio]').forEach(i => { i.checked = false; i.disabled = false; });
  document.getElementById('score-' + id).textContent = '';
  document.getElementById('reset-' + id).style.display = 'none';
  quiz.querySelector('.quiz-submit-btn').disabled = false;
}

document.addEventListener('change', e => {
  if (e.target.type !== 'radio' || !e.target.name.startsWith('q-')) return;
  const nm = e.target.name;
  document.querySelectorAll('input[name="' + nm + '"]').forEach(r =>
    r.closest('.quiz-opt').classList.toggle('selected', r.checked));
});

"""


# ── Helper to build a quiz slide ──────────────────────────────────────────────
def opt(key, text):
    return (
        f'<label class="quiz-opt">'
        f'<input type="radio" name="QNAME" value="{key}">'
        f'<span class="quiz-key">{key}</span>{text}</label>'
    )


def quiz_slide(deck_id, deck_label, slide_num, total, questions):
    """
    questions: list of (question_text, answer_key, [(key, text), ...])
    """
    qs_html = []
    for i, (qtext, ans, opts_list) in enumerate(questions, 1):
        name = f'q-{deck_id}-{i}'
        opts_html = '\n                  '.join(
            f'<label class="quiz-opt">'
            f'<input type="radio" name="{name}" value="{k}">'
            f'<span class="quiz-key">{k}</span>{t}</label>'
            for k, t in opts_list
        )
        qs_html.append(
            f'              <div class="quiz-q" data-answer="{ans}">\n'
            f'                <div class="quiz-q-text">{i}. {qtext}</div>\n'
            f'                <div class="quiz-opts">\n'
            f'                  {opts_html}\n'
            f'                </div>\n'
            f'              </div>'
        )

    grid = '\n'.join(qs_html)
    return f'''
        <!-- ── QUIZ SLIDE ── -->
        <div class="slide">
          <div class="sl-num">{deck_label.upper()} · SLIDE {slide_num} / {total}</div>
          <div class="sl-title">Knowledge Check</div>
          <div class="sl-sub">{deck_label} — 5 questions &nbsp;·&nbsp; Select the best answer then click Check</div>
          <div class="sl-rule"></div>
          <div id="quiz-{deck_id}">
            <div class="quiz-grid">
{grid}
            </div>
            <div class="quiz-actions">
              <button class="quiz-submit-btn" onclick="checkQuiz('{deck_id}')">Check Answers</button>
              <span class="quiz-score-lbl" id="score-{deck_id}"></span>
              <button class="quiz-reset-btn" id="reset-{deck_id}" onclick="resetQuiz('{deck_id}')">Try Again</button>
            </div>
          </div>
        </div>'''


# ── Quiz content per deck ─────────────────────────────────────────────────────
QUIZZES = {
    'fix': ('Market Protocols', 23, 23, [
        ('Which FIX tag carries the message type?',
         'C', [('A','Tag 8 — BeginString'), ('B','Tag 49 — SenderCompID'),
               ('C','Tag 35 — MsgType'), ('D','Tag 10 — CheckSum')]),
        ('A FIX Execution Report with OrdStatus=8 means the order was:',
         'B', [('A','Filled'), ('B','Rejected'), ('C','Cancelled'), ('D','Partially Filled')]),
        ('The FIX CheckSum (tag 10) is the:',
         'C', [('A','SHA-256 hash of the body'), ('B','CRC32 of all fields'),
               ('C','Sum of all byte values mod 256'), ('D','Message length in bytes')]),
        ('ITCH differs from FIX because ITCH is:',
         'B', [('A','XML-based and bidirectional'), ('B','Binary and unidirectional market-data broadcast'),
               ('C','Text-based with encryption'), ('D','Used only for order cancellation')]),
        ('SenderCompID and TargetCompID appear in which section of a FIX message?',
         'D', [('A','Body'), ('B','Trailer'), ('C','Footer'), ('D','Header')]),
    ]),

    'kafka': ('Kafka', 9, 9, [
        ('In Kafka, message ordering is guaranteed within a:',
         'C', [('A','Topic'), ('B','Consumer Group'), ('C','Partition'), ('D','Broker')]),
        ('A producer with acks=all requires acknowledgment from:',
         'D', [('A','The leader only'), ('B','A majority quorum'),
               ('C','No broker'), ('D','All in-sync replicas')]),
        ('When max.poll.interval.ms is exceeded the consumer is:',
         'B', [('A','Paused temporarily'), ('B','Removed from the group and rebalance triggers'),
               ('C','Throttled by the broker'), ('D','Sent a retry signal')]),
        ('The __consumer_offsets topic stores:',
         'C', [('A','Message payloads'), ('B','Topic configurations'),
               ('C','Committed offsets for consumer groups'), ('D','Producer acknowledgments')]),
        ('With replication factor 3 and min.insync.replicas=2, how many broker failures can you sustain while still accepting writes?',
         'B', [('A','0'), ('B','1'), ('C','2'), ('D','3')]),
    ]),

    'k8s': ('Kubernetes & Argo', 10, 10, [
        ('Which Kubernetes object ensures N replicas of a pod always run?',
         'C', [('A','DaemonSet'), ('B','Job'), ('C','ReplicaSet'), ('D','StatefulSet')]),
        ('kubectl rollout undo deployment/myapp does what?',
         'C', [('A','Deletes the deployment'), ('B','Scales the deployment to zero'),
               ('C','Rolls back to the previous ReplicaSet'), ('D','Pauses the rollout')]),
        ('A pod in CrashLoopBackOff state means:',
         'B', [('A','The image cannot be pulled'), ('B','The container starts and immediately crashes, repeatedly'),
               ('C','A network policy is blocking traffic'), ('D','The node has insufficient resources')]),
        ('In Argo Workflows, a DAG template specifies:',
         'D', [('A','Resource limits for pods'), ('B','Artifact storage locations'),
               ('C','Retry policies for failed steps'), ('D','Task dependencies via a directed acyclic graph')]),
        ('Which command shows logs from the previous (crashed) container instance?',
         'A', [('A','kubectl logs &lt;pod&gt; --previous'), ('B','kubectl logs &lt;pod&gt; -c prev'),
               ('C','kubectl get logs --last'), ('D','kubectl describe pod | grep logs')]),
    ]),

    'marketdata': ('Market Data', 9, 9, [
        ('HDF5 organizes data using which hierarchical structure?',
         'D', [('A','Tables and rows'), ('B','Collections and documents'),
               ('C','Shards and segments'), ('D','Groups and datasets')]),
        ('VWAP is calculated as:',
         'B', [('A','(High + Low + Close) / 3'), ('B','Sum(price x volume) / Sum(volume)'),
               ('C','Total volume divided by time elapsed'), ('D','Average of all trade prices')]),
        ('A "sequence gap" in a market data feed most likely indicates:',
         'C', [('A','A stale price'), ('B','A slow consumer'),
               ('C','Dropped UDP packets causing missed messages'), ('D','Planned exchange maintenance')]),
        ('L2 order book data shows:',
         'D', [('A','Only the best bid and offer (L1 data)'), ('B','Historical OHLCV bars'),
               ('C','Last trade price only'), ('D','Full depth — all price levels and their quantities')]),
        ('Which storage format is most common for HFT tick data in quant finance?',
         'C', [('A','CSV'), ('B','JSON'), ('C','HDF5 or Parquet'), ('D','XML')]),
    ]),

    'sql': ('SQL', 8, 8, [
        ('Which window function returns the previous row\'s value?',
         'B', [('A','RANK()'), ('B','LAG()'), ('C','ROW_NUMBER()'), ('D','LEAD()')]),
        ('The EXCEPT operator returns:',
         'C', [('A','All rows from both queries'), ('B','Rows present only in the second query'),
               ('C','Rows in the first query that are not in the second'), ('D','Only matching rows')]),
        ('A LEFT JOIN returns:',
         'D', [('A','Only matching rows'), ('B','The Cartesian product'),
               ('C','All rows from the right table'), ('D','All rows from the left table; NULLs where right has no match')]),
        ('To find sequence gaps in tick data, which approach is most efficient?',
         'D', [('A','UNION ALL then filter'), ('B','GROUP BY with HAVING'),
               ('C','DISTINCT and ORDER BY'), ('D','LAG() window function comparing consecutive sequence numbers')]),
        ('Which isolation level prevents dirty reads but allows non-repeatable reads?',
         'D', [('A','Serializable'), ('B','Read Uncommitted'),
               ('C','Repeatable Read'), ('D','Read Committed')]),
    ]),

    'airflow': ('Airflow', 9, 9, [
        ('Using datetime.now() inside an Airflow task breaks:',
         'C', [('A','Timezone conversion'), ('B','Worker scheduling'),
               ('C','Idempotency — reruns produce different timestamps'), ('D','DAG file parsing')]),
        ('Airflow\'s execution_date represents:',
         'B', [('A','When the task actually started'), ('B','The logical interval start (data interval start)'),
               ('C','The current wall-clock time'), ('D','The DAG file modification time')]),
        ('Sensor mode="reschedule" differs from mode="poke" because it:',
         'C', [('A','Runs in a subprocess'), ('B','Never retries on failure'),
               ('C','Releases the worker slot between checks'), ('D','Checks more frequently')]),
        ('To re-run a failed task for a specific past date without re-running other tasks you should:',
         'C', [('A','Delete and recreate the DAG'), ('B','Use backfill --reset-dagruns'),
               ('C','Clear the specific task instances for that run'), ('D','Trigger the DAG with --exec-date')]),
        ('Which concept means a task can run multiple times and always produce the same result?',
         'D', [('A','Parallelism'), ('B','Atomicity'), ('C','Backpressure'), ('D','Idempotency')]),
    ]),

    'linux': ('Linux & Systems', 7, 7, [
        ('Which command shows real-time CPU and memory usage per process?',
         'C', [('A','ps aux'), ('B','vmstat'), ('C','top or htop'), ('D','lsof')]),
        ('lsof -i :8080 shows:',
         'B', [('A','Files modified at timestamp 8080'), ('B','Processes using port 8080'),
               ('C','Memory usage of PID 8080'), ('D','Network packets captured on port 8080')]),
        ('A zombie process is one that:',
         'C', [('A','Consumes 100% CPU'), ('B','Is blocked on I/O'),
               ('C','Has exited but whose parent has not yet called wait()'), ('D','Has no controlling TTY')]),
        ('ulimit -n controls:',
         'D', [('A','Maximum number of processes'), ('B','Stack size limit'),
               ('C','Network buffer size'), ('D','Maximum file descriptor count per process')]),
        ('journalctl -u myservice --since "1 hour ago" does what?',
         'C', [('A','Starts and monitors the service'), ('B','Checks service health status'),
               ('C','Shows systemd journal logs for myservice from the past hour'), ('D','Rotates log files older than one hour')]),
    ]),

    'python': ('Python & Bash', 9, 9, [
        ('asyncio.gather() is used to:',
         'D', [('A','Synchronize threads'), ('B','Cancel running tasks'),
               ('C','Schedule tasks for a future time'), ('D','Run multiple coroutines concurrently')]),
        ('A Python @dataclass with frozen=True makes instances:',
         'C', [('A','JSON-serializable by default'), ('B','Thread-safe'),
               ('C','Immutable and hashable'), ('D','Automatically pickleable')]),
        ('In Bash, set -e causes the script to:',
         'D', [('A','Export all variables automatically'), ('B','Suppress error messages'),
               ('C','Echo every command before executing'), ('D','Exit immediately on any non-zero return code')]),
        ('pandas.DataFrame.merge(how="left") is equivalent to which SQL join?',
         'B', [('A','INNER JOIN'), ('B','LEFT OUTER JOIN'),
               ('C','RIGHT OUTER JOIN'), ('D','FULL OUTER JOIN')]),
        ('For high-performance numerical arrays stored in HDF5, the standard Python libraries are:',
         'C', [('A','pandas + sqlite3'), ('B','scipy + netCDF4'),
               ('C','numpy + h5py'), ('D','polars + duckdb')]),
    ]),

    'aws': ('AWS', 6, 6, [
        ('AWS Lambda\'s maximum execution timeout is:',
         'D', [('A','5 minutes'), ('B','10 minutes'), ('C','30 minutes'), ('D','15 minutes')]),
        ('Amazon SQS FIFO queues guarantee:',
         'C', [('A','Higher throughput than Standard queues'), ('B','At-least-once delivery only'),
               ('C','Message ordering and exactly-once processing'), ('D','Free retries for all failures')]),
        ('EKS Node Groups use which underlying AWS resource?',
         'D', [('A','ECS tasks'), ('B','EMR clusters'),
               ('C','Fargate profiles'), ('D','EC2 Auto Scaling Groups')]),
        ('CloudWatch Logs Insights is best used for:',
         'C', [('A','Setting billing alarms'), ('B','Real-time metric dashboards'),
               ('C','Querying log data with a SQL-like syntax'), ('D','Tracing Lambda invocations end-to-end')]),
        ('An S3 lifecycle rule that transitions objects to Glacier after 90 days applies to:',
         'A', [('A','Current object versions'), ('B','All versions including delete markers'),
               ('C','Only deleted objects'), ('D','Only objects with specific tags')]),
    ]),

    'networking': ('Networking', 5, 5, [
        ('TCP\'s three-way handshake sequence is:',
         'D', [('A','SYN → ACK → SYN-ACK'), ('B','ACK → SYN → FIN'),
               ('C','SYN → FIN → ACK'), ('D','SYN → SYN-ACK → ACK')]),
        ('UDP is preferred over TCP for market data feeds because:',
         'C', [('A','UDP guarantees delivery'), ('B','UDP has built-in congestion control'),
               ('C','UDP has lower latency — no retransmission or connection overhead'), ('D','UDP supports larger packet sizes')]),
        ('An MTU of 1500 bytes defines the:',
         'D', [('A','Max throughput in Mbps'), ('B','Max concurrent TCP connections'),
               ('C','Max segment size at the TCP layer'), ('D','Maximum Layer 2 frame payload size')]),
        ('Multicast in trading systems is used to:',
         'B', [('A','Encrypt peer-to-peer order routing'), ('B','Deliver the same market data to many subscribers simultaneously'),
               ('C','Load-balance orders across brokers'), ('D','Store historical tick data')]),
        ('Which protocol does ITCH use for transport, and why?',
         'A', [('A','UDP Multicast — low latency, supports many receivers with one stream'),
               ('B','TCP — guaranteed delivery is required for order book integrity'),
               ('C','HTTP/2 — for compatibility with web clients'),
               ('D','FIX over TCP — to reuse existing FIX infrastructure')]),
    ]),

    'git': ('Git', 5, 5, [
        ('git rebase main on a feature branch does what?',
         'C', [('A','Merges main into the feature branch with a merge commit'),
               ('B','Resets the feature branch to exactly match main'),
               ('C','Replays feature commits on top of main\'s latest tip'),
               ('D','Creates a new branch from main')]),
        ('git stash pop differs from git stash apply in that it:',
         'D', [('A','Applies only the latest stash'), ('B','Applies changes to a specific file'),
               ('C','Creates a new branch from the stash'), ('D','Also removes the stash entry after applying it')]),
        ('git cherry-pick &lt;commit&gt; does what?',
         'C', [('A','Merges an entire branch'), ('B','Tags a commit for release'),
               ('C','Copies a specific commit\'s changes onto the current branch'), ('D','Reverts a commit from history')]),
        ('git reflog is most useful for:',
         'D', [('A','Comparing two branches'), ('B','Listing all remote branch names'),
               ('C','Viewing tag history'), ('D','Recovering commits lost after a reset or rebase')]),
        ('What does git bisect do?',
         'B', [('A','Splits a commit into two smaller commits'),
               ('B','Binary-searches commit history to find the commit that introduced a bug'),
               ('C','Compares two branches and highlights divergence'),
               ('D','Merges two branches without creating a merge commit')]),
    ]),

    'support': ('Support & Incidents', 8, 8, [
        ('During a production incident, your first priority should be:',
         'C', [('A','Document the full timeline'), ('B','Identify the root cause'),
               ('C','Restore service and reduce customer impact'), ('D','Notify all stakeholders')]),
        ('A P1/Sev1 incident typically means:',
         'C', [('A','A non-critical bug in non-production'), ('B','Performance degradation under 10%'),
               ('C','Complete production outage or data loss'), ('D','A security vulnerability in a dev environment')]),
        ('The "Five Whys" post-mortem technique is used to:',
         'D', [('A','Rank incident severity'), ('B','Estimate recovery time'),
               ('C','Assign responsibility to teams'), ('D','Iteratively drill down to identify root cause')]),
        ('A sequence gap alert from the market data feed most likely indicates:',
         'B', [('A','A slow downstream consumer'), ('B','Dropped UDP packets causing missed messages'),
               ('C','Planned exchange maintenance'), ('D','A stale cached price')]),
        ('A runbook\'s primary content should be:',
         'D', [('A','System architecture diagrams'), ('B','Code review guidelines'),
               ('C','Business requirements'), ('D','Step-by-step procedures for known failure scenarios')]),
    ]),

    'interview': ('Interview Prep', 7, 7, [
        ('When introducing yourself in a technical interview, the best structure is:',
         'D', [('A','Your life story chronologically'), ('B','Your biggest weakness first'),
               ('C','A complete list of technical skills'), ('D','Current role → relevant experience → why this role')]),
        ('Behavioral stories about debugging incidents best follow which framework?',
         'B', [('A','CAR (Challenge, Action, Result)'), ('B','STAR (Situation, Task, Action, Result)'),
               ('C','MECE framework'), ('D','Agile retrospective format')]),
        ('VWAP is most useful in trading because it:',
         'D', [('A','Predicts future price movements'), ('B','Determines order routing priority'),
               ('C','Calculates real-time position P&amp;L'), ('D','Measures execution quality vs. the volume-weighted average market price')]),
        ('For "what\'s your biggest weakness," the best approach is:',
         'C', [('A','Claim you have none'), ('B','Mention a strength disguised as a weakness'),
               ('C','Name a real weakness with concrete steps you are taking to improve it'), ('D','Choose a weakness unrelated to the role')]),
        ('"How would you detect a stale market data feed?" tests your knowledge of:',
         'D', [('A','SQL query optimization'), ('B','Cloud storage pricing'),
               ('C','Network topology design'), ('D','Sequence number monitoring, timestamp lag detection, and alerting')]),
    ]),
}

# ── Old COUNTS and new COUNTS ─────────────────────────────────────────────────
OLD_COUNTS = (
    'const COUNTS = {\n'
    '  fix: 22, kafka: 8, k8s: 9, marketdata: 8,\n'
    '  sql: 7, airflow: 8, linux: 6, python: 8,\n'
    '  aws: 5, networking: 4, git: 4, support: 7, interview: 6\n'
    '};'
)
NEW_COUNTS = (
    'const COUNTS = {\n'
    '  fix: 23, kafka: 9, k8s: 10, marketdata: 9,\n'
    '  sql: 8, airflow: 9, linux: 7, python: 9,\n'
    '  aws: 6, networking: 5, git: 5, support: 8, interview: 7\n'
    '};'
)

# Badge replacements: old badge → new badge (using surrounding context to be precise)
BADGE_UPDATES = [
    # fix
    ('Market Protocols\n      <span class="badge">22</span>',
     'Market Protocols\n      <span class="badge">23</span>'),
    # kafka
    ('Kafka\n      <span class="badge">8</span>',
     'Kafka\n      <span class="badge">9</span>'),
    # k8s
    ('Kubernetes &amp; Argo\n      <span class="badge">9</span>',
     'Kubernetes &amp; Argo\n      <span class="badge">10</span>'),
    # marketdata
    ('Market Data\n      <span class="badge">8</span>',
     'Market Data\n      <span class="badge">9</span>'),
    # sql
    ('SQL\n      <span class="badge">7</span>',
     'SQL\n      <span class="badge">8</span>'),
    # airflow
    ('Airflow\n      <span class="badge">8</span>',
     'Airflow\n      <span class="badge">9</span>'),
    # linux
    ('Linux &amp; Systems\n      <span class="badge">6</span>',
     'Linux &amp; Systems\n      <span class="badge">7</span>'),
    # python — badge was 5, COUNTS was 8, new is 9
    ('Python &amp; Bash\n      <span class="badge">5</span>',
     'Python &amp; Bash\n      <span class="badge">9</span>'),
    # aws
    ('AWS\n      <span class="badge">5</span>',
     'AWS\n      <span class="badge">6</span>'),
    # networking
    ('Networking\n      <span class="badge">4</span>',
     'Networking\n      <span class="badge">5</span>'),
    # git
    ('Git\n      <span class="badge">4</span>',
     'Git\n      <span class="badge">5</span>'),
    # support
    ('Support &amp; Incidents\n      <span class="badge">7</span>',
     'Support &amp; Incidents\n      <span class="badge">8</span>'),
    # interview
    ('Interview Prep\n      <span class="badge">6</span>',
     'Interview Prep\n      <span class="badge">7</span>'),
]

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    html = SRC.read_text(encoding='utf-8')

    # 1. CSS
    assert '</style>' in html, 'Could not find </style>'
    html = html.replace('</style>', QUIZ_CSS + '</style>', 1)
    print('OK CSS injected')

    # 2. JS
    marker = '// -- Keyboard --'
    marker2 = '// ── Keyboard ──'
    if marker2 in html:
        html = html.replace(marker2, QUIZ_JS + marker2, 1)
    elif marker in html:
        html = html.replace(marker, QUIZ_JS + marker, 1)
    else:
        raise ValueError('Could not find Keyboard section in JS')
    print('OK JS injected')

    # 3. COUNTS
    if OLD_COUNTS not in html:
        raise ValueError('Could not find OLD_COUNTS — already patched?')
    html = html.replace(OLD_COUNTS, NEW_COUNTS, 1)
    print('OK COUNTS updated')

    # 4. Badges
    for old, new in BADGE_UPDATES:
        if old not in html:
            print(f'  WARN badge not found: {old[:40]!r}')
        else:
            html = html.replace(old, new, 1)
    print('OK badges updated')

    # 5. Quiz slides — insert before each deck's slide-nav
    for deck_id, (label, slide_num, total, questions) in QUIZZES.items():
        marker = (
            f'      </div>\n'
            f'      <div class="slide-nav">\n'
            f'        <button class="nav-btn" id="prev-{deck_id}"'
        )
        if marker not in html:
            print(f'  WARN insertion point not found for deck: {deck_id}')
            continue
        slide_html = quiz_slide(deck_id, label, slide_num, total, questions)
        replacement = (
            slide_html + '\n'
            f'      </div>\n'
            f'      <div class="slide-nav">\n'
            f'        <button class="nav-btn" id="prev-{deck_id}"'
        )
        html = html.replace(marker, replacement, 1)
        print(f'OK quiz slide inserted: {deck_id}')

    SRC.write_text(html, encoding='utf-8')
    print(f'\nDone — {SRC}')


if __name__ == '__main__':
    main()
