from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.research_ranking import data_checks, recent_card, score_research

NOW = datetime(2026, 10, 3, 12, tzinfo=UTC)


def card(index=1, **updates):
    return {
        "event_id": str(index),
        "publication_id": "pub" + str(index),
        "published_at": NOW - timedelta(days=1),
        "kind": "extracted_fact",
        "evidence": "AAA reports its results",
        "event_type": "financial_results",
        "relationship": {"basis": "security_mention", "role": "subject"},
        "coverage": {"coverage_ratio": 1, "selected_count": 1, "analyzed_count": 1},
        **updates,
    }


def test_score_components_are_bounded_explained_and_sourced():
    result = score_research([card(1), card(2), card(3), card(4)], NOW)
    assert result["score"] == 100 == sum(c["points"] for c in result["components"])
    assert result["recent_fact_count"] == 4 and result["scored_publication_count"] == 3
    assert len(result["facts"]) == 3
    for component in result["components"]:
        assert 0 <= component["points"] <= component["maximum"]
        assert set(component["event_ids"]) <= {f["event_id"] for f in result["facts"]}


def test_sibling_facts_and_their_parent_do_not_inflate_publication_count():
    first = card(publication_id="same")
    siblings = [card(i, publication_id="same") for i in range(2, 12)]
    parent = card(12, publication_id="same", kind="publication")
    result = score_research([first, *siblings, parent], NOW)
    assert result["score"] == score_research([first], NOW)["score"] == 90
    assert result["recent_fact_count"] == 11 and result["recent_publication_count"] == 1
    assert result["scored_publication_count"] == 1


@pytest.mark.parametrize(
    "updates",
    [
        {"kind": "publication"},
        {"evidence": None},
        {"evidence": "  "},
        {"publication_group_verified": False},
        {"relationship": {"basis": "issuer_document", "role": "source_subject"}},
        {"relationship": {"basis": "issuer_mention", "role": "source_subject"}},
    ],
)
def test_documents_or_unproven_facts_do_not_receive_a_fact_score(updates):
    result = score_research([card(**updates)], NOW)
    assert result["score"] == 0 and result["facts"] == []
    assert result["research_status"] == "documents_only"


def test_other_share_classes_remain_issuer_context_and_direction_is_not_predicted():
    exact = score_research([card(sentiment_score=-1)], NOW)
    issuer = score_research(
        [card(relationship={"basis": "issuer_mention", "role": "mention"})], NOW
    )
    assert exact["score"] > issuer["score"]
    assert exact["score"] == score_research([card(sentiment_score=1)], NOW)["score"]
    assert "buy" not in exact and "return" not in exact


@pytest.mark.parametrize(
    "age,points",
    [
        (timedelta(days=2), 30),
        (timedelta(days=2, seconds=1), 20),
        (timedelta(days=7), 20),
        (timedelta(days=7, seconds=1), 10),
    ],
)
def test_recency_uses_publication_time_boundaries(age, points):
    result = score_research([card(published_at=NOW - age)], NOW)
    assert result["components"][0]["points"] == points


def event_with_sources(dates):
    return NS(
        id="fact",
        parent_event_id="parent",
        title="Fact",
        event_type="financial_results",
        evidence_excerpt="AAA reports results",
        fact_analysis_run=None,
        company_links=[],
        structured_data={
            "fact": {"summary": "AAA reports results"},
            "entity_resolution": {
                "entities": [
                    {
                        "status": "resolved",
                        "kind": "equity",
                        "role": "subject",
                        "quote": "AAA",
                        "candidates": [{"cik": "0000000001", "ticker": "AAA", "exchange": "NYSE"}],
                    }
                ]
            },
        },
        article_links=[
            NS(
                is_primary_source=primary,
                article=NS(
                    url="https://example.org/" + str(index), document_url=None, published_at=when
                ),
            )
            for index, (when, primary) in enumerate(dates)
        ],
    )


@pytest.mark.parametrize(
    "dates",
    [
        [(None, True)],
        [(NOW + timedelta(seconds=1), True)],
        [(NOW - timedelta(days=31), True)],
        [(NOW - timedelta(days=31), True), (NOW, False)],
    ],
)
def test_undated_future_old_or_republished_old_facts_are_excluded(dates):
    instrument = NS(cik="0000000001", symbol="AAA", exchange="NYSE")
    assert recent_card(event_with_sources(dates), instrument, NOW) is None


def test_newer_secondary_source_does_not_change_fact_recency():
    instrument = NS(cik="0000000001", symbol="AAA", exchange="NYSE")
    event = event_with_sources([(NOW - timedelta(days=8), True), (NOW, False)])
    recent = recent_card(event, instrument, NOW)
    assert recent["published_at"] == NOW - timedelta(days=8)
    assert score_research([recent], NOW)["components"][0]["points"] == 10


def test_partial_coverage_and_unknown_coverage_are_review_questions():
    partial = score_research(
        [card(coverage={"coverage_ratio": 0.2, "document_truncated": True})], NOW
    )
    assert any("partielle" in check for check in partial["checks"])
    unknown = score_research([card(coverage=None)], NOW)
    assert any("non documentée" in check for check in unknown["checks"])
    empty = score_research([], NOW)
    assert empty["score"] == 0 and empty["research_status"] == "no_recent_evidence"


def test_data_checks_separate_local_quote_fx_and_wls():
    instrument = NS(currency="HKD")
    wls = {"status": "unknown", "source_url": None, "as_of": None}
    no_price = data_checks(
        instrument, None, {"conversion": None, "status": "missing_price"}, wls, NOW
    )
    assert [c["status"] for c in no_price] == ["missing", "not_evaluated", "unknown"]
    price = NS(session_date=NOW.date(), source_url="https://example.org/price")
    missing_fx = data_checks(
        instrument, price, {"conversion": None, "status": "missing_fx"}, wls, NOW
    )
    assert [c["status"] for c in missing_fx] == ["available", "missing", "unknown"]
    old_fx = {
        "fx_date": (NOW - timedelta(days=20)).date().isoformat(),
        "fx_source_url": "https://example.org/fx",
    }
    stale = data_checks(instrument, price, {"conversion": old_fx, "status": "stale"}, wls, NOW)
    assert stale[1]["status"] == "stale" and stale[1]["source_url"] == old_fx["fx_source_url"]
    instrument.currency = "USD"
    assert (
        data_checks(instrument, price, {"conversion": None, "status": "available"}, wls, NOW)[1][
            "status"
        ]
        == "not_required"
    )


def test_ranking_api_bounds_pagination_before_any_database_access():
    client = TestClient(app)
    for query in ("limit=0", "limit=51", "offset=-1", "offset=20001"):
        assert client.get("/api/v1/market/research-ranking?" + query).status_code == 422
