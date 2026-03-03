#!/usr/bin/env python3
import argparse
import re
import sys
import time
from pathlib import Path

import httpx


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _poll_job(client: httpx.Client, base_url: str, job_id: str, timeout_s: int = 900) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"{base_url}/jobs/{job_id}")
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status == "done":
            return payload
        if status == "failed":
            raise RuntimeError(f"Job {job_id} failed: {payload.get('error_message')}")
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


def _upload_document(client: httpx.Client, base_url: str, pdf_path: Path) -> dict:
    with pdf_path.open("rb") as pdf_file:
        resp = client.post(
            f"{base_url}/documents",
            files={"file": (pdf_path.name, pdf_file, "application/pdf")},
        )
    resp.raise_for_status()
    return resp.json()


def _ask_and_assert(
    client: httpx.Client,
    base_url: str,
    doc_id: str,
    total_pages: int,
    question: str,
    expected_patterns: list[str],
    should_be_found: bool,
) -> None:
    resp = client.post(
        f"{base_url}/ask",
        json={"question": question, "doc_ids": [doc_id]},
    )
    resp.raise_for_status()
    payload = resp.json()
    answer = (payload.get("answer") or "").strip()
    citations = payload.get("citations") or []

    print(f"Q: {question}")
    print(f"A: {answer}")
    print(f"Citations: {[citation.get('chunk_id') for citation in citations]}")

    _assert(citations, f"Expected citations for question: {question}")
    for citation in citations:
        page_start = citation.get("pdf_page_start")
        page_end = citation.get("pdf_page_end")
        _assert(
            isinstance(page_start, int) and isinstance(page_end, int),
            f"Citation pages missing for question: {question}",
        )
        _assert(
            1 <= page_start <= total_pages and 1 <= page_end <= total_pages,
            f"Citation pages out of range for question: {question}",
        )

    if should_be_found:
        lowered = answer.lower()
        _assert(any(re.search(pattern, lowered) for pattern in expected_patterns), f"Answer mismatch for question: {question}")
    else:
        _assert(answer == "Not found in the provided documents.", f"Expected not-found answer for question: {question}")


TEST_CASES = [
    {
        "question": "What does OVG stand for in Directive 060?",
        "patterns": [r"overall\s+vent\s+gas"],
        "found": True,
    },
    {
        "question": "What does DVG stand for in Directive 060?",
        "patterns": [r"defined\s+vent\s+gas"],
        "found": True,
    },
    {
        "question": "What does OGCA stand for in Directive 060?",
        "patterns": [r"oil\s+and\s+gas\s+conservation\s+act"],
        "found": True,
    },
    {
        "question": "What is the OVG monthly limit at a site?",
        "patterns": [r"15(\.0)?\s*10\s*3", r"15,?000", r"per\s+month"],
        "found": True,
    },
    {
        "question": "In section 8.7, what total gas volume and duration limits apply to temporary short-term venting?",
        "patterns": [r"2(\.0)?\s*10\s*3", r"24\s*hours"],
        "found": True,
    },
    {
        "question": "What true vapour pressure limit applies to hydrocarbons stored in atmospheric tanks vented to atmosphere?",
        "patterns": [r"83\s*(kpa|kilopascals)", r"21\.1"],
        "found": True,
    },
    {
        "question": "At what H2S concentration is a permit required for sour gas flaring or incineration?",
        "patterns": [r"50\s*mol/kmol", r"5\s*per\s*cent", r"5%"],
        "found": True,
    },
    {
        "question": "Which section defines the Overall Vent Gas limit?",
        "patterns": [r"section\s+8\.3"],
        "found": True,
    },
    {
        "question": "Where are terms relevant to this directive defined?",
        "patterns": [r"appendix\s+1"],
        "found": True,
    },
    {
        "question": "What directive is referenced for inventory requirements for active glycol dehydrators?",
        "patterns": [r"directive\s+039"],
        "found": True,
    },
    {
        "question": "What does XYZG stand for in Directive 060?",
        "patterns": [],
        "found": False,
    },
]


def main() -> int:
    parser = argparse.ArgumentParser(description="PaperBridge RAG verification runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--pdf", required=True, help="Path to Directive060.pdf")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    _assert(pdf_path.exists(), f"PDF not found: {pdf_path}")

    with httpx.Client(timeout=180) as client:
        first_upload = _upload_document(client, args.base_url, pdf_path)
        second_upload = _upload_document(client, args.base_url, pdf_path)
        _assert(first_upload["id"] == second_upload["id"], "Expected re-upload to return the same deduped document ID")

        doc_id = first_upload["id"]
        total_pages = int(first_upload["total_pages"])
        pipeline_job_id = first_upload.get("pipeline_job_id")
        _assert(pipeline_job_id, "Upload response missing pipeline_job_id")

        print(f"Using document_id={doc_id} version={first_upload['version']} total_pages={total_pages}")
        _poll_job(client, args.base_url, pipeline_job_id)
        print(f"Pipeline complete: job_id={pipeline_job_id}")

        for case in TEST_CASES:
            _ask_and_assert(
                client=client,
                base_url=args.base_url,
                doc_id=doc_id,
                total_pages=total_pages,
                question=case["question"],
                expected_patterns=case["patterns"],
                should_be_found=case["found"],
            )

    print("Verification passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
