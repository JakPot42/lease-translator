"""
Tests for LeaseVerifier — the Z3 contradiction engine.

Three check categories, each with SAT/UNSAT cases plus edge cases.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lease_verifier import LeaseVerifier, VerificationResult


def _schema(*, monthly_rent=None, lease_term_days=None,
            fee_pct=None, fee_cap=None,
            notice_days=None,
            deposit_amount=None, max_deposit_months=None) -> dict:
    return {
        "property": {
            "monthly_rent_usd": monthly_rent,
            "lease_term_days": lease_term_days,
        },
        "clauses": {
            "late_fee": {
                "clause_name": "Late Fee",
                "fee_pct_of_monthly_rent": fee_pct,
                "fee_cap_usd": fee_cap,
            },
            "vacate_notice": {
                "clause_name": "Notice to Vacate",
                "required_notice_days": notice_days,
            },
            "security_deposit": {
                "clause_name": "Security Deposit",
                "deposit_amount_usd": deposit_amount,
                "max_deposit_months": max_deposit_months,
            },
        },
    }


# ─── Late fee cap check ────────────────────────────────────────────────────

def test_late_fee_pass_fee_below_cap():
    # 5% of $1500 = $75 < $100 cap
    s = _schema(monthly_rent=1500, fee_pct=5.0, fee_cap=100.0)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_late_fee_pass_fee_equals_cap():
    # 10% of $1000 = $100 == $100 cap (exactly at boundary — SAT)
    s = _schema(monthly_rent=1000, fee_pct=10.0, fee_cap=100.0)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_late_fee_fail_fee_exceeds_cap():
    # 10% of $2000 = $200 > $100 cap
    s = _schema(monthly_rent=2000, fee_pct=10.0, fee_cap=100.0)
    result = LeaseVerifier().verify(s)
    assert result.status == "FAIL"
    assert len(result.conflicts) == 1


def test_late_fee_fail_names_correct_clauses():
    s = _schema(monthly_rent=2000, fee_pct=10.0, fee_cap=100.0)
    conflict = LeaseVerifier().verify(s).conflicts[0]
    assert any("Late Fee" in c for c in conflict.clauses)
    assert len(conflict.clauses) == 2


def test_late_fee_fail_explanation_cites_dollar_amounts():
    s = _schema(monthly_rent=2000, fee_pct=10.0, fee_cap=100.0)
    conflict = LeaseVerifier().verify(s).conflicts[0]
    assert "$" in conflict.explanation


def test_late_fee_fail_explanation_cites_shortfall():
    # 10% of $2000 = $200, cap = $50, shortfall = $150
    s = _schema(monthly_rent=2000, fee_pct=10.0, fee_cap=50.0)
    conflict = LeaseVerifier().verify(s).conflicts[0]
    assert "150" in conflict.explanation


def test_late_fee_skip_when_pct_missing():
    s = _schema(monthly_rent=2000, fee_cap=100.0)  # no fee_pct
    assert LeaseVerifier().verify(s).status == "PASS"


def test_late_fee_skip_when_cap_missing():
    s = _schema(monthly_rent=2000, fee_pct=10.0)  # no cap
    assert LeaseVerifier().verify(s).status == "PASS"


def test_late_fee_skip_when_rent_missing():
    s = _schema(fee_pct=10.0, fee_cap=100.0)  # no monthly rent
    assert LeaseVerifier().verify(s).status == "PASS"


# ─── Notice vs. term check ─────────────────────────────────────────────────

def test_notice_pass_fits_in_term():
    # 30-day notice on 365-day lease — fine
    s = _schema(monthly_rent=1500, lease_term_days=365, notice_days=30)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_notice_pass_notice_equals_term():
    # 60-day notice on 60-day lease — exactly feasible (notice from day 0)
    s = _schema(monthly_rent=1500, lease_term_days=60, notice_days=60)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_notice_fail_notice_exceeds_term():
    # 90-day notice on 60-day lease
    s = _schema(monthly_rent=1200, lease_term_days=60, notice_days=90)
    result = LeaseVerifier().verify(s)
    assert result.status == "FAIL"
    assert len(result.conflicts) == 1


def test_notice_fail_names_both_clauses():
    s = _schema(monthly_rent=1200, lease_term_days=60, notice_days=90)
    conflict = LeaseVerifier().verify(s).conflicts[0]
    assert any("Notice" in c or "notice" in c for c in conflict.clauses)


def test_notice_fail_explanation_mentions_days():
    s = _schema(monthly_rent=1200, lease_term_days=60, notice_days=90)
    conflict = LeaseVerifier().verify(s).conflicts[0]
    assert "90" in conflict.explanation and "60" in conflict.explanation


def test_notice_skip_when_term_missing():
    s = _schema(monthly_rent=1200, notice_days=90)  # no lease_term_days
    assert LeaseVerifier().verify(s).status == "PASS"


def test_notice_skip_when_notice_missing():
    s = _schema(monthly_rent=1200, lease_term_days=60)  # no notice_days
    assert LeaseVerifier().verify(s).status == "PASS"


# ─── Security deposit cap check ────────────────────────────────────────────

def test_deposit_pass_within_cap():
    # $1500 deposit, max 1x $1500/month = $1500 (equal — SAT)
    s = _schema(monthly_rent=1500, deposit_amount=1500, max_deposit_months=1.0)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_deposit_pass_below_cap():
    # $1500 deposit, max 2x $1500/month = $3000 cap (well within)
    s = _schema(monthly_rent=1500, deposit_amount=1500, max_deposit_months=2.0)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_deposit_fail_exceeds_cap():
    # $4000 deposit, max 2x $1500/month = $3000 cap
    s = _schema(monthly_rent=1500, deposit_amount=4000, max_deposit_months=2.0)
    result = LeaseVerifier().verify(s)
    assert result.status == "FAIL"
    assert len(result.conflicts) == 1


def test_deposit_fail_names_both_clauses():
    s = _schema(monthly_rent=1500, deposit_amount=4000, max_deposit_months=2.0)
    conflict = LeaseVerifier().verify(s).conflicts[0]
    assert any("Security Deposit" in c for c in conflict.clauses)
    assert len(conflict.clauses) == 2


def test_deposit_fail_explanation_cites_dollar_amounts():
    s = _schema(monthly_rent=1500, deposit_amount=4000, max_deposit_months=2.0)
    conflict = LeaseVerifier().verify(s).conflicts[0]
    assert "$" in conflict.explanation


def test_deposit_skip_when_amount_missing():
    s = _schema(monthly_rent=1500, max_deposit_months=2.0)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_deposit_skip_when_cap_missing():
    s = _schema(monthly_rent=1500, deposit_amount=4000)
    assert LeaseVerifier().verify(s).status == "PASS"


def test_deposit_skip_when_rent_missing():
    s = _schema(deposit_amount=4000, max_deposit_months=2.0)
    assert LeaseVerifier().verify(s).status == "PASS"


# ─── Multi-conflict and edge cases ─────────────────────────────────────────

def test_multiple_conflicts_detected():
    # Both late fee AND notice conflict in one lease
    s = _schema(
        monthly_rent=2000, lease_term_days=60,
        fee_pct=10.0, fee_cap=100.0,
        notice_days=90,
    )
    result = LeaseVerifier().verify(s)
    assert result.status == "FAIL"
    assert len(result.conflicts) == 2


def test_empty_schema_passes():
    result = LeaseVerifier().verify({})
    assert result.status == "PASS"
    assert result.conflicts == []


def test_empty_clauses_passes():
    result = LeaseVerifier().verify({"property": {}, "clauses": {}})
    assert result.status == "PASS"


def test_to_dict_format():
    s = _schema(monthly_rent=2000, fee_pct=10.0, fee_cap=100.0)
    result = LeaseVerifier().verify(s)
    d = result.to_dict()
    assert "status" in d
    assert "conflicts" in d
    assert d["status"] == "FAIL"
    assert d["conflicts"][0]["clauses"]
    assert d["conflicts"][0]["explanation"]


def test_demo1_clean_passes():
    # Demo 1 from seed data: 5% of $1500 = $75 < $100 cap, 30-day notice on 365-day term, $1500 <= 1x$1500
    s = {
        "property": {"monthly_rent_usd": 1500.0, "lease_term_days": 365},
        "clauses": {
            "late_fee": {"clause_name": "Late Fee", "fee_pct_of_monthly_rent": 5.0, "fee_cap_usd": 100.0},
            "vacate_notice": {"clause_name": "Notice to Vacate", "required_notice_days": 30},
            "security_deposit": {"clause_name": "Security Deposit", "deposit_amount_usd": 1500.0, "max_deposit_months": 1.0},
        },
    }
    assert LeaseVerifier().verify(s).status == "PASS"


def test_demo2_fee_conflict_fails():
    # Demo 2: 10% of $2000 = $200 > $100 cap
    s = {
        "property": {"monthly_rent_usd": 2000.0, "lease_term_days": 365},
        "clauses": {
            "late_fee": {"clause_name": "Late Fee", "fee_pct_of_monthly_rent": 10.0, "fee_cap_usd": 100.0},
            "vacate_notice": {"clause_name": "Notice to Vacate", "required_notice_days": 30},
            "security_deposit": {"clause_name": "Security Deposit", "deposit_amount_usd": None, "max_deposit_months": None},
        },
    }
    result = LeaseVerifier().verify(s)
    assert result.status == "FAIL"
    assert len(result.conflicts) == 1


def test_demo3_notice_conflict_fails():
    # Demo 3: 90-day notice on 60-day lease
    s = {
        "property": {"monthly_rent_usd": 1200.0, "lease_term_days": 60},
        "clauses": {
            "late_fee": {"clause_name": "Late Fee", "fee_pct_of_monthly_rent": 3.0, "fee_cap_usd": None},
            "vacate_notice": {"clause_name": "Notice to Vacate", "required_notice_days": 90},
            "security_deposit": {"clause_name": "Security Deposit", "deposit_amount_usd": 1200.0, "max_deposit_months": None},
        },
    }
    result = LeaseVerifier().verify(s)
    assert result.status == "FAIL"
    assert len(result.conflicts) == 1
