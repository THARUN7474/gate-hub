"""Clickable navigation helpers (v6). The Analysis Matrix renders as real HTML
links: a cell click deep-links to that cell's drill-down, and each drill-down
question deep-links into the Review Workspace. Pure functions so tests cover
them without a browser. Values are HTML-escaped and URL-encoded."""
from __future__ import annotations
from html import escape
from urllib.parse import quote

def drill_href(section_id: str, year: int) -> str:
    return f"?drill_sec={quote(str(section_id))}&drill_year={int(year)}"

def review_href(question_id: str) -> str:
    return f"?review_q={quote(str(question_id))}"

def parse_drill_params(params) -> tuple[str | None, int | None]:
    """params: st.query_params-like mapping. Returns (section_or_topic, year)
    or (None, None) when absent/invalid. drill_topic carries a topic id."""
    sec = params.get("drill_sec") or params.get("drill_topic")
    yr = params.get("drill_year")
    try:
        return (str(sec), int(yr)) if sec and yr else (None, None)
    except (TypeError, ValueError):
        return (None, None)

def topic_drill_href(topic: str, year: int) -> str:
    return f"?drill_topic={escape(str(topic))}&drill_year={year}"

def topic_matrix_html(rows: list[dict], names: dict | None = None) -> str:
    """Topic x year question-count matrix as an HTML table; every non-empty
    cell links to its drill-down. rows: analyze.topic_year_matrix()."""
    names = names or {}
    years = sorted({r["year"] for r in rows})
    piv: dict[str, dict] = {}
    for r in rows:
        piv.setdefault(r["topic"], {})[r["year"]] = r["questions"]
    out = ['<table style="border-collapse:collapse; width:100%">', "<thead><tr>",
           '<th style="text-align:left; padding:4px 8px; border-bottom:2px solid #ccc">Topic</th>']
    for y in years:
        out.append(f'<th style="padding:4px 8px; border-bottom:2px solid #ccc">{y}</th>')
    out.append('<th style="padding:4px 8px; border-bottom:2px solid #ccc">Total</th></tr></thead><tbody>')
    for t, d in sorted(piv.items()):
        label = f"{t} - {names[t]}" if names.get(t) else t
        out.append(f'<tr><td style="padding:4px 8px; border-bottom:1px solid #eee">'
                   f'<b>{escape(label)}</b></td>')
        tot = 0
        for y in years:
            v = d.get(y)
            if v is None:
                out.append('<td style="padding:4px 8px; border-bottom:1px solid #eee"></td>')
            else:
                tot += v
                out.append(f'<td style="padding:4px 8px; border-bottom:1px solid #eee; text-align:center">'
                           f'<a href="{topic_drill_href(t, y)}" target="_self">{v}</a></td>')
        out.append(f'<td style="padding:4px 8px; border-bottom:1px solid #eee; text-align:center"><b>{tot}</b></td></tr>')
    out.append("</tbody></table>")
    return "".join(out)

def matrix_html(m: dict) -> str:
    """Section x year marks matrix as an HTML table; every non-empty cell is a
    link into its drill-down. Input shape: analyze.section_year_matrix()."""
    years = m["years"]
    out = ['<table style="border-collapse:collapse; width:100%">', "<thead><tr>",
           '<th style="text-align:left; padding:4px 8px; border-bottom:2px solid #ccc">Section</th>']
    for y in years:
        out.append(f'<th style="padding:4px 8px; border-bottom:2px solid #ccc">{y}</th>')
    out.append('<th style="padding:4px 8px; border-bottom:2px solid #ccc">Total</th></tr></thead><tbody>')
    for sec, d in m["sections"].items():
        out.append(f'<tr><td style="padding:4px 8px; border-bottom:1px solid #eee">'
                   f'<b>{escape(str(sec))}</b></td>')
        for y in years:
            cell = d["years"].get(y, {})
            marks = cell.get("marks")
            if marks is None:
                out.append('<td style="padding:4px 8px; border-bottom:1px solid #eee"></td>')
            else:
                out.append(
                    f'<td style="padding:4px 8px; border-bottom:1px solid #eee; text-align:center">'
                    f'<a href="{drill_href(sec, y)}" target="_self" '
                    f'title="{cell.get("questions", 0)} questions - click to drill down">'
                    f'{marks:g}</a></td>')
        out.append(f'<td style="padding:4px 8px; border-bottom:1px solid #eee; text-align:center">'
                   f'<b>{d["total_marks"]:g}</b></td></tr>')
    out.append("</tbody></table>")
    return "".join(out)

def drill_list_html(question_ids: list[str]) -> str:
    """Drill-down contributors as links into the Review Workspace."""
    lis = "".join(
        f'<li><a href="{review_href(q)}" target="_self">{escape(str(q))}</a></li>'
        for q in question_ids)
    return (f'<p><a href="?" target="_self">&larr; back to full matrix</a></p>'
            f"<ul>{lis}</ul>")
