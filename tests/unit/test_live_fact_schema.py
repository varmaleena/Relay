from datetime import UTC, datetime

from google.genai import types

from packages.intake.service import merge_facts
from packages.schemas.models import CaseFacts
from services.live_gateway.provider import TOOL_DECLARATIONS, live_fact_schema


def test_live_tool_advertises_real_camel_case_fields_without_server_proofs():
    schema = live_fact_schema()
    assert "$defs" not in schema and "$ref" not in str(schema)
    assert "provenance" not in str(schema)
    properties = schema["properties"]
    assert "ongoingContact" in properties and "ongoing_contact" not in properties
    assert "authorizedByVictim" in str(properties["payment"])
    assert "recipientIdentifier" in str(properties["payment"])
    declaration = types.FunctionDeclaration.model_validate(TOOL_DECLARATIONS[0])
    assert declaration.parameters_json_schema["properties"]["facts"] == schema


def test_advertised_partial_facts_merge_with_only_server_bound_statement_proof():
    result = merge_facts(
        CaseFacts().model_dump(mode="json", by_alias=True),
        {
            "country": {"value": "IN"},
            "payment": {"method": "upi", "amount": {"value": "45000", "currency": "INR"}},
        },
        confirmed=False,
        now=datetime(2026, 10, 18, tzinfo=UTC),
        statement_reference="case:case_synthetic:turn:turn_synthetic:facts:1",
    )
    assert result["country"]["value"] == "IN"
    assert result["payment"]["amount"]["value"] == "45000"
    assert result["fieldProvenance"]["payment.amount"]["source"] == "victim_statement"
