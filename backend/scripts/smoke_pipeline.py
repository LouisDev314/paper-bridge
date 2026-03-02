import argparse
import time
from pathlib import Path

import httpx


def _poll_job(
    client: httpx.Client,
    base_url: str,
    job_id: str,
    timeout_seconds: int = 900,
    poll_interval_seconds: float = 2.0,
) -> dict:
    start = time.monotonic()
    while True:
        resp = client.get(f"{base_url}/jobs/{job_id}")
        resp.raise_for_status()
        payload = resp.json()
        status = str(payload.get("status"))
        print(f"job_id={job_id} status={status}")
        if status not in {"queued", "processing"}:
            return payload
        if time.monotonic() - start > timeout_seconds:
            raise TimeoutError(f"Timed out waiting for job {job_id}")
        time.sleep(poll_interval_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test upload + optional auto pipeline orchestration.")
    parser.add_argument("--file", required=True, help="Path to a PDF file")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--auto-process", action="store_true", help="Queue extract+embed pipeline automatically")
    parser.add_argument("--dedupe", action="store_true", default=True, help="Enable checksum dedupe")
    parser.add_argument("--no-dedupe", action="store_false", dest="dedupe", help="Disable checksum dedupe")
    args = parser.parse_args()

    pdf_path = Path(args.file).expanduser().resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    base_url = args.base_url.rstrip("/")

    with httpx.Client(timeout=120.0) as client:
        with pdf_path.open("rb") as fd:
            upload_resp = client.post(
                f"{base_url}/documents",
                params={
                    "dedupe": str(args.dedupe).lower(),
                    "auto_process": str(args.auto_process).lower(),
                },
                files={"file": (pdf_path.name, fd, "application/pdf")},
            )
        upload_resp.raise_for_status()
        upload_payload = upload_resp.json()
        document_id = upload_payload["id"]
        pipeline_job_id = upload_payload.get("pipeline_job_id")
        print(f"document_id={document_id}")
        print(f"pipeline_job_id={pipeline_job_id}")

        if args.auto_process and pipeline_job_id:
            final = _poll_job(client, base_url, pipeline_job_id)
            print(f"pipeline_final_status={final.get('status')}")
            if final.get("status") != "done":
                raise RuntimeError(f"Pipeline failed: {final.get('error_message')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
