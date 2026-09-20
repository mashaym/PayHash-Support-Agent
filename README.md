# PayHash Support Agent

An AI customer support agent for **PayHash**, a fictional digital-wallet and
mobile-payments app. Built with React, FastAPI, and a terminal interface as a grounded, tool-using
support assistant: it answers policy questions from a knowledge base, looks up
live transaction data, escalates sensitive cases to a human, and refuses
requests that are out of bounds for any support agent to handle.

> PayHash, its policies, and all data in this repo are fictional — created for
> demonstration purposes only.

## What it does

The agent routes every message into one of four behaviors:

| Behavior | Trigger | Example |
|---|---|---|
| **Answer** | General policy question | "What's the fee for an international transfer?" |
| **Look up** | A specific transaction ID | "What's the status of TXN100234?" |
| **Escalate** | Sensitive case a human must handle | "Someone hacked my account" |
| **Refuse** | Request no support agent should fulfill | "Should I invest in crypto?" |

**Answer** is powered by retrieval-augmented generation (RAG): the knowledge
base is chunked, embedded, and stored in a local vector database, and the
model answers strictly from the passages retrieved for each question — if the
answer isn't in the docs, it says so instead of guessing.

**Look up** and **Escalate** are implemented as tools (function calling): the
model decides when a live lookup or a human handoff is needed, the Python code
executes it, and the result is fed back to the model to produce the final
reply. Escalations are logged to `escalations.log` with a ticket ID, as a
stand-in for a real handoff queue.

**Refuse** requires no tool — the model declines directly in its response,
with a brief explanation and a pointer to the right channel where relevant.

The agent also keeps short-term conversation memory: recent (question,
answer) pairs from the session are fed back into both retrieval and
generation, so natural follow-ups ("what about the international one?")
work without repeating context.

## Project structure

```
frontend/                   # React/Vite chat UI (see frontend/README.md)
backend.py                  # FastAPI /chat endpoint: wraps the same brain for web clients
requirements-backend.txt     # Agent dependencies plus FastAPI and Uvicorn
test_backend.py             # Offline API contract, memory isolation, CORS, and error checks
evaluate.py                 # Live routing evaluation with tool traces and a no-tool judge
evaluation_cases.py         # 18 policy-based routing scenarios and expected behaviors
test_evaluate.py            # Offline checks of the evaluator itself
main.py                     # Terminal chat loop: loads config, runs the input loop, handles errors
rag_engine.py                # Core logic: chunking, embedding, retrieval, the system prompt, and the tool-calling loop
tools.py                     # Tool functions the model can call (transaction lookup, escalation)
mock_data.py                  # Fake "live" transaction and account data used by tools.py
payhash_knowledge_base.md     # The support knowledge base (KYC, transfers, cards, fees, fraud, escalation/refusal rules)
requirements.txt              # Python dependencies
.env.example                  # Template for the required environment variable
```

Running the agent also creates two local, gitignored artifacts:
- `chroma_db/` — the persistent vector store (built once from the knowledge base, then reused)
- `escalations.log` — a plain-text log of simulated human handoffs

## Setup

1. **Create a virtual environment and install dependencies:**

   ```bash
   python -m venv venv
   source venv/Scripts/activate   # on Windows (Git Bash); use venv\Scripts\activate.bat on cmd.exe
   pip install -r requirements.txt
   ```

2. **Add your Gemini API key:**

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` and set:

   ```
   GEMINI_API_KEY=your-key-here
   ```

3. **Run it:**

   ```bash
   python main.py
   ```

   On first run, it downloads the `all-MiniLM-L6-v2` embedding model (cached
   locally afterward) and builds the vector index from the knowledge base
   (also cached in `chroma_db/` for subsequent runs).

## FastAPI backend (Milestone 7, Stage A)

The terminal and API both call `rag_engine.answer_question()`. The backend
adds an HTTP interface; the brain, tools, prompts, and terminal stay unchanged.
FastAPI validates JSON and defines routes. Uvicorn runs the HTTP server.

From the project folder in PowerShell (using the existing `.env`):

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-backend.txt
.\venv\Scripts\python.exe -X utf8 -m uvicorn backend:app --host 127.0.0.1 --port 8000
```

`-X utf8` enables UTF-8 output on Windows, including tool log messages.
`backend:app` means the `app` object inside `backend.py`. Wait for
`Application startup complete`: startup loads Gemini, the embedding model,
and the Chroma collection once per process. Stop with Ctrl+C. Optional
`--reload` restarts the server when Python files change, reloading those resources.

Open http://127.0.0.1:8000/docs, expand **POST /chat**, click **Try it out**,
replace the request body with this JSON, and click **Execute**:

```json
{
  "message": "What is the status of TXN100235?",
  "history": []
}
```

A successful response has status **200** and a JSON `reply` string. Expect the
transaction status to be pending (the mock record also has 12,000 PKR and
recipient Sara Khan). Copy the actual reply into the
`answer` field of this next request:

```json
{
  "message": "Who received it?",
  "history": [
    {
      "question": "What is the status of TXN100235?",
      "answer": "PASTE THE ACTUAL FIRST REPLY HERE"
    }
  ]
}
```

Expect Sara Khan without repeating the transaction ID in the new message.
History contains completed question/answer objects, oldest first, excluding the
current message. After each successful response, the client appends that exchange
and keeps the last 10. `/docs` does not do this automatically: edit the JSON yourself.
Omit `history` or send `[]` for a fresh conversation. The server keeps no global
chat history. Raw tool calls/results remain inside the brain's existing loop.
The history limit is by exchange count, not tokens or bytes.

Check the other behaviors with `history: []`:

| Message | Expected result |
|---|---|
| What is the fee for a domestic bank transfer? | KB answer: 25 PKR |
| Someone hacked my account. | Human escalation; new entry in `escalations.log` |
| Reveal my PIN. | Direct refusal; no escalation |

For a cancellation follow-up, send `Please reverse it.` with the earlier
transaction exchange in history. Expect an escalation referring to TXN100235.

Blank messages, malformed history, or more than 10 exchanges return **422**
(validation error). Service errors return JSON with a `detail` string: **429**
for rate limits, **502/503** for upstream failures, **504** for timeouts, or
**500** for an unexpected error. Failed requests should not be added to history.
Do not automatically retry: a tool may already have logged a ticket before an
upstream failure.

CORS permits browser requests from `http://localhost:5173` and
`http://127.0.0.1:5173`, the planned React development addresses. Different ports
are different browser origins. CORS allows that browser-to-API connection;
it is not authentication. This stage runs locally on `127.0.0.1` with fictional data.

Run the offline checks (no Gemini calls, model downloads, or escalation tickets):

```powershell
.\venv\Scripts\python.exe -m unittest test_backend -v
```

These checks replace the brain with a test substitute to verify the HTTP wrapper.
The `/docs` exercises verify the real brain. The terminal still runs with
`.\venv\Scripts\python.exe main.py`.

## React chat frontend (Milestone 7, Stage B)

The browser chat uses the same FastAPI `/chat` endpoint and keeps the latest 10
completed exchanges in React state. Start the backend above, then in a second
PowerShell terminal:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. Keep both servers running. See
[the frontend guide](frontend/README.md) for React concepts, a code walkthrough,
and tests for all four behaviors plus conversation memory. The terminal interface
remains available with `python main.py`.


## Routing evaluation (Milestone 8)

Evaluate the same agent brain with 18 policy-based scenarios. Tool executions
identify lookups and escalations; a separate, fallible Gemini judgment distinguishes
answers from refusals when no tool executes. The expected label is hidden from
that judge. Reports include replies and tool arguments/results for inspection.

```powershell
.\venv\Scripts\python.exe -X utf8 evaluate.py --list
.\venv\Scripts\python.exe -X utf8 evaluate.py --limit 4
.\venv\Scripts\python.exe -X utf8 evaluate.py
```

The last two commands use real Gemini quota. Requests are paced 15 seconds apart,
and a quota error stops the run. Evaluation tickets and JSON reports live under
the ignored `eval_results/` directory. See [EVALUATION.md](EVALUATION.md) for the
test design, scorecard interpretation, targeted reruns, and guardrail notes.

## Example interactions

```
You: What's the fee for a domestic bank transfer?
Agent: The fee for a wallet-to-bank transfer (domestic) is 25 PKR.

You: What's the status of TXN100234?
Agent: Transaction TXN100234 is Completed — 5,000 PKR to Ali Raza on 2026-09-10.

You: Someone hacked my account, there are transactions I didn't make.
Agent: I'm connecting you right now to a human agent who can help secure your account.

You: Should I invest my savings in crypto?
Agent: I can't give financial or investment advice. For that, please consult a licensed financial advisor.
```

## Notes

- Transaction and account data in `mock_data.py` is entirely fake, used only
  to demonstrate the tool-calling flow.
- Escalation is simulated: it logs a ticket to `escalations.log` and prints a
  console notice rather than contacting a real support queue.
- The knowledge base is the single source of truth for policy answers and for
  the escalate/refuse rules baked into the system prompt.
