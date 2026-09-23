"""Validated catalog and request contracts."""
import re
from datetime import date
from pydantic import BaseModel, ConfigDict, Field, field_validator

DATE_MIN = date(2026, 9, 23)
DATE_MAX = date(2026, 12, 31)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    anon_name: str
    categories: list[str]
    city: str
    price_from_kzt: int = Field(ge=0)
    event_formats: list[str]
    languages: list[str]
    max_hours: int | None = Field(default=None, gt=0)
    busy_dates: list[date]
    description: str
    synthetic: bool = False
    city_imputed: bool = False
    price_imputed: bool = False


class MatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    city: str = Field(min_length=1, max_length=80)
    category: str = Field(min_length=1, max_length=80)
    event_date: date
    event_format: str = Field(min_length=1, max_length=80)
    budget: int = Field(ge=1, le=1_000_000_000, strict=True)
    duration_hours: int | None = Field(default=None, ge=1, le=48, strict=True)
    language: str | None = Field(default=None, min_length=1, max_length=40)
    blind_mode: bool = False

    @field_validator("event_date", mode="before")
    @classmethod
    def iso_date_only(cls, value):
        if isinstance(value, date):
            return value
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Дата должна иметь формат YYYY-MM-DD")
        return value

    @field_validator("event_date")
    @classmethod
    def in_calendar(cls, value):
        if not DATE_MIN <= value <= DATE_MAX:
            raise ValueError("Календарь доступен с 23.09.2026 по 31.12.2026")
        return value
