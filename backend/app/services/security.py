from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ScanResult:
    status: str
    provider: str
    message: str


class FileSecurityService(Protocol):
    async def scan(self, file_path: Path) -> ScanResult:
        ...


class StubFileSecurityService:
    async def scan(self, file_path: Path) -> ScanResult:
        return ScanResult(
            status="not_performed",
            provider="stub",
            message="Антивирусная проверка не подключена",
        )
