"""One CLI for humans and coding agents. Local only: nothing here deploys,
uploads, or spends money. The real LLM provider raises until key + approved
spend exist."""
from __future__ import annotations
import json
from pathlib import Path
import typer, yaml

from .analytics import analyze as az, exports as ex
from .classification import classify as cl
from .db.session import init_schema, make_session
from .extraction.extract import extract_questions, persist_records, reconcile
from .ingestion import ingest as ig
from .ingestion import keys as kmod
from .taxonomy import taxonomy as tx
from .extraction.extract import extract_questions as _extract_for_drift
from .validation import drift as dr
from .validation import review as rv, validate as vd

from .settings import load_env as _load_env
_load_env()

app = typer.Typer(help="GATE CSE Intelligence - Phase 1 local pipeline")
DB_URL = typer.Option(None, help="overrides GATE_DB_URL")
CFG = typer.Option("config.yaml")

def _cfg(path: str) -> dict:
    return yaml.safe_load(open(path))

def _require_current_schema(db_url: str | None) -> None:
    """Old-schema database (e.g. the live DB before promotion): say what is missing in plain words instead of a
    stack trace. Reads the schema only; changes nothing."""
    from .db import dev_upgrade as du
    missing = du.missing_schema(db_url)
    if missing:
        typer.echo("This database was created by an older version and lacks: " + ", ".join(missing[:6]) + ".\n"
                   "Nothing was read or changed. The additive upgrade is part of promotion: run the dry run "
                   "`.\\scripts\\dev.ps1 promote` and then, if you approve, `promote --yes` - or open the app and use "
                   "'Back up the database, then upgrade it'.")
        raise typer.Exit(3)

@app.command()
def init(db_url: str | None = DB_URL):
    """Dev shortcut (SQLite/no-Docker). On Postgres prefer: alembic upgrade head"""
    init_schema(db_url)
    typer.echo("schema ready")

@app.command()
def taxonomy(db_url: str | None = DB_URL, config: str = CFG):
    cfg = _cfg(config)
    tax = tx.load_taxonomy(cfg["taxonomy_file"])
    errors = tx.validate_taxonomy(tax)
    if errors:
        for e in errors: typer.echo(f"TAXONOMY ERROR: {e}")
        raise typer.Exit(1)
    with make_session(db_url) as s:
        n = tx.upsert_taxonomy(s, tax)
        s.commit()
    typer.echo(f"loaded {n} taxonomy nodes, version {tax['taxonomy_version']}")

@app.command()
def ingest(path: str, year: int, session: str, role: str | None = None,
           expected_questions: int | None = None, expected_marks: float | None = None,
           source_url: str | None = None, db_url: str | None = DB_URL):
    """Register a paper file (PDF). Directories/ZIPs: extract first, then ingest each."""
    with make_session(db_url) as s:
        run = ig.start_run(s, "ingest", detail={"path": path})
        doc, is_new = ig.register_document(s, path, role, source_url)
        pid, state = ig.register_paper(s, year, session, doc.id if doc.doc_type != "key" else None,
                                       expected_questions, expected_marks)
        ig.finish_run(s, run, "done" if state != "conflict" else "conflict",
                      detail={"paper_id": pid, "state": state})
        s.commit()
    if state == "conflict":
        typer.echo(f"CONFLICT: a different file already claims {pid}. Human reconciliation required.")
        raise typer.Exit(2)
    typer.echo(f"registered {pid} ({'new document' if is_new else 'duplicate hash, reused'})")

@app.command()
def extract(paper_id: str, pdf: str, db_url: str | None = DB_URL,
            assets_root: str = "data/assets", write_crops: bool = False):
    with make_session(db_url) as s:
        run = ig.start_run(s, "extract", detail={"paper_id": paper_id})
        records = extract_questions(pdf, paper_id, assets_root, write_crops=write_crops)
        res = persist_records(s, records)
        rec = reconcile(s, paper_id)
        ig.finish_run(s, run, "done", detail={**res, **rec})
        s.commit()
    typer.echo(json.dumps({**res, **rec}, indent=2))

@app.command()
def keys(paper_id: str, csv_file: str, key_version: str = "final", db_url: str | None = DB_URL):
    with make_session(db_url) as s:
        result = kmod.import_keys_csv(s, paper_id, csv_file, key_version)
        s.commit()
    typer.echo(json.dumps(result, indent=2))

@app.command()
def classify(provider: str = "mock", paper_id: str | None = None, sample: float = 1.0,
             taxonomy_version: str = "gate-cs-2027", estimate_cost: bool = False,
             price_in: float = 0.0, price_out: float = 0.0,
             allow_spend: bool = False, dry_run: bool = False, model: str | None = None,
             allow_external: bool = False, free_only: bool = False,
             reclassify: bool = typer.Option(False, help="replace UNVERIFIED suggestions from another prompt "
                                             "version (audited). Default: leave them, so no question gets two rows."),
             proposals: bool = typer.Option(False, help="write INDEPENDENT per-provider proposals to "
                                            "classification_proposals instead of touching the classifications "
                                            "table: existing agent labels and human review stay untouched, and "
                                            "agreement is compared afterwards with proposals-report."),
             years: str | None = typer.Option(None, help="only these years, e.g. 2022-2026 or 2017,2019-2021"),
             max_calls: int | None = typer.Option(None, help="hard cap on API calls this run (retries count)"),
             checkpoint_every: int = typer.Option(10, help="commit to the database every N questions"),
             db_url: str | None = DB_URL):
    """Classify questions. Providers: mock (offline) | gemini | groq |
    openrouter | anthropic | openai | auto (tries available providers in
    GATE_LLM_PRIORITY order with bounded failover, never crossing consent
    gates) | free (first available free-tier). Free-tier
    providers need the key in .env AND --allow-external (or
    GATE_LLM_ALLOW_EXTERNAL=1): question text leaves this machine. Paid
    providers keep the --allow-spend gate. --dry-run prints the exact request
    payloads and a MEASURED cost estimate without any network call.
    Already-classified questions are skipped; a quota/billing/auth error stops the run (exit code 3)
    with everything done so far saved, and re-running continues where it stopped."""
    from .settings import external_calls_allowed
    try:
        yrs = cl.parse_years(years)
    except ValueError as e:
        typer.echo(str(e)); raise typer.Exit(2)
    with make_session(db_url) as s:
        est = lambda: cl.estimate_cost(s, paper_id, price_in, price_out, years=yrs,
                                       only_unclassified=not reclassify, taxonomy_version=taxonomy_version)
        if estimate_cost:
            typer.echo(json.dumps(est(), indent=2))
            return
        if dry_run:
            typer.echo(json.dumps(est(), indent=2))
        if provider == "auto":
            result = cl.run_auto_classification(
                s, taxonomy_version, paper_id, sample, allow_spend=allow_spend,
                dry_run=dry_run, allow_external=allow_external or external_calls_allowed(),
                free_only=free_only, reclassify=reclassify)
        elif proposals:
            if provider == "auto":
                typer.echo("--proposals needs one explicit provider (agreement is per provider); "
                           "auto picks silently."); raise typer.Exit(2)
            if reclassify:
                typer.echo("--proposals never overwrites anything; --reclassify does not apply.")
                raise typer.Exit(2)
            result = cl.run_proposals(
                s, cl.get_provider(provider, model=model, free_only=free_only),
                taxonomy_version, paper_id, sample, allow_spend=allow_spend,
                dry_run=dry_run, allow_external=allow_external or external_calls_allowed(),
                years=yrs, max_calls=max_calls, checkpoint_every=checkpoint_every)
        else:
            result = cl.run_classification(
                s, cl.get_provider(provider, model=model, free_only=free_only),
                taxonomy_version, paper_id, sample, allow_spend=allow_spend,
                dry_run=dry_run, allow_external=allow_external or external_calls_allowed(),
                reclassify=reclassify, years=yrs, max_calls=max_calls,
                checkpoint_every=checkpoint_every)
        if not dry_run:
            s.commit()
    typer.echo(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("stopped"):
        raise typer.Exit(3)


@app.command()
def proposals_report(taxonomy_version: str = "gate-cs-2027", db_url: str | None = DB_URL):
    """Agreement between independent provider proposals (classification_proposals) and the
    current labels in classifications. Proposals never overwrite labels; this shows how
    much each provider agrees, where it fills still-unclassified questions, and how many
    compared labels are human-verified ground truth."""
    with make_session(db_url) as s:
        report = {"agreement": cl.proposal_agreement(s, taxonomy_version),
                  "staleness": cl.proposal_staleness(s, taxonomy_version)}
    typer.echo(json.dumps(report, indent=2))


@app.command()
def benchmark_sample(n: int = 120, seed: int = 42,
                     batch: str = typer.Option(None, help="batch name; default bench-<date>"),
                     db_url: str | None = DB_URL):
    """Pick a stratified sample of questions for HUMAN gold review (stratified by
    paper and marks, deterministic for a given seed). Rows are written with
    status='pending_user_review' - the tool never assigns gold labels; only your
    review turns a row into gold, and metrics read only verified gold."""
    from .validation import benchmark as bm
    from datetime import date
    batch = batch or f"bench-{date.today().isoformat()}"
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        result = bm.select_benchmark_sample(s, n, seed, batch)
        s.commit()
    typer.echo(json.dumps(result, indent=2))


@app.command()
def benchmark_status(db_url: str | None = DB_URL):
    """Benchmark sample counts per status and per batch (pending vs verified gold)."""
    from .validation import benchmark as bm
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        typer.echo(json.dumps(bm.benchmark_status(s), indent=2))


@app.command()
def evaluate_benchmark(taxonomy_version: str = "gate-cs-2027", batch: str | None = None,
                       provider: str | None = typer.Option(None, help="score this provider's "
                                                           "proposals instead of the current labels"),
                       db_url: str | None = DB_URL):
    """Score predictions against USER-VERIFIED gold only (topic/section accuracy,
    per-section and per-year breakdown, concept P/R/F1, calibration). No verified
    gold yet -> an honest zero-sample report, never made-up numbers."""
    from .validation import metrics as mt
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        typer.echo(json.dumps(mt.evaluate_benchmark(s, taxonomy_version, batch, provider), indent=2))


@app.command()
def review_queue(limit: int | None = None, no_spotcheck: bool = False,
                 db_url: str | None = DB_URL):
    """The review queue in priority order: taxonomy gaps, classifier-flagged,
    low-confidence, extraction issues, provider disagreements, then remaining
    suggestions, with a small verified spot-check sample at the end."""
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        rows = rv.prioritized_review_queue(s, limit=limit, include_spotcheck=not no_spotcheck)
    typer.echo(json.dumps(rows, indent=2))


@app.command()
def classify_local(paper_id: str | None = None, taxonomy_version: str = "gate-cs-2027",
                   reclassify: bool = typer.Option(False, help="replace UNVERIFIED suggestions from "
                                                   "another prompt version (audited)"),
                   flag_below: float = 0.45,
                   db_url: str | None = DB_URL):
    """Fully offline first-pass classification with the local keyword heuristic
    (model=local-heuristic-v1, provenance=inferred, never verified). No network,
    no key, no external disclosure. Strong on named concepts, weak on bare
    numerical problems; low-confidence rows are flagged for human review."""
    from .classification.heuristic import run_local_classify
    with make_session(db_url) as s:
        result = run_local_classify(s, taxonomy_version,
                                    [paper_id] if paper_id else None,
                                    reclassify=reclassify, flag_below=flag_below)
    typer.echo(json.dumps(result, indent=2))

@app.command()
def classify_compare(provider: str, paper_id: str | None = None, sample: float = 0.08,
                     taxonomy_version: str = "gate-cs-2027", model: str | None = None,
                     allow_spend: bool = False, allow_external: bool = False,
                     db_url: str | None = DB_URL):
    """Run ONE provider on a small SAMPLE of already-classified questions and print its AGREEMENT with the
    existing suggestions (section/topic match, id validity). Writes NOTHING. Agreement, not accuracy: the
    existing suggestions are unverified unless a human verified them. Same consent gates as `classify`.
    The sample is spread evenly across the paper. Also prints the ACTUAL tokens used and the question ids that
    need a human look."""
    from .settings import external_calls_allowed
    with make_session(db_url) as s:
        res = cl.compare_with_existing(
            s, cl.get_provider(provider, model=model), taxonomy_version, paper_id, sample,
            allow_spend=allow_spend, allow_external=allow_external or external_calls_allowed())
    typer.echo(json.dumps(res, indent=2))
    if res.get("stopped"):
        raise typer.Exit(3)

@app.command()
def classify_ensemble(paper_id: str | None = None, sample: float = 1.0,
                      taxonomy_version: str = "gate-cs-2027",
                      allow_spend: bool = False, dry_run: bool = False,
                      allow_external: bool = False, include_paid: bool = False,
                      reclassify: bool = False,
                      db_url: str | None = DB_URL):
    """Classify every question with ALL available providers and combine the
    results: consensus topic by majority vote (confidence tiebreak),
    agreement = fraction of providers on the winning topic, combo_score =
    agreement x mean confidence (review-priority heuristic, not a correctness
    probability). Free-tier providers participate with --allow-external;
    paid ones only with --include-paid AND --allow-spend."""
    from .settings import external_calls_allowed
    names, skipped = cl.runnable_providers(
        allow_spend=allow_spend and include_paid,
        allow_external=allow_external or external_calls_allowed(),
        free_only=not include_paid)
    if not names:
        typer.echo("No providers can run under the current keys/consents: "
                   f"{skipped}. Add keys (see .env.example) "
                   "or use `classify --provider mock` for offline work.")
        raise typer.Exit(1)
    for n, why in skipped.items():
        typer.echo(f"skipping {n}: {why}")
    typer.echo(f"ensemble providers: {', '.join(names)}")
    with make_session(db_url) as s:
        result = cl.run_ensemble(
            s, [cl.get_provider(n) for n in names], taxonomy_version, paper_id,
            sample, allow_spend=allow_spend and include_paid, dry_run=dry_run,
            allow_external=allow_external or external_calls_allowed(), reclassify=reclassify)
        if not dry_run:
            s.commit()
    typer.echo(json.dumps(result, indent=2))

@app.command()
def chat_export(years: str | None = typer.Option(None, help="e.g. 2022-2026 (newest first)"),
                paper_id: str | None = typer.Option(None, help="one paper, e.g. GATE-CS-2026-S2"),
                size: int = typer.Option(20, help="questions per batch, 1-25"),
                include_classified: bool = typer.Option(False, help="also export questions that already have a suggestion"),
                images: bool = typer.Option(True, help="render each question's PDF region as a PNG to attach"),
                out: str = typer.Option("exports/chat_batches", help="where batch folders are written"),
                taxonomy_version: str = "gate-cs-2027", db_url: str | None = DB_URL):
    """NO API KEY: write one batch folder for ChatGPT/Claude chat (prompt.md to paste, images to attach, batch.json,
    answers_template.json). Exports unclassified questions by default. Reads the database only."""
    from .classification import chat_batch as cb
    try:
        yrs = cl.parse_years(years)
    except ValueError as e:
        typer.echo(str(e)); raise typer.Exit(2)
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        try:
            r = cb.export_batch(s, out, paper_id=paper_id, years=yrs, size=size, include_classified=include_classified,
                                taxonomy_version=taxonomy_version, images=images)
        except ValueError as e:
            typer.echo(str(e)); raise typer.Exit(2)
    if not r["batch_dir"]:
        typer.echo(r["note"]); return
    typer.echo(f"Batch {r['batch_id']}: {r['questions']} questions ({r['first']} .. {r['last']}), {r['images']} image(s)\n"
               f"Folder: {r['batch_dir']}\n"
               "Next: open prompt.md, paste it into a NEW chat, attach the PNGs from images/, save the JSON reply as\n"
               f"answers.json in that folder, then:  python -m src.cli chat-import \"{r['batch_dir']}\" "
               f"\"{r['batch_dir']}\\answers.json\"   (dry run; add --yes to import)")

@app.command()
def chat_import(batch_dir: str, answers: str,
                model: str | None = typer.Option(None, help="which chat model answered (else model_or_agent in the JSON)"),
                yes: bool = typer.Option(False, "--yes", help="actually import (default: validate only, change nothing)"),
                replace_unverified: bool = typer.Option(False, help="replace an existing UNVERIFIED suggestion (audited)"),
                db_url: str | None = DB_URL):
    """Validate a chat's JSON answers against the batch + taxonomy + database and (with --yes) import them as
    SUGGESTIONS. Never verified; never touches a question a human verified or corrected."""
    from .classification import chat_batch as cb
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        try:
            rep = cb.import_answers(s, batch_dir, answers, model_label=model, apply=False,
                                    replace_unverified=replace_unverified)
        except (ValueError, OSError, json.JSONDecodeError) as e:
            typer.echo(f"Cannot import: {e}"); raise typer.Exit(2)
        for r in rep["rows"]:
            typer.echo(f"  {r['action']:8s} {r['question_id']:24s} {r.get('status', ''):10s} {r.get('why', '')}")
        typer.echo(f"\n{rep['new']} new, {rep['replace']} replace, {rep['flagged']} of those flagged for review, "
                   f"{rep['skipped']} skipped, {rep['rejected']} rejected; missing from answers: {rep['missing_from_answers'] or 'none'}")
        if not yes:
            typer.echo("VALIDATION ONLY - nothing was written. Re-run with --yes to import the accepted rows."); return
        if not (rep["new"] or rep["replace"]):
            typer.echo("nothing to import."); return
        from . import backup as bk
        b = bk.backup(db_url)
        if b.get("integrity_check") not in (None, "ok"):
            typer.echo("backup integrity FAILED - nothing imported"); raise typer.Exit(1)
        rep = cb.import_answers(s, batch_dir, answers, model_label=model, apply=True, replace_unverified=replace_unverified)
        s.commit()
    typer.echo(f"Backup: {b['file']}\nImported {rep['new'] + rep['replace']} suggestion(s) (run {rep.get('run_id')}). "
               "They are suggestions: review them in the Review Workspace.")

@app.command()
def review_status(db_url: str | None = DB_URL):
    """Human-review coverage with numerators and denominators (not model accuracy)."""
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        typer.echo(json.dumps(rv.review_coverage(s), indent=2))

@app.command()
def upgrade_dev(db_url: str | None = DB_URL):
    """Dev-only additive schema upgrade for databases created before v6
    (adds ensemble columns; backfills combo fields for old single-provider
    rows). Idempotent. On PostgreSQL prefer: alembic upgrade head"""
    from .db import dev_upgrade
    typer.echo(json.dumps(dev_upgrade.upgrade_schema(db_url), indent=2))

@app.command()
def llm_status():
    """Show which LLM providers have keys set (never the keys), the priority
    order, and what `auto` would pick."""
    from .settings import load_env, external_calls_allowed
    load_env()
    out = {"providers": cl.provider_status(),
           "priority": cl.priority_list(),
           "external_calls_allowed": external_calls_allowed()}
    try:
        out["auto_picks"] = cl.resolve_provider_name("auto")
    except RuntimeError as e:
        out["auto_picks"] = None
        out["auto_error"] = str(e)
    typer.echo(json.dumps(out, indent=2))

_MODEL_ENVS = {"freellmapi": "FREELLMAPI_MODEL", "gemini": "GEMINI_MODEL", "groq": "GROQ_MODEL", "openrouter": "OPENROUTER_MODEL",
               "anthropic": "ANTHROPIC_MODEL", "openai": "OPENAI_MODEL"}

@app.command()
def set_key(provider: str = typer.Argument(..., help="freellmapi | openai-decisions | jev | gemini | groq | openrouter | anthropic | openai"),
            model: str | None = typer.Option(None, help="also save this provider's model name (e.g. GEMINI_MODEL)"),
            env_file: str = typer.Option(".env", help="file to write (default: .env, which is gitignored)")):
    """Save an API key into .env WITHOUT ever echoing it.

    The key is typed/pasted at a hidden prompt (nothing appears on screen), written to .env only, and never
    printed, logged or sent anywhere. This does NOT enable any external call: that still needs
    GATE_LLM_ALLOW_EXTERNAL=1 (and, for gemini/groq, your own free-plan statement) in .env."""
    import re as _re
    from dotenv import set_key as _dotenv_set_key
    from .classification import decision_models as _dm
    name = provider.lower().strip()
    reg = cl._PROVIDER_REGISTRY
    if name in _dm.SPECS:                      # decision models: separate keys, separate from FreeLLMAPI
        key_env = _dm.SPECS[name].key_env
    elif name not in _MODEL_ENVS or name not in reg:
        typer.echo(f"Unknown provider {provider!r}. Choose one of: {', '.join(list(_MODEL_ENVS) + list(_dm.SPECS))}")
        raise typer.Exit(2)
    else:
        key_env = reg[name]["key_env"]
    raw = typer.prompt(f"Paste your {name} API key (input is hidden - nothing will show as you paste)",
                       hide_input=True)
    value = raw.strip().strip("'\"")
    if len(value) < 10 or _re.search(r"\s", value):
        typer.echo("That does not look like an API key (too short, or contains spaces). Nothing was saved."); raise typer.Exit(2)
    _dotenv_set_key(env_file, key_env, value, quote_mode="never")
    typer.echo(f"Saved {key_env} to {env_file} ({len(value)} characters). It was not printed or sent anywhere.")
    if model:
        menv = _dm.SPECS[name].model_env if name in _dm.SPECS else _MODEL_ENVS[name]
        _dotenv_set_key(env_file, menv, model.strip(), quote_mode="never")
        typer.echo(f"Saved {menv}={model.strip()}")
    typer.echo("Next: `python -m src.cli llm-status` (shows the key as set, never its value). "
               "External calls stay OFF until you set GATE_LLM_ALLOW_EXTERNAL=1 yourself.")

@app.command()
def llm_models(provider: str = typer.Argument("gemini", help="'gemini' or 'freellmapi'"),
               all_models: bool = typer.Option(False, "--all", help="include models that cannot generateContent")):
    """List the model IDs your API key can see (so you can pick GEMINI_MODEL).

    Sends ONLY your API key to the provider's model-list endpoint: no question text leaves this machine.
    Seeing a model does not prove the free tier serves it - quota and billing show up only on a real call."""
    from .settings import load_env
    load_env()
    if provider.lower() == "freellmapi":
        try:
            models = cl.list_freellmapi_models()
        except RuntimeError as e:
            typer.echo(str(e)); raise typer.Exit(1)
        typer.echo(f"{len(models)} model(s) the FreeLLMAPI router can call right now with your keys:")
        for m in models:
            typer.echo(f"  {m['id']:<48} {m['owned_by'] or ''}")
        typer.echo("\nDefault FREELLMAPI_MODEL=auto lets the router choose and fail over. Pin one with:\n"
                   "  python -m src.cli set-key freellmapi --model <id>   (or set FREELLMAPI_MODEL in .env)")
        return
    if provider.lower() != "gemini":
        typer.echo("Only 'gemini' is supported here. For groq/openrouter/anthropic/openai use the provider's own model list "
                   "(links in docs/13_LLM_SETUP.md)."); raise typer.Exit(2)
    try:
        models = cl.list_gemini_models(generate_only=not all_models)
    except RuntimeError as e:          # missing key (or a ProviderError: it subclasses RuntimeError)
        ex = cl.explain_provider_error(str(e))
        typer.echo(str(e) if "GEMINI_API_KEY" in str(e) else f"{ex['what']}\nFix: {ex['fix']}\nRaw: {ex['raw']}")
        raise typer.Exit(1)
    typer.echo(f"{len(models)} model(s) visible to your key"
               f"{'' if all_models else ' that support generateContent'}:")
    for m in models:
        typer.echo(f"  {m['id']:<42} in={m['input_tokens']!s:>8} out={m['output_tokens']!s:>7}  {m['display_name']}")
    typer.echo("\nPick one and save it with:  python -m src.cli set-key gemini --model <id>   (or set GEMINI_MODEL in .env).")
    typer.echo("Prefer a '-lite' or 'flash' model first: they are the cheapest and most likely to be on the free tier.")

@app.command()
def decisions(provider: str = typer.Argument(..., help="openai-decisions | jev"),
              benchmark: bool = typer.Option(False, "--benchmark", help="the 120-question gold sample (recommended)"),
              paper_id: str | None = typer.Option(None, help="or one paper"),
              yes: bool = typer.Option(False, "--yes", help="actually call (default: dry run)"),
              allow_spend: bool = typer.Option(False, "--allow-spend", help="required: both APIs are paid"),
              max_calls: int | None = typer.Option(None, help="hard cap on paid requests (required for a real run)"),
              with_images: bool = typer.Option(False, help="openai-decisions only: also send the PDF crop"),
              db_url: str | None = DB_URL):
    """Decision-model second opinion (typed topic choice with calibrated probabilities) - SEPARATE from the
    FreeLLMAPI chat router. Writes only classification_proposals (never live labels, never gold).
    Dry run by default: prints the cost estimate and the first payload. A real run needs the provider key,
    DECISIONS_ENABLED=1 in .env, --yes --allow-spend and --max-calls. Score afterwards with
    `evaluate-benchmark --provider <name>` (meaningful only once you have verified gold)."""
    from .settings import load_env
    from .classification import decision_models as dm
    from sqlalchemy import select
    from .db.models import BenchmarkSample, Question
    load_env()
    if provider not in dm.SPECS:
        typer.echo(f"unknown provider {provider!r}: {', '.join(dm.SPECS)}"); raise typer.Exit(2)
    if benchmark == bool(paper_id):
        typer.echo("choose exactly one of --benchmark or --paper-id"); raise typer.Exit(2)
    with make_session(db_url) as s:
        if benchmark:
            ids = sorted(s.scalars(select(BenchmarkSample.question_id)))
            qs = [s.get(Question, i) for i in ids]
        else:
            qs = s.scalars(select(Question).where(Question.paper_id == paper_id).order_by(Question.q_number)).all()
        from .analytics.dupes import duplicate_map
        _copies = duplicate_map(s)["copy_of"]
        qs = [q for q in qs if q.id not in _copies]          # duplicate copies follow their original
        res = dm.run(s, provider, qs, yes=yes, allow_spend=allow_spend, max_calls=max_calls, with_images=with_images)
    if res.get("dry_run"):
        res["first_payload"] = json.dumps(res["first_payload"], ensure_ascii=False)[:1500] + " ..."
    typer.echo(json.dumps(res, indent=2, ensure_ascii=False))

@app.command()
def review(db_url: str | None = DB_URL):
    with make_session(db_url) as s:
        typer.echo(json.dumps(rv.review_queue(s), indent=2))

@app.command()
def analyze(year_from: int = 2011, year_to: int = 2026, out: str = "docs/analysis/ANALYSIS.md",
            db_url: str | None = DB_URL):
    """Write the section-by-year matrix (+ coverage) as markdown. Default: docs/analysis/ANALYSIS.md."""
    with make_session(db_url) as s:
        md = az.matrix_markdown(s, year_from, year_to)
        cov = az.coverage_report(s)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(md + "\n\n## Coverage\n\n```json\n" + json.dumps(cov, indent=2) + "\n```\n")
    typer.echo(f"wrote {out}")

@app.command()
def export(out_dir: str = "exports", year_from: int = 2011, year_to: int = 2026,
           db_url: str | None = DB_URL):
    with make_session(db_url) as s:
        typer.echo(json.dumps(ex.export_all(s, out_dir, year_from, year_to), indent=2))

@app.command()
def validate(db_url: str | None = DB_URL):
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        checks = vd.run_checks(s)
    for c in checks:
        typer.echo(f"{'PASS' if c['ok'] else 'FAIL'}  {c['check']}  {c['details']}")
    if not all(c["ok"] for c in checks):
        raise typer.Exit(1)

@app.command()
def stats(db_url: str | None = DB_URL):
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        typer.echo(json.dumps(az.coverage_report(s), indent=2))

@app.command()
def drift_check(paper_id: str, pdf: str, db_url: str | None = DB_URL,
                assets_root: str = "data/assets"):
    """Re-extract the paper and compare against stored rows: exact match,
    normalized (glyph/spacing) match, or real content drift. Count
    reconciliation alone cannot see text changes - this can."""
    records = _extract_for_drift(pdf, paper_id, assets_root)
    with make_session(db_url) as s:
        report = dr.compare_records_vs_db(s, records)
    typer.echo(json.dumps(report, indent=2))
    if report["summary"]["changed"] or report["summary"]["missing_from_pdf"]:
        raise typer.Exit(2)

@app.command()
def doctor(db_url: str | None = DB_URL):
    """Check this machine + project (Python, packages, DB, schema, PDFs, keys, Docker)
    and print PASS/WARN/FAIL with the exact fix. Never prints secrets; read-only."""
    from . import doctor as dc
    res = dc.run_checks(db_url)
    typer.echo(dc.render(res))
    if any(r["level"] == dc.FAIL for r in res):
        raise typer.Exit(1)

@app.command()
def backup(out_dir: str = "backups", db_url: str | None = DB_URL):
    """Write a verified, timestamped backup of the CURRENT database (SQLite online-backup
    API or pg_dump). Safe to run while the app is open; never modifies the database."""
    from . import backup as bk
    typer.echo(json.dumps(bk.backup(db_url, out_dir), indent=2))

@app.command()
def papers_probe(only: str | None = typer.Option(None, help="comma list of years or paper ids"),
                 manifest: str = typer.Option("manifests/papers.yaml"),
                 include_pending: bool = False, as_json: bool = False):
    """Extract every registered paper IN MEMORY (no database writes) and print the
    reconciliation gate: question count, marks, types, gaps, OCR use, flags."""
    from .ingestion import registry as rg
    rows = []
    for e in rg.select(rg.load_manifest(manifest), only, include_pending):
        try:
            rows.append(rg.probe_entry(e))
        except Exception as ex:  # report, keep going: one bad paper must not hide the rest
            rows.append({"paper_id": e.paper_id, "error": f"{type(ex).__name__}: {ex}", "reconciles": False})
    if as_json:
        typer.echo(json.dumps(rows, indent=2, default=str)); return
    for r in rows:
        if "error" in r:
            typer.echo(f"ERR  {r['paper_id']:18s} {r['error']}"); continue
        typer.echo(f"{'OK  ' if r['reconciles'] else 'FAIL'} {r['paper_id']:18s} q={r['questions']:3d} marks={r['marks']:5.1f} "
                   f"types={r['types']} review={r['needs_review']:2d} ocr_pages={r['ocr_pages']} "
                   f"missing={r['missing_numbers']} gaps={r['gaps']} rejected={r['rejected_candidates']}")
        if r["flag_reasons"]:
            typer.echo(f"       flags: {r['flag_reasons']}")

@app.command()
def papers_load(only: str | None = typer.Option(None, help="comma list of years or paper ids"),
                manifest: str = typer.Option("manifests/papers.yaml"),
                include_pending: bool = False, refresh: bool = typer.Option(
                    False, help="rewrite text+options of questions NO human has touched (repairs extractor defects)"),
                no_keys: bool = False, db_url: str | None = DB_URL):
    """Register + extract + reconcile + import keys for every paper in the manifest.
    Idempotent. Never changes human-reviewed rows. Prints one summary per paper."""
    from .ingestion import registry as rg
    entries = rg.select(rg.load_manifest(manifest), only, include_pending)
    summary = []
    for e in entries:
        with make_session(db_url) as s:
            try:
                res = rg.load_entry(s, e, refresh=refresh, with_keys=not no_keys)
                s.commit()
            except Exception as ex:
                s.rollback()
                res = {"paper_id": e.paper_id, "error": f"{type(ex).__name__}: {ex}"}
        summary.append(res)
        rc, ex_, ky = res.get("reconcile", {}), res.get("extract", {}), res.get("key", {})
        kdesc = ("no key" if "missing" in ky else f"KEY ERROR {ky['error']}" if "error" in ky else
                 f"key {ky['imported']}/65 typeMismatch={len(ky['type_mismatches'])} marksMismatch={len(ky['marks_mismatches'])}"
                 f"{' msq+' + str(len(ky['upgraded_to_msq'])) if ky['upgraded_to_msq'] else ''}") if ky else "keys skipped"
        flag = "OK  " if rc.get("reconciled") else "FAIL"
        typer.echo(f"{flag} {res['paper_id']:18s} q={rc.get('derived_questions')} marks={rc.get('derived_marks')} "
                   f"created={ex_.get('created')} refreshed={ex_.get('refreshed')} ocr={ex_.get('ocr_pages')} | {kdesc}"
                   + (f" | ERROR {res['error']}" if "error" in res else ""))
    n_ok = sum(1 for r in summary if r.get("reconcile", {}).get("reconciled"))
    typer.echo(f"{n_ok}/{len(summary)} papers reconciled")

@app.command()
def papers_drift(only: str | None = typer.Option(None, help="comma list of years or paper ids"),
                 manifest: str = typer.Option("manifests/papers.yaml"), db_url: str | None = DB_URL):
    """Re-extract every registered paper and compare with the stored rows (exact / normalized / changed).
    Exits 2 if any question shows real content drift or a stored question is missing from its PDF."""
    from .ingestion import registry as rg
    bad = 0
    _require_current_schema(db_url)
    with make_session(db_url) as s:
        for e in rg.select(rg.load_manifest(manifest), only):
            r = rg.drift_entry(s, e)
            ok = r["changed"] == 0 and r["missing_from_pdf"] == 0 and r["new"] == 0
            bad += 0 if ok else 1
            typer.echo(f"{'OK  ' if ok else 'DRIFT'} {r['paper_id']:18s} exact={r['exact']:3d} normalized={r['normalized_match']:2d} "
                       f"changed={r['changed']:2d} new={r['new']:2d} missing={r['missing_from_pdf']:2d}  [{r['layout']}]"
                       + (f"  {r['changed_ids']}" if r["changed"] else ""))
    typer.echo(f"{'all papers re-extract identically' if not bad else str(bad) + ' paper(s) drifted'}")
    if bad:
        raise typer.Exit(2)

@app.command()
def quickstart(out_dir: str = "quickstart-out", db_url: str | None = DB_URL,
               config: str = CFG):
    """Offline end-to-end smoke run: builds the SYNTHETIC fixture paper (no
    real GATE data), runs init -> taxonomy -> ingest -> extract -> keys ->
    mock classify -> analyze -> export -> validate on a throwaway SQLite file.
    Proves a fresh checkout works with zero Docker, network or spend."""
    import subprocess, sys, tempfile
    from pathlib import Path
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    url = db_url or f"sqlite:///{(out / 'quickstart.db').resolve()}"
    pdf, key = out / "fixture_paper.pdf", out / "fixture_key.csv"
    subprocess.run([sys.executable, "scripts/make_fixture.py", str(pdf), str(key)], check=True)
    init_schema(url)
    with make_session(url) as s:
        from .db.models import Document as _Doc, Paper as _Paper
        from sqlalchemy import select as _sel
        real = s.scalars(_sel(_Paper.id).join(_Doc, _Doc.id == _Paper.document_id)
                         .where(_Doc.rights_status != "fixture")).all()
        if real:
            typer.echo(f"REFUSED: {url} already holds non-fixture papers {real}. "
                       "quickstart only writes synthetic fixture data to a throwaway DB. "
                       "Point --db-url / --out-dir elsewhere.")
            raise typer.Exit(3)
        tax = tx.load_taxonomy(_cfg(config)["taxonomy_file"])
        errors = tx.validate_taxonomy(tax)
        if errors:
            for e in errors: typer.echo(f"TAXONOMY ERROR: {e}")
            raise typer.Exit(1)
        tx.upsert_taxonomy(s, tax)
        doc, _ = ig.register_document(s, pdf, role="fixture", rights_status="fixture")
        pid, state = ig.register_paper(s, 2099, "CS-FX", doc.id,
                                       expected_questions=6, expected_marks=8.0)
        recs = extract_questions(pdf, pid, out / "assets")
        res = persist_records(s, recs)
        kmod.import_keys_csv(s, pid, key)
        rec = reconcile(s, pid)
        cls = cl.run_classification(s, cl.get_provider("mock"), "gate-cs-2027", pid)
        s.commit()
        checks = vd.run_checks(s)
    failed = [c for c in checks if not c["ok"]]
    summary = {"paper_id": pid, "extraction": {**res, **rec}, "classification": cls,
               "checks": {c["check"]: c["ok"] for c in checks}}
    typer.echo(json.dumps(summary, indent=2))
    if failed:
        typer.echo(f"quickstart FAILED: {[c['check'] for c in failed]}")
        raise typer.Exit(1)
    typer.echo(f"quickstart OK - synthetic fixture only, db at {url}")

@app.command()
def ui(db_url: str | None = DB_URL):
    import os, subprocess, sys
    env = dict(os.environ)
    if db_url: env["GATE_DB_URL"] = db_url
    subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"], env=env)

if __name__ == "__main__":
    app()
