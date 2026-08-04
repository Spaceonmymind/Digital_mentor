from dataclasses import dataclass
import os
from pathlib import Path


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://digital_mentor:change_me@db:5432/digital_mentor",
    )
    storage_path: Path = Path(os.getenv("STORAGE_PATH", "/app/storage"))
    max_upload_size_mb: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
    allowed_file_types: tuple[str, ...] = tuple(
        item.strip().lower()
        for item in os.getenv("ALLOWED_FILE_TYPES", ".pdf,.docx").split(",")
        if item.strip()
    )
    mock_analysis_enabled: bool = _bool_env("MOCK_ANALYSIS_ENABLED", True)
    demo_mode: bool = _bool_env("DEMO_MODE", True)
    frontend_mock_mode: bool = _bool_env("FRONTEND_MOCK_MODE", False)
    tts_mode: str = os.getenv("TTS_MODE", "browser")
    tts_max_text_length: int = int(os.getenv("TTS_MAX_TEXT_LENGTH", "700"))
    document_retention_hours: int = int(os.getenv("DOCUMENT_RETENTION_HOURS", "24"))
    audio_retention_minutes: int = int(os.getenv("AUDIO_RETENTION_MINUTES", "60"))
    report_retention_hours: int = int(os.getenv("REPORT_RETENTION_HOURS", "24"))
    mock_analysis_step_delay: float = float(os.getenv("MOCK_ANALYSIS_STEP_DELAY", "1.5"))
    cors_origins: tuple[str, ...] = tuple(
        item.strip()
        for item in os.getenv("CORS_ORIGINS", "*").split(",")
        if item.strip()
    )
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


settings = Settings()
