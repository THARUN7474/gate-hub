"""Apply agent-read classification labels (claude-agent-manual-v2) to a database.

Input: a TSV file, one line per question:
    question_id<TAB>primary_topic_id<TAB>confidence<TAB>flag(optional reason or '-')
Concept ids are taken from the local heuristic's matches within the chosen topic (may be []).
Safety: refuses to touch any question that already has a classification row (the v1 65, or
verified/validated rows); refuses taxonomy-invalid topic ids; writes provenance=inferred,
status=suggested|flagged only. Run row records provider=agent-analysis.

    python scripts/apply_agent_classifications.py DB_URL LABELS_TSV [--run-note NOTE]
"""
from __future__ import annotations
import argparse, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sqlalchemy import select  # noqa: E402
from src.db.session import make_session  # noqa: E402
from src.db.models import Classification, ClassificationRun, Question  # noqa: E402
from src.classification.heuristic import build_lexicon, advise_one  # noqa: E402
from src.classification.classify import combo_score  # noqa: E402
from src.taxonomy.taxonomy import valid_node_ids  # noqa: E402

MODEL = "claude-agent-manual-v2"
PROMPT_VERSION = "agent-v2"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("db_url"); ap.add_argument("labels_tsv")
    ap.add_argument("--run-note", default="agent manual pass (heuristic-assisted); NOT an LLM API integration run")
    ap.add_argument("--taxonomy-version", default="gate-cs-2027")
    a = ap.parse_args()

    lines = [l.rstrip("\n") for l in open(a.labels_tsv, encoding="utf-8") if l.strip()]
    parsed = []
    for i, l in enumerate(lines, 1):
        parts = l.split("\t")
        if len(parts) < 3:
            print(f"line {i}: bad format: {l!r}"); return 1
        qid, topic, conf = parts[0], parts[1], parts[2]
        flag = parts[3] if len(parts) > 3 and parts[3] != "-" else ""
        parsed.append((qid, topic, float(conf), flag))

    with make_session(a.db_url) as s:
        valid = valid_node_ids(s, a.taxonomy_version, include_deprecated=False)
        topics = {n for n in valid if s.query.__self__ and True}
        lex = build_lexicon(s, a.taxonomy_version)
        topic_parent = {t["node_id"]: t["parent_id"] for t in lex}
        run = ClassificationRun(model=MODEL, prompt_version=PROMPT_VERSION, provider="agent-analysis",
                                )
        s.add(run); s.flush()
        blocks, written, skipped, errors = {}, 0, 0, []
        for qid, topic, conf, flag in parsed:
            if topic not in topic_parent:
                errors.append(f"{qid}: invalid topic {topic}"); continue
            q = s.get(Question, qid)
            if q is None:
                errors.append(f"{qid}: no such question"); continue
            existing = s.scalars(select(Classification).where(Classification.question_id == qid)).all()
            if existing:
                skipped += 1; continue
            adv = advise_one(s, q, lex, blocks)
            concepts = []
            if adv["primary_topic_id"] == topic:
                concepts = adv["concept_ids"]
            row = Classification(question_id=qid, run_id=run.id, taxonomy_version=a.taxonomy_version,
                                 section_id=topic_parent[topic], primary_topic_id=topic,
                                 topic_weight={topic: 1.0}, concept_ids=concepts, prerequisite_ids=[],
                                 what_it_tests=None,  # honest missing: no per-question prose was recorded in the v2 pass
                                 confidence=conf, agreement=None, combo_score=combo_score(1.0, conf),
                                 provider_votes=None, provider_count=1,
                                 evidence_quote="; ".join(adv["evidence"][:5]),
                                 raw_response={"agent_flag": flag or None, "heuristic_topic": adv["primary_topic_id"],
                                               "heuristic_conf": adv["confidence"]},
                                 provenance="inferred", status="flagged" if flag else "suggested",
                                 model=MODEL, prompt_version=PROMPT_VERSION)
            s.add(row); written += 1
            if flag:
                from src.db.models import ReviewEvent
                s.add(ReviewEvent(question_id=qid, field="classification_flagged", before=None,
                                  after=flag, reviewer="agent-manual-v2",
                                  note="flagged during first-pass agent classification"))
        if errors:
            for e in errors: print("ERROR:", e)
            print("aborted, nothing committed"); return 1
        s.commit()
        print(f"written={written} skipped_existing={skipped} run_id={run.id}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
