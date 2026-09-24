"""Point mort (âge de rentabilité) du report des prestations RRQ et SV.

Compare, en dollars constants, le cumul des prestations reçues selon deux
âges de début; l'âge de rentabilité est celui à partir duquel le report a
rapporté plus que le début hâtif.
"""
from dataclasses import dataclass

from planner.core.benefits.oas import OAS
from planner.core.benefits.rrq import RRQ

MAX_AGE = 100


@dataclass
class BreakevenResult:
    benefit: str          # "RRQ" | "SV"
    early_age: int
    late_age: int
    early_annual: float   # rente annuelle si début hâtif (dollars constants)
    late_annual: float
    breakeven_age: int | None  # None si jamais rentable avant MAX_AGE
    cumulative_early: list[float]  # index = âge - early_age
    cumulative_late: list[float]


def _cumulative(annual: float, start_age: int, from_age: int) -> list[float]:
    total, out = 0.0, []
    for age in range(from_age, MAX_AGE + 1):
        if age >= start_age:
            total += annual
        out.append(total)
    return out


def _breakeven(early_annual: float, early_age: int,
               late_annual: float, late_age: int, benefit: str) -> BreakevenResult:
    cum_early = _cumulative(early_annual, early_age, early_age)
    cum_late = _cumulative(late_annual, late_age, early_age)
    be = next((early_age + i for i, (e, l) in enumerate(zip(cum_early, cum_late))
               if l > e and i > 0), None)
    return BreakevenResult(benefit, early_age, late_age, early_annual, late_annual,
                           be, cum_early, cum_late)


def rrq_breakeven(monthly_at_65: float, early_age: int, late_age: int,
                  year: int) -> BreakevenResult:
    rrq = RRQ(year)
    return _breakeven(rrq.annual_pension(monthly_at_65, early_age), early_age,
                      rrq.annual_pension(monthly_at_65, late_age), late_age, "RRQ")


def oas_breakeven(early_age: int, late_age: int, year: int,
                  residence_years: int = 40) -> BreakevenResult:
    oas = OAS(year)

    def annual(start: int) -> float:
        # Montant à l'âge de début (la majoration de 75 ans s'applique aux deux)
        return oas.annual_pension(max(start, 65), start, residence_years)

    return _breakeven(annual(early_age), early_age, annual(late_age), late_age, "SV")


def standard_breakevens(monthly_at_65: float, year: int,
                        residence_years: int = 40) -> list[BreakevenResult]:
    """Comparaisons usuelles: RRQ 60 vs 65, 65 vs 70, 60 vs 70; SV 65 vs 70."""
    out = []
    if monthly_at_65 > 0:
        for a, b in ((60, 65), (65, 70), (60, 70), (65, 72)):
            out.append(rrq_breakeven(monthly_at_65, a, b, year))
    out.append(oas_breakeven(65, 70, year, residence_years))
    return out
