"""Analyse successorale — impôt latent au décès et valeur nette de la succession.

Règles de la disposition réputée au décès (sans conjoint survivant):
- REER/CRI/FERR/FRV: la totalité du solde s'ajoute au revenu de la dernière
  déclaration (100% imposable).
- Non-enregistré: le gain latent est réputé réalisé (inclusion 50%).
- CELI/CELIAPP: transmis libres d'impôt.

Avec conjoint survivant, le roulement diffère l'impôt — le simulateur le
gère déjà; cette analyse répond à « que vaudrait la succession si le(s)
décès survenai(en)t à la fin de l'année X? ».
"""
from dataclasses import dataclass

from planner.core.simulation.types import PersonYearResult, HouseholdYearResult
from planner.core.tax import TaxCalculator, TaxInput


@dataclass
class EstateResult:
    year: int
    gross_estate: float
    registered_income_at_death: float
    unrealized_gains: float
    tax_at_death: float
    net_estate: float


def estate_at_death(pr: PersonYearResult, calc: TaxCalculator) -> EstateResult:
    """Succession nette d'une personne si elle décédait à la fin de l'année."""
    registered = pr.bal_reer + pr.bal_cri + pr.bal_ferr + pr.bal_frv
    gains = pr.taxable_unrealized_gain
    gross = pr.wealth
    if registered <= 0 and gains <= 0:
        return EstateResult(pr.year, gross, 0.0, 0.0, 0.0, gross)
    # Dernière déclaration: revenu de l'année + disposition réputée
    inp = TaxInput(
        year=calc.year, age=pr.age,
        ordinary_income=max(0.0, pr.taxable_income) + registered,
        capital_gains=gains,
    )
    total_tax = calc.compute(inp, _marginal_probe=False).total_tax
    # Impôt déjà payé sur le revenu de l'année → impôt marginal du décès
    base_inp = TaxInput(year=calc.year, age=pr.age,
                        ordinary_income=max(0.0, pr.taxable_income))
    base_tax = calc.compute(base_inp, _marginal_probe=False).total_tax
    death_tax = max(0.0, total_tax - base_tax)
    return EstateResult(
        year=pr.year, gross_estate=gross,
        registered_income_at_death=registered, unrealized_gains=gains,
        tax_at_death=death_tax, net_estate=gross - death_tax)


def estate_timeline(results: list[HouseholdYearResult],
                    province: str = "QC") -> list[EstateResult]:
    """Succession nette du MÉNAGE année par année (si tous décédaient).

    Hypothèse: roulement au conjoint au premier décès, donc l'impôt est
    calculé comme si tout le patrimoine était imposé sur une seule
    dernière déclaration (le survivant).
    """
    timeline = []
    for hr in results:
        alive = [p for p in hr.persons if p.alive]
        if not alive:
            break
        calc = TaxCalculator(year=hr.year if hr.year <= 2100 else 2100,
                             province=province)
        registered = sum(p.bal_reer + p.bal_cri + p.bal_ferr + p.bal_frv
                         for p in alive)
        gains = sum(p.taxable_unrealized_gain for p in alive)
        gross = sum(p.wealth for p in alive)
        # Tout imposé sur la déclaration du dernier survivant
        richest = max(alive, key=lambda p: p.taxable_income)
        inp = TaxInput(year=calc.year, age=richest.age,
                       ordinary_income=max(0.0, richest.taxable_income) + registered,
                       capital_gains=gains)
        base = TaxInput(year=calc.year, age=richest.age,
                        ordinary_income=max(0.0, richest.taxable_income))
        death_tax = max(0.0, calc.compute(inp, _marginal_probe=False).total_tax
                        - calc.compute(base, _marginal_probe=False).total_tax)
        timeline.append(EstateResult(
            year=hr.year, gross_estate=gross,
            registered_income_at_death=registered, unrealized_gains=gains,
            tax_at_death=death_tax, net_estate=gross - death_tax))
    return timeline
