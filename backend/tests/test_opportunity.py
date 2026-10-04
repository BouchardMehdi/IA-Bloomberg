from datetime import UTC, datetime, timedelta

from app.services.opportunity import financial_arguments, upcoming_events

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)


def observation(**changes):
    return {
        "id": "schedule",
        "kind": "schedule",
        "provider": "alpha_vantage",
        "observed_at": (NOW - timedelta(days=1)).isoformat(),
        "published_at": None,
        "source_url": "https://example.org/calendar",
        "fiscal_period_end": "2026-09-30",
        "report_date": "2026-10-20",
        **changes,
    }


def test_moved_past_schedule_does_not_resurrect_future_history():
    older = observation(observed_at=(NOW - timedelta(days=3)).isoformat())
    newer = observation(report_date="2026-10-01")
    assert upcoming_events([older, newer], NOW) == []


def test_estimate_and_schedule_share_one_event_without_changing_history():
    items = [observation(), observation(kind="estimate", id="estimate")]
    assert len(upcoming_events(items, NOW)) == 1
    assert len(items) == 2


def test_reported_result_suppresses_old_prediction_for_same_period():
    assert upcoming_events([observation(), observation(kind="reported")], NOW) == []


def test_conflicting_provider_dates_are_visible_without_invented_publication():
    rows = upcoming_events(
        [observation(), observation(provider="manual", report_date="2026-10-25")], NOW
    )
    assert len(rows) == 2
    assert all(row["conflicting_dates"] for row in rows)
    assert rows[0]["published_at"] is None
    assert rows[0]["source_url"] == "https://example.org/calendar"


def test_simultaneous_snapshots_keep_conflicts_but_newer_snapshot_replaces_both():
    rows = [observation(), observation(report_date="2026-10-25", id="conflict")]
    assert len(upcoming_events(rows, NOW)) == 2
    rows.append(observation(observed_at=NOW.isoformat(), report_date="2026-11-01"))
    assert len(upcoming_events(rows, NOW)) == 1


def test_future_sources_and_observations_and_distant_calendar_are_excluded():
    future = (NOW + timedelta(days=1)).isoformat()
    for changes in [
        {"published_at": future},
        {"observed_at": future},
        {"report_date": "2027-10-20"},
    ]:
        assert upcoming_events([observation(**changes)], NOW) == []


def fact(**changes):
    return {
        "metric": "net_income",
        "value": "100",
        "unit": "USD",
        "start": "2026-01-01",
        "end": "2026-09-30",
        "filed": "2026-10-01",
        "concept": "NetIncomeLoss",
        "accession": "0000320193-26-000001",
        "source_url": "https://example.org/filing",
        **changes,
    }


def test_financial_signs_preserve_periods_units_and_conflicting_filings():
    positive, negative = financial_arguments(
        [
            fact(),
            fact(start="2026-07-01", value="-10"),
            fact(value="120", accession="0000320193-26-000002"),
            fact(value="0"),
            fact(metric="eps_diluted", value="2"),
            fact(end="2026-06-30", value="9999"),
            fact(filed="2026-10-05"),
        ],
        NOW,
    )
    assert len(positive) == 2
    assert len(negative) == 1
    assert negative[0]["start"] == "2026-07-01"
    assert positive[0]["sources"][0]["published_at"] == "2026-10-01"
    assert positive[0]["unit"] == "USD"
    assert "croissance" in positive[0]["notice"]


def test_old_accounting_observation_is_flagged_not_called_new():
    positive, _ = financial_arguments([fact(end="2026-01-31")], NOW)
    assert positive[0]["stale_period"] is True


def test_no_observations_means_empty_sections_not_zero_or_fabricated_signal():
    assert financial_arguments([], NOW) == ([], [])
    assert upcoming_events([], NOW) == []
