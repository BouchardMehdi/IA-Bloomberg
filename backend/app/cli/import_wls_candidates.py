"""Load a supplied, prepared WLS manifest without enabling simulated purchases."""

import argparse
import asyncio
from pathlib import Path

from app.db.session import async_session_factory
from app.schemas.wls_candidates import CandidateManifest
from app.services.wls_candidates import WlsCandidateService


async def import_candidates(path: Path):
    if path.stat().st_size > 10_000_000:
        raise ValueError("Préparation limitée à 10 Mo.")
    manifest = CandidateManifest.model_validate_json(path.read_bytes())
    async with async_session_factory() as session:
        result = await WlsCandidateService(session).load(manifest)
    print(
        f"Liste WLS partielle : {result['security_count']} titres ; nouvel import : "
        f"{result['inserted']}. Éligibilité des achats inchangée."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(import_candidates(args.file))


if __name__ == "__main__":
    main()
