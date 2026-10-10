"""Declared partial WLS exports and explicit listing correspondences."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.international import SourcedObservation


class CandidateRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bloomberg_identifier: str = Field(min_length=1, max_length=100)
    bloomberg_ticker: str = Field(min_length=1, max_length=32)
    bloomberg_market_code: str = Field(pattern=r"^[A-Z0-9]{2,4}$")
    bloomberg_sector: Literal["Equity"]
    source_cell: str = Field(pattern=r"^A[1-9][0-9]*$")
    listing_mapping: None = None

    @model_validator(mode="after")
    def consistent_identifier(self):
        expected = f"{self.bloomberg_ticker} {self.bloomberg_market_code} Equity"
        if self.bloomberg_identifier != expected:
            raise ValueError("Identifiant Bloomberg incohérent.")
        return self


class CandidateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    source_filename: str = Field(min_length=1, max_length=255, pattern=r"^[^/\\]+$")
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_sheet: str = Field(min_length=1, max_length=100)
    observed_at: datetime
    origin: str = Field(min_length=10, max_length=1000)
    composition_as_of: None = None
    source_url: None = None
    partial: Literal[True]
    security_count: int = Field(ge=1, le=20000)
    eligibility_imported: Literal[False]
    records: list[CandidateRow] = Field(min_length=1, max_length=20000)

    @model_validator(mode="after")
    def unique_rows(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("La date de lecture doit avoir un fuseau horaire.")
        if self.observed_at > datetime.now(UTC):
            raise ValueError("La date de lecture ne peut pas être future.")
        identifiers = {row.bloomberg_identifier for row in self.records}
        cells = {row.source_cell for row in self.records}
        if len(identifiers) != len(self.records) or len(cells) != len(self.records):
            raise ValueError("Identifiant ou cellule source en doublon.")
        if self.security_count != len(self.records):
            raise ValueError("Le compteur ne correspond pas aux lignes fournies.")
        return self


class CandidateMapping(SourcedObservation):
    instrument_id: UUID
    bloomberg_identifier: str = Field(min_length=1, max_length=100)
    correspondence_confirmed: Literal[True]
    note: str = Field(min_length=20, max_length=1500)

    @model_validator(mode="after")
    def no_empty_note(self):
        if len(self.note.strip()) < 20:
            raise ValueError("Documenter la correspondance entre le titre et sa cotation.")
        return self


class CandidateMappingBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[CandidateMapping] = Field(min_length=1, max_length=100)
