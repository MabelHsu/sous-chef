"""
Sous - Streamlit interface (Phase 2: control room + forecast chips added).
Run locally:   python -m streamlit run app.py
Deploys to Cloud Run as-is. Works with no GCP/Gemini set (demo mode).

The visual system is an original kitchen-service / guest-check treatment:
cream paper, khaki time-cards, a near-black board, red stamps, slab-serif type.
"""
import datetime
import html
import os

import pandas as pd
import streamlit as st

import sous_core as sc
from ui_refinement import CSS as REFINEMENT_CSS
from ui_components import (recipe_source_badge, recipe_source_links,
                           render_recipe_coverage, render_recipe_policy)


st.set_page_config(
    page_title="Sous - every second counts",
    layout="wide",
    initial_sidebar_state="collapsed",
)


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Rokkitt:wght@500;600;700;800;900&display=swap');

:root {
  --paper: #F5F2EB;
  --card: #E5E5E5;
  --khaki: #C2B280;
  --navy: #1A365D;
  --teal: #005A5B;
  --orange: #CC5500;
  --gold: #D4AF37;
  --danger: #C62828;
  --board: #1A1A1A;
  --ink: #1C1A17;
  --ink-soft: rgba(28, 26, 23, 0.72);
  --cream: #F5F2EB;
  --line: rgba(26, 54, 93, 0.32);
  --shadow: rgba(26, 54, 93, 0.22);
  --display-font: "Lubalin Graph", "ITC Lubalin Graph", "Rockwell Extra Bold", "Rockwell", "Rokkitt", Georgia, serif;
  --body-font: "Rockwell", "Rokkitt", Georgia, serif;
  --mono-font: "Courier New", Courier, monospace;
  --action-font-size: 0.86rem;
}

.stApp,
.stApp * {
  letter-spacing: 0 !important;
}

.stApp {
  color: var(--ink);
  background:
    repeating-linear-gradient(0deg, transparent 0, transparent 42px, rgba(26, 54, 93, 0.05) 43px),
    var(--paper);
}

[data-testid="stHeader"] {
  background: transparent !important;
}

[data-testid="stDeployButton"],
[data-testid="stAppDeployButton"],
[data-testid="stMainMenu"] {
  visibility: hidden;
}


.block-container {
  max-width: 1220px;
  padding-top: 1.25rem;
  padding-bottom: 3.5rem;
}

h1, h2, h3, h4, p, li, label, span, div {
  font-family: var(--body-font);
}

.guest-check {
  position: relative;
  overflow: hidden;
  border: 3px solid var(--ink);
  background:
    repeating-linear-gradient(0deg, rgba(26, 54, 93, 0.08) 0 1px, transparent 1px 43px),
    linear-gradient(180deg, var(--card), var(--paper));
  box-shadow: 8px 8px 0 var(--navy);
  padding: 1rem 1.1rem 1.2rem;
  margin-bottom: 1.1rem;
}

.guest-check:before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.3;
  background-image:
    linear-gradient(45deg, rgba(26, 54, 93, 0.07) 25%, transparent 25%),
    linear-gradient(-45deg, rgba(0, 90, 91, 0.06) 25%, transparent 25%);
  background-size: 5px 5px;
}

.guest-check > * {
  position: relative;
}

.brand-lockup {
  text-align: center;
  border-bottom: 4px double var(--navy);
  padding-bottom: 0.65rem;
}

.brand-name {
  color: var(--navy);
  font-family: var(--display-font);
  font-weight: 900;
  font-size: 5.2rem;
  line-height: 0.92;
  text-transform: uppercase;
}

.brand-sub {
  color: var(--teal);
  font-size: 0.86rem;
  font-weight: 800;
  line-height: 1.05;
  text-transform: uppercase;
}

.count-line {
  color: var(--orange);
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 1.2;
  text-transform: lowercase;
}

.check-meta {
  display: grid;
  grid-template-columns: 1fr 1.3fr 0.8fr;
  border-bottom: 3px solid var(--navy);
  margin-top: 0.65rem;
}

.meta-box {
  min-height: 62px;
  border-right: 2px solid var(--navy);
  padding: 0.45rem 0.65rem;
}

.meta-box:last-child {
  border-right: 0;
}

.meta-label {
  color: var(--navy);
  font-size: 0.68rem;
  font-weight: 800;
  text-transform: uppercase;
}

.meta-value {
  margin-top: 0.15rem;
  color: var(--teal);
  font-size: 1.22rem;
  font-weight: 800;
  line-height: 1.12;
}

.meta-value.mono {
  font-family: var(--mono-font);
  font-size: 1.02rem;
  padding-top: 0.3rem;
}

.service-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(270px, 0.8fr);
  gap: 1rem;
  align-items: stretch;
  padding-top: 1rem;
}

.service-copy {
  color: var(--ink);
  max-width: 760px;
}

.service-copy h1 {
  color: var(--navy);
  font-family: var(--display-font);
  font-weight: 900;
  font-size: 2.95rem;
  line-height: 1.02;
  margin: 0;
  text-transform: uppercase;
}

.service-copy p {
  color: var(--ink-soft);
  max-width: 680px;
  margin: 0.75rem 0 0;
  font-size: 1.02rem;
  font-weight: 500;
  line-height: 1.48;
}

.can-sketch {
  align-self: end;
  min-height: 230px;
  border-left: 3px solid var(--navy);
  padding-left: 1rem;
  display: grid;
  place-items: center;
}

.tomato-can {
  width: 220px;
  height: 190px;
  border: 5px solid var(--ink);
  border-radius: 26px / 16px;
  background:
    linear-gradient(90deg, transparent 0 31%, rgba(26, 54, 93, 0.16) 31% 32%, transparent 32% 63%, rgba(26, 54, 93, 0.16) 63% 64%, transparent 64%),
    var(--card);
  position: relative;
  box-shadow: 9px 10px 0 rgba(26, 54, 93, 0.18);
}

.tomato-can:before,
.tomato-can:after {
  content: "";
  position: absolute;
  left: 18px;
  right: 18px;
  height: 38px;
  border: 4px solid var(--ink);
  border-radius: 50%;
  background: var(--paper);
}

.tomato-can:before {
  top: -23px;
}

.tomato-can:after {
  bottom: -23px;
}

.tomato-label {
  position: absolute;
  left: 15px;
  right: 15px;
  top: 48px;
  z-index: 2;
  background: rgba(245, 242, 235, 0.92);
  border-top: 3px solid var(--navy);
  border-bottom: 3px solid var(--navy);
  padding: 0.42rem 0.25rem;
  color: var(--teal);
  font-size: 1.02rem;
  font-weight: 800;
  line-height: 1.16;
  text-align: center;
  transform: rotate(-2deg);
}

.tomatoes {
  position: absolute;
  bottom: 26px;
  left: 38px;
  right: 38px;
  display: flex;
  justify-content: space-between;
}

.tomato {
  width: 29px;
  height: 50px;
  border-radius: 47% 53% 45% 55%;
  background: var(--orange);
  border: 2px solid var(--danger);
}

.section-label {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  color: var(--navy);
  font-size: 0.76rem;
  font-weight: 800;
  line-height: 1.2;
  margin: 1.15rem 0 0.65rem;
  text-transform: uppercase;
}

.section-label:after {
  content: "";
  height: 2px;
  flex: 1;
  background: var(--navy);
  opacity: 0.4;
}

.section-num {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border: 2px solid var(--ink);
  background: var(--card);
  color: var(--orange);
  box-shadow: 3px 3px 0 var(--navy);
}

.brief-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  border: 3px solid var(--ink);
  background: var(--card);
  box-shadow: 6px 6px 0 var(--shadow);
}

.brief-cell {
  padding: 0.8rem 0.9rem;
  border-right: 2px solid var(--ink);
  min-height: 118px;
}

.brief-cell:last-child {
  border-right: 0;
}

.brief-kicker {
  color: var(--orange);
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
}

.brief-title {
  color: var(--navy);
  margin-top: 0.2rem;
  font-size: 1.05rem;
  font-weight: 800;
  text-transform: uppercase;
}

.brief-body {
  color: var(--ink-soft);
  margin-top: 0.35rem;
  font-size: 0.9rem;
  line-height: 1.38;
}

.station-rack {
  position: relative;
  border: 3px solid var(--board);
  background:
    radial-gradient(circle at 18px 18px, rgba(212, 175, 55, 0.35) 0 3px, rgba(212, 175, 55, 0.1) 4px 6px, transparent 7px),
    radial-gradient(circle at calc(100% - 22px) 20px, rgba(194, 178, 128, 0.32) 0 3px, rgba(194, 178, 128, 0.1) 4px 6px, transparent 7px),
    repeating-linear-gradient(0deg, #1A1A1A 0 52px, #1C1A17 52px 58px),
    var(--board);
  padding: 1rem 0.85rem 0.9rem;
  box-shadow: inset 0 0 0 2px rgba(245, 242, 235, 0.09), 8px 10px 0 rgba(26, 54, 93, 0.3);
  color: var(--khaki);
  transform: rotate(-1.2deg);
  transform-origin: 48% 8%;
  margin: 0.25rem 0 1.1rem;
}

.rack-title {
  color: var(--cream);
  font-size: 0.78rem;
  font-weight: 800;
  line-height: 1.15;
  text-transform: uppercase;
}

.rack-card {
  margin-top: 0.55rem;
  background: var(--khaki);
  color: var(--ink);
  border: 1px solid rgba(26, 54, 93, 0.38);
  border-left: 4px solid var(--orange);
  padding: 0.42rem 0.55rem;
  font-size: 0.84rem;
  font-weight: 800;
  line-height: 1.25;
}

.status-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 0.45rem;
  border: 2px solid var(--ink);
  border-radius: 50%;
  background: var(--khaki);
}

.status-dot.on {
  background: var(--teal);
}

.status-stack {
  display: grid;
  gap: 0.18rem;
  margin-top: -0.15rem;
  margin-bottom: 0.35rem;
}

.status-line {
  display: flex;
  align-items: center;
  color: var(--ink);
  font-size: 0.76rem;
  font-weight: 600;
  line-height: 1.22;
}

.status-line .status-dot {
  flex: 0 0 auto;
  width: 7px;
  height: 7px;
  border-width: 1.5px;
  margin-right: 0.38rem;
}

.call-ticket {
  border: 3px solid var(--ink);
  background: var(--card);
  box-shadow: 6px 6px 0 var(--navy);
  padding: 1rem;
  color: var(--ink-soft);
}

.call-ticket strong {
  color: var(--navy);
}

.alert-ticket {
  border: 3px solid var(--danger);
  border-left-width: 12px;
  background: rgba(198, 40, 40, 0.1);
  color: var(--ink);
  padding: 0.9rem 1rem;
  box-shadow: 5px 5px 0 rgba(198, 40, 40, 0.22);
}

.alert-ticket .alert-kicker {
  color: var(--danger);
  font-size: 0.74rem;
  font-weight: 800;
  text-transform: uppercase;
}

.decision-strip {
  display: flex;
  align-items: baseline;
  gap: 0.8rem;
  flex-wrap: wrap;
  border: 3px solid var(--ink);
  background: var(--navy);
  color: var(--cream);
  box-shadow: 6px 6px 0 var(--gold);
  padding: 0.6rem 0.9rem;
  margin-bottom: 0.9rem;
}

.ds-k {
  color: var(--gold);
  font-size: 0.72rem;
  font-weight: 800;
  text-transform: uppercase;
}

.ds-b {
  color: var(--cream);
  font-size: 1rem;
  font-weight: 700;
}

.ticket-rail {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.9rem;
  align-items: stretch;
}

.special-ticket {
  min-height: 245px;
  border: 2px solid var(--ink);
  background:
    repeating-linear-gradient(0deg, transparent 0, transparent 31px, rgba(26, 54, 93, 0.12) 32px),
    var(--card);
  box-shadow: 5px 5px 0 var(--navy);
  padding: 0.75rem;
  color: var(--ink);
}

.ticket-top {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.5rem;
  border-bottom: 2px solid var(--ink);
  padding-bottom: 0.45rem;
  color: var(--ink);
  font-size: 0.68rem;
  font-weight: 800;
  text-transform: uppercase;
}

.ticket-dish {
  color: var(--navy);
  min-height: 55px;
  margin-top: 0.75rem;
  font-family: var(--display-font);
  font-weight: 900;
  font-size: 1.45rem;
  line-height: 1.04;
  text-transform: uppercase;
}

.ticket-note {
  color: var(--ink-soft);
  margin-top: 0.6rem;
  font-size: 0.9rem;
  line-height: 1.38;
}

.stamp {
  display: inline-block;
  border: 3px solid var(--orange);
  color: var(--orange);
  margin-top: 0.85rem;
  padding: 0.18rem 0.55rem;
  font-weight: 800;
  transform: rotate(-4deg);
  text-transform: uppercase;
}

.stamp.blue {
  border-color: var(--teal);
  color: var(--teal);
}

.order-sheet {
  border: 3px solid var(--ink);
  background:
    repeating-linear-gradient(0deg, transparent 0, transparent 33px, rgba(26, 54, 93, 0.11) 34px),
    var(--card);
  box-shadow: 7px 7px 0 var(--shadow);
  padding: 1rem;
}

.order-head {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 0.75rem;
  border-bottom: 3px double var(--navy);
  color: var(--ink);
  padding-bottom: 0.55rem;
}

.order-title {
  color: var(--navy);
  font-family: var(--display-font);
  font-size: 1.42rem;
  font-weight: 900;
  line-height: 1.05;
  text-transform: uppercase;
}

.order-sheet table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.65rem;
  color: var(--ink);
  font-size: 0.9rem;
}

.order-sheet th {
  color: var(--ink);
  font-size: 0.68rem;
  text-align: left;
  text-transform: uppercase;
  border-bottom: 2px solid var(--ink);
  padding: 0.28rem 0.35rem;
}

.order-sheet td {
  padding: 0.35rem;
  border-bottom: 1px solid rgba(28, 26, 23, 0.22);
  vertical-align: top;
}

.order-grid {
  display: grid;
  grid-template-columns: minmax(130px, 1.1fr) 86px 96px minmax(180px, 1.45fr) 92px;
  margin-top: 0.65rem;
  border-top: 2px solid var(--ink);
}

.order-cell {
  min-height: 34px;
  border-bottom: 1px solid rgba(28, 26, 23, 0.24);
  padding: 0.35rem;
  color: var(--ink);
  font-size: 0.9rem;
}

.order-head-cell {
  color: var(--ink);
  font-size: 0.68rem;
  font-weight: 800;
  text-transform: uppercase;
  border-bottom: 2px solid var(--ink);
}

.order-empty {
  grid-column: 1 / -1;
}

.num {
  text-align: right;
  white-space: nowrap;
}

.spike {
  color: var(--orange);
  font-weight: 800;
}

.total-row {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  border-top: 3px double var(--navy);
  margin-top: 0.75rem;
  padding-top: 0.55rem;
  color: var(--navy);
  font-size: 1.15rem;
  font-weight: 800;
  text-transform: uppercase;
}

.speed-ticket {
  border: 3px solid var(--ink);
  background: var(--navy);
  color: var(--cream);
  box-shadow: 6px 6px 0 var(--gold);
  padding: 1rem;
}

.speed-kicker {
  color: var(--gold);
  font-size: 0.74rem;
  font-weight: 800;
  text-transform: uppercase;
}

.speed-big {
  color: var(--cream);
  font-family: var(--display-font);
  font-weight: 900;
  font-size: 4rem;
  line-height: 0.95;
}

.speed-note {
  color: rgba(245, 242, 235, 0.86);
  font-size: 0.9rem;
  line-height: 1.38;
}

.footer-line {
  margin-top: 1.5rem;
  border-top: 3px double var(--navy);
  color: var(--ink-soft);
  font-size: 0.72rem;
  font-weight: 500;
  padding-top: 0.55rem;
  text-align: center;
  text-transform: uppercase;
}

.footer-line strong {
  color: var(--orange);
  font-size: var(--action-font-size);
  font-weight: 900;
  line-height: 1.12;
}

.pipeline-strip {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  border: 3px solid var(--ink);
  background: var(--card);
  box-shadow: 6px 6px 0 var(--shadow);
  margin: 0.2rem 0 0.9rem;
}

.pipe-step {
  position: relative;
  padding: 0.55rem 0.7rem;
  border-right: 2px solid var(--ink);
}

.pipe-step:last-child {
  border-right: 0;
}

.pipe-n {
  color: var(--orange);
  font-size: 0.62rem;
  font-weight: 800;
  text-transform: uppercase;
}

.pipe-t {
  color: var(--navy);
  font-size: 0.86rem;
  font-weight: 800;
  text-transform: uppercase;
  line-height: 1.12;
  margin-top: 0.12rem;
}

.pipe-d {
  color: var(--ink-soft);
  font-size: 0.72rem;
  margin-top: 0.18rem;
}

.pipe-arrow {
  position: absolute;
  right: -10px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 3;
  color: var(--orange);
  font-weight: 800;
  background: var(--card);
  border: 2px solid var(--ink);
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  font-size: 0.82rem;
}

.proof-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.6rem;
  margin-bottom: 0.55rem;
}

.proof-stat {
  border: 2px solid var(--ink);
  background: var(--card);
  box-shadow: 4px 4px 0 var(--shadow);
  padding: 0.6rem 0.72rem;
}

.ps-n {
  color: var(--navy);
  font-family: var(--display-font);
  font-weight: 900;
  font-size: 1.62rem;
  line-height: 1;
}

.ps-l {
  color: var(--orange);
  font-size: 0.66rem;
  font-weight: 800;
  text-transform: uppercase;
  margin-top: 0.22rem;
}

.ps-d {
  color: var(--ink-soft);
  font-size: 0.74rem;
  margin-top: 0.08rem;
}

.buy-rank {
  display: inline-block;
  min-width: 1.1rem;
  color: var(--navy);
  font-weight: 800;
  margin-right: 0.35rem;
}

.quote-bucket {
  border: 2px dashed var(--danger);
  background: rgba(198, 40, 40, 0.1);
  color: var(--ink);
  padding: 0.5rem 0.65rem;
  margin-top: 0.6rem;
  font-size: 0.85rem;
}

.quote-bucket b {
  color: var(--danger);
  text-transform: uppercase;
  font-size: 0.68rem;
  font-weight: 800;
}

.stButton > button,
.stDownloadButton > button {
  min-height: 42px;
  border: 2px solid var(--navy);
  border-radius: 0;
  background: var(--orange);
  color: var(--cream);
  font-family: var(--body-font);
  font-size: var(--action-font-size);
  font-weight: 800;
  line-height: 1.12;
  text-transform: uppercase;
  box-shadow: 4px 4px 0 var(--navy);
}

.stButton > button *,
.stDownloadButton > button *,
[data-testid="stBaseButton-primary"] *,
[data-testid="stBaseButton-secondary"] * {
  color: inherit !important;
  font-size: var(--action-font-size) !important;
  font-weight: 800 !important;
  line-height: 1.12 !important;
  text-transform: uppercase !important;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
  border-color: var(--navy);
  background: var(--navy);
  color: var(--cream);
}

[data-testid="stExpander"] details {
  border: 2px solid var(--ink);
  background: var(--card);
  box-shadow: 3px 3px 0 var(--shadow);
  border-radius: 0;
}

[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary * {
  color: var(--navy) !important;
  font-weight: 800 !important;
}

[data-testid="stSidebar"] {
  background:
    repeating-linear-gradient(0deg, rgba(26, 54, 93, 0.07) 0 1px, transparent 1px 36px),
    linear-gradient(180deg, var(--khaki), var(--card));
  border-right: 3px solid var(--navy);
  min-width: min(23rem, 92vw) !important;
  width: min(23rem, 92vw) !important;
}

[data-testid="stSidebarContent"] {
  min-width: min(23rem, 92vw) !important;
  width: min(23rem, 92vw) !important;
}

[data-testid="stSidebarUserContent"] {
  width: auto !important;
}

[data-testid="stSidebar"] .stMarkdown,
[data-testid="stSidebar"] .stCaption,
[data-testid="stSidebar"] p {
  color: var(--ink) !important;
}

[data-testid="stSidebar"] .station-rack,
[data-testid="stSidebar"] .station-rack .rack-title {
  color: var(--cream) !important;
}

[data-testid="stSidebar"] .station-rack .rack-card {
  color: var(--ink) !important;
}

[data-testid="stSidebar"] .status-stack,
[data-testid="stSidebar"] .status-stack * {
  color: var(--ink) !important;
}

[data-testid="stSidebar"] .stCaption p,
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {
  color: rgba(28, 26, 23, 0.8) !important;
  font-size: 0.74rem;
  font-weight: 500;
  line-height: 1.35;
}

[data-testid="stSidebar"] .stDataFrame,
[data-testid="stSidebar"] [data-testid="stDataEditor"] {
  border: 2px solid var(--navy);
}

[data-testid="stSidebar"] [data-testid="stExpander"] details {
  border: 2px solid var(--navy);
  background: var(--paper);
  box-shadow: 3px 3px 0 rgba(26, 54, 93, 0.24);
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  background: var(--navy);
  color: var(--cream) !important;
  font-size: var(--action-font-size);
  font-weight: 800;
  line-height: 1.12;
  text-transform: uppercase;
}

[data-testid="stSidebar"] [data-testid="stExpander"] summary * {
  color: var(--cream) !important;
  font-size: var(--action-font-size) !important;
  font-weight: 800 !important;
  line-height: 1.12 !important;
}

/* ---- Phase 2: control room, risk chips, timing tags ---- */
.risk-chip {
  display: inline-block;
  border: 2px solid var(--ink);
  padding: 0.06rem 0.42rem;
  margin-top: 0.45rem;
  font-size: 0.7rem;
  font-weight: 800;
  text-transform: uppercase;
  background: var(--card);
  color: var(--teal);
}

.risk-chip.watch {
  color: var(--orange);
  border-color: var(--orange);
}

.risk-chip.high {
  color: var(--danger);
  border-color: var(--danger);
}

.timing-tag {
  display: inline-block;
  margin-left: 0.35rem;
  padding: 0 0.3rem;
  border: 1.5px solid var(--teal);
  color: var(--teal);
  font-size: 0.64rem;
  font-weight: 800;
  text-transform: uppercase;
  white-space: nowrap;
}

.timing-tag.now {
  border-color: var(--orange);
  color: var(--orange);
}

.draft-banner {
  border: 3px solid var(--teal);
  border-left-width: 12px;
  background: rgba(0, 90, 91, 0.08);
  color: var(--ink);
  padding: 0.9rem 1rem;
  margin-bottom: 0.9rem;
  box-shadow: 5px 5px 0 rgba(0, 90, 91, 0.22);
}

.draft-banner .alert-kicker {
  color: var(--teal);
  font-size: 0.74rem;
  font-weight: 800;
  text-transform: uppercase;
}

.verdict-badge {
  display: inline-block;
  min-width: 64px;
  text-align: center;
  border: 2px solid var(--ink);
  padding: 0 0.3rem;
  font-size: 0.66rem;
  font-weight: 800;
  text-transform: uppercase;
  background: var(--card);
  color: var(--teal);
}

.verdict-badge.concern {
  color: var(--orange);
  border-color: var(--orange);
}

.verdict-badge.veto {
  color: var(--cream);
  background: var(--danger);
  border-color: var(--danger);
}

.verdict-badge.counter,
.verdict-badge.draft,
.verdict-badge.converge {
  color: var(--navy);
  border-color: var(--navy);
}

.nego-line {
  font-size: 0.88rem;
  color: var(--ink);
  padding: 0.18rem 0;
  border-bottom: 1px solid rgba(28, 26, 23, 0.14);
}

.ing-line {
  font-size: 0.9rem;
  color: var(--ink);
  padding: 0.16rem 0;
  border-bottom: 1px dashed rgba(28, 26, 23, 0.16);
}

.ing-badge {
  display: inline-block;
  min-width: 52px;
  text-align: center;
  margin-right: 0.45rem;
  border: 1.5px solid var(--ink);
  padding: 0 0.25rem;
  font-size: 0.62rem;
  font-weight: 800;
  text-transform: uppercase;
  background: var(--card);
  color: var(--ink-soft);
}

.ing-badge.have {
  color: var(--teal);
  border-color: var(--teal);
}

.ing-badge.need {
  color: var(--orange);
  border-color: var(--orange);
}

.recipe-step {
  font-size: 0.9rem;
  color: var(--ink);
  padding: 0.16rem 0;
  line-height: 1.4;
}

.recipe-step .step-n {
  display: inline-block;
  min-width: 1.3rem;
  color: var(--orange);
  font-weight: 800;
}

.recipe-panel {
  background:
    repeating-linear-gradient(0deg, transparent 0 25px, rgba(0, 90, 91, 0.07) 25px 26px),
    #FBF6EA;
  border: 2px solid var(--teal);
  border-left: 7px solid var(--teal);
  box-shadow: 4px 4px 0 rgba(0, 90, 91, 0.18);
  padding: 0.7rem 0.8rem 0.65rem;
}

.recipe-sub {
  color: var(--navy);
  font-size: 0.64rem;
  font-weight: 800;
  text-transform: uppercase;
}

.recipe-panel .ing-badge {
  background: rgba(255, 255, 255, 0.55);
}

.recipe-adapt {
  margin-top: 0.55rem;
  background: rgba(212, 175, 55, 0.18);
  border-left: 4px solid var(--gold);
  padding: 0.45rem 0.55rem;
  font-size: 0.86rem;
  line-height: 1.4;
  color: var(--ink);
}

.recipe-src {
  margin-top: 0.5rem;
  color: var(--ink-soft);
  font-size: 0.72rem;
  font-style: italic;
  line-height: 1.35;
}

.nego-agent {
  display: inline-block;
  min-width: 88px;
  color: var(--navy);
  font-weight: 800;
  font-size: 0.74rem;
  text-transform: uppercase;
}

@media (max-width: 900px) {
  .brand-name {
    font-size: 3.4rem;
  }
  .check-meta,
  .service-grid,
  .brief-strip,
  .pipeline-strip,
  .proof-grid,
  .ticket-rail {
    grid-template-columns: 1fr;
  }
  .meta-box,
  .brief-cell {
    border-right: 0;
    border-bottom: 2px solid var(--ink);
  }
  .meta-box:last-child,
  .brief-cell:last-child {
    border-bottom: 0;
  }
  .can-sketch {
    border-left: 0;
    border-top: 3px solid var(--navy);
    padding-left: 0;
    padding-top: 1rem;
  }
  .pipe-step {
    border-right: 0;
    border-bottom: 2px solid var(--ink);
  }
  .pipe-step:last-child {
    border-bottom: 0;
  }
  .pipe-arrow {
    display: none;
  }
  .order-grid {
    grid-template-columns: minmax(120px, 1.15fr) 72px 80px minmax(140px, 1fr) 82px;
    overflow-x: auto;
  }
  [data-testid="stSidebar"] {
    min-width: 0;
  }
}
</style>
"""

def md(html_text: str) -> None:
    st.markdown(html_text, unsafe_allow_html=True)


def esc(value) -> str:
    return html.escape(str(value))


def status_dot(on: bool, label: str) -> str:
    state = "on" if on else ""
    return (
        f'<div class="status-line"><span class="status-dot {state}"></span>'
        f'<span>{esc(label)}</span></div>'
    )


def service_header(bq_ready: bool, gemini_ready: bool) -> None:
    bq_label = "BigQuery connected" if bq_ready else "demo recipe book"
    gemini_label = "Gemini chef online" if gemini_ready else "deterministic chef"
    today = datetime.date.today().strftime("%Y-%m-%d")
    md(
        f"""
        <div class="guest-check">
          <div class="brand-lockup">
            <div class="brand-name">SOUS</div>
            <div class="brand-sub">Guest Check</div>
            <div class="count-line">every second counts</div>
          </div>
          <div class="check-meta">
            <div class="meta-box">
              <div class="meta-label">Kitchen</div>
              <div class="meta-value">Indiranagar</div>
            </div>
            <div class="meta-box">
              <div class="meta-label">Decision line</div>
              <div class="meta-value">{esc(bq_label)} / {esc(gemini_label)}</div>
            </div>
            <div class="meta-box">
              <div class="meta-label">Service</div>
              <div class="meta-value mono">{esc(today)}</div>
            </div>
          </div>
          <div class="service-grid">
            <div class="service-copy">
              <h1>Three specials.<br>One clear call.</h1>
              <p>
                Turn today's walk-in and mandi prices into a margin-checked board,
                complete recipes, and a supplier ticket before service starts.
              </p>
            </div>
            <div class="can-sketch" aria-hidden="true">
              <div class="tomato-can">
                <div class="tomato-label">price spike: tomato +40%</div>
                <div class="tomatoes">
                  <div class="tomato"></div>
                  <div class="tomato"></div>
                  <div class="tomato"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
        """
    )


def section(number: str, label: str) -> None:
    md(f'<div class="section-label"><span class="section-num">{esc(number)}</span>{esc(label)}</div>')


def inventory_from_editor(df: pd.DataFrame) -> dict:
    inv = {}
    for _, row in df.iterrows():
        raw_item = row.get("Ingredient")
        if pd.isna(raw_item):
            continue
        item = str(raw_item).strip().lower()
        if not item or item == "nan":
            continue
        try:
            amount = float(row["Amount"])
        except Exception:
            amount = 0.0
        raw_unit = row.get("Unit")
        unit = str(raw_unit).strip() if pd.notna(raw_unit) and str(raw_unit).strip() else "kg"
        try:
            days = int(row["Days left"])
        except Exception:
            days = 99
        inv[item] = {
            "qty": f"{amount:g} {unit}",
            "amount": amount,
            "unit": unit,
            "days_to_expiry": days,
        }
    return inv


_UNITS = ["kg", "g", "L", "ml", "packet", "unit", "dozen", "bunch", "tray"]


def _default_inv_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Ingredient": k, "Amount": sc.split_qty(v["qty"])[0],
             "Unit": sc.split_qty(v["qty"])[1], "Days left": v["days_to_expiry"]}
            for k, v in sc.DEFAULT_INVENTORY.items()
        ]
    )


def render_sidebar(bq_ready: bool, gemini_ready: bool) -> pd.DataFrame:
    with st.sidebar:
        md(
            """
            <div class="station-rack">
              <div class="rack-title">Time-card rack / walk-in</div>
              <div class="rack-card">Add or remove rows when stock changes.</div>
              <div class="rack-card">Days 0-3 get near-expiry priority.</div>
              <div class="rack-card">Fold the rack away during service.</div>
            </div>
            """
        )
        if "inv_base" not in st.session_state:
            st.session_state["inv_base"] = _default_inv_df()
            st.session_state["inv_ver"] = 0

        edited = st.data_editor(
            st.session_state["inv_base"],
            key=f"walkin_{st.session_state['inv_ver']}",
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "Ingredient": st.column_config.TextColumn("Item", help="What's on hand", width="small"),
                "Amount": st.column_config.NumberColumn("Qty", min_value=0.0, step=0.5, format="%.1f", width="small"),
                "Unit": st.column_config.SelectboxColumn("Unit", options=_UNITS, width="small", required=True),
                "Days left": st.column_config.NumberColumn(
                    "Days", min_value=0, step=1, format="%d", width="small",
                    help="Days until it spoils; 3 or fewer is flagged near-expiry"),
            },
        )

        st.caption(
            "Use the + / trash controls to add or remove stock. Enter weights "
            "(kg/g/L/ml) where you can; packet or unit items are treated as on hand."
        )

        section("S", "service status")
        md(
            '<div class="status-stack">'
            + status_dot(bq_ready, "BigQuery / RecipeNLG 2.23M")
            + status_dot(True, f"cuDF GPU scoring / {sc.SPEEDUP}x proven")
            + status_dot(gemini_ready, "Gemini negotiation")
            + status_dot(True, "Forecast & margin-risk engine (7-day)")
            + "</div>"
        )
        st.caption("Offline mode still works: demo dishes plus deterministic ranking.")
    return edited

def render_pipeline_strip() -> None:
    steps = sc.PIPELINE_STEPS
    cells = []
    for i, (title, desc) in enumerate(steps):
        arrow = '<span class="pipe-arrow">&rsaquo;</span>' if i < len(steps) - 1 else ""
        cells.append(
            f'<div class="pipe-step"><div class="pipe-n">Step {i + 1}</div>'
            f'<div class="pipe-t">{esc(title)}</div><div class="pipe-d">{esc(desc)}</div>{arrow}</div>'
        )
    md('<div class="pipeline-strip">' + "".join(cells) + "</div>")


def render_brief_strip() -> None:
    md(
        """
        <div class="brief-strip">
          <div class="brief-cell">
            <div class="brief-kicker">User</div>
            <div class="brief-title">Independent kitchen</div>
            <div class="brief-body">A chef needs a menu and supplier order before the lunch rush moves.</div>
          </div>
          <div class="brief-cell">
            <div class="brief-kicker">Decision</div>
            <div class="brief-title">What should we sell today?</div>
            <div class="brief-body">Balance expiring stock, price spikes, food cost, and vegetarian coverage.</div>
          </div>
          <div class="brief-cell">
            <div class="brief-kicker">Acceleration</div>
            <div class="brief-title">Rerun while it matters</div>
            <div class="brief-body">GPU scoring makes the board interactive when prices or stock change.</div>
          </div>
        </div>
        """
    )


def render_waiting_state() -> None:
    md(
        """
        <div class="call-ticket">
          <strong>Ready on the pass.</strong>
          Edit the walk-in stock, then fire today's specials to produce a ranked board and supplier ticket.
        </div>
        """
    )


def render_decision_strip(res: dict) -> None:
    po = res["po"]
    n_specials = len(res["chosen"])
    n_buy = len(po["lines"])
    bought = {line["ingredient"] for line in po["lines"]}
    held = [k for k in po["spike_watch"] if k not in bought]
    parts = [f"{n_specials} specials fired"]
    parts.append(f"buy {n_buy} items / est. INR {po['total_inr']:,}" if n_buy
                 else "nothing to buy, walk-in covers it")
    if held:
        parts.append(f"{', '.join(held)} spike held in the walk-in")
    total_s = res.get("timings", {}).get("total_s")
    if total_s is not None:
        parts.append(f"decided in {total_s:.1f}s")
    body = " &middot; ".join(parts)
    md(f'<div class="decision-strip"><span class="ds-k">The call</span>'
       f'<span class="ds-b">{body}</span></div>')


def render_spike_alert(res: dict) -> None:
    po = res["po"]
    if not po["spike_watch"]:
        return
    bought = {line["ingredient"] for line in po["lines"]}
    held = [ingredient for ingredient in po["spike_watch"] if ingredient not in bought]
    spike_text = ", ".join(f"<strong>{esc(k)} +{v}%</strong>" for k, v in po["spike_watch"].items())
    extra = ""
    if held:
        extra = f" You already hold <strong>{esc(', '.join(held))}</strong>, so the order dodges that spike."
    # Phase 2: 7-day outlook + restock timing from the forecast layer.
    outlook_bits = []
    forecasts = res.get("forecast") or {}
    timing = res.get("timing") or {}
    for ing in po["spike_watch"]:
        f = forecasts.get(ing)
        if not f:
            continue
        line = f"{esc(ing)}: 7-day outlook {f['pct_7d']:+.0f}% ({esc(f['direction'])})"
        t = timing.get(ing)
        if t and t["tag"] == "DEFER":
            line += f" &middot; <strong>defer restock</strong>, save ~&#8377;{abs(t['save_inr_per_kg']):g}/kg"
        elif t and t["tag"] == "BUY_MIN":
            line += " &middot; buy today's shortfall only"
        elif t and t["tag"] == "BUY_NOW":
            line += " &middot; <strong>top up now</strong> before it climbs"
        outlook_bits.append(line)
    outlook = ""
    if outlook_bits:
        outlook = ('<div style="margin-top:0.35rem;font-size:0.86rem;">'
                   + " / ".join(outlook_bits) + "</div>")
    md(
        f"""
        <div class="alert-ticket">
          <div class="alert-kicker">Mandi board / price spike</div>
          {spike_text} today.{extra}
          {outlook}
        </div>
        """
    )


def render_special_ticket(index: int, dish: dict, brief_by_name: dict,
                          risk: dict = None) -> str:
    brief = brief_by_name.get(dish["title"], {})
    food_cost = brief.get("est_food_cost_pct", 0)
    within_target = food_cost <= sc.TARGET_FOOD_COST
    margin_text = "under target" if within_target else "over target"
    stamp_class = "stamp blue" if within_target else "stamp"
    uses = dish.get("uses_expiring") or []
    clears = f"Clears: {esc(', '.join(uses))}" if uses else "No urgent expiry cleared"
    veg = "Vegetarian" if brief.get("vegetarian") else "Non-veg"
    allergens = brief.get("allergens") or []
    allergy_text = f" / allergens: {esc(', '.join(allergens))}" if allergens else ""
    risk_html = ""
    if risk:
        cls = {"LOW": "", "WATCH": " watch", "HIGH": " high"}.get(risk.get("label"), "")
        tip = (f"Chance (0-100) that this dish's food cost tops the "
               f"{sc.TARGET_FOOD_COST}% target within 7 days, from the price "
               f"forecast bands")
        risk_html = (f'<br><span class="risk-chip{cls}" title="{esc(tip)}">'
                     f'margin risk {risk.get("score")} '
                     f'/ {esc(risk.get("label", ""))} (7-day)</span>')
    return f"""<div class="special-ticket">
<div class="ticket-top">
<span>No. {index:02d} / Special</span>
<span>Food cost {food_cost}%</span>
</div>
<div class="ticket-dish">{esc(dish["title"])}</div>
<div class="ticket-note">
{esc(clears)}<br>
{esc(veg)}{allergy_text}<br>
Target: {sc.TARGET_FOOD_COST}% / this dish is {esc(margin_text)}.{risk_html}
</div>
<div class="{stamp_class}">heard</div>
</div>"""


def render_recipe_card_body(card: dict) -> None:
    """One special's recipe inside its column, on a distinct parchment panel:
    tagged ingredients, method, optional adaptation note, source line."""
    parts = ['<div class="recipe-panel">',
             '<div class="recipe-sub">Ingredients '
             + recipe_source_badge(card) + '</div>']
    for ing in card["ingredients"]:
        status = ing["status"]
        label = {"have": "have", "need": "buy", "pantry": "pantry"}[status]
        parts.append(
            f'<div class="ing-line"><span class="ing-badge {esc(status)}">'
            f'{label}</span>{esc(ing["text"])}</div>')
    if card.get("directions"):
        parts.append('<div class="recipe-sub" style="margin-top:0.55rem;">Method</div>')
        for n, step in enumerate(card["directions"][:10], start=1):
            parts.append(f'<div class="recipe-step"><span class="step-n">{n}.</span>'
                         f'{esc(step)}</div>')
        if len(card["directions"]) > 10:
            parts.append('<div class="recipe-step">&hellip;</div>')
    else:
        parts.append('<div class="recipe-sub" style="margin-top:0.55rem;">Method '
                     '<span class="recipe-source-badge missing">Unavailable</span></div>')
        parts.append('<div class="method-empty">No reviewed method was found in BigQuery '
                     'or the search fallback. Ingredients remain available for planning.</div>')
    if card.get("adaptation"):
        parts.append(
            f'<div class="recipe-adapt"><strong>Sous-chef&#39;s adaptation for '
            f'your walk-in.</strong><br>'
            f'{esc(card["adaptation"]).replace(chr(10), "<br>")}</div>')
    source_links = recipe_source_links(card)
    parts.append(
        f'<div class="recipe-src"><strong>Recipe source:</strong> '
        f'{esc(card.get("source", ""))}</div>{source_links}'
        f'<div class="recipe-src">The supplier ticket is a deterministic buy list '
        f'scaled for {sc.PLANNED_COVERS} covers; fallback recipe text never changes '
        f'its quantities.</div></div>')
    md("".join(parts))


def render_specials(res: dict) -> None:
    brief_by_name = {brief["dish"]: brief for brief in res["brief"]}
    risks = res.get("risk") or {}
    recipes = res.get("recipes") or {}
    render_recipe_coverage(res)
    columns = st.columns(max(1, len(res["chosen"])))
    for column, (index, dish) in zip(columns, enumerate(res["chosen"], start=1)):
        with column:
            md(render_special_ticket(index, dish, brief_by_name,
                                     risk=risks.get(dish["title"])))
    available_titles = [d["title"] for d in res["chosen"] if recipes.get(d["title"])]
    if available_titles:
        with st.expander("Recipes"):
            selected = st.selectbox(
                "Choose a special", available_titles, key="recipe_special")
            render_recipe_card_body(recipes[selected])

    if res.get("recipes_note"):
        st.caption(f"Recipe text note: {res['recipes_note']}.")


def render_order_ticket(res: dict) -> None:
    po = res["po"]
    summary = sc.order_summary(po, top_n=5)
    rows = []
    for rank, line in enumerate(summary["top"], start=1):
        spike = f' <span class="spike">+{line["spike_pct"]}%</span>' if line["spike_pct"] >= 25 else ""
        tag = ""
        if line.get("timing") == "BUY_NOW":
            tag = (' <span class="timing-tag now" title="7-day forecast: price '
                   'rising - today&#39;s buy is well-timed">buy now</span>')
        elif line.get("timing") == "BUY_MIN":
            tag = (' <span class="timing-tag" title="7-day forecast: price easing '
                   '- buy only today&#39;s shortfall, top up cheaper later">'
                   'min buy / easing</span>')
        used_by = ", ".join(line["used_by"])
        rows.append(
            f'<div class="order-cell"><span class="buy-rank">{rank}</span>{esc(line["ingredient"])}{spike}{tag}</div>'
            f'<div class="order-cell num">{line["qty_kg"]:.1f} kg</div>'
            f'<div class="order-cell num">&#8377;{line["unit_price_inr"]:.0f}/kg</div>'
            f'<div class="order-cell">{esc(used_by)}</div>'
            f'<div class="order-cell num">&#8377;{line["line_cost_inr"]:.0f}</div>'
        )
    if summary["more_count"]:
        rows.append(
            f'<div class="order-cell order-empty">+{summary["more_count"]} more priced items '
            f'&middot; &#8377;{summary["more_total"]:,} (full list in the CSV)</div>'
        )
    if not rows:
        rows.append('<div class="order-cell order-empty">Nothing to buy. The chosen specials are covered by the walk-in.</div>')

    quote_note = ""
    if summary["quote"]:
        q = summary["quote"]
        shown = ", ".join(q[:10]) + (f" and {len(q) - 10} more" if len(q) > 10 else "")
        quote_note = (
            f'<div class="quote-bucket"><b>Needs supplier quote &middot; {len(q)} items</b><br>'
            f'{esc(shown)}</div>'
        )

    total_label = "Known priced total" if summary["quote"] else "Total"
    today = datetime.date.today().isoformat()
    specials = ", ".join(dish["title"] for dish in res["chosen"])
    md(
        f"""<div class="order-sheet">
<div class="order-head">
<div>
<div class="order-title">Supplier order ticket</div>
<div>{esc(sc.RESTAURANT)} to {esc(sc.SUPPLIER)}</div>
</div>
<div class="num">{esc(today)}<br>No. GPU-{int(sc.SPEEDUP * 10)}</div>
</div>
<div class="order-grid">
<div class="order-cell order-head-cell">Item</div>
<div class="order-cell order-head-cell num">Qty</div>
<div class="order-cell order-head-cell num">Price</div>
<div class="order-cell order-head-cell">Used by</div>
<div class="order-cell order-head-cell num">Line</div>
{''.join(rows)}
</div>
<div class="total-row"><span>{total_label}</span><span>&#8377;{po["total_inr"]:,}</span></div>
<div class="ticket-note">Specials: {esc(specials)}. Plan: {sc.PLANNED_COVERS} covers/special, about {int(sc.PORTION_KG * 1000)} g/item.<br>Top 5 priced items shown; full supplier list in the CSV.</div>
{quote_note}
</div>"""
    )


def render_supplier_exports(res: dict) -> None:
    st.caption("Supplier ticket exports. Nothing is sent from this demo.")
    today = datetime.date.today().isoformat()
    po = res["po"]
    header = (
        f"SOUS SUPPLIER ORDER ({today})\n"
        f"From: {sc.RESTAURANT}\n"
        f"To: {sc.SUPPLIER}\n"
        f"Specials: {', '.join(d['title'] for d in res['chosen'])}\n"
        f"Estimated total: INR {po['total_inr']}\n\n"
    )
    c1, c2 = st.columns(2)
    c1.download_button(
        "Export CSV",
        sc.po_to_csv(po),
        file_name=f"supplier_order_{today}.csv",
        mime="text/csv",
        type="primary",
    )
    c2.download_button(
        "Export TXT",
        header + sc.po_to_csv(po),
        file_name=f"supplier_order_{today}.txt",
        mime="text/plain",
    )

def render_reasoning(res: dict) -> None:
    with st.expander("Head chef's call / negotiation"):
        if res["coord_text"]:
            st.markdown(res["coord_text"])
        else:
            st.info(
                "Live negotiation runs on Vertex AI (Gemini). This run used deterministic "
                "ranking: clear near-expiry stock first, then maximize stock match."
            )

    with st.expander("Audit trail / which agent argued what"):
        for item in res["trail"]:
            st.markdown(f"**{item['dish']}**")
            st.write(f"- Menu/Recipe: {item['menu']} ({res['menu_source']})")
            st.write(f"- Market & Price: {item['price']} (Agmarknet-style snapshot)")
            st.write(f"- Nutrition: {item['nutrition']} (rule-based on names)")
            st.write(f"- Margin verdict: {item['margin']}")

    if res.get("runtime") != "agents":
        st.caption(
            "Tip: flip on the negotiating agent runtime above to watch this call "
            "argued round-by-round - vetoes, counters, a full trace, and the "
            "veto ledger in the control room.")


def render_how_it_works() -> None:
    with st.expander("How Sous works (pipeline + acceleration)"):
        render_pipeline_strip()
        render_brief_strip()
        st.caption(
            f"Acceleration: pandas {sc.PANDAS_SECS}s -> cuDF {sc.CUDF_SECS}s over 2.23M recipes "
            f"({sc.SPEEDUP}x - {sc.ACCEL_SOURCE})."
        )
        st.bar_chart(
            pd.DataFrame({"seconds": [sc.PANDAS_SECS, sc.CUDF_SECS]}, index=["pandas CPU", "cuDF GPU"])
        )


def render_accel_line() -> None:
    md(
        '<div class="speed-ticket" style="display:flex;align-items:baseline;gap:0.9rem;flex-wrap:wrap;">'
        f'<span class="speed-big" style="font-size:2.1rem;">{sc.SPEEDUP}x</span>'
        f'<span class="speed-note">menu recompute, cuDF vs pandas ({sc.PANDAS_SECS}s to {sc.CUDF_SECS}s '
        "over 2.23M recipes) - fast enough to rerun during service.</span>"
        "</div>"
    )


def render_acceleration() -> None:
    section("86", "decision proof / why every second counts")
    md(
        '<div class="proof-grid">'
        f'<div class="proof-stat"><div class="ps-n">{sc.PANDAS_SECS}s &rarr; {sc.CUDF_SECS}s</div>'
        '<div class="ps-l">pandas to cuDF</div><div class="ps-d">same scoring, one GPU pass</div></div>'
        '<div class="proof-stat"><div class="ps-n">2.23M</div>'
        '<div class="ps-l">recipes ranked</div><div class="ps-d">BigQuery recipe book</div></div>'
        '<div class="proof-stat"><div class="ps-n">Live</div>'
        '<div class="ps-l">rerun during service</div><div class="ps-d">prices move, board updates</div></div>'
        '</div>'
    )
    left, right = st.columns([0.92, 1.08])
    with left:
        md(
            f"""
            <div class="speed-ticket">
              <div class="speed-kicker">Menu recompute / GPU line</div>
              <div class="speed-big">{sc.SPEEDUP}x</div>
              <div class="speed-note">
                cuDF vs pandas: {sc.PANDAS_SECS}s to {sc.CUDF_SECS}s over 2.23M recipes.
                The point is not a prettier chart. It is a decision while service is still moving.
              </div>
            </div>
            """
        )
    with right:
        chart_df = pd.DataFrame(
            {"seconds": [sc.PANDAS_SECS, sc.CUDF_SECS]},
            index=["pandas CPU", "cuDF GPU"],
        )
        st.bar_chart(chart_df)


def _verdict_badge(verdict: str) -> str:
    v = esc(str(verdict).lower())
    return f'<span class="verdict-badge {v}">{v}</span>'


def render_relaxation_card(res: dict) -> None:
    """The Coordinator asked to exceed the food-cost target. Only the human
    can grant it - and either answer becomes part of the trace."""
    req = res.get("relaxation_request")
    if not req:
        return
    st.warning(
        f"**The Coordinator requests a constraint relaxation.** "
        f"Allow **{req['dish']}** at **{req['food_cost_pct']}%** food cost "
        f"(target {req['target_pct']}%)? {req.get('reason', '')} "
        f"Sous never relaxes the target on its own."
    )
    c1, c2 = st.columns(2)
    decision = None
    if c1.button("Allow once", key="relax_allow"):
        decision = True
    if c2.button("Refuse / hold the target", key="relax_refuse"):
        decision = False
    if decision is not None:
        from agents.orchestrator import apply_relaxation
        st.session_state["result"] = apply_relaxation(res, allow=decision)
        st.session_state["toast_msg"] = (
            "Relaxation allowed once - recorded in the veto ledger."
            if decision else
            "Refused - the board holds the target. Recorded in the veto ledger.")
        st.rerun()


def render_strike_replace(res: dict) -> None:
    """Chef's override: strike a special, swap in another candidate. Traced."""
    chosen_titles = [d["title"] for d in res["chosen"]]
    bench = [d["title"] for d in res["dishes"] if d["title"] not in chosen_titles]
    if not chosen_titles or not bench:
        return
    with st.expander("Chef's override / strike & replace a special"):
        c1, c2, c3 = st.columns([1, 1, 0.6])
        out_t = c1.selectbox("Strike", chosen_titles, key="strike_out")
        in_t = c2.selectbox("Replace with", bench, key="strike_in")
        c3.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        if c3.button("Swap", key="strike_go"):
            from agents.orchestrator import replace_special
            st.session_state["result"] = replace_special(res, out_t, in_t)
            st.session_state["toast_msg"] = (
                f"Chef's override: {out_t} -> {in_t}. Order recomputed and logged.")
            st.rerun()


def render_control_room(res: dict) -> None:
    """Phase 2 observability: every agent turn, veto, and human decision.
    Only rendered when the agents runtime produced a trace."""
    trace = res.get("trace")
    if not trace:
        return
    section("04", "control room / negotiation, trace & oversight")
    tab_nego, tab_timeline, tab_ledger = st.tabs(
        ["Negotiation", "Agent timeline", "Veto ledger & oversight"])

    nego = res.get("negotiation") or {}
    with tab_nego:
        if nego.get("plan"):
            md(f'<div class="call-ticket"><strong>Coordinator plan.</strong> '
               f'{esc(nego["plan"])}</div>')
        rounds = nego.get("rounds") or []
        step_mode = os.environ.get("SOUS_STEP") == "1"
        run_id = trace[0].get("run_id", "run") if trace else "run"
        shown = len(rounds)
        if step_mode:
            key = f"step_{run_id}"
            st.session_state.setdefault(key, 1)
            shown = st.session_state[key]
            if shown < len(rounds) and st.button("Continue service &#9654;", key=f"{key}_btn"):
                st.session_state[key] += 1
                st.rerun()
        for r in rounds[:shown]:
            st.markdown(f"**Round {r['round']} - {r['title']}**")
            lines = []
            for item in r.get("items", []):
                lines.append(
                    f'<div class="nego-line"><span class="nego-agent">{esc(item["agent"])}</span>'
                    f'{_verdict_badge(item["verdict"])} '
                    f'<strong>{esc(item["dish"])}</strong> &middot; {esc(item["reason"])}</div>')
            md("".join(lines))
        resolution = nego.get("resolution")
        if resolution and shown >= len(rounds):
            md(f'<div class="decision-strip"><span class="ds-k">Converged</span>'
               f'<span class="ds-b">{esc(", ".join(resolution.get("picks", [])))} '
               f'&middot; confidence {resolution.get("confidence")}</span></div>')

    with tab_timeline:
        rows = []
        for e in trace:
            p = e.get("payload") or {}
            detail = (p.get("reason") or p.get("text")
                      or ", ".join(f"{k}={v}" for k, v in p.items() if k != "evidence"))
            rows.append({"t (s)": e.get("ts"), "round": e.get("round"),
                         "agent": e.get("agent"), "model": e.get("model"),
                         "action": e.get("action"),
                         "detail": str(detail)[:160],
                         "ms": e.get("latency_ms")})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        import json as _json
        st.download_button(
            "Export trace JSON",
            _json.dumps({"run_id": run_id, "events": trace}, indent=2, default=str),
            file_name=f"sous_trace_{run_id}.json", mime="application/json")
        st.caption("Every agent turn on the record: who ran, on what, how long, "
                   "and where the system degraded. Replay offline with "
                   "scripts/replay_trace.py.")

    with tab_ledger:
        ledger_actions = {"veto", "guardrail_fired", "approve", "refuse",
                          "override", "relaxation_requested"}
        entries = [e for e in trace if e.get("action") in ledger_actions]
        if entries:
            rows = []
            for e in entries:
                p = e.get("payload") or {}
                rows.append({"agent": e.get("agent"), "action": e.get("action"),
                             "dish": p.get("dish") or p.get("out") or "-",
                             "detail": str(p.get("reason") or p.get("decision")
                                           or p.get("action") or p)[:160]})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.caption("No vetoes, guardrails, or human overrides this run.")
        st.caption(
            f"The margin target ({sc.TARGET_FOOD_COST}%) cannot be exceeded and "
            "nothing is ever ordered without a decision recorded here.")
        render_strike_replace(res)


def render_draft_banner() -> None:
    prepared = st.session_state.get("draft_prepared_at")
    if prepared:
        md(f"""
        <div class="draft-banner">
          <div class="alert-kicker">Digital teammate / scheduled run</div>
          Today's draft board was prepared autonomously at <strong>{esc(prepared)}</strong>
          and is awaiting your approval. Rerun anytime with fresh stock - nothing is
          ordered until you fire it.
        </div>""")


def load_draft_on_boot() -> None:
    """agents/daily_run.py leaves a draft; pick it up once per session."""
    if "result" in st.session_state or st.session_state.get("draft_checked"):
        return
    st.session_state["draft_checked"] = True
    if os.environ.get("SOUS_LOAD_DRAFT", "1") != "1":
        return
    path = os.path.join(os.environ.get("SOUS_DRAFT_DIR", "drafts"), "latest.json")
    try:
        import json as _json
        with open(path, encoding="utf-8") as f:
            draft = _json.load(f)
        result = draft.get("result")
        if result and result.get("chosen"):
            st.session_state["result"] = result
            st.session_state["draft_prepared_at"] = draft.get("prepared_at", "earlier today")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[draft] load skipped ({type(e).__name__}: {e})")


def render_service(edited_inventory) -> None:
    toast = st.session_state.pop("toast_msg", None)
    if toast:
        st.toast(toast)
    section("01", "set the board")
    control_a, control_b = st.columns(2)
    curated = control_a.toggle(
        "Use curated demo catalog",
        value=False,
        help="ON: six clean curated dishes - a stable, reproducible board for a "
             "recorded demo. OFF: live server-side match over 2.23M RecipeNLG "
             "recipes in BigQuery.",
    )
    agents_mode = control_b.toggle(
        "Run negotiating agents",
        value=os.environ.get("SOUS_AGENT_RUNTIME", "legacy").lower() == "agents",
        help="ON: the Coordinator delegates to Menu / Price / Nutrition / Margin "
             "agents, brokers up to 3 rounds (hard margin veto), and every turn "
             "lands in the control room below. OFF: the Phase 1 pipeline.",
    )
    render_recipe_policy()
    md('<div class="run-help">Live catalog is the default. Search is attempted only '
       'when the selected BigQuery recipe still has no reviewed method.</div>')
    if st.button("Fire today's specials", type="primary", width="stretch"):
        st.session_state.pop("draft_prepared_at", None)
        spin = ("Coordinator on the pass: delegating, negotiating, converging..."
                if agents_mode else
                "Working the rail, pricing the board, checking the walk-in...")
        with st.spinner(spin):
            st.session_state["result"] = sc.run_pipeline(
                inventory_from_editor(edited_inventory), force_demo=curated,
                runtime="agents" if agents_mode else "legacy")

    result = st.session_state.get("result")
    if not result:
        render_waiting_state()
        render_accel_line()
        md('<div class="footer-line"><strong>Every second counts</strong></div>')
        return

    render_draft_banner()
    runtime_note = ("negotiating agents (traced)" if result.get("runtime") == "agents"
                    else "legacy pipeline")
    st.caption(f"Recipe candidates from: {result['menu_source']} / prices: "
               f"{getattr(sc, 'PRICE_SOURCE', 'built-in daily snapshot')} / "
               f"runtime: {runtime_note}")
    render_decision_strip(result)
    render_relaxation_card(result)     # a pending human decision belongs on top
    render_spike_alert(result)

    section("02", "specials on the rail")
    render_specials(result)
    render_reasoning(result)

    section("03", "supplier ticket")
    render_order_ticket(result)
    render_supplier_exports(result)

    render_control_room(result)
    render_accel_line()

    md('<div class="footer-line"><strong>Every second counts</strong></div>')


bq_ready = sc.get_bq_client() is not None
gemini_ready = sc.gemini_ready()

md(CSS + REFINEMENT_CSS)
load_draft_on_boot()
service_header(bq_ready, gemini_ready)
render_how_it_works()
edited_inventory = render_sidebar(bq_ready, gemini_ready)

render_service(edited_inventory)
