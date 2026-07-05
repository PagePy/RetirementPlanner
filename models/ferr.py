# models/ferr.py
from dataclasses import dataclass
from .account_base import Account

@dataclass
class FERR(Account):
    owner_age: int = 71
    use_spousal_age: bool = False
    spouse_age: int = None  # optionnel

    def effective_age(self) -> int:
        if self.use_spousal_age and self.spouse_age is not None:
            return max(71, self.spouse_age)
        return max(71, self.owner_age)

    def min_withdrawal_rate(self) -> float:
        age = self.effective_age()
        table = {
            71: 0.0528, 72: 0.054, 73: 0.0553, 74: 0.0567, 75: 0.0582,
            76: 0.0598, 77: 0.0617, 78: 0.0636, 79: 0.0658, 80: 0.0682,
            81: 0.0708, 82: 0.0738, 83: 0.0771, 84: 0.0808, 85: 0.0851,
            86: 0.0899, 87: 0.0955, 88: 0.1021, 89: 0.1099, 90: 0.1192,
        }
        if age in table:
            return table[age]
        return min(0.20, 0.1192 + 0.01 * (age - 90))

    def mandatory_withdrawal(self) -> float:
        return self.balance * self.min_withdrawal_rate()