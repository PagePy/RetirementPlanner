"""Projets de vie — achat de maison, mariage, auto, rénovations.

Deux outils:
1. Comparateur de stratégies de mise de fonds (CELIAPP vs RAP vs les deux).
2. Coût réel d'un projet en patrimoine retraite: simulation avec/sans le
   projet → différence de patrimoine final et de succession nette.
"""
from dataclasses import dataclass, replace

from planner.core.accounts.params import load_account_params
from planner.core.analysis.succession import estate_timeline
from planner.core.simulation import (
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)


# ==================== MISE DE FONDS: CELIAPP vs RAP ====================

@dataclass
class DownPaymentOption:
    name: str
    description: str
    down_payment: float          # mise de fonds disponible à l'achat
    tax_refunds: float           # remboursements d'impôt générés en chemin
    rap_repayment_annual: float  # remboursement RAP annuel requis après achat
    notes: list[str]


def compare_down_payment_strategies(
        annual_savings: float, years_to_purchase: int,
        marginal_rate: float, annual_return: float = 0.04,
        couple: bool = False, year: int = 2026) -> list[DownPaymentOption]:
    """Compare CELIAPP seul, RAP seul (via REER) et la combinaison.

    Hypothèses: les remboursements d'impôt sont réinvestis dans le même
    véhicule l'année suivante; rendement constant.
    """
    p = load_account_params(year)
    fhsa_annual = p["fhsa"]["annual_limit"] * (2 if couple else 1)
    fhsa_lifetime = p["fhsa"]["lifetime_limit"] * (2 if couple else 1)
    hbp_max = p["hbp"]["max_withdrawal"] * (2 if couple else 1)
    repay_years = p["hbp"]["repayment_years"]

    def accumulate(annual: float, cap_total: float | None) -> tuple[float, float, float]:
        """(valeur finale, total cotisé, remboursements d'impôt cumulés)."""
        balance = contributed = refunds = 0.0
        carry_refund = 0.0
        for _ in range(years_to_purchase):
            room = annual + carry_refund
            if cap_total is not None:
                room = min(room, max(0.0, cap_total - contributed))
            balance = balance * (1 + annual_return) + room
            contributed += room
            refund = room * marginal_rate
            refunds += refund
            carry_refund = refund
        return balance, contributed, refunds

    options = []

    # 1. CELIAPP seul
    celiapp_savings = min(annual_savings, fhsa_annual)
    bal, contrib, refunds = accumulate(celiapp_savings, fhsa_lifetime)
    options.append(DownPaymentOption(
        name="celiapp",
        description="CELIAPP seul" + (" (2 comptes)" if couple else ""),
        down_payment=bal, tax_refunds=refunds, rap_repayment_annual=0.0,
        notes=[
            f"Cotisations déductibles (≈{refunds:,.0f}$ d'impôt récupéré).",
            "Retrait 100% non imposable, AUCUN remboursement requis.",
            f"Plafond: {fhsa_lifetime:,.0f}$ de cotisations à vie.",
        ]))

    # 2. RAP seul (épargne via REER puis retrait RAP)
    bal, contrib, refunds = accumulate(annual_savings, None)
    rap_amount = min(bal, hbp_max)
    options.append(DownPaymentOption(
        name="rap",
        description="RAP seul (épargne REER)" + (" (2 RAP)" if couple else ""),
        down_payment=rap_amount, tax_refunds=refunds,
        rap_repayment_annual=rap_amount / repay_years,
        notes=[
            f"Retrait RAP plafonné à {hbp_max:,.0f}$.",
            f"Remboursement obligatoire: {rap_amount / repay_years:,.0f}$/an "
            f"pendant {repay_years} ans (sinon imposable).",
            "L'argent RAP retourne au REER: il reste dédié à la retraite.",
        ]))

    # 3. Combinaison: CELIAPP au max, surplus au REER pour RAP
    celiapp_part = min(annual_savings, fhsa_annual)
    reer_part = max(0.0, annual_savings - celiapp_part)
    bal_f, _, refunds_f = accumulate(celiapp_part, fhsa_lifetime)
    bal_r, _, refunds_r = accumulate(reer_part, None) if reer_part > 0 else (0.0, 0.0, 0.0)
    rap_part = min(bal_r, hbp_max)
    options.append(DownPaymentOption(
        name="celiapp_plus_rap",
        description="CELIAPP maximisé + RAP sur le surplus",
        down_payment=bal_f + rap_part,
        tax_refunds=refunds_f + refunds_r,
        rap_repayment_annual=rap_part / repay_years if rap_part > 0 else 0.0,
        notes=[
            "Stratégie généralement optimale: le CELIAPP d'abord (aucun "
            "remboursement), le RAP en complément si nécessaire.",
        ]))

    return sorted(options, key=lambda o: -o.down_payment)


# ==================== COÛT RETRAITE D'UN PROJET ====================

@dataclass
class ProjectImpact:
    name: str
    year: int
    amount: float
    final_wealth_without: float
    final_wealth_with: float
    wealth_cost: float          # patrimoine final sacrifié
    net_estate_cost: float      # succession nette sacrifiée
    plan_still_succeeds: bool


def retirement_cost_of_project(hh: HouseholdConfig, scen: ScenarioConfig,
                               name: str, project_year: int,
                               amount: float,
                               tolerance: float = 500.0) -> ProjectImpact:
    """Le « vrai coût » d'un projet: différence de patrimoine final et de
    succession nette entre le plan avec et sans la dépense."""
    base_results = HouseholdSimulator(hh, scen).run()
    expenses = dict(hh.special_expenses)
    expenses[project_year] = expenses.get(project_year, 0.0) + amount
    with_results = HouseholdSimulator(
        replace(hh, special_expenses=expenses), scen).run()

    base_estate = estate_timeline(base_results, hh.province)
    with_estate = estate_timeline(with_results, hh.province)
    still_ok = not any(
        r.target_gap < -tolerance for r in with_results
        if any(p.retired for p in r.persons if p.alive))
    return ProjectImpact(
        name=name, year=project_year, amount=amount,
        final_wealth_without=base_results[-1].total_wealth,
        final_wealth_with=with_results[-1].total_wealth,
        wealth_cost=base_results[-1].total_wealth - with_results[-1].total_wealth,
        net_estate_cost=(base_estate[-1].net_estate - with_estate[-1].net_estate
                         if base_estate and with_estate else 0.0),
        plan_still_succeeds=still_ok)
