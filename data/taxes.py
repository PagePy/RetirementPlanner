# services/taxes.py
from dataclasses import dataclass

@dataclass
class TaxResult:
    federal: float
    provincial: float
    credits: float
    net_tax: float
    oas_clawback: float

def _apply_brackets(income: float, brackets):
    tax = 0.0
    last_threshold = 0.0
    for threshold, rate in brackets:
        if income > threshold:
            taxable_at_rate = min(income - threshold, (income - last_threshold))
            tax += taxable_at_rate * rate
            last_threshold = threshold
    return max(0.0, tax)

def compute_taxes_qc(income_breakdown, fiscal, pension_income_for_credit: float = 0.0, oas_clawback: float = 0.0):
    # income_breakdown keys: employment, pension, interest, eligible_dividends_gross, capital_gains, oas, rrq
    taxable_income = (
        income_breakdown.get("employment", 0.0)
        + income_breakdown.get("pension", 0.0)
        + income_breakdown.get("interest", 0.0)
        + income_breakdown.get("eligible_dividends_gross", 0.0)
        + 0.5 * income_breakdown.get("capital_gains", 0.0)
        + income_breakdown.get("oas", 0.0)
        + income_breakdown.get("rrq", 0.0)
    )

    # Impôts par paliers
    federal_tax = _apply_brackets(taxable_income, fiscal.federal.brackets)
    quebec_tax = _apply_brackets(taxable_income, fiscal.quebec.brackets)

    # Crédits de base
    federal_tax = max(0.0, federal_tax - fiscal.federal.basic_personal_amount * 0.15)
    quebec_tax = max(0.0, quebec_tax - fiscal.quebec.basic_personal_amount * 0.15)

    # Crédit pour revenu de pension (approx)
    if pension_income_for_credit > 0:
        federal_tax = max(0.0, federal_tax - fiscal.federal.pension_credit * 0.15)
        quebec_tax = max(0.0, quebec_tax - fiscal.quebec.pension_credit * 0.15)

    net_tax = federal_tax + quebec_tax + oas_clawback
    return TaxResult(
        federal=round(federal_tax, 2),
        provincial=round(quebec_tax, 2),
        credits=round(fiscal.federal.basic_personal_amount + fiscal.quebec.basic_personal_amount, 2),
        net_tax=round(net_tax, 2),
        oas_clawback=round(oas_clawback, 2),
    )