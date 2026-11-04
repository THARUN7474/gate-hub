# Chat-assisted classification (no API key)

Use your own ChatGPT or Claude **chat** to propose classifications for small batches, then import the answers as **suggestions**.
No key, no subscription, no network call from this app. It is not automatic: you carry files between the app and the chat.

## The round trip

```powershell
# 1. export 10-25 unclassified questions (reads the database only)
python -m src.cli chat-export --years 2022-2026 --size 20
#    or one paper:   python -m src.cli chat-export --paper-id GATE-CS-2026-S2 --size 20
#    short form:     .\scripts\dev.ps1 chat-export --years 2022-2026
```
This writes `exports\chat_batches\<batch id>\`:

| File | What to do with it |
| --- | --- |
| `prompt.md` | open it, copy everything, paste into a **new** chat |
| `images\*.png` | attach them in the same chat (each is the question's original PDF region; vital for figures, tables and notation) |
| `answers_template.json` | the shape the answer must have (the prompt already asks for it) |
| `batch.json` | the manifest the importer checks against - do not edit |

2. The chat replies with JSON only. Save that reply as `answers.json` in the same folder (a ```json fence around it is fine).
3. Check it - **this changes nothing**:
```powershell
python -m src.cli chat-import "exports\chat_batches\<batch id>" "exports\chat_batches\<batch id>\answers.json" --model "ChatGPT GPT-5 (chat)"
```
4. Read the report (new / flagged / skipped / rejected with a reason per question). If it is right, import:
```powershell
python -m src.cli chat-import "exports\chat_batches\<batch id>" "exports\chat_batches\<batch id>\answers.json" --model "ChatGPT GPT-5 (chat)" --yes
```
   `--yes` takes a verified database backup first, then writes the accepted rows only.
5. Open **Review Workspace**, filter the paper, review each suggestion against its image (`docs/18_HUMAN_REVIEW_AND_SCORING.md`).

Repeat with the next batch: questions that already have a suggestion are not exported again.

## What the importer checks (every row)

| Check | If it fails |
| --- | --- |
| the file is for this batch (`batch_id`) and names the chat model | whole file refused |
| JSON shape: required fields, confidence 0-1 | row rejected with the field and reason |
| the question is in this batch, appears once | rejected |
| the stored question text/options are unchanged since export (SHA-256 per question) | rejected: re-export |
| every id exists, is not deprecated, in the batch's taxonomy version; the primary topic belongs to the section; concepts/prerequisites exist | rejected, listing the bad ids |
| a human verified or corrected this question | skipped - never touched |
| an AI suggestion already exists | skipped, unless `--replace-unverified` (replaced in place, audit event `classification_replaced`; never a second row) |
| the chat set `needs_review`, confidence < 0.5, or the section contradicts the paper's GA/CS block | imported as `flagged`, question marked for review with the reason |

Imported rows: `status=suggested` (or `flagged`), `provenance=inferred`, `prompt_version=chat-v1`, `model=<your --model text>`,
run `provider=chat-assisted`, `raw_response` = the exact item plus its batch id; the run stores a SHA-256 of the answers file.
**Nothing is ever imported as verified.**

## Tips
- 20 questions per chat works well; start a new chat for every batch so earlier answers don't leak in.
- Always attach the images. Scanned years and questions with figures are unreliable from text alone.
- If the chat invents an id, the importer rejects that row; ask the chat to correct only those rows and re-run the check.
- The official answer is included in the prompt (it helps identify the tested concept); it is never changed by an import.

Tested by `tests/test_chat_batch.py` (export, every rejection reason, no-overwrite of human work, flagged rows, CLI round trip).
