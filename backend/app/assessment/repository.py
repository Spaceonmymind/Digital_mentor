from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assessment.models import Assessment, AssessmentResult, IndicatorResult


class AssessmentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_assessment(
        self,
        artifact_type: str,
        artifact_id: str,
        methodology_id: str,
        status: str = "created",
    ) -> Assessment:
        assessment = Assessment(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            methodology_id=methodology_id,
            status=status,
        )
        self.session.add(assessment)
        await self.session.commit()
        await self.session.refresh(assessment)
        return assessment

    async def get_assessment(self, assessment_id: str) -> Assessment | None:
        return await self.session.get(Assessment, assessment_id)

    async def list_assessments(self, limit: int = 100, offset: int = 0) -> Sequence[Assessment]:
        result = await self.session.execute(
            select(Assessment).order_by(Assessment.created_at.desc()).offset(offset).limit(limit)
        )
        return result.scalars().all()

    async def create_assessment_result(
        self,
        assessment_id: str,
        methodology_criterion_id: str,
        status: str,
        severity: str | None = None,
        score: float | None = None,
        summary: str | None = None,
    ) -> AssessmentResult:
        result = AssessmentResult(
            assessment_id=assessment_id,
            methodology_criterion_id=methodology_criterion_id,
            severity=severity,
            score=score,
            status=status,
            summary=summary,
        )
        self.session.add(result)
        await self.session.commit()
        await self.session.refresh(result)
        return result

    async def create_indicator_result(
        self,
        assessment_result_id: str,
        assessment_id: str,
        methodology_indicator_id: str,
        status: str,
        score: float | None = None,
        summary: str | None = None,
        evidence: str | None = None,
        evidence_json: list | None = None,
        recommendation: str | None = None,
        recommendations_json: list | None = None,
        confidence: float | None = None,
        prompt_template_id: str | None = None,
        prompt_version: str | None = None,
        llm_call_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> IndicatorResult:
        result = IndicatorResult(
            assessment_result_id=assessment_result_id,
            assessment_id=assessment_id,
            methodology_indicator_id=methodology_indicator_id,
            status=status,
            score=score,
            summary=summary,
            evidence=evidence,
            evidence_json=evidence_json or [],
            recommendation=recommendation,
            recommendations_json=recommendations_json or [],
            confidence=confidence,
            prompt_template_id=prompt_template_id,
            prompt_version=prompt_version,
            llm_call_id=llm_call_id,
            idempotency_key=idempotency_key,
        )
        self.session.add(result)
        await self.session.commit()
        await self.session.refresh(result)
        return result
