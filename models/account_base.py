# models/account_base.py
from dataclasses import dataclass, field

@dataclass
class Account:
    name: str
    balance: float = 0.0
    annual_return: float = 0.04

    def grow(self):
        self.balance *= (1 + self.annual_return)

    def deposit(self, amount: float):
        self.balance += max(0.0, amount)

    def withdraw(self, amount: float) -> float:
        amt = min(self.balance, max(0.0, amount))
        self.balance -= amt
        return amt