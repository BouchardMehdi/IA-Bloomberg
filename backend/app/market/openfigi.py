"""OpenFIGI public mapping API; identifiers are observations, never WLS composition."""

import asyncio
import json

import httpx
from pydantic import BaseModel, ConfigDict, Field

URL = "https://api.openfigi.com/v3/mapping"
DOC_URL = "https://www.openfigi.com/api/documentation"
MIC_SOURCE = "https://www.openfigi.com/docs/OpenFIGI-exchange-codes.csv"
# Operating Nasdaq has several segments; retain all results, never choose one arbitrarily.
US_MICS = {"NYSE": ("XNYS",), "Nasdaq": ("XNGS", "XNMS", "XNCM")}
MIC_EXCHANGE_CODES = {"XNYS": "UN", "XNGS": "UW", "XNMS": "UQ", "XNCM": "UR"}


class FigiRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    figi: str = Field(pattern=r"^BBG[A-Z0-9]{9}$")
    ticker: str | None = Field(default=None, max_length=100)
    name: str | None = Field(default=None, max_length=512)
    exchCode: str | None = Field(default=None, max_length=50)
    compositeFIGI: str | None = Field(default=None, pattern=r"^BBG[A-Z0-9]{9}$")
    shareClassFIGI: str | None = Field(default=None, pattern=r"^BBG[A-Z0-9]{9}$")
    marketSector: str | None = Field(default=None, max_length=100)
    securityType: str | None = Field(default=None, max_length=100)
    securityType2: str | None = Field(default=None, max_length=100)


class FigiError(ValueError):
    def __init__(self, code, retry_seconds=300):
        self.code = code
        self.retry_seconds = retry_seconds
        super().__init__(code)


def parse_job(value):
    if not isinstance(value, dict):
        raise FigiError("invalid_response")
    if "error" in value:
        return {"status": "provider_error", "records": []}
    if "warning" in value and "data" not in value:
        return {"status": "not_found", "records": []}
    raw = value.get("data")
    if not isinstance(raw, list) or len(raw) > 100:
        raise FigiError("invalid_response")
    try:
        records = [FigiRecord.model_validate(row).model_dump() for row in raw]
    except ValueError:
        raise FigiError("invalid_response") from None
    # Conflicting descriptions for the same FIGI are ambiguous too.
    unique = {json.dumps(row, sort_keys=True): row for row in records}
    records = list(unique.values())
    status = "resolved" if len(records) == 1 else "ambiguous" if records else "not_found"
    return {"status": status, "records": records}


class OpenFigiClient:
    def __init__(self, transport=None):
        self.transport = transport

    async def fetch(self, jobs):
        if not 1 <= len(jobs) <= 5:
            raise ValueError("OpenFIGI : un à cinq identifiants par requête.")
        try:
            async with asyncio.timeout(25):
                async with httpx.AsyncClient(
                    timeout=20, transport=self.transport, follow_redirects=False
                ) as client:
                    async with client.stream("POST", URL, json=jobs) as response:
                        if response.status_code == 429:
                            try:
                                retry = int(response.headers.get("ratelimit-reset", "60"))
                            except ValueError:
                                retry = 60
                            raise FigiError("quota", max(60, min(86400, retry)))
                        if response.status_code != 200:
                            raise FigiError("http_error")
                        body = bytearray()
                        async for chunk in response.aiter_bytes():
                            body.extend(chunk)
                            if len(body) > 1_000_000:
                                raise FigiError("response_too_large")
            payload = json.loads(body)
            if not isinstance(payload, list) or len(payload) != len(jobs):
                raise FigiError("invalid_response")
            return [parse_job(item) for item in payload]
        except FigiError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise FigiError("timeout") from None
        except (httpx.HTTPError, ValueError):
            raise FigiError("invalid_response") from None
