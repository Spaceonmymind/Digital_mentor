from dataclasses import dataclass

from app.core.errors import AppError
from app.methodology.models import Methodology
from app.methodology.repository import MethodologyRepository


@dataclass(frozen=True)
class WorkTypeDefinition:
    code: str
    display_name: str
    description: str
    sort_order: int


WORK_TYPES = (
    WorkTypeDefinition("STARTUP_VKR", "ВКР в виде стартапа", "Анализ стартап-проекта по утверждённой методологии.", 10),
    WorkTypeDefinition("COURSE_WORK", "Курсовая работа", "Методология находится в подготовке.", 20),
    WorkTypeDefinition("BACHELOR_SPECIALIST_THESIS", "ВКР бакалавра / специалиста", "Методология находится в подготовке.", 30),
    WorkTypeDefinition("MASTER_THESIS", "Магистерская диссертация", "Методология находится в подготовке.", 40),
    WorkTypeDefinition("PRACTICE_REPORT", "Отчёт по практике", "Методология находится в подготовке.", 50),
    WorkTypeDefinition("RESEARCH_REPORT", "Отчёт по НИР", "Методология находится в подготовке.", 60),
    WorkTypeDefinition("SCIENTIFIC_ARTICLE", "Научная статья", "Методология находится в подготовке.", 70),
    WorkTypeDefinition("CANDIDATE_DISSERTATION", "Кандидатская диссертация", "Методология находится в подготовке.", 80),
    WorkTypeDefinition("DOCTORAL_DISSERTATION", "Докторская диссертация", "Методология находится в подготовке.", 90),
    WorkTypeDefinition("DISSERTATION_ABSTRACT", "Автореферат диссертации", "Методология находится в подготовке.", 100),
)
WORK_TYPE_BY_CODE = {item.code: item for item in WORK_TYPES}


class MethodologyRegistry:
    def __init__(self, repository: MethodologyRepository):
        self.repository = repository

    async def resolve(
        self,
        work_type: str,
        methodology_version: str | None = None,
        additional_parameters: dict | None = None,
    ) -> Methodology:
        del additional_parameters  # reserved for education level, department, discipline and review stage
        normalized = work_type.strip().upper()
        if normalized not in WORK_TYPE_BY_CODE:
            raise AppError(
                "WORK_TYPE_NOT_FOUND",
                "Неизвестный тип работы",
                status_code=404,
                details={"work_type": normalized},
            )
        methodology = (
            await self.repository.get_version_for_work_type(normalized, methodology_version)
            if methodology_version
            else await self.repository.get_active_for_work_type(normalized)
        )
        # Backward compatibility for methodologies created before work_type_code
        # existed. New records must use the explicit relationship.
        if methodology is None:
            methodology = (
                await self.repository.get_version(normalized, methodology_version)
                if methodology_version
                else await self.repository.get_active(normalized)
            )
        if methodology is None:
            raise AppError(
                "METHODOLOGY_NOT_CONFIGURED",
                "Методология для данного типа работы находится в подготовке",
                status_code=409,
                details={"work_type": normalized, "methodology_version": methodology_version},
            )
        return methodology

    async def resolve_historical(self, methodology_code: str, methodology_version: str) -> Methodology:
        methodology = await self.repository.get_version(methodology_code, methodology_version)
        if methodology is None:
            raise AppError(
                "METHODOLOGY_VERSION_NOT_FOUND",
                "Сохранённая версия методологии не найдена",
                status_code=404,
                details={"methodology_id": methodology_code, "methodology_version": methodology_version},
            )
        return methodology
