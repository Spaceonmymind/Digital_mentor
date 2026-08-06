from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.methodology.repository import MethodologyRepository
from app.methodology.schemas import MethodologyCreate, MethodologyFullResponse, MethodologyResponse
from app.methodology.service import MethodologyService


router = APIRouter(prefix="/api/v1/internal/methodologies", tags=["internal-methodologies"])


@router.post("", response_model=MethodologyResponse)
async def create_methodology(
    payload: MethodologyCreate,
    session: AsyncSession = Depends(get_session),
) -> MethodologyResponse:
    service = MethodologyService(MethodologyRepository(session))
    methodology = await service.create_methodology(
        code=payload.code,
        name=payload.name,
        version=payload.version,
        description=payload.description,
        is_active=payload.is_active,
    )
    return MethodologyResponse.model_validate(methodology)


@router.get("", response_model=list[MethodologyResponse])
async def list_methodologies(session: AsyncSession = Depends(get_session)) -> list[MethodologyResponse]:
    service = MethodologyService(MethodologyRepository(session))
    return await service.list_methodologies()


@router.get("/{code}", response_model=MethodologyFullResponse)
async def get_methodology(
    code: str,
    session: AsyncSession = Depends(get_session),
) -> MethodologyFullResponse:
    service = MethodologyService(MethodologyRepository(session))
    return await service.get_full_by_code(code)
