import json
import re
from pathlib import Path
from typing import Any

from app.db.models import Document


def load_extracted_payload(document: Document) -> dict[str, Any]:
    if not document.extracted_path:
        return {}
    path = Path(document.extracted_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def relevant_document_fragments(document: Document, query: str, limit: int = 8, max_chars: int = 900) -> list[dict[str, Any]]:
    payload = load_extracted_payload(document)
    items = _items_from_payload(payload)
    if not items:
        return []

    query_terms = _terms(query)
    scored = []
    for item in items:
        text = item["text"]
        score = _score(text, query_terms)
        if score > 0:
            scored.append((score, item))

    if not scored:
        scored = [(0, item) for item in items[:limit]]
    scored.sort(key=lambda row: row[0], reverse=True)
    result = []
    for _, item in scored[:limit]:
        result.append({**item, "text": _trim(item["text"], max_chars)})
    return result


def document_fragments_for_report(document: Document, result_json: dict, limit: int = 14, max_chars: int = 900) -> list[dict[str, Any]]:
    query_parts = []
    query_parts.append(str(result_json.get("verdict") or ""))
    query_parts.extend(str(item) for item in result_json.get("strengths") or [])
    query_parts.extend(str(item) for item in result_json.get("improvements") or [])
    for item in result_json.get("remarks") or []:
        query_parts.append(str(item.get("title") or ""))
        query_parts.append(str(item.get("recommendation") or ""))
    for item in result_json.get("recommendations") or []:
        query_parts.append(str(item.get("title") or ""))
        query_parts.append(str(item.get("effect") or ""))
    return relevant_document_fragments(document, "\n".join(query_parts), limit=limit, max_chars=max_chars)


def _items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if payload.get("pages"):
        items = []
        for page in payload["pages"]:
            for block in page.get("blocks") or []:
                text = str(block.get("text") or "").strip()
                if len(text) >= 60:
                    items.append(
                        {
                            "page": page.get("page_number"),
                            "section": None,
                            "block_index": block.get("block_index"),
                            "text": text,
                        }
                    )
        return items

    items = []
    current_section = None
    for paragraph in payload.get("paragraphs") or []:
        text = str(paragraph.get("text") or "").strip()
        if not text:
            continue
        style = str(paragraph.get("style") or "")
        if "heading" in style.lower() or _looks_like_heading(text):
            current_section = text[:160]
        if len(text) >= 60:
            items.append(
                {
                    "page": None,
                    "section": current_section,
                    "block_index": paragraph.get("paragraph_index"),
                    "text": text,
                }
            )
    return items


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zа-яА-Я0-9]{4,}", text.lower())
    stop = {"котор", "документ", "работ", "анализ", "нужно", "может", "есть", "это", "того"}
    return {word for word in words if word not in stop}


def _score(text: str, query_terms: set[str]) -> int:
    normalized = text.lower()
    score = sum(1 for term in query_terms if term in normalized)
    important = ("проблем", "архитект", "эконом", "риск", "решени", "механизм", "выруч", "клиент", "данн", "довер")
    score += sum(3 for term in important if term in normalized)
    return score


def _looks_like_heading(text: str) -> bool:
    return len(text) <= 120 and bool(re.match(r"^([0-9]+[.)]|[0-9]+\\.[0-9]+|[А-ЯA-Z][^.!?]{5,})", text))


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."
