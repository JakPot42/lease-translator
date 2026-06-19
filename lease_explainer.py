"""
Claude-powered plain-English lease explainer.

Given the confirmed lease schema and Z3 verification result, Claude writes
a plain-language explanation of each clause and any contradictions found.
Doctrine: Z3 finds the contradictions; Claude explains them in plain language.
"""

import json

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE

_EXPLAIN_PROMPT = """You are a plain-language lease translator helping a tenant without legal expertise.

LEASE TERMS (extracted):
{schema_json}

Z3 VERIFICATION RESULT:
{z3_json}

Generate a JSON response with this exact structure:
{{
  "summary": "One sentence stating the overall result (contradictions found or not).",
  "clause_explanations": [
    {{"clause": "clause name", "plain_english": "1-2 sentence explanation a non-lawyer would understand"}}
  ],
  "contradiction_explanations": [
    {{"clauses": ["clause1", "clause2"], "plain_english": "What the contradiction means in practice for the tenant"}}
  ],
  "disclaimer": "This analysis checks for logical contradictions in the extracted terms. It does not check whether terms are legal, fair, or enforceable in your jurisdiction. Consult a tenant rights organization or attorney for legal advice."
}}

Rules:
- Use simple, everyday language.
- For contradictions: explain what BOTH clauses say, why they conflict, and the practical impact on the tenant.
- Never say a term is "illegal" or "invalid" — only that it conflicts with another term.
- If no contradictions: set contradiction_explanations to an empty array.
- Include one entry in clause_explanations for each clause found in the schema (skip null fields).
- Return ONLY the JSON — no markdown, no commentary."""


_DEMO_EXPLANATIONS: dict[str, dict] = {
    "PASS": {
        "summary": "No logical contradictions were found in this lease.",
        "clause_explanations": [
            {
                "clause": "Monthly Rent",
                "plain_english": "Your rent is $1,500 per month for a 12-month lease.",
            },
            {
                "clause": "Late Fee",
                "plain_english": "If you pay rent late, you'll be charged 5% of your monthly rent ($75). This fee cannot exceed $100 — and in this case, $75 is under that cap, so the fee and cap are consistent.",
            },
            {
                "clause": "Notice to Vacate",
                "plain_english": "You must tell your landlord at least 30 days before you plan to leave. Since the lease is 12 months long, this is entirely feasible.",
            },
            {
                "clause": "Security Deposit",
                "plain_english": "You pay $1,500 at signing. The lease states the maximum deposit is one month's rent — which equals $1,500, so the amount matches the stated cap.",
            },
        ],
        "contradiction_explanations": [],
        "disclaimer": "This analysis checks for logical contradictions in the extracted terms. It does not check whether terms are legal, fair, or enforceable in your jurisdiction. Consult a tenant rights organization or attorney for legal advice.",
    },
    "FAIL_FEE": {
        "summary": "One logical contradiction was found: the late fee clause contains two sub-clauses that cannot both be true.",
        "clause_explanations": [
            {
                "clause": "Monthly Rent",
                "plain_english": "Your rent is $2,000 per month for a 12-month lease.",
            },
            {
                "clause": "Late Fee",
                "plain_english": "The late fee clause has a problem: it says fees are 10% of rent (which would be $200) but also says fees can't exceed $100. Both parts can't be true at the same time.",
            },
            {
                "clause": "Notice to Vacate",
                "plain_english": "You must give your landlord 30 days written notice before moving out.",
            },
        ],
        "contradiction_explanations": [
            {
                "clauses": [
                    "Late Fee — percentage sub-clause",
                    "Late Fee — cap sub-clause",
                ],
                "plain_english": "The lease says your late fee is 10% of your $2,000 monthly rent — that's $200. But the same clause says late fees can't exceed $100. It's mathematically impossible to charge you $200 and also cap the fee at $100. If you were ever charged a late fee, there would be no clear answer about the correct amount. A tenant's rights organization could argue the lower figure ($100) should apply, but this ambiguity shouldn't be in your lease at all.",
            }
        ],
        "disclaimer": "This analysis checks for logical contradictions in the extracted terms. It does not check whether terms are legal, fair, or enforceable in your jurisdiction. Consult a tenant rights organization or attorney for legal advice.",
    },
    "FAIL_NOTICE": {
        "summary": "One logical contradiction was found: the required notice period is longer than the entire lease.",
        "clause_explanations": [
            {
                "clause": "Monthly Rent",
                "plain_english": "Your rent is $1,200 per month.",
            },
            {
                "clause": "Late Fee",
                "plain_english": "If you pay rent late, you'll be charged 3% of your monthly rent ($36).",
            },
            {
                "clause": "Notice to Vacate",
                "plain_english": "The lease says you must give 90 days notice before leaving — but the total lease is only 60 days. This is impossible.",
            },
            {
                "clause": "Security Deposit",
                "plain_english": "You pay a $1,200 security deposit at signing.",
            },
        ],
        "contradiction_explanations": [
            {
                "clauses": ["Notice to Vacate", "Lease Term"],
                "plain_english": "The lease requires 90 days advance notice before you vacate, but the entire lease is only 60 days long. You would need to give notice 90 days before the end — meaning you'd have to give notice before the lease even starts. This is logically impossible. One of these two terms must be a drafting error. Ask your landlord to correct this before signing.",
            }
        ],
        "disclaimer": "This analysis checks for logical contradictions in the extracted terms. It does not check whether terms are legal, fair, or enforceable in your jurisdiction. Consult a tenant rights organization or attorney for legal advice.",
    },
}


class ExplainError(Exception):
    pass


def explain_lease(lease_schema: dict, z3_result: dict) -> dict:
    """
    Generate plain-English explanations for lease clauses and any contradictions.
    Returns the explanation dict.
    """
    if DEMO_MODE:
        status = z3_result.get("status", "PASS")
        conflicts = z3_result.get("conflicts", [])
        if status == "PASS":
            return _DEMO_EXPLANATIONS["PASS"]
        # Pick the right demo explanation by conflict content
        if conflicts:
            explanation_text = conflicts[0].get("explanation", "")
            if "notice" in explanation_text.lower() or "Notice" in explanation_text:
                return _DEMO_EXPLANATIONS["FAIL_NOTICE"]
        return _DEMO_EXPLANATIONS["FAIL_FEE"]

    if not ANTHROPIC_API_KEY:
        return _fallback_explanation(z3_result)

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1500,
            messages=[
                {
                    "role": "user",
                    "content": _EXPLAIN_PROMPT.format(
                        schema_json=json.dumps(lease_schema, indent=2),
                        z3_json=json.dumps(z3_result, indent=2),
                    ),
                }
            ],
        )
        raw = msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExplainError(f"Claude returned invalid JSON: {e}") from e
    except Exception as exc:
        raise ExplainError(f"Claude API error: {exc}") from exc


def _fallback_explanation(z3_result: dict) -> dict:
    """Used when API key missing and not in DEMO_MODE."""
    status = z3_result.get("status", "PASS")
    conflicts = z3_result.get("conflicts", [])
    return {
        "summary": (
            "No logical contradictions found."
            if status == "PASS"
            else f"{len(conflicts)} logical contradiction(s) found."
        ),
        "clause_explanations": [],
        "contradiction_explanations": [
            {"clauses": c["clauses"], "plain_english": c["explanation"]}
            for c in conflicts
        ],
        "disclaimer": "Plain-language explanation requires an API key. The Z3 technical details are shown above.",
    }
