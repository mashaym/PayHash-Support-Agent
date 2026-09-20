# PayHash Support Agent

An AI customer-support agent for a fintech digital wallet that answers questions from company documentation, looks up live transaction data, and, critically, knows when to escalate to a human or refuse a request it shouldn't handle.

> **Note:** PayHash is a fictional company created for this project. All data and policies are invented for demonstration purposes only.

## The Problem

Companies pay human agents to handle live chat support, which is expensive and slow. An AI can handle much of this, but the hard part isn't answering questions, it's doing so *safely*: knowing what it can confidently answer, what needs a human, and what it should refuse outright. A support bot that confidently gives wrong information about someone's money is worse than no bot at all. This project builds an agent that makes that judgment reliably.

## What It Does

The agent routes every message into one of four behaviors:

| Behavior | Trigger | Example |
|---|---|---|
| **Answer** | General policy question | "What's the fee for an international transfer?" |
| **Look up** | A specific transaction ID | "What's the status of TXN100234?" |
| **Escalate** | Sensitive case a human must handle | "Someone hacked my account" |
| **Refuse** | Request no support agent should fulfill | "Should I invest in crypto?" |

- **Answers** policy questions (fees, limits, KYC, etc.) using retrieval-augmented generation (RAG). The knowledge base is chunked, embedded, and stored in a local vector database, and the model answers strictly from the retrieved passages. If the answer isn't in the docs, it says so instead of guessing.
- **Looks up** live transaction data using tools (function calling). The model decides when a lookup is needed, the Python code executes it, and the result is fed back to produce the final reply.
- **Escalates** sensitive cases (fraud, unauthorized transactions, disputes, lost or stolen cards, wrong-recipient transfers) to a human agent. Each escalation is logged to `escalations.log` with a ticket ID, as a stand-in for a real handoff queue.
- **Refuses** out-of-bounds requests (financial advice, executing transfers, revealing PINs) with a brief explanation and a pointer to the right channel where relevant.
- **Remembers** the conversation. Recent question/answer pairs are fed back into both retrieval and generation, so follow-ups like "who did I send it to?" work without repeating context.

## Example Interactions

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

## Screenshot

<!-- Add a screenshot of the chat UI here, ideally showing an escalation or a memory follow-up.
     Save the image (e.g. docs/screenshot.png) and uncomment the line below:
![PayHash chat interface](docs/screenshot.png)
-->

## Evaluation

Routing accuracy is measured by an automated evaluation harness (`evaluate.py`) across 18 policy-based test cases covering all four behaviors, including tricky distinctions like "my card was declined" (answer) vs. "my card was stolen" (escalate).

- The harness verifies **which tool actually fired**, not just the wording of the reply, to identify lookups and escalations.
- When no tool fires, a separate Gemini judge (with the expected label hidden) decides whether the reply was an answer or a refusal. This judgment is useful but fallible.
- Reports include replies and tool arguments/results so every result can be inspected.

**Latest result: 18/18 cases routed correctly.**

See [EVALUATION.md](EVALUATION.md) for the test design, scorecard interpretation, and targeted reruns.

## Tech Stack

- **Language:** Python
- **LLM:** Google Gemini API (function calling / tool use)
- **RAG:** sentence-transformers (`all-MiniLM-L6-v2`) embeddings + ChromaDB vector database
- **Backend:** FastAPI + Uvicorn
- **Frontend:** React + Vite
- **Evaluation:** custom automated harness with tool-trace verification

## How to Run

### 1. Setup

Create a virtual environment and install dependencies. `requirements-backend.txt` includes everything the agent needs plus FastAPI and Uvicorn.

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-backend.txt
```

**macOS / Linux:**

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-backend.txt
```

### 2. API key

Get a free Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey), then copy the template and add your key:

```bash
cp .env.example .env        # on Windows PowerShell: copy .env.example .env
```

Edit `.env`:

```
GEMINI_API_KEY=your-key-here
```

### 3. Run the backend (terminal 1)

```bash
python -X utf8 -m uvicorn backend:app --host 127.0.0.1 --port 8000
```

Wait for `Application startup complete`. On first run, the embedding model is downloaded and the vector index is built from the knowledge base (both are cached for later runs). You can try the API at http://127.0.0.1:8000/docs.

### 4. Run the frontend (terminal 2)

```bash
cd frontend
npm ci
npm run dev
```

Then open http://127.0.0.1:5173. Keep both servers running. (On Windows PowerShell, use `npm.cmd` instead of `npm` if script execution is blocked.) See [frontend/README.md](frontend/README.md) for a code walkthrough.

### Other ways to run

- **Terminal version:** `python main.py`
- **Backend tests** (offline, no Gemini calls): `python -m unittest test_backend -v`
- **Evaluation:**

```bash
  python -X utf8 evaluate.py --list        # show the test cases
  python -X utf8 evaluate.py --limit 4     # run a small sample
  python -X utf8 evaluate.py               # run all 18 cases
```

  The last two commands use real Gemini quota. Requests are paced 15 seconds apart, and a quota error stops the run.

## API Reference

`POST /chat` accepts a message plus the recent conversation history and returns the agent's reply.

```json
{
  "message": "Who received it?",
  "history": [
    {
      "question": "What is the status of TXN100235?",
      "answer": "Transaction TXN100235 is Pending — 12,000 PKR to Sara Khan."
    }
  ]
}
```

- `history` holds completed question/answer pairs, oldest first, excluding the current message. Omit it or send `[]` for a fresh conversation. The server keeps no global chat history.
- Blank messages, malformed history, or more than 10 exchanges return **422**. Service errors return a JSON `detail` string: **429** (rate limit), **502/503** (upstream failure), **504** (timeout), or **500** (unexpected error).
- Do not automatically retry failed requests: a tool may already have logged a ticket before an upstream failure.
- CORS allows browser requests from `http://localhost:5173` and `http://127.0.0.1:5173` (the React dev server). CORS is not authentication; this project is meant to run locally with fictional data.

## Project Structure

```
frontend/                    # React/Vite chat UI
backend.py                   # FastAPI /chat endpoint wrapping the agent
main.py                      # Terminal chat interface
rag_engine.py                # Agent "brain": chunking, embedding, retrieval, system prompt, tool-calling loop
tools.py                     # Tools the model can call (transaction lookup, human escalation)
mock_data.py                 # Fake transaction/account data (stands in for a live backend)
payhash_knowledge_base.md    # The fictional company's support knowledge base
evaluate.py                  # Evaluation harness with tool traces and a no-tool judge
evaluation_cases.py          # The 18 routing test cases
test_backend.py              # Offline API contract, CORS, memory, and error checks
test_evaluate.py             # Offline checks of the evaluator itself
requirements.txt             # Agent dependencies
requirements-backend.txt     # Agent dependencies plus FastAPI and Uvicorn
.env.example                 # Template for the required environment variable
```

Running the agent also creates two local, gitignored artifacts: `chroma_db/` (the persistent vector store) and `escalations.log` (simulated human handoffs).

## Notes

- All transaction and account data in `mock_data.py` is fake and exists only to demonstrate the tool-calling flow.
- Escalation is simulated: it logs a ticket and prints a console notice rather than contacting a real support queue.
- The knowledge base is the single source of truth for policy answers and for the escalate/refuse rules in the system prompt.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
