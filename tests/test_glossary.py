"""Glossary module: expansions resolve, provenance layers stay distinct."""
from src.taxonomy import glossary as glos

G = glos.build_glossary("taxonomy.yaml")

def test_counts_and_official_sections():
    official = [x for x in G["sections"] if x["Provenance"].startswith("official")]
    assert len(official) == 11                                   # the 2027 syllabus sections
    assert [x["Code"] for x in G["sections"] if not x["Provenance"].startswith("official")] == ["LEGACY"]
    assert len(G["topics"]) > 40 and len(G["concepts"]) > 90
    ga = next(s for s in G["sections"] if s["Code"] == "GA")
    assert ga["Full name"] == "General Aptitude"
    assert ga["Provenance"].startswith("official")
    assert "Verbal Aptitude" in ga["What it covers (official syllabus text, verbatim)"]

def test_sort_scope_is_searching_sorting_hashing():
    sort = next(t for t in G["topics"] if t["Full code"] == "ALGO.SORT")
    assert sort["Full name / what it covers"] == "Searching, sorting, hashing"

def test_deprecated_and_structure_notes():
    pump = next(t for t in G["topics"] if t["Full code"] == "TOC.PUMP")
    assert "DEPRECATED" in pump["Provenance"]
    assert any("structure is curation" in n for n in G["structure_notes"])

def test_describe_codes_and_unknown():
    rows = {r["Code"]: r for r in glos.describe_codes(G, ["GA", "ALGO.SORT", "DB.NF.NF", "ZZZ"])}
    assert rows["GA"]["Meaning"] == "General Aptitude"
    assert "Searching, sorting, hashing" in rows["ALGO.SORT"]["Meaning"]
    assert "Normal forms" in rows["DB.NF.NF"]["Meaning"]
    assert rows["ZZZ"]["Provenance"] == "unknown"

def test_hover_legend_escapes_and_labels():
    html = glos.hover_legend_html(G, ["GA"])
    assert '<abbr title="General Aptitude' in html
    assert '"' not in html.split("General Aptitude")[1].split("]")[0]
