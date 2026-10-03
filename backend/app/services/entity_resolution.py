import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.resolver import VERSION, EntityResolver, parse_registry
from app.models.analysis_passage import AnalysisPassage
from app.models.company import Company
from app.models.entity_registry import EntityRegistry
from app.models.event import Event

REGISTRY_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


class EntityResolutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def sync_registry(self, user_agent: str, *, transport=None, force=False) -> bool:
        previous = await self.session.get(EntityRegistry, "sec_tickers")
        if (
            previous is not None
            and not force
            and previous.observed_at > datetime.now(UTC) - timedelta(days=1)
        ):
            return False
        async with httpx.AsyncClient(timeout=60, transport=transport) as client:
            async with client.stream("GET", REGISTRY_URL, headers={"User-Agent": user_agent}) as r:
                r.raise_for_status()
                chunks = bytearray()
                async for chunk in r.aiter_bytes():
                    chunks.extend(chunk)
                    if len(chunks) > 5_000_000:
                        raise ValueError("SEC registry exceeds 5 MB")
        records = parse_registry(json.loads(chunks))
        digest = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
        await self.session.execute(
            insert(EntityRegistry)
            .values(
                name="sec_tickers",
                source_url=REGISTRY_URL,
                observed_at=datetime.now(UTC),
                content_hash=digest,
                records=records,
            )
            .on_conflict_do_update(
                index_elements=[EntityRegistry.name],
                set_={
                    "source_url": REGISTRY_URL,
                    "observed_at": datetime.now(UTC),
                    "content_hash": digest,
                    "records": records,
                },
            )
        )
        await self.session.commit()
        return True

    async def process_pending(self, limit: int = 100) -> int:
        registry = await self.session.get(EntityRegistry, "sec_tickers")
        rows = (await self.session.execute(select(Company.cik, Company.name))).all()
        companies = [{"cik": row.cik, "name": row.name} for row in rows]
        resolver = EntityResolver(registry.records if registry else [], companies)
        # Filing names also form part of the identity reference and its cache key.
        signature = hashlib.sha256(
            json.dumps(
                {
                    "version": VERSION,
                    "registry": registry.content_hash if registry else None,
                    "companies": sorted(companies, key=lambda c: c["cik"]),
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        events = (
            (
                await self.session.execute(
                    select(Event)
                    .where(
                        Event.merged_into_event_id.is_(None),
                        Event.structured_data.is_not(None),
                        Event.structured_data["entity_resolution"][
                            "signature"
                        ].astext.is_distinct_from(signature),
                    )
                    .order_by(Event.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        processed = 0
        for event in events:
            data = dict(event.structured_data or {})
            fact = data.get("fact")
            if fact:
                passage = (
                    await self.session.execute(
                        select(AnalysisPassage).where(
                            AnalysisPassage.run_id == event.fact_analysis_run_id,
                            AnalysisPassage.passage_index == data.get("passage_index"),
                        )
                    )
                ).scalar_one_or_none()
                # The saved passage is the only authoritative context for new roles.
                text = passage.input_text if passage else (event.evidence_excerpt or "")
                entities = resolver.resolve_fact(fact, text)
            elif data.get("cik") and data.get("company_name"):
                entities = [resolver.document_subject(data["cik"], data["company_name"])]
            else:
                entities = []
            data["entity_resolution"] = {
                "version": VERSION,
                "signature": signature,
                "entities": entities,
                "resolved_at": datetime.now(UTC).isoformat(),
                "registry": {
                    "url": registry.source_url,
                    "observed_at": registry.observed_at.isoformat(),
                    "published_at": None,
                }
                if registry
                else None,
            }
            result = await self.session.execute(
                update(Event)
                .where(
                    Event.id == event.id,
                    Event.structured_data == event.structured_data,
                )
                .values(structured_data=data)
                .execution_options(synchronize_session=False)
            )
            processed += result.rowcount
        await self.session.commit()
        return processed
