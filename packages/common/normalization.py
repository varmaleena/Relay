"""Entity normalization and HMAC-only linking inputs (spec section 18.1)."""

import hashlib
import hmac
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit

import phonenumbers


def normalize_entity(
    kind: str,
    value: str,
    *,
    country: str | None = None,
    currency: str | None = None,
    case_sensitive_wallet: bool = True,
) -> str:
    value = value.strip()
    if not value or len(value) > 4000:
        raise ValueError("entity value must be nonempty and bounded")
    if kind == "phone":
        try:
            phone = phonenumbers.parse(value, country)
        except phonenumbers.NumberParseException as exc:
            raise ValueError("phone country/prefix is ambiguous") from exc
        # Synthetic test numbers may not be assigned; require a possible shape.
        if not phonenumbers.is_possible_number(phone):
            raise ValueError("invalid phone shape")
        return str(phonenumbers.format_number(phone, phonenumbers.PhoneNumberFormat.E164))
    if kind in {"upi_id", "email", "social_handle"}:
        return value.lower()
    if kind in {"bank_account", "iban", "ifsc_or_sort_code"}:
        result = re.sub(r"[\s-]", "", value).upper()
        if not re.fullmatch(r"[A-Z0-9]+", result):
            raise ValueError("account/code contains invalid characters")
        return result
    if kind == "wallet_address":
        return value if case_sensitive_wallet else value.lower()
    if kind == "url":
        parsed = urlsplit(value if "://" in value else "https://" + value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("invalid URL")
        host = parsed.hostname.lower().removeprefix("www.")
        port = parsed.port
        host = f"[{host}]" if ":" in host else host
        default_port = 443 if parsed.scheme == "https" else 80
        if port and port != default_port:
            host += f":{port}"
        query = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid", "msclkid"}
        ]
        return host + parsed.path.rstrip("/") + ("?" + urlencode(sorted(query)) if query else "")
    if kind == "amount":
        if not currency or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("amount requires currency")
        try:
            amount = Decimal(value.replace(",", ""))
        except InvalidOperation as exc:
            raise ValueError("invalid amount") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError("invalid amount")
        parts = amount.as_tuple()
        exponent = int(parts.exponent)
        if len(parts.digits) > 20 or exponent > 20 or exponent < -8:
            raise ValueError("amount exceeds supported precision")
        if amount.adjusted() >= 20:
            raise ValueError("amount exceeds supported precision")
        exact = format(amount, "f")
        if "." in exact:
            exact = exact.rstrip("0").rstrip(".")
        return currency + " " + exact
    if kind == "timestamp":
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timestamp requires timezone")
        return stamp.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raise ValueError("unsupported entity type for normalization")


def entity_hmac(kind: str, normalized_value: str, secret: bytes) -> str:
    if len(secret) < 32:
        raise ValueError("HMAC key must contain at least 32 bytes")
    return hmac.new(secret, f"{kind}|{normalized_value}".encode(), hashlib.sha256).hexdigest()
