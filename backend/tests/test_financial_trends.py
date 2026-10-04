from datetime import UTC, datetime

import pytest

from app.services.financial_trends import compare_results

NOW = datetime(2026, 10, 4, tzinfo=UTC)


def row(**changes):
    return {
        "id": "current",
        "metric": "revenue",
        "concept": "Revenues",
        "taxonomy": "us-gaap",
        "unit": "USD",
        "start": "2026-01-01",
        "end": "2026-03-31",
        "value": "120",
        "filed": "2026-05-01",
        "accession": "0000320193-26-000001",
        "source_url": "https://example.org/filing",
        **changes,
    }


def previous(**changes):
    return row(
        **{"id": "previous", "start": "2025-01-01", "end": "2025-03-31", "value": "100", **changes}
    )


def test_exact_comparison_preserves_two_periods_and_source():
    result = compare_results([row(), previous()], NOW)[0]
    assert result["status"] == "comparable"
    assert result["delta"] == "20"
    assert result["percent"] == "20.00"
    assert result["previous"]["start"] == "2025-01-01"
    assert result["current"]["sources"][0]["filed"] == "2026-05-01"


@pytest.mark.parametrize(
    "changes",
    [
        {"concept": "SalesRevenueNet"},
        {"unit": "EUR"},
        {"accession": "0000320193-26-000002"},
        {"filed": "2026-05-02"},
        {"start": "2025-01-02"},
        {"end": "2025-09-30"},
        {"taxonomy": "ifrs-full"},
    ],
)
def test_incompatible_definitions_units_deposits_and_durations_are_blocked(changes):
    old = previous()
    old.update(changes)
    result = next(
        r for r in compare_results([row(), old], NOW) if r["current"]["start"] == "2026-01-01"
    )
    assert result["status"] == "not_comparable"
    assert result["delta"] is None


@pytest.mark.parametrize(
    "before,after,direction",
    [
        ("0", "100", "increase"),
        ("-100", "-50", "increase"),
        ("-100", "50", "turned_profitable"),
        ("100", "-50", "turned_loss"),
    ],
)
def test_losses_and_zero_do_not_become_misleading_growth_rates(before, after, direction):
    result = compare_results(
        [
            row(metric="net_income", concept="NetIncomeLoss", value=after),
            previous(metric="net_income", concept="NetIncomeLoss", value=before),
        ],
        NOW,
    )[0]
    assert result["direction"] == direction
    assert result["percent"] is None if before in {"0", "-100"} else result["percent"] == "-150.00"


def test_latest_amendment_without_comparative_does_not_fall_back_to_old_filing():
    amendment = row(id="amendment", filed="2026-06-01", accession="0000320193-26-000002")
    result = compare_results([row(), previous(), amendment], NOW)[0]
    assert result["status"] == "not_comparable"
    assert result["current"]["sources"][0]["id"] == "amendment"


def test_conflicting_values_are_not_resolved_by_arbitrary_latest_id():
    result = compare_results([row(), row(id="conflict", value="130"), previous()], NOW)[0]
    assert result["status"] == "not_comparable"
    assert result["current"]["value"] is None
    result = compare_results([row(), previous(), previous(id="conflict", value="101")], NOW)[0]
    assert result["status"] == "not_comparable"


def test_identical_republished_frames_preserve_evidence_without_inflating_change():
    result = compare_results([row(), row(id="duplicate"), previous()], NOW)[0]
    assert result["percent"] == "20.00"
    assert len(result["current"]["sources"]) == 2


def test_future_and_undated_duration_are_not_comparison_inputs():
    assert compare_results([row(filed="2026-10-05"), row(start=None)], NOW) == []


def test_52_and_53_week_years_are_not_equal_durations():
    current = row(start="2025-09-28", end="2026-09-26", filed="2026-10-01")
    old = previous(start="2024-09-22", end="2025-09-27", filed="2026-10-01")
    assert compare_results([current, old], NOW)[0]["status"] == "not_comparable"
