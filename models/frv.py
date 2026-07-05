# models/frv.py
from dataclasses import dataclass
from .account_base import Account
from data.frv_qc_tables import frv_min_rate_qc, frv_max_rate_qc

@dataclass
class FRV(Account):
    owner_age: int = 65
    province: str = "QC"

    def min_withdrawal_rate(self) -> float:
        if self.province == "QC":
            return frv_min_rate_qc(self.owner_age)
        # défaut simple si autre province
        return 0.04

    def max_withdrawal_rate(self) -> float:
        if self.province == "QC":
            return frv_max_rate_qc(self.owner_age)
        # défaut simple si autre province
        return 0.20

    def min_withdrawal(self) -> float:
        return self.balance * self.min_withdrawal_rate()

    def max_withdrawal(self) -> float:
        return self.balance * self.max_withdrawal_rate()