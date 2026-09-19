# PayHash Support Agent

An AI customer support agent for **PayHash**, a fictional digital-wallet and
mobile-payments app. Built as a terminal-based demo of a grounded, tool-using
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
