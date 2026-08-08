from app.core.errors import AppError
from app.methodology.models import Methodology
from app.methodology.repository import MethodologyRepository


class MethodologyResolver:
    def __init__(self, repository: MethodologyRepository):
        self.repository = repository

    async def resolve(self, artifact_type: str) -> Methodology:
        methodology = await self.repository.get_active(artifact_type)
        if methodology is None:
            raise AppError(
                "ACTIVE_METHODOLOGY_NOT_FOUND",
                "Активная методология не найдена",
                status_code=404,
                details={"artifact_type": artifact_type},
            )
        return methodology
