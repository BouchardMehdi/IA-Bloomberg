import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.market.sec_financials import parse_financials
from app.schemas.journal import DecisionCreate
from app.services.collection_health import health_state, safe_error
from app.services.financial_trends import compare_results
from app.services.opportunity import liquidity_observations


def test_health_does_not_hide_failure_with_old_success_or_disabled_state():
    now = datetime.now(UTC)
    run = SimpleNamespace(status="failed", started_at=now)
    assert health_state(run, now, now, 15) == "failed"
    assert health_state(run, now, now, 15, False) == "disabled"
    run.status = "running"
    run.started_at = now - timedelta(days=1)
    assert health_state(run, now, now, 15) == "interrupted"
    run.status = "success"
    assert health_state(run, now-timedelta(days=1), now, 15) == "stale"
    assert health_state(None, None, now, 15) == "pending"


def test_errors_do_not_expose_provider_body_or_credentials():
    assert safe_error("sec_rate_limit") == "sec_rate_limit"
    assert safe_error("GET https://provider/?apikey=secret") == "collecte_echouee"


def declaration():
    return {"client_request_id":str(uuid4()), "instrument_id":str(uuid4()), "title":"Hypothèse déclarée",
        "hypothesis":"Une hypothèse de recherche à vérifier", "risks":"Risques à examiner", "invalidation":"Résultats contradictoires",
        "horizon":"Trois mois", "review_on":"2026-10-20", "status":"considering", "acknowledged":True,
        "evidence":[{"url":"https://example.org/proof", "published_at":(datetime.now(UTC)-timedelta(days=1)).isoformat(), "note":"Preuve à examiner"}]}


@pytest.mark.parametrize("change", [{"acknowledged":False}, {"evidence":[]}, {"status":"buy_now"}])
def test_journal_requires_sources_and_explicit_acknowledgment(change):
    with pytest.raises(ValidationError):
        DecisionCreate.model_validate({**declaration(), **change})


@pytest.mark.parametrize("stamp", ["2099-01-01T00:00:00Z", "2026-01-01T12:00:00"])
def test_journal_never_invents_publication_timezone_or_backdates_evidence(stamp):
    data = declaration()
    data["evidence"][0]["published_at"] = stamp
    with pytest.raises(ValidationError):
        DecisionCreate.model_validate(data)


def test_ifrs_concepts_are_kept_separate_and_not_used_as_gaap_growth_or_eps():
    today = datetime.now(UTC).date()
    row = {"val":-50, "start":str(today-timedelta(days=400)), "end":str(today-timedelta(days=35)),
        "filed":str(today-timedelta(days=5)), "accn":"0001234567-26-000001", "form":"20-F"}
    data = {"cik":1234567, "facts":{
        "ifrs-full":{"Revenue":{"units":{"EUR":[{**row,"val":100}]}}, "ProfitLoss":{"units":{"EUR":[row]}},
            "CashAndCashEquivalents":{"units":{"EUR":[{k:v for k,v in {**row,"val":30}.items() if k!="start"}]}},
            "BasicEarningsLossPerShare":{"units":{"EUR/shares":[row]}}},
        "us-gaap":{"Revenues":{"units":{"EUR":[{**row,"val":200}]}}}}}
    rows = parse_financials(json.dumps(data).encode(), "0001234567")
    assert len(rows)==4 and not any(r.metric.startswith("eps") for r in rows)
    assert {r.taxonomy for r in rows}=={"us-gaap","ifrs-full"}
    cash=next(r for r in rows if r.concept=="CashAndCashEquivalents")
    assert cash.start is None
    loss=next(r for r in rows if r.concept=="ProfitLoss")
    assert loss.metric=="ifrs_profit_loss" and loss.value==-50
    assert compare_results([r.model_dump(mode="json") for r in rows if r.taxonomy=="ifrs-full"], datetime.now(UTC))==[]
    assert liquidity_observations([loss.model_dump(mode="json")], datetime.now(UTC)) == []
