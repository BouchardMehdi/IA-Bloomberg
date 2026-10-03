import argparse
import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import HttpUrl, TypeAdapter
from sqlalchemy.dialects.postgresql import insert

from app.db.session import async_session_factory
from app.market.wls import parse_wls_csv
from app.models.entity_registry import EntityRegistry


async def import_export(path: Path, as_of: date, source_url: str):
    if as_of > datetime.now(UTC).date():
        raise ValueError("La date de l'univers ne peut pas être future.")
    if path.stat().st_size > 5_000_000:
        raise ValueError("Export limité à 5 Mo.")
    records = parse_wls_csv(path.read_text(encoding="utf-8-sig"), as_of)
    url = str(TypeAdapter(HttpUrl).validate_python(source_url))
    digest = hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    async with async_session_factory() as session:
        values = {
            "source_url": url,
            "observed_at": datetime.now(UTC),
            "content_hash": digest,
            "records": records,
        }
        await session.execute(
            insert(EntityRegistry)
            .values(name="wls_universe", **values)
            .on_conflict_do_update(index_elements=[EntityRegistry.name], set_=values)
        )
        await session.commit()
    print(f"Univers WLS importé : {len(records)} titres, date {as_of}.")


def main():
    parser = argparse.ArgumentParser(description="Import an authorized WLS security export")
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--source-url", required=True, help="URL officielle, même avec accès privé")
    args = parser.parse_args()
    asyncio.run(import_export(args.file, args.as_of, args.source_url))


if __name__ == "__main__":
    main()
