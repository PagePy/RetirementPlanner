"""CELI avec droits de cotisation réels.

Règles:
- Nouveaux droits chaque année (plafond annuel indexé).
- Les retraits restaurent les droits... mais seulement le 1er janvier SUIVANT.
- Retraits et croissance non imposables.
"""
from dataclasses import dataclass, field

from planner.core.accounts.params import load_account_params


@dataclass
class CELI:
    balance: float = 0.0
    contribution_room: float = 0.0
    year: int = 2025
    _pending_room_restore: float = field(default=0.0, repr=False)

    def __post_init__(self):
        self.p = load_account_params(self.year)["tfsa"]

    def new_year(self, year: int) -> None:
        """1er janvier: nouveaux droits + restauration des retraits de l'an passé."""
        params = load_account_params(year)["tfsa"]
        self.contribution_room += params["annual_limit"] + self._pending_room_restore
        self._pending_room_restore = 0.0

    def contribute(self, amount: float) -> float:
        actual = max(0.0, min(amount, self.contribution_room))
        self.balance += actual
        self.contribution_room -= actual
        return actual

    def withdraw(self, amount: float) -> float:
        """Retrait non imposable; les droits reviennent l'année suivante."""
        actual = max(0.0, min(amount, self.balance))
        self.balance -= actual
        self._pending_room_restore += actual
        return actual

    def grow(self, rate: float) -> None:
        self.balance *= (1 + rate)
