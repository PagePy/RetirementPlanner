# models/taxable.py
from .account_base import Account
from dataclasses import dataclass

@dataclass
class Taxable(Account):
    # Répartition des revenus de placement (somme = 1.0)
    interest_ratio: float = 0.40
    eligible_dividend_ratio: float = 0.20
    capital_gain_ratio: float = 0.40

    # Rendement annuel total (annual_return); distribué selon ratios
    def annual_taxable_components(self) -> dict:
        """
        Retourne les composantes imposables générées sur l'année:
        - interest: intérêts, 100% imposables
        - eligible_dividends: dividendes admissibles (avant gross-up)
        - capital_gains: gains en capital (50% imposables au Canada)
        Les montants retournés sont basés sur le rendement de l'année, sans retrait.
        """
        total_return_amount = self.balance * self.annual_return
        interest = total_return_amount * self.interest_ratio
        eligible_dividends = total_return_amount * self.eligible_dividend_ratio
        capital_gains = total_return_amount * self.capital_gain_ratio
        return {
            "interest": max(0.0, interest),
            "eligible_dividends": max(0.0, eligible_dividends),
            "capital_gains": max(0.0, capital_gains),
        }