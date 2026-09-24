"""Impôt du Québec avec crédits réels (BPA, âge, retraite, personne seule)."""
from planner.core.tax.params import load_params, bracket_tax
from planner.core.tax.provincial import ProvinceTax, register_province
from planner.core.tax.types import TaxInput, LevelTaxResult


@register_province
class QuebecTax(ProvinceTax):
    code = "QC"
    uses_federal_abatement = True

    def __init__(self, year: int):
        self.p = load_params(year, "quebec")

    def compute(self, inp: TaxInput, taxable_income: float, net_income: float,
                grossed_up_eligible: float, grossed_up_non_eligible: float) -> LevelTaxResult:
        p = self.p
        r = LevelTaxResult()
        r.gross_tax = bracket_tax(taxable_income, p["brackets"])
        credit_rate = p["credit_rate"]

        # Crédits des aînés (âge + revenus de retraite + personne seule),
        # réduits ensemble à 18,75% du revenu familial net au-delà du seuil.
        age_amt = p["age_amount"] if inp.age >= p["age_eligibility"] else 0.0
        pension_amt = min(inp.eligible_pension_income, p["pension_amount_max"])
        alone_amt = p["living_alone_amount"] if inp.lives_alone else 0.0
        senior_base = age_amt + pension_amt + alone_amt
        family_income = inp.family_net_income if inp.family_net_income is not None else net_income
        reduction = max(0.0, family_income - p["senior_credits_threshold"]) * p["senior_credits_reduction_rate"]
        senior_amount = max(0.0, senior_base - reduction)

        credit_base = p["bpa"] + senior_amount
        medical_credit = self._medical_credit(inp.medical_expenses, family_income)
        donation_credit = self._donation_credit(inp.donations)
        r.non_refundable_credits = (credit_base * credit_rate
                                    + medical_credit + donation_credit)
        r.refundable_credits = self._home_support_credit(
            inp.age, inp.home_support_expenses, family_income)
        r.credits_detail = {
            "bpa": p["bpa"],
            "senior_amount_before_reduction": senior_base,
            "senior_amount": senior_amount,
            "medical_credit": medical_credit,
            "donation_credit": donation_credit,
            "home_support_credit": r.refundable_credits,
            "credit_rate": credit_rate,
        }

        tax_after_credits = max(0.0, r.gross_tax - r.non_refundable_credits)

        div = p["dividends"]
        r.dividend_credits = (
            grossed_up_eligible * div["eligible"]["credit_rate_on_grossed_up"]
            + grossed_up_non_eligible * div["non_eligible"]["credit_rate_on_grossed_up"]
        )
        r.net_tax = max(0.0, tax_after_credits - r.dividend_credits)
        return r

    # ---------- crédits additionnels ----------
    def _medical_credit(self, medical: float, family_income: float) -> float:
        m = self.p.get("medical")
        if not m or medical <= 0:
            return 0.0
        return max(0.0, medical - family_income * m["threshold_rate"]) * m["credit_rate"]

    def _donation_credit(self, donations: float) -> float:
        d = self.p.get("donations")
        if not d or donations <= 0:
            return 0.0
        first = min(donations, d["first_tier_limit"])
        return first * d["first_tier_rate"] + (donations - first) * d["second_tier_rate"]

    def _home_support_credit(self, age: int, expenses: float,
                             family_income: float) -> float:
        """Crédit remboursable pour maintien à domicile (personne autonome)."""
        h = self.p.get("home_support")
        if not h or expenses <= 0 or age < h["min_age"]:
            return 0.0
        credit = min(expenses, h["max_expenses"]) * h["rate"]
        reduction = max(0.0, family_income - h["reduction_threshold"]) * h["reduction_rate"]
        return max(0.0, credit - reduction)
