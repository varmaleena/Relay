"""Explicitly fictional scenario inputs; no cached model results or approvals."""

from datetime import datetime, timedelta
from typing import Any

SCENARIOS: dict[str, dict[str, Any]] = {
    "asha_in_hi_voice": {
        "language": "hi",
        "country": "IN",
        "inputMode": "voice",
        "description": "Fictional India Hindi bank impersonation report.",
    },
    "daniel_uk_text": {
        "language": "en",
        "country": "GB",
        "inputMode": "text",
        "description": "Fictional UK bank transfer impersonation report.",
    },
    "generic_fragmented": {
        "language": "en",
        "country": None,
        "inputMode": "text",
        "description": "Fictional incomplete report requiring more information.",
    },
    "injection_attempt": {
        "language": "en",
        "country": "IN",
        "inputMode": "text",
        "description": "Fictional adversarial input; no bypass is authorized.",
    },
}


def facts_for(name: str, now: datetime) -> dict[str, Any]:
    if name == "generic_fragmented":
        return {"ongoingContact": False}
    country = SCENARIOS[name]["country"]
    return {
        "country": {
            "value": country,
            "availability": "available",
            "provenance": {"source": "selected"},
        },
        "payment": {
            "method": "bank_transfer" if country == "GB" else "upi",
            "amount": {
                "value": "45000" if country == "IN" else "250",
                "currency": "INR" if country == "IN" else "GBP",
            },
            "timestamp": (now - timedelta(minutes=20)).isoformat(),
            "authorizedByVictim": True,
            "recipientIdentifier": {
                "type": "upi_id" if country == "IN" else "bank_account",
                "value": "synthetic@fictional" if country == "IN" else "TEST0001",
            },
            "transactionRef": "SYNTHETIC0001",
        },
        "contact": {"channel": "phone", "claimedIdentity": "Fictional Test Bank"},
        "victimBank": "Fictional Test Bank",
        "ongoingContact": False,
        "credentialsShared": ["none"],
    }
