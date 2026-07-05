"""Solveurs d'objectifs de retraite.

Chaque solveur exécute des simulations complètes (moteur fiscal réel,
prestations, fractionnement) et cherche le paramètre demandé:
- épargne annuelle requise pour que le plan réussisse;
- âge de retraite le plus tôt possible;
- revenu net soutenable maximal;
- âges optimaux de début RRQ et SV (critère: succession nette finale).
"""
from dataclasses import dataclass, replace

from planner.core.analysis.succession import estate_timeline
from planner.core.simulation import (
    HouseholdConfig, ScenarioConfig, HouseholdSimulator, HouseholdYearResult)


def plan_succeeds(results: list[HouseholdYearResult],
                  tolerance: float = 500.0) -> bool:
    """Vrai si la cible nette est atteinte (±tolérance) chaque année de retraite."""
    return not any(
        r.target_gap < -tolerance
        for r in results
        if any(p.retired for p in r.persons if p.alive))


def _run(hh: HouseholdConfig, scen: ScenarioConfig) -> list[HouseholdYearResult]:
    return HouseholdSimulator(hh, scen).run()


def _with_extra_savings(hh: HouseholdConfig, extra_annual: float) -> HouseholdConfig:
    """Ajoute une épargne annuelle fixe répartie entre les personnes.

    L'épargne va au non-enregistré (aucun plafond de droits): estimation
    CONSERVATRICE — l'utilisateur qui a des droits CELI/REER disponibles
    fera au moins aussi bien.
    """
    share = extra_annual / len(hh.persons)
    persons = [
        replace(p, contributions=replace(
            p.contributions,
            taxable_fixed=p.contributions.taxable_fixed + share))
        for p in hh.persons]
    return replace(hh, persons=persons)


def required_annual_savings(hh: HouseholdConfig, scen: ScenarioConfig,
                            max_annual: float = 100000.0,
                            precision: float = 250.0) -> float | None:
    """Épargne annuelle ADDITIONNELLE minimale pour que le plan réussisse.

    Retourne 0 si le plan réussit déjà, None si même `max_annual` ne suffit pas.
    """
    if plan_succeeds(_run(hh, scen)):
        return 0.0
    if not plan_succeeds(_run(_with_extra_savings(hh, max_annual), scen)):
        return None
    lo, hi = 0.0, max_annual
    while hi - lo > precision:
        mid = (lo + hi) / 2
        if plan_succeeds(_run(_with_extra_savings(hh, mid), scen)):
            hi = mid
        else:
            lo = mid
    return hi


def achievable_retirement_age(hh: HouseholdConfig, scen: ScenarioConfig,
                              person_index: int = 0,
                              min_age: int = 55, max_age: int = 71) -> int | None:
    """Âge de retraite le plus tôt possible pour la personne donnée
    (les autres paramètres restant constants)."""
    for age in range(min_age, max_age + 1):
        persons = list(hh.persons)
        persons[person_index] = replace(persons[person_index], retirement_age=age)
        if plan_succeeds(_run(replace(hh, persons=persons), scen)):
            return age
    return None


def sustainable_income(hh: HouseholdConfig, scen: ScenarioConfig,
                       max_income: float = 300000.0,
                       precision: float = 500.0) -> float:
    """Revenu net annuel MAXIMAL soutenable (dollars d'aujourd'hui)."""
    lo, hi = 0.0, max_income
    while hi - lo > precision:
        mid = (lo + hi) / 2
        if plan_succeeds(_run(replace(hh, target_net_income=mid), scen)):
            lo = mid
        else:
            hi = mid
    return lo


@dataclass
class BenefitAgeOption:
    rrq_age: int
    oas_age: int
    success: bool
    final_net_estate: float
    lifetime_tax: float


def optimal_benefit_ages(hh: HouseholdConfig, scen: ScenarioConfig,
                         person_index: int = 0,
                         rrq_ages: tuple = (60, 62, 65, 68, 70, 72),
                         oas_ages: tuple = (65, 67, 70)) -> list[BenefitAgeOption]:
    """Compare les combinaisons d'âges de début RRQ/SV.

    Critère de classement: plans réussis d'abord, puis succession nette
    finale décroissante (la valeur laissée après avoir vécu le plan).
    """
    options = []
    for rrq_age in rrq_ages:
        for oas_age in oas_ages:
            persons = list(hh.persons)
            persons[person_index] = replace(
                persons[person_index], rrq_start_age=rrq_age, oas_start_age=oas_age)
            results = _run(replace(hh, persons=persons), scen)
            estates = estate_timeline(results, hh.province)
            options.append(BenefitAgeOption(
                rrq_age=rrq_age, oas_age=oas_age,
                success=plan_succeeds(results),
                final_net_estate=estates[-1].net_estate if estates else 0.0,
                lifetime_tax=sum(r.total_tax for r in results)))
    return sorted(options, key=lambda o: (not o.success, -o.final_net_estate))
