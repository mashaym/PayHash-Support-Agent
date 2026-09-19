"""
Fake "live" backend data for the support agent to look up.

In a real system these would be database queries or internal API calls.
Keeping them as plain dicts here means the tool functions in tools.py don't
care where the data actually comes from — swapping this for a real API
later won't require touching rag_engine.py or main.py.
"""

TRANSACTIONS = {
    "TXN100234": {
        "status": "Completed",
        "amount": "5,000 PKR",
        "date": "2026-09-10",
        "recipient": "Ali Raza",
    },
    "TXN100235": {
        "status": "Pending",
        "amount": "12,000 PKR",
        "date": "2026-09-18",
        "recipient": "Sara Khan",
    },
    "TXN100236": {
        "status": "Failed",
        "amount": "3,000 PKR",
        "date": "2026-09-15",
        "recipient": "Bilal Ahmed",
    },
    "TXN100237": {
        "status": "On hold",
        "amount": "250,000 PKR",
        "date": "2026-09-19",
        "recipient": "Unknown Merchant",
    },
}

# Not used by any tool yet — reserved for a future account-lookup tool.
ACCOUNTS = {
    "ACC10045": {"kyc_level": 2, "status": "Active"},
    "ACC10046": {"kyc_level": 1, "status": "Active"},
    "ACC10047": {"kyc_level": 3, "status": "Suspended"},
}
