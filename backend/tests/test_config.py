from app.core.config import Settings


def test_cors_origins_are_parsed() -> None:
    settings = Settings(backend_cors_origins="http://localhost,http://localhost:3000")
    assert settings.cors_origins == ["http://localhost", "http://localhost:3000"]
