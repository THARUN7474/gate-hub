"""Glossary: human-readable expansions of every short code shown in the app
(sections like GA, topics like SORT, concepts like HASH), built at runtime
from taxonomy.yaml so the long forms never drift from the data.

Provenance layers are kept distinct, same as the taxonomy loader:
- Sections: official - syllabus_text is verbatim from the GATE syllabus PDF.
- Topics and concepts: inferred - a curation split of the official text,
  pending owner review (the GA note and deprecated ids are carried through).
"""
from __future__ import annotations

from .taxonomy import load_taxonomy

OFFICIAL = "official (verbatim GATE syllabus text)"
INFERRED = "inferred (curation split of the official text)"


def build_glossary(path: str) -> dict:
    tax = load_taxonomy(path)
    sections, topics, concepts, notes = [], [], [], []
    for sec in tax.get("sections", []):
        stext = " ".join(sec.get("syllabus_text", "").split())
        sections.append({
            "Code": sec["id"],
            "Full name": sec["name"],
            "What it covers (official syllabus text, verbatim)": stext,
            "Provenance": OFFICIAL,
        })
        if sec.get("syllabus_note"):
            notes.append(f'{sec["id"]}: {sec["syllabus_note"]}')
        for top in sec.get("topics", []) or []:
            short = top["id"][len(sec["id"]) + 1:]
            prov = INFERRED
            if top.get("deprecated"):
                prov = ("inferred - DEPRECATED: superseded id, kept only so "
                        "older data still resolves")
            topics.append({
                "Short code": short,
                "Full code": top["id"],
                "Full name / what it covers": top["name"],
                "Section": f'{sec["id"]} - {sec["name"]}',
                "Provenance": prov,
            })
            for con in top.get("concepts", []) or []:
                cshort = con["id"][len(top["id"]) + 1:]
                concepts.append({
                    "Short code": cshort,
                    "Full code": con["id"],
                    "Full name / what it covers": con["name"],
                    "Topic": f'{top["id"]} - {top["name"]}',
                    "Provenance": INFERRED,
                })
    return {
        "sections": sections,
        "topics": topics,
        "concepts": concepts,
        "structure_notes": notes,
        "syllabus_year": tax.get("syllabus_year"),
        "source_pdf": tax.get("source_pdf"),
    }


def index(glossary: dict) -> dict:
    """Full-code -> (short_code, expansion, provenance) lookup."""
    idx = {}
    for row in glossary["sections"]:
        idx[row["Code"]] = (row["Code"], row["Full name"], row["Provenance"])
    for row in glossary["topics"]:
        idx[row["Full code"]] = (
            row["Short code"],
            f'{row["Full name / what it covers"]} - {row["Section"]}',
            row["Provenance"])
    for row in glossary["concepts"]:
        idx[row["Full code"]] = (
            row["Short code"],
            f'{row["Full name / what it covers"]} - {row["Topic"]}',
            row["Provenance"])
    return idx


def describe_codes(glossary: dict, codes: list[str]) -> list[dict]:
    """Resolve codes as displayed in the app (e.g. 'GA', 'ALGO.SORT',
    'DB.NF.NF') to their expansions. Unknown codes are kept visible and
    marked as not found rather than silently dropped."""
    idx = index(glossary)
    out = []
    for code in codes:
        if not code:
            continue
        hit = idx.get(code)
        if hit:
            short, expansion, prov = hit
            out.append({"Code": code, "Meaning": expansion, "Provenance": prov})
        else:
            out.append({"Code": code, "Meaning": "(not in the taxonomy)",
                        "Provenance": "unknown"})
    return out


def hover_legend_html(glossary: dict, codes: list[str]) -> str:
    """Inline badges with native browser tooltips: hovering a short code on
    desktop shows its expansion. On touch screens there is no hover, so this
    always sits next to a tappable expander with the same information."""
    idx = index(glossary)
    badges = []
    for code in codes:
        if not code:
            continue
        hit = idx.get(code)
        tip = f"{hit[1]} [{hit[2]}]" if hit else "(not in the taxonomy)"
        tip = tip.replace('"', "&quot;").replace("<", "&lt;")
        badges.append(
            f'<abbr title="{tip}" style="cursor:help; text-decoration:underline dotted; '
            f'margin-right:10px; white-space:nowrap;">{code}</abbr>')
    return ("<span style='font-size:0.85em; color:#555;'>Hover a code for its meaning: "
            + " ".join(badges) + "</span>")
