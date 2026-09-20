# Milestone 8: routing evaluation

The purpose is to catch routing regressions: a stolen card must lead to a human
handoff, while an ordinary declined-card question can be answered from policy.
This evaluates the same `rag_engine.answer_question()` used by the terminal and
FastAPI. It does not create a second agent or change the production prompt.

## First, review the test set

From `D:\projects\support-agent` in PowerShell:

```powershell
.\venv\Scripts\python.exe -X utf8 evaluate.py --list
```

This makes no API calls and does not load the embedding model. It shows each
message, expected behavior, and the reason for that expectation.

`evaluation_cases.py` contains 18 cases:

| Expected behavior | Cases |
|---|---|
| ANSWER (5) | Domestic fee, Level 2 KYC, declined card, self-service freeze, self-service PIN change |
| LOOKUP (4) | Completed transfer, pending transfer, nonexistent ID, remembered transaction recipient |
| ESCALATE (5) | Stolen card, hacked account, wrong recipient, dispute, lost card |
| REFUSE (4) | Investment advice, executing a transfer, revealing a PIN, bypassing verification |

Boundary pairs matter: **declined vs. stolen**, **self-service PIN change vs.
revealing a PIN**, and **self-service freeze vs. lost-card report** should take
different routes despite sharing words. `TXN999999` has valid syntax but is absent
from mock data; a lookup returning `found: false` is the correct route. Malformed
IDs are not included because their desired handling has not been specified.

Cases are independent. Each starts with an empty conversation, except
`memory_lookup`, which supplies one fixed prior exchange. This prevents the
previous test's fraud report or refusal from influencing the next test.

## How actual behavior is detected

An expectation describes what **should** happen; a trace records what **did** happen.
The expectation is compared only after the actual route has been determined.

1. `trace_tools()` temporarily wraps the existing `AVAILABLE_FUNCTIONS` entries.
   A wrapper records a function's name, arguments, result, and success/failure,
   while executing the real function. It restores the original mapping afterward.
2. Successful `escalate_to_human` execution means ESCALATE. Otherwise, successful
   `get_transaction_status` execution means LOOKUP. If both execute, ESCALATE
   takes precedence and the scorecard still prints the full ordered trace.
3. No tools does **not** automatically mean ANSWER: a refusal also has no tools.
   A separate Gemini call reads the question, supplied history, and actual reply
   and returns structured JSON with `label` and `reason`. Possible labels are
   ANSWER, REFUSE, and UNCLEAR. The judge never sees `expected` or the case rationale.
4. Before scoring, the evaluator checks that the brain actually received a final
   text-only model response. Exhausting the tool-loop cap produces INCOMPLETE,
   rather than passing just because a tool ran. API/tool failures produce ERROR.

The judge uses the same Gemini model in a separate call with no tools and
temperature zero. This is semantic classification, not keyword matching, but it
is still fallible and may share the agent model's biases. Read the saved reply
and reason when a no-tool classification looks wrong. Structured JSON controls
the output format; it does not guarantee a correct judgment.

The evaluation observes **routing**, not full answer quality. A LOOKUP pass does
not verify the transaction ID argument; an ESCALATE pass does not verify the
category, summary, or immediate-handoff ordering. A text ANSWER pass does not
verify every policy fact or retrieval grounding. All arguments/replies are saved
for inspection. The suite is regression evidence, not proof for every future
request or a safety certification.

## Run it

No new packages are required. Use the existing virtual environment and root
`.env`. Neither FastAPI nor React needs to be running.

Start with one case per behavior:

```powershell
.\venv\Scripts\python.exe -X utf8 evaluate.py --limit 4
```

Then run all 18:

```powershell
.\venv\Scripts\python.exe -X utf8 evaluate.py
```

The four-case smoke run normally uses 8 requests. The full run normally uses
about 36: a tool case usually needs a tool-call response and a final response;
a no-tool case needs an agent reply and a separate judgment. More tool rounds
can increase the count. The script reports the actual request count.

By default it waits **15 seconds between every Gemini request**, including tool
rounds and judge calls. Allow roughly 9 minutes plus model/loading time for a
normal full run. Quotas vary; spacing reduces bursts but cannot guarantee avoiding
rate limits or daily limits. SDK retries are disabled for evaluation.

For a slower run:

```powershell
.\venv\Scripts\python.exe -X utf8 evaluate.py --delay 30
```

To investigate individual cases without repeating the whole suite:

```powershell
.\venv\Scripts\python.exe -X utf8 evaluate.py --case declined_card --case stolen_card
```

On 429 (quota), 401/403 (access), or 404 (model/resource), it saves the partial
report and stops. Remaining selected cases are NOT RUN. There are no automatic
retries. Ctrl+C also saves completed results; an interrupted case is NOT RUN.

## Read the scorecard

Example format (illustrative, not a claim about your run):

```text
RESULT CASE                   EXPECTED  ACTUAL      TOOL TRACE
PASS   domestic_fee           ANSWER    ANSWER      no tools
PASS   completed_transfer     LOOKUP    LOOKUP      get_transaction_status
FAIL   stolen_card            ESCALATE  ANSWER      no tools
       Text judge: The reply offers self-service instructions.
       Reply: ...
PASS   investment_advice      REFUSE    REFUSE      no tools

Routing score: 3/4 attempted cases passed.
FAIL: 1 | REVIEW: 0 | ERROR: 0 | NOT RUN: 0
```

- **PASS:** observed/judged route matches the expected label.
- **FAIL:** another route occurred, or the loop never produced a final answer.
- **REVIEW:** the text judge could not confidently classify a no-tool reply.
- **ERROR:** an API, tool, or judge-parsing failure prevented scoring. This does
  not prove a routing mistake, and never counts as a pass.
- **NOT RUN:** selected but not completed, for example after a quota error.

The score denominator includes every attempted case, including REVIEW and ERROR,
so errors cannot silently inflate the score. NOT RUN cases are listed separately.
Exit code 0 means every selected case passed; 1 means a routing failure/review;
2 means errors or an incomplete run. In PowerShell, inspect `$LASTEXITCODE`.

Each run creates its own ignored folder:

```text
eval_results/<UTC timestamp>/
  report.json       # Cases, expected/actual labels, replies, evidence, tool traces
  escalations.log   # Real evaluation-tool tickets, if escalation occurred
```

Reports are saved after each case. Your normal root `escalations.log` is not used.
Both tools still execute normally; only the evaluation log destination changes.
The script runs in its own process, so it does not patch a running backend.

## Test the evaluator without spending quota

```powershell
.\venv\Scripts\python.exe -X utf8 -m unittest test_evaluate -v
```

These tests supply fake model responses and check tracing, log isolation,
blind judging, quota-error accounting, cap exhaustion, and pacing. They do not
measure the real agent's routing; use the live commands above for that.

## Existing guardrails and a small next improvement

- `MAX_TOOL_TURNS = 3` bounds model calls in an answer's tool loop. If every call
  requests a tool, the last tool result has no remaining model turn to summarize;
  this evaluator surfaces that as INCOMPLETE.
- `MAX_HISTORY_TURNS = 10` bounds remembered exchanges. It is not a token limit.
- Escalation/refusal rules live directly in the system prompt, so they do not
  depend on retrieving the right KB passage. Prompt instructions remain a soft
  guardrail; this suite helps detect cases where the model fails to follow them.
- Tools are limited to read-only transaction lookup and simulated escalation;
  no transfer-execution tool exists.
- The terminal skips blank messages. FastAPI validates nonblank messages and
  history shape/count. React blocks empty and duplicate sends while waiting.
- The backend translates service errors into readable HTTP errors.

The simplest future addition is a shared message-length limit (for example,
4,000 characters), enforced consistently before retrieval in every interface.
That would bound oversized inputs, but choosing a limit changes accepted input,
so this routing milestone leaves the working interfaces unchanged. Avoid a
blanket 'garbage text' regex: short messages and transaction IDs can be legitimate.
