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
            return self._build_mentor_report_lines(analysis, document, mentor_report)
        candidate_report = (payload.get("extra_blocks") or {}).get("rule_based_report") or (payload.get("extra_blocks") or {}).get("candidate_dissertation_report")
        if analysis.methodology_id in {"SCIENTIFIC_ARTICLE", "GRADUATION_THESIS", "MASTER_DISSERTATION", "COURSE_PAPER", "INTERNSHIP_REPORT", "RESEARCH_REPORT", "DOCTORAL_DISSERTATION", "DISSERTATION_ABSTRACT"} and candidate_report:
            return self._build_rule_based_report_lines(analysis, document, candidate_report, payload, detailed=False)
        if analysis.methodology_id == "CANDIDATE_DISSERTATION" and candidate_report:
            return self._build_candidate_report_lines(analysis, document, candidate_report, payload, detailed=False)
        demo_report = (payload.get("extra_blocks") or {}).get("demo_report")
        if demo_report:
            return self._build_demo_report_lines(analysis, document, demo_report, payload)

        total_score_max = (payload.get("extra_blocks") or {}).get("total_score_max") or analysis.methodology_max_score

        lines = [
            "Цифровой ментор. Итоговый отчет",
            f"Файл: {document.original_name}",
            f"Дата анализа: {analysis.completed_at or analysis.created_at}",
            f"ID анализа: {analysis.id}",
            f"Методология: {analysis.methodology_name or (payload.get('methodology') or {}).get('methodology_id', analysis.methodology_id)} {analysis.methodology_version}",
            (
                f"Общий балл: {payload.get('overall_score')} / {total_score_max}"
                if payload.get("overall_score") is not None and total_score_max is not None
                else "Общий балл: не рассчитывался"
            ),
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

    def _build_mentor_report_lines(self, analysis: Analysis, document: Document, report: dict) -> list[str]:
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
            f"Методология: {header.get('methodology') or analysis.methodology_name or analysis.methodology_id} {analysis.methodology_version}",
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

    def _build_demo_report_lines(self, analysis: Analysis, document: Document, report: dict, payload: dict) -> list[str]:
        total_score_max = (payload.get("extra_blocks") or {}).get("total_score_max") or analysis.methodology_max_score
        criterion_max_scores = {item.get("code"): item.get("max_score") for item in payload.get("criteria", [])}
        lines = [
            "ЦИФРОВОЙ МЕНТОР",
            "Предварительная оценка документа ВКР-стартапа",
            "",
            f"Работа: {document.original_name}",
            f"Методология: {analysis.methodology_name or analysis.methodology_id} {analysis.methodology_version}",
            f"Общий балл: {report.get('overall_score')} / {total_score_max or '—'}",
            "",
            "Оценки по критериям:",
        ]
        for item in report.get("criteria", []):
            criterion_max = item.get("max_score") or criterion_max_scores.get(item.get("code")) or 10
            lines.append(f"- {item.get('code')}. {item.get('name')}: {item.get('score')} / {criterion_max}. {item.get('comment')}")
            for strength in item.get("strengths", []):
                lines.append(f"  Сильная сторона: {strength}")
            for issue in item.get("issues", []):
                lines.append(f"  Требует доработки: {issue}")
        lines.extend(["", "Сильные стороны:"])
        lines.extend(f"- {item}" for item in report.get("strengths", []))
        lines.extend(["", "Что требует доработки:"])
        lines.extend(f"- {item}" for item in report.get("remarks", []))
        lines.extend(["", "Приоритетные рекомендации:"])
        lines.extend(f"- {item}" for item in report.get("recommendations", []))
        lines.extend(["", "Итоговое заключение:", report.get("conclusion") or ""])
        lines.extend(["", report.get("disclaimer") or "Предварительная аналитическая оценка не заменяет решение ГЭК."])
        return lines

    def _build_detailed_lines(self, analysis: Analysis, document: Document, payload: dict) -> list[str]:
        extra = payload.get("extra_blocks") or {}
        candidate_report = extra.get("rule_based_report") or extra.get("candidate_dissertation_report")
        if analysis.methodology_id in {"SCIENTIFIC_ARTICLE", "GRADUATION_THESIS", "MASTER_DISSERTATION", "COURSE_PAPER", "INTERNSHIP_REPORT", "RESEARCH_REPORT", "DOCTORAL_DISSERTATION", "DISSERTATION_ABSTRACT"} and candidate_report:
            return self._build_rule_based_report_lines(analysis, document, candidate_report, payload, detailed=True)
        if analysis.methodology_id == "CANDIDATE_DISSERTATION" and candidate_report:
            return self._build_candidate_report_lines(analysis, document, candidate_report, payload, detailed=True)
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
            f"Методология: {analysis.methodology_name or (payload.get('methodology') or {}).get('methodology_id', analysis.methodology_id)} {analysis.methodology_version}",
            "",
            "1. Краткое заключение:",
            payload.get("verdict") or source_report.get("conclusion") or source_report.get("what_this_work_is") or "",
            "",
            "2. Оценки и разбор критериев:",
        ]
        if demo_report.get("criteria"):
            for item in demo_report.get("criteria", []):
                criterion_max = item.get("max_score") or next(
                    (criterion.get("max_score") for criterion in payload.get("criteria", []) if criterion.get("code") == item.get("code")),
                    None,
                ) or 10
                lines.extend(
                    [
                        f"- {item.get('name')}: {item.get('score')} / {criterion_max}",
                        f"  Комментарий: {item.get('comment')}",
                        *[f"  Сильная сторона: {value}" for value in item.get("strengths", [])],
                        *[f"  Требует доработки: {value}" for value in item.get("issues", [])],
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
                why, action = self._fragment_guidance(fragment.get("text") or "")
                lines.extend(
                    [
                        f"Фрагмент {index} — {location_label}:",
                        f"Цитата: {fragment.get('text') or ''}",
                        f"Почему этот фрагмент важен: {why}",
                        f"Что рекомендуется изменить: {action}",
                        "",
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

    def _build_candidate_report_lines(self, analysis: Analysis, document: Document, report: dict, payload: dict, *, detailed: bool) -> list[str]:
        candidate_report = {"title": "Предварительный анализ кандидатской диссертации", "methodology_name": "Кандидатская диссертация", **report}
        return self._build_rule_based_report_lines(analysis, document, candidate_report, payload, detailed=detailed)

    def _build_rule_based_report_lines(self, analysis: Analysis, document: Document, report: dict, payload: dict, *, detailed: bool) -> list[str]:
        overall_score = payload.get("overall_score")
        evaluated_max = report.get("evaluated_max_score")
        score_label = (
            "не рассчитывалась — нет автоматически проверенных применимых правил"
            if overall_score is None or not evaluated_max
            else f"{overall_score} / {evaluated_max}"
        )
        lines = [
            "DIGITAL MENTOR",
            report.get("title") or "Предварительный анализ документа",
            "",
            f"Работа: {document.original_name}",
            f"Методология: {report.get('methodology_name') or analysis.methodology_name or analysis.methodology_id}",
            f"Версия: {analysis.methodology_version}",
            f"Внутренняя предварительная оценка Digital Mentor: {score_label}",
            f"Номинальная шкала: {report.get('nominal_max_score')} баллов",
            f"Полнота автоматической проверки: {round(float(report.get('coverage') or 0) * 100)}%",
            "",
            payload.get("verdict") or "",
            "",
            "Результаты по критериям:",
        ]
        for item in payload.get("criteria", []):
            score = "Не проверялось автоматически" if item.get("score") is None else f"{item.get('score')} / {item.get('max_score')}"
            lines.extend([f"- {item.get('code')} {item.get('title')}: {score}", f"  {item.get('explanation') or ''}"])
        lines.extend(["", "Сильные стороны:"])
        lines.extend(f"- {item}" for item in payload.get("strengths", []))
        lines.extend(["", "Существенные замечания:"])
        lines.extend(f"- {item}" for item in payload.get("improvements", []))
        lines.extend(["", "Рекомендации:"])
        lines.extend(f"- {item.get('title')}" for item in payload.get("recommendations", []))
        represented = report.get("represented_result") or {}
        if represented.get("text"):
            lines.extend(["", represented.get("title") or "Результат, представленный в работе", represented["text"]])
            if detailed:
                for evidence in represented.get("evidence") or []:
                    if evidence.get("quote"):
                        lines.append(f"- {evidence['quote']}")
        lines.extend(["", "Что не проверялось автоматически:"])
        for item in report.get("not_checked", []):
            lines.append(f"- {item.get('title')}: параметр не проверялся автоматически")
        limitations = report.get("limitations") or []
        if limitations:
            lines.extend(["", "В рамках данного анализа не выполняются:"])
            lines.extend(f"- {item}" for item in limitations)
        if detailed and report.get("source_type") != "INTERNAL_METHODOLOGY":
            lines.extend(["", "Нормативные основания rule checks:"])
            for item in report.get("rule_checks", []):
                if item.get("source_type") != "NORMATIVE_DOCUMENT" or not item.get("source_document"):
                    continue
                pages = "–".join(str(value) for value in item.get("source_pages") or [])
                lines.extend(
                    [
                        f"- {item.get('title')} — {item.get('status')}",
                        f"  Вывод: {item.get('finding')}",
                        f"  Основание: {item.get('source_document')}, {item.get('source_section')}, стр. {pages}",
                    ]
                )
        lines.extend(["", report.get("disclaimer") or ""])
        return lines

    @staticmethod
    def _fragment_guidance(text: str) -> tuple[str, str]:
        normalized = text.lower()
        if any(term in normalized for term in ("руб", "выруч", "затрат", "финанс", "окупаем")):
            return (
                "Он влияет на проверяемость финансовой реализуемости проекта.",
                "Добавьте источник исходных чисел, период расчета, формулу и сценарий проверки допущений.",
            )
        if any(term in normalized for term in ("рынок", "клиент", "аудитор", "конкурент", "спрос")):
            return (
                "Он используется как основание для оценки рынка и подтверждения потребности.",
                "Свяжите утверждение с исследованием, выборкой, датой и измеримым результатом проверки гипотезы.",
            )
        if any(term in normalized for term in ("риск", "угроз", "огранич", "отказ")):
            return (
                "Он определяет, насколько реалистично описаны ограничения и сценарии развития.",
                "Укажите вероятность, последствия, владельца риска и конкретную меру снижения.",
            )
        if any(term in normalized for term in ("технолог", "архитект", "алгоритм", "данн", "mvp")):
            return (
                "Он подтверждает технический механизм и реализуемость продукта.",
                "Покажите входные данные, последовательность обработки, измеримый результат и ограничения решения.",
            )
        return (
            "Он связан с одним из выводов отчета и требует более проверяемого обоснования.",
            "Добавьте проверяемый источник, метрику, расчет или конкретный механизм.",
        )

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

            block_height = len(wrapped_lines) * (self.line_height if fontsize <= 11 else self.line_height + 5) + spacing_after
            if y + block_height > self.page_height - self.margin:
                page = self._new_page(doc)
                y = self.margin
            if is_section:
                page.draw_rect(
                    fitz.Rect(self.margin - 10, y - 15, self.page_width - self.margin + 10, y + block_height - 2),
                    color=(0.82, 0.91, 0.92),
                    fill=(0.93, 0.97, 0.97),
                    width=0.8,
                )
            elif raw_line.startswith("-"):
                page.draw_rect(
                    fitz.Rect(self.margin - 7, y - 11, self.page_width - self.margin + 7, y + block_height - 3),
                    color=(0.9, 0.92, 0.92),
                    fill=(0.985, 0.99, 0.99),
                    width=0.5,
                )

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
        page.draw_rect(
            fitz.Rect(0, 0, self.page_width, 22),
            color=(0.08, 0.34, 0.36),
            fill=(0.08, 0.34, 0.36),
        )
        page.draw_rect(
            fitz.Rect(0, self.page_height - 14, self.page_width, self.page_height),
            color=(0.88, 0.94, 0.94),
            fill=(0.88, 0.94, 0.94),
        )
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
