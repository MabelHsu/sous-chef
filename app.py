"""
Sous - Streamlit interface.
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


st.set_page_config(
    page_title="Sous - every second counts",
    layout="wide",
    initial_sidebar_state="expanded",
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
  display: none !important;
  visibility: hidden !important;
}

[data-testid="stDeployButton"],
[data-testid="stMainMenu"] {
  visibility: hidden;
}

[data-testid="stExpandSidebarButton"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebarCollapsedControl"] {
  display: none !important;
  visibility: hidden !important;
  pointer-events: none !important;
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
  transform: translateX(0) !important;
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
              <div class="meta-label">Cast</div>
              <div class="meta-value">{esc(bq_label)} / {esc(gemini_label)}</div>
            </div>
            <div class="meta-box">
              <div class="meta-label">Service</div>
              <div class="meta-value mono">{esc(today)}</div>
            </div>
          </div>
          <div class="service-grid">
            <div class="service-copy">
              <h1>Margin calls before the rush.</h1>
              <p>
                Today's mandi prices and walk-in stock become a specials board,
                supplier order ticket, and acceleration proof fast enough to use during service.
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
              <div class="rack-card">Chef edits stock before service.</div>
              <div class="rack-card">Near-expiry gets priority.</div>
              <div class="rack-card">Spike board: tomato +40%.</div>
            </div>
            """
        )
        if "inv_base" not in st.session_state:
            st.session_state["inv_base"] = _default_inv_df()
            st.session_state["inv_ver"] = 0

        edited = st.data_editor(
            st.session_state["inv_base"],
            key=f"walkin_{st.session_state['inv_ver']}",
            num_rows="fixed",
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

        with st.expander("Add an ingredient"):
            name = st.text_input("Item", key="add_name", placeholder="e.g. capsicum")
            col_a, col_b = st.columns(2)
            amount = col_a.number_input("Qty", min_value=0.0, step=0.5, value=1.0, key="add_amount")
            unit = col_b.selectbox("Unit", _UNITS, key="add_unit")
            days = st.number_input("Days left", min_value=0, step=1, value=7, key="add_days")
            if st.button("Add to walk-in") and str(name).strip():
                new_row = pd.DataFrame(
                    [{"Ingredient": str(name).strip(), "Amount": amount,
                      "Unit": unit, "Days left": days}]
                )
                st.session_state["inv_base"] = pd.concat([edited, new_row], ignore_index=True)
                st.session_state["inv_ver"] += 1
                st.rerun()

        st.caption(
            "Enter weights (kg/g/L/ml) where you can. Items counted by packet or unit "
            "are assumed on hand and left off the auto-order."
        )

        section("S", "service status")
        md(
            '<div class="status-stack">'
            + status_dot(bq_ready, "BigQuery / RecipeNLG 2.23M")
            + status_dot(True, f"cuDF GPU scoring / {sc.SPEEDUP}x proven")
            + status_dot(gemini_ready, "Gemini negotiation")
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


def render_spike_alert(po: dict) -> None:
    if not po["spike_watch"]:
        return
    bought = {line["ingredient"] for line in po["lines"]}
    held = [ingredient for ingredient in po["spike_watch"] if ingredient not in bought]
    spike_text = ", ".join(f"<strong>{esc(k)} +{v}%</strong>" for k, v in po["spike_watch"].items())
    extra = ""
    if held:
        extra = f" You already hold <strong>{esc(', '.join(held))}</strong>, so the order dodges that spike."
    md(
        f"""
        <div class="alert-ticket">
          <div class="alert-kicker">Mandi board / price spike</div>
          {spike_text} today.{extra}
        </div>
        """
    )


def render_special_ticket(index: int, dish: dict, brief_by_name: dict) -> str:
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
    return f"""<div class="special-ticket">
<div class="ticket-top">
<span>No. {index:02d} / Special</span>
<span>Food cost {food_cost}%</span>
</div>
<div class="ticket-dish">{esc(dish["title"])}</div>
<div class="ticket-note">
{esc(clears)}<br>
{esc(veg)}{allergy_text}<br>
Target: {sc.TARGET_FOOD_COST}% / this dish is {esc(margin_text)}.
</div>
<div class="{stamp_class}">heard</div>
</div>"""


def render_specials(res: dict) -> None:
    brief_by_name = {brief["dish"]: brief for brief in res["brief"]}
    columns = st.columns(max(1, len(res["chosen"])))
    for column, (index, dish) in zip(columns, enumerate(res["chosen"], start=1)):
        with column:
            md(render_special_ticket(index, dish, brief_by_name))


def render_order_ticket(res: dict) -> None:
    po = res["po"]
    summary = sc.order_summary(po, top_n=5)
    rows = []
    for rank, line in enumerate(summary["top"], start=1):
        spike = f' <span class="spike">+{line["spike_pct"]}%</span>' if line["spike_pct"] >= 25 else ""
        used_by = ", ".join(line["used_by"])
        rows.append(
            f'<div class="order-cell"><span class="buy-rank">{rank}</span>{esc(line["ingredient"])}{spike}</div>'
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
                "Set GEMINI_API_KEY for live negotiation text. This run used deterministic ranking: "
                "clear near-expiry stock first, then maximize stock match."
            )

    with st.expander("Audit trail / which agent argued what"):
        for item in res["trail"]:
            st.markdown(f"**{item['dish']}**")
            st.write(f"- Menu/Recipe: {item['menu']} ({res['menu_source']})")
            st.write(f"- Market & Price: {item['price']} (Agmarknet-style snapshot)")
            st.write(f"- Nutrition: {item['nutrition']} (rule-based on names)")
            st.write(f"- Margin verdict: {item['margin']}")


def render_how_it_works() -> None:
    with st.expander("How Sous works (pipeline + acceleration)"):
        render_pipeline_strip()
        render_brief_strip()
        st.caption(
            f"Acceleration: pandas {sc.PANDAS_SECS}s -> cuDF {sc.CUDF_SECS}s over 2.23M recipes "
            f"({sc.SPEEDUP}x on a T4 GPU)."
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


def render_service(edited_inventory) -> None:
    section("01", "set the board")
    curated = st.toggle(
        "Curated demo dishes (off = live BigQuery over 2.23M recipes)",
        value=True,
    )
    if st.button("Fire today's specials", type="primary"):
        with st.spinner("Working the rail, pricing the board, checking the walk-in..."):
            st.session_state["result"] = sc.run_pipeline(
                inventory_from_editor(edited_inventory), force_demo=curated)

    result = st.session_state.get("result")
    if not result:
        render_waiting_state()
        render_accel_line()
        md('<div class="footer-line"><strong>Every second counts</strong></div>')
        return

    st.caption(f"Recipe candidates from: {result['menu_source']} / prices: {getattr(sc, "PRICE_SOURCE", "built-in daily snapshot")}")
    render_decision_strip(result)
    render_spike_alert(result["po"])

    section("02", "specials on the rail")
    render_specials(result)
    render_reasoning(result)

    section("03", "supplier ticket")
    render_order_ticket(result)
    render_supplier_exports(result)
    render_accel_line()

    md('<div class="footer-line"><strong>Every second counts</strong></div>')


bq_ready = sc.get_bq_client() is not None
gemini_ready = bool((os.environ.get("GEMINI_API_KEY") or "").strip())

md(CSS)
service_header(bq_ready, gemini_ready)
render_how_it_works()
edited_inventory = render_sidebar(bq_ready, gemini_ready)

render_service(edited_inventory)
