"""Strict API schemas for the translator directory."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProfileIn(StrictModel):
    subject_type: str
    display_name: str
    bio: str = ""
    country_code: str
    city: str = ""
    service_mode: str
    languages: list[str] = Field(min_length=1, max_length=12)
    services: list[str] = Field(min_length=1, max_length=2)
    domains: list[str] = Field(min_length=1, max_length=8)
    contacts: dict[str, str] = Field(default_factory=dict)


class ContactRequestIn(StrictModel):
    purpose: str = Field(default="", max_length=160)


class NeedIn(StrictModel):
    source_lang: str
    target_lang: str
    service_type: str
    service_mode: str
    country_code: str = ""
    city: str = ""
    service_at: datetime | None = None
    note: str = Field(default="", max_length=120)
    response_limit: int = Field(default=3, ge=1, le=5)


class ReportIn(StrictModel):
    reason: str
    note: str = Field(default="", max_length=120)
