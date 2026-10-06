from app.methodology.models import Methodology
from app.methodology.registry import MethodologyRegistry
from app.methodology.repository import MethodologyRepository


class MethodologyResolver:
    def __init__(self, repository: MethodologyRepository):
        self.repository = repository

    async def resolve(self, work_type: str, methodology_version: str | None = None) -> Methodology:
        return await MethodologyRegistry(self.repository).resolve(work_type, methodology_version)
