# data/fiscal_tables.py
from dataclasses import dataclass, field
from typing import List, Tuple

Bracket = Tuple[float, float]  # (seuil, taux)

@dataclass
class FederalTaxConfig:
    brackets: List[Bracket]
    basic_personal_amount: float
    pension_credit: float
    dividend_credit_rate: float

@dataclass
class QuebecTaxConfig:
    brackets: List[Bracket]
    basic_personal_amount: float
    pension_credit: float
    dividend_credit_rate: float

@dataclass
class FiscalQC:
    REER_MAX: float = 32790.0
    CELI_LIMIT: float = 6500.0

    federal: FederalTaxConfig = field(
        default_factory=lambda: FederalTaxConfig(
            brackets=[(0, 0.15), (55000, 0.205), (110000, 0.26), (165000, 0.29)],
            basic_personal_amount=15000.0,
            pension_credit=2000.0,
            dividend_credit_rate=0.15,
        )
    )

    quebec: QuebecTaxConfig = field(
        default_factory=lambda: QuebecTaxConfig(
            brackets=[(0, 0.15), (50000, 0.20), (100000, 0.24), (150000, 0.257)],
            basic_personal_amount=18000.0,
            pension_credit=2000.0,
            dividend_credit_rate=0.10,
        )
    )