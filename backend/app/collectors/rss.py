import calendar
import hashlib
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import feedparser
import httpx

from app.collectors.base import BaseCollector, NormalizedArticle


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return _normalize_text(" ".join(self.parts))


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def _canonicalize_url(value: str, base_url: str) -> str:
    absolute = urljoin(base_url, value.strip())
    parts = urlsplit(absolute)
    filtered_query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path,
            urlencode(sorted(filtered_query)),
            "",
        )
    )


def _content_hash(title: str, content: str | None, url: str) -> str:
    body_or_url = _normalize_text(content).casefold() if content else url
    normalized = f"{_normalize_text(title).casefold()}\n{body_or_url}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _published_at(entry: feedparser.FeedParserDict) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=UTC)


class RSSCollector(BaseCollector):
    feed_url: str
    language: str | None = None
    request_timeout_seconds: float = 20.0

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def fetch(self) -> bytes:
        if self._client is not None:
            response = await self._client.get(self.feed_url)
            response.raise_for_status()
            return response.content

        async with httpx.AsyncClient(
            timeout=self.request_timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "MarketAI/0.1 RSS collector"},
        ) as client:
            response = await client.get(self.feed_url)
            response.raise_for_status()
            return response.content

    def normalize(self, payload: bytes) -> list[NormalizedArticle]:
        parsed = feedparser.parse(payload)
        if parsed.bozo and not parsed.entries:
            raise ValueError(f"Invalid RSS feed: {parsed.bozo_exception}")

        fetched_at = datetime.now(UTC)
        articles: list[NormalizedArticle] = []
        for entry in parsed.entries:
            title = _normalize_text(entry.get("title", ""))
            link = entry.get("link", "")
            if not title or not link:
                continue

            url = _canonicalize_url(link, self.feed_url)
            raw_content = entry.get("summary", "")
            if entry.get("content"):
                raw_content = entry.content[0].get("value", raw_content)
            content = _html_to_text(raw_content) or None

            articles.append(
                NormalizedArticle(
                    external_id=entry.get("id") or entry.get("guid") or url,
                    url=url,
                    title=title,
                    content=content,
                    language=entry.get("language") or self.language,
                    author=entry.get("author"),
                    published_at=_published_at(entry),
                    fetched_at=fetched_at,
                    content_hash=_content_hash(title, content, url),
                )
            )
        return articles
