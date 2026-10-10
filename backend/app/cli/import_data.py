import argparse
import asyncio
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from app.db.session import async_session_factory
from app.schemas.workspace import DataBatch
from app.services.data_import import DataImportService


async def main(path):
    file = Path(path)
    if file.stat().st_size > 1_000_000:
        raise SystemExit("Fichier trop volumineux (1 Mo maximum).")
    data = DataBatch.model_validate_json(file.read_bytes())
    async with async_session_factory() as session:
        result = await DataImportService(session).ingest(data)
    import json
    print(json.dumps(jsonable_encoder(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    asyncio.run(main(parser.parse_args().file))
