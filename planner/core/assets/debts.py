"""Passifs du ménage — dettes de tout genre avec amortissement réel.

Types supportés: hypothèque, prêt auto, carte de crédit, prêt personnel,
marge de crédit, autre. Chaque année:
    intérêts = solde × taux
    capital remboursé = paiement − intérêts
    nouveau solde = solde − capital remboursé

Le service de la dette (paiements) s'ajoute aux besoins de liquidités du
ménage à la retraite; pendant l'accumulation, il est supposé couvert par
les salaires (comme les autres dépenses courantes).
"""
from dataclasses import dataclass, field

DEBT_KINDS = ("hypotheque", "auto", "carte_credit", "personnel", "marge", "autre")


@dataclass
class DebtConfig:
    name: str
    balance: float
    interest_rate: float         # taux annuel (ex: 0.055)
    annual_payment: float        # paiement annuel (capital + intérêts)
    kind: str = "autre"


@dataclass
class Debt:
    """État runtime d'une dette pendant la simulation."""
    cfg: DebtConfig
    balance: float = field(init=False)

    def __post_init__(self):
        self.balance = self.cfg.balance

    @property
    def is_active(self) -> bool:
        return self.balance > 0.005

    def annual_service(self) -> dict:
        """Applique une année de paiements.

        Retourne {"payment", "interest", "principal"} — le paiement réel
        est plafonné à ce qu'il faut pour éteindre la dette.
        """
        if not self.is_active:
            return {"payment": 0.0, "interest": 0.0, "principal": 0.0}
        interest = self.balance * self.cfg.interest_rate
        payment = min(self.cfg.annual_payment, self.balance + interest)
        principal = max(0.0, payment - interest)
        if payment <= interest:
            # Paiement insuffisant: la dette croît (ex: carte de crédit
            # au paiement minimum).
            self.balance += interest - payment
        else:
            self.balance = max(0.0, self.balance - principal)
        return {"payment": payment, "interest": interest, "principal": principal}

    def payoff(self) -> float:
        """Rembourse entièrement (ex: à la vente de l'actif lié).
        Retourne le montant payé."""
        amount, self.balance = self.balance, 0.0
        return amount

    def years_to_payoff(self) -> int | None:
        """Nombre d'années avant extinction au paiement actuel (None si jamais)."""
        bal, years = self.balance, 0
        while bal > 0.005:
            interest = bal * self.cfg.interest_rate
            if self.cfg.annual_payment <= interest:
                return None
            bal = bal + interest - self.cfg.annual_payment
            years += 1
            if years > 100:
                return None
        return years
