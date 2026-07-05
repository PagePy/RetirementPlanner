# services/tax_recalc.py
from services.taxes import compute_taxes_person_qc

def recompute_net_income(income_breakdown, fiscal):
    """
    Recalcule l'impôt et le net (revenu net = revenus imposables ajustés - impôts)
    income_breakdown: dict complet (employment, pension, interest, eligible_dividends, capital_gains, oas, rrq)
    Retourne (tax_result, net_income)
    """
    pension_income_for_credit = income_breakdown.get("pension", 0.0)
    # Ici, le clawback OAS est déjà intégré au key "oas" (net d’OAS).
    tax_res = compute_taxes_person_qc(income_breakdown, fiscal, pension_income_for_credit=pension_income_for_credit, oas_clawback=0.0)
    net_income = (
        income_breakdown.get("employment", 0.0)
        + income_breakdown.get("pension", 0.0)
        + income_breakdown.get("rrq", 0.0)
        + income_breakdown.get("oas", 0.0)
        + income_breakdown.get("interest", 0.0)
        + income_breakdown.get("eligible_dividends", 0.0)
        + 0.5 * income_breakdown.get("capital_gains", 0.0)
        - tax_res.net_tax
    )
    return tax_res, net_income