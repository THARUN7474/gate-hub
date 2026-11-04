"""v6 provider surface - fully offline: fake transports, no network, no keys,
no spend. Covers Gemini/Groq/OpenRouter shapes, availability-aware auto/free
selection, the free-tier external-call gate, OpenRouter paid-model handling,
and the ensemble consensus + combined score."""
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import Classification, Question
from src.db.session import make_session

GOOD = {"section_id": "ALGO", "primary_topic_id": "ALGO.SORT",
        "topic_weight": {"ALGO.SORT": 1.0}, "concept_ids": ["ALGO.SORT.HASH"],
        "what_it_tests": "hashing", "prerequisite_ids": [], "confidence": 0.9,
        "evidence_quote": "hash table"}
GOOD_JSON = json.dumps(GOOD)

@pytest.fixture()
def all_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GATE_LLM_MODEL", "test-model-1")
    monkeypatch.setenv("GATE_LLM_FREE_PLAN_CONFIRMED", "1")

def gemini_transport(payload_text):
    def t(url, headers, payload):
        assert headers["x-goog-api-key"] == "test-key"
        assert "test-model-1:generateContent" in url
        assert payload["generationConfig"]["response_mime_type"] == "application/json"
        assert "<question>" in payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [{"text": payload_text}]}}]}
    return t

def test_gemini_success(loaded, all_keys):
    db_url, pid, _ = loaded
    p = cl.get_provider("gemini", transport=gemini_transport(GOOD_JSON))
    with make_session(db_url) as s:
        res = cl.run_classification(s, p, "gate-cs-2027", pid, allow_external=True)
        c = s.scalars(select(Classification)).all()
        s.commit()
    assert res["classified"] == 6 and res["provider_errors"] == 0
    assert all(r.combo_score == pytest.approx(0.9) for r in c)  # single provider: agreement 1.0
    assert all(r.provider_count == 1 for r in c)

def test_groq_openrouter_shapes(all_keys):
    def t(url, headers, payload):
        assert headers["Authorization"] == "Bearer test-key"
        assert payload["response_format"] == {"type": "json_object"}
        return {"choices": [{"message": {"content": GOOD_JSON}}]}
    g = cl.get_provider("groq", transport=t)
    o = cl.get_provider("openrouter", transport=t)
    assert g.classify("q", [], []).primary_topic_id == "ALGO.SORT"
    assert o.classify("q", [], []).primary_topic_id == "ALGO.SORT"
    assert g.model == "test-model-1" and o.model == "test-model-1"

def test_openrouter_default_model_is_free(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    p = cl.OpenRouterProvider(transport=lambda *a: None)
    assert p.model.endswith(":free")
    assert cl.effective_tier(p) == "free"
    p2 = cl.OpenRouterProvider(model="some/paid-model", transport=lambda *a: None)
    assert cl.effective_tier(p2) == "paid"

def test_free_gate_blocks_without_allow_external(loaded, all_keys):
    db_url, pid, _ = loaded
    calls = []
    p = cl.get_provider("openrouter", model="meta-llama/llama-3.3-70b-instruct:free",
                        transport=lambda *a: calls.append(a) or {})
    with make_session(db_url) as s:
        with pytest.raises(RuntimeError, match="allow-external"):
            cl.run_classification(s, p, "gate-cs-2027", pid)
    assert calls == []

def test_account_dependent_needs_attestation_or_spend(loaded, all_keys, monkeypatch):
    """gemini/groq: key + allow_external is NOT enough - the free plan cannot
    be verified, so no silent billable call is possible through the free path."""
    monkeypatch.delenv("GATE_LLM_FREE_PLAN_CONFIRMED", raising=False)
    db_url, pid, _ = loaded
    calls = []
    p = cl.get_provider("gemini", transport=lambda *a: calls.append(a) or {})
    with make_session(db_url) as s:
        with pytest.raises(RuntimeError, match="GATE_LLM_FREE_PLAN_CONFIRMED"):
            cl.run_classification(s, p, "gate-cs-2027", pid, allow_external=True)
        # explicit spend approval treats it as paid - permitted
        res = cl.run_classification(
            s, cl.get_provider("gemini", transport=gemini_transport(GOOD_JSON)),
            "gate-cs-2027", pid, allow_spend=True)
        s.commit()
    assert res["classified"] == 6 and calls == []

def test_gemini_requires_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="model"):
        cl.get_provider("gemini")

def test_single_run_has_no_ensemble_agreement(loaded, all_keys):
    db_url, pid, _ = loaded
    p = cl.get_provider("gemini", transport=gemini_transport(GOOD_JSON))
    with make_session(db_url) as s:
        cl.run_classification(s, p, "gate-cs-2027", pid, allow_external=True)
        rows = s.scalars(select(Classification)).all()
        s.commit()
    assert all(r.agreement is None for r in rows)
    assert all(r.provider_count == 1 for r in rows)

def test_paid_gate_still_requires_allow_spend(loaded, all_keys):
    db_url, pid, _ = loaded
    calls = []
    p = cl.get_provider("openrouter", model="some/paid-model",
                        transport=lambda *a: calls.append(a) or {})
    with make_session(db_url) as s:
        with pytest.raises(RuntimeError, match="allow_spend"):
            cl.run_classification(s, p, "gate-cs-2027", pid, allow_external=True)
    assert calls == []

def test_auto_picks_first_available_by_priority(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setenv("GATE_LLM_PRIORITY", "gemini,groq,openrouter")
    assert cl.resolve_provider_name("auto") == "groq"
    assert cl.resolve_provider_name("free") == "groq"

def test_auto_free_skips_paid(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("GATE_LLM_PRIORITY", "anthropic,groq")
    assert cl.resolve_provider_name("auto") == "anthropic"
    with pytest.raises(RuntimeError, match="no free-tier provider"):
        cl.resolve_provider_name("free")

def test_provider_status_hides_secrets(all_keys, monkeypatch):
    monkeypatch.setenv("FREELLMAPI_API_KEY", "test-key")   # v12: the router is in the default priority list
    rows = cl.provider_status()
    assert all(set(r) == {"provider", "tier", "key_env", "key_set"} for r in rows)
    assert all(r["key_set"] for r in rows)
    blob = json.dumps(rows)
    assert "test-key" not in blob

# ---- ensemble ---------------------------------------------------------------
class StubProvider:
    """Deterministic fake provider for ensemble tests (no network)."""
    is_mock = False
    def __init__(self, name, topic, confidence, fail=False):
        self.name = name; self.model = f"{name}-stub"; self.tier = "free"
        self._topic, self._conf, self._fail = topic, confidence, fail
    def classify(self, question_text, options, topics):
        if self._fail:
            raise cl.ProviderError("stub failure")
        sec = self._topic.split(".")[0]
        return cl.ClassificationOut(section_id=sec, primary_topic_id=self._topic,
            topic_weight={self._topic: 1.0}, concept_ids=[],
            what_it_tests="stub", prerequisite_ids=[], confidence=self._conf,
            evidence_quote="")
    def build_request(self, question_text, options, topics):
        return ("stub://local", {}, {})

def test_ensemble_unanimous(loaded):
    db_url, pid, _ = loaded
    provs = [StubProvider("pa", "ALGO.SORT", 0.8), StubProvider("pb", "ALGO.SORT", 0.6)]
    with make_session(db_url) as s:
        res = cl.run_ensemble(s, provs, "gate-cs-2027", pid, allow_external=True)
        rows = s.scalars(select(Classification)).all()
        s.commit()
    assert res["classified"] == 6 and res["provider_errors"] == 0
    for r in rows:
        assert r.primary_topic_id == "ALGO.SORT"
        assert r.agreement == 1.0
        assert r.combo_score == pytest.approx(cl.combo_score(1.0, 0.7))  # mean conf
        assert r.provider_count == 2 and len(r.provider_votes) == 2

def test_ensemble_split_vote_and_combo(loaded):
    db_url, pid, _ = loaded
    provs = [StubProvider("pa", "ALGO.SORT", 0.9), StubProvider("pb", "DL.NUM", 0.5)]
    with make_session(db_url) as s:
        cl.run_ensemble(s, provs, "gate-cs-2027", pid, allow_external=True)
        rows = s.scalars(select(Classification)).all()
        s.commit()
    for r in rows:
        assert r.primary_topic_id == "ALGO.SORT"   # tie 1-1 broken by summed confidence
        assert r.agreement == 0.5
        assert r.combo_score == pytest.approx(cl.combo_score(0.5, 0.7))
        assert r.status == "flagged"               # combo 0.35 < 0.5

def test_ensemble_tolerates_one_failure(loaded):
    db_url, pid, _ = loaded
    provs = [StubProvider("pa", "ALGO.SORT", 0.8), StubProvider("pb", "X", 0.0, fail=True)]
    with make_session(db_url) as s:
        res = cl.run_ensemble(s, provs, "gate-cs-2027", pid, allow_external=True)
        rows = s.scalars(select(Classification)).all()
        s.commit()
    assert res["classified"] == 6 and res["provider_errors"] == 0
    for r in rows:
        assert r.provider_count == 1 and r.agreement == 1.0
        assert any("error" in v for v in r.provider_votes)

def test_ensemble_all_fail_flags_question(loaded):
    db_url, pid, _ = loaded
    provs = [StubProvider("pa", "X", 0.0, fail=True)]
    with make_session(db_url) as s:
        res = cl.run_ensemble(s, provs, "gate-cs-2027", pid, allow_external=True)
        qs = s.scalars(select(Question)).all()
        s.commit()
    assert res["provider_errors"] == 6 and res["classified"] == 0
    assert all(q.needs_review for q in qs)

def test_ensemble_gate_applies_to_each_provider(loaded):
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        with pytest.raises(RuntimeError, match="allow-external"):
            cl.run_ensemble(s, [StubProvider("pa", "ALGO.SORT", 0.8)],
                            "gate-cs-2027", pid)

def test_combo_score_bounds():
    assert cl.combo_score(1.0, 1.0) == 1.0
    assert cl.combo_score(0.0, 1.0) == 0.0
    assert cl.combo_score(2.0, 0.5) == 0.5    # clamped
    assert cl.combo_score(-1, 0.5) == 0.0


# ---- auto: bounded failover within consent gates ------------------------------
def test_auto_failover_to_next_candidate(loaded, all_keys, monkeypatch):
    monkeypatch.setenv("GATE_LLM_PRIORITY", "gemini,openrouter")
    monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "test-model-1")
    db_url, pid, _ = loaded
    def flaky(url, headers, payload):
        raise cl.ProviderError("HTTP 429 quota exceeded")
    import src.classification.classify as cmod
    real_get = cmod.get_provider
    def patched(name, model=None, transport=None, free_only=False):
        if name == "gemini":
            return cmod.GeminiProvider(transport=flaky)
        return real_get(name, model=model,
                        transport=transport or (lambda u, h, pl:
                            {"choices": [{"message": {"content": GOOD_JSON}}]}),
                        free_only=free_only)
    monkeypatch.setattr(cmod, "get_provider", patched)
    with make_session(db_url) as s:
        res = cmod.run_auto_classification(s, "gate-cs-2027", pid, allow_external=True)
        rows = s.scalars(select(Classification)).all()
        s.commit()
    assert res["classified"] == 6 and res["failovers"] == 6
    assert all(r.primary_topic_id == "ALGO.SORT" for r in rows)
    assert all(r.provider_votes[0]["answered"] is False for r in rows)
    assert all(r.provider_votes[1]["answered"] is True for r in rows)
    assert all(r.agreement is None for r in rows)  # one answerer: no ensemble

def test_auto_never_falls_back_to_paid_without_spend(loaded, all_keys, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("GATE_LLM_PRIORITY", "anthropic")
    db_url, pid, _ = loaded
    with make_session(db_url) as s:
        with pytest.raises(RuntimeError, match="no provider can run"):
            cl.run_auto_classification(s, "gate-cs-2027", pid, allow_external=True)

def test_auto_dry_run_makes_no_calls(loaded, all_keys, monkeypatch):
    monkeypatch.setenv("GATE_LLM_PRIORITY", "openrouter")
    monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    db_url, pid, _ = loaded
    calls = []
    monkeypatch.setattr(cl, "_urllib_transport", lambda *a: calls.append(a) or {})
    with make_session(db_url) as s:
        out = cl.run_auto_classification(s, "gate-cs-2027", pid,
                                         allow_external=True, dry_run=True)
    assert out["dry_run"] and out["candidates"] == ["openrouter"] and calls == []

def test_runnable_providers_respects_gates(all_keys, monkeypatch):
    monkeypatch.delenv("GATE_LLM_FREE_PLAN_CONFIRMED", raising=False)
    monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "test-model-1")
    names, skipped = cl.runnable_providers(False, True)
    assert names == ["openrouter"]                     # only true-free route runs
    assert "gemini" in skipped and "groq" in skipped
    assert "anthropic" in skipped and "openai" in skipped
    names2, _ = cl.runnable_providers(False, True, free_only=True)
    assert names2 == ["openrouter"]
    monkeypatch.setenv("GATE_LLM_FREE_PLAN_CONFIRMED", "1")
    names3, _ = cl.runnable_providers(False, True, free_only=True)
    assert set(names3) == {"gemini", "groq", "openrouter"}
