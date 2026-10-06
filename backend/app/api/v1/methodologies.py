from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.methodology.models import Methodology, MethodologyCriterion
from app.methodology.registry import WORK_TYPES
from app.methodology.schemas import ActiveMethodologySummary, WorkTypeCatalogItem


router = APIRouter(prefix="/api/v1/methodologies", tags=["methodologies"])


@router.get("", response_model=list[WorkTypeCatalogItem])
async def list_methodology_catalog(session: AsyncSession = Depends(get_session)) -> list[WorkTypeCatalogItem]:
    rows = (
        await session.execute(
            select(Methodology, func.count(MethodologyCriterion.id))
            .outerjoin(MethodologyCriterion, MethodologyCriterion.methodology_id == Methodology.id)
            .where(Methodology.is_active.is_(True), Methodology.work_type_code.is_not(None))
            .group_by(Methodology.id)
        )
    ).all()
    active_by_work_type = {methodology.work_type_code: (methodology, criteria_count) for methodology, criteria_count in rows}
    result = []
    for definition in WORK_TYPES:
        active = active_by_work_type.get(definition.code)
        methodology = active[0] if active else None
        result.append(
            WorkTypeCatalogItem(
                work_type=definition.code,
                display_name=definition.display_name,
                description=(methodology.description if methodology and methodology.description else definition.description),
                availability="AVAILABLE" if methodology else "NOT_CONFIGURED",
                active_methodology=(
                    ActiveMethodologySummary(
                        methodology_id=methodology.code,
                        name=methodology.name,
                        version=methodology.version,
                        max_score=methodology.max_score,
                        criteria_count=int(active[1]),
                    )
                    if methodology
                    else None
                ),
                active_version=methodology.version if methodology else None,
                max_score=methodology.max_score if methodology else None,
            )
        )
    return result
