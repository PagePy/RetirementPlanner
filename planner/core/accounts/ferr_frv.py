"""FERR (RRIF) et FRV (LIF) — minimums légaux et règles de retrait.

Règles:
- Minimum FERR: avant 71 ans = 1/(90 − âge); ensuite table légale (5,28% à 71,
  jusqu'à 20% à 95+). L'âge du CONJOINT le plus jeune peut être utilisé pour
  réduire le minimum obligatoire.
- FRV Québec: minimum identique au FERR. Le plafond MAXIMUM de retrait est
  ABOLI depuis le 1er janvier 2025 (les FRV québécois n'ont plus de maximum).
- Retraits 100% imposables; admissibles au crédit pension et au
  fractionnement à partir de 65 ans.
"""
from dataclasses import dataclass

from planner.core.accounts.params import load_rrif_factors, load_account_params


def rrif_min_factor(age: int) -> float:
    """Facteur de retrait minimum FERR selon l'âge au 1er janvier."""
    if age < 0:
        raise ValueError("âge invalide")
    factors = load_rrif_factors()
    cap_age = factors["rrif_min_cap_age"]
    table = factors["rrif_min_factors"]
    if age >= cap_age:
        return table[str(cap_age)]
    if str(age) in table:
        return table[str(age)]
    # Avant 71 ans: 1/(90 - âge)
    if age >= 90:
        return table[str(cap_age)]
    return 1.0 / (90 - age) if age < 90 else table[str(cap_age)]


@dataclass
class FERR:
    balance: float = 0.0
    spouse_age_offset: int = 0  # âge du conjoint − âge du rentier (négatif si plus jeune)
    use_spouse_age: bool = False

    def min_withdrawal(self, age: int) -> float:
        """Retrait minimum obligatoire de l'année (âge au 1er janvier)."""
        if self.balance <= 0:
            return 0.0
        effective_age = age + self.spouse_age_offset if self.use_spouse_age else age
        return self.balance * rrif_min_factor(max(0, effective_age))

    def withdraw(self, amount: float) -> float:
        actual = max(0.0, min(amount, self.balance))
        self.balance -= actual
        return actual

    def grow(self, rate: float) -> None:
        self.balance *= (1 + rate)


@dataclass
class FRV(FERR):
    """FRV québécois: minimum FERR, maximum aboli depuis 2025."""
    year: int = 2025
    province: str = "QC"

    def max_withdrawal(self, age: int) -> float | None:
        """Retourne None si aucun maximum (QC depuis 2025)."""
        p = load_account_params(self.year).get("lif_quebec", {})
        abolished_since = p.get("max_abolished_since")
        if self.province == "QC" and abolished_since and self.year >= abolished_since:
            return None
        # Provinces avec maximum: à implémenter lors de l'ajout des provinces.
        return None
