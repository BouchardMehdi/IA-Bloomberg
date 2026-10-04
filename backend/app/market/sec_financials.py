"""Issuer facts with explicit instant/duration conventions; no security EPS inference."""

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
    "CashAndCashEquivalentsAtCarryingValue": "cash",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": "cash_restricted",
    "ShortTermBorrowings": "short_term_debt",
    "LongTermDebtCurrent": "debt_current",
    "LongTermDebtNoncurrent": "debt_noncurrent",
    "LongTermDebt": "long_term_debt",
    "LongTermDebtAndCapitalLeaseObligationsCurrent": "debt_leases_current",
    "LongTermDebtAndCapitalLeaseObligationsNoncurrent": "debt_leases_noncurrent",
    "NetCashProvidedByUsedInOperatingActivities": "operating_cash_flow",
    "NetCashProvidedByUsedInInvestingActivities": "investing_cash_flow",
    "NetCashProvidedByUsedInFinancingActivities": "financing_cash_flow",
    "PaymentsToAcquirePropertyPlantAndEquipment": "capex",
}
INSTANT_CONCEPTS = frozenset(
    concept
    for concept, metric in CONCEPTS.items()
    if metric
    in {
        "cash",
        "cash_restricted",
        "short_term_debt",
        "debt_current",
        "debt_noncurrent",
        "long_term_debt",
        "debt_leases_current",
        "debt_leases_noncurrent",
    }
)
COLLECTOR_VERSION = "financial-v2"
METRIC_LABELS = {
    "revenue": "chiffre d’affaires",
    "net_income": "résultat net",
    "eps_basic": "BPA de base",
    "eps_diluted": "BPA dilué",
    "cash": "trésorerie et équivalents",
    "cash_restricted": "trésorerie incluant fonds restreints",
    "short_term_debt": "emprunts à court terme",
    "debt_current": "dette long terme, part courante",
    "debt_noncurrent": "dette long terme, part non courante",
    "long_term_debt": "dette long terme",
    "debt_leases_current": "dette et crédit-bail, part courante",
    "debt_leases_noncurrent": "dette et crédit-bail, part non courante",
    "operating_cash_flow": "flux de trésorerie d’exploitation",
    "investing_cash_flow": "flux de trésorerie d’investissement",
    "financing_cash_flow": "flux de trésorerie de financement",
    "capex": "paiements d’acquisition d’immobilisations corporelles",
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
    start: date | None = None
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
        instant = self.concept in INSTANT_CONCEPTS
        if instant and (self.start is not None or self.value < 0):
            raise ValueError("invalid instant balance")
        if not instant and (self.start is None or self.start > self.end):
            raise ValueError("duration requires explicit start")
        if not self.end <= self.filed <= datetime.now(UTC).date():
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
                        start=row.get("start") if concept in INSTANT_CONCEPTS else row["start"],
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
