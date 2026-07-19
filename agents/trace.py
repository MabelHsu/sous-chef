"""Append-only trace of every agent turn - the observability spine.
Events are plain dicts (JSON-serializable) so the whole trace survives
st.session_state, file export, and the scheduled-run archive unchanged."""
import json
import time
import uuid

ACTIONS = {"plan", "propose", "assess", "veto", "draft", "counter", "accept_counter",
           "hold", "replan", "converge", "guardrail_fired", "degrade",
           "approve", "refuse", "override", "complete", "relaxation_requested"}

HUMAN_ACTIONS = {"approve", "refuse", "override"}
LEDGER_ACTIONS = {"veto", "guardrail_fired", "approve", "refuse", "override",
                  "relaxation_requested"}


class Trace:
    def __init__(self, run_id: str = None):
        self.run_id = run_id or uuid.uuid4().hex[:8]
        self.t0 = time.time()
        self.events = []

    def add(self, agent: str, action: str, payload=None, model: str = None,
            round: int = 0, latency_ms: int = None) -> dict:
        event = {
            "ts": round_ms(time.time() - self.t0),
            "run_id": self.run_id,
            "round": round,
            "agent": agent,                      # coordinator|menu|price|nutrition|margin|human|guardrail|system
            "model": model or "deterministic",   # gemini id, or 'deterministic'
            "action": action if action in ACTIONS else "assess",
            "payload": payload if isinstance(payload, dict) else {"text": str(payload or "")},
            "latency_ms": latency_ms,
        }
        self.events.append(event)
        return event

    # ---- views ----
    def ledger(self):
        """Vetoes, guardrails, and human decisions - the oversight record."""
        return [e for e in self.events if e["action"] in LEDGER_ACTIONS]

    def by_round(self, round: int):
        return [e for e in self.events if e["round"] == round]

    def to_dicts(self):
        return list(self.events)

    def to_json(self, **kw) -> str:
        return json.dumps({"run_id": self.run_id, "events": self.events}, indent=2, **kw)


def round_ms(seconds: float) -> float:
    return round(seconds, 3)
