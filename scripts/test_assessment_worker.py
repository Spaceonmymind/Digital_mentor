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
    with request.urlopen(req, timeout=300) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path: str) -> dict | list:
    with request.urlopen(BASE_URL + path, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def upload_demo_document() -> dict:
    path = Path("demo/sample-document.docx")
    boundary = "----mirclass-smoke-boundary"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="upload"; filename="sample-document.docx"\r\n'
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


def llm_call_metrics(llm_call_ids: list[str]) -> dict[str, dict]:
    if not llm_call_ids:
        return {}
    ids = ",".join(f"'{item}'" for item in llm_call_ids)
    sql = (
        "select json_agg(row_to_json(t)) from ("
        "select id,total_tokens,cost_rub,provider,latency_ms from llm_calls "
        f"where id in ({ids}) order by created_at"
        ") t;"
    )
    completed = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "digital_mentor", "-d", "digital_mentor", "-t", "-A", "-c", sql],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(completed.stdout.strip() or "[]")
    return {row["id"]: row for row in rows}


def main() -> int:
    if not os.getenv("POLZA_API_KEY"):
        print("POLZA_API_KEY is not set in the current shell. Docker may still use .env, but the script will not print it.")
    document = upload_demo_document()
    print(f"document_id={document['id']}")

    pipeline = post_json(
        "/api/v1/internal/pipeline/build",
        {"artifact_type": "UNIVERSAL_DOCUMENT", "artifact_id": document["id"]},
    )
    print(f"assessment_id={pipeline['assessment_id']} tasks_count={pipeline['tasks_count']}")

    execution = post_json(f"/api/v1/internal/assessments/{pipeline['assessment_id']}/execute", {})
    print(json.dumps(execution, ensure_ascii=False, indent=2))

    for _ in range(3):
        status = get_json(f"/api/v1/internal/assessments/{pipeline['assessment_id']}/execution")
        if status["status"] in {"completed", "failed"}:
            break
        time.sleep(1)

    results = get_json(f"/api/v1/internal/assessments/{pipeline['assessment_id']}/indicator-results")
    metrics = llm_call_metrics([item["llm_call_id"] for item in results if item.get("llm_call_id")])
    total_cost = 0.0
    for item in results:
        metric = metrics.get(item.get("llm_call_id"), {})
        cost = float(metric.get("cost_rub") or 0)
        total_cost += cost
        print(
            json.dumps(
                {
                    "status": item["status"],
                    "score": str(item["score"]),
                    "summary": item["summary"],
                    "evidence_count": len(item["evidence_json"]),
                    "recommendations": item["recommendations_json"],
                    "tokens": metric.get("total_tokens"),
                    "cost_rub": metric.get("cost_rub"),
                    "provider": metric.get("provider"),
                    "latency_ms": metric.get("latency_ms"),
                },
                ensure_ascii=False,
            )
        )
    print(f"total_cost_rub={total_cost:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
