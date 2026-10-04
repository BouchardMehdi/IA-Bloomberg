"""Issuer-wide duration facts only; no inference of quarterly or security EPS."""

import asyncio
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.collectors.company_sec import CompanyPublicationError
from app.schemas.international import CURRENCIES

CONCEPTS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "revenue",
    "Revenues": "revenue",
    "SalesRevenueNet": "revenue",
    "NetIncomeLoss": "net_income",
    "EarningsPerShareBasic": "eps_basic",
    "EarningsPerShareDiluted": "eps_diluted",
}
FORMS = {
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A",
    "8-K",
    "8-K/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
    "6-K",
    "6-K/A",
}


class FinancialRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metric: str
    taxonomy: str = "us-gaap"
    concept: str
    unit: str
    value: Decimal = Field(gt=-(10**18), lt=10**18, decimal_places=10)
    start: date
    end: date
    filed: date
    accession: str = Field(pattern=r"^[0-9]{10}-[0-9]{2}-[0-9]{6}$")
    form: str
    fiscal_year: int | None = Field(default=None, strict=True, ge=1900, le=2200)
    filing_period: str | None = Field(default=None, max_length=10)
    frame: str | None = Field(default=None, max_length=50)

    @model_validator(mode="after")
    def consistent(self):
        if (
            self.taxonomy != "us-gaap"
            or CONCEPTS.get(self.concept) != self.metric
            or self.form not in FORMS
        ):
            raise ValueError("unsupported concept")
        currency = self.unit.removesuffix("/shares")
        if currency not in CURRENCIES or self.unit != currency + (
            "/shares" if self.metric.startswith("eps_") else ""
        ):
            raise ValueError("incompatible unit")
        if not self.start <= self.end <= self.filed <= datetime.now(UTC).date():
            raise ValueError("invalid dates")
        return self


def parse_financials(payload: bytes, cik: str, today: date | None = None):
    today = today or datetime.now(UTC).date()
    try:
        data = json.loads(payload, parse_float=Decimal)
        identity = str(data["cik"])
        if not re.fullmatch(r"[0-9]{1,10}", identity) or identity.zfill(10) != cik:
            raise CompanyPublicationError("sec_identity_mismatch")
        facts = data["facts"]
        if not isinstance(facts, dict):
            raise ValueError("invalid facts")
        gaap = facts.get("us-gaap", {})
        if not isinstance(gaap, dict):
            raise ValueError("invalid taxonomy")
        records = {}
        row_count = 0
        for concept, metric in CONCEPTS.items():
            if concept not in gaap:
                continue
            units = gaap[concept]["units"]
            if not isinstance(units, dict):
                raise ValueError("invalid units")
            for unit, rows in units.items():
                if not isinstance(rows, list):
                    raise ValueError("invalid rows")
                row_count += len(rows)
                if row_count > 50000:
                    raise ValueError("too many rows")
                currency = unit.removesuffix("/shares")
                expected = currency + ("/shares" if metric.startswith("eps_") else "")
                if currency not in CURRENCIES or unit != expected:
                    continue
                for row in rows:
                    if row.get("form") not in FORMS:
                        continue
                    filed, end = date.fromisoformat(row["filed"]), date.fromisoformat(row["end"])
                    if (
                        filed > today
                        or end > today
                        or filed < today - timedelta(days=365)
                        or end < today - timedelta(days=730)
                    ):
                        continue
                    record = FinancialRecord(
                        metric=metric,
                        concept=concept,
                        unit=unit,
                        value=row["val"],
                        start=row["start"],
                        end=end,
                        filed=filed,
                        accession=row["accn"],
                        form=row["form"],
                        fiscal_year=row.get("fy"),
                        filing_period=row.get("fp"),
                        frame=row.get("frame"),
                    )
                    canonical = record.model_dump(mode="json")
                    digest = hashlib.sha256(
                        json.dumps(canonical, sort_keys=True).encode()
                    ).hexdigest()
                    records[digest] = record
        if len(records) > 2000:
            raise ValueError("too many selected records")
        return list(records.values())
    except CompanyPublicationError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise CompanyPublicationError("sec_invalid_response") from None


class SecFinancialClient:
    def __init__(self, cik: str, user_agent: str, *, transport=None):
        if not re.fullmatch(r"[0-9]{10}", cik) or not int(cik):
            raise ValueError("CIK vérifié requis.")
        self.cik, self.user_agent, self.transport = cik, user_agent, transport
        self.source_url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    async def fetch(self):
        try:
            async with asyncio.timeout(60):
                await asyncio.sleep(0.25)
                async with httpx.AsyncClient(timeout=45, transport=self.transport) as client:
                    async with client.stream(
                        "GET",
                        self.source_url,
                        follow_redirects=False,
                        headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                    ) as response:
                        if response.status_code == 429:
                            raise CompanyPublicationError("sec_rate_limit")
                        if response.status_code != 200:
                            raise CompanyPublicationError("sec_http_error")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 12_000_000:
                                raise CompanyPublicationError("sec_response_too_large")
            return parse_financials(bytes(body), self.cik)
        except (TimeoutError, httpx.TimeoutException):
            raise CompanyPublicationError("sec_timeout") from None
        except httpx.HTTPError:
            raise CompanyPublicationError("sec_http_error") from None
