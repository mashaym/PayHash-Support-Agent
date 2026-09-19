"""
Retrieval + answering logic for the PayHash support agent.

This module knows nothing about the terminal loop or .env loading — it just
turns a question into a grounded answer. That separation is what lets later
milestones (tools, escalation, refusal) sit on top of this file without
rewriting it.
"""

import re
from pathlib import Path

import chromadb
from google.genai import types
from sentence_transformers import SentenceTransformer

import tools

KB_PATH = Path(__file__).parent / "payhash_knowledge_base.md"
DB_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "payhash_kb"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
GEMINI_MODEL_NAME = "gemini-3.5-flash-lite"
TOP_K = 4
MAX_CHUNK_CHARS = 700

SYSTEM_PROMPT = """You are a customer support assistant for PayHash, a digital wallet app.
You have four ways to respond, and no other sources of information:

1. ANSWER using CONTEXT PASSAGES below, pulled from PayHash's official
   support knowledge base. Use these for general policy questions (fees,
   limits, how features work).
2. Call the get_transaction_status TOOL whenever the user asks about the
   status or details of a SPECIFIC transaction (an ID that looks like TXN
   followed by digits, e.g. TXN100234). The knowledge base does not contain
   live transaction data, so never guess a transaction's status from
   context — always call the tool for that.
3. Call the escalate_to_human TOOL for a legitimate PayHash matter that a
   human agent needs to handle, because it needs judgment or access you
   don't have — not because the request itself is improper. Escalate for:
   - Fraud, hacking, scams, or unauthorized transactions.
   - A lost or stolen card.
   - Money sent to the wrong recipient, or a reversal request.
   - A dispute, chargeback, or refund request.
   - A name mismatch or repeated identity-verification failure.
   - A bill payment that was deducted but not reflected by the biller.
   - Anything else the context passages do not clearly cover, or anything
     that would require changing the user's account in a way you cannot
     safely do yourself.

   When escalating: do NOT try to explain, resolve, or walk the user through
   the issue first. Call escalate_to_human right away with a short summary
   and the closest matching category, then reassure the user warmly and
   briefly that you're connecting them to a human agent. Do not promise a
   specific resolution or timeline.
4. REFUSE directly in your own text response, with no tool call, for
   requests that are out of bounds for ANY PayHash agent — human or
   automated — to do at all:
   - Giving financial, investment, or tax advice ("should I invest in...",
     "is X a good financial decision?").
   - Actually executing a money transfer, payment, or withdrawal on the
     user's behalf.
   - Revealing or asking for sensitive credentials (PINs, passwords, full
     OTPs).
   - Anything illegal, or that helps circumvent security or identity
     verification.

   When refusing: politely decline, briefly explain why in one sentence, and
   where helpful point to the right channel (e.g. "for investment advice,
   please consult a licensed financial advisor"). Do not lecture, and do not
   repeat the refusal more than once.

HOW TO TELL REFUSE APART FROM ESCALATE: ask yourself whether a human PayHash
support agent, given the right access, would ever do this. If yes — it just
needs a human's judgment or access you don't have — escalate it. If no human
PayHash agent would ever do this either (it isn't PayHash support's job, or
it asks you to act as the user, or it asks for secrets) — refuse it directly
yourself; there is no reason to send it to a human.

Do not use any outside knowledge. If nothing above answers the question and
it is neither an escalation nor a refusal case, say clearly that you don't
have that information, rather than making something up. Keep answers short
and to the point, in plain customer-support language."""

GET_TRANSACTION_STATUS_DECLARATION = types.FunctionDeclaration(
    name="get_transaction_status",
    description="Look up the status, amount, date, and recipient of a specific PayHash transaction by its transaction ID.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "transaction_id": {
                "type": "string",
                "description": "A PayHash transaction ID, formatted as TXN followed by six digits, e.g. TXN100234.",
            },
        },
        "required": ["transaction_id"],
    },
)

ESCALATE_TO_HUMAN_DECLARATION = types.FunctionDeclaration(
    name="escalate_to_human",
    description="Hand off a sensitive or out-of-scope case to a human support agent. Use for fraud, lost/stolen cards, wrong-recipient transfers, disputes/refunds, verification problems, or anything not clearly covered by policy.",
    parameters_json_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A short, one-sentence summary of the user's issue, written for a human agent picking up the case.",
            },
            "category": {
                "type": "string",
                "description": "The closest matching escalation category.",
                "enum": [
                    "fraud_or_unauthorized_access",
                    "lost_or_stolen_card",
                    "wrong_recipient_or_reversal",
                    "dispute_or_chargeback_or_refund",
                    "verification_issue",
                    "unreflected_bill_payment",
                    "other_uncovered_case",
                ],
            },
        },
        "required": ["summary", "category"],
    },
)

AGENT_TOOLS = types.Tool(
    function_declarations=[GET_TRANSACTION_STATUS_DECLARATION, ESCALATE_TO_HUMAN_DECLARATION]
)

AVAILABLE_FUNCTIONS = {
    "get_transaction_status": tools.get_transaction_status,
    "escalate_to_human": tools.escalate_to_human,
}

MAX_TOOL_TURNS = 3


def chunk_markdown(text: str) -> list[str]:
    """Split a markdown document into paragraph-sized chunks, tagged with
    their section heading so each chunk keeps its topic context.

    Strategy:
      1. Break the doc into sections at each heading line (#, ##, ###...).
      2. Break each section into paragraphs (blank-line-separated blocks) —
         this naturally keeps bullet lists and related sentences together.
      3. If a paragraph is still too long, fall back to splitting it into
         sentences and regrouping them under a max character budget.
    """
    lines = text.split("\n")

    sections: list[tuple[str, list[str]]] = []
    current_heading = "PayHash Support Knowledge Base"
    current_lines: list[str] = []

    for line in lines:
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            sections.append((current_heading, current_lines))
            current_heading = heading_match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)
    sections.append((current_heading, current_lines))

    chunks: list[str] = []
    for heading, section_lines in sections:
        body = "\n".join(section_lines).strip()
        if not body:
            continue

        paragraphs = re.split(r"\n\s*\n", body)
        for paragraph in paragraphs:
            paragraph = paragraph.strip()
            if not paragraph or re.fullmatch(r"-{3,}", paragraph):
                continue
            for piece in _split_to_size(paragraph):
                chunks.append(f"[{heading}]\n{piece}")

    return chunks


def _split_to_size(paragraph: str) -> list[str]:
    """Return `paragraph` as-is if it fits the size budget, otherwise split
    it into sentences and regroup those sentences into chunks that fit."""
    if len(paragraph) <= MAX_CHUNK_CHARS:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(\"])", paragraph)

    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if len(candidate) > MAX_CHUNK_CHARS and current:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)

    return pieces


def load_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def get_collection(embed_model: SentenceTransformer):
    """Open the persistent Chroma collection, building it from the
    knowledge base on first run only. On later runs, the collection already
    has data on disk, so we just reuse it."""
    client = chromadb.PersistentClient(path=str(DB_DIR))
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    if collection.count() == 0:
        text = KB_PATH.read_text(encoding="utf-8")
        chunks = chunk_markdown(text)
        embeddings = embed_model.encode(chunks).tolist()
        ids = [f"chunk_{i}" for i in range(len(chunks))]
        collection.add(ids=ids, documents=chunks, embeddings=embeddings)
        print(f"[setup] Indexed {len(chunks)} chunks into '{DB_DIR}'.")

    return collection


def retrieve(collection, embed_model: SentenceTransformer, question: str, top_k: int = TOP_K) -> list[str]:
    query_embedding = embed_model.encode([question]).tolist()
    results = collection.query(query_embeddings=query_embedding, n_results=top_k)
    return results["documents"][0]


def answer_question(gemini_client, collection, embed_model: SentenceTransformer, question: str) -> str:
    chunks = retrieve(collection, embed_model, question)
    context = "\n\n---\n\n".join(chunks)

    user_message = f"Context passages:\n\n{context}\n\nQuestion: {question}"
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.2,
        tools=[AGENT_TOOLS],
    )

    conversation = [types.Content(role="user", parts=[types.Part(text=user_message)])]

    for _ in range(MAX_TOOL_TURNS):
        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL_NAME,
            contents=conversation,
            config=config,
        )

        if not response.function_calls:
            return response.text

        # The model wants to call a tool. Run the requested function
        # ourselves, then send the result back so the model can either
        # call another tool or write the final answer.
        function_call = response.function_calls[0]
        function = AVAILABLE_FUNCTIONS[function_call.name]
        result = function(**function_call.args)

        conversation.append(response.candidates[0].content)
        conversation.append(
            types.Content(
                role="user",
                parts=[types.Part.from_function_response(name=function_call.name, response=result)],
            )
        )

    return "I'm sorry, I'm having trouble completing this request. Please try rephrasing, or contact support directly."
