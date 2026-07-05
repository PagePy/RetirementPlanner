"""SRG (GIS) et Allocation au conjoint — prestations selon le revenu.

Règles (simplifiées mais fidèles aux mécanismes officiels):
- SRG personne seule: maximum réduit de 50 cents par dollar de revenu
  (excluant la SV et une exemption sur le revenu d'emploi).
- SRG couple (les deux reçoivent la SV): maximum par personne réduit de
  25 cents par dollar de revenu combiné du couple.
- Allocation au conjoint (60-64 ans, conjoint d'un prestataire du SRG):
  maximum réduit de 75 cents par dollar de revenu combiné.
- Le SRG est NON IMPOSABLE.
"""
from planner.core.benefits.params import load_benefits


class GIS:
    def __init__(self, year: int):
        self.p = load_benefits(year)["gis"]
        self.year = year

    def _countable_income(self, income_excluding_oas: float,
                          employment_income: float = 0.0) -> float:
        """Revenu considéré: exclut la SV et applique l'exemption d'emploi."""
        exemption = min(employment_income, self.p["employment_income_exemption"])
        return max(0.0, income_excluding_oas - exemption)

    def annual_single(self, income_excluding_oas: float,
                      employment_income: float = 0.0) -> float:
        """SRG annuel pour une personne seule recevant la SV."""
        p = self.p
        countable = self._countable_income(income_excluding_oas, employment_income)
        max_annual = p["single_max_monthly"] * 12
        return max(0.0, max_annual - countable * p["single_reduction_rate"])

    def annual_couple_each(self, combined_income_excluding_oas: float,
                           combined_employment_income: float = 0.0) -> float:
        """SRG annuel PAR PERSONNE pour un couple dont les deux reçoivent la SV."""
        p = self.p
        countable = self._countable_income(
            combined_income_excluding_oas, combined_employment_income)
        max_annual = p["couple_both_oas_each_max_monthly"] * 12
        return max(0.0, max_annual - countable * p["couple_reduction_rate_each"])

    def annual_allowance(self, spouse_age: int,
                         combined_income_excluding_oas: float) -> float:
        """Allocation au conjoint (60-64 ans) d'un prestataire du SRG."""
        p = self.p
        if not (p["allowance_min_age"] <= spouse_age <= p["allowance_max_age"]):
            return 0.0
        max_annual = p["allowance_max_monthly"] * 12
        reduction = combined_income_excluding_oas * p["allowance_reduction_rate"]
        return max(0.0, max_annual - reduction)
