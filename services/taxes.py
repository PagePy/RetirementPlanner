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
    prev = 0.0
    for threshold, rate in brackets:
        if income > threshold:
            taxable_at_rate = income - max(prev, threshold)
            if taxable_at_rate > 0:
                tax += taxable_at_rate * rate
            prev = threshold
    return max(0.0, tax)

def compute_taxes_person_qc(income_breakdown, fiscal, pension_income_for_credit: float = 0.0, oas_clawback: float = 0.0):
    # Dividendes admissibles: gross-up fédéral approx 38%
    eligible_dividends = income_breakdown.get("eligible_dividends", 0.0)
    gross_up_rate_fed = 0.38
    dividends_grossed = eligible_dividends * (1 + gross_up_rate_fed)

    taxable_income = (
        income_breakdown.get("employment", 0.0)
        + income_breakdown.get("pension", 0.0)
        + income_breakdown.get("interest", 0.0)
        + dividends_grossed
        + 0.5 * income_breakdown.get("capital_gains", 0.0)
        + income_breakdown.get("oas", 0.0)
        + income_breakdown.get("rrq", 0.0)
    )

    federal_tax = _apply_brackets(taxable_income, fiscal.federal.brackets)
    quebec_tax = _apply_brackets(taxable_income, fiscal.quebec.brackets)

    # Crédits de base approximés
    federal_tax = max(0.0, federal_tax - fiscal.federal.basic_personal_amount * 0.15)
    quebec_tax = max(0.0, quebec_tax - fiscal.quebec.basic_personal_amount * 0.15)

    # Crédit pour revenu de pension
    if pension_income_for_credit > 0:
        federal_tax = max(0.0, federal_tax - fiscal.federal.pension_credit * 0.15)
        quebec_tax = max(0.0, quebec_tax - fiscal.quebec.pension_credit * 0.15)

    # Crédit dividendes admissibles (approx)
    federal_tax = max(0.0, federal_tax - eligible_dividends * fiscal.federal.dividend_credit_rate)
    quebec_tax = max(0.0, quebec_tax - eligible_dividends * fiscal.quebec.dividend_credit_rate)

    net_tax = federal_tax + quebec_tax + oas_clawback
    return TaxResult(
        federal=round(federal_tax, 2),
        provincial=round(quebec_tax, 2),
        credits=round(fiscal.federal.basic_personal_amount + fiscal.quebec.basic_personal_amount, 2),
        net_tax=round(net_tax, 2),
        oas_clawback=round(oas_clawback, 2),
    )

def aggregate_household_taxes(tax_primary: TaxResult, tax_spouse: TaxResult):
    return {
        "federal": round(tax_primary.federal + tax_spouse.federal, 2),
        "provincial": round(tax_primary.provincial + tax_spouse.provincial, 2),
        "net_tax": round(tax_primary.net_tax + tax_spouse.net_tax, 2),
        "oas_clawback_total": round(tax_primary.oas_clawback + tax_spouse.oas_clawback, 2),
    }