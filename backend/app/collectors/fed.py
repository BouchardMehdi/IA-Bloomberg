from app.collectors.rss import RSSCollector


class FedPressCollector(RSSCollector):
    source_name = "Federal Reserve Board"
    source_url = "https://www.federalreserve.gov/"
    source_type = "central_bank"
    country = "US"
    region = "NORTH_AMERICA"
    reliability_score = 1.0
    feed_url = "https://www.federalreserve.gov/feeds/press_all.xml"
    language = "en"
