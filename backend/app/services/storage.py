from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings


class StoredFile:
    def __init__(self, stored_name: str, path: Path, size: int, checksum: str):
        self.stored_name = stored_name
        self.path = path
        self.size = size
        self.checksum = checksum


class DocumentStorage:
    def __init__(self, root: Path | None = None):
        self.root = root or settings.storage_path
        self.documents_dir = self.root / "documents"
        self.extracted_dir = self.root / "extracted"
        self.reports_dir = self.root / "reports"
        for directory in (self.documents_dir, self.extracted_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadFile, extension: str) -> StoredFile:
        import hashlib

        stored_name = f"{uuid4()}{extension}"
        path = self.documents_dir / stored_name
        checksum = hashlib.sha256()
        size = 0

        with path.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                checksum.update(chunk)
                handle.write(chunk)

        return StoredFile(stored_name, path, size, checksum.hexdigest())

    def get(self, stored_name: str) -> Path:
        path = (self.documents_dir / stored_name).resolve()
        if not str(path).startswith(str(self.documents_dir.resolve())):
            raise ValueError("Invalid storage path")
        return path

    def exists(self, stored_name: str) -> bool:
        return self.get(stored_name).exists()

    def delete(self, stored_name: str) -> None:
        path = self.get(stored_name)
        if path.exists():
            path.unlink()

    def extracted_path(self, document_id: str) -> Path:
        directory = self.extracted_dir / document_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "content.json"

    def extracted_directory(self, document_id: str) -> Path:
        return (self.extracted_dir / document_id).resolve()

    def report_directory(self, analysis_id: str) -> Path:
        directory = (self.reports_dir / analysis_id).resolve()
        if not str(directory).startswith(str(self.reports_dir.resolve())):
            raise ValueError("Invalid report path")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def report_path(self, analysis_id: str, report_id: str) -> Path:
        path = (self.report_directory(analysis_id) / f"{report_id}.pdf").resolve()
        if not str(path).startswith(str(self.reports_dir.resolve())):
            raise ValueError("Invalid report path")
        return path

    def audio_directory(self) -> Path:
        directory = (self.root / "audio").resolve()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def audio_path(self, audio_id: str) -> Path:
        path = (self.audio_directory() / f"{audio_id}.mp3").resolve()
        if not str(path).startswith(str(self.audio_directory().resolve())):
            raise ValueError("Invalid audio path")
        return path

    def delete_tree(self, path: Path | str | None) -> None:
        if not path:
            return
        resolved = Path(path).resolve()
        if not str(resolved).startswith(str(self.root.resolve())):
            raise ValueError("Invalid storage path")
        if resolved.is_dir():
            shutil.rmtree(resolved, ignore_errors=True)
        elif resolved.exists():
            resolved.unlink()
