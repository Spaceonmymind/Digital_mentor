from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.db.models import Analysis, ChatMessage


MOCK_ANSWERS = {
    "Почему была снижена оценка?": "Основное снижение связано с неполным описанием методологии, слабой сравнительной частью и недостаточно выраженной авторской позицией.",
    "Как получить больше 90 баллов?": "Чтобы выйти выше 90 баллов, добавьте критерии оценки, расширьте список источников и явно свяжите выводы с целью исследования.",
    "Как повысить итоговый балл?": "Чтобы повысить итоговый балл, сначала уточните методологию, затем усилите сравнительный анализ и добавьте авторские выводы.",
    "Что исправить в первую очередь?": "В первую очередь стоит доработать раздел методологии: описать выборку, показатели, критерии анализа и способ интерпретации результатов.",
    "Как усилить практическую ценность?": "Добавьте сценарий внедрения, целевую аудиторию, ожидаемый эффект и ограничения применения предложенного решения.",
}


class ChatService:
    async def answer(self, session: AsyncSession, analysis_id: str, message: str) -> ChatMessage:
        analysis = await session.get(Analysis, analysis_id)
        if analysis is None:
            raise AppError("ANALYSIS_NOT_FOUND", "Анализ не найден", status_code=404)

        session.add(ChatMessage(analysis_id=analysis_id, role="user", content=message))
        answer = MOCK_ANSWERS.get(
            message,
            "Я бы предложил начать с уточнения цели, критериев оценки и авторских выводов. Это даст самый заметный прирост качества работы.",
        )
        assistant_message = ChatMessage(analysis_id=analysis_id, role="assistant", content=answer)
        session.add(assistant_message)
        await session.commit()
        await session.refresh(assistant_message)
        return assistant_message
