"""Render an exported run trace as a readable transcript.

    python scripts/replay_trace.py drafts/latest.json
    python scripts/replay_trace.py trace_export.json

Accepts either a raw trace export ({"run_id":..., "events":[...]}), a draft
file from agents/daily_run.py, or a full result dict with a "trace" key.
Also the fixture renderer for the golden-trace tests (timestamps/latency are
ignored there, content is compared).
"""
import json
import sys


def load_events(path: str):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        if "events" in data:
            return data["events"]
        if "trace" in data:
            return data["trace"]
        if "result" in data and isinstance(data["result"], dict):
            return data["result"].get("trace", [])
    raise SystemExit("no trace events found in file")


def transcript(events, include_timing=True) -> str:
    lines = []
    current_round = None
    for e in events:
        if e.get("round") != current_round:
            current_round = e.get("round")
            label = {0: "PLAN", 1: "ROUND 1 - proposals & assessments",
                     2: "ROUND 2 - draft & pushback",
                     3: "ROUND 3 - resolution & oversight"}.get(current_round,
                                                                f"ROUND {current_round}")
            lines.append(f"\n=== {label} ===")
        p = e.get("payload") or {}
        detail = (p.get("reason") or p.get("text")
                  or ", ".join(f"{k}={v}" for k, v in p.items() if k != "evidence"))
        timing = ""
        if include_timing and e.get("latency_ms"):
            timing = f"  ({e['latency_ms']} ms)"
        model = f" [{e['model']}]" if e.get("model") not in (None, "deterministic") else ""
        lines.append(f"{e.get('agent', '?'):>12} | {e.get('action', '?'):<20}"
                     f"{model} {detail}{timing}")
    return "\n".join(lines).strip()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    print(transcript(load_events(sys.argv[1])))
