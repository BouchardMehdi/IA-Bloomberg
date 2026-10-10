"""Read a supplied one-column Bloomberg XLSX into a declared, undated manifest."""

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from app.schemas.wls_candidates import CandidateManifest

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def prepare_workbook(raw: bytes, filename: str, origin: str) -> CandidateManifest:
    if len(raw) > 5_000_000:
        raise ValueError("Classeur limité à 5 Mo.")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if (
                len(archive.infolist()) > 1000
                or sum(i.file_size for i in archive.infolist()) > 20_000_000
            ):
                raise ValueError("Classeur décompressé trop volumineux.")
            if len({i.filename for i in archive.infolist()}) != len(archive.infolist()):
                raise ValueError("Entrées de classeur en doublon.")
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            sheets = workbook.findall("m:sheets/m:sheet", NS)
            if len(sheets) != 1:
                raise ValueError("Un seul onglet est attendu pour cet import.")
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = [
                r.get("Target")
                for r in relationships
                if r.get("Id") == sheets[0].get(f"{{{REL}}}id")
                and r.get("TargetMode") != "External"
            ]
            if len(targets) != 1 or targets[0] is None:
                raise ValueError("Onglet introuvable.")
            target = targets[0].lstrip("/")
            target = target if target.startswith("xl/") else "xl/" + target
            if ".." in PurePosixPath(target).parts or not target.startswith("xl/worksheets/"):
                raise ValueError("Chemin d'onglet invalide.")
            strings = []
            if "xl/sharedStrings.xml" in archive.namelist():
                strings = [
                    "".join(t.text or "" for t in si.findall(".//m:t", NS))
                    for si in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall(
                        "m:si", NS
                    )
                ]
            rows = []
            for row in ET.fromstring(archive.read(target)).findall("m:sheetData/m:row", NS):
                cells = [
                    c
                    for c in row.findall("m:c", NS)
                    if c.find("m:v", NS) is not None
                    or c.find("m:is", NS) is not None
                    or c.find("m:f", NS) is not None
                ]
                if not cells:
                    continue
                cell = cells[0]
                if len(cells) != 1 or cell.find("m:f", NS) is not None:
                    raise ValueError("Une colonne de texte sans formule est requise.")
                if cell.get("t") == "s":
                    index = int(cell.find("m:v", NS).text)
                    if not 0 <= index < len(strings):
                        raise ValueError("Référence textuelle invalide.")
                    value = strings[index]
                elif cell.get("t") == "inlineStr":
                    value = "".join(t.text or "" for t in cell.findall(".//m:t", NS))
                else:
                    raise ValueError(
                        "Identifiant textuel requis ; aucun zéro initial ne sera deviné."
                    )
                parts = value.split()
                if len(parts) != 3 or parts[-1] != "Equity":
                    raise ValueError("Identifiant Bloomberg attendu : ticker code Equity.")
                rows.append(
                    {
                        "bloomberg_identifier": value,
                        "bloomberg_ticker": parts[0],
                        "bloomberg_market_code": parts[1],
                        "bloomberg_sector": parts[2],
                        "source_cell": cell.get("r"),
                        "listing_mapping": None,
                    }
                )
                if len(rows) > 20000:
                    raise ValueError("Liste limitée à 20 000 titres.")
            return CandidateManifest.model_validate(
                {
                    "schema_version": 1,
                    "source_filename": filename,
                    "source_sha256": hashlib.sha256(raw).hexdigest(),
                    "source_sheet": sheets[0].get("name"),
                    "observed_at": datetime.now(UTC),
                    "origin": origin,
                    "composition_as_of": None,
                    "source_url": None,
                    "partial": True,
                    "security_count": len(rows),
                    "eligibility_imported": False,
                    "records": rows,
                }
            )
    except (zipfile.BadZipFile, KeyError, ET.ParseError, IndexError, TypeError) as exc:
        raise ValueError("Structure XLSX invalide ou incomplète.") from exc
