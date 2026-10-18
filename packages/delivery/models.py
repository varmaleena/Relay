"""Minimal approved-packet projection for simulated institution tools."""

import json
import re
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from packages.safety import scrub_credentials
from packages.schemas.models import Model

Identifier = Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.:@-]+$")]
Hash = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class Simulation(Model):
    bank_mode: Literal["auto", "success", "funds_moved"] = "auto"
    rail_mode: Literal["normal", "misrouted"] = "normal"
    minutes_since_payment: Annotated[
        float | None, Field(ge=0, le=10_000_000, allow_inf_nan=False)
    ] = None


class DeliveryProjection(Model):
    owner_uid: Identifier
    case_id: Identifier
    case_ref: Identifier
    packet_id: Identifier
    packet_version: Annotated[int, Field(ge=1, le=10000)]
    content_hash: Hash
    pack_id: Identifier
    pack_version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+$", max_length=40)]
    recipient_id: Identifier
    fields: dict[str, str | int | bool | None]
    typology: Annotated[str, Field(min_length=1, max_length=80)]
    category: Annotated[str | None, Field(max_length=128)] = None
    simulation: Simulation = Field(default_factory=Simulation)

    @field_validator("fields", mode="before")
    @classmethod
    def bounded_safe_fields(cls, value):
        if type(value) is not dict or len(value) > 80:
            raise ValueError("bounded scalar fields required")
        for key, item in value.items():
            if type(key) is not str or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", key):
                raise ValueError("invalid field name")
            if any(
                term in key.lower() for term in ("password", "otp", "cvv", "pin", "card_number")
            ):
                raise ValueError("credential fields forbidden")
            if type(item) not in (str, int, bool, type(None)):
                raise ValueError("scalar fields required")
            if type(item) is int and abs(item) > 10**18:
                raise ValueError("integer field exceeds bound")
            if type(item) is str and (len(item) > 4000 or scrub_credentials(item) != item):
                raise ValueError("unsafe or oversized field")
        if len(json.dumps(value, ensure_ascii=False)) > 32_000:
            raise ValueError("projection fields exceed bound")
        return value

    @model_validator(mode="after")
    def no_extra_case_material(self):
        if any(
            key.split(".")[0] in {"transcript", "evidence", "case", "facts"} for key in self.fields
        ):
            raise ValueError("full case material forbidden")
        return self


class DeliveryReceipt(Model):
    delivery_id: Identifier
    adapter: Literal["mcp-bank-mock", "mcp-rail-mock"]
    ticket_ref: Annotated[str, Field(pattern=r"^SIM-[A-Z]{2,12}-\d{6}$")]
    status: Literal["RECEIVED", "NEEDS_INFO", "ROUTED", "MISROUTED_SIMULATED"]
    simulated: Literal[True] = True
    sent_at: datetime
    missing_items: list[str] = Field(default_factory=list)
    routed_to: list[str] = Field(default_factory=list)


class DeliveryLookup(Model):
    owner_uid: Identifier
    case_id: Identifier
    delivery_id: Annotated[str, Field(pattern=r"^delivery_[a-f0-9]{64}$")]


class HoldReceipt(Model):
    hold_ref: Annotated[str, Field(pattern=r"^SIM-HOLD-\d{6}$")]
    ticket_ref: str
    status: Literal["HOLD_RECORDED", "FUNDS_ALREADY_MOVED", "REJECTED"]
    simulated: Literal[True] = True


class DeliveryError(ValueError):
    pass
