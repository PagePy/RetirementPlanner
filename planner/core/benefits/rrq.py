"""RRQ/CPP — rente de retraite avec ajustements réels selon l'âge de début.

Règles:
- Avant 65 ans: réduction de 0,6% par mois d'anticipation (max -36% à 60 ans).
- Après 65 ans: bonification de 0,7% par mois de report (max +58,8% à 72 ans au QC).
- Rente de conjoint survivant: simplifiée à 60% de la rente du défunt,
  plafonnée pour que (rente propre + survivant) <= rente maximale à 65 ans.
- Prestation de décès: montant forfaitaire.
"""
from planner.core.benefits.params import load_benefits


class RRQ:
    def __init__(self, year: int):
        self.p = load_benefits(year)["rrq"]
        self.year = year

    def adjustment_factor(self, start_age: float) -> float:
        """Facteur multiplicatif appliqué à la rente à 65 ans selon l'âge de début."""
        p = self.p
        start_age = max(p["min_start_age"], min(p["max_start_age"], start_age))
        months = round((start_age - p["reference_age"]) * 12)
        if months < 0:
            return 1.0 + months * p["early_reduction_per_month"]
        return 1.0 + months * p["late_increase_per_month"]

    def annual_pension(self, amount_at_65_monthly: float, start_age: float) -> float:
        """Rente annuelle selon le montant projeté à 65 ans et l'âge de début réel.

        `amount_at_65_monthly`: montant mensuel auquel la personne aurait droit
        à 65 ans (fourni par le relevé Retraite Québec), plafonné au maximum.
        """
        monthly = min(amount_at_65_monthly, self.p["max_monthly_at_65"])
        return monthly * 12 * self.adjustment_factor(start_age)

    def survivor_pension(self, deceased_annual_pension: float,
                         survivor_own_annual_pension: float) -> float:
        """Rente annuelle de conjoint survivant (simplifiée).

        60% de la rente du défunt, plafonnée pour que le total (rente propre +
        survivant) ne dépasse pas la rente maximale à 65 ans.
        """
        p = self.p
        combined_max = p["max_monthly_at_65"] * 12
        survivor = deceased_annual_pension * p["survivor_rate"]
        room = max(0.0, combined_max - survivor_own_annual_pension)
        return min(survivor, room)

    def death_benefit(self) -> float:
        return self.p["death_benefit"]
