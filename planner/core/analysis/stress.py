"""Tests de stress — scénarios adverses prédéfinis appliqués à un plan.

Scénarios:
- Krach boursier: choc de rendement une année donnée (défaut -30%).
- Risque de séquence: mauvais rendements les 5 premières années de retraite.
- Inflation élevée: inflation majorée sur tout l'horizon.
- Longévité: espérance de vie prolongée (défaut +5 ans).
- Décès prématuré d'un conjoint.
"""
from dataclasses import dataclass, replace, field

from planner.core.simulation import (
    HouseholdConfig, ScenarioConfig, HouseholdSimulator, HouseholdYearResult)


@dataclass
class StressOutcome:
    name: str
    description: str
    results: list[HouseholdYearResult]
    success: bool           # cible atteinte (±500$) chaque année de retraite
    first_shortfall_year: int | None
    final_wealth: float
    total_lifetime_tax: float


def _evaluate(name: str, description: str,
              results: list[HouseholdYearResult],
              tolerance: float = 500.0) -> StressOutcome:
    first_shortfall = None
    for r in results:
        retired = any(p.retired for p in r.persons if p.alive)
        if retired and r.target_gap < -tolerance:
            first_shortfall = r.year
            break
    return StressOutcome(
        name=name, description=description, results=results,
        success=first_shortfall is None,
        first_shortfall_year=first_shortfall,
        final_wealth=results[-1].total_wealth,
        total_lifetime_tax=sum(r.total_tax for r in results))


def run_baseline(hh: HouseholdConfig, scen: ScenarioConfig) -> StressOutcome:
    results = HouseholdSimulator(hh, scen).run()
    return _evaluate("baseline", "Scénario de base", results)


def run_market_crash(hh: HouseholdConfig, scen: ScenarioConfig,
                     crash_year: int, magnitude: float = -0.30) -> StressOutcome:
    shocks = dict(scen.return_delta_by_year)
    shocks[crash_year] = shocks.get(crash_year, 0.0) + magnitude
    scen2 = replace(scen, return_delta_by_year=shocks)
    results = HouseholdSimulator(hh, scen2).run()
    return _evaluate("market_crash",
                     f"Krach de {magnitude:.0%} en {crash_year}", results)


def run_sequence_risk(hh: HouseholdConfig, scen: ScenarioConfig,
                      magnitude: float = -0.10, years: int = 5) -> StressOutcome:
    """Mauvais rendements les N premières années de retraite (du plus vieux)."""
    first_retirement = min(p.birth_year + p.retirement_age for p in hh.persons)
    shocks = dict(scen.return_delta_by_year)
    for y in range(first_retirement, first_retirement + years):
        shocks[y] = shocks.get(y, 0.0) + magnitude
    scen2 = replace(scen, return_delta_by_year=shocks)
    results = HouseholdSimulator(hh, scen2).run()
    return _evaluate("sequence_risk",
                     f"{magnitude:.0%}/an pendant les {years} premières années de retraite",
                     results)


def run_high_inflation(hh: HouseholdConfig, scen: ScenarioConfig,
                       extra: float = 0.02) -> StressOutcome:
    scen2 = replace(scen, inflation=scen.inflation + extra)
    results = HouseholdSimulator(hh, scen2).run()
    return _evaluate("high_inflation",
                     f"Inflation à {scen.inflation + extra:.1%}", results)


def run_longevity(hh: HouseholdConfig, scen: ScenarioConfig,
                  extra_years: int = 5) -> StressOutcome:
    persons = [replace(p, life_expectancy=p.life_expectancy + extra_years)
               for p in hh.persons]
    hh2 = replace(hh, persons=persons)
    results = HouseholdSimulator(hh2, scen).run()
    return _evaluate("longevity", f"Espérance de vie +{extra_years} ans", results)


def run_premature_death(hh: HouseholdConfig, scen: ScenarioConfig,
                        person_index: int, death_year: int) -> StressOutcome:
    hh2 = replace(hh, premature_death={"person_index": person_index,
                                       "year": death_year})
    results = HouseholdSimulator(hh2, scen).run()
    name = hh.persons[person_index].name
    return _evaluate("premature_death",
                     f"Décès de {name} en {death_year}", results)


def run_all_stress_tests(hh: HouseholdConfig, scen: ScenarioConfig) -> list[StressOutcome]:
    """Exécute la batterie complète de tests de stress."""
    first_retirement = min(p.birth_year + p.retirement_age for p in hh.persons)
    outcomes = [
        run_baseline(hh, scen),
        run_market_crash(hh, scen, crash_year=first_retirement + 1),
        run_sequence_risk(hh, scen),
        run_high_inflation(hh, scen),
        run_longevity(hh, scen),
    ]
    if hh.is_couple:
        outcomes.append(run_premature_death(
            hh, scen, person_index=0, death_year=first_retirement + 5))
    return outcomes
