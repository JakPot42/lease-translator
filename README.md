# Lease Translator

**Plain-English Lease Contradiction Detector — powered by Z3 formal verification and Claude.**

Paste a residential lease. Claude extracts the key terms (late fees, notice periods, security deposit). Z3 — Microsoft's SMT solver — checks for *logical contradictions* that can't both be true at the same time. Claude explains any contradiction in plain language.

**Live demo:** https://lease-translator.onrender.com

---

## What it detects

Three categories of logical contradiction:

| Check | What it catches | Example |
|---|---|---|
| **Late fee cap** | Fee percentage × rent > stated cap | 10% of $2,000 = $200, but cap is $100 |
| **Notice vs. term** | Required notice > total lease term | 90-day notice on a 60-day lease |
| **Security deposit cap** | Deposit amount > stated monthly-rent multiple | $4,000 deposit, cap stated as 2× rent ($3,000) |

A *logical contradiction* is different from an unfavorable term. A contradiction means two clauses in the same lease cannot both be satisfied — one must be wrong. That's exactly what a tenant without a lawyer would never catch.

## Architecture

```
Lease text
    │
    ▼ Claude (extraction)
Structured JSON schema
    │
    ▼ Human confirmation (SEAD 3 pattern)
Confirmed schema
    │
    ▼ Z3 (SMT solver — formal verification)
PASS / FAIL + named conflicting clauses
    │
    ▼ Claude (plain-language explanation)
Result page
```

**Doctrine: Claude extracts — Z3 decides.** Claude is confined to natural language work (extracting terms, explaining contradictions). The contradiction finding is purely deterministic — Z3 either returns SAT or UNSAT, and the tool reports which.

This is the same `assert_and_track` / UNSAT core pattern from [z3-contract](https://github.com/JakPot42/z3-contract), applied to residential leases instead of term sheets.

## Tech stack

- **FastAPI** + Jinja2 for the web app
- **z3-solver** for formal contradiction checking
- **Claude Haiku** (`claude-haiku-4-5-20251001`) for extraction and plain-language explanation
- **SQLAlchemy** + SQLite for session state
- **Render** for deployment

## Running locally

```bash
git clone https://github.com/JakPot42/lease-translator
cd lease-translator
pip install -r requirements.txt

# DEMO_MODE=True uses pre-baked demo data (no API key needed)
DEMO_MODE=True uvicorn main:app --reload

# Full mode (Claude calls)
DEMO_MODE=False ANTHROPIC_API_KEY=sk-ant-... uvicorn main:app --reload
```

Open http://localhost:8000.

## Running tests

```bash
pytest tests/ -v
```

31 tests covering all three Z3 checks (SAT/UNSAT cases, boundary conditions, null/missing fields, multi-conflict detection).

## Demo leases

Three pre-seeded examples:

| Demo | Scenario | Result |
|---|---|---|
| Demo 1 | 45 Harbor View Drive — all clauses consistent | **PASS** |
| Demo 2 | 210 Brook Street — late fee 10% = $200, cap $100 | **FAIL** (fee conflict) |
| Demo 3 | 88 Elmwood Avenue — 90-day notice on 60-day lease | **FAIL** (notice conflict) |

## Honest limitations

- **Three checks only.** Lease contradictions are infinite in variety. This tool checks three common arithmetic/logical types. Other contradiction types are not detected.
- **Extraction quality matters.** If Claude misses a term (or your lease states it ambiguously), that check is skipped. The confirmation screen is the human checkpoint.
- **Not legal advice.** This tool detects internal logical contradictions. It does not check whether terms are fair, legal, or enforceable in your jurisdiction.

---

*Part of a defense and legal-tech portfolio. This is project 26.*
