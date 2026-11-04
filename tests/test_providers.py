"""Real LLM provider contract - fully offline: transports are fakes, no
network, no keys, no spend. Covers request shape, response parsing, error
flagging and the two spend gates (env key + allow_spend)."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from src.classification import classify as cl
from src.db.models import Classification
from src.db.session import make_session

GOOD = {"section_id": "ALGO", "primary_topic_id": "ALGO.SORT",
        "topic_weight": {"ALGO.SORT": 1.0}, "concept_ids": ["ALGO.SORT.HASH"],
        "what_it_tests": "hashing", "prerequisite_ids": [], "confidence": 0.9,
        "evidence_quote": "hash table"}

def anthropic_transport(payload_text):
    def t(url, headers, payload):
        assert url == cl.AnthropicProvider.URL
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"
        assert payload["messages"][0]["role"] == "user"
        assert "<question>" in payload["messages"][0]["content"]
        return {"content": [{"type": "text", "text": payload_text}]}
    return t

def openai_transport(payload_text):
    def t(url, headers, payload):
        assert headers["Authorization"] == "Bearer test-key"
        assert payload["response_format"] == {"type": "json_object"}
        return {"choices": [{"message": {"content": payload_text}}]}
    return t

@pytest.fixture()
def keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GATE_LLM_MODEL", "test-model-1")

def test_anthropic_success(loaded, keys):
    db_url, pid, _ = loaded
    import json
    p = cl.get_provider("anthropic", transport=anthropic_transport(json.dumps(GOOD)))
    with make_session(db_url) as s:
        res = cl.run_classification(s, p, "gate-cs-2027", pid, allow_spend=True)
        c = s.scalars(select(Classification)).all()
        s.commit()
    assert res["classified"] == 6 and res["provider_errors"] == 0
    assert all(r.primary_topic_id == "ALGO.SORT" for r in c)
    assert all(r.concept_ids == ["ALGO.SORT.HASH"] for r in c)

def test_openai_success(loaded, keys):
    db_url, pid, _ = loaded
    import json
    p = cl.get_provider("openai", transport=openai_transport(json.dumps(GOOD)))
    with make_session(db_url) as s:
        res = cl.run_classification(s, p, "gate-cs-2027", pid, allow_spend=True)
        s.commit()
    assert res["classified"] == 6

def test_malformed_response_flags_question(loaded, keys):
    db_url, pid, _ = loaded
    p = cl.get_provider("anthropic", transport=anthropic_transport("not json at all"))
    with make_session(db_url) as s:
        res = cl.run_classification(s, p, "gate-cs-2027", pid, allow_spend=True)
        s.commit()
    # each bad answer flags ONE question; after 5 questions in a row fail the run stops instead of burning the
    # 6th call (something systematic is wrong) - see tests/test_run_guard.py
    assert res["provider_errors"] == 5 and res["classified"] == 0
    assert res["stopped"]["kind"] == "repeated_failures"

def test_invalid_taxonomy_id_flagged(loaded, keys):
    db_url, pid, _ = loaded
    import json
    bad = dict(GOOD, primary_topic_id="ALGO.NONEXISTENT")
    p = cl.get_provider("anthropic", transport=anthropic_transport(json.dumps(bad)))
    with make_session(db_url) as s:
        res = cl.run_classification(s, p, "gate-cs-2027", pid, allow_spend=True)
        rows = s.scalars(select(Classification)).all()
        s.commit()
    assert res["flagged"] == 6
    assert all(r.status == "flagged" for r in rows)

def test_spend_gate_blocks_real_provider(loaded, keys):
    db_url, pid, _ = loaded
    calls = []
    p = cl.get_provider("anthropic",
                        transport=lambda *a: calls.append(a) or {"content": []})
    with make_session(db_url) as s:
        with pytest.raises(RuntimeError, match="allow_spend"):
            cl.run_classification(s, p, "gate-cs-2027", pid)
    assert calls == []  # nothing was sent

def test_dry_run_makes_no_network_call(loaded, keys):
    db_url, pid, _ = loaded
    calls = []
    p = cl.get_provider("anthropic",
                        transport=lambda *a: calls.append(a) or {"content": []})
    with make_session(db_url) as s:
        out = cl.run_classification(s, p, "gate-cs-2027", pid, dry_run=True)
    assert out["dry_run"] and out["questions_would_classify"] == 6
    assert calls == []
    assert out["request_previews"][0]["headers"]["x-api-key"] == "***"  # redacted

def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        cl.get_provider("anthropic")

def test_openai_requires_explicit_model(keys, monkeypatch):
    monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="model"):
        cl.get_provider("openai")
