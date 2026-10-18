from scripts.preflight import run
from tests.unit.test_preflight import transport


def test_cold_start_budget_can_observe_ready_response_without_relaxing_validation():
    def cold(url, timeout):
        if url.endswith("/healthz") and timeout < 16:
            raise TimeoutError("synthetic cold start")
        return transport(url, timeout)

    options = dict(transport=cold, checks=lambda _: [])
    assert not run("http://localhost:8000", "http://localhost:5173", timeout=10, **options)[
        "servingChecksPassed"
    ]
    assert run("http://localhost:8000", "http://localhost:5173", **options)["servingChecksPassed"]


def test_larger_budget_does_not_turn_unhealthy_response_into_success():
    def unhealthy(url, timeout):
        if url.endswith("/healthz"):
            return 503, b'{"status":"not_ready"}'
        return transport(url, timeout)

    assert not run(
        "http://localhost:8000",
        "http://localhost:5173",
        transport=unhealthy,
        checks=lambda _: [],
    )["servingChecksPassed"]
