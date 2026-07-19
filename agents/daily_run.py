"""Scheduled autonomous run: the digital-teammate morning draft.

    python -m agents.daily_run

Runs the full agents pipeline against the current price feed and saves the
draft board + purchase order + trace as JSON. The app picks the draft up on
boot ("prepared at 06:00 - awaiting your approval"). Nothing is ordered,
sent, or approved here - the human gate stays in the UI.

Local:   writes drafts/latest.json (+ a dated copy).
Cloud:   set SOUS_DRAFTS_URI=gs://bucket/path to also archive to Cloud Storage
         (wire this entrypoint to Cloud Scheduler -> Cloud Run job in Phase 2
         deploy; NOT part of the Phase 1 service).
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sous_core as sc  # noqa: E402
from agents.orchestrator import run_agents_pipeline  # noqa: E402

DRAFT_DIR = os.environ.get("SOUS_DRAFT_DIR", "drafts")


def main():
    inventory = sc.DEFAULT_INVENTORY
    result = run_agents_pipeline(inventory, force_demo=os.environ.get("SOUS_DRAFT_DEMO") == "1")
    now = datetime.datetime.now()
    draft = {
        "prepared_at": now.isoformat(timespec="seconds"),
        "result": result,
    }
    os.makedirs(DRAFT_DIR, exist_ok=True)
    body = json.dumps(draft, default=str, indent=2)
    latest = os.path.join(DRAFT_DIR, "latest.json")
    dated = os.path.join(DRAFT_DIR, f"draft_{now.date().isoformat()}.json")
    for path in (latest, dated):
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
    print(f"[daily_run] draft saved: {latest} "
          f"({len(result['chosen'])} specials, PO Rs {result['po']['total_inr']}, "
          f"{len(result['trace'])} trace events)")

    uri = (os.environ.get("SOUS_DRAFTS_URI") or "").strip()
    if uri.startswith("gs://"):
        try:
            from google.cloud import storage
            bucket_name, prefix = uri[5:].split("/", 1)
            blob = storage.Client(project=sc.PROJECT_ID).bucket(bucket_name).blob(
                f"{prefix.rstrip('/')}/draft_{now.date().isoformat()}.json")
            blob.upload_from_string(body, content_type="application/json")
            print(f"[daily_run] archived to {uri}")
        except Exception as e:
            print(f"[daily_run] GCS archive skipped ({type(e).__name__}: {e})")


if __name__ == "__main__":
    main()
