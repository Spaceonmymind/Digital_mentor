from app.core.errors import AppError
from app.methodology.models import Methodology
from app.methodology.repository import MethodologyRepository
from app.methodology.schemas import (
    MethodologyCriterionResponse,
    MethodologyFullResponse,
    MethodologyIndicatorResponse,
    MethodologyResponse,
)


class MethodologyService:
    def __init__(self, repository: MethodologyRepository):
        self.repository = repository

    async def create_methodology(self, code: str, name: str, version: str, description: str | None, is_active: bool):
        return await self.repository.create(
            code=code,
            name=name,
            version=version,
            description=description,
            is_active=is_active,
        )

    async def list_methodologies(self) -> list[MethodologyResponse]:
        methodologies = await self.repository.list()
        return [MethodologyResponse.model_validate(methodology) for methodology in methodologies]

    async def get_full_by_code(self, code: str) -> MethodologyFullResponse:
        methodology = await self.repository.get_full_by_code(code)
        if methodology is None:
            raise AppError("METHODOLOGY_NOT_FOUND", "Методология не найдена", status_code=404)
        return self._full_response(methodology)

    def _full_response(self, methodology: Methodology) -> MethodologyFullResponse:
        criteria = []
        for criterion in sorted(methodology.criteria, key=lambda item: (item.order_index, item.number, item.id)):
            indicators = [
                MethodologyIndicatorResponse(
                    id=indicator.id,
                    title=indicator.title,
                    description=indicator.description,
                    expected_result=indicator.expected_result,
                    weight=indicator.weight,
                    order_index=indicator.order_index,
                    is_demo=indicator.is_demo,
                )
                for indicator in sorted(criterion.indicators, key=lambda item: (item.order_index, item.id))
            ]
            criteria.append(
                MethodologyCriterionResponse(
                    id=criterion.id,
                    number=criterion.number,
                    title=criterion.title,
                    description=criterion.description,
                    weight=criterion.weight,
                    order_index=criterion.order_index,
                    is_demo=criterion.is_demo,
                    indicators=indicators,
                )
            )
        return MethodologyFullResponse(
            id=methodology.id,
            code=methodology.code,
            name=methodology.name,
            description=methodology.description,
            version=methodology.version,
            is_active=methodology.is_active,
            is_demo=methodology.is_demo,
            created_at=methodology.created_at,
            criteria=criteria,
            prompts=[prompt for prompt in sorted(methodology.prompts, key=lambda item: (item.stage, item.version, item.id))],
        )
