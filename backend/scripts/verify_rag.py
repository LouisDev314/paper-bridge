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


def _poll_job(client: httpx.Client, base_url: str, job_id: str, timeout_s: int = 600) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"{base_url}/jobs/{job_id}")
        resp.raise_for_status()
        payload = resp.json()
        status = payload.get("status")
        if status in {"done", "needs_review"}:
            return payload
        if status == "failed":
            raise RuntimeError(f"Job {job_id} failed: {payload.get('error_message')}")
        time.sleep(2)
    raise TimeoutError(f"Timed out waiting for job {job_id}")


def _upload_document(client: httpx.Client, base_url: str, pdf_path: Path, dedupe: bool = True) -> dict:
    with pdf_path.open("rb") as f:
        resp = client.post(
            f"{base_url}/documents",
            params={"dedupe": str(dedupe).lower()},
            files={"file": (pdf_path.name, f, "application/pdf")},
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
        json={"question": question, "doc_ids": [doc_id], "top_k": 8},
    )
    resp.raise_for_status()
    payload = resp.json()
    answer = (payload.get("answer") or "").strip()
    citations = payload.get("citations") or []

    print(f"Q: {question}")
    print(f"A: {answer}")
    print(f"Citations: {[c.get('chunk_id') for c in citations]}")

    _assert(citations, f"Expected citations for question: {question}")
    for citation in citations:
        ps = citation.get("pdf_page_start")
        pe = citation.get("pdf_page_end")
        _assert(isinstance(ps, int) and isinstance(pe, int), f"Citation pages missing for question: {question}")
        _assert(1 <= ps <= total_pages and 1 <= pe <= total_pages, f"Citation pages out of range for question: {question}")

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
        doc_a = _upload_document(client, args.base_url, pdf_path, dedupe=True)
        doc_b = _upload_document(client, args.base_url, pdf_path, dedupe=True)
        _assert(doc_a["id"] == doc_b["id"], "Expected dedupe=true re-upload to return the same document ID")

        doc_new_version = _upload_document(client, args.base_url, pdf_path, dedupe=False)
        _assert(doc_new_version["id"] != doc_a["id"], "Expected dedupe=false re-upload to create a new document")
        _assert(doc_new_version["version"] > doc_a["version"], "Expected version increment on dedupe=false upload")

        doc_id = doc_new_version["id"]
        total_pages = int(doc_new_version["total_pages"])
        print(f"Using document_id={doc_id} version={doc_new_version['version']} total_pages={total_pages}")

        embed_resp = client.post(f"{args.base_url}/documents/{doc_id}/embed")
        embed_resp.raise_for_status()
        embed_job = embed_resp.json()["id"]
        _poll_job(client, args.base_url, embed_job)
        print(f"Embedding complete: job_id={embed_job}")

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
