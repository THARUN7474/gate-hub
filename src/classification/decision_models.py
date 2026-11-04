"""Decision models (typed-answer APIs) - a SEPARATE path from the FreeLLMAPI chat router.

Two verified services (docs checked 4-5 Nov 2026, see docs/handoff/decision-models-assessment.md):
  * openai-decisions : POST https://api.openai.com/v1/decisions, model gpt-6-luna. Request:
        {"model", "input", "questions": [{"type": "choice", "name", "instructions",
                                          "choices": [{"value", "description"}]}]}
    response: answers[] -> {"type": "choice", "name", "choice", "probabilities": [{"value", "probability"}],
    "confidence"}; text + image input. Pricing: input tokens only (output not charged).
  * jev (TypeSafe System One): POST https://api.typesafe.ai/v1/systemone, model jev-1.14.0. Request:
        {"model", "state", "questions": {<name>: {"type": "choice", "instructions", "criteria": {opt: desc}}}}
    response: {"model", "answers": {<name>: {"choice", "probabilities": {opt: p}, "confidence"}}, "usage"}.
    Text only (diagram questions must be described/OCR'd first). Input tokens billed, output free.

What they are good for HERE: one `choice` question over the fixed 2027 topic list returns a CALIBRATED
probability distribution instead of generated prose - exactly the shape of a classification_proposals
row (choice -> primary_topic_id, probability -> confidence, distribution -> topic_weight). That makes them
a cheap independent second opinion and a review-priority signal. They do NOT create truth: their value is
measurable only against YOUR verified gold (`evaluate-benchmark --provider <name>`), so run them on the
benchmark sample after you have reviewed it.

Safety (both are PAID account APIs): nothing is sent unless ALL of
    key in .env + DECISIONS_ENABLED=1 + --yes + --allow-spend + --max-calls N
Default is a dry run that prints the payload of the first question and a cost estimate. Results go ONLY
to classification_proposals (append-only, never the live labels, never verified, never gold)."""
from __future__ import annotations
import json, os, time
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import ClassificationProposal, ClassificationRun, Option, Question, TaxonomyNode, utcnow
from .classify import CHARS_PER_TOKEN, ProviderError, _urllib_transport, question_content_hash

TAXV = "gate-cs-2027"
PROMPT_VERSION = "decisions-v1"
INSTRUCTIONS = ("This is a GATE Computer Science exam question (text and options below). Which ONE syllabus "
                "topic does it primarily test? Judge by the knowledge needed to solve it, not by surface words.")

@dataclass(frozen=True)
class DecisionSpec:
    name: str
    key_env: str
    url_env: str
    default_url: str
    model_env: str
    default_model: str
    price_env: str
    default_price_in_per_m: float     # USD per 1M input tokens (uncached); output is free on both
    images: bool

SPECS = {
    "openai-decisions": DecisionSpec("openai-decisions", "OPENAI_DECISIONS_API_KEY", "OPENAI_DECISIONS_URL",
                                     "https://api.openai.com/v1/decisions", "OPENAI_DECISIONS_MODEL", "gpt-6-luna",
                                     "OPENAI_DECISIONS_PRICE_IN_PER_M", 0.10, True),
    "jev": DecisionSpec("jev", "TYPESAFE_API_KEY", "TYPESAFE_URL", "https://api.typesafe.ai/v1/systemone",
                        "JEV_MODEL", "jev-1.14.0", "JEV_PRICE_IN_PER_M", 0.042, False),
}

def topic_choices(s: Session) -> dict[str, str]:
    """{topic_id: 'Section name - topic name'} for every non-deprecated 2027 topic."""
    nodes = s.scalars(select(TaxonomyNode).where(TaxonomyNode.version == TAXV,
                                                 TaxonomyNode.deprecated == False)).all()  # noqa: E712
    sec = {n.node_id: n.name for n in nodes if n.level == "section"}
    return {n.node_id: f"{sec.get(n.parent_id, n.parent_id)} - {n.name}" for n in nodes if n.level == "topic"}

def topic_section(s: Session) -> dict[str, str]:
    return {n.node_id: n.parent_id for n in s.scalars(select(TaxonomyNode).where(
        TaxonomyNode.version == TAXV, TaxonomyNode.level == "topic"))}

def question_state(s: Session, q: Question) -> str:
    opts = s.scalars(select(Option).where(Option.question_id == q.id).order_by(Option.label)).all()
    body = q.text or ""
    if opts:
        body += "\n" + "\n".join(f"({o.label}) {o.content}" for o in opts)
    return body

def build_request(spec: DecisionSpec, state: str, choices: dict[str, str], image_data_url: str | None = None):
    url = os.environ.get(spec.url_env) or spec.default_url
    model = os.environ.get(spec.model_env) or spec.default_model
    headers = {"Authorization": "Bearer " + os.environ.get(spec.key_env, "<not set>")}
    if spec.name == "openai-decisions":
        content = [{"type": "input_text", "text": state}]
        if image_data_url and spec.images:
            content.append({"type": "input_image", "image_url": image_data_url})
        payload = {"model": model, "input": [{"role": "user", "content": content}],
                   "questions": [{"type": "choice", "name": "topic", "instructions": INSTRUCTIONS,
                                  "choices": [{"value": k, "description": v} for k, v in choices.items()]}]}
    else:
        payload = {"model": model, "state": state,
                   "questions": {"topic": {"type": "choice", "instructions": INSTRUCTIONS, "criteria": dict(choices)}}}
    return url, headers, payload

def parse_answer(spec: DecisionSpec, resp: dict) -> tuple[str, float, dict[str, float]]:
    """-> (chosen topic, confidence, {topic: probability})."""
    try:
        if spec.name == "openai-decisions":
            a = next(x for x in resp["answers"] if x.get("name") == "topic")
            if a.get("type") == "refusal":
                raise ProviderError("decision refused by the model", kind="refusal")
            probs = {p["value"]: float(p["probability"]) for p in a.get("probabilities", [])}
        else:
            a = resp["answers"]["topic"]
            probs = {k: float(v) for k, v in (a.get("probabilities") or {}).items()}
        return a["choice"], float(a.get("confidence", probs.get(a["choice"], 0.0))), probs
    except (KeyError, StopIteration, TypeError, ValueError) as e:
        raise ProviderError(f"unexpected {spec.name} response shape: {resp!r:.200}") from e

def estimate(s: Session, spec: DecisionSpec, questions: list[Question]) -> dict:
    choices = topic_choices(s)
    overhead = len(INSTRUCTIONS) + sum(len(k) + len(v) + 8 for k, v in choices.items())
    chars = sum(len(question_state(s, q)) + overhead for q in questions)
    tokens = int(chars / CHARS_PER_TOKEN)
    price = float(os.environ.get(spec.price_env) or spec.default_price_in_per_m)
    return {"questions": len(questions), "est_input_tokens": tokens, "price_in_per_1m_usd": price,
            "est_cost_usd": round(tokens / 1e6 * price, 4), "output_tokens": "not charged (both APIs)",
            "note": "estimate from character count; the provider's own usage figures are what you are billed"}

def gate(spec: DecisionSpec, yes: bool, allow_spend: bool, max_calls: int | None) -> str | None:
    """None when a real call is allowed, else why not. Every condition is required."""
    from ..settings import env_flag, load_env
    load_env()
    if not os.environ.get(spec.key_env):
        return f"{spec.key_env} is not set in .env"
    if not env_flag("DECISIONS_ENABLED", False):
        return "DECISIONS_ENABLED=1 is not set in .env (decision models are off by default)"
    if not (yes and allow_spend):
        return f"{spec.name} is a PAID API: pass --yes --allow-spend after you approve the estimate"
    if not max_calls:
        return "pass --max-calls N (a hard cap on paid requests)"
    return None

def run(s: Session, provider: str, questions: list[Question], *, yes: bool = False, allow_spend: bool = False,
        max_calls: int | None = None, transport: Callable | None = None, with_images: bool = False,
        rpm: float = 30.0) -> dict:
    spec = SPECS[provider]
    choices = topic_choices(s); parent = topic_section(s)
    est = estimate(s, spec, questions)
    blocked = gate(spec, yes, allow_spend, max_calls) if transport is None else None
    if blocked or not yes:
        url, headers, payload = build_request(spec, question_state(s, questions[0]) if questions else "", choices)
        return {"dry_run": True, "blocked_because": blocked, "estimate": est, "endpoint": url,
                "first_payload": payload}
    tx = transport or _urllib_transport
    run_row = ClassificationRun(model=os.environ.get(spec.model_env) or spec.default_model,
                                prompt_version=PROMPT_VERSION, provider=provider,
                                stats={"estimate": est, "note": "decision-model proposals; not human verification"})
    s.add(run_row); s.flush()
    done = errors = 0; last = 0.0; stop = None
    for q in questions[: max_calls]:
        if rpm:
            wait = 60.0 / rpm - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        last = time.monotonic()
        img = None
        if with_images and spec.images and q.image_path:
            img = _data_url(q.image_path)
        url, headers, payload = build_request(spec, question_state(s, q), choices, img)
        try:
            resp = tx(url, headers, payload)
            choice, conf, probs = parse_answer(spec, resp)
        except ProviderError as e:
            errors += 1
            if e.status in (401, 402, 403, 404) or errors >= 3:
                stop = f"stopped after error: {e}"; break
            continue
        if choice not in parent:
            errors += 1; continue
        top = dict(sorted(probs.items(), key=lambda kv: -kv[1])[:5])
        row = s.scalar(select(ClassificationProposal).where(
            ClassificationProposal.question_id == q.id, ClassificationProposal.provider == provider,
            ClassificationProposal.model == run_row.model, ClassificationProposal.prompt_version == PROMPT_VERSION))
        if row is None:
            row = ClassificationProposal(question_id=q.id, provider=provider, model=run_row.model,
                                         prompt_version=PROMPT_VERSION, taxonomy_version=TAXV)
            s.add(row)
        row.run_id = run_row.id; row.section_id = parent[choice]; row.primary_topic_id = choice
        row.topic_weight = top; row.concept_ids = []; row.confidence = conf
        row.raw_response = {"usage": resp.get("usage"), "model": resp.get("model"), "probabilities_top5": top}
        row.source_content_hash = question_content_hash(q); row.status = "suggested" if conf >= 0.6 else "flagged"
        done += 1
    run_row.finished_at = utcnow(); run_row.stats = {**run_row.stats, "proposals": done, "errors": errors, "stop": stop}
    s.commit()
    return {"dry_run": False, "proposals_written": done, "errors": errors, "stopped": stop, "estimate": est}

def _data_url(path: str) -> str | None:
    import base64
    from pathlib import Path
    p = Path(path)
    if not p.is_file():
        return None
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()
