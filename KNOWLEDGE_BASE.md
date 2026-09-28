# Company Knowledge Base

The gap VOICE_AND_MEETINGS.md called out explicitly: *"There's no document
store to ask, so there's no `ask_documents` intent."* This adds the store and
turns the intent on.

## What it is

Upload a policy, price list, contract template or handbook (PDF, DOCX, TXT,
Markdown, CSV). It's chunked, embedded, and searchable — by the UI at
`/knowledge-base`, or by voice: *"What does our refund policy say about late
returns?"*

```
upload -> extract text -> chunk (~1200 chars, paragraph-aware) -> embed each
chunk -> store

ask    -> embed the question -> cosine similarity over stored chunks
        -> top 5 passages -> model answers from those passages only
```

No vector database. `kb_document_chunks.embedding_json` is a JSON-encoded
`list[float]`, and the similarity search is plain Python — the right trade at
the scale this app runs at (dozens to low hundreds of documents per company),
not a reason to add pgvector or a hosted vector DB before the data volume
needs it.

## Running without an OpenAI key

Upload and extraction still work. Search falls back to a case-insensitive
keyword match instead of cosine similarity, and `ask_documents` returns the
matching passages directly (`mode: "passages_only"`) instead of a synthesised
answer — a worse search, not a broken feature. The UI and the voice response
both say which mode answered. Contract clause extraction (below) has the same
philosophy: a keyword pass over chunks instead of a model read.

## Scanned PDFs (OCR)

A PDF page with no text layer — a scanned contract, a faxed page, a photo of
a document — used to make the whole upload fail with "no extractable text."
Now `document_store._extract_pdf` extracts text page by page and, for any
page that comes back blank, renders that page to an image and runs OCR on it
(`_ocr_pages`, PyMuPDF + pytesseract) instead of giving up. A contract that's
part typed, part scanned (e.g. a hand-signed signature page) gets real text
where it exists and OCR text where it doesn't.

This needs two things beyond the base install: the `pymupdf` and
`pytesseract` pip packages (already in `requirements.txt`), **and** the
`tesseract-ocr` binary on the host — `apt-get install tesseract-ocr` /
`brew install tesseract`. Pip alone isn't enough for OCR; there's no way
around a real OCR engine being installed somewhere. If the binary or the
packages are missing, OCR is silently skipped and behaviour falls back to
the old error — nothing crashes either way. Set `OCR_ENABLED=false` to turn
it off outright (e.g. to keep upload latency predictable), or `OCR_MAX_PAGES`
to cap how many blank pages get OCR'd inline in one request.

`Document.ocr_used` records whether OCR ran for a given upload, and the
`/knowledge-base` UI shows an "OCR" badge on those documents so a scan that
came back thin or garbled doesn't look like a silent, unexplained failure.

## Contract clause extraction

`ask_documents` answers a question you already know to ask — "what's our
notice period?" A different, common need is "read this whole contract and
tell me what's in it" without knowing the twelve questions up front, and
knowing what's conspicuously *missing*. `contract_analysis.py` does that
second job:

```
chunks (already stored by document_store) -> whole-document text
    -> classify against a fixed clause taxonomy -> structured clauses
    -> diff against the taxonomy -> "missing" list
```

The taxonomy (`STANDARD_CLAUSE_TYPES`) is 14 clause types common to
commercial contracts — termination, auto-renewal, payment terms, limitation
of liability, indemnification, confidentiality, IP ownership, non-compete,
governing law, warranties, force majeure, dispute resolution, assignment,
data protection. It's a closed list on purpose: that's what makes "missing
clauses" a stable signal instead of an artifact of how one run happened to
phrase things.

With an OpenAI key, each clause found gets a title, the source excerpt, a
plain-English summary, and a risk flag (`standard` / `attention` /
`high_risk` — e.g. uncapped liability or a narrow auto-renewal opt-out window
read as `high_risk`/`attention`). Without a key, a keyword pass over the
chunks still finds candidate clauses (`risk_level: "unreviewed"`, no
summarisation) — worse, not broken, same as search. Either way the response
says which mode ran (`mode: "answered" | "keyword_fallback"`).

Results are cached on `Document.contract_analysis_json` so reopening a
contract doesn't re-spend a model call; `POST .../contract-analysis?refresh=true`
forces a redo.

```
POST /api/documents/{id}/contract-analysis[?refresh=true]   -> run (or reuse cached) analysis
GET  /api/documents/{id}/contract-analysis                  -> fetch the cached analysis, 404 if none yet
```

## Files

| File | Job |
| --- | --- |
| `document_models.py` | `Document`, `DocumentChunk` tables |
| `document_store.py` | Extraction (PDF/DOCX/text, with OCR fallback), chunking, embedding, cosine search, RAG answer |
| `contract_analysis.py` | Contract-specific clause extraction + missing-clause detection |
| `document_schemas.py` | Wire shapes |
| `routers/documents.py` | Upload / list / update / delete / ask / contract-analysis |
| `frontend/app/(app)/knowledge-base/` | Upload UI, ask box with cited sources, contract analysis panel |

## What changed elsewhere

- `voice_intent.INTENT_CATALOG` — `ask_documents` (read-only).
- `voice_permissions.INTENT_PERMISSIONS` — mapped to the existing
  `voice.read` permission; no new permission needed.
- `voice_actions.py` — `action_ask_documents`, registered as `AUTO_EXECUTE` /
  `READ_ONLY_INTENTS` (it writes nothing, so it never waits for a tap).
- `main.py` — one router include, one model import.
- `requirements.txt` — `pypdf` (PDF text extraction), `python-docx` (DOCX),
  `pymupdf` + `pytesseract` + `pillow` (OCR fallback for scanned PDFs).

## Known limits, honestly

- **OCR needs a system binary, not just pip packages.** `tesseract-ocr` has
  to be installed on the host; see "Scanned PDFs" above. Image quality still
  matters — a low-resolution or skewed scan will OCR worse than it would in
  a dedicated document-scanning pipeline.
- **Contract analysis reads chunk text, not the original layout.** Tables,
  multi-column layouts, and anything conveyed by formatting rather than
  words can get flattened or reordered during extraction, same limitation
  `ask_documents` already has — clause extraction inherits it rather than
  fixing it.
- **Synchronous for small files.** Anything under ~200,000 characters
  (roughly 40–50 pages) is chunked and embedded inline, before the upload
  response returns. Bigger files fall back to a background task, same shape
  as the meeting pipeline, with `status` on the row as the progress
  indicator. Contract analysis itself always runs inline (bounded to the
  first ~100,000 characters of a document; longer contracts are still
  analyzed, just truncated, and the response says so via `truncated: true`).
- **Per-company, not per-document permissions.** Every document is visible to
  everyone at the company who can read business data (`voice.read` /
  logged-in access to `/knowledge-base`). There's no per-document ACL — add
  one if some uploads need to be restricted to certain roles.
