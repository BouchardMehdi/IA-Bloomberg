"""WLS membership comes from an explicitly supplied security-level export."""

import csv
import io
import re
from datetime import date


def parse_wls_csv(text: str, as_of: date) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"security_id", "symbol", "exchange", "asset_class"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("Colonnes requises : security_id,symbol,exchange,asset_class")
    records, identities, listings = [], set(), set()
    for row in reader:
        security_id = (row.get("security_id") or "").strip()
        symbol = (row.get("symbol") or "").strip().upper()
        exchange = (row.get("exchange") or "").strip()
        if (
            not security_id
            or len(security_id) > 100
            or not exchange
            or len(exchange) > 50
            or not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}", symbol)
        ):
            raise ValueError("Identifiant de titre, ticker ou marché invalide.")
        if (row.get("asset_class") or "").strip().lower() != "equity":
            raise ValueError("L'univers du challenge ne peut contenir que des actions (equity).")
        if security_id in identities or (symbol, exchange) in listings:
            raise ValueError("Titre ou cotation en doublon : vérifier l'export WLS.")
        identities.add(security_id)
        listings.add((symbol, exchange))
        records.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "exchange": exchange,
                "asset_class": "equity",
                "as_of": as_of.isoformat(),
            }
        )
        if len(records) > 20000:
            raise ValueError("Export WLS limité à 20 000 titres.")
    if not records:
        raise ValueError("Export WLS vide.")
    return records


def eligibility(instrument, registry) -> dict:
    if registry is None:
        return {"status": "unknown", "security_id": None, "source_url": None, "as_of": None}
    matches = [
        r
        for r in registry.records
        if r.get("symbol") == instrument.symbol
        and r.get("exchange") == instrument.exchange
        and r.get("asset_class") == "equity"
    ]
    if len(matches) != 1:
        return {
            "status": "not_verified",
            "security_id": None,
            "source_url": registry.source_url,
            "as_of": None,
        }
    row = matches[0]
    return {
        "status": "verified",
        "security_id": row["security_id"],
        "source_url": registry.source_url,
        "as_of": row["as_of"],
    }
