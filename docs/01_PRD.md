# Phase 1 PRD - GATE CSE Intelligence (5-Day Local MVP)

## Goal

One working LOCAL application: GATE CSE papers (2012-2026, all sessions) +
official keys + 2027 syllabus in -> a trustworthy, deeply classified question
bank with useful analysis out.

## Definition of success

Select Operating System -> Deadlock-equivalent topic, choose any year or range,
and immediately see every matching question with session, question number,
official key, concepts, confidence, review status, totals, and the original
source crop. Every aggregate number drills down to actual question records.

By Day 5 we must know EXACTLY which papers succeeded, which failed, and why.
15-year verified coverage is the corpus goal, not a Day-5 promise: coverage is
whatever passes validation, reported measured, never asserted.

## In scope (frozen)

- Local PDF ingestion (files, directories, ZIPs) with dedup and inventory
- Question/option/marks/type extraction with original page crops
- Official key matching (CSV import path; anomalies modelled)
- Official-syllabus taxonomy (versioned, verbatim sections)
- One-provider LLM classification with structured output, evidence, confidence
- Human review workspace with audit history; corrections survive reruns
- SQLite fallback / PostgreSQL 17 + pgvector primary; FTS + structured filters
- Year x subject / year x topic matrices, type/marks mix, priority ranking,
  pipeline status, CSV/JSON exports, data-quality report

## Out of scope (frozen)

Cloud storage/S3, Kubernetes/Terraform, user authentication, multi-agent
orchestration, vector RAG (pgvector embeddings optional Day 5 only), fine-tuning,
cloud monitoring, AI tutor/quiz platform, deployment, other GATE branches,
EAPCET (later reuse only), student accounts, personalized plans.

## Users

Owner (Tharun) + his coding agents (Claude Code, Codex, Antigravity).

## Deliverables (all local)

1. Question database (questions, options, keys, metadata, source refs)
2. Classification dataset (section/topic/concepts, confidence, provenance)
3. Analytics matrices (counts, marks, trends; drill-down everywhere)
4. Concept/prerequisite data (curated edges; classifier-proposed stay inferred)
5. Local Streamlit app (browser, matrix, topic report, review workspace, status)
6. Quality report (exports/validation_report.json: missing files, unmatched
   keys, ambiguous classifications, coverage)

## Acceptance (the gate, not a wish)

All checks in docs/04_CHECKLISTS.md "Definition of done" pass, and the
validation report states measured coverage. Nothing unverified is labelled
complete.
