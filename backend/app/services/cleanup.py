from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.core.config import settings
from app.services.storage import DocumentStorage


class CleanupService:
    def __init__(self, storage: DocumentStorage | None = None):
        self.storage = storage or DocumentStorage()

    def cleanup_audio(self) -> int:
        return self._cleanup_directory(self.storage.audio_directory(), settings.audio_retention_minutes, "minutes")

    def cleanup_reports(self) -> int:
        return self._cleanup_directory(self.storage.reports_dir, settings.report_retention_hours, "hours")

    def _cleanup_directory(self, directory: Path, amount: int, unit: str) -> int:
        if not directory.exists():
            return 0
        delta = timedelta(minutes=amount) if unit == "minutes" else timedelta(hours=amount)
        cutoff = datetime.now(timezone.utc) - delta
        deleted = 0
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified_at < cutoff:
                path.unlink()
                deleted += 1
        return deleted
