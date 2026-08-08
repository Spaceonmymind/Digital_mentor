from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.methodology.models import Methodology, MethodologyAgent, MethodologyCriterion, MethodologyIndicator, PromptTemplate


class MethodologyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        code: str,
        name: str,
        version: str,
        description: str | None = None,
        is_active: bool = True,
        is_demo: bool = False,
    ) -> Methodology:
        methodology = Methodology(
            code=code,
            name=name,
            version=version,
            description=description,
            is_active=is_active,
            is_demo=is_demo,
        )
        self.session.add(methodology)
        await self.session.commit()
        await self.session.refresh(methodology)
        return methodology

    async def get_by_code(self, code: str) -> Methodology | None:
        result = await self.session.execute(select(Methodology).where(Methodology.code == code).order_by(Methodology.version.desc()).limit(1))
        return result.scalar_one_or_none()

    async def get_active(self, code: str) -> Methodology | None:
        result = await self.session.execute(
            select(Methodology)
            .where(Methodology.code == code, Methodology.is_active.is_(True))
            .order_by(Methodology.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list(self, is_active: bool | None = None) -> Sequence[Methodology]:
        query = select(Methodology).order_by(Methodology.code)
        if is_active is not None:
            query = query.where(Methodology.is_active == is_active)
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_full_by_code(self, code: str) -> Methodology | None:
        result = await self.session.execute(
            select(Methodology)
            .where(Methodology.code == code)
            .options(
                selectinload(Methodology.criteria).selectinload(MethodologyCriterion.indicators),
                selectinload(Methodology.prompts),
                selectinload(Methodology.agents),
            )
            .order_by(Methodology.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_criterion(
        self,
        methodology_id: str,
        number: str,
        title: str,
        description: str | None,
        weight: float | None,
        order_index: int,
        is_demo: bool = False,
    ) -> MethodologyCriterion:
        criterion = MethodologyCriterion(
            methodology_id=methodology_id,
            number=number,
            title=title,
            description=description,
            weight=weight,
            order_index=order_index,
            is_demo=is_demo,
        )
        self.session.add(criterion)
        await self.session.commit()
        await self.session.refresh(criterion)
        return criterion

    async def create_indicator(
        self,
        criterion_id: str,
        title: str,
        description: str | None,
        expected_result: str | None,
        weight: float | None,
        order_index: int,
        is_demo: bool = False,
    ) -> MethodologyIndicator:
        indicator = MethodologyIndicator(
            criterion_id=criterion_id,
            title=title,
            description=description,
            expected_result=expected_result,
            weight=weight,
            order_index=order_index,
            is_demo=is_demo,
        )
        self.session.add(indicator)
        await self.session.commit()
        await self.session.refresh(indicator)
        return indicator

    async def create_agent(
        self,
        methodology_id: str,
        code: str,
        name: str,
        version: str,
        stage_code: str,
        execution_order: int,
        execution_mode: str,
        model_role: str,
        prompt_template_id: str | None = None,
        input_schema_code: str | None = None,
        output_schema_code: str | None = None,
        is_active: bool = True,
        is_required: bool = True,
        is_demo: bool = False,
    ) -> MethodologyAgent:
        agent = MethodologyAgent(
            methodology_id=methodology_id,
            code=code,
            name=name,
            version=version,
            stage_code=stage_code,
            execution_order=execution_order,
            execution_mode=execution_mode,
            model_role=model_role,
            prompt_template_id=prompt_template_id,
            input_schema_code=input_schema_code,
            output_schema_code=output_schema_code,
            is_active=is_active,
            is_required=is_required,
            is_demo=is_demo,
        )
        self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent

    async def create_prompt(
        self,
        methodology_id: str,
        stage: str,
        system_prompt: str,
        user_template: str,
        version: str,
        is_demo: bool = False,
    ) -> PromptTemplate:
        prompt = PromptTemplate(
            methodology_id=methodology_id,
            stage=stage,
            system_prompt=system_prompt,
            user_template=user_template,
            version=version,
            is_demo=is_demo,
        )
        self.session.add(prompt)
        await self.session.commit()
        await self.session.refresh(prompt)
        return prompt
