"""Environment + LLM provider configuration for v6.

Design goal (owner request): `cp .env.example .env`, add your values, and
everything picks them up - the CLI, the Streamlit app and scripts all call
load_env() first. Secrets are NEVER printed or returned; status helpers
report only whether a key is set.
"""
from __future__ import annotations
import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent

_loaded = False

def load_env() -> None:
    """Load <repo>/.env once (python-dotenv). Missing file or library is fine:
    everything still works with real environment variables or defaults."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(APP_ROOT / ".env")

def env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name, "")
    if not v:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

def external_calls_allowed() -> bool:
    """Owner opt-in for question text leaving this machine to a FREE-tier LLM
    provider. Set GATE_LLM_ALLOW_EXTERNAL=1 in .env (or pass --allow-external).
    Paid providers keep the stricter --allow-spend gate instead."""
    return env_flag("GATE_LLM_ALLOW_EXTERNAL", False)

def free_plan_confirmed() -> bool:
    """Owner attestation that their gemini/groq accounts are on free plans
    (billing cannot be verified from the key). Without it, those providers
    need explicit per-run spend approval instead."""
    return env_flag("GATE_LLM_FREE_PLAN_CONFIRMED", False)
