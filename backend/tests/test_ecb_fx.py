from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.market.ecb_fx import (
    MAX_BYTES,
    SOURCE_URL,
    EcbFxClient,
    FxCollectionError,
    parse_reference_rates,
)

FIXTURE = (Path(__file__).parent / "fixtures" / "ecb_fx_90d.xml").read_bytes()


def test_usd_conversion_direction_history_and_evidence():
    records = parse_reference_rates(FIXTURE)
    latest = {r["currency"]: r for r in records if r["rate_date"] == date(2020, 1, 3)}
    assert len(records) == 6
    assert latest["EUR"]["usd_per_unit"] == Decimal("1.20")
    assert latest["GBP"]["usd_per_unit"] == Decimal("1.5")
    assert latest["HKD"]["usd_per_unit"] == Decimal("0.125")
    assert "TWD" not in latest and "USD" not in latest and "THB" not in latest
    assert latest["HKD"]["derivation"]["currency_per_eur"] == "9.60"
    assert latest["HKD"]["derivation"]["usd_per_eur"] == "1.20"


@pytest.mark.parametrize(
    "payload",
    [
        b"not xml",
        b"<html>maintenance</html>",
        b"<!DOCTYPE x><x />",
        b"x" * (MAX_BYTES + 1),
        FIXTURE.replace(b"2020-01-03", b"2999-01-03"),
        FIXTURE.replace(b"2020-01-03", b"2020-01-02"),
        FIXTURE.replace(b'currency="USD"', b'currency="EUR"'),
        FIXTURE.replace(b'rate="9.60"', b'rate="0"'),
        FIXTURE.replace(b'rate="9.60"', b'rate="NaN"'),
        FIXTURE.replace(b'rate="9.60"', b'rate="-1"'),
        FIXTURE.replace(b'currency="HKD"', b'currency="GBP"'),
        FIXTURE.replace(b'rate="9.60"', b'rate="0.00000000000000000000000001"'),
    ],
)
def test_invalid_document_is_rejected_as_a_whole(payload):
    with pytest.raises(FxCollectionError, match="invalid_reference_payload"):
        parse_reference_rates(payload)


@pytest.mark.asyncio
async def test_http_client_uses_fixed_official_url():
    def handler(request):
        assert str(request.url) == SOURCE_URL
        return httpx.Response(200, content=FIXTURE)

    assert len(await EcbFxClient(transport=httpx.MockTransport(handler)).fetch()) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,content,error",
    [
        (500, b"private response", "reference_http_error"),
        (200, b"x" * (MAX_BYTES + 1), "response_too_large"),
    ],
)
async def test_http_failures_have_sanitized_codes(status, content, error):
    client = EcbFxClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, content=content))
    )
    with pytest.raises(FxCollectionError, match=error):
        await client.fetch()
