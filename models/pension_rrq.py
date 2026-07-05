# models/pension_rrq.py
from dataclasses import dataclass

@dataclass
class RRQ:
    start_age: int = 65
    monthly_amount_at_65: float = 1200.0  # placeholder, ajustable
    index_rate: float = 0.02

    def monthly_benefit(self, age: int) -> float:
        # Ajustement simple par âge (réduction si avant 65, hausse si après 65)
        if age < 65:
            # réduction approx 0.6% par mois avant 65 (~7.2% par an)
            years_early = 65 - age
            factor = max(0.6, 1.0 - 0.072 * years_early)
            base = self.monthly_amount_at_65 * factor
        elif age > 65:
            # hausse approx 0.7% par mois après 65 (~8.4% par an)
            years_late = age - 65
            factor = 1.0 + 0.084 * years_late
            base = self.monthly_amount_at_65 * factor
        else:
            base = self.monthly_amount_at_65
        return base

    def annual_benefit(self, age: int) -> float:
        return 12.0 * self.monthly_benefit(age)

    def indexed_annual_benefit(self, age: int, years_since_start: int) -> float:
        # Indexation annuelle (CPI)
        return self.annual_benefit(age) * ((1 + self.index_rate) ** max(0, years_since_start))