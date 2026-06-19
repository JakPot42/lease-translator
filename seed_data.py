"""
Seed data: 3 demo lease analyses, pre-baked with Z3 results.

Demo 1 — Clean: all clauses consistent, PASS.
Demo 2 — Late Fee Conflict: 10% of $2,000 = $200 exceeds $100 cap, FAIL.
Demo 3 — Notice Conflict: 90-day notice on a 60-day lease, FAIL.
"""

import json
from sqlalchemy.orm import Session

from models import LeaseAnalysis

_DEMO_1_TEXT = """LEASE AGREEMENT

Property: 45 Harbor View Drive, Providence, RI 02906
Monthly Rent: $1,500
Lease Term: 12 months (365 days), beginning September 1, 2024

SECTION 3 — SECURITY DEPOSIT
A security deposit of $1,500 is due at signing. Security deposits shall not
exceed one month's rent.

SECTION 7 — NOTICE TO VACATE
Tenant must provide 30 days written notice prior to the end of the lease term.

SECTION 9 — LATE FEES
If rent is not received by the 5th of the month, a late fee of 5% of monthly
rent shall be charged. Late fees shall not exceed $100 per occurrence.
"""

_DEMO_1_SCHEMA = {
    "property": {
        "address": "45 Harbor View Drive, Providence, RI 02906",
        "monthly_rent_usd": 1500.0,
        "lease_term_days": 365,
        "start_date": "2024-09-01",
    },
    "clauses": {
        "late_fee": {
            "clause_name": "Late Fee",
            "fee_pct_of_monthly_rent": 5.0,
            "fee_cap_usd": 100.0,
        },
        "vacate_notice": {
            "clause_name": "Notice to Vacate",
            "required_notice_days": 30,
        },
        "security_deposit": {
            "clause_name": "Security Deposit",
            "deposit_amount_usd": 1500.0,
            "max_deposit_months": 1.0,
        },
    },
}

_DEMO_1_Z3 = {"status": "PASS", "conflicts": []}

_DEMO_1_PLAIN = {
    "summary": "No logical contradictions were found in this lease.",
    "clause_explanations": [
        {
            "clause": "Monthly Rent",
            "plain_english": "Your rent is $1,500 per month for a 12-month lease starting September 1, 2024.",
        },
        {
            "clause": "Late Fee",
            "plain_english": "If you pay late, you'll owe 5% of your monthly rent ($75). The lease caps late fees at $100 — and $75 is below that cap, so these two sub-clauses are consistent.",
        },
        {
            "clause": "Notice to Vacate",
            "plain_english": "You must give your landlord at least 30 days written notice before you plan to move out. On a 365-day lease, 30 days notice is entirely feasible.",
        },
        {
            "clause": "Security Deposit",
            "plain_english": "You pay a $1,500 security deposit at signing. The lease states the maximum deposit is one month's rent ($1,500) — your deposit matches this cap exactly.",
        },
    ],
    "contradiction_explanations": [],
    "disclaimer": "This analysis checks for logical contradictions in the extracted terms. It does not check whether terms are legal, fair, or enforceable in your jurisdiction. Consult a tenant rights organization or attorney for legal advice.",
}

_DEMO_2_TEXT = """LEASE AGREEMENT

Property: 210 Brook Street, Providence, RI 02906
Monthly Rent: $2,000
Lease Term: 12 months (365 days), beginning October 1, 2024

SECTION 7 — NOTICE TO VACATE
Tenant must provide 30 days written notice prior to the end of the lease term.

SECTION 9 — LATE FEES
If rent is not received by the 5th of the month, a late fee of 10% of monthly
rent shall be charged. Late fees shall not exceed $100 per occurrence.
"""

_DEMO_2_SCHEMA = {
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

_DEMO_2_Z3 = {
    "status": "FAIL",
    "conflicts": [
        {
            "clauses": [
                "Late Fee — percentage sub-clause",
                "Late Fee — cap sub-clause",
            ],
            "explanation": (
                'The "Late Fee" clause sets a fee of 10.0% of monthly rent '
                "($200 on $2,000/month) but also caps late fees at $100. "
                "The computed fee ($200) exceeds the stated cap ($100) "
                "by $100 — both sub-clauses cannot be satisfied simultaneously."
            ),
        }
    ],
}

_DEMO_2_PLAIN = {
    "summary": "One logical contradiction was found: the late fee clause contains two sub-clauses that cannot both be true.",
    "clause_explanations": [
        {
            "clause": "Monthly Rent",
            "plain_english": "Your rent is $2,000 per month for a 12-month lease.",
        },
        {
            "clause": "Late Fee",
            "plain_english": "This clause has a problem: it says your late fee is 10% of monthly rent (that's $200) but also says fees can never exceed $100. Both cannot be true.",
        },
        {
            "clause": "Notice to Vacate",
            "plain_english": "You must give your landlord 30 days written notice before moving out. This is consistent with a 365-day lease.",
        },
    ],
    "contradiction_explanations": [
        {
            "clauses": [
                "Late Fee — percentage sub-clause",
                "Late Fee — cap sub-clause",
            ],
            "plain_english": (
                "The lease says your late fee is 10% of your $2,000 monthly rent — that's $200. "
                "But the same clause says late fees cannot exceed $100. "
                "It is mathematically impossible to charge $200 and cap the fee at $100 simultaneously. "
                "If you were ever charged a late fee, there would be no clear answer about the correct amount. "
                "A tenant's rights advocate would likely argue the lower amount ($100) applies, "
                "but this ambiguity should not exist in your lease. Ask your landlord to correct this before signing."
            ),
        }
    ],
    "disclaimer": "This analysis checks for logical contradictions in the extracted terms. It does not check whether terms are legal, fair, or enforceable in your jurisdiction. Consult a tenant rights organization or attorney for legal advice.",
}

_DEMO_3_TEXT = """LEASE AGREEMENT

Property: 88 Elmwood Avenue, Providence, RI 02907
Monthly Rent: $1,200
Lease Term: 60 days, beginning July 1, 2024

SECTION 3 — SECURITY DEPOSIT
A security deposit of $1,200 is due at signing.

SECTION 7 — NOTICE TO VACATE
Tenant must provide 90 days written notice before vacating the property.

SECTION 9 — LATE FEES
If rent is not received by the 5th of the month, a late fee of 3% of monthly
rent shall be charged.
"""

_DEMO_3_SCHEMA = {
    "property": {
        "address": "88 Elmwood Avenue, Providence, RI 02907",
        "monthly_rent_usd": 1200.0,
        "lease_term_days": 60,
        "start_date": "2024-07-01",
    },
    "clauses": {
        "late_fee": {
            "clause_name": "Late Fee",
            "fee_pct_of_monthly_rent": 3.0,
            "fee_cap_usd": None,
        },
        "vacate_notice": {
            "clause_name": "Notice to Vacate",
            "required_notice_days": 90,
        },
        "security_deposit": {
            "clause_name": "Security Deposit",
            "deposit_amount_usd": 1200.0,
            "max_deposit_months": None,
        },
    },
}

_DEMO_3_Z3 = {
    "status": "FAIL",
    "conflicts": [
        {
            "clauses": ["Notice to Vacate", "Lease Term"],
            "explanation": (
                'The "Notice to Vacate" clause requires 90 days of advance notice '
                "before vacating, but the lease term is only 60 days. "
                "The tenant would need to give notice before the lease even begins — "
                "a logical impossibility. One of these terms must be incorrect."
            ),
        }
    ],
}

_DEMO_3_PLAIN = {
    "summary": "One logical contradiction was found: the required notice period is longer than the entire lease.",
    "clause_explanations": [
        {
            "clause": "Monthly Rent",
            "plain_english": "Your rent is $1,200 per month for a 60-day lease.",
        },
        {
            "clause": "Late Fee",
            "plain_english": "If you pay late, you'll owe 3% of your monthly rent ($36). No cap is stated.",
        },
        {
            "clause": "Notice to Vacate",
            "plain_english": "The lease requires 90 days advance notice before you move out — but the lease itself is only 60 days long. This is impossible to comply with.",
        },
        {
            "clause": "Security Deposit",
            "plain_english": "You pay a $1,200 security deposit at signing (no stated maximum).",
        },
    ],
    "contradiction_explanations": [
        {
            "clauses": ["Notice to Vacate", "Lease Term"],
            "plain_english": (
                "The lease requires you to give 90 days notice before moving out, "
                "but the entire lease term is only 60 days. "
                "You would need to give notice 90 days before the end — "
                "meaning you would have to give notice 30 days BEFORE the lease even starts. "
                "This is a logical impossibility — one of these two terms must be a drafting error. "
                "Do not sign this lease without getting this corrected in writing first."
            ),
        }
    ],
    "disclaimer": "This analysis checks for logical contradictions in the extracted terms. It does not check whether terms are legal, fair, or enforceable in your jurisdiction. Consult a tenant rights organization or attorney for legal advice.",
}

_DEMOS = [
    (_DEMO_1_TEXT, _DEMO_1_SCHEMA, _DEMO_1_Z3, _DEMO_1_PLAIN),
    (_DEMO_2_TEXT, _DEMO_2_SCHEMA, _DEMO_2_Z3, _DEMO_2_PLAIN),
    (_DEMO_3_TEXT, _DEMO_3_SCHEMA, _DEMO_3_Z3, _DEMO_3_PLAIN),
]


def load_seed_data(db: Session) -> None:
    if db.query(LeaseAnalysis).count() > 0:
        return
    for raw, schema, z3, plain in _DEMOS:
        analysis = LeaseAnalysis(
            raw_text=raw,
            extracted_json=json.dumps(schema),
            confirmed_json=json.dumps(schema),
            z3_result_json=json.dumps(z3),
            plain_english_json=json.dumps(plain),
        )
        db.add(analysis)
    db.commit()
