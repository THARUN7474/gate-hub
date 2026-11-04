"""v7.3 run safety, fully offline (fake transports + fake clock, no network, no key, no spend):
actual token accounting, pacing, conservative retry, stop on quota/billing/auth, call cap, checkpoints, resume,
year selection, evenly spread sampling, and 'an AI run can never mark anything human-verified'."""
import json
import pytest
from sqlalchemy import func, select
from src.classification import classify as cl
from src.db.models import Classification, Question
from src.db.session import make_session

GOOD = {"section_id": "ALGO", "primary_topic_id": "ALGO.SORT", "topic_weight": {"ALGO.SORT": 1.0},
        "concept_ids": ["ALGO.SORT.HASH"], "what_it_tests": "hashing", "prerequisite_ids": [],
        "confidence": 0.9, "evidence_quote": "hash table"}

def ok(payload=GOOD, tin=1000, tout=120, thoughts=0):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": tin, "candidatesTokenCount": tout, "thoughtsTokenCount": thoughts,
                              "totalTokenCount": tin + tout + thoughts}}

def http(status, body="", retry_after=None):
    return cl.ProviderError(f"HTTP {status} from provider: {body!r:.100}", status=status,
                            retry_after=retry_after, body=body)

class Script:
    """Transport that plays back a list: dict -> response, Exception -> raised. Repeats the last item when empty."""
    def __init__(self, *items):
        self.items, self.calls = list(items), 0
    def __call__(self, url, headers, payload):
        self.calls += 1
        item = self.items.pop(0) if len(self.items) > 1 else self.items[0]
        if isinstance(item, Exception):
            raise item
        return item

class Clock:
    def __init__(self):
        self.t, self.slept = 0.0, []
    def now(self):
        return self.t
    def sleep(self, s):
        self.slept.append(s); self.t += s

@pytest.fixture()
def gem(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GATE_LLM_MODEL", "test-model-1")
    monkeypatch.setenv("GATE_LLM_FREE_PLAN_CONFIRMED", "1")

def provider(*items):
    t = Script(*items)
    return cl.get_provider("gemini", transport=t), t

def run(db_url, p, pid, clock=None, rpm=0, **kw):
    clock = clock or Clock()
    guard = kw.pop("guard", None) or cl.RunGuard(rpm=rpm, max_calls=kw.pop("max_calls", None),
                                                 sleep=clock.sleep, clock=clock.now)
    with make_session(db_url) as s:
        res = cl.run_classification(s, p, "gate-cs-2027", pid, allow_external=True, guard=guard, **kw)
        s.commit()
    return res, clock

def count(db_url, *where):
    with make_session(db_url) as s:
        return s.scalar(select(func.count()).select_from(Classification).where(*where))

# ------------------------------------------------------------------------------------------- usage
def test_usage_parsers_cover_every_provider_shape():
    assert cl.usage_from_response(ok(tin=10, tout=5, thoughts=7)) == (10, 12)          # thinking counts as output
    assert cl.usage_from_response({"usage": {"prompt_tokens": 3, "completion_tokens": 4}}) == (3, 4)
    assert cl.usage_from_response({"usage": {"input_tokens": 8, "output_tokens": 9}}) == (8, 9)
    assert cl.usage_from_response({}) == (0, 0) and cl.usage_from_response("x") == (0, 0)

def test_run_records_actual_usage(loaded, gem):
    db_url, pid, _ = loaded
    p, t = provider(ok(tin=1000, tout=100, thoughts=50))
    res, _ = run(db_url, p, pid)
    assert res["classified"] == 6 and t.calls == 6
    assert res["actual_usage"] == {"calls": 6, "input_tokens": 6000, "output_tokens": 900, "calls_without_usage": 0}
    assert res["guard"]["api_attempts"] == 6 and res["stopped"] is None
    with make_session(db_url) as s:      # persisted on the run row too
        from src.db.models import ClassificationRun
        assert s.scalar(select(ClassificationRun)).stats["actual_usage"]["input_tokens"] == 6000

def test_missing_usage_is_reported_not_invented(loaded, gem):
    db_url, pid, _ = loaded
    r = ok(); del r["usageMetadata"]
    p, _ = provider(r)
    res, _ = run(db_url, p, pid)
    assert res["actual_usage"]["calls_without_usage"] == 6 and res["actual_usage"]["input_tokens"] == 0

# ------------------------------------------------------------------------------------------- pacing
def test_pacing_spaces_calls_by_the_rpm_limit(loaded, gem):
    db_url, pid, _ = loaded
    p, _ = provider(ok())
    res, clock = run(db_url, p, pid, rpm=6)            # 6 requests/minute = one every 10 s
    assert res["classified"] == 6
    assert clock.slept == [pytest.approx(10.0)] * 5     # 6 calls -> 5 gaps, none before the first
    assert res["guard"]["rpm_limit"] == 6.0

# ------------------------------------------------------------------------------------------- retry / stop
def test_per_minute_429_waits_what_the_provider_asked_then_retries_once(loaded, gem):
    db_url, pid, _ = loaded
    p, t = provider(http(429, '{"error":{"status":"RESOURCE_EXHAUSTED"}} per minute', retry_after=7), ok())
    res, clock = run(db_url, p, pid)
    assert res["classified"] == 6 and res["stopped"] is None
    assert clock.slept == [9.0]                         # retryDelay 7 s + 2 s margin
    assert t.calls == 7 and res["guard"]["retries"] == 1

def test_rate_limit_that_persists_stops_the_run_and_keeps_finished_work(loaded, gem):
    db_url, pid, _ = loaded
    p, _ = provider(ok(), ok(), http(429, "slow down", retry_after=3))     # 3rd question: 429, retry: 429 again
    res, _ = run(db_url, p, pid)
    assert res["stopped"]["kind"] == "rate_limit" and res["classified"] == 2
    assert count(db_url) == 2                                              # saved
    with make_session(db_url) as s:                                        # the unfinished question is untouched
        assert s.scalar(select(Question.needs_review).where(Question.id == f"{pid}-Q03")) in (False, None)

def test_daily_quota_stops_immediately_without_retry(loaded, gem):
    db_url, pid, _ = loaded
    body = '{"violations":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}'
    p, t = provider(http(429, body, retry_after=40))
    res, clock = run(db_url, p, pid)
    assert res["stopped"]["kind"] == "daily_quota" and t.calls == 1 and clock.slept == []
    assert "tomorrow" in res["stopped"]["what_to_do"]

@pytest.mark.parametrize("err", [http(403, "billing account required"), http(401, "bad key"),
                                 http(404, "model not found"), http(402, "payment required"),
                                 http(400, "API key not valid")])
def test_billing_auth_and_model_errors_stop_at_once(loaded, gem, err):
    db_url, pid, _ = loaded
    p, t = provider(err)
    res, clock = run(db_url, p, pid)
    assert res["stopped"]["kind"] == "billing_or_auth" and t.calls == 1 and clock.slept == []
    assert res["classified"] == 0 and res["provider_errors"] == 0           # nothing was flagged as 'bad question'

def test_server_errors_are_retried_twice_with_backoff(loaded, gem):
    db_url, pid, _ = loaded
    p, t = provider(http(503, "overloaded"), http(503, "overloaded"), ok())
    res, clock = run(db_url, p, pid)
    assert res["classified"] == 6 and clock.slept == [5.0, 15.0]

def test_a_service_that_never_recovers_flags_questions_then_stops(loaded, gem):
    db_url, pid, _ = loaded
    p, t = provider(http(503, "down"))
    res, _ = run(db_url, p, pid)
    assert res["stopped"]["kind"] == "repeated_failures"                    # 5 questions in a row -> stop
    assert res["provider_errors"] == 5 and res["classified"] == 0
    assert t.calls == 5 * 3                                                 # 1 try + 2 retries each, then stop

def test_bad_json_is_retried_once(loaded, gem):
    db_url, pid, _ = loaded
    junk = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
    p, t = provider(junk, ok())
    res, _ = run(db_url, p, pid)
    assert res["classified"] == 6 and res["guard"]["retries"] == 1 and t.calls == 7

@pytest.mark.parametrize("text", ['["a list"]', '{"section_id": "ALGO"}', '{"section_id": 1, "primary_topic_id": []}', "42"])
def test_wrong_shape_json_flags_a_question_instead_of_crashing_the_run(loaded, gem, text):
    db_url, pid, _ = loaded
    p, _ = provider({"candidates": [{"content": {"parts": [{"text": text}]}}]})
    res, _ = run(db_url, p, pid)            # must RETURN, not raise pydantic.ValidationError
    assert res["classified"] == 0 and res["provider_errors"] >= 1

def test_cut_off_output_is_not_retried_and_says_why(loaded, gem):
    db_url, pid, _ = loaded
    cut = {"candidates": [{"content": {"parts": [{"text": '{"section_id": "AL'}]}, "finishReason": "MAX_TOKENS"}]}
    p, t = provider(cut)
    res, _ = run(db_url, p, pid)
    assert t.calls == 5                                        # 1 try per question, no retries, stops after 5 in a row
    assert res["stopped"]["kind"] == "repeated_failures" and "GEMINI_MAX_OUTPUT_TOKENS" in res["stopped"]["reason"]

def test_blocked_prompt_is_explained(gem):
    p, _ = provider({"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(cl.ProviderError, match="prompt blocked: SAFETY"):
        p.classify("q", [], [])

# ------------------------------------------------------------------------------------------- cap / resume / checkpoint
def test_call_cap_then_resume_skips_what_is_done(loaded, gem):
    db_url, pid, _ = loaded
    p, t = provider(ok())
    res, _ = run(db_url, p, pid, max_calls=3)
    assert res["classified"] == 3 and res["stopped"]["kind"] == "cap" and t.calls == 3
    res2, _ = run(db_url, p, pid)                               # same command again
    assert res2["classified"] == 3 and res2["skipped_existing"] == 3 and t.calls == 6   # did NOT redo the first 3
    assert count(db_url) == 6

def test_checkpoint_survives_a_crash(loaded, gem):
    db_url, pid, _ = loaded
    class Boom(Exception): pass
    p, t = provider(ok(), ok(), ok(), ok(), Boom("kaboom"))
    with make_session(db_url) as s:
        with pytest.raises(Boom):
            cl.run_classification(s, p, "gate-cs-2027", pid, allow_external=True, checkpoint_every=2,
                                  guard=cl.RunGuard(rpm=0))
        s.rollback()                                            # what a dead process loses: only the un-checkpointed part
    assert count(db_url) == 4                                   # two checkpoints of 2 were already durable

def test_provider_error_note_is_not_duplicated_on_rerun(loaded, gem):
    db_url, pid, _ = loaded
    bad = {"candidates": [{"content": {"parts": [{"text": "x"}]}}]}
    for _ in range(2):
        p, _ = provider(bad)
        run(db_url, p, pid)
    with make_session(db_url) as s:
        reason = s.scalar(select(Question.review_reason).where(Question.id == f"{pid}-Q01"))
    assert reason.count("provider error") == 1

# ------------------------------------------------------------------------------------------- selection
def test_parse_years():
    assert cl.parse_years("2022-2026") == [2022, 2023, 2024, 2025, 2026]
    assert cl.parse_years("2017,2019-2020, 2011") == [2011, 2017, 2019, 2020]
    assert cl.parse_years(None) is None and cl.parse_years("  ") is None
    for bad in ("abc", "2026-2022", "20-30"):
        with pytest.raises(ValueError):
            cl.parse_years(bad)

def test_years_filter_selects_only_those_papers(loaded, gem):
    db_url, pid, _ = loaded                                    # the fixture paper is year 2099
    p, t = provider(ok())
    res, _ = run(db_url, p, pid, years=[2022, 2023])
    assert res["classified"] == 0 and t.calls == 0
    res, _ = run(db_url, p, pid, years=[2099])
    assert res["classified"] == 6 and res["years"] == [2099]

def test_spread_sampling_covers_the_whole_paper_not_just_the_first_questions():
    picked = cl._spread(list(range(1, 66)), 0.12)
    assert len(picked) == 7 and picked[0] > 1 and picked[-1] > 55          # first-N would give 1..7
    assert picked == sorted(set(picked))
    assert cl._spread([1, 2, 3], 0.01) == [2] and cl._spread([], 0.5) == [] and cl._spread([1, 2], 1.0) == [1, 2]

def test_dry_run_counts_only_what_would_be_sent(loaded, gem):
    db_url, pid, _ = loaded
    p, t = provider(ok())
    run(db_url, p, pid, max_calls=2)
    with make_session(db_url) as s:
        out = cl.run_classification(s, p, "gate-cs-2027", pid, dry_run=True)
        est = cl.estimate_cost(s, pid, only_unclassified=True, taxonomy_version="gate-cs-2027")
    assert out["questions_would_classify"] == 4 and out["would_skip_already_classified"] == 2
    assert est["questions"] == 4 and est["fixed_prompt_basis"].startswith("measured")
    assert est["est_input_tokens_per_call_fixed_prompt"] > 400            # the taxonomy is re-sent with every call
    assert t.calls == 2                                                    # dry run made no call
    assert "x-goog-api-key" in json.dumps(out["request_previews"][0]["headers"]) and "test-key" not in json.dumps(out)

# ------------------------------------------------------------------------------------------- honesty guarantees
def test_ai_runs_never_produce_human_verified_rows(loaded, gem):
    db_url, pid, _ = loaded
    p, _ = provider(ok(), ok(dict(GOOD, primary_topic_id="ALGO.NOPE")), ok(dict(GOOD, confidence=0.2)))
    run(db_url, p, pid)
    with make_session(db_url) as s:
        rows = s.scalars(select(Classification)).all()
    assert rows and {r.status for r in rows} <= {"suggested", "flagged"}
    assert {r.provenance for r in rows} == {"inferred"}
    assert any(r.status == "flagged" for r in rows)                        # invalid id / low confidence -> review queue

def test_compare_reports_usage_and_review_list_and_writes_nothing(loaded, gem):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        for n in (1, 2, 3, 4):
            s.add(Classification(question_id=f"{pid}-Q0{n}", taxonomy_version="gate-cs-2027", prompt_version="agent-v1",
                                 section_id="ALGO", primary_topic_id="ALGO.SORT", confidence=0.9, status="suggested",
                                 model="agent", provenance="inferred"))
        s.commit()
    p, _ = provider(ok(), ok(dict(GOOD, primary_topic_id="ALGO.GRAPH")), ok(dict(GOOD, concept_ids=["NOT.A.CONCEPT"])), ok())
    before = count(db_url)
    with make_session(db_url) as s:
        res = cl.compare_with_existing(s, p, "gate-cs-2027", pid, sample=1.0, allow_external=True,
                                       guard=cl.RunGuard(rpm=0))
    assert res["sampled"] == 4 and res["answered"] == 4 and res["valid_json_and_shape"] == 1.0
    assert res["actual_usage"]["input_tokens"] == 4000 and res["stopped"] is None
    assert res["topic_agreement"] == 0.75 and res["all_ids_valid"] == 0.75         # concept id check included
    assert len(res["rows_needing_manual_review"]) == 2                              # the disagreement + the bad id
    assert count(db_url) == before

def test_cli_rejects_bad_years_before_touching_anything(blank_db):
    from typer.testing import CliRunner
    from src.cli import app
    r = CliRunner().invoke(app, ["classify", "--provider", "mock", "--years", "abc", "--db-url", blank_db])
    assert r.exit_code == 2 and "--years" in r.output
