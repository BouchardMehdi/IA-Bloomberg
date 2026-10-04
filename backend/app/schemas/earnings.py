from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from app.schemas.international import CURRENCIES


class EarningsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["schedule", "estimate", "reported"]
    fiscal_period_end: date
    report_date: date
    period_type: Literal["quarterly", "annual", "unknown"] = "unknown"
    source_url: HttpUrl
    published_at: datetime
    eps: Decimal | None = Field(default=None, gt=-1_000_000, lt=1_000_000, decimal_places=6)
    currency: str | None = None
    basis: Literal[
        "unknown", "gaap_basic", "gaap_diluted", "adjusted_basic", "adjusted_diluted"
    ] = "unknown"

    @field_validator("source_url")
    @classmethod
    def safe_source(cls, value):
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("URL documentaire sans identifiants ni paramètres requise.")
        return value

    @field_validator("published_at")
    @classmethod
    def dated_source(cls, value):
        if value.tzinfo is None or value > datetime.now(UTC):
            raise ValueError("Date de publication passée avec fuseau horaire requise.")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def consistent(self):
        if self.fiscal_period_end > self.report_date:
            raise ValueError("La période doit se terminer au plus tard à la date des résultats.")
        if self.currency is not None and self.currency not in CURRENCIES:
            raise ValueError("Devise non prise en charge.")
        if self.kind == "schedule":
            if self.eps is not None or self.currency is not None or self.basis != "unknown":
                raise ValueError("Une date de calendrier ne contient pas de BPA.")
        elif self.eps is None or self.currency is None:
            raise ValueError("BPA et devise explicites requis pour un chiffre.")
        if self.kind == "reported" and self.report_date > self.published_at.date():
            raise ValueError("Des résultats publiés ne peuvent pas être futurs.")
        return self
