from datetime import UTC, datetime, timedelta

import pytest

from packages.intake.repository import MemoryRepository
from packages.linking.core import Hasher, compute, normalize
from packages.linking.service import INDEX, LinkingService

NOW = datetime(2026, 10, 18, tzinfo=UTC)


def sight(hasher, ref, kind="upi_id", value="ring@fictional", hours=0, **kwargs):
    return hasher.sighting(
        case_ref=ref,
        entity_type=kind,
        value=value,
        role=kwargs.get("role", "scammer"),
        status=kwargs.get("status", "confirmed"),
        first_seen=NOW + timedelta(hours=hours),
    )


@pytest.mark.parametrize(
    ("kind", "raw", "expected"),
    [
        ("phone", "09000000000", "+919000000000"),
        ("upi_id", " Ring@Test ", "ring@test"),
        ("email", " X@EXAMPLE.INVALID ", "x@example.invalid"),
        ("bank_account", "AB-12 34", "AB1234"),
        ("iban", "GB-00 TEST", "GB00TEST"),
        ("url", "https://WWW.Example.invalid/path/?utm_source=x&a=1#x", "example.invalid/path?a=1"),
        ("wallet_address", "AbCd", "AbCd"),
    ],
)
def test_normalization(kind, raw, expected):
    assert normalize(kind, raw) == expected


def test_six_case_ring_and_duplicate_type_not_double_weighted():
    h = Hasher(b"x" * 32)
    rows = [sight(h, f"case_{i}") for i in range(6)]
    links, clusters = compute(rows + rows)
    assert len(links) == 15
    assert len(clusters) == 1 and len(clusters[0].case_refs) == 6
    assert all(x.strength == 0.9 and x.confidence_band == "likely" for x in links)
    assert "ring@fictional" not in str([x.model_dump() for x in rows])


@pytest.mark.parametrize("role", ["victim", "unknown", "merchant"])
def test_role_exclusion(role):
    assert sight(Hasher(b"x" * 32), "a", role=role) is None


@pytest.mark.parametrize(
    "kind",
    [
        "amount",
        "transaction_ref",
        "timestamp",
        "currency",
        "bank_name",
        "app_name",
        "claimed_identity",
        "ifsc_or_sort_code",
    ],
)
def test_non_linking_types(kind):
    assert sight(Hasher(b"x" * 32), "a", kind=kind) is None


def test_denylist_key_separation_and_confirmation():
    h = Hasher(b"x" * 32)
    digest = h.digest("phone", "09000000000")
    assert digest != Hasher(b"y" * 32).digest("phone", "09000000000")
    assert sight(Hasher(b"x" * 32, frozenset({digest})), "a", "phone", "09000000000") is None
    assert sight(h, "a", status="extracted") is None


@pytest.mark.parametrize(("hours", "strength"), [(72, 0.9), (73, 0.72), (720, 0.72), (721, None)])
def test_time_boundaries(hours, strength):
    h = Hasher(b"x" * 32)
    links, _ = compute([sight(h, "a"), sight(h, "b", hours=hours)])
    assert (round(links[0].strength, 2) if links else None) == strength


def test_type_combination_and_single_pair_no_cluster():
    h = Hasher(b"x" * 32)
    rows = [
        sight(h, ref, kind, value)
        for ref in ["a", "b"]
        for kind, value in [("email", "a@example.invalid"), ("phone", "09000000000")]
    ]
    links, clusters = compute(rows)
    assert links[0].strength == 0.8 and not clusters


def test_projection_scope_and_deletion_recompute():
    repo = MemoryRepository()
    service = LinkingService(repo, Hasher(b"x" * 32))
    for i in range(6):
        service.replace_case(
            f"case_{i}",
            {"bank" if i < 5 else "other"},
            [
                {
                    "type": "upi_id",
                    "value": "ring@fictional",
                    "role": "scammer",
                    "status": "confirmed",
                }
            ],
            NOW,
        )
    assert len(service.links_for("case_0", "bank")) == 4
    with pytest.raises(PermissionError):
        service.links_for("case_0", "other")
    repo.atomic(lambda tx: service.cleanup_case(tx, "case_0"))
    record = repo.get(INDEX)
    assert "case_0" not in record["cases"]
    assert all("case_0" not in link["case_refs"] for link in record["links"])
    assert "ring@fictional" not in str(record)


def test_bounds_and_timezone():
    with pytest.raises(ValueError):
        Hasher(b"short")
    with pytest.raises(ValueError):
        Hasher(b"x" * 32).sighting(
            case_ref="a",
            entity_type="phone",
            value="09000000000",
            role="scammer",
            status="confirmed",
            first_seen=datetime(2026, 1, 1),
        )


def test_ingestion_joins_existing_transaction_and_rolls_back():
    repo = MemoryRepository()
    service = LinkingService(repo, Hasher(b"x" * 32))
    entities = [
        {"type": "upi_id", "value": "ring@fictional", "role": "scammer", "status": "confirmed"}
    ]

    def rollback(tx):
        service.replace_case("RLY_A", {"bank"}, entities, NOW, case_id="case_a", tx=tx)
        raise RuntimeError("synthetic rollback")

    with pytest.raises(RuntimeError):
        repo.atomic(rollback)
    assert repo.get(INDEX) is None
    repo.atomic(
        lambda tx: service.replace_case("RLY_A", {"bank"}, entities, NOW, case_id="case_a", tx=tx)
    )
    assert repo.get(INDEX)["cases"]["RLY_A"]["caseId"] == "case_a"
