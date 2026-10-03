"""Conservative identity matching; no fuzzy matching or LLM calls."""

import re
import unicodedata
from collections import defaultdict

VERSION = "entities-v1"
# Deliberately limited to currencies supported by this first release.
CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "CNY"}


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"\w+", value))


def contains_name(text: str, name: str, *, case_sensitive: bool = False) -> bool:
    # Word boundaries prevent matching a short ticker inside an ordinary word.
    return bool(
        re.search(
            r"(?<!\w)" + re.escape(name) + r"(?!\w)",
            text,
            0 if case_sensitive else re.I,
        )
    )


def parse_registry(payload: dict) -> list[dict]:
    fields = payload.get("fields")
    data = payload.get("data")
    if not isinstance(fields, list) or not isinstance(data, list) or not data:
        raise ValueError("SEC registry must contain nonempty fields and data")
    if not {"cik", "name", "ticker", "exchange"}.issubset(fields):
        raise ValueError("Missing SEC registry fields")
    records = []
    for row in data:
        if not isinstance(row, list) or len(row) != len(fields):
            raise ValueError("Invalid SEC registry row")
        item = dict(zip(fields, row, strict=True))
        cik = str(item["cik"])
        if not cik.isascii() or not cik.isdigit() or not 1 <= len(cik) <= 10:
            raise ValueError("Invalid SEC CIK")
        if not isinstance(item["name"], str) or not item["name"].strip():
            raise ValueError("Invalid SEC company name")
        for key in ("ticker", "exchange"):
            if item[key] is not None and (not isinstance(item[key], str) or len(item[key]) > 100):
                raise ValueError(f"Invalid SEC {key}")
        records.append(
            {
                "cik": cik.zfill(10),
                "name": item["name"].strip(),
                "ticker": item["ticker"],
                "exchange": item["exchange"],
            }
        )
    return records


class EntityResolver:
    def __init__(self, records: list[dict], companies: list[dict] = ()) -> None:
        self.by_cik: dict[str, dict] = {}
        self.by_name: dict[str, set[str]] = defaultdict(set)
        self.by_ticker: dict[str, list[dict]] = defaultdict(list)
        for row in records:
            company = self.by_cik.setdefault(
                row["cik"], {"cik": row["cik"], "name": row["name"], "listings": []}
            )
            self.by_name[normalize_name(row["name"])].add(row["cik"])
            if row["ticker"]:
                listing = {"ticker": row["ticker"], "exchange": row["exchange"]}
                if listing not in company["listings"]:
                    company["listings"].append(listing)
                candidate = {"cik": row["cik"], "name": row["name"], **listing}
                if candidate not in self.by_ticker[row["ticker"]]:
                    self.by_ticker[row["ticker"]].append(candidate)
        for row in companies:
            self.by_cik.setdefault(
                row["cik"], {"cik": row["cik"], "name": row["name"], "listings": []}
            )
            self.by_name[normalize_name(row["name"])].add(row["cik"])

    def resolve(self, name: str, kind: str, role: str, quote: str, text: str) -> dict:
        result = {
            "name": name,
            "kind": kind,
            "role": role,
            "quote": quote,
            "status": "unresolved",
            "method": None,
            "candidates": [],
        }
        normalized_text = " ".join(text.split()).casefold()
        if (
            not quote
            or " ".join(quote.split()).casefold() not in normalized_text
            or not contains_name(quote, name, case_sensitive=kind in {"equity", "currency"})
        ):
            return {**result, "status": "unverified", "role": "mention"}
        if kind == "company":
            ciks = self.by_name.get(normalize_name(name), set())
            candidates = [self.by_cik[cik] for cik in sorted(ciks)]
            return self._match(result, candidates, "exact_name")
        if kind == "currency":
            if name in CURRENCIES:
                return {
                    **result,
                    "status": "resolved",
                    "method": "explicit_currency_code",
                    "candidates": [{"code": name}],
                }
            return result
        if kind == "equity":
            # SEC only certifies ticker/issuer/venue; instrument class is not verified.
            return self._match(result, self.by_ticker.get(name, []), "exact_ticker")
        # No authoritative bond identifier registry yet: preserve the mention.
        return result

    @staticmethod
    def _match(result: dict, candidates: list[dict], method: str) -> dict:
        return {
            **result,
            "candidates": candidates,
            "method": method if candidates else None,
            "status": "resolved"
            if len(candidates) == 1
            else "ambiguous"
            if candidates
            else "unresolved",
        }

    def document_subject(self, cik: str, name: str) -> dict:
        candidate = self.by_cik.get(cik, {"cik": cik, "name": name, "listings": []})
        return {
            "name": name,
            "kind": "company",
            "role": "source_subject",
            "quote": None,
            "status": "resolved",
            "method": "filing_cik",
            "candidates": [candidate],
        }

    def resolve_fact(self, fact: dict, text: str) -> list[dict]:
        mentions = list(fact.get("entity_mentions", []))
        explicit = {normalize_name(m["name"]) for m in mentions}
        # Older analyses are reused as mentions, without inventing business roles.
        for kind, names in (
            ("company", fact.get("companies", [])),
            ("equity", fact.get("assets", [])),
        ):
            for name in names:
                if normalize_name(name) in explicit:
                    continue
                quote = next(
                    (
                        e["quote"]
                        for e in fact.get("evidence", [])
                        if contains_name(e["quote"], name)
                    ),
                    "",
                )
                mentions.append(
                    {
                        "name": name,
                        "kind": "currency" if name in CURRENCIES else kind,
                        "role": "mention",
                        "quote": quote,
                    }
                )
        for amount in fact.get("amounts", []):
            currency = amount.get("currency")
            if currency and not any(m["name"] == currency for m in mentions):
                quote = next(
                    (
                        e["quote"]
                        for e in fact.get("evidence", [])
                        if contains_name(e["quote"], currency)
                    ),
                    "",
                )
                mentions.append(
                    {"name": currency, "kind": "currency", "role": "mention", "quote": quote}
                )
        return [self.resolve(m["name"], m["kind"], m["role"], m["quote"], text) for m in mentions]
