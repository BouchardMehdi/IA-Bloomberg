from app.collectors.rss import RSSCollector


class ECBPressCollector(RSSCollector):
    source_name = "European Central Bank"
    source_url = "https://www.ecb.europa.eu/"
    source_type = "central_bank"
    country = None
    region = "EUROPE"
    reliability_score = 1.0
    feed_url = "https://www.ecb.europa.eu/rss/press.html"
    language = "en"
