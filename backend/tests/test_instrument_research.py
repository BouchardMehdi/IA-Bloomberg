from datetime import UTC, datetime
from types import SimpleNamespace as NS

from app.services.instrument_research import relationship, research_card


def fixture(entities=None, source_cik=None, dated=True):
    instrument = NS(cik="0000000001", symbol="AAA", exchange="NYSE")
    event = NS(
        id="event",
        title="Publication",
        event_type="company_event",
        parent_event_id="parent",
        evidence_excerpt="AAA reports results.",
        fact_analysis_run=None,
        structured_data={
            "fact": {"summary": "Results reported."},
            "entity_resolution": {"entities": entities or []},
        },
        company_links=[NS(company=NS(cik=source_cik))] if source_cik else [],
        article_links=[
            NS(
                is_primary_source=True,
                article=NS(
                    document_url="https://example.org/report",
                    url="https://example.org/index",
                    published_at=datetime.now(UTC) if dated else None,
                ),
            )
        ],
    )
    return instrument, event


def mention(status="resolved", ticker="AAA", exchange="NYSE", role="counterparty"):
    return {
        "status": status,
        "kind": "equity",
        "quote": "AAA reports results.",
        "role": role,
        "candidates": [{"cik": "0000000001", "ticker": ticker, "exchange": exchange}],
    }


def test_exact_security_preserves_counterparty_role_and_source():
    instrument, event = fixture([mention()])
    card = research_card(event, instrument)
    assert card["relationship"]["basis"] == "security_mention"
    assert card["relationship"]["role"] == "counterparty"
    assert card["sources"][0]["url"] == "https://example.org/report"
    assert card["kind"] == "extracted_fact"


def test_other_share_class_or_exchange_is_only_issuer_context():
    for entity in [mention(ticker="AAA.B"), mention(exchange="Nasdaq")]:
        instrument, event = fixture([entity])
        assert relationship(event, instrument)["basis"] == "issuer_mention"


def test_unresolved_ambiguous_and_unverified_mentions_are_not_links():
    for status in ["unresolved", "ambiguous", "unverified"]:
        instrument, event = fixture([mention(status=status)])
        assert research_card(event, instrument) is None


def test_no_blanket_macro_association_or_undated_claims():
    instrument, event = fixture()
    assert research_card(event, instrument) is None
    instrument, event = fixture(source_cik=instrument.cik, dated=False)
    assert research_card(event, instrument) is None


def test_issuer_document_is_context_not_a_security_mention():
    instrument, event = fixture(source_cik="0000000001")
    assert research_card(event, instrument)["relationship"]["basis"] == "issuer_document"
    event.parent_event_id = None
    assert research_card(event, instrument)["summary"] is None
