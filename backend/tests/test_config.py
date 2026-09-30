import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_are_parsed() -> None:
    settings = Settings(backend_cors_origins="http://localhost,http://localhost:3000")
    assert settings.cors_origins == ["http://localhost", "http://localhost:3000"]


def test_collection_interval_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        Settings(ecb_collection_interval_minutes=0)

    with pytest.raises(ValidationError):
        Settings(fed_collection_interval_minutes=0)

    with pytest.raises(ValidationError):
        Settings(sec_collection_interval_minutes=0)

    with pytest.raises(ValidationError):
        Settings(event_extraction_interval_minutes=0)
