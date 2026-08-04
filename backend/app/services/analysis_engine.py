from typing import Protocol

from app.schemas.results import AnalysisResultPayload


class AnalysisEngine(Protocol):
    async def run(
        self,
        analysis_id: str,
        document_id: str,
        methodology_id: str,
        methodology_version: str,
    ) -> AnalysisResultPayload:
        ...
