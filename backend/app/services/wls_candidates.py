"""Partial Bloomberg universe: preparation never grants trading eligibility."""

import copy
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.entity_registry import EntityRegistry
from app.models.market import MarketInstrument
from app.schemas.wls_candidates import CandidateManifest, CandidateMapping

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
        # One immutable snapshot per source hash. Replays preserve manual mappings.
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
        existing = await self.session.get(EntityRegistry, REGISTRY)
        if existing.content_hash != manifest.source_sha256:
            raise ValueError(
                "Une autre liste est déjà chargée ; conserver cet instantané séparément."
            )
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
        filtered = [r for r in rows if search.casefold() in r["bloomberg_identifier"].casefold()]
        items = []
        for row in filtered[offset : offset + limit]:
            mapping = row.get("listing_mapping")
            instrument = by_id.get(mapping["instrument"]["id"]) if mapping else None
            valid = bool(mapping and mapping_matches(mapping, instrument))
            suggestion = by_bloomberg.get(row["bloomberg_identifier"])
            items.append(
                {
                    **row,
                    "mapping_status": "declared" if valid else "conflict" if mapping else "missing",
                    "suggested_instrument": listing_identity(suggestion) if suggestion else None,
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
            "total": len(filtered),
            "offset": offset,
            "limit": limit,
            "items": items,
            "notice": "Liste WLS partielle déclarée. Date de composition inconnue. "
            "Les correspondances restent déclarées, sans certification automatique des preuves. "
            "Cette préparation ne donne pas d'éligibilité aux achats simulés. "
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
