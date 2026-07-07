"""
fv_core.py -- shared Z3 verification scaffolding for the Formal Verification
Toolkit (Phase 6, Cluster 4).

Canonicalizes a pattern independently reimplemented three times across
z3_contract, guarden_fv, and lease_translator, each with real drift:
`_safe_name()` had two different implementations (z3_contract and
lease_translator stripped trailing underscores and fell back to "clause"
when the result was empty; guarden_fv's was a bare regex substitution with
neither), `VerificationResult.to_dict()` existed in only two of the three
copies, and guarden_fv's own unsat-core reporting was a hardcoded shortcut
-- it returned every tracked constraint's name as "the conflict" whenever
the check came back unsat, without ever calling `unsat_core()`. That
shortcut happened to produce correct output for every check that existed
(each tracked exactly 2 mutually-dependent constraints, where a 2-constraint
UNSAT can't drop either side without becoming SAT again) but was never
verified in code -- fixed standalone in guarden_fv's own repo first (see
its own commit history), and reproduced here correctly by construction so
every future check gets that correctness automatically rather than
re-deriving it.

Every check across all three source projects follows the same shape: build
a Solver, assert_and_track() each fact behind a uniquely-named boolean,
check(), and on unsat map the real unsat_core() literals back to
human-readable names. TrackedSolver is that shape, extracted once.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from z3 import Bool, Solver, unsat


def safe_name(name: str) -> str:
    """Convert an arbitrary clause/rule name into a valid Z3 symbol name.

    Strips to ASCII word characters, trims leading/trailing underscores, and
    falls back to "clause" if that leaves nothing -- matches z3_contract's
    and lease_translator's original behavior (guarden_fv's own copy lacked
    the strip/fallback; reconciled here as the one canonical version).
    """
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", name).strip("_")
    return clean if clean else "clause"


@dataclass
class Conflict:
    """One named logical contradiction.

    `names` lists the human-readable clause/rule names Z3's real unsat core
    says are actually necessary for the contradiction -- never every
    constraint that happened to be tracked in the same solver.
    """
    names: list[str]
    explanation: str


@dataclass
class VerificationResult:
    status: str  # "PASS" or "FAIL"
    conflicts: list[Conflict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "conflicts": [
                {"names": c.names, "explanation": c.explanation}
                for c in self.conflicts
            ],
        }


class TrackedSolver:
    """A Z3 Solver wrapper that tracks facts under human-readable names and
    resolves UNSAT results through the solver's real `unsat_core()` -- never
    a hardcoded guess at which tracked facts are actually in conflict.

    Usage:
        s = TrackedSolver()
        s.track(alt <= max_altitude_m, max_rule_name)
        s.track(alt >= min_altitude_m, min_rule_name)
        names = s.check_conflict()
        if names is not None:
            ...  # names is the real minimal conflicting subset, by name
    """

    def __init__(self) -> None:
        self._solver = Solver()
        self._name_map: dict[str, str] = {}

    def track(self, constraint, name: str) -> None:
        """Assert `constraint`, tracked under `name` for unsat-core reporting."""
        symbol = safe_name(name)
        self._name_map[symbol] = name
        self._solver.assert_and_track(constraint, Bool(symbol))

    def check_conflict(self) -> list[str] | None:
        """Run the solver.

        Returns None if the tracked constraints are satisfiable, or the list
        of human-readable names Z3's real unsat_core() says are necessary
        for the contradiction if not -- never a hardcoded list of everything
        that was tracked.
        """
        if self._solver.check() != unsat:
            return None
        return [
            self._name_map.get(str(item), str(item))
            for item in self._solver.unsat_core()
        ]
