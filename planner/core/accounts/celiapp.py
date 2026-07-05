"""CELIAPP (FHSA) — compte d'épargne libre d'impôt pour l'achat d'une
première propriété.

Règles:
- Cotisations déductibles du revenu (comme un REER): 8 000$/an,
  40 000$ à vie, report des droits inutilisés (max 8 000$).
- Retrait admissible (achat première habitation): NON imposable.
- Compte fermé après 15 ans ou à 71 ans; le solde peut être transféré
  au REER/FERR sans impact sur les droits REER.
"""
from dataclasses import dataclass

from planner.core.accounts.params import load_account_params


@dataclass
class CELIAPP:
    balance: float = 0.0
    year_opened: int = 2025
    lifetime_contributed: float = 0.0
    carryforward: float = 0.0  # droits reportés de l'année précédente (max 8000)
    _current_year_contributed: float = 0.0

    def __post_init__(self):
        self.p = load_account_params(self.year_opened)["fhsa"]

    def new_year(self) -> None:
        """1er janvier: le droit annuel inutilisé se reporte (max 8 000$)."""
        unused = self.p["annual_limit"] - self._current_year_contributed
        self.carryforward = min(self.p["max_carryforward"], max(0.0, self.carryforward + unused))
        self._current_year_contributed = 0.0

    @property
    def contribution_room(self) -> float:
        annual = self.p["annual_limit"] - self._current_year_contributed + self.carryforward
        lifetime = self.p["lifetime_limit"] - self.lifetime_contributed
        return max(0.0, min(annual, lifetime))

    def contribute(self, amount: float) -> float:
        """Cotise (déductible). Retourne le montant réellement cotisé."""
        actual = max(0.0, min(amount, self.contribution_room))
        self.balance += actual
        used_carryforward = min(self.carryforward, actual)
        self.carryforward -= used_carryforward
        self._current_year_contributed += actual - used_carryforward
        self.lifetime_contributed += actual
        return actual

    def qualifying_withdrawal(self, amount: float) -> float:
        """Retrait admissible pour achat de première habitation (NON imposable)."""
        actual = max(0.0, min(amount, self.balance))
        self.balance -= actual
        return actual

    def transfer_to_reer(self, reer) -> float:
        """Transfert du solde au REER (sans consommer de droits REER)."""
        amount, self.balance = self.balance, 0.0
        reer.balance += amount
        return amount

    def must_close(self, current_year: int, age: int) -> bool:
        return (current_year - self.year_opened >= self.p["max_years_open"]
                or age >= self.p["max_age"])

    def grow(self, rate: float) -> None:
        self.balance *= (1 + rate)
