"""Local heuristic classifier: offline, honest provenance, taxonomy-safe."""
from sqlalchemy import select

from src.classification.heuristic import run_local_classify
from src.db.models import Classification, Question
from src.db.session import make_session
from src.taxonomy.taxonomy import valid_node_ids


def _set_texts(db_url):
    with make_session(db_url) as s:
        qs = s.scalars(select(Question)).all()
        qs[0].text = "Which of the following is a regular expression over {a, b}?"
        qs[1].text = "The number of states in a minimal DFA accepting the language"
        qs[2].text = "zzqx qvkv jjjj wqkx"  # no keyword signal
        s.commit()


def test_heuristic_writes_inferred_never_verified(loaded):
    db_url, pid, _ = loaded
    _set_texts(db_url)
    with make_session(db_url) as s:
        out = run_local_classify(s, "gate-cs-2027")
        rows = s.scalars(select(Classification)).all()
        valid = valid_node_ids(s, "gate-cs-2027", include_deprecated=False)
    assert out.get("written_suggested", 0) + out.get("written_flagged", 0) > 0
    assert rows, "expected classification rows"
    for r in rows:
        assert r.provenance == "inferred"
        assert r.status in ("suggested", "flagged")
        assert r.model == "local-heuristic-v1"
        assert r.primary_topic_id in valid


def test_heuristic_never_overwrites_verified(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        q = s.scalars(select(Question)).first()
        row = Classification(question_id=q.id, taxonomy_version="gate-cs-2027",
                             prompt_version="human", section_id="TOC", primary_topic_id="TOC.REG",
                             provenance="verified", status="verified", model="human",
                             confidence=1.0)
        s.add(row)
        s.commit()
        out = run_local_classify(s, "gate-cs-2027", reclassify=True)
        s.refresh(row)
        assert row.model == "human" and row.provenance == "verified"


def test_heuristic_flags_weak_or_no_signal(loaded):
    db_url, pid, _ = loaded
    _set_texts(db_url)
    with make_session(db_url) as s:
        out = run_local_classify(s, "gate-cs-2027", flag_below=0.45)
    assert out.get("no_signal", 0) + out.get("written_flagged", 0) > 0
