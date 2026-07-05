# models/pension_oas.py
from dataclasses import dataclass

@dataclass
class OAS:
    start_age: int = 65
    annual_amount_at_65: float = 8400.0  # placeholder (PSV)
    index_rate: float = 0.02
    clawback_threshold: float = 90000.0  # seuil approximatif
    clawback_rate: float = 0.15         # 15% sur l'excédent

    def annual_benefit(self, age: int) -> float:
        if age < self.start_age:
            return 0.0
        return self.annual_amount_at_65

    def indexed_annual_benefit(self, age: int, years_since_start: int) -> float:
        base = self.annual_benefit(age)
        return base * ((1 + self.index_rate) ** max(0, years_since_start))

    def clawback(self, net_income: float) -> float:
        if net_income <= self.clawback_threshold:
            return 0.0
        return self.clawback_rate * (net_income - self.clawback_threshold)