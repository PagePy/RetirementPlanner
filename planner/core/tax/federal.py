"""Impôt fédéral canadien avec crédits non remboursables réels."""
from planner.core.tax.params import load_params, bracket_tax
from planner.core.tax.types import TaxInput, LevelTaxResult


class FederalTax:
    def __init__(self, year: int):
        self.p = load_params(year, "federal")

    # ---------- crédits ----------
    def _bpa(self, net_income: float) -> float:
        """Montant personnel de base, réduit progressivement pour hauts revenus."""
        p = self.p
        bpa_max, bpa_min = p["bpa_max"], p["bpa_min"]
        start, end = p["bpa_phaseout_start"], p["bpa_phaseout_end"]
        if net_income <= start:
            return bpa_max
        if net_income >= end:
            return bpa_min
        ratio = (net_income - start) / (end - start)
        return bpa_max - (bpa_max - bpa_min) * ratio

    def _age_amount(self, age: int, net_income: float) -> float:
        """Crédit en raison de l'âge (65+), réduit selon le revenu net."""
        p = self.p
        if age < p["age_eligibility"]:
            return 0.0
        reduction = max(0.0, net_income - p["age_amount_threshold"]) * p["age_amount_reduction_rate"]
        return max(0.0, p["age_amount_max"] - reduction)

    def _pension_amount(self, eligible_pension_income: float) -> float:
        return min(eligible_pension_income, self.p["pension_credit_max"])

    # ---------- calcul ----------
    def compute(self, inp: TaxInput, taxable_income: float, net_income: float,
                grossed_up_eligible: float, grossed_up_non_eligible: float,
                quebec_resident: bool) -> LevelTaxResult:
        p = self.p
        r = LevelTaxResult()
        r.gross_tax = bracket_tax(taxable_income, p["brackets"])

        # Crédits non remboursables au taux du premier palier
        credit_rate = p["credit_rate"]
        bpa = self._bpa(net_income)
        age_amt = self._age_amount(inp.age, net_income)
        pension_amt = self._pension_amount(inp.eligible_pension_income)
        credit_base = bpa + age_amt + pension_amt
        r.non_refundable_credits = credit_base * credit_rate
        r.credits_detail = {
            "bpa": bpa,
            "age_amount": age_amt,
            "pension_amount": pension_amt,
            "credit_rate": credit_rate,
        }

        tax_after_credits = max(0.0, r.gross_tax - r.non_refundable_credits)

        # Crédits d'impôt pour dividendes (sur montants majorés)
        div = p["dividends"]
        r.dividend_credits = (
            grossed_up_eligible * div["eligible"]["credit_rate_on_grossed_up"]
            + grossed_up_non_eligible * div["non_eligible"]["credit_rate_on_grossed_up"]
        )
        tax_after_div = max(0.0, tax_after_credits - r.dividend_credits)

        # Abattement du Québec (16,5% de l'impôt fédéral de base)
        if quebec_resident:
            r.abatement = tax_after_div * p["quebec_abatement"]
        r.net_tax = tax_after_div - r.abatement
        return r
