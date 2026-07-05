# models/pension_srg.py
from dataclasses import dataclass

@dataclass
class SRG:
    # Supplément de revenu garanti (simplifié)
    eligible_age: int = 65
    max_annual_amount: float = 12000.0  # placeholder pour une personne seule
    reduction_rate: float = 0.50        # réduit en fonction du revenu
    index_rate: float = 0.02

    def annual_benefit(self, age: int, income_for_srg: float) -> float:
        if age < self.eligible_age:
            return 0.0
        # SRG diminue avec le revenu total pertinent
        benefit = max(0.0, self.max_annual_amount - self.reduction_rate * income_for_srg)
        return benefit

    def indexed_annual_benefit(self, age: int, income_for_srg: float, years_since_start: int) -> float:
        base = self.annual_benefit(age, income_for_srg)
        return base * ((1 + self.index_rate) ** max(0, years_since_start))