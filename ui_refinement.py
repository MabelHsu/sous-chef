"""Phase 2 visual refinement layered over the original guest-check theme."""

CSS = r"""
<style>
/* Keep the character; reduce the ceremony before the chef can act. */
.block-container {
  max-width: 1320px;
  padding-top: 0.7rem;
  padding-bottom: 2.5rem;
}

.guest-check {
  padding: 0.65rem 0.85rem 0.75rem;
  margin-bottom: 0.65rem;
  box-shadow: 5px 5px 0 var(--navy);
}

.brand-lockup {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 0.7rem;
  padding-bottom: 0.35rem;
}

.brand-name { font-size: 2.85rem; line-height: 0.9; }
.brand-sub { font-size: 0.68rem; }
.count-line { font-size: 0.68rem; }

.check-meta { margin-top: 0.35rem; }
.meta-box { min-height: 46px; padding: 0.32rem 0.55rem; }
.meta-label { font-size: 0.6rem; }
.meta-value { font-size: 0.98rem; margin-top: 0.08rem; }
.meta-value.mono { font-size: 0.86rem; padding-top: 0.12rem; }

.service-grid {
  grid-template-columns: minmax(0, 1fr) 180px;
  gap: 0.7rem;
  padding-top: 0.65rem;
}
.service-copy h1 { font-size: clamp(1.8rem, 3vw, 2.5rem); }
.service-copy p {
  font-size: 0.9rem;
  line-height: 1.42;
  margin-top: 0.45rem;
  max-width: 780px;
}
.can-sketch { min-height: 112px; padding-left: 0.6rem; }
.tomato-can {
  width: 128px;
  height: 96px;
  border-width: 3px;
  border-radius: 18px / 11px;
  box-shadow: 5px 5px 0 rgba(26, 54, 93, 0.18);
}
.tomato-can:before, .tomato-can:after {
  left: 10px;
  right: 10px;
  height: 20px;
  border-width: 2px;
}
.tomato-can:before { top: -12px; }
.tomato-can:after { bottom: -12px; }
.tomato-label {
  left: 8px;
  right: 8px;
  top: 21px;
  padding: 0.22rem 0.15rem;
  border-width: 2px 0;
  font-size: 0.66rem;
}
.tomatoes { left: 22px; right: 22px; bottom: 12px; }
.tomato { width: 15px; height: 25px; border-width: 1.5px; }

.section-label { margin-top: 0.85rem; margin-bottom: 0.5rem; }
.section-num { width: 24px; height: 24px; box-shadow: 2px 2px 0 var(--navy); }

/* The walk-in remains a tool, but no longer owns one third of the viewport. */
[data-testid="stSidebar"],
[data-testid="stSidebarContent"] {
  min-width: min(21rem, 92vw) !important;
  width: min(21rem, 92vw) !important;
}
[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"] {
  display: flex !important;
  visibility: visible !important;
  pointer-events: auto !important;
}
/* Keep only the sidebar handle from Streamlit's chrome. The inventory starts
   folded, so this control must remain reachable after the header is cleaned. */
[data-testid="stHeader"] {
  display: block !important;
  visibility: visible !important;
  height: 3rem !important;
  min-height: 3rem !important;
  background: transparent !important;
}
[data-testid="stHeader"] [data-testid="stToolbar"] {
  display: flex !important;
  visibility: visible !important;
  height: 3rem !important;
  min-height: 3rem !important;
  overflow: visible !important;
}
[data-testid="stExpandSidebarButton"] {
  position: fixed !important;
  top: 0.55rem !important;
  left: 0.55rem !important;
  z-index: 1000000 !important;
  width: 2.15rem !important;
  height: 2.15rem !important;
  border: 2px solid var(--navy) !important;
  background: var(--paper) !important;
  color: var(--navy) !important;
  box-shadow: 2px 2px 0 var(--navy) !important;
}
.station-rack { transform: none; margin-bottom: 0.75rem; box-shadow: 5px 6px 0 rgba(26, 54, 93, 0.3); }
.rack-card { margin-top: 0.4rem; padding: 0.32rem 0.45rem; font-size: 0.76rem; }

.setup-grid, .source-policy, .recipe-quality {
  display: grid;
  gap: 0.55rem;
}
.source-policy {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0.35rem 0 0.7rem;
}
.source-tier {
  position: relative;
  border: 2px solid var(--ink);
  background: rgba(229, 229, 229, 0.74);
  padding: 0.55rem 0.65rem 0.52rem;
  min-height: 82px;
}
.source-tier.primary { border-color: var(--teal); box-shadow: 3px 3px 0 rgba(0, 90, 91, 0.2); }
.source-tier.fallback { border-style: dashed; }
.tier-n { color: var(--orange); font-size: 0.6rem; font-weight: 900; text-transform: uppercase; }
.tier-title { color: var(--navy); font-size: 0.82rem; font-weight: 900; text-transform: uppercase; margin-top: 0.1rem; }
.tier-copy { color: var(--ink-soft); font-size: 0.72rem; line-height: 1.28; margin-top: 0.16rem; }
.run-help { color: var(--ink-soft); font-size: 0.78rem; margin: -0.15rem 0 0.4rem; }

.recipe-quality {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin: 0.45rem 0 0.8rem;
}
.quality-cell {
  border: 2px solid var(--ink);
  background: var(--card);
  padding: 0.45rem 0.55rem;
}
.quality-n { color: var(--navy); font: 900 1.35rem/1 var(--display-font); }
.quality-l { color: var(--ink-soft); font-size: 0.65rem; font-weight: 800; text-transform: uppercase; margin-top: 0.18rem; }
.quality-cell.good { border-color: var(--teal); }
.quality-cell.warn { border-color: var(--orange); }

.recipe-source-badge {
  display: inline-block;
  border: 1.5px solid var(--teal);
  color: var(--teal);
  padding: 0.04rem 0.3rem;
  margin-left: 0.35rem;
  font-size: 0.58rem;
  font-weight: 900;
  text-transform: uppercase;
  vertical-align: middle;
}
.recipe-source-badge.search { border-color: var(--orange); color: var(--orange); }
.recipe-source-badge.missing { border-color: var(--danger); color: var(--danger); }
.method-empty {
  margin-top: 0.28rem;
  border-left: 4px solid var(--orange);
  background: rgba(204, 85, 0, 0.08);
  padding: 0.42rem 0.5rem;
  color: var(--ink-soft);
  font-size: 0.78rem;
  line-height: 1.35;
}
.recipe-links { margin-top: 0.4rem; font-size: 0.7rem; }
.recipe-links a { color: var(--teal) !important; font-weight: 800; }

@media (max-width: 900px) {
  .brand-lockup { flex-wrap: wrap; gap: 0.25rem 0.55rem; }
  .service-grid, .source-policy, .recipe-quality { grid-template-columns: 1fr; }
  .can-sketch { display: none; }
  [data-testid="stSidebar"], [data-testid="stSidebarContent"] { width: min(19rem, 92vw) !important; }
}
[data-testid="stSidebar"][aria-expanded="false"] {
  min-width: 0 !important;
  width: 0 !important;
  border-right: 0 !important;
  overflow: hidden !important;
}
[data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarContent"] {
  min-width: 0 !important;
  width: 0 !important;
}
</style>
"""
