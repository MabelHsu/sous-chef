"""Sous Phase 2 agent layer.

A primary Coordinator plans, delegates to specialist agents (Menu, Price,
Nutrition, Margin), brokers a bounded negotiation (max 3 rounds), and
converges on the board - with every turn recorded as a TraceEvent.

Design rules:
  - All numbers come from the tool layer (sous_core.py + forecast.py).
    Gemini narrates and argues; it never computes.
  - The Margin agent's veto is HARD: only a logged human decision can
    override it (constraint-relaxation card in the UI).
  - Any LLM failure degrades to a deterministic stand-in. A run always
    completes - offline, keyless, or mid-outage.

Opt in with SOUS_AGENT_RUNTIME=agents (default is the Phase 1 legacy path).
"""
