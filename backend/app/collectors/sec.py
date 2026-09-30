import httpx

from app.collectors.rss import RSSCollector


class SEC8KCollector(RSSCollector):
    source_name = "SEC EDGAR 8-K"
    source_url = "https://www.sec.gov/edgar/search-and-access"
    source_type = "regulator"
    country = "US"
    region = "NORTH_AMERICA"
    reliability_score = 1.0
    feed_url = (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&"
        "company=&dateb=&owner=include&start=0&count=100&output=atom"
    )
    language = "en"

    def __init__(
        self,
        user_agent: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        super().__init__(client)
        self.user_agent = user_agent
