"""REER avec droits de cotisation réels + mécanisme RAP (HBP).

Règles:
- Nouveaux droits annuels = min(18% du revenu gagné de l'année précédente,
  plafond annuel). Les droits inutilisés se reportent indéfiniment.
- Cotisation déductible du revenu imposable; retrait 100% imposable.
- Conversion obligatoire en FERR au plus tard l'année des 71 ans.
- RAP: retrait non imposable jusqu'à 60 000$ pour l'achat d'une première
  habitation; remboursement en 15 versements annuels égaux après 2 ans de
  grâce; tout versement manquant s'ajoute au revenu imposable.
"""
from dataclasses import dataclass, field

from planner.core.accounts.params import load_account_params


@dataclass
class REER:
    balance: float = 0.0
    contribution_room: float = 0.0
    year: int = 2025

    def __post_init__(self):
        self.p = load_account_params(self.year)["rrsp"]

    def add_new_room(self, prior_year_earned_income: float) -> float:
        """Ajoute les nouveaux droits basés sur le revenu gagné de l'an dernier."""
        new_room = min(prior_year_earned_income * self.p["earned_income_rate"],
                       self.p["annual_max"])
        self.contribution_room += new_room
        return new_room

    def contribute(self, amount: float) -> float:
        """Cotise (plafonné aux droits). Retourne le montant réellement cotisé
        (= la déduction fiscale)."""
        actual = max(0.0, min(amount, self.contribution_room))
        self.balance += actual
        self.contribution_room -= actual
        return actual

    def withdraw(self, amount: float) -> float:
        """Retrait (100% imposable). Les droits ne sont PAS restaurés."""
        actual = max(0.0, min(amount, self.balance))
        self.balance -= actual
        return actual

    def grow(self, rate: float) -> None:
        self.balance *= (1 + rate)

    def must_convert(self, age: int) -> bool:
        return age >= self.p["conversion_age"]

    def convert_to_ferr(self) -> float:
        """Transfert complet vers un FERR (non imposable). Retourne le montant."""
        amount, self.balance = self.balance, 0.0
        return amount


@dataclass
class RAP:
    """Régime d'accession à la propriété (HBP) — suivi du remboursement."""
    year: int = 2025
    withdrawal_year: int | None = None
    outstanding: float = 0.0
    _repaid_years: int = field(default=0, repr=False)

    def __post_init__(self):
        self.p = load_account_params(self.year)["hbp"]

    @property
    def max_withdrawal(self) -> float:
        return self.p["max_withdrawal"]

    def borrow(self, reer: REER, amount: float, year: int) -> float:
        """Retrait RAP du REER (non imposable). Retourne le montant retiré."""
        if self.outstanding > 0:
            raise ValueError("Un RAP est déjà en cours de remboursement")
        actual = min(amount, self.max_withdrawal, reer.balance)
        reer.withdraw(actual)  # non imposable: le simulateur ne le compte pas comme revenu
        self.outstanding = actual
        self.withdrawal_year = year
        self._repaid_years = 0
        return actual

    def repayment_due(self, year: int) -> float:
        """Versement annuel requis pour `year`."""
        if self.outstanding <= 0 or self.withdrawal_year is None:
            return 0.0
        first_repayment_year = self.withdrawal_year + self.p["grace_years"]
        if year < first_repayment_year:
            return 0.0
        remaining_years = self.p["repayment_years"] - self._repaid_years
        if remaining_years <= 0:
            return self.outstanding
        return self.outstanding / remaining_years

    def repay(self, reer: REER, amount: float, year: int) -> dict:
        """Rembourse le RAP (cotisation REER SANS utiliser de droits).

        Retourne {"repaid": x, "taxable_shortfall": y} — le manque à rembourser
        s'ajoute au revenu imposable de l'année.
        """
        due = self.repayment_due(year)
        repaid = min(amount, self.outstanding)
        shortfall = max(0.0, due - repaid)
        # Le remboursement retourne dans le REER sans consommer de droits.
        reer.balance += repaid
        self.outstanding = max(0.0, self.outstanding - repaid - shortfall)
        if due > 0:
            self._repaid_years += 1
        return {"repaid": repaid, "taxable_shortfall": shortfall}
