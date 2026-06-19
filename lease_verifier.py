"""
Z3-based verifier for residential lease terms.

Doctrine: Claude (or a human) fills in the JSON schema from the lease text.
This module encodes the schema as Z3 SMT constraints and reports UNSAT cores
as named conflicting clause pairs. The deterministic logic decides.

Three checks:
  1. Late fee cap — percentage-based fee cannot exceed stated cap
  2. Notice vs. term — required notice days cannot exceed total lease term
  3. Security deposit cap — deposit cannot exceed stated maximum (e.g. 2x rent)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from z3 import Bool, Int, Real, Solver, unsat


def _safe_name(clause_name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", clause_name).strip("_")
    return clean if clean else "clause"


@dataclass
class Conflict:
    clauses: list[str]
    explanation: str


@dataclass
class VerificationResult:
    status: str  # "PASS" or "FAIL"
    conflicts: list[Conflict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "conflicts": [
                {"clauses": c.clauses, "explanation": c.explanation}
                for c in self.conflicts
            ],
        }


class LeaseVerifier:
    """
    Encodes extracted lease clause terms as Z3 constraints and checks for UNSAT.
    Each check corresponds to one potential contradiction in the lease.
    """

    def verify(self, lease_schema: dict) -> VerificationResult:
        props = lease_schema.get("property", {})
        clauses = lease_schema.get("clauses", {})
        conflicts: list[Conflict] = []

        r = self._check_late_fee_cap(props, clauses)
        if r:
            conflicts.append(r)

        r = self._check_notice_vs_term(props, clauses)
        if r:
            conflicts.append(r)

        r = self._check_security_deposit_cap(props, clauses)
        if r:
            conflicts.append(r)

        return VerificationResult(
            status="FAIL" if conflicts else "PASS",
            conflicts=conflicts,
        )

    # ------------------------------------------------------------------
    # Check 1: Late fee cap
    #
    # Let f = late fee amount (Real).
    #
    #   Percentage sub-clause → f >= monthly_rent * pct / 100
    #   Cap sub-clause        → f <= cap_usd
    #
    # If monthly_rent * pct / 100 > cap_usd, UNSAT.
    # ------------------------------------------------------------------

    def _check_late_fee_cap(self, props: dict, clauses: dict) -> Optional[Conflict]:
        lf = clauses.get("late_fee") or {}
        monthly_rent = lf.get("monthly_rent_usd") or props.get("monthly_rent_usd")
        pct = lf.get("fee_pct_of_monthly_rent")
        cap = lf.get("fee_cap_usd")

        if None in (monthly_rent, pct, cap):
            return None

        computed_fee = float(monthly_rent) * float(pct) / 100.0
        cap_val = float(cap)

        clause_name = lf.get("clause_name", "Late Fee")
        pct_name = f"{clause_name} — percentage sub-clause"
        cap_name = f"{clause_name} — cap sub-clause"

        s = Solver()
        f = Real("late_fee_amount")
        pct_bool = Bool(_safe_name(pct_name))
        cap_bool = Bool(_safe_name(cap_name))

        s.assert_and_track(f >= computed_fee, pct_bool)
        s.assert_and_track(f <= cap_val, cap_bool)

        if s.check() == unsat:
            name_map = {_safe_name(pct_name): pct_name, _safe_name(cap_name): cap_name}
            conflicting = [name_map.get(str(item), str(item)) for item in s.unsat_core()]
            shortfall = computed_fee - cap_val
            return Conflict(
                clauses=conflicting,
                explanation=(
                    f'The "{clause_name}" clause sets a fee of {pct}% of monthly rent '
                    f"(${computed_fee:,.0f} on ${float(monthly_rent):,.0f}/month) "
                    f"but also caps late fees at ${cap_val:,.0f}. "
                    f"The computed fee (${computed_fee:,.0f}) exceeds the stated cap (${cap_val:,.0f}) "
                    f"by ${shortfall:,.0f} — both sub-clauses cannot be satisfied simultaneously."
                ),
            )
        return None

    # ------------------------------------------------------------------
    # Check 2: Notice period vs. lease term
    #
    # Let n = notice days, t = lease term days.
    #
    #   Notice clause → n >= required_notice_days
    #   Term clause   → t == lease_term_days
    #   Feasibility   → n <= t   (can't give notice before lease starts)
    #
    # If required_notice_days > lease_term_days, UNSAT.
    # ------------------------------------------------------------------

    def _check_notice_vs_term(self, props: dict, clauses: dict) -> Optional[Conflict]:
        vn = clauses.get("vacate_notice") or {}
        notice_days = vn.get("required_notice_days")
        lease_term_days = props.get("lease_term_days")

        if None in (notice_days, lease_term_days):
            return None

        notice_days = int(notice_days)
        lease_term_days = int(lease_term_days)
        notice_name = vn.get("clause_name", "Notice to Vacate")
        term_name = "Lease Term"

        s = Solver()
        n = Int("notice_days")
        t = Int("lease_term_days_var")
        notice_bool = Bool(_safe_name(notice_name))
        term_bool = Bool(_safe_name(term_name))
        feasibility_bool = Bool("notice_fits_in_term")

        s.assert_and_track(n >= notice_days, notice_bool)
        s.assert_and_track(t == lease_term_days, term_bool)
        s.assert_and_track(n <= t, feasibility_bool)

        if s.check() == unsat:
            name_map = {
                _safe_name(notice_name): notice_name,
                _safe_name(term_name): term_name,
            }
            conflicting = [name_map.get(str(item), str(item)) for item in s.unsat_core()]
            return Conflict(
                clauses=conflicting,
                explanation=(
                    f'The "{notice_name}" clause requires {notice_days} days of advance notice '
                    f"before vacating, but the lease term is only {lease_term_days} days. "
                    f"The tenant would need to give notice before the lease even begins — "
                    f"a logical impossibility. One of these terms must be incorrect."
                ),
            )
        return None

    # ------------------------------------------------------------------
    # Check 3: Security deposit vs. stated maximum
    #
    # Let d = deposit amount (Real).
    #
    #   Deposit clause → d >= deposit_amount_usd
    #   Cap clause     → d <= max_deposit_months * monthly_rent
    #
    # If deposit_amount > max_months * monthly_rent, UNSAT.
    # ------------------------------------------------------------------

    def _check_security_deposit_cap(self, props: dict, clauses: dict) -> Optional[Conflict]:
        sd = clauses.get("security_deposit") or {}
        monthly_rent = sd.get("monthly_rent_usd") or props.get("monthly_rent_usd")
        deposit = sd.get("deposit_amount_usd")
        max_months = sd.get("max_deposit_months")

        if None in (monthly_rent, deposit, max_months):
            return None

        deposit_val = float(deposit)
        cap_val = float(monthly_rent) * float(max_months)

        clause_name = sd.get("clause_name", "Security Deposit")
        deposit_name = f"{clause_name} — stated amount"
        cap_name = f"{clause_name} — stated maximum"

        s = Solver()
        d = Real("deposit_amount")
        dep_bool = Bool(_safe_name(deposit_name))
        cap_bool = Bool(_safe_name(cap_name))

        s.assert_and_track(d >= deposit_val, dep_bool)
        s.assert_and_track(d <= cap_val, cap_bool)

        if s.check() == unsat:
            name_map = {_safe_name(deposit_name): deposit_name, _safe_name(cap_name): cap_name}
            conflicting = [name_map.get(str(item), str(item)) for item in s.unsat_core()]
            excess = deposit_val - cap_val
            return Conflict(
                clauses=conflicting,
                explanation=(
                    f'The "{clause_name}" clause sets a deposit of ${deposit_val:,.0f} '
                    f"but also states the maximum is {max_months} month(s) of rent "
                    f"(${cap_val:,.0f} on ${float(monthly_rent):,.0f}/month). "
                    f"The stated deposit (${deposit_val:,.0f}) exceeds the stated maximum "
                    f"(${cap_val:,.0f}) by ${excess:,.0f}."
                ),
            )
        return None
