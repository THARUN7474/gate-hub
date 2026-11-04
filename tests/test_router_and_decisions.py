"""FreeLLMAPI router provider + decision-model adapters: offline only (fake transports, no network)."""
import json

import pytest

from src.classification import classify as cl
from src.classification import decision_models as dm


def test_freellmapi_uses_single_unified_key_and_records_upstream(monkeypatch):
    monkeypatch.setenv("FREELLMAPI_API_KEY", "freellmapi-test-key-123")
    monkeypatch.delenv("FREELLMAPI_MODEL", raising=False); monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    monkeypatch.setenv("FREELLMAPI_BASE_URL", "http://127.0.0.1:3001/v1/")
    seen = {}
    def fake(url, headers, payload):
        seen.update(url=url, headers=headers, payload=payload)
        out = {"section_id": "OS", "primary_topic_id": "OS.SCHED", "topic_weight": {"OS.SCHED": 1.0},
               "concept_ids": [], "confidence": 0.9, "evidence_quote": "FCFS"}
        return {"choices": [{"message": {"content": json.dumps(out)}}], "_routed_via": "groq/llama"}
    p = cl.get_provider("freellmapi", transport=fake)
    r = p.classify("Which scheduler cannot be preemptive?", ["FCFS", "RR"], [])
    assert r.primary_topic_id == "OS.SCHED"
    assert seen["url"] == "http://127.0.0.1:3001/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer freellmapi-test-key-123"
    assert seen["payload"]["model"] == "auto"
    assert p.last_routed_via == "groq/llama"
    assert cl.provider_tier("freellmapi") == "free-if-plan"


def test_router_only_mode_hides_direct_providers(monkeypatch):
    monkeypatch.setenv("GATE_LLM_ROUTER_ONLY", "1")
    monkeypatch.setenv("GATE_LLM_PRIORITY", "gemini,groq")
    monkeypatch.setenv("GEMINI_API_KEY", "x" * 20)
    monkeypatch.delenv("FREELLMAPI_API_KEY", raising=False)
    assert cl.priority_list() == ["freellmapi"]
    with pytest.raises(RuntimeError):
        cl.resolve_provider_name("auto")          # gemini key is ignored in router-only mode


def test_freellmapi_call_gate_needs_external_and_plan(monkeypatch):
    monkeypatch.setenv("FREELLMAPI_API_KEY", "freellmapi-test-key-123")
    monkeypatch.setenv("GATE_LLM_FREE_PLAN_CONFIRMED", "0")
    p = cl.get_provider("freellmapi", transport=lambda *a: {})
    assert cl.gate_status(p, allow_spend=False, allow_external=False)
    assert cl.gate_status(p, allow_spend=False, allow_external=True)        # plan not confirmed
    monkeypatch.setenv("GATE_LLM_FREE_PLAN_CONFIRMED", "1")
    assert cl.gate_status(p, allow_spend=False, allow_external=True) is None


CHOICES = {"OS.SCHED": "Operating System - CPU scheduling", "OS.MEM": "Operating System - Memory"}


def test_decision_payload_shapes_match_the_documented_apis():
    url, _, jev = dm.build_request(dm.SPECS["jev"], "Q text", CHOICES)
    assert url.endswith("/v1/systemone") and jev["state"] == "Q text"
    assert jev["questions"]["topic"]["type"] == "choice" and jev["questions"]["topic"]["criteria"] == CHOICES
    url, _, oa = dm.build_request(dm.SPECS["openai-decisions"], "Q text", CHOICES, "data:image/png;base64,AA")
    assert url.endswith("/v1/decisions") and oa["model"] == "gpt-6-luna"
    q = oa["questions"][0]
    assert q["type"] == "choice" and q["name"] == "topic" and {c["value"] for c in q["choices"]} == set(CHOICES)
    assert oa["input"][0]["content"][1]["type"] == "input_image"


def test_decision_answers_parse_to_choice_confidence_distribution():
    jev = {"answers": {"topic": {"type": "choice", "choice": "OS.MEM", "confidence": 0.8,
                                 "probabilities": {"OS.MEM": 0.9, "OS.SCHED": 0.1}}}}
    assert dm.parse_answer(dm.SPECS["jev"], jev) == ("OS.MEM", 0.8, {"OS.MEM": 0.9, "OS.SCHED": 0.1})
    oa = {"answers": [{"type": "choice", "name": "topic", "choice": "OS.SCHED", "confidence": 0.7,
                       "probabilities": [{"value": "OS.SCHED", "probability": 0.75},
                                         {"value": "OS.MEM", "probability": 0.25}]}]}
    assert dm.parse_answer(dm.SPECS["openai-decisions"], oa)[0] == "OS.SCHED"
    with pytest.raises(cl.ProviderError):
        dm.parse_answer(dm.SPECS["openai-decisions"], {"answers": [{"type": "refusal", "name": "topic"}]})


def test_decision_gate_requires_every_condition(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-" + "x" * 20)
    monkeypatch.setenv("DECISIONS_ENABLED", "0")
    spec = dm.SPECS["jev"]
    assert "DECISIONS_ENABLED" in dm.gate(spec, True, True, 5)
    monkeypatch.setenv("DECISIONS_ENABLED", "1")
    assert "PAID" in dm.gate(spec, True, False, 5)
    assert "max-calls" in dm.gate(spec, True, True, None)
    assert dm.gate(spec, True, True, 5) is None
