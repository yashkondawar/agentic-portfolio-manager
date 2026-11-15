"""Meridian visual system, shared by the shell, dashboards and charts."""

from contextlib import contextmanager
from html import escape
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

ACCENT = "#087f5b"
INK = "#08120f"
MUTED = "#4c6058"
PALETTE = [ACCENT, "#647bc0", "#bd8c49", "#927eb2", "#438f99", "#be676b"]


@contextmanager
def card(*, key: str | None = None):
    with st.container(border=True, key=key):
        st.markdown(
            '<span class="meridian-card-marker"></span>', unsafe_allow_html=True
        )
        yield


def brand_markup() -> str:
    return (
        '<div class="meridian-brand"><span class="meridian-mark" aria-hidden="true">'
        '<svg viewBox="0 0 32 32" fill="none"><path d="M6 24V16h5v8H6Zm8 0V10h5v14h-5Zm8 0V4h5v20h-5Z" '
        'fill="currentColor"/></svg></span><div><strong>Portfolio</strong>'
        "<small>THE INVESTOR WORKSPACE</small></div></div>"
    )


def empty_state(title: str, description: str) -> None:
    st.markdown(
        '<div class="meridian-empty-state"><span class="empty-symbol" aria-hidden="true">'
        '<svg viewBox="0 0 32 32" fill="none"><rect x="5" y="7" width="22" height="20" rx="4" '
        'stroke="currentColor" stroke-width="1.5"/><path d="M11 5v4m10-4v4M11 16h10m-10 5h6" '
        'stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></span>'
        f"<strong>{escape(title)}</strong><p>{escape(description)}</p></div>",
        unsafe_allow_html=True,
    )


def apply_theme() -> None:
    css = Path(__file__).with_name("meridian.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    pio.templates["meridian"] = go.layout.Template(
        layout={
            "font": {"family": "Segoe UI, sans-serif", "color": INK, "size": 14},
            "paper_bgcolor": "#ffffff",
            "plot_bgcolor": "#ffffff",
            "colorway": PALETTE,
            "xaxis": {
                "showgrid": False,
                "zeroline": False,
                "color": MUTED,
                "tickfont": {"size": 14},
            },
            "yaxis": {
                "gridcolor": "#e8eeea",
                "zeroline": False,
                "color": MUTED,
                "tickfont": {"size": 14},
            },
            "hoverlabel": {
                "bgcolor": INK,
                "font": {"color": "#ffffff", "size": 14},
            },
        }
    )
    pio.templates.default = "meridian"


def badge(text: str, *, warning: bool = False) -> str:
    tone = " warning" if warning else ""
    return f'<span class="meridian-badge{tone}">{escape(text)}</span>'


def money(value: float | None) -> str:
    if value is None:
        return "Not available"
    # Indian digit grouping, without rounding a small P&L to zero.
    sign = "-" if value < 0 else ""
    whole, fraction = f"{abs(value):.2f}".split(".")
    tail, head = whole[-3:], whole[:-3]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    return f"{sign}\u20b9{','.join([*groups, tail])}.{fraction}"


def style_chart(figure: go.Figure, *, height: int = 290) -> go.Figure:
    figure.update_layout(
        template=(
            pio.templates["meridian"] if "meridian" in pio.templates else "plotly_white"
        ),
        height=height,
        margin={"l": 20, "r": 16, "t": 20, "b": 24},
        hovermode="x unified",
        legend={"orientation": "h", "y": 1.15, "x": 0},
        font={"family": "Segoe UI, sans-serif", "color": INK, "size": 14},
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
    )
    figure.update_xaxes(automargin=True)
    figure.update_yaxes(automargin=True, side="right")
    return figure
