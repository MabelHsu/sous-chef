"""Small, testable UI components for recipe provenance and coverage."""
import html
from urllib.parse import urlparse

import streamlit as st


def render_recipe_policy():
    st.markdown(
        """
        <div class="source-policy">
          <div class="source-tier primary">
            <div class="tier-n">01 / source of truth</div>
            <div class="tier-title">BigQuery corpus</div>
            <div class="tier-copy">RecipeNLG ingredients and methods, selected with the menu row.</div>
          </div>
          <div class="source-tier primary">
            <div class="tier-n">02 / reviewed completion</div>
            <div class="tier-title">Approved details</div>
            <div class="tier-copy">Human-approved BigQuery records complete partial corpus rows.</div>
          </div>
          <div class="source-tier fallback">
            <div class="tier-n">03 / only on a miss</div>
            <div class="tier-title">Gemini + Search</div>
            <div class="tier-copy">Clearly labelled, cited enrichment; never promoted automatically.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recipe_coverage(result):
    coverage = result.get("recipe_coverage") or {}
    if not coverage:
        return
    canonical = int(coverage.get("canonical", 0))
    search = int(coverage.get("search", 0))
    missing = int(coverage.get("missing", 0))
    missing_class = "warn" if missing else "good"
    st.markdown(
        f"""
        <div class="recipe-quality">
          <div class="quality-cell good"><div class="quality-n">{canonical}</div>
            <div class="quality-l">BigQuery / curated methods</div></div>
          <div class="quality-cell"><div class="quality-n">{search}</div>
            <div class="quality-l">Search-enriched methods</div></div>
          <div class="quality-cell {missing_class}"><div class="quality-n">{missing}</div>
            <div class="quality-l">Methods still unavailable</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def recipe_source_badge(card):
    source_type = card.get("source_type", "ner_floor")
    labels = {
        "bigquery_corpus": ("BigQuery corpus", ""),
        "bigquery_approved": ("BigQuery approved", ""),
        "curated": ("Curated demo", ""),
        "search_fallback": ("Search fallback", "search"),
        "ner_floor": ("Ingredients only", "missing"),
    }
    label, css_class = labels.get(source_type, ("Recipe source", ""))
    return (f'<span class="recipe-source-badge {css_class}">'
            f'{html.escape(label)}</span>')


def recipe_source_links(card):
    links = []
    for item in card.get("source_urls") or []:
        if isinstance(item, dict):
            title, url = item.get("title"), item.get("url")
        else:
            title, url = "Reference", item
        url = str(url or "").strip()
        if urlparse(url).scheme not in {"http", "https"}:
            continue
        links.append(
            f'<a href="{html.escape(url, quote=True)}" target="_blank" '
            f'rel="noopener noreferrer">{html.escape(str(title or "Reference"))}</a>')
    if not links:
        return ""
    return '<div class="recipe-links">References: ' + " &middot; ".join(links[:3]) + "</div>"
