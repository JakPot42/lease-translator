"""
Claude-powered lease term extractor.

Doctrine: Claude extracts — Z3 decides.
The extractor pulls only explicitly stated numeric and boolean values from
the lease text. It never infers or calculates. Null means not found.
"""

import json

import anthropic

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE

_EXTRACTION_PROMPT = """You are a lease term extractor. Read the lease agreement below and extract specific numeric values into a JSON schema.

RULES:
1. Only extract values EXPLICITLY stated in the lease. Do not infer, calculate, or assume.
2. If a term is not mentioned, set it to null.
3. Return ONLY the JSON object — no commentary, no markdown.
4. monthly_rent_usd is monthly rent in USD.
5. lease_term_days is the total length of the lease in days (e.g. "12 months" = 365, "60 days" = 60).
6. fee_pct_of_monthly_rent is the late fee percentage (e.g. "10%" = 10.0).
7. fee_cap_usd is the maximum late fee in USD.
8. required_notice_days is advance notice required to vacate (e.g. "30 days" = 30).
9. deposit_amount_usd is the stated security deposit amount in USD.
10. max_deposit_months is the stated maximum deposit in months of rent (e.g. "two months' rent" = 2.0).

Extract into this exact schema:
{
  "property": {
    "address": "string or null",
    "monthly_rent_usd": number or null,
    "lease_term_days": number or null,
    "start_date": "YYYY-MM-DD or null"
  },
  "clauses": {
    "late_fee": {
      "clause_name": "Late Fee",
      "fee_pct_of_monthly_rent": number or null,
      "fee_cap_usd": number or null
    },
    "vacate_notice": {
      "clause_name": "Notice to Vacate",
      "required_notice_days": number or null
    },
    "security_deposit": {
      "clause_name": "Security Deposit",
      "deposit_amount_usd": number or null,
      "max_deposit_months": number or null
    }
  }
}

LEASE TEXT:
{lease_text}"""


_DEMO_SCHEMA = {
    "property": {
        "address": "210 Brook Street, Providence, RI 02906",
        "monthly_rent_usd": 2000.0,
        "lease_term_days": 365,
        "start_date": "2024-10-01",
    },
    "clauses": {
        "late_fee": {
            "clause_name": "Late Fee",
            "fee_pct_of_monthly_rent": 10.0,
            "fee_cap_usd": 100.0,
        },
        "vacate_notice": {
            "clause_name": "Notice to Vacate",
            "required_notice_days": 30,
        },
        "security_deposit": {
            "clause_name": "Security Deposit",
            "deposit_amount_usd": None,
            "max_deposit_months": None,
        },
    },
}


class ExtractionError(Exception):
    pass


def extract_lease_terms(raw_text: str) -> dict:
    """
    Extract structured lease terms from raw text.
    Returns the lease schema dict.
    Raises ExtractionError on failure.
    """
    if DEMO_MODE:
        return _DEMO_SCHEMA

    if not ANTHROPIC_API_KEY:
        raise ExtractionError("ANTHROPIC_API_KEY is not set. Set DEMO_MODE=True for demo use.")

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": _EXTRACTION_PROMPT.format(lease_text=raw_text[:8000]),
                }
            ],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ExtractionError(f"Claude returned invalid JSON: {e}") from e
    except Exception as exc:
        raise ExtractionError(f"Claude API error: {exc}") from exc
