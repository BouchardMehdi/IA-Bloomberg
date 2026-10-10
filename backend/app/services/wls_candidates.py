"""Partial Bloomberg universe: preparation never grants trading eligibility."""

import copy
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.entity_registry import EntityRegistry
from app.models.market import MarketInstrument
from app.schemas.wls_candidates import CandidateManifest, CandidateMapping
from app.services.wls_automation import WlsAutomationService, assess_listing

REGISTRY = "wls_candidates"


def listing_identity(instrument):
    return {
        "id": str(instrument.id),
        "symbol": instrument.symbol,
        "exchange": instrument.exchange,
        "isin": instrument.isin,
        "bloomberg_symbol": instrument.bloomberg_symbol,
    }


def mapping_matches(mapping, instrument):
    return instrument is not None and mapping["instrument"] == listing_identity(instrument)


class WlsCandidateService:
    def __init__(self, session):
        self.session = session

    async def load(self, manifest: CandidateManifest):
        # Replays preserve manual mappings; replacements archive the complete old snapshot.
        values = manifest.model_dump(mode="json")
        statement = (
            insert(EntityRegistry)
            .values(
                name=REGISTRY,
                source_url=f"urn:sha256:{manifest.source_sha256}",
                observed_at=datetime.now(UTC),
                content_hash=manifest.source_sha256,
                records=[values],
            )
            .on_conflict_do_nothing(index_elements=[EntityRegistry.name])
            .returning(EntityRegistry.name)
        )
        inserted = (await self.session.execute(statement)).scalar_one_or_none() is not None
        existing = (
            await self.session.execute(
                select(EntityRegistry)
                .where(EntityRegistry.name == REGISTRY)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        if existing.content_hash != manifest.source_sha256:
            archive_name = "wls_archive_" + existing.content_hash[:32]
            await self.session.execute(
                insert(EntityRegistry)
                .values(
                    name=archive_name,
                    source_url=existing.source_url,
                    observed_at=existing.observed_at,
                    content_hash=existing.content_hash,
                    records=copy.deepcopy(existing.records),
                )
                .on_conflict_do_update(
                    index_elements=[EntityRegistry.name],
                    set_={
                        "source_url": existing.source_url,
                        "observed_at": existing.observed_at,
                        "records": copy.deepcopy(existing.records),
                    },
                    where=EntityRegistry.content_hash == existing.content_hash,
                )
            )
            archived = await self.session.get(EntityRegistry, archive_name)
            if archived.content_hash != existing.content_hash:
                raise ValueError("Conflit d'identifiant d'archive : import interrompu.")
            # Reactivating an already seen file restores its declarations.
            restored = await self.session.get(
                EntityRegistry, "wls_archive_" + manifest.source_sha256[:32]
            )
            if restored is not None and restored.content_hash != manifest.source_sha256:
                raise ValueError("Conflit d'identifiant d'archive : import interrompu.")
            existing.records = copy.deepcopy(restored.records) if restored else [values]
            existing.content_hash = manifest.source_sha256
            existing.source_url = f"urn:sha256:{manifest.source_sha256}"
            existing.observed_at = datetime.now(UTC)
            inserted = True
        await self.session.commit()
        return {"inserted": inserted, "security_count": len(existing.records[0]["records"])}

    async def detail(self, search="", offset=0, limit=50):
        registry = await self.session.get(EntityRegistry, REGISTRY)
        if registry is None:
            return {"loaded": False, "items": [], "total": 0}
        manifest = registry.records[0]
        instruments = (await self.session.execute(select(MarketInstrument))).scalars().all()
        by_id = {str(i.id): i for i in instruments}
        by_bloomberg = {i.bloomberg_symbol: i for i in instruments if i.bloomberg_symbol}
        rows = manifest["records"]
        observations = await WlsAutomationService(self.session).latest(registry.content_hash)
        automatic = {str(i.id): assess_listing(i, manifest, observations) for i in instruments}
        filtered = [r for r in rows if search.casefold() in r["bloomberg_identifier"].casefold()]
        items = []
        for row in filtered[offset : offset + limit]:
            mapping = row.get("listing_mapping")
            instrument = by_id.get(mapping["instrument"]["id"]) if mapping else None
            valid = bool(mapping and mapping_matches(mapping, instrument))
            suggestion = by_bloomberg.get(row["bloomberg_identifier"])
            identity = observations.get((row["bloomberg_identifier"], "identity"))
            items.append(
                {
                    **row,
                    "mapping_status": "declared" if valid else "conflict" if mapping else "missing",
                    "suggested_instrument": listing_identity(suggestion) if suggestion else None,
                    "identity_observation": {
                        "status": identity.status,
                        "observed_at": identity.observed_at,
                        "source_url": "https://api.openfigi.com/v3/mapping",
                        "query": identity.query,
                        "data": identity.data,
                    }
                    if identity
                    else None,
                    "automatic_mappings": [
                        a["evidence"]
                        for a in automatic.values()
                        if a["status"] == "matched"
                        and a["evidence"]["bloomberg_identifier"] == row["bloomberg_identifier"]
                    ],
                }
            )
        mapped_count = sum(
            bool(
                r.get("listing_mapping")
                and mapping_matches(
                    r["listing_mapping"], by_id.get(r["listing_mapping"]["instrument"]["id"])
                )
            )
            for r in rows
        )
        archives = (
            (
                await self.session.execute(
                    select(EntityRegistry)
                    .where(EntityRegistry.name.startswith("wls_archive_"))
                    .order_by(EntityRegistry.observed_at.desc())
                    .limit(11)
                )
            )
            .scalars()
            .all()
        )
        identity_statuses = {}
        for (_, key), observation in observations.items():
            if key == "identity":
                identity_statuses[observation.status] = (
                    identity_statuses.get(observation.status, 0) + 1
                )
        return {
            "loaded": True,
            "source_filename": manifest["source_filename"],
            "source_sha256": registry.content_hash,
            "source_sheet": manifest["source_sheet"],
            "observed_at": manifest["observed_at"],
            "origin": manifest["origin"],
            "composition_as_of": manifest["composition_as_of"],
            "partial": True,
            "security_count": len(rows),
            "mapped_count": mapped_count,
            "automatic_mapped_count": sum(a["status"] == "matched" for a in automatic.values()),
            "identity_statuses": identity_statuses,
            "archive_history": [
                {
                    "source_hash": a.content_hash,
                    "source_filename": a.records[0]["source_filename"],
                    "observed_at": a.observed_at,
                    "security_count": len(a.records[0]["records"]),
                }
                for a in archives[:10]
            ],
            "archive_history_limited": len(archives) > 10,
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "items": items,
            "notice": "Liste WLS partielle déclarée. Date de composition inconnue. "
            "Les correspondances restent déclarées, sans certification automatique des preuves. "
            "Le mode strict exige un export daté. Le mode provisoire permet une simulation "
            "sur la liste déclarée après résolution de la cotation et du type d'action. "
            "Un titre absent n'est pas nécessairement exclu du WLS.",
        }

    async def map_listing(self, request: CandidateMapping):
        registry = (
            await self.session.execute(
                select(EntityRegistry).where(EntityRegistry.name == REGISTRY).with_for_update()
            )
        ).scalar_one_or_none()
        if registry is None:
            raise LookupError("Liste partielle non chargée.")
        # Replace the JSON value explicitly so SQLAlchemy persists nested edits.
        manifest = copy.deepcopy(registry.records[0])
        row = next(
            (
                r
                for r in manifest["records"]
                if r["bloomberg_identifier"] == request.bloomberg_identifier
            ),
            None,
        )
        instrument = await self.session.get(MarketInstrument, request.instrument_id)
        if row is None or instrument is None:
            raise LookupError("Identifiant Bloomberg ou titre suivi introuvable.")
        if instrument.bloomberg_symbol not in {None, request.bloomberg_identifier}:
            raise ValueError("Ce titre possède déjà un autre identifiant Bloomberg.")
        owner = (
            await self.session.execute(
                select(MarketInstrument.id).where(
                    MarketInstrument.bloomberg_symbol == request.bloomberg_identifier
                )
            )
        ).scalar_one_or_none()
        if owner is not None and owner != instrument.id:
            raise ValueError("Cet identifiant Bloomberg est déclaré sur une autre cotation.")
        data = request.model_dump(mode="json") | {"instrument": listing_identity(instrument)}
        existing = row.get("listing_mapping")
        if existing:
            if {k: v for k, v in existing.items() if k != "observed_at"} != data:
                raise ValueError("Correspondance déjà déclarée ; aucun remplacement automatique.")
            return {"inserted": False}
        for other in manifest["records"]:
            mapping = other.get("listing_mapping")
            if mapping and mapping["instrument_id"] == str(request.instrument_id):
                raise ValueError("Cette cotation est déjà rapprochée d'un autre identifiant.")
        row["listing_mapping"] = data | {"observed_at": datetime.now(UTC).isoformat()}
        registry.records = [manifest]
        await self.session.commit()
        return {"inserted": True}

    async def map_batch(self, request):
        results = []
        for item in request.items:
            try:
                result = await self.map_listing(item)
                results.append(
                    {"bloomberg_identifier": item.bloomberg_identifier, "status": "saved", **result}
                )
            except (ValueError, LookupError) as exc:
                await self.session.rollback()
                results.append(
                    {
                        "bloomberg_identifier": item.bloomberg_identifier,
                        "status": "rejected",
                        "reason": str(exc),
                    }
                )
        return {"items": results, "saved": sum(r["status"] == "saved" for r in results)}
