import asyncio
import hashlib
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup


class UnsupportedDocument(ValueError):
    pass


@dataclass(frozen=True)
class DocumentContent:
    text: str
    url: str
    content_hash: str
    truncated: bool


def validate_document_url(url: str) -> str:
    parsed = urlsplit(url)
    parsed = parsed._replace(path=re.sub(r"/{2,}", "/", parsed.path))
    prefixes = {
        "www.ecb.europa.eu": "/press/",
        "www.federalreserve.gov": "/newsevents/",
        "www.sec.gov": "/Archives/edgar/data/",
    }
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.hostname not in prefixes
        or not parsed.path.startswith(prefixes[parsed.hostname])
        or re.search(r"(?:%2e|%2f|%5c|\\|\.\.)", parsed.path, re.I)
    ):
        raise UnsupportedDocument("URL is outside the supported official publication paths")
    return urlunsplit(parsed)


def extract_document_html(html: str, url: str, max_chars: int) -> DocumentContent:
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select(
        "script, style, nav, header, footer, aside, noscript, ix\\:hidden, ix\\:header, [hidden]"
    ):
        node.decompose()
    for node in soup.select("[style]"):
        if node.attrs is None:
            continue
        if re.search(
            r"(?:display\s*:\s*none|visibility\s*:\s*hidden)", node.get("style", ""), re.I
        ):
            node.decompose()
    host = urlsplit(url).hostname
    selectors = {
        "www.ecb.europa.eu": [
            ".ecb-pressContent",
            "#main-wrapper main",
            "main",
            "article",
            "#main-wrapper",
        ],
        "www.federalreserve.gov": ["#article", ".col-xs-12.col-sm-8.col-md-8", "main", "article"],
    }
    root = None
    for selector in selectors.get(host, []):
        root = soup.select_one(selector)
        if root is not None:
            break
    if root is None and host != "www.sec.gov":
        raise UnsupportedDocument("Publication text container was not found")
    root = root or soup.body or soup
    text = " ".join(root.get_text(" ", strip=True).split())
    if len(text) < 100:
        raise UnsupportedDocument("Publication text is empty or too short")
    truncated = len(text) > max_chars
    text = text[:max_chars]
    return DocumentContent(text, url, hashlib.sha256(text.encode()).hexdigest(), truncated)


def sec_primary_document(html: str, index_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for row in soup.select("table.tableFile tr"):
        cells = row.find_all("td")
        if len(cells) < 4 or cells[3].get_text(strip=True) not in {"8-K", "8-K/A"}:
            continue
        link = cells[2].find("a", href=True)
        if link is None:
            continue
        target = urljoin(index_url, link["href"])
        if urlsplit(target).path in {"/ix", "/ixviewer/doc/action"}:
            doc = parse_qs(urlsplit(target).query).get("doc", [""])[0]
            target = urljoin(index_url, doc)
        target = validate_document_url(target)
        if urlsplit(target).path.rsplit("/", 1)[0] != urlsplit(index_url).path.rsplit("/", 1)[0]:
            raise UnsupportedDocument("SEC document belongs to a different filing directory")
        return target
    raise UnsupportedDocument("No primary 8-K document in filing index")


class OfficialDocumentClient:
    def __init__(
        self,
        user_agent: str,
        max_bytes: int = 2_000_000,
        max_chars: int = 60_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self.max_chars = max_chars
        self.client = client

    async def _read(self, client: httpx.AsyncClient, url: str) -> tuple[str, str]:
        origin = urlsplit(url).hostname
        for _ in range(4):
            url = validate_document_url(url)
            if urlsplit(url).hostname != origin:
                raise UnsupportedDocument("Cross-domain redirect is not permitted")
            # Sequential requests remain well below the SEC fair-access limit.
            if origin == "www.sec.gov":
                await asyncio.sleep(0.25)
            async with client.stream(
                "GET", url, follow_redirects=False, headers={"User-Agent": self.user_agent}
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].lower()
                if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                    raise UnsupportedDocument(f"Unsupported content type: {content_type}")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > self.max_bytes:
                        raise UnsupportedDocument("Document exceeds download size limit")
                return data.decode(response.encoding or "utf-8", errors="replace"), url
        raise UnsupportedDocument("Too many redirects")

    async def fetch(self, url: str) -> DocumentContent:
        url = validate_document_url(url)
        async with asyncio.timeout(90):
            if self.client is None:
                async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)) as client:
                    return await self._fetch(client, url)
            return await self._fetch(self.client, url)

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> DocumentContent:
        html, final_url = await self._read(client, url)
        if urlsplit(final_url).hostname == "www.sec.gov" and re.search(
            r"-index\.html?$", urlsplit(final_url).path
        ):
            html, final_url = await self._read(client, sec_primary_document(html, final_url))
        return extract_document_html(html, final_url, self.max_chars)
