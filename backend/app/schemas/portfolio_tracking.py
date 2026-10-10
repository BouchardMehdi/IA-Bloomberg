from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from app.market.providers import QuoteIdentity


class SourceDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    source_url: HttpUrl
    published_at: datetime
    note: str = Field(min_length=20, max_length=1500)
    confirmed: Literal[True]

    @model_validator(mode="after")
    def safe_source(self):
        u = self.source_url
        if u.username or u.password or u.query or u.fragment:
            raise ValueError("URL documentaire sans identifiants ni paramètres requise.")
        if self.published_at.tzinfo is None or self.published_at > datetime.now(UTC):
            raise ValueError("Publication datée avec fuseau, non future requise.")
        return self


class CorporateActionInput(SourceDeclaration):
    kind: Literal["dividend", "split"]
    effective_date: date
    payment_date: date | None = None
    currency: str | None = None
    net_amount_per_security: Decimal | None = Field(
        default=None, gt=0, lt=1000000, decimal_places=6
    )
    numerator: int | None = Field(default=None, ge=1, le=10000, strict=True)
    denominator: int | None = Field(default=None, ge=1, le=10000, strict=True)

    @model_validator(mode="after")
    def conventions(self):
        if (
            not self.published_at.astimezone(UTC).date()
            <= self.effective_date
            <= datetime.now(UTC).date()
        ):
            raise ValueError("Date effective non future, au plus tôt à la publication.")
        if self.kind == "dividend":
            if (
                self.payment_date is None
                or self.currency is None
                or self.net_amount_per_security is None
                or self.numerator is not None
                or self.denominator is not None
            ):
                raise ValueError("Dividende : devise, montant NET par titre et paiement requis.")
            if not self.effective_date <= self.payment_date <= datetime.now(UTC).date():
                raise ValueError("Paiement non futur, après la date de détachement.")
        elif (
            self.numerator is None
            or self.denominator is None
            or self.numerator == self.denominator
            or self.payment_date is not None
            or self.currency is not None
            or self.net_amount_per_security is not None
        ):
            raise ValueError("Split : ratio nouveau/ancien requis, sans montant ou devise.")
        return self


class PriceMappingInput(QuoteIdentity, SourceDeclaration):
    provider_symbol: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9.:-]{0,49}$")
    provider: Literal["alpha_vantage"] = "alpha_vantage"
    as_of: date

    @model_validator(mode="after")
    def dated(self):
        if not self.published_at.astimezone(UTC).date() <= self.as_of <= datetime.now(UTC).date():
            raise ValueError("Correspondance datée, non future et postérieure à sa source.")
        return self
