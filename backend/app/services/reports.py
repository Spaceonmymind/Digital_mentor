from datetime import datetime, timezone
from textwrap import wrap
from uuid import uuid4

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Analysis, AnalysisResult, Document
from app.schemas.reports import ReportResponse
from app.services.storage import DocumentStorage


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


class ReportService:
    def __init__(self, storage: DocumentStorage | None = None):
        self.storage = storage or DocumentStorage()

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

    def _build_lines(self, analysis: Analysis, document: Document, payload: dict) -> list[str]:
        lines = [
            "Цифровой ментор. Итоговый отчет",
            f"Файл: {document.original_name}",
            f"Дата анализа: {analysis.completed_at or analysis.created_at}",
            f"ID анализа: {analysis.id}",
            f"Общий балл: {payload.get('overall_score')} / 100",
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
        ai_risk = payload.get("ai_risk") or {}
        lines.extend(
            [
                "",
                f"Уровень риска использования генеративного ИИ: {ai_risk.get('level')}",
                ai_risk.get("disclaimer", ""),
            ]
        )
        if settings.mock_analysis_enabled:
            lines.append("Отметка: отчет сформирован в демонстрационном режиме MockAnalysisEngine.")
        return lines

    def _render_pdf(self, lines: list[str]) -> bytes:
        text_commands = ["BT", "/F1 11 Tf", "50 790 Td", "14 TL"]
        for raw_line in lines:
            for line in wrap(raw_line, width=88) or [""]:
                safe_line = _pdf_escape(line)
                text_commands.append(f"({safe_line}) Tj")
                text_commands.append("T*")
        text_commands.append("ET")
        stream = "\n".join(text_commands).encode("utf-8")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        ]
        content = bytearray(b"%PDF-1.4\n")
        offsets = [0]
        for index, obj in enumerate(objects, start=1):
            offsets.append(len(content))
            content.extend(f"{index} 0 obj\n".encode("ascii"))
            content.extend(obj)
            content.extend(b"\nendobj\n")
        xref = len(content)
        content.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
        for offset in offsets[1:]:
            content.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        content.extend(
            f"trailer << /Root 1 0 R /Size {len(objects) + 1} >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii")
        )
        return bytes(content)
