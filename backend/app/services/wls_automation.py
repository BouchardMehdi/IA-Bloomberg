"""Resumable identity enrichment; strict separation from dated WLS membership."""

import copy
import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.market.openfigi import (
    DOC_URL,
    MIC_EXCHANGE_CODES,
    URL,
    US_MICS,
    FigiError,
    OpenFigiClient,
)
from app.models.entity_registry import EntityRegistry
from app.models.market import MarketInstrument
from app.models.wls_identity import WlsIdentityObservation

STATE = "wls_openfigi_state"
REGISTRY = "wls_candidates"
MAX_AGE = timedelta(days=7)
MIC_SOURCE = "https://www.iso20022.org/market-identifier-codes"


def recent(observation, now):
    return observation is not None and timedelta(0) <= now - observation.observed_at <= MAX_AGE


def identity_job(row):
    return {
        "idType": "TICKER",
        "idValue": row["bloomberg_ticker"],
        "exchCode": row["bloomberg_market_code"],
        "marketSecDes": "Equity",
        "includeUnlistedEquities": False,
    }


def single_common(observation):
    if observation is None or observation.status != "resolved" or not observation.data:
        return None
    records = observation.data.get("records", [])
    if len(records) != 1:
        return None
    row = records[0]
    if (
        row.get("securityType") != "Common Stock"
        or row.get("securityType2") != "Common Stock"
        or row.get("marketSector") != "Equity"
    ):
        return None
    return row


def candidate_for(instrument, rows):
    explicit = instrument.bloomberg_symbol
    if explicit:
        matches = [r for r in rows if r["bloomberg_identifier"] == explicit]
    elif instrument.exchange in US_MICS and instrument.currency == "USD":
        # This selects requests to investigate; it does not assert a correspondence.
        matches = [
            r
            for r in rows
            if r["bloomberg_market_code"] == "US" and r["bloomberg_ticker"] == instrument.symbol
        ]
    else:
        matches = []
    return matches[0] if len(matches) == 1 else None


def venue_jobs(instrument, row, observation):
    security = single_common(observation)
    if (
        security is None
        or security.get("ticker") != row["bloomberg_ticker"]
        or security.get("exchCode") != row["bloomberg_market_code"]
        or not security.get("compositeFIGI")
        or not security.get("shareClassFIGI")
    ):
        return []
    mics = US_MICS.get(instrument.exchange, (instrument.exchange,))
    if any(len(mic) != 4 for mic in mics):
        return []
    return [
        (
            f"venue:{instrument.id}:{mic}",
            {
                "idType": "COMPOSITE_ID_BB_GLOBAL",
                "idValue": security["compositeFIGI"],
                "micCode": mic,
                "currency": instrument.currency,
                "marketSecDes": "Equity",
                "includeUnlistedEquities": False,
            },
        )
        for mic in mics
    ]


def assess_listing(instrument, manifest, observations, now=None):
    now = now or datetime.now(UTC)
    blocked = {"status": "unresolved", "evidence": None}
    row = candidate_for(instrument, manifest["records"])
    if row is None:
        return blocked
    identifier = row["bloomberg_identifier"]
    identity = observations.get((identifier, "identity"))
    if not recent(identity, now) or identity.query != identity_job(row):
        return blocked
    security = single_common(identity)
    jobs = venue_jobs(instrument, row, identity)
    if not jobs:
        return blocked
    matches, proof = [], [identity]
    for key, query in jobs:
        observation = observations.get((identifier, key))
        if (
            not recent(observation, now)
            or observation.query != query
            or observation.status not in {"resolved", "not_found"}
        ):
            return blocked
        proof.append(observation)
        record = single_common(observation)
        if record:
            expected_code = MIC_EXCHANGE_CODES.get(query["micCode"])
            if expected_code and record.get("exchCode") != expected_code:
                return blocked
            if (
                record.get("compositeFIGI") != security["compositeFIGI"]
                or record.get("shareClassFIGI") != security["shareClassFIGI"]
                or record.get("ticker") != instrument.symbol
            ):
                return blocked
            matches.append(record)
        elif observation.status != "not_found":
            return blocked
    if len({r["figi"] for r in matches}) != 1:
        return blocked
    return {
        "status": "matched",
        "evidence": {
            "bloomberg_identifier": identifier,
            "source_hash": manifest["source_sha256"],
            "composition_as_of": manifest["composition_as_of"],
            "partial": True,
            "listing_figi": matches[0]["figi"],
            "composite_figi": security["compositeFIGI"],
            "share_class_figi": security["shareClassFIGI"],
            "source_url": URL,
            "mic_source_url": MIC_SOURCE,
            "instrument_id": str(instrument.id),
            "symbol": instrument.symbol,
            "exchange": instrument.exchange,
            "currency": instrument.currency,
            "observations": [str(o.id) for o in proof],
            "identity_observed_at": min(o.observed_at for o in proof).isoformat(),
            "notice": "Correspondance technique actuelle OpenFIGI ; appartenance WLS déclarée "
            "dans un fichier partiel sans date de composition.",
        },
    }


class WlsAutomationService:
    def __init__(self, session):
        self.session = session

    async def latest(self, source_hash):
        rows = (
            (
                await self.session.execute(
                    select(WlsIdentityObservation)
                    .where(WlsIdentityObservation.source_hash == source_hash)
                    .distinct(
                        WlsIdentityObservation.bloomberg_identifier,
                        WlsIdentityObservation.query_key,
                    )
                    .order_by(
                        WlsIdentityObservation.bloomberg_identifier,
                        WlsIdentityObservation.query_key,
                        WlsIdentityObservation.observed_at.desc(),
                        WlsIdentityObservation.id.desc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        return {(r.bloomberg_identifier, r.query_key): r for r in rows}

    async def assessments(self, instruments):
        registry = await self.session.get(EntityRegistry, REGISTRY)
        if registry is None:
            return {str(i.id): {"status": "unresolved", "evidence": None} for i in instruments}
        observations = await self.latest(registry.content_hash)
        return {
            str(i.id): assess_listing(i, registry.records[0], observations) for i in instruments
        }

    async def collect(self, client=None):
        now = datetime.now(UTC)
        registry = await self.session.get(EntityRegistry, REGISTRY)
        if registry is None:
            return {"status": "no_list", "attempted": 0}
        source_hash = registry.content_hash
        manifest = copy.deepcopy(registry.records[0])
        await self.session.execute(
            insert(EntityRegistry)
            .values(
                name=STATE,
                source_url=DOC_URL,
                content_hash=hashlib.sha256(b"openfigi").hexdigest(),
                observed_at=now,
                records=[{"next_attempt_at": now.isoformat()}],
            )
            .on_conflict_do_nothing(index_elements=[EntityRegistry.name])
        )
        state = (
            await self.session.execute(
                select(EntityRegistry).where(EntityRegistry.name == STATE).with_for_update()
            )
        ).scalar_one()
        if datetime.fromisoformat(state.records[0]["next_attempt_at"]) > now:
            await self.session.rollback()
            return {"status": "waiting", "attempted": 0}
        observations = await self.latest(source_hash)
        instruments = (
            (
                await self.session.execute(
                    select(MarketInstrument).order_by(MarketInstrument.created_at)
                )
            )
            .scalars()
            .all()
        )
        requests, seen = [], set()

        def add(row, key, query):
            pair = (row["bloomberg_identifier"], key)
            previous = observations.get(pair)
            if previous and previous.query == query:
                delay = (
                    timedelta(minutes=5)
                    if previous.status in {"running", "failed"}
                    else timedelta(days=1)
                    if previous.status == "provider_error"
                    else MAX_AGE
                )
                if timedelta(0) <= now - previous.observed_at < delay:
                    return
            if pair not in seen and len(requests) < 5:
                seen.add(pair)
                requests.append((row, key, query))

        # Watched securities first; only then enrich the rest of the supplied file.
        for instrument in instruments:
            row = candidate_for(instrument, manifest["records"])
            if row:
                add(row, "identity", identity_job(row))
                identity = observations.get((row["bloomberg_identifier"], "identity"))
                if recent(identity, now):
                    for key, query in venue_jobs(instrument, row, identity):
                        add(row, key, query)
        for row in sorted(manifest["records"], key=lambda r: r["bloomberg_market_code"] != "US"):
            add(row, "identity", identity_job(row))
            if len(requests) >= 5:
                break
        if not requests:
            await self.session.rollback()
            watched = await self.prepare_watchlist()
            return {"status": "cached", "attempted": 0, "auto_watched": watched}
        token = str(uuid.uuid4())
        state.records = [
            {
                "next_attempt_at": (now + timedelta(minutes=5)).isoformat(),
                "token": token,
                "status": "running",
            }
        ]
        attempts = [
            WlsIdentityObservation(
                source_hash=source_hash,
                bloomberg_identifier=row["bloomberg_identifier"],
                query_key=key,
                query=query,
                observed_at=now,
                status="running",
            )
            for row, key, query in requests
        ]
        self.session.add_all(attempts)
        await self.session.commit()  # Persist reservation before contacting the provider.
        error, results, delay = None, None, 5
        try:
            results = await (client or OpenFigiClient()).fetch([q for _, _, q in requests])
        except FigiError as exc:
            error, delay = exc.code, exc.retry_seconds
        completed = datetime.now(UTC)
        for index, observation in enumerate(attempts):
            observation.status = "failed" if error else results[index]["status"]
            observation.data = {"error_code": error} if error else results[index]
        state = (
            await self.session.execute(
                select(EntityRegistry)
                .where(EntityRegistry.name == STATE)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        if state.records[0].get("token") == token:
            state.records = [
                {
                    "next_attempt_at": (completed + timedelta(seconds=delay)).isoformat(),
                    "status": "failed" if error else "success",
                    "error_code": error,
                    "completed_at": completed.isoformat(),
                    "attempted": len(attempts),
                }
            ]
            state.observed_at = completed
        await self.session.commit()
        watched = await self.prepare_watchlist()
        return {
            "status": "failed" if error else "success",
            "attempted": len(attempts),
            "error_code": error,
            "auto_watched": watched,
        }

    async def prepare_watchlist(self):
        """Bounded research watchlist, never a recommendation or WLS certification."""
        registry = await self.session.get(EntityRegistry, REGISTRY)
        sec = await self.session.get(EntityRegistry, "sec_tickers")
        now = datetime.now(UTC)
        if not registry or not sec or not timedelta(0) <= now - sec.observed_at <= MAX_AGE:
            return 0
        # Serialize automatic watchlist additions across CLI, API and scheduler.
        registry = (
            await self.session.execute(
                select(EntityRegistry)
                .where(EntityRegistry.name == REGISTRY)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        existing = (await self.session.execute(select(MarketInstrument))).scalars().all()
        remaining = max(0, get_settings().wls_auto_watch_limit - len(existing))
        if not remaining:
            await self.session.rollback()
            return 0
        observations = await self.latest(registry.content_hash)
        known = {(i.symbol, i.exchange) for i in existing}
        added = 0
        for row in registry.records[0]["records"]:
            if row["bloomberg_market_code"] != "US":
                continue
            observation = observations.get((row["bloomberg_identifier"], "identity"))
            record = single_common(observation)
            if (
                not recent(observation, now)
                or record is None
                or observation.query != identity_job(row)
                or record.get("ticker") != row["bloomberg_ticker"]
                or record.get("exchCode") != "US"
            ):
                continue
            matches = {
                (r["cik"], r["exchange"]): r
                for r in sec.records
                if r["ticker"] == row["bloomberg_ticker"] and r["exchange"] in US_MICS
            }
            if len(matches) != 1:
                continue
            identity = next(iter(matches.values()))
            if (row["bloomberg_ticker"], identity["exchange"]) in known:
                continue
            result = await self.session.execute(
                insert(MarketInstrument)
                .values(
                    symbol=row["bloomberg_ticker"],
                    exchange=identity["exchange"],
                    cik=identity["cik"],
                    name=identity["name"],
                    currency="USD",
                    registry_url=sec.source_url,
                    registry_observed_at=sec.observed_at,
                )
                .on_conflict_do_nothing(constraint="uq_market_symbol_exchange")
                .returning(MarketInstrument.id)
            )
            added += result.scalar_one_or_none() is not None
            if added >= remaining:
                break
        await self.session.commit()
        return added
