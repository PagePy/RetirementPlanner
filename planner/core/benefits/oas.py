"""SV (OAS) — pension avec report, majoration 75+, proratisation et récupération.

Règles:
- Début entre 65 et 70 ans; bonification de 0,6% par mois de report (max +36%).
- Majoration de 10% du montant à partir de 75 ans.
- Proratisation selon les années de résidence au Canada (pleine pension à 40 ans).
- Récupération (clawback): 15% du revenu net au-delà du seuil, plafonnée à la SV reçue.
"""
from planner.core.benefits.params import load_benefits


class OAS:
    def __init__(self, year: int):
        self.p = load_benefits(year)["oas"]
        self.year = year

    def deferral_factor(self, start_age: float) -> float:
        p = self.p
        start_age = max(p["min_start_age"], min(p["max_start_age"], start_age))
        months = min(round((start_age - p["min_start_age"]) * 12), p["max_deferral_months"])
        return 1.0 + months * p["deferral_increase_per_month"]

    def annual_pension(self, current_age: int, start_age: float,
                       residence_years: int = 40) -> float:
        """Pension SV annuelle brute (avant récupération) à l'âge `current_age`."""
        p = self.p
        if current_age < start_age or current_age < p["min_start_age"]:
            return 0.0
        base = p["monthly_65_74"] * 12
        residence_factor = min(1.0, residence_years / p["full_pension_residence_years"])
        amount = base * residence_factor * self.deferral_factor(start_age)
        if current_age >= 75:
            amount *= (1.0 + p["uplift_75_plus"])
        return amount

    def clawback(self, net_income: float, oas_received: float) -> float:
        """Impôt de récupération de la SV selon le revenu net individuel."""
        p = self.p
        if net_income <= p["clawback_threshold"]:
            return 0.0
        recovery = (net_income - p["clawback_threshold"]) * p["clawback_rate"]
        return min(recovery, oas_received)

    @property
    def clawback_threshold(self) -> float:
        return self.p["clawback_threshold"]
