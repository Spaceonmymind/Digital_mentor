from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import fitz

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisResult, Document
from app.schemas.reports import ReportResponse
from app.services.document_context import document_fragments_for_report
from app.services.storage import DocumentStorage


class ReportService:
    page_width = 595
    page_height = 842
    margin = 50
    line_height = 15

    def __init__(self, storage: DocumentStorage | None = None):
        self.storage = storage or DocumentStorage()
        self.font_regular = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Golos-Text_Regular.ttf"
        self.font_bold = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Golos-Text_Bold.ttf"

    def create_pdf_report(self, analysis: Analysis, document: Document, result: AnalysisResult) -> ReportResponse:
        if analysis.status != "completed":
            raise AppError("ANALYSIS_NOT_COMPLETED", "Результат еще не сформирован", status_code=409)

        report_id = str(uuid4())
        output_path = self.storage.report_path(analysis.id, report_id)
        lines = self._build_lines(analysis, document, result.result_json)
        output_path.write_bytes(self._render_pdf(lines))
        return ReportResponse(
            report_id=report_id,
            analysis_id=analysis.id,
            format="pdf",
            report_url=f"/api/v1/analyses/{analysis.id}/reports/{report_id}",
            created_at=datetime.now(timezone.utc),
        )

    def create_detailed_pdf_report(
        self,
        analysis: Analysis,
        document: Document,
        result: AnalysisResult,
        report_id: str | None = None,
    ) -> ReportResponse:
        if analysis.status != "completed":
            raise AppError("ANALYSIS_NOT_COMPLETED", "Результат еще не сформирован", status_code=409)

        report_id = report_id or str(uuid4())
        output_path = self.storage.report_path(analysis.id, report_id)
        lines = self._build_detailed_lines(analysis, document, result.result_json)
        output_path.write_bytes(self._render_pdf(lines))
        return ReportResponse(
            report_id=report_id,
            analysis_id=analysis.id,
            format="pdf",
            report_url=f"/api/v1/analyses/{analysis.id}/detailed-report/download",
            created_at=datetime.now(timezone.utc),
        )

    def _build_lines(self, analysis: Analysis, document: Document, payload: dict) -> list[str]:
        mentor_report = (payload.get("extra_blocks") or {}).get("mentor_report")
        if mentor_report:
            return self._build_mentor_report_lines(document, mentor_report)
        demo_report = (payload.get("extra_blocks") or {}).get("demo_report")
        if demo_report:
            return self._build_demo_report_lines(document, demo_report)

        lines = [
            "Цифровой ментор. Итоговый отчет",
            f"Файл: {document.original_name}",
            f"Дата анализа: {analysis.completed_at or analysis.created_at}",
            f"ID анализа: {analysis.id}",
            f"Методология: {(payload.get('methodology') or {}).get('methodology_id', analysis.methodology_id)} {(payload.get('methodology') or {}).get('methodology_version', analysis.methodology_version)}",
            f"Общий балл: {payload.get('overall_score')} / 100" if payload.get("overall_score") else "Общий балл: не рассчитывался",
            f"Заключение: {payload.get('verdict')}",
            "",
            "Оценки по критериям:",
        ]
        for item in payload.get("criteria", []):
            lines.append(f"- {item.get('title')}: {item.get('score')} / {item.get('max_score', 100)}. {item.get('explanation', '')}")
        lines.extend(["", "Сильные стороны:"])
        lines.extend(f"- {item}" for item in payload.get("strengths", []))
        lines.extend(["", "Зоны развития:"])
        lines.extend(f"- {item}" for item in payload.get("improvements", []))
        lines.extend(["", "Замечания:"])
        for item in payload.get("remarks", []):
            lines.append(f"- {item.get('title')}: {item.get('quote')} Рекомендация: {item.get('recommendation')}")
        lines.extend(["", "Рекомендации:"])
        for item in payload.get("recommendations", []):
            lines.append(f"- {item.get('priority')}: {item.get('title')} Эффект: {item.get('effect')}. Сложность: {item.get('complexity')}.")
        lines.extend(["", "Доказательные фрагменты:"])
        for item in payload.get("evidence", []):
            lines.append(f"- {item.get('section') or 'Фрагмент'}: {item.get('quote')}")
        extra = payload.get("extra_blocks") or {}
        lines.extend(["", "Противоречия:"])
        lines.extend(f"- {item}" for item in extra.get("contradictions", []))
        lines.extend(["", "Вопросы автору:"])
        lines.extend(f"- {item}" for item in extra.get("questions_to_author", []))
        lines.extend(["", "Ограничения анализа:"])
        lines.extend(f"- {item}" for item in extra.get("limitations", []))
        ai_risk = payload.get("ai_risk") or {}
        lines.extend(
            [
                "",
                "Отметка об использовании AI: анализ выполнен с использованием LLM-агентов; выводы требуют человеческой проверки.",
                f"Уровень риска использования генеративного ИИ: {ai_risk.get('level')}",
                ai_risk.get("disclaimer", ""),
                "",
                "Техническое приложение:",
                f"Assessment ID: {extra.get('assessment_id')}",
                f"Токены: {extra.get('total_tokens')}",
                f"Стоимость, RUB: {extra.get('total_cost_rub')}",
                f"Время обработки, ms: {extra.get('processing_time_ms')}",
            ]
        )
        if settings.mock_analysis_enabled:
            lines.append("Отметка: отчет сформирован в демонстрационном режиме MockAnalysisEngine.")
        return lines

    def _build_mentor_report_lines(self, document: Document, report: dict) -> list[str]:
        header = report.get("header") or {}
        veto = report.get("veto") or {}
        question = report.get("one_question") or {}
        next_step = report.get("one_next_step") or {}
        lines = [
            "ЦИФРОВОЙ МЕНТОР",
            "Разбор работы",
            "",
            f"Работа: {header.get('work_title') or document.original_name}",
            f"Тип: {header.get('work_type') or 'ВКР как стартап'}",
            f"Дата: {header.get('analysis_date') or ''}",
            f"Версия работы: {header.get('work_version') or 'не указана'}",
            f"Методология: {header.get('methodology') or ''}",
            f"Текущая стадия работы: {header.get('current_stage') or ''}",
            "",
            "1. Что это за работа:",
            report.get("what_this_work_is") or "",
            "",
        ]
        if veto.get("is_active"):
            lines.extend(
                [
                    "2. Вето:",
                    "ВЕТО",
                    f"Причина: {veto.get('reason') or ''}",
                    f"Почему дальнейшее оценивание сейчас бессмысленно: {veto.get('why_further_assessment_is_meaningless') or ''}",
                    f"Что необходимо сделать, чтобы снять вето: {veto.get('how_to_remove') or ''}",
                    "",
                ]
            )

        lines.extend(["3. Что устояло:"])
        lines.extend(f"- {item}" for item in report.get("what_survived", []))
        lines.extend(["", "4. Главные возражения:"])
        for item in report.get("objections", []):
            lines.extend(
                [
                    f"- {item.get('title')}",
                    f"  Что не работает: {item.get('what_does_not_work')}",
                    f"  Почему: {item.get('why')}",
                    f"  Куда двигаться: {item.get('where_to_move')}",
                ]
            )
        lines.extend(
            [
                "",
                "5. Один вопрос:",
                question.get("question") or "",
                "",
                "6. Следующий шаг:",
                next_step.get("step") or "",
                f"Как проверить результат: {next_step.get('check_result') or ''}",
                "",
                "7. Путь работы по стадиям:",
            ]
        )
        for item in report.get("stage_assessments", []):
            lines.extend(
                [
                    f"- {item.get('stage_code')} {item.get('title')} — {item.get('score')}/5",
                    f"  Что выполнено: {item.get('completed')}",
                    f"  До следующего уровня: {item.get('next_level_requirement')}",
                ]
            )
        lines.extend(["", "Отметка об использовании AI: разбор сформирован цифровым ментором и требует человеческой проверки."])
        return lines

    def _build_demo_report_lines(self, document: Document, report: dict) -> list[str]:
        lines = [
            "ЦИФРОВОЙ МЕНТОР",
            "Demo-разбор работы",
            "",
            f"Работа: {document.original_name}",
            f"Общий балл: {report.get('overall_score')} / 60",
            "",
            "Оценки по критериям:",
        ]
        for item in report.get("criteria", []):
            lines.append(f"- {item.get('name')}: {item.get('score')} / 10. {item.get('comment')}")
        lines.extend(["", "3 сильные стороны:"])
        lines.extend(f"- {item}" for item in report.get("strengths", []))
        lines.extend(["", "3 замечания:"])
        lines.extend(f"- {item}" for item in report.get("remarks", []))
        lines.extend(["", "3 рекомендации:"])
        lines.extend(f"- {item}" for item in report.get("recommendations", []))
        lines.extend(["", "Итоговое заключение:", report.get("conclusion") or ""])
        lines.extend(["", "Отметка: demo-режим использует сокращенный мультиагентный анализ и не заменяет полный expert-разбор."])
        return lines

    def _build_detailed_lines(self, analysis: Analysis, document: Document, payload: dict) -> list[str]:
        extra = payload.get("extra_blocks") or {}
        demo_report = extra.get("demo_report") or {}
        mentor_report = extra.get("mentor_report") or {}
        source_report = demo_report or mentor_report
        fragments = document_fragments_for_report(document, payload)

        lines = [
            "ЦИФРОВОЙ МЕНТОР",
            "Подробный аналитический отчет",
            "",
            f"Работа: {document.original_name}",
            f"Дата анализа: {analysis.completed_at or analysis.created_at}",
            f"Методология: {(payload.get('methodology') or {}).get('methodology_id', analysis.methodology_id)} {(payload.get('methodology') or {}).get('methodology_version', analysis.methodology_version)}",
            "",
            "1. Краткое заключение:",
            payload.get("verdict") or source_report.get("conclusion") or source_report.get("what_this_work_is") or "",
            "",
            "2. Оценки и разбор критериев:",
        ]
        if demo_report.get("criteria"):
            for item in demo_report.get("criteria", []):
                lines.extend(
                    [
                        f"- {item.get('name')}: {item.get('score')} / 10",
                        f"  Комментарий: {item.get('comment')}",
                        "  Что проверить в тексте: найдите разделы, где автор показывает наблюдаемую проблему, механизм решения, архитектуру, экономику и риски не декларациями, а проверяемыми элементами.",
                    ]
                )
        else:
            for item in payload.get("criteria", []):
                lines.extend(
                    [
                        f"- {item.get('title')}: {item.get('score')} / {item.get('max_score', 100)}",
                        f"  Комментарий: {item.get('explanation', '')}",
                    ]
                )

        lines.extend(["", "3. Сильные стороны с пояснениями:"])
        for item in payload.get("strengths") or source_report.get("strengths") or source_report.get("what_survived") or []:
            lines.extend([f"- {item}", "  Как усилить: привяжите этот элемент к конкретному месту документа и покажите, почему он выдерживает критическую проверку."])

        lines.extend(["", "4. Замечания и риски:"])
        remarks = payload.get("remarks") or [{"title": item} for item in source_report.get("remarks", [])]
        for item in remarks:
            title = item.get("title") or ""
            recommendation = item.get("recommendation") or "Уточнить доказательство, механизм и проверяемый результат."
            lines.extend(
                [
                    f"- {title}",
                    f"  Почему это важно: без этого вывода эксперт не сможет отличить работоспособную конструкцию от декларации.",
                    f"  Совет: {recommendation}",
                ]
            )

        lines.extend(["", "5. Рекомендации к доработке:"])
        recommendations = payload.get("recommendations") or [{"title": item} for item in source_report.get("recommendations", [])]
        for item in recommendations:
            lines.extend(
                [
                    f"- {item.get('title') or item}",
                    f"  Ожидаемый эффект: {item.get('effect') or 'повысит проверяемость и убедительность работы.'}",
                    f"  Практический шаг: оформите изменение как конкретный фрагмент текста, таблицу, схему или расчет.",
                ]
            )

        lines.extend(["", "6. Конкретные фрагменты текста и как их править:"])
        if fragments:
            for index, fragment in enumerate(fragments, start=1):
                location = []
                if fragment.get("page"):
                    location.append(f"стр. {fragment.get('page')}")
                if fragment.get("section"):
                    location.append(str(fragment.get("section")))
                location_label = ", ".join(location) or f"блок {fragment.get('block_index')}"
                lines.extend(
                    [
                        f"Фрагмент {index} ({location_label}):",
                        fragment.get("text") or "",
                        "Что сделать: проверьте, является ли этот фрагмент доказательством, механизмом, расчетом или только декларацией. Если это декларация, добавьте конкретное действие, источник данных, метрику или условие проверки.",
                    ]
                )
        else:
            lines.append("Извлеченный текст документа недоступен для приложения к подробному отчету.")

        lines.extend(
            [
                "",
                "7. Предлагаемые схемы для доработки:",
                "- Схема механизма результата: входные данные -> действие сервиса -> проверяемый результат.",
                "- Схема доверия: участник -> что видит -> что может изменить -> чем ограничены полномочия.",
                "- Таблица go/no-go: условие -> порог -> источник данных -> решение.",
                "",
                "8. Ограничения:",
                "- Подробный отчет использует быстрый результат анализа и фрагменты исходного текста документа.",
                "- Он не блокирует быстрый demo-результат и может быть пересобран отдельно.",
                "- Финальные выводы требуют проверки человеком.",
            ]
        )
        return lines

    def _render_pdf(self, lines: list[str]) -> bytes:
        doc = fitz.open()
        regular_font = fitz.Font(fontfile=str(self.font_regular))
        page = self._new_page(doc)
        y = self.margin

        for raw_line in lines:
            is_title = raw_line in {"Цифровой ментор. Итоговый отчет", "ЦИФРОВОЙ МЕНТОР"}
            is_section = raw_line.endswith(":") and not raw_line.startswith("-")
            fontname = "GolosBold" if is_title or is_section else "Golos"
            fontsize = 18 if is_title else 13 if is_section else 11
            color = (0.08, 0.15, 0.17) if is_title else (0.15, 0.4, 0.41) if is_section else (0.1, 0.1, 0.1)
            spacing_after = 9 if is_title else 6 if is_section else 2

            wrapped_lines = self._wrap_line(raw_line, regular_font, fontsize)
            if not wrapped_lines:
                y += self.line_height
                continue

            for line in wrapped_lines:
                if y > self.page_height - self.margin:
                    page = self._new_page(doc)
                    y = self.margin
                page.insert_text(
                    (self.margin, y),
                    line,
                    fontname=fontname,
                    fontsize=fontsize,
                    color=color,
                )
                y += self.line_height if fontsize <= 11 else self.line_height + 5
            y += spacing_after

        payload = doc.tobytes(garbage=4, deflate=True)
        doc.close()
        return payload

    def _new_page(self, doc: fitz.Document) -> fitz.Page:
        page = doc.new_page(width=self.page_width, height=self.page_height)
        page.insert_font(fontname="Golos", fontfile=str(self.font_regular))
        page.insert_font(fontname="GolosBold", fontfile=str(self.font_bold))
        return page

    def _wrap_line(self, text: str, font: fitz.Font, fontsize: int) -> list[str]:
        if not text:
            return []
        max_width = self.page_width - self.margin * 2
        result: list[str] = []
        current = ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if font.text_length(candidate, fontsize=fontsize) <= max_width:
                current = candidate
                continue
            if current:
                result.append(current)
            current = word
        if current:
            result.append(current)
        return result
