"""
streamlit_app.py
────────────────
GeM Tender Tracker — Streamlit Dashboard

Calls the live FastAPI backend (configured via API_BASE_URL env var)
and renders a premium, interactive dashboard for business users.

Deploy on: https://streamlit.io/cloud  (free, no credit card)
"""

from __future__ import annotations

import os
import math
import requests
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GeM Tender Tracker",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── API Base URL ───────────────────────────────────────────────────────────────
API_BASE = os.getenv(
    "API_BASE_URL",
    "http://localhost:8000",  # fallback: local FastAPI dev server
).rstrip("/")

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

/* Global */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%);
}
[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] .stTextInput label,
[data-testid="stSidebar"] .stSlider label,
[data-testid="stSidebar"] .stCheckbox label {
    color: #94a3b8 !important;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Metric cards */
[data-testid="metric-container"] {
    background: linear-gradient(135deg, #1e293b, #0f172a);
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 1rem;
}

/* Header */
.main-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 50%, #1a1a2e 100%);
    border-radius: 16px;
    padding: 2rem 2.5rem;
    margin-bottom: 1.5rem;
    border: 1px solid #334155;
}
.main-header h1 {
    color: #f1f5f9;
    font-size: 2rem;
    font-weight: 700;
    margin: 0;
}
.main-header p {
    color: #94a3b8;
    margin: 0.4rem 0 0 0;
    font-size: 0.95rem;
}

/* Status badges */
.badge-active {
    background: #064e3b;
    color: #6ee7b7;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-closed {
    background: #1e293b;
    color: #64748b;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
}
.badge-ai {
    background: #312e81;
    color: #a5b4fc;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
}

/* Tender card */
.tender-card {
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 0.75rem;
    transition: border-color 0.2s;
}
.tender-card:hover {
    border-color: #3b82f6;
}
.tender-title {
    color: #f1f5f9;
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 0.4rem;
}
.tender-meta {
    color: #64748b;
    font-size: 0.8rem;
    margin-bottom: 0.6rem;
}
.tender-ai {
    color: #a5b4fc;
    font-size: 0.85rem;
    font-style: italic;
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid #334155;
}
.tag-pill {
    display: inline-block;
    background: #1e3a5f;
    color: #93c5fd;
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 0.72rem;
    margin-right: 4px;
    margin-top: 4px;
}

/* Divider */
hr { border-color: #334155; }
</style>
""", unsafe_allow_html=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

@st.cache_data(ttl=120)
def fetch_stats() -> dict:
    try:
        r = requests.get(f"{API_BASE}/stats/summary", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


@st.cache_data(ttl=60)
def fetch_tenders(
    keyword: str | None,
    department: str | None,
    location: str | None,
    min_value: float | None,
    max_value: float | None,
    active_only: bool,
    limit: int,
    offset: int,
) -> dict:
    params: dict = {
        "limit": limit,
        "offset": offset,
        "active_only": str(active_only).lower(),
    }
    if keyword:
        params["keyword"] = keyword
    if department:
        params["department"] = department
    if location:
        params["location"] = location
    if min_value is not None:
        params["min_value"] = min_value
    if max_value is not None:
        params["max_value"] = max_value

    try:
        r = requests.get(f"{API_BASE}/tenders", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"count": 0, "results": [], "error": str(e)}


@st.cache_data(ttl=300)
def fetch_ai_status() -> dict:
    try:
        r = requests.get(f"{API_BASE}/ai/status", timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {"enabled": False}


def fmt_inr(value: float | None) -> str:
    """Format a number as Indian Rupees."""
    if value is None:
        return "—"
    if value >= 1_00_00_000:
        return f"₹{value/1_00_00_000:.1f} Cr"
    if value >= 1_00_000:
        return f"₹{value/1_00_000:.1f} L"
    return f"₹{value:,.0f}"


def is_active(end_date_str: str | None) -> bool:
    if not end_date_str:
        return False
    try:
        end = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
        return end > datetime.now(end.tzinfo)
    except Exception:
        return False


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>GeM Tender Tracker</h1>
    <p>Live AI-enriched Government e-Marketplace tender intelligence · Updated daily</p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar Filters ────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Filters")
    st.markdown("---")

    keyword = st.text_input("Keyword Search", placeholder="e.g. laptop, defence, solar")
    department = st.text_input("Department", placeholder="e.g. Ministry of Defence")
    location = st.text_input("Location", placeholder="e.g. Delhi, Mumbai")

    st.markdown("**Estimated Value (₹)**")
    col1, col2 = st.columns(2)
    with col1:
        min_val_input = st.text_input("Min", placeholder="e.g. 100000")
    with col2:
        max_val_input = st.text_input("Max", placeholder="e.g. 5000000")

    active_only = st.checkbox("Active tenders only", value=False)
    limit = st.selectbox("Records per page", [20, 50, 100], index=0)

    st.markdown("---")
    st.markdown("### AI Status")
    ai_status = fetch_ai_status()
    if ai_status.get("enabled"):
        st.success(f"Gemini {ai_status.get('model', 'AI')} active")
        st.caption(f"Free tier: {ai_status.get('free_tier_rpm', 15)} req/min")
    else:
        st.warning("AI enrichment inactive")

    st.markdown("---")
    st.caption(f"API: `{API_BASE}`")

# Parse optional value filters
min_value = float(min_val_input) if min_val_input.strip() else None
max_value = float(max_val_input) if max_val_input.strip() else None

# ── Pagination state ───────────────────────────────────────────────────────────
if "page" not in st.session_state:
    st.session_state.page = 0

offset = st.session_state.page * limit

# ── Fetch Data ─────────────────────────────────────────────────────────────────
stats = fetch_stats()
data = fetch_tenders(
    keyword=keyword or None,
    department=department or None,
    location=location or None,
    min_value=min_value,
    max_value=max_value,
    active_only=active_only,
    limit=limit,
    offset=offset,
)

# Reset page on filter change
filter_key = f"{keyword}{department}{location}{min_value}{max_value}{active_only}{limit}"
if "last_filter" not in st.session_state:
    st.session_state.last_filter = filter_key
if st.session_state.last_filter != filter_key:
    st.session_state.page = 0
    st.session_state.last_filter = filter_key
    st.rerun()

# ── KPI Cards ──────────────────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)

total_db = stats.get("total_tenders", 0)
active_db = stats.get("active_tenders", 0)
avg_val = stats.get("avg_estimated_value_inr", 0)
ai_enriched = stats.get("ai_enriched_count", 0)

col1.metric("Total Tenders", f"{total_db:,}")
col2.metric("Active Tenders", f"{active_db:,}")
col3.metric("Avg. Value", fmt_inr(avg_val) if avg_val else "—")
col4.metric("AI Enriched", f"{ai_enriched:,}" if ai_enriched else "—")

st.markdown("---")

results = data.get("results", [])
count = data.get("count", 0)
error = data.get("error")

if error:
    st.error(f"⚠️ Could not reach API: `{error}`\n\nMake sure `API_BASE_URL` is set correctly.")
    st.stop()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["Tender List", "Analytics", "API Reference"])

# ── Tab 1: Tender List ────────────────────────────────────────────────────────
with tab1:
    if not results:
        st.info("No tenders found for the current filters. Try broadening your search.")
    else:
        st.markdown(f"**Showing {offset + 1}–{offset + len(results)} of matching results** (page {st.session_state.page + 1})")

        for tender in results:
            active = is_active(tender.get("end_date"))
            status_badge = '<span class="badge-active">Active</span>' if active else '<span class="badge-closed">Closed</span>'

            tags_html = ""
            if tender.get("ai_tags"):
                for tag in tender["ai_tags"].split(","):
                    tag = tag.strip()
                    if tag:
                        tags_html += f'<span class="tag-pill">{tag}</span>'

            ai_badge = '<span class="badge-ai">AI Enriched</span>' if tender.get("ai_summary") else ""
            ai_block = f'<div class="tender-ai">{tender["ai_summary"]}</div>' if tender.get("ai_summary") else ""

            dept = tender.get("department") or "—"
            loc = tender.get("location") or "—"
            val = fmt_inr(tender.get("estimated_value_inr"))
            qty = tender.get("quantity", "—")
            bid_num = tender.get("bid_number", "—")
            src = tender.get("source_url", "#")

            card_html = f"""
            <div class="tender-card">
                <div style="display:flex; justify-content:space-between; align-items:flex-start;">
                    <div class="tender-title">{tender.get("title", "Untitled Tender")}</div>
                    <div>{status_badge} {ai_badge}</div>
                </div>
                <div class="tender-meta">
                    Dept: {dept} &nbsp;|&nbsp; Location: {loc} &nbsp;|&nbsp;
                    Value: {val} &nbsp;|&nbsp; Qty: {qty} &nbsp;|&nbsp;
                    Bid No: {bid_num}
                </div>
                {tags_html}
                {ai_block}
                <div style="margin-top:0.6rem;">
                    <a href="{src}" target="_blank" style="color:#3b82f6; font-size:0.8rem; text-decoration:none;">
                        View on GeM ↗
                    </a>
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

        # Pagination
        st.markdown("---")
        pcol1, pcol2, pcol3 = st.columns([1, 2, 1])
        with pcol1:
            if st.session_state.page > 0:
                if st.button("← Previous"):
                    st.session_state.page -= 1
                    st.rerun()
        with pcol2:
            st.markdown(f"<div style='text-align:center; color:#64748b;'>Page {st.session_state.page + 1}</div>", unsafe_allow_html=True)
        with pcol3:
            if len(results) == limit:
                if st.button("Next →"):
                    st.session_state.page += 1
                    st.rerun()

# ── Tab 2: Analytics ──────────────────────────────────────────────────────────
with tab2:
    if not results:
        st.info("Run a search first to see analytics for the current results.")
    else:
        df = pd.DataFrame(results)

        acol1, acol2 = st.columns(2)

        # Department breakdown
        with acol1:
            st.markdown("#### Tenders by Department")
            if "department" in df.columns:
                dept_df = (
                    df["department"]
                    .dropna()
                    .str.split("|").str[0]
                    .str.strip()
                    .value_counts()
                    .head(10)
                    .reset_index()
                )
                dept_df.columns = ["Department", "Count"]
                fig = px.bar(
                    dept_df,
                    x="Count",
                    y="Department",
                    orientation="h",
                    color="Count",
                    color_continuous_scale="Blues",
                    template="plotly_dark",
                )
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    coloraxis_showscale=False,
                    margin=dict(l=0, r=0, t=10, b=0),
                    yaxis=dict(autorange="reversed"),
                )
                st.plotly_chart(fig, use_container_width=True)

        # Value distribution
        with acol2:
            st.markdown("#### Estimated Value Distribution")
            val_df = df["estimated_value_inr"].dropna()
            if len(val_df) > 0:
                fig2 = px.histogram(
                    val_df,
                    nbins=20,
                    labels={"value": "Value (INR)"},
                    template="plotly_dark",
                    color_discrete_sequence=["#3b82f6"],
                )
                fig2.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    showlegend=False,
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis_title="Value (INR)",
                    yaxis_title="Tender Count",
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No value data available for current results.")

        # AI tags cloud
        st.markdown("#### Top AI-Generated Tags")
        all_tags: list[str] = []
        for r in results:
            if r.get("ai_tags"):
                all_tags.extend([t.strip() for t in r["ai_tags"].split(",") if t.strip()])

        if all_tags:
            tag_counts = pd.Series(all_tags).value_counts().head(20)
            fig3 = px.bar(
                x=tag_counts.values,
                y=tag_counts.index,
                orientation="h",
                color=tag_counts.values,
                color_continuous_scale="Purples",
                template="plotly_dark",
                labels={"x": "Count", "y": "Tag"},
            )
            fig3.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                showlegend=False,
                coloraxis_showscale=False,
                margin=dict(l=0, r=0, t=10, b=0),
                yaxis=dict(autorange="reversed"),
            )
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.info("No AI tags in current results. Run batch enrichment via the API to generate tags.")

        # Raw table
        st.markdown("#### Export Current Results")
        display_cols = [c for c in ["bid_number", "title", "department", "location",
                                     "estimated_value_inr", "quantity", "end_date",
                                     "ai_summary", "ai_tags"] if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, height=300)
        st.download_button(
            "Download as CSV",
            data=df[display_cols].to_csv(index=False),
            file_name="gem_tenders.csv",
            mime="text/csv",
        )

# ── Tab 3: API Reference ──────────────────────────────────────────────────────
with tab3:
    st.markdown(f"""
### Live API Endpoints

All endpoints are served from: `{API_BASE}`

| Method | Endpoint | Description |
|---|---|---|
| GET | [`/`]({API_BASE}/) | Welcome + links |
| GET | [`/health`]({API_BASE}/health) | Service health check |
| GET | [`/tenders`]({API_BASE}/tenders) | List tenders (supports filters) |
| GET | `/tenders/{{id}}` | Single tender by ID |
| GET | [`/stats/summary`]({API_BASE}/stats/summary) | Aggregated pipeline stats |
| GET | [`/ai/status`]({API_BASE}/ai/status) | Gemini AI configuration status |
| POST | `/tenders/{{id}}/enrich` | Enrich single tender with Gemini AI |
| POST | `/ai/enrich-batch` | Batch-enrich all unenriched tenders |

### Interactive Docs
- **Swagger UI**: [{API_BASE}/docs]({API_BASE}/docs)
- **ReDoc**: [{API_BASE}/redoc]({API_BASE}/redoc)

### Example Queries
```
# Active tenders from Ministry of Defence
GET /tenders?department=defence&active_only=true

# Laptop tenders under ₹5L
GET /tenders?keyword=laptop&max_value=500000

# High-value tenders
GET /tenders?min_value=10000000&limit=50
```
""")
