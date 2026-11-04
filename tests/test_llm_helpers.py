"""set-key (hidden input -> .env) and llm-models (what can my key see?). Offline: fake transports only."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from typer.testing import CliRunner
from src import cli
from src.classification import classify as cl

runner = CliRunner()
FAKE = "AIzaFAKE-test-key-0123456789abcdef"


def _set_key(env: Path, provider="gemini", key=FAKE, *extra):
    return runner.invoke(cli.app, ["set-key", provider, "--env-file", str(env), *extra], input=key + "\n")


def test_set_key_writes_env_without_echoing_and_keeps_other_lines(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# my settings\nPOSTGRES_PASSWORD=keepme\n# GEMINI_API_KEY=\n")
    r = _set_key(env)
    assert r.exit_code == 0, r.output
    assert FAKE not in r.output                                   # never echoed
    text = env.read_text()
    assert f"GEMINI_API_KEY={FAKE}" in text
    assert "POSTGRES_PASSWORD=keepme" in text and "# my settings" in text
    assert f"({len(FAKE)} characters)" in r.output                # confirms WITHOUT revealing it


def test_set_key_replaces_instead_of_duplicating(tmp_path):
    env = tmp_path / ".env"
    _set_key(env, key="first-key-AAAAAAAAAAAA")
    _set_key(env, key="second-key-BBBBBBBBBBB")
    lines = [l for l in env.read_text().splitlines() if l.startswith("GEMINI_API_KEY=")]
    assert lines == ["GEMINI_API_KEY=second-key-BBBBBBBBBBB"]


def test_set_key_strips_quotes_and_rejects_garbage(tmp_path):
    env = tmp_path / ".env"
    assert _set_key(env, key=f'"{FAKE}"').exit_code == 0
    assert f"GEMINI_API_KEY={FAKE}\n" in env.read_text() + "\n"
    before = env.read_text()
    for bad in ("qk9zx", "has some spaces in it 123456"):         # too short / contains spaces
        r = _set_key(env, key=bad)
        assert r.exit_code == 2 and "Nothing was saved" in r.output
        assert bad not in r.output
    assert env.read_text() == before                              # file untouched by rejected input


def test_set_key_rejects_unknown_provider(tmp_path):
    env = tmp_path / ".env"
    r = _set_key(env, provider="notaprovider")
    assert r.exit_code == 2 and not env.exists()


def test_set_key_can_save_model_and_never_enables_external_calls(tmp_path):
    env = tmp_path / ".env"
    r = _set_key(env, "gemini", FAKE, "--model", "gemini-3.5-flash-lite")
    assert r.exit_code == 0
    text = env.read_text()
    assert "GEMINI_MODEL=gemini-3.5-flash-lite" in text
    # saving a key must NOT flip any consent gate: those stay the owner's explicit decision
    assert "GATE_LLM_ALLOW_EXTERNAL" not in text and "GATE_LLM_FREE_PLAN_CONFIRMED" not in text


def _pages():
    return [{"models": [{"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash",
                         "inputTokenLimit": 1048576, "outputTokenLimit": 65536,
                         "supportedGenerationMethods": ["generateContent", "countTokens"]},
                        {"name": "models/gemini-embedding-2", "supportedGenerationMethods": ["embedContent"]}],
             "nextPageToken": "t1"},
            {"models": [{"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]}]}]


def _fake_get(seen):
    pages = _pages()
    def get(url, headers):
        seen.append((url, headers))
        return pages[len(seen) - 1]
    return get


def test_list_models_pages_filters_and_keeps_key_out_of_the_url(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k-secret-123456")
    seen = []
    out = cl.list_gemini_models(_fake_get(seen))
    assert [m["id"] for m in out] == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]      # embeddings filtered, sorted
    assert out[1]["input_tokens"] == 1048576
    assert len(seen) == 2 and "pageToken=t1" in seen[1][0]
    assert all("k-secret" not in url for url, _ in seen)                                # key only in the header
    assert seen[0][1] == {"x-goog-api-key": "k-secret-123456"}
    seen2 = []
    assert len(cl.list_gemini_models(_fake_get(seen2), generate_only=False)) == 3        # --all keeps embeddings


def test_list_models_needs_key_and_rejects_odd_shapes(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="set-key"):
        cl.list_gemini_models(lambda u, h: {})
    monkeypatch.setenv("GEMINI_API_KEY", "k-secret-123456")
    with pytest.raises(cl.ProviderError, match="unexpected models.list"):
        cl.list_gemini_models(lambda u, h: {"error": "weird"})


def test_llm_models_command_output_and_plain_language_errors(monkeypatch):
    monkeypatch.setattr(cl, "list_gemini_models", lambda generate_only=True: [
        {"id": "gemini-3.5-flash-lite", "display_name": "Flash Lite", "input_tokens": 1000000, "output_tokens": 65536, "methods": []}])
    r = runner.invoke(cli.app, ["llm-models"])
    assert r.exit_code == 0 and "gemini-3.5-flash-lite" in r.output and "set-key gemini --model" in r.output
    def boom(generate_only=True):
        raise cl.ProviderError("HTTP 403 from provider: API key not valid")
    monkeypatch.setattr(cl, "list_gemini_models", boom)
    r = runner.invoke(cli.app, ["llm-models"])
    assert r.exit_code == 1 and "rejected the API key" in r.output
    assert runner.invoke(cli.app, ["llm-models", "groq"]).exit_code == 2


def test_gemini_adapter_has_no_stale_default_model(monkeypatch):
    assert not hasattr(cl.GeminiProvider, "DEFAULT_MODEL")        # gemini-2.5-* is deprecated: never assume a model
    monkeypatch.setenv("GEMINI_API_KEY", "k-secret-123456")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GATE_LLM_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="model not chosen"):
        cl.GeminiProvider()
