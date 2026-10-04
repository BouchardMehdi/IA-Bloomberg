"""Bounded, issuer-specific EDGAR submissions; no guessed security identities."""

import asyncio
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta

import httpx

from app.collectors.base import BaseCollector, NormalizedArticle

FORMS = {
    "8-K",
    "8-K/A",
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A",
    "6-K",
    "6-K/A",
    "20-F",
    "20-F/A",
    "40-F",
    "40-F/A",
}


class CompanyPublicationError(ValueError):
    def __init__(self, code):
        self.code = (
            code
            if code
            in {
                "sec_http_error",
                "sec_rate_limit",
                "sec_timeout",
                "sec_invalid_response",
                "sec_response_too_large",
                "sec_identity_mismatch",
            }
            else "sec_invalid_response"
        )
        super().__init__(self.code)


class SECCompanyCollector(BaseCollector):
    source_type = "regulator"
    country = "US"
    region = "NORTH_AMERICA"
    reliability_score = 1.0

    def __init__(self, cik: str, user_agent: str, *, client=None, now=None):
        if not re.fullmatch(r"[0-9]{10}", cik) or int(cik) == 0:
            raise ValueError("CIK vérifié à dix chiffres requis.")
        self.cik = cik
        self.user_agent = user_agent
        self.client = client
        self.now = now
        self.source_name = f"SEC company {cik}"
        self.source_url = f"https://data.sec.gov/submissions/CIK{cik}.json"

    async def fetch(self):
        async def read(client):
            await asyncio.sleep(0.25)
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
                    if len(body) > 4_000_000:
                        raise CompanyPublicationError("sec_response_too_large")
                return bytes(body)

        try:
            async with asyncio.timeout(45):
                if self.client is not None:
                    return await read(self.client)
                async with httpx.AsyncClient(timeout=30) as client:
                    return await read(client)
        except (httpx.TimeoutException, TimeoutError):
            raise CompanyPublicationError("sec_timeout") from None
        except httpx.HTTPError:
            raise CompanyPublicationError("sec_http_error") from None

    def normalize(self, payload):
        now = self.now or datetime.now(UTC)
        try:
            data = json.loads(payload)
            identity = str(data["cik"])
            if not re.fullmatch(r"[0-9]{1,10}", identity) or identity.zfill(10) != self.cik:
                raise CompanyPublicationError("sec_identity_mismatch")
            name = data["name"]
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 512:
                raise ValueError("invalid name")
            recent = data["filings"]["recent"]
            columns = ["form", "accessionNumber", "acceptanceDateTime", "primaryDocument"]
            if any(not isinstance(recent[key], list) for key in columns):
                raise ValueError("invalid arrays")
            length = len(recent["form"])
            if length > 10000 or any(len(recent[key]) != length for key in columns):
                raise ValueError("invalid array lengths")
            articles, accessions = [], set()
            for index, form in enumerate(recent["form"]):
                if form not in FORMS:
                    continue
                published = datetime.fromisoformat(recent["acceptanceDateTime"][index])
                if published.tzinfo is None:
                    raise ValueError("undated publication")
                published = published.astimezone(UTC)
                if published > now or published < now - timedelta(days=365):
                    continue
                accession = recent["accessionNumber"][index]
                document = recent["primaryDocument"][index]
                if not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", accession):
                    raise ValueError("invalid accession")
                if (
                    not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,250}\.(?:htm|html)", document)
                    or ".." in document
                ):
                    raise ValueError("unsupported primary document")
                if accession in accessions:
                    raise ValueError("duplicate accession")
                accessions.add(accession)
                url = f"https://www.sec.gov/Archives/edgar/data/{int(self.cik)}/"
                url += f"{accession.replace('-', '')}/{document}"
                title = f"{form} - {name.strip()} ({self.cik}) (Filer)"
                content = f"Dépôt SEC {form}. Accession {accession}. "
                content += f"Accepté le {published.isoformat()}. "
                content += "Métadonnées du dépôt ; consulter le document complet."
                articles.append(
                    NormalizedArticle(
                        external_id=f"accession-number={accession}",
                        url=url,
                        title=title,
                        content=content,
                        language="en",
                        published_at=published,
                        fetched_at=now,
                        content_hash=hashlib.sha256(url.encode()).hexdigest(),
                    )
                )
            return sorted(articles, key=lambda article: article.published_at, reverse=True)[:50]
        except CompanyPublicationError:
            raise
        except (ValueError, TypeError, KeyError, AttributeError):
            raise CompanyPublicationError("sec_invalid_response") from None
