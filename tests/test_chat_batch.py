"""Chat-assisted (no API) classification: export a batch, validate and import the chat's JSON as suggestions only."""
import json
from pathlib import Path
import pytest
from sqlalchemy import select
from src.classification import chat_batch as cb
from src.db.models import Classification, ClassificationRun, Question, ReviewEvent
from src.db.session import make_session
from src.validation import review as rv

def good(qid, **kw):
    d = {"question_id": qid, "section_id": "ALGO", "primary_topic_id": "ALGO.SORT", "secondary_topic_ids": ["ALGO.GRAPH"],
         "concept_ids": ["ALGO.SORT.HASH"], "prerequisite_ids": [], "what_it_tests": "hashing", "evidence": "hash table",
         "confidence": 0.9, "needs_review": False, "review_reason": ""}
    d.update(kw); return d

@pytest.fixture()
def batch(loaded, tmp_path):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        r = cb.export_batch(s, tmp_path / "batches", paper_id=pid, size=6, images=False)
    return db_url, pid, Path(r["batch_dir"]), r

def write(tmp_path, obj, name="answers.json"):
    p = tmp_path / name; p.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8"); return p

def test_export_writes_a_complete_batch(batch):
    db_url, pid, d, r = batch
    assert r["questions"] == 6 and {p.name for p in d.iterdir()} >= {"batch.json", "prompt.md", "answers_template.json", "images"}
    m = json.loads((d / "batch.json").read_text(encoding="utf-8"))
    assert [q["question_id"] for q in m["questions"]] == [f"{pid}-Q0{i}" for i in range(1, 7)]
    assert all(len(q["source_hash"]) == 64 and q["source"]["document_sha256"] for q in m["questions"])
    prompt = (d / "prompt.md").read_text(encoding="utf-8")
    assert "ALGO.SORT" in prompt and "<question>" in prompt and "needs_review" in prompt and "Official answer" in prompt
    t = json.loads((d / "answers_template.json").read_text(encoding="utf-8"))
    assert t["batch_id"] == m["batch_id"] and len(t["classifications"]) == 6

def test_export_size_limits_and_skips_classified(loaded, tmp_path):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        for bad in (0, 26):
            with pytest.raises(ValueError):
                cb.export_batch(s, tmp_path, paper_id=pid, size=bad, images=False)
        s.add(Classification(question_id=f"{pid}-Q01", taxonomy_version="gate-cs-2027", prompt_version="agent-v1",
                             section_id="ALGO", primary_topic_id="ALGO.SORT", model="x", status="suggested"))
        s.flush()
        r = cb.export_batch(s, tmp_path, paper_id=pid, size=25, images=False)
        assert r["questions"] == 5 and r["first"] == f"{pid}-Q02"

def test_export_renders_source_images(loaded, tmp_path):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        r = cb.export_batch(s, tmp_path, paper_id=pid, size=2, images=True)
    imgs = list((Path(r["batch_dir"]) / "images").glob("*.png"))
    assert r["images"] == len(imgs) and len(imgs) >= 2 and imgs[0].read_bytes()[:4] == b"\x89PNG"

def test_dry_run_writes_nothing_and_apply_writes_suggestions_only(batch, tmp_path):
    db_url, pid, d, r = batch
    ans = write(tmp_path, {"batch_id": r["batch_id"], "model_or_agent": "ChatGPT GPT-5 (chat)",
                           "classifications": [good(f"{pid}-Q0{i}") for i in range(1, 7)]})
    with make_session(db_url) as s:
        rep = cb.import_answers(s, d, ans)
        assert rep["new"] == 6 and rep["rejected"] == 0 and not rep["applied"]
        assert s.scalar(select(Classification.id)) is None                       # validation only
        rep = cb.import_answers(s, d, ans, apply=True)
        s.commit()
        rows = s.scalars(select(Classification)).all()
    assert rep["applied"] and len(rows) == 6
    assert {(c.status, c.provenance, c.prompt_version, c.model) for c in rows} == {
        ("suggested", "inferred", "chat-v1", "ChatGPT GPT-5 (chat)")}
    assert all(set(c.topic_weight) == {"ALGO.SORT", "ALGO.GRAPH"} and c.raw_response["batch_id"] == r["batch_id"] for c in rows)
    with make_session(db_url) as s:
        run = s.scalar(select(ClassificationRun).where(ClassificationRun.provider == "chat-assisted"))
        assert run.stats["imported"] == 6 and len(run.stats["answers_sha256"]) == 64

def test_every_bad_answer_is_rejected_with_a_reason(batch, tmp_path):
    db_url, pid, d, r = batch
    items = [good(f"{pid}-Q01", primary_topic_id="ALGO.NOPE"),                       # unknown id
             good(f"{pid}-Q02", section_id="DB"),                                   # topic not under section
             good(f"{pid}-Q03", concept_ids=["MADE.UP"]),                           # unknown concept
             good(f"{pid}-Q04", confidence=3),                                      # wrong shape
             good(f"{pid}-Q05"), good(f"{pid}-Q05"),                                # duplicate
             good("GATE-CS-1999-S1-Q01"),                                           # not in batch
             {"question_id": f"{pid}-Q06"}]                                         # missing fields
    ans = write(tmp_path, {"batch_id": r["batch_id"], "model_or_agent": "claude (chat)", "classifications": items})
    with make_session(db_url) as s:
        rep = cb.import_answers(s, d, ans, apply=True)
        why = {x["question_id"]: x.get("why", "") for x in rep["rows"] if x["action"] == "reject"}
        assert rep["rejected"] == 7 and rep["new"] == 1
        assert "unknown or deprecated" in why[f"{pid}-Q01"] and "not under section" in why[f"{pid}-Q02"]
        assert "MADE.UP" in why[f"{pid}-Q03"] and "confidence" in why[f"{pid}-Q04"]
        assert "twice" in why[f"{pid}-Q05"] and "not in this batch" in why["GATE-CS-1999-S1-Q01"]
        assert s.scalar(select(Classification.question_id)) == f"{pid}-Q05"         # only the good one imported

def test_changed_source_and_wrong_batch_and_missing_model_are_refused(batch, tmp_path):
    db_url, pid, d, r = batch
    with make_session(db_url) as s:
        s.get(Question, f"{pid}-Q01").text += " edited after export"; s.commit()
        rep = cb.import_answers(s, d, write(tmp_path, {"model_or_agent": "x", "classifications": [good(f"{pid}-Q01")]}))
        assert "changed since export" in rep["rows"][0]["why"]
        with pytest.raises(ValueError, match="wrong file"):
            cb.import_answers(s, d, write(tmp_path, {"batch_id": "other", "model_or_agent": "x", "classifications": []}))
        with pytest.raises(ValueError, match="which chat model"):
            cb.import_answers(s, d, write(tmp_path, {"classifications": [good(f"{pid}-Q02")]}))

def test_human_work_is_never_overwritten(batch, tmp_path):
    db_url, pid, d, r = batch
    from src.classification import classify as cl
    with make_session(db_url) as s:
        cl.run_classification(s, cl.MockProvider(), "gate-cs-2027", pid)
        rv.save_rubric(s, f"{pid}-Q01", {k: 1 for k in rv.RUBRIC_KEYS}, "owner")
        rv.set_status(s, f"{pid}-Q01", "verified", "owner")                          # verified
        rv.apply_decision(s, f"{pid}-Q02", "primary_topic_id", "ALGO.GRAPH", "owner")  # corrected, not verified
        s.commit()
        ans = write(tmp_path, {"model_or_agent": "x", "classifications": [good(f"{pid}-Q0{i}") for i in range(1, 4)]})
        rep = cb.import_answers(s, d, ans, apply=True, replace_unverified=True)
        acts = {x["question_id"]: x["action"] for x in rep["rows"]}
        assert acts == {f"{pid}-Q01": "skip", f"{pid}-Q02": "skip", f"{pid}-Q03": "replace"}
        s.commit()
        st = {c.question_id: (c.status, c.primary_topic_id, c.prompt_version) for c in s.scalars(select(Classification))}
        assert st[f"{pid}-Q01"][0] == "verified" and st[f"{pid}-Q02"][1] == "ALGO.GRAPH"
        assert st[f"{pid}-Q03"][2] == "chat-v1" and len(st) == 6                      # replaced in place, no 2nd row
        assert s.scalar(select(ReviewEvent).where(ReviewEvent.field == "classification_replaced",
                                                  ReviewEvent.question_id == f"{pid}-Q03")) is not None
        rep = cb.import_answers(s, d, write(tmp_path, {"model_or_agent": "x", "classifications": [good(f"{pid}-Q04")]}))
        assert rep["rows"][0]["action"] == "skip" and "already has a suggestion" in rep["rows"][0]["why"]

def test_review_requests_and_low_confidence_become_flagged(batch, tmp_path):
    db_url, pid, d, r = batch
    ans = write(tmp_path, "```json\n" + json.dumps([
        good(f"{pid}-Q01", needs_review=True, review_reason="figure unreadable"),
        good(f"{pid}-Q02", confidence=0.3)]) + "\n```")                              # fenced + bare list tolerated
    with make_session(db_url) as s:
        rep = cb.import_answers(s, d, ans, model_label="ChatGPT (chat)", apply=True)
        s.commit()
        assert rep["flagged"] == 2
        st = dict(s.execute(select(Classification.question_id, Classification.status)).all())
        assert st == {f"{pid}-Q01": "flagged", f"{pid}-Q02": "flagged"}
        assert "figure unreadable" in s.get(Question, f"{pid}-Q01").review_reason

def test_cli_round_trip(loaded, tmp_path):
    from typer.testing import CliRunner
    from src.cli import app
    db_url, pid, _ = loaded
    out = tmp_path / "b"
    r = CliRunner().invoke(app, ["chat-export", "--paper-id", pid, "--size", "3", "--no-images", "--out", str(out), "--db-url", db_url])
    assert r.exit_code == 0 and "3 questions" in r.output
    d = next(out.iterdir())
    ans = write(tmp_path, {"model_or_agent": "x", "classifications": [good(f"{pid}-Q0{i}") for i in (1, 2, 3)]})
    r = CliRunner().invoke(app, ["chat-import", str(d), str(ans), "--db-url", db_url])
    assert r.exit_code == 0 and "VALIDATION ONLY" in r.output and "3 new" in r.output
    r = CliRunner().invoke(app, ["chat-export", "--size", "40", "--db-url", db_url])
    assert r.exit_code == 2
