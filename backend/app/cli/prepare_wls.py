import argparse
from pathlib import Path

from app.market.wls_workbook import prepare_workbook


def main():
    parser = argparse.ArgumentParser(
        description="Préparer une liste WLS XLSX fournie, sans date inventée"
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--origin", required=True, help="Provenance déclarée du fichier")
    args = parser.parse_args()
    if args.file.stat().st_size > 5_000_000:
        raise ValueError("Classeur limité à 5 Mo.")
    manifest = prepare_workbook(args.file.read_bytes(), args.file.name, args.origin)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(manifest.model_dump_json(indent=2) + "\n")
    print(f"Préparation : {manifest.security_count} identifiants, date de composition inconnue.")


if __name__ == "__main__":
    main()
