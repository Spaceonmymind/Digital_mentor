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
    presentation_mode: bool = _bool_env("PRESENTATION_MODE", False)
    frontend_mock_mode: bool = _bool_env("FRONTEND_MOCK_MODE", False)
    tts_mode: str = os.getenv("TTS_MODE", "remote")
    tts_max_text_length: int = int(os.getenv("TTS_MAX_TEXT_LENGTH", "700"))
    tts_dialog_max_text_length: int = int(os.getenv("TTS_DIALOG_MAX_TEXT_LENGTH", "3000"))
    tts_model: str = os.getenv("TTS_MODEL", "openai/gpt-4o-mini-tts")
    tts_voice: str = os.getenv("TTS_VOICE", "verse")
    tts_speed: float = float(os.getenv("TTS_SPEED", "1.3"))
    tts_timeout_seconds: float = float(os.getenv("TTS_TIMEOUT_SECONDS", "20"))
    tts_max_retries: int = int(os.getenv("TTS_MAX_RETRIES", "2"))
    document_retention_hours: int = int(os.getenv("DOCUMENT_RETENTION_HOURS", "24"))
    audio_retention_minutes: int = int(os.getenv("AUDIO_RETENTION_MINUTES", "60"))
    report_retention_hours: int = int(os.getenv("REPORT_RETENTION_HOURS", "24"))
    mock_analysis_step_delay: float = float(os.getenv("MOCK_ANALYSIS_STEP_DELAY", "1.5"))
    polza_api_key: str | None = os.getenv("POLZA_API_KEY")
    polza_base_url: str = os.getenv("POLZA_BASE_URL", "https://polza.ai/api/v1")
    llm_request_timeout_seconds: float = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "60"))
    analysis_engine: str = os.getenv("ANALYSIS_ENGINE", "mock")
    ai_document_max_chars: int = int(os.getenv("AI_DOCUMENT_MAX_CHARS", "60000"))
    ai_document_excerpt_strategy: str = os.getenv("AI_DOCUMENT_EXCERPT_STRATEGY", "head_tail")
    ai_worker_temperature: float = float(os.getenv("AI_WORKER_TEMPERATURE", "0"))
    ai_worker_max_completion_tokens: int = int(os.getenv("AI_WORKER_MAX_COMPLETION_TOKENS", "2000"))
    ai_worker_seed: int | None = int(os.getenv("AI_WORKER_SEED", "42")) if os.getenv("AI_WORKER_SEED", "42") else None
    ai_execution_stop_on_error: bool = _bool_env("AI_EXECUTION_STOP_ON_ERROR", True)
    ai_demo_auto_approve_gates: bool = _bool_env("AI_DEMO_AUTO_APPROVE_GATES", True)
    mentor_block_visible_to_student: bool = _bool_env("MENTOR_BLOCK_VISIBLE_TO_STUDENT", False)
    ai_assessment_max_cost_rub: float = float(os.getenv("AI_ASSESSMENT_MAX_COST_RUB", "100"))
    ai_max_worker_calls: int = int(os.getenv("AI_MAX_WORKER_CALLS", "100"))
    ai_max_critic_calls: int = int(os.getenv("AI_MAX_CRITIC_CALLS", "30"))
    ai_max_final_expert_calls: int = int(os.getenv("AI_MAX_FINAL_EXPERT_CALLS", "1"))
    ai_critic_temperature: float = float(os.getenv("AI_CRITIC_TEMPERATURE", "0"))
    ai_critic_max_completion_tokens: int = int(os.getenv("AI_CRITIC_MAX_COMPLETION_TOKENS", "4000"))
    ai_final_expert_temperature: float = float(os.getenv("AI_FINAL_EXPERT_TEMPERATURE", "0"))
    ai_final_expert_max_completion_tokens: int = int(os.getenv("AI_FINAL_EXPERT_MAX_COMPLETION_TOKENS", "3000"))
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
