import json
import re

import pytest
from fastapi import HTTPException

from scripts.export_contracts import outputs
from services.api.contracts import contract_app


def test_generated_files_have_no_drift():
    for path, expected in outputs().items():
        assert path.read_text(encoding="utf-8") == expected, f"Contract drift: {path}"


def test_catalog_complete_and_path_parameters_declared():
    document = json.loads(
        next(value for path, value in outputs().items() if path.name == "openapi.json")
    )
    operations = [
        operation for methods in document["paths"].values() for operation in methods.values()
    ]
    assert len(operations) == 50
    assert {operation["operationId"] for operation in operations} == (
        {f"E{number}" for number in range(1, 44)}
        | {"E44_health", "E44_ready", "E44_version", "E44_config"}
        | {"E45_generate", "E46_notifications", "E47_read"}
    )
    for path, methods in document["paths"].items():
        for operation in methods.values():
            required = {
                parameter["name"]
                for parameter in operation["parameters"]
                if parameter["in"] == "path" and parameter["required"]
            }
            assert required == set(re.findall(r"\{([^}]+)\}", path))


def test_administrator_cannot_impersonate_send_or_institution_decision():
    document = contract_app().openapi()
    assert document["paths"]["/api/v1/cases/{caseId}/packets/{packetId}/approve"]["post"][
        "x-relay-roles"
    ] == ["V"]
    assert document["paths"]["/api/v1/console/cases/{caseId}/packets/{packetId}/decision"]["post"][
        "x-relay-roles"
    ] == ["R"]
    assert set(
        document["paths"]["/api/v1/pack-builds/{buildId}/publish"]["post"]["x-relay-roles"]
    ) == {"P", "A"}


def test_future_contracts_do_not_claim_working_business_operations():
    # Stubs have no awaited I/O. Execute the coroutine directly without creating
    # Windows' loopback socketpair, unavailable in the restricted local sandbox.
    routes = [
        route
        for route in contract_app().routes
        if getattr(route, "operation_id", "").startswith("E")
    ]
    for route in routes:
        coroutine = route.endpoint()
        with pytest.raises(HTTPException) as error:
            coroutine.send(None)
        assert error.value.status_code == 501
