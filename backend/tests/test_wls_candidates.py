from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.market.wls import eligibility
from app.schemas.wls_candidates import CandidateManifest, CandidateMapping
from app.services.wls_candidates import listing_identity, mapping_matches


def manifest():
    return {
        "schema_version": 1,
        "source_filename": "supplied.xlsx",
        "source_sha256": "a" * 64,
        "source_sheet": "Feuil1",
        "observed_at": datetime.now(UTC).isoformat(),
        "origin": "Liste WLS partielle confirmée par l'utilisateur",
        "composition_as_of": None,
        "source_url": None,
        "partial": True,
        "security_count": 1,
        "eligibility_imported": False,
        "records": [
            {
                "bloomberg_identifier": "005930 KS Equity",
                "bloomberg_ticker": "005930",
                "bloomberg_market_code": "KS",
                "bloomberg_sector": "Equity",
                "source_cell": "A1",
                "listing_mapping": None,
            }
        ],
    }


def test_partial_manifest_preserves_unknown_date_and_leading_zeros():
    parsed = CandidateManifest.model_validate(manifest())
    assert parsed.records[0].bloomberg_ticker == "005930"
    assert parsed.composition_as_of is None
    # A prepared snapshot cannot accidentally satisfy the existing purchase guard.
    registry = SimpleNamespace(records=[parsed.model_dump()], source_url="urn:sha256:example")
    instrument = SimpleNamespace(symbol="005930", exchange="XKRX")
    assert eligibility(instrument, registry)["status"] != "verified"


@pytest.mark.parametrize(
    "change",
    [
        {"security_count": 2},
        {"partial": False},
        {"eligibility_imported": True},
        {"composition_as_of": "2026-10-07"},
        {"observed_at": "2026-10-01T00:00:00"},
        {"source_filename": "../supplied.xlsx"},
    ],
)
def test_manifest_rejects_inconsistent_or_invented_metadata(change):
    with pytest.raises(ValidationError):
        CandidateManifest.model_validate(manifest() | change)


def test_manifest_rejects_duplicate_or_inconsistent_rows():
    data = manifest()
    data["records"].append(deepcopy(data["records"][0]))
    data["security_count"] = 2
    with pytest.raises(ValidationError):
        CandidateManifest.model_validate(data)
    data = manifest()
    data["records"][0]["bloomberg_ticker"] = "5930"
    with pytest.raises(ValidationError):
        CandidateManifest.model_validate(data)


def test_mapping_does_not_follow_an_instrument_to_another_listing():
    instrument = SimpleNamespace(
        id=uuid4(), symbol="EX", exchange="NYSE", isin=None, bloomberg_symbol=None
    )
    mapping = {"instrument": listing_identity(instrument)}
    assert mapping_matches(mapping, instrument)
    instrument.exchange = "Nasdaq"
    assert not mapping_matches(mapping, instrument)
    assert not mapping_matches(mapping, None)


@pytest.mark.parametrize(
    "change",
    [
        {"correspondence_confirmed": False},
        {"note": " " * 20},
        {"source_url": "https://example.org/identity?secret=x"},
        {"as_of": (datetime.now(UTC).date() + timedelta(days=1)).isoformat()},
    ],
)
def test_mapping_requires_explicit_sourced_correspondence(change):
    data = {
        "instrument_id": uuid4(),
        "bloomberg_identifier": "EX US Equity",
        "correspondence_confirmed": True,
        "note": "Titre et cotation décrits par la source.",
        "source_url": "https://example.org/identity",
        "as_of": datetime.now(UTC).date(),
    }
    with pytest.raises(ValidationError):
        CandidateMapping.model_validate(data | change)
