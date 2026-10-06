import re


def deterministic_document_preflight(payload: dict) -> dict:
    """Methodology-neutral inventory of extractable document structure."""
    blocks = []
    for page in payload.get("pages") or []:
        for block in page.get("blocks") or []:
            text = str(block.get("text") or "").strip()
            if text:
                blocks.append({"location": f"page:{page.get('page_number')}:block:{block.get('block_index')}", "text": text})
    for paragraph in payload.get("paragraphs") or []:
        text = str(paragraph.get("text") or "").strip()
        if text:
            blocks.append({"location": f"paragraph:{paragraph.get('paragraph_index')}", "text": text})
    if not blocks:
        blocks = [{"location": "full_text", "text": str(payload.get("full_text") or "")}]

    heading_re = re.compile(r"^(список\s+(?:использованной\s+)?литературы|литература|references|библиографический\s+список)(?:\s|$)", re.I)
    bibliography_index = next((i for i, block in enumerate(blocks) if heading_re.match(block["text"])), None)
    body_blocks = blocks[:bibliography_index] if bibliography_index is not None else blocks
    bibliography_blocks = blocks[bibliography_index + 1:] if bibliography_index is not None else []
    body = "\n".join(block["text"] for block in body_blocks)
    entries, entry_numbers = [], set()
    for block in bibliography_blocks:
        match = re.match(r"^\s*(?:\[(\d+)\]|(\d+)[.)])\s+", block["text"])
        if match:
            entries.append(block)
            entry_numbers.add(int(match.group(1) or match.group(2)))
        elif len(block["text"]) >= 20:
            entries.append(block)
    citations = {int(value) for value in re.findall(r"\[(\d{1,4})\]", body)}
    author_year = re.findall(r"\([A-ZА-ЯЁ][^()]{1,80},\s*(?:19|20)\d{2}[a-zа-я]?\)", body)
    headings = [block for block in blocks if len(block["text"]) < 180 and (
        block["text"].isupper() or re.match(r"^\d+(?:\.\d+)*\s+", block["text"])
        or re.match(r"^(введение|заключение|выводы|приложение|глава|раздел)\b", block["text"], re.I)
    )]
    joined = "\n".join(block["text"] for block in blocks)

    def objects(pattern):
        return [block for block in blocks if re.search(pattern, block["text"], re.I)]

    tables = objects(r"\bтаблиц[аы]?\s*\d*")
    figures = objects(r"\b(?:рисунок|рис\.)\s*\d*")
    formulas = objects(r"\bформул[аы]?\b|\([0-9]+\)\s*$")
    applications = objects(r"^\s*приложение\s+[А-ЯA-Z0-9]+")
    return {
        "bibliography_found": bibliography_index is not None,
        "bibliography_entries": entries,
        "entry_count": len(entries), "entry_numbers": sorted(entry_numbers),
        "citations": sorted(citations), "author_year_citation_count": len(author_year),
        "missing_references": sorted(citations - entry_numbers) if entry_numbers else sorted(citations),
        "unused_references": sorted(entry_numbers - citations),
        "headings": headings, "section_candidates": headings,
        "tables": tables, "figures": figures, "formulas": formulas, "applications": applications,
        "captions_and_identifiers": tables + figures + applications,
        "extraction_diagnostics": {"chars": len(str(payload.get("full_text") or joined)), "blocks": len(blocks),
                                   "pages": len(payload.get("pages") or []), "has_text": bool(joined.strip())},
        "searched_locations": [block["location"] for block in blocks[:200]],
        "blocks": blocks,
    }
