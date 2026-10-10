"""Public official RSS only: bounded downloads, no paywall or arbitrary URL."""
from urllib.parse import urlsplit

import httpx

from app.collectors.rss import RSSCollector, _content_hash


class OfficialInternationalCollector(RSSCollector):
    source_type = "official_news"
    region = "EUROPE"
    reliability_score = 1.0
    max_bytes = 2_000_000

    async def fetch(self):
        async def download(client):
            url = self.feed_url
            for _ in range(4):
                async with client.stream("GET", url) as response:
                    if response.is_redirect:
                        from urllib.parse import urljoin
                        url = urljoin(url, response.headers.get("location", ""))
                        p = urlsplit(url)
                        if p.scheme != "https" or p.hostname != urlsplit(self.feed_url).hostname or p.username or p.port not in {None, 443}:
                            raise ValueError("Redirection RSS hors domaine officiel refusée.")
                        continue
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise ValueError("Flux RSS trop volumineux.")
                        chunks.append(chunk)
                    return b"".join(chunks)
            raise ValueError("Trop de redirections RSS.")
        if self._client:
            return await download(self._client)
        async with httpx.AsyncClient(timeout=20, follow_redirects=False,
                                     headers={"User-Agent": self.user_agent}) as client:
            return await download(client)

    def normalize(self, payload):
        articles = super().normalize(payload)
        result = []
        for article in articles[:200]:
            p = urlsplit(article.url)
            if p.scheme != "https" or p.hostname != urlsplit(self.source_url).hostname or p.username or p.port not in {None, 443}:
                continue
            # Only the publisher-provided RSS excerpt is retained, no linked HTML/PDF.
            article.content = article.content[:4000] if article.content else None
            article.content_hash = _content_hash(article.title, article.content, article.url)
            result.append(article)
        return result


class AirbusPressCollector(OfficialInternationalCollector):
    source_name = "Airbus official press releases"
    source_url = "https://www.airbus.com/en/rss-feeds"
    feed_url = "https://www.airbus.com/en/generate-rss-feeds?type=all-press-releases"
    language = "en"
    # An issuer is not assigned a country/listing/CIK from its website.


class AMFNewsCollector(OfficialInternationalCollector):
    source_name = "AMF official news"
    source_url = "https://www.amf-france.org/fr/abonnements-flux-rss"
    feed_url = "https://www.amf-france.org/fr/flux-rss/display/21"
    language = "fr"
    country = "FR"


class BankOfEnglandNewsCollector(OfficialInternationalCollector):
    source_name = "Bank of England official news"
    source_url = "https://www.bankofengland.co.uk/news"
    feed_url = "https://www.bankofengland.co.uk/rss/news"
    language = "en"
    country = "GB"
    # Kept as official_publication: no issuer/listing or market impact inferred.
