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

_TH = 'style="padding:6px 8px; border-bottom:2px solid #888; text-align:center"'
_TD = 'style="padding:5px 8px; border-bottom:1px solid #4444; text-align:center"'
_TF = 'style="padding:6px 8px; border-top:2px solid #888; text-align:center; font-weight:700"'

def _num(v) -> str:
    return f"{round(v, 2):g}" if isinstance(v, float) else str(v)

def _label_cell(code: str, name: str | None) -> str:
    sub = (f'<br><span style="font-size:0.78em; opacity:0.7">{escape(name)}</span>' if name else "")
    return (f'<td style="padding:5px 8px; border-bottom:1px solid #4444; text-align:left" title="{escape(name or code)}">'
            f'<b>{escape(str(code))}</b>{sub}</td>')

def topic_matrix_html(rows: list[dict], names: dict | None = None) -> str:
    """Topic x year question-count matrix as an HTML table; every non-empty
    cell links to its drill-down; a bottom Total row sums each year and the
    bottom-right cell is the grand total. rows: analyze.topic_year_matrix()."""
    names = names or {}
    years = sorted({r["year"] for r in rows})
    piv: dict[str, dict] = {}
    for r in rows:
        piv.setdefault(r["topic"], {})[r["year"]] = r["questions"]
    out = ['<table style="border-collapse:collapse; width:100%">', "<thead><tr>",
           '<th style="text-align:left; padding:6px 8px; border-bottom:2px solid #888">Topic</th>']
    out += [f"<th {_TH}>{y}</th>" for y in years]
    out.append(f"<th {_TH}>Total</th></tr></thead><tbody>")
    col = {y: 0 for y in years}
    for t, d in sorted(piv.items()):
        out.append("<tr>" + _label_cell(t, names.get(t)))
        tot = 0
        for y in years:
            v = d.get(y)
            if v is None:
                out.append(f"<td {_TD}></td>")
            else:
                tot += v; col[y] += v
                out.append(f'<td {_TD}><a href="{topic_drill_href(t, y)}" target="_self">{v}</a></td>')
        out.append(f"<td {_TD}><b>{tot}</b></td></tr>")
    out.append("</tbody><tfoot><tr><td style=\"padding:6px 8px; border-top:2px solid #888; font-weight:700\">Total</td>")
    out += [f"<td {_TF}>{col[y]}</td>" for y in years]
    out.append(f"<td {_TF}>{sum(col.values())}</td></tr></tfoot></table>")
    return "".join(out)

def matrix_html(m: dict, names: dict | None = None, metric: str = "marks") -> str:
    """Section x year marks matrix as an HTML table; every non-empty cell is a
    link into its drill-down. A bottom Total row sums each year's column and the
    bottom-right cell is the grand total. metric: 'marks' or 'questions'.
    Input shape: analyze.section_year_matrix()."""
    names = names or {}
    years = m["years"]
    out = ['<table style="border-collapse:collapse; width:100%">', "<thead><tr>",
           '<th style="text-align:left; padding:6px 8px; border-bottom:2px solid #888">Section</th>']
    out += [f"<th {_TH}>{y}</th>" for y in years]
    out.append(f"<th {_TH}>Total</th></tr></thead><tbody>")
    col = {y: 0 for y in years}
    grand = 0
    for sec, d in m["sections"].items():
        out.append("<tr>" + _label_cell(sec, names.get(sec)))
        for y in years:
            cell = d["years"].get(y, {})
            marks = cell.get(metric)
            if marks is None:
                out.append(f"<td {_TD}></td>")
            else:
                col[y] += marks
                out.append(
                    f'<td {_TD}><a href="{drill_href(sec, y)}" target="_self" '
                    f'title="{cell.get("questions", 0)} questions, {cell.get("marks", 0):g} marks - click to drill down">'
                    f'{marks:g}</a></td>')
        _rt = d["total_q" if metric == "questions" else "total_marks"]
        grand += _rt
        out.append(f'<td {_TD}><b>{_num(_rt)}</b></td></tr>')
    out.append("</tbody><tfoot><tr><td style=\"padding:6px 8px; border-top:2px solid #888; font-weight:700\">Total</td>")
    out += [f"<td {_TF}>{_num(col[y])}</td>" for y in years]
    out.append(f"<td {_TF}>{_num(grand)}</td></tr></tfoot></table>")
    return "".join(out)

def drill_list_html(question_ids: list[str]) -> str:
    """Drill-down contributors as links into the Review Workspace."""
    lis = "".join(
        f'<li><a href="{review_href(q)}" target="_self">{escape(str(q))}</a></li>'
        for q in question_ids)
    return (f'<p><a href="?" target="_self">&larr; back to full matrix</a></p>'
            f"<ul>{lis}</ul>")
