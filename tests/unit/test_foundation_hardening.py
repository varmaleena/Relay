from datetime import UTC, datetime

import pytest

from packages.common.normalization import normalize_entity
from packages.packs.deadlines import add_duration, parse_duration
from packages.packs.validator import load_pack


@pytest.mark.parametrize("value", ["1e100000", "1e-100000", "123456789012345678901", "1.000000001"])
def test_amount_exponent_and_precision_bounded(value):
    with pytest.raises(ValueError, match="precision"):
        normalize_entity("amount", value, currency="INR")


def test_exact_amount_format_avoids_decimal_context_rounding():
    assert (
        normalize_entity("amount", "123456789012.12345678", currency="INR")
        == "INR 123456789012.12345678"
    )


def test_nondefault_url_ports_remain_distinct():
    assert normalize_entity("url", "https://example.com:80/x") == "example.com:80/x"
    assert normalize_entity("url", "http://example.com:443/x") == "example.com:443/x"
    assert normalize_entity("url", "https://example.com:443/x") == "example.com/x"


@pytest.mark.parametrize(
    "body", ["x: &loop [*loop]", "a: &a ['x']\nb: [*a,*a]", "x: " + "[" * 21 + "0" + "]" * 21]
)
def test_pack_yaml_aliases_cycles_and_depth_rejected(body, tmp_path):
    path = tmp_path / "unsafe.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(ValueError):
        load_pack(path)


def test_ambiguous_dst_deadline_is_not_guessed():
    with pytest.raises(ValueError, match="ambiguous DST"):
        add_duration(
            datetime(2026, 10, 24, 0, 30, tzinfo=UTC), parse_duration("P1D"), "Europe/London"
        )
