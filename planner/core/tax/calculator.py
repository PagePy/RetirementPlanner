"""Calculateur d'impôt combiné fédéral + provincial pour une personne."""
from planner.core.tax.federal import FederalTax
from planner.core.tax.params import load_params
from planner.core.tax.provincial import get_province_tax
from planner.core.tax.types import TaxInput, TaxResult


class TaxCalculator:
    """Calcule l'impôt total d'une personne pour une année et une province.

    Usage:
        calc = TaxCalculator(year=2026, province="QC")
        result = calc.compute(TaxInput(year=2026, age=67, ordinary_income=60000))
    """

    def __init__(self, year: int, province: str = "QC"):
        self.year = year
        self.province = province
        self.federal = FederalTax(year)
        self.provincial = get_province_tax(province, year)
        self._fed_params = load_params(year, "federal")

    def compute(self, inp: TaxInput, _marginal_probe: bool = True) -> TaxResult:
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
        cash_received = (
            inp.ordinary_income + inp.capital_gains
            + inp.eligible_dividends + inp.non_eligible_dividends
        )
        r.after_tax_income = cash_received - r.total_tax
        r.average_rate = (r.total_tax / taxable_income) if taxable_income > 0 else 0.0

        if _marginal_probe:
            probe = TaxInput(
                year=inp.year, age=inp.age,
                ordinary_income=inp.ordinary_income + 100.0,
                eligible_pension_income=inp.eligible_pension_income,
                capital_gains=inp.capital_gains,
                eligible_dividends=inp.eligible_dividends,
                non_eligible_dividends=inp.non_eligible_dividends,
                deductions=inp.deductions,
                lives_alone=inp.lives_alone,
                family_net_income=(
                    inp.family_net_income + 100.0
                    if inp.family_net_income is not None else None
                ),
            )
            probe_result = self.compute(probe, _marginal_probe=False)
            r.marginal_rate = (probe_result.total_tax - r.total_tax) / 100.0

        return r
