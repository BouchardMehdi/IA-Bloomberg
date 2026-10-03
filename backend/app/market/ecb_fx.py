"""Bounded ECB XML reference rates, converted from the EUR base to USD."""

import asyncio
import re
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from xml.etree import ElementTree

import httpx

from app.schemas.international import CURRENCIES

SOURCE_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
NS = "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"
MAX_BYTES = 1_000_000


class FxCollectionError(ValueError):
    pass


def parse_reference_rates(raw: bytes, today: date | None = None) -> list[dict]:
    today = today or datetime.now(UTC).date()
    try:
        if len(raw) > MAX_BYTES:
            raise ValueError()
        xml = raw.decode("utf-8-sig")
        if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
            raise ValueError()
        root = ElementTree.fromstring(xml)
        days = root.findall(f"./{{{NS}}}Cube/{{{NS}}}Cube")
        if not 1 <= len(days) <= 150:
            raise ValueError()
        seen_dates, records = set(), []
        for node in days:
            reference_date = date.fromisoformat(node.attrib["time"])
            if reference_date > today or reference_date in seen_dates:
                raise ValueError()
            seen_dates.add(reference_date)
            rates = {}
            for child in node:
                if child.tag != f"{{{NS}}}Cube":
                    raise ValueError()
                currency, text = child.attrib["currency"], child.attrib["rate"]
                if (
                    not re.fullmatch(r"[A-Z]{3}", currency)
                    or currency in rates
                    or currency == "EUR"
                    or len(text) > 32
                    or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text)
                ):
                    raise ValueError()
                value = Decimal(text)
                if not 0 < value < Decimal("10000000000"):
                    raise ValueError()
                rates[currency] = value
            if "USD" not in rates:
                raise ValueError()
            for currency in sorted((rates.keys() | {"EUR"}) & (CURRENCIES - {"USD"})):
                # EUR/EUR=1 is an identity, not an external observation.
                denominator = rates.get(currency, Decimal("1"))
                with localcontext() as context:
                    context.prec = 50
                    raw_rate = rates["USD"] / denominator
                    if raw_rate >= Decimal("10000000000"):
                        raise ValueError()
                    rate = raw_rate.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_UP)
                if not 0 < rate < Decimal("10000000000"):
                    raise ValueError()
                records.append(
                    {
                        "currency": currency,
                        "rate_date": reference_date,
                        "usd_per_unit": rate,
                        "derivation": {
                            "base_currency": "EUR",
                            "usd_per_eur": str(rates["USD"]),
                            "currency_per_eur": str(denominator),
                            "formula": "USD_per_EUR / currency_per_EUR",
                        },
                    }
                )
        if not records:
            raise ValueError()
        return sorted(records, key=lambda r: (r["rate_date"], r["currency"]))
    except (ValueError, KeyError, UnicodeError, ElementTree.ParseError):
        raise FxCollectionError("invalid_reference_payload") from None


class EcbFxClient:
    def __init__(self, *, transport=None):
        self.transport = transport

    async def fetch(self) -> list[dict]:
        try:
            async with asyncio.timeout(60):
                async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                    async with client.stream("GET", SOURCE_URL) as response:
                        response.raise_for_status()
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > MAX_BYTES:
                                raise FxCollectionError("response_too_large")
        except (httpx.HTTPError, TimeoutError):
            raise FxCollectionError("reference_http_error") from None
        return parse_reference_rates(bytes(raw))
