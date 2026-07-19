"""End-to-end UI probe via Streamlit's AppTest: boots the real app, fires the
pipeline in both runtimes, and asserts the Phase 2 surfaces render without
exceptions. Slower than the unit tests (~30-60s); skip with:
    pytest -q -k "not app_ui"
Troubleshooting: if this segfaults on rerun, it's a pyarrow build issue in
your environment - `pip install pyarrow==17.0.0` fixes it."""
import os
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _fresh():
    os.environ.pop("SOUS_AGENT_RUNTIME", None)
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _fire(at, agents: bool):
    for t in at.toggle:
        t.set_value(agents)          # curated demo ON + runtime toggle together
    next(b for b in at.button if "Fire" in b.label).click()
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_app_ui_boot_clean():
    _fresh()


def test_app_ui_legacy_fire():
    at = _fire(_fresh(), agents=False)
    md_text = " ".join(str(m.value) for m in at.markdown).lower()
    assert "specials on the rail" in md_text
    # agents-only surfaces stay hidden (no control-room section, no tabs)
    assert "negotiation, trace & oversight" not in md_text
    assert len(at.tabs) == 0


def test_app_ui_agents_fire_renders_control_room():
    at = _fire(_fresh(), agents=True)
    md_text = " ".join(str(m.value) for m in at.markdown).lower()
    for needle in ("control room", "round 1", "margin risk", "converged",
                   "ing-badge"):        # recipe-card ingredient tags rendered
        assert needle in md_text, f"missing UI element: {needle}"
    assert len(at.tabs) >= 3                  # negotiation / timeline / ledger
