"""Compte non-enregistré avec suivi du prix de base rajusté (PBR).

Corrige le défaut majeur de l'ancien moteur qui imposait 50% de chaque
retrait: seule la PLUS-VALUE réalisée est un gain en capital, calculée
au prorata du PBR sur la valeur marchande.

Règles:
- Cotisation: augmente le PBR du même montant.
- Retrait: gain réalisé = retrait × (1 − PBR/valeur); le PBR est réduit
  proportionnellement.
- Distributions annuelles (intérêts, dividendes, distributions de gains):
  imposables l'année reçue; si réinvesties, elles augmentent le PBR.
"""
from dataclasses import dataclass


@dataclass
class Taxable:
    balance: float = 0.0
    acb: float = 0.0  # prix de base rajusté (coût fiscal)
    # Répartition du rendement annuel total entre types de revenus
    interest_ratio: float = 0.0
    eligible_dividend_ratio: float = 0.0
    capital_growth_ratio: float = 1.0  # croissance non distribuée (gain latent)

    def contribute(self, amount: float) -> float:
        if amount <= 0:
            return 0.0
        self.balance += amount
        self.acb += amount
        return amount

    def withdraw(self, amount: float) -> dict:
        """Retire `amount`. Retourne {"proceeds", "realized_gain", "acb_used"}."""
        actual = max(0.0, min(amount, self.balance))
        if actual == 0.0 or self.balance <= 0:
            return {"proceeds": 0.0, "realized_gain": 0.0, "acb_used": 0.0}
        acb_ratio = min(1.0, self.acb / self.balance) if self.balance > 0 else 1.0
        acb_used = actual * acb_ratio
        realized_gain = actual - acb_used
        self.balance -= actual
        self.acb = max(0.0, self.acb - acb_used)
        return {"proceeds": actual, "realized_gain": realized_gain, "acb_used": acb_used}

    def grow(self, rate: float, reinvest_distributions: bool = True) -> dict:
        """Applique le rendement annuel et retourne les revenus imposables.

        Retourne {"interest", "eligible_dividends", "capital_gains_distributions"}
        — montants imposables de l'année (les gains latents ne sont PAS imposés).
        """
        total_return = self.balance * rate
        interest = total_return * self.interest_ratio
        dividends = total_return * self.eligible_dividend_ratio
        growth = total_return * self.capital_growth_ratio

        # La croissance latente augmente la valeur sans toucher le PBR.
        self.balance += growth
        if reinvest_distributions:
            # Distributions réinvesties: valeur ET PBR augmentent.
            self.balance += interest + dividends
            self.acb += interest + dividends
        return {
            "interest": interest,
            "eligible_dividends": dividends,
            "capital_gains_distributions": 0.0,
        }

    @property
    def unrealized_gain(self) -> float:
        """Gain latent (pertinent pour l'analyse successorale)."""
        return max(0.0, self.balance - self.acb)
