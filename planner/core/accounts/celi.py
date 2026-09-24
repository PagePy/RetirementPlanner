"""CELI avec droits de cotisation réels.

Règles:
- Nouveaux droits chaque année (plafond annuel indexé, arrondi au 500 $).
- Les retraits restaurent les droits... mais seulement le 1er janvier SUIVANT.
- Retraits et croissance non imposables.
"""
import math
from dataclasses import dataclass, field

from planner.core.accounts.params import load_account_params, load_tfsa_limits

TFSA_START_YEAR = 2009
TFSA_MIN_AGE = 18


def annual_limit(year: int, inflation: float = 0.0) -> float:
    """Plafond officiel si publié, sinon dernier plafond connu indexé et arrondi au 500 $."""
    history = load_tfsa_limits()
    if year in history:
        return history[year]
    params = load_account_params(year)
    limit = params["tfsa"]["annual_limit"]
    years_after = year - params["_effective_year"]
    if years_after <= 0:
        return float(limit)
    raw = limit * (1 + inflation) ** years_after
    return float(math.floor(raw / 500 + 0.5) * 500)


def cumulative_room(birth_year: int, year: int, inflation: float = 0.0) -> float:
    """Droits CELI cumulés au 1er janvier de `year` pour une personne qui n'a
    jamais cotisé (résidente depuis 18 ans)."""
    first = max(TFSA_START_YEAR, birth_year + TFSA_MIN_AGE)
    return float(sum(annual_limit(y, inflation) for y in range(first, year + 1)))


@dataclass
class CELI:
    balance: float = 0.0
    contribution_room: float = 0.0
    year: int = 2025
    inflation: float = 0.0
    _pending_room_restore: float = field(default=0.0, repr=False)

    def __post_init__(self):
        self.p = load_account_params(self.year)["tfsa"]

    def new_year(self, year: int) -> None:
        """1er janvier: nouveaux droits + restauration des retraits de l'an passé."""
        self.contribution_room += (annual_limit(year, self.inflation)
                                   + self._pending_room_restore)
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
