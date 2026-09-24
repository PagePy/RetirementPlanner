"""Calculateur d'impôt combiné fédéral + provincial pour une personne."""
from dataclasses import replace

from planner.core.tax.federal import FederalTax
from planner.core.tax.params import load_params
from planner.core.tax.provincial import get_province_tax
from planner.core.tax.types import TaxInput, TaxResult, LevelTaxResult


def _scale_input(inp: TaxInput, k: float) -> TaxInput:
    return replace(
        inp,
        ordinary_income=inp.ordinary_income * k,
        eligible_pension_income=inp.eligible_pension_income * k,
        capital_gains=inp.capital_gains * k,
        eligible_dividends=inp.eligible_dividends * k,
        non_eligible_dividends=inp.non_eligible_dividends * k,
        deductions=inp.deductions * k,
        family_net_income=(inp.family_net_income * k
                           if inp.family_net_income is not None else None),
        medical_expenses=inp.medical_expenses * k,
        donations=inp.donations * k,
        home_support_expenses=inp.home_support_expenses * k,
    )


def _scale_level(lvl: LevelTaxResult, k: float) -> None:
    lvl.gross_tax *= k
    lvl.non_refundable_credits *= k
    lvl.dividend_credits *= k
    lvl.abatement *= k
    lvl.refundable_credits *= k
    lvl.net_tax *= k
    lvl.credits_detail = {
        key: (v if "rate" in key else v * k)
        for key, v in lvl.credits_detail.items()}


def _scale_result(r: TaxResult, k: float) -> TaxResult:
    r.total_income *= k
    r.taxable_income *= k
    r.net_income *= k
    r.total_tax *= k
    r.refundable_credits *= k
    r.after_tax_income *= k
    _scale_level(r.federal, k)
    _scale_level(r.provincial, k)
    return r


class TaxCalculator:
    """Calcule l'impôt total d'une personne pour une année et une province.

    Usage:
        calc = TaxCalculator(year=2026, province="QC")
        result = calc.compute(TaxInput(year=2026, age=67, ordinary_income=60000))

    `price_factor` = niveau des prix de l'année simulée par rapport à l'année
    des barèmes (ex. 1.02**n). Les montants sont déflatés avant le calcul puis
    réinflatés, ce qui équivaut à indexer paliers, crédits et seuils.
    """

    def __init__(self, year: int, province: str = "QC"):
        self.year = year
        self.province = province
        self.federal = FederalTax(year)
        self.provincial = get_province_tax(province, year)
        self._fed_params = load_params(year, "federal")

    def compute(self, inp: TaxInput, _marginal_probe: bool = True,
                price_factor: float = 1.0) -> TaxResult:
        if price_factor != 1.0:
            if price_factor <= 0:
                raise ValueError("price_factor doit être > 0")
            r = self.compute(_scale_input(inp, 1.0 / price_factor), _marginal_probe)
            return _scale_result(r, price_factor)
        fp = self._fed_params
        inclusion = fp["capital_gains_inclusion"]
        div = fp["dividends"]

        grossed_up_eligible = inp.eligible_dividends * (1 + div["eligible"]["gross_up"])
        grossed_up_non_eligible = inp.non_eligible_dividends * (1 + div["non_eligible"]["gross_up"])
        taxable_capital_gains = inp.capital_gains * inclusion

        total_income = (
            inp.ordinary_income
            + taxable_capital_gains
            + grossed_up_eligible
            + grossed_up_non_eligible
        )
        net_income = max(0.0, total_income - inp.deductions)
        taxable_income = net_income  # déductions déjà appliquées

        r = TaxResult(year=self.year, province=self.province)
        r.total_income = total_income
        r.net_income = net_income
        r.taxable_income = taxable_income

        quebec_resident = self.provincial.uses_federal_abatement
        r.federal = self.federal.compute(
            inp, taxable_income, net_income,
            grossed_up_eligible, grossed_up_non_eligible,
            quebec_resident=quebec_resident,
        )
        r.provincial = self.provincial.compute(
            inp, taxable_income, net_income,
            grossed_up_eligible, grossed_up_non_eligible,
        )

        r.total_tax = r.federal.net_tax + r.provincial.net_tax
        r.refundable_credits = r.federal.refundable_credits + r.provincial.refundable_credits
        cash_received = (
            inp.ordinary_income + inp.capital_gains
            + inp.eligible_dividends + inp.non_eligible_dividends
        )
        r.after_tax_income = cash_received - r.total_tax + r.refundable_credits
        r.average_rate = (r.total_tax / taxable_income) if taxable_income > 0 else 0.0

        if _marginal_probe:
            probe = replace(
                inp,
                ordinary_income=inp.ordinary_income + 100.0,
                family_net_income=(
                    inp.family_net_income + 100.0
                    if inp.family_net_income is not None else None
                ),
            )
            probe_result = self.compute(probe, _marginal_probe=False)
            r.marginal_rate = (probe_result.total_tax - r.total_tax) / 100.0

        return r
