"""Typed message contracts for the agent layer. This file is the spec:
every agent-to-agent message is one of these models, validated on receipt.
Anything that fails validation degrades to a deterministic stand-in."""
import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Proposal(BaseModel):
    """Menu agent -> Coordinator: one candidate dish."""
    model_config = ConfigDict(extra="ignore")
    dish: str
    have: list = Field(default_factory=list)
    need: list = Field(default_factory=list)
    uses_expiring: list = Field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.6


class Assessment(BaseModel):
    """Specialist -> Coordinator: verdict on one dish, citing tool numbers."""
    model_config = ConfigDict(extra="ignore")
    dish: str
    agent: str = ""
    verdict: Literal["approve", "concern", "veto"]
    reason: str = ""
    evidence: dict = Field(default_factory=dict)


class BoardDraft(BaseModel):
    """Coordinator -> specialists: proposed board for a round."""
    model_config = ConfigDict(extra="ignore")
    round: int
    picks: list
    open_questions: list = Field(default_factory=list)


class Resolution(BaseModel):
    """Coordinator, final: the converged board + the negotiation log."""
    model_config = ConfigDict(extra="ignore")
    picks: list
    negotiation_log: list = Field(default_factory=list)
    confidence: float = 0.7


class RelaxationRequest(BaseModel):
    """Coordinator -> human: permission to exceed the food-cost target.
    The system NEVER relaxes a constraint on its own."""
    model_config = ConfigDict(extra="ignore")
    dish: str
    food_cost_pct: int
    target_pct: int
    reason: str = ""


# --------------------------------------------------------------------------
# Parsing helpers: extract strict JSON from LLM prose, tolerantly.
# --------------------------------------------------------------------------
_FENCE = re.compile(r"```(?:json)?\s*(.+?)\s*```", re.DOTALL)


def extract_json(text: str):
    """Best-effort: fenced block first, then the outermost [..] or {..}.
    Returns a parsed object or None (caller degrades deterministically)."""
    if not text:
        return None
    candidates = [m.group(1) for m in _FENCE.finditer(text)]
    # Object before array: an LLM reply like {"directions": [...]} must parse as
    # the whole object, not the inner array (which "[" first would grab).
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start, end = text.find(open_c), text.rfind(close_c)
        if start != -1 and end > start:
            candidates.append(text[start:end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except Exception:
            continue
    return None


def parse_picks(text: str, valid_titles) -> Optional[list]:
    """Parse the machine-readable PICKS: [...] line (same seam Phase 1 closed),
    keeping only titles that actually exist. None if unusable."""
    if not text:
        return None
    by_lower = {t.lower(): t for t in valid_titles}
    for line in reversed(text.strip().splitlines()):
        upper = line.upper()
        if "PICKS:" in upper:
            try:
                names = json.loads(line[upper.index("PICKS:") + 6:].strip())
                picked = [by_lower[str(n).lower().strip()] for n in names
                          if str(n).lower().strip() in by_lower]
                return picked or None
            except Exception:
                return None
    return None
