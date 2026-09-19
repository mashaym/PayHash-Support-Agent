"""
Tool functions the agent can call. Plain Python — no Gemini-specific code
here, so this module stays easy to unit test on its own, and new tools just
get added as new functions.
"""

import datetime
import uuid
from pathlib import Path

import mock_data

ESCALATIONS_LOG_PATH = Path(__file__).parent / "escalations.log"


def get_transaction_status(transaction_id: str) -> dict:
    """Read-only lookup of a transaction's status and details by its ID."""
    record = mock_data.TRANSACTIONS.get(transaction_id.strip().upper())
    if record is None:
        return {
            "found": False,
            "transaction_id": transaction_id,
            "message": "No transaction found with this ID.",
        }
    return {"found": True, "transaction_id": transaction_id.strip().upper(), **record}


def escalate_to_human(summary: str, category: str) -> dict:
    """Simulate handing a case off to a human agent: log it and return a
    confirmation with a ticket ID. No real ticketing system involved."""
    ticket_id = f"ESC{uuid.uuid4().hex[:6].upper()}"
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")
    log_line = f"[{timestamp}] {ticket_id} | category={category} | summary={summary}"

    print(f"\n[ESCALATION LOGGED] {log_line}")
    with open(ESCALATIONS_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(log_line + "\n")

    return {
        "escalated": True,
        "ticket_id": ticket_id,
        "message": "This case has been logged and handed off to a human support agent.",
    }
