# services/stress.py
from dataclasses import dataclass
from typing import Optional, Dict

@dataclass
class StressParams:
    # Inflation appliquée à certaines composantes indexées (prestations, dépenses)
    inflation_rate: float = 0.02
    # Chocs de rendement par année (override du annual_return des comptes)
    # Exemple: {2026: {"REER": -0.15, "Taxable": -0.10}, 2027: {"REER": 0.0}}
    return_shocks: Optional[Dict[int, Dict[str, float]]] = None
    # Dépenses imprévues ménage par année (montant net à déduire du revenu disponible)
    unexpected_expenses: Optional[Dict[int, float]] = None
    # Décès prématuré: année et personne ("primary" ou "spouse")
    premature_death_year: Optional[int] = None
    premature_death_person: Optional[str] = None

def apply_return_shocks(year: int, accounts: dict, stress: StressParams):
    if not stress or not stress.return_shocks:
        return
    shock_year = stress.return_shocks.get(year)
    if not shock_year:
        return
    for acc_name, shock_return in shock_year.items():
        if acc_name in accounts:
            accounts[acc_name].annual_return = shock_return

def inflate_value(base: float, inflation_rate: float, years_since_start: int) -> float:
    return base * ((1 + inflation_rate) ** max(0, years_since_start))

def is_person_deceased(year: int, stress: StressParams, target: str) -> bool:
    if not stress or not stress.premature_death_year:
        return False
    return (stress.premature_death_person == target) and (year >= stress.premature_death_year)

def unexpected_expense_for_year(year: int, stress: StressParams) -> float:
    if not stress or not stress.unexpected_expenses:
        return 0.0
    return stress.unexpected_expenses.get(year, 0.0)