#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib import request


BASE_URL = os.getenv("MIRCLASS_BASE_URL", "http://localhost:8080")


def post_json(path: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        BASE_URL + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path: str) -> dict:
    with request.urlopen(BASE_URL + path, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def upload_demo_document() -> dict:
    path = Path("demo/sample-document.docx")
    boundary = "----mirclass-startup-vkr-e2e"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="upload"; filename="startup-vkr-demo.docx"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document\r\n\r\n"
    ).encode("utf-8") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = request.Request(
        BASE_URL + "/api/v1/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def db_json(sql: str):
    completed = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "digital_mentor", "-d", "digital_mentor", "-t", "-A", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout.strip() or "[]")


def main() -> int:
    ready = get_json("/health/ready")
    print(f"analysis_engine={ready.get('analysis_engine')}")
    if ready.get("analysis_engine") != "startup_vkr_agents":
        print("ERROR: set ANALYSIS_ENGINE=startup_vkr_agents and recreate backend before running this smoke test.")
        return 2

    document = upload_demo_document()
    print(f"document_id={document['id']}")
    analysis = post_json(
        "/api/v1/analyses",
        {
            "document_id": document["id"],
            "analysis_type": "mentor",
            "methodology_id": "STARTUP_VKR",
            "methodology_version": "1.0",
        },
    )
    analysis_id = analysis["analysis_id"]
    print(f"analysis_id={analysis_id}")

    status = {}
    started = time.monotonic()
    for _ in range(180):
        status = get_json(f"/api/v1/analyses/{analysis_id}")
        if status["status"] in {"completed", "failed", "cancelled"}:
            break
        time.sleep(2)
    elapsed = time.monotonic() - started
    print(f"analysis_status={status.get('status')} elapsed_seconds={elapsed:.1f}")
    if status.get("status") != "completed":
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 1

    result = get_json(f"/api/v1/analyses/{analysis_id}/result")
    report = post_json(f"/api/v1/analyses/{analysis_id}/reports", {})
    chat = post_json("/api/v1/chat/messages", {"analysis_id": analysis_id, "message": "Что исправить в первую очередь?"})
    extra = result.get("extra_blocks") or {}
    assessment_id = extra.get("assessment_id")

    model_rows = db_json(
        "select json_agg(row_to_json(t)) from ("
        "select requested_model, count(*) as calls, sum(total_tokens) as tokens, sum(cost_rub) as cost_rub "
        f"from llm_calls where analysis_id = '{analysis_id}' group by requested_model order by requested_model"
        ") t;"
    )
    total_rows = db_json(
        "select json_agg(row_to_json(t)) from ("
        "select sum(total_tokens) as tokens, sum(cost_rub) as cost_rub from llm_calls "
        f"where analysis_id = '{analysis_id}'"
        ") t;"
    )
    evidence_count = sum(len(item.get("evidence") or []) for item in result.get("remarks", [])) + len(result.get("evidence") or [])
    print(json.dumps({
        "assessment_id": assessment_id,
        "models": model_rows,
        "total": total_rows[0] if total_rows else {},
        "overall_status": extra.get("status"),
        "evidence_count": evidence_count,
        "recommendations_count": len(result.get("recommendations") or []),
        "report_url": report.get("report_url"),
        "chat_answer_preview": chat.get("answer", "")[:300],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
