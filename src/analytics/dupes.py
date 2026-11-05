"""Duplicate question papers (special cases), computed from the data - never hand-listed.

GATE 2013 CS was ONE exam printed in four shuffled sets; the repository stores all four (GATE-CS-2013-S1..S4),
so sets 2-4 repeat set 1 question for question. We KEEP every copy (the totals stay 1,885 and every paper still
reconciles to 65 questions / 100 marks), but:
  * every copy points at its ORIGINAL (the same question in the earliest set of that year);
  * reviews and classification (human review, gold set, AI review, API proposals, decision models) work on
    originals only - a copy follows its original;
  * every screen that shows totals says how many are copies ("1,885 = 1,690 unique + 195 copies").

Matching: same year, different paper, same marks, and the normalised question text + options are >= 85% similar
(text alone is not enough - many stems are just 'Which one of the following is TRUE?'). One-to-one per paper."""
from __future__ import annotations
import difflib
import re
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db.models import Option, Paper, Question, ReviewEvent

THRESHOLD = 0.85
_CACHE: dict = {}


_JUNK = re.compile(r"end of (the )?question paper|computer science and information technology|"
                   r"number of questions|section marks|options ?:", re.I)


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", _JUNK.sub(" ", s or "").lower())


def _key(s: Session) -> tuple:
    return (str(s.get_bind().url), s.scalar(select(func.count()).select_from(Question)),
            s.scalar(select(func.max(ReviewEvent.id)).where(ReviewEvent.field == "text")))


def duplicate_map(s: Session) -> dict:
    """{'copy_of': {copy_id: original_id}, 'copies_by_paper': {paper: n}, 'years': {year: [papers]},
    'unique': int, 'total': int}. Cached per database until questions or text corrections change."""
    k = _key(s)
    if _CACHE.get("key") == k:
        return _CACHE["val"]
    opts: dict[str, str] = defaultdict(str)
    for qid, content in s.execute(select(Option.question_id, Option.content).order_by(Option.question_id, Option.label)):
        opts[qid] += " " + (content or "")
    rows = s.execute(select(Question.id, Question.paper_id, Paper.year, Question.marks, Question.text)
                     .join(Paper, Paper.id == Question.paper_id).order_by(Question.paper_id, Question.q_number)).all()
    by_year: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for qid, pid, year, marks, text in rows:
        own = (text or "").split("|")[-1]          # common-data questions: match the sub-question, not the shared passage
        by_year[year][pid].append((qid, marks, _norm(own + opts.get(qid, ""))[:400]))
    copy_of: dict[str, str] = {}
    years: dict[int, list] = {}
    for year, papers in by_year.items():
        names = sorted(papers)
        if len(names) < 2:
            continue
        first = papers[names[0]]
        for later in names[1:]:
            cands = []                       # every plausible pair, then best pairs first (one-to-one)
            for qid, marks, t in papers[later]:
                if len(t) < 20:
                    continue
                for oid, omarks, ot in first:
                    if omarks != marks:
                        continue
                    sm = difflib.SequenceMatcher(None, t, ot, autojunk=False)
                    if sm.real_quick_ratio() < THRESHOLD or sm.quick_ratio() < THRESHOLD:
                        continue
                    r = sm.ratio()
                    if r >= THRESHOLD:
                        cands.append((r, qid, oid))
            used_c, used_o = set(), set()
            for r, qid, oid in sorted(cands, reverse=True):
                if qid not in used_c and oid not in used_o:
                    copy_of[qid] = oid
                    used_c.add(qid); used_o.add(oid)
            if any(q[0] in copy_of for q in papers[later]):
                years.setdefault(year, [names[0]])
                years[year].append(later)
    by_paper: dict[str, int] = defaultdict(int)
    for c in copy_of:
        by_paper[c.rsplit("-", 1)[0]] += 1
    val = {"copy_of": copy_of, "copies_by_paper": dict(by_paper), "years": years,
           "total": len(rows), "unique": len(rows) - len(copy_of)}
    _CACHE.update(key=k, val=val)
    return val


def copies_of(s: Session, original_id: str) -> list[str]:
    return sorted(c for c, o in duplicate_map(s)["copy_of"].items() if o == original_id)


def summary_line(s: Session) -> str:
    d = duplicate_map(s)
    if not d["copy_of"]:
        return f"{d['total']:,} questions, all unique."
    parts = []
    for year, papers in sorted(d["years"].items()):
        n = sum(d["copies_by_paper"].get(p, 0) for p in papers[1:])
        parts.append(f"{year}: sets {', '.join(p.rsplit('S', 1)[-1] for p in papers[1:])} repeat set "
                     f"{papers[0].rsplit('S', 1)[-1]} ({n} copies)")
    return (f"{d['total']:,} questions loaded = **{d['unique']:,} unique** + {len(d['copy_of']):,} duplicate copies "
            f"({'; '.join(parts)}).")


def special_cases_md(s: Session) -> str:
    d = duplicate_map(s)
    rows = []
    for year, papers in sorted(d["years"].items()):
        for p in papers[1:]:
            rows.append(f"| {year} | `{p}` | copy of `{papers[0]}` | {d['copies_by_paper'].get(p, 0)} of 65 |")
    table = ("| Year | Paper | Status | Questions that repeat |\n|---|---|---|---|\n" + "\n".join(rows)) if rows else ""
    return (
        "**Duplicate question papers**\n\n" + summary_line(s) + "\n\n" + table + "\n\n"
        "- **Why:** GATE 2013 CS was a single exam printed in four shuffled sets. All four sets were loaded, so "
        "sets 2-4 repeat set 1 (same questions, different order and numbering).\n"
        "- **What we keep:** every copy stays in the database, every paper still reconciles to 65 questions / "
        "100 marks, and the default totals (1,885 questions, 2,900 marks) include the copies.\n"
        "- **What changes:** human review, the gold set, AI review, API proposals and decision models work on "
        "the **original** only. When you verify an original, its copies get the same label automatically "
        "(audited as 'follows original'). The Analysis Matrix can count copies or unique questions only.\n"
        "- **How it is found:** same year, same marks, question text + options at least 85% similar - "
        "computed from the data each time, never a hand-made list. Other years were checked: no repeats "
        "(similar stems like 'Which one of the following is TRUE?' do not count because the options differ).\n"
        "- **Repeats across different years** (a GA question re-used years later) are not treated as "
        "duplicates: they are separate exam appearances.")
