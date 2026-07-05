"""Simulations Monte Carlo — probabilité de succès du plan de retraite.

Génère des trajectoires de rendements aléatoires (chocs annuels gaussiens
appliqués à tous les comptes — corrélation parfaite entre comptes, une
simplification documentée; l'allocation d'actifs différenciée viendra
en post-v1) et mesure:
- la probabilité que la cible nette soit atteinte chaque année de retraite;
- la distribution du patrimoine final (percentiles);
- la distribution de l'année du premier manque.
"""
import random
import statistics
from dataclasses import dataclass, replace, field

from planner.core.simulation import (
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)


@dataclass
class MonteCarloResult:
    iterations: int
    success_probability: float
    final_wealth_percentiles: dict[int, float]   # {10: x, 25: x, 50: x, 75: x, 90: x}
    shortfall_years: list[int]                    # année du 1er manque par itération ratée
    mean_final_wealth: float
    mean_lifetime_tax: float


def run_monte_carlo(hh: HouseholdConfig, scen: ScenarioConfig,
                    iterations: int = 200,
                    return_volatility: float = 0.10,
                    tolerance: float = 500.0,
                    seed: int | None = 42) -> MonteCarloResult:
    """Exécute `iterations` simulations avec chocs de rendement aléatoires.

    `return_volatility`: écart-type annuel des chocs (défaut 10 points).
    """
    rng = random.Random(seed)
    start = scen.start_year
    end = scen.end_year or max(p.birth_year + p.life_expectancy for p in hh.persons)

    successes = 0
    finals, taxes, shortfalls = [], [], []
    for _ in range(iterations):
        shocks = {y: rng.gauss(0.0, return_volatility)
                  for y in range(start, end + 1)}
        scen_i = replace(scen, return_delta_by_year=shocks)
        results = HouseholdSimulator(hh, scen_i).run()
        first_shortfall = None
        for r in results:
            retired = any(p.retired for p in r.persons if p.alive)
            if retired and r.target_gap < -tolerance:
                first_shortfall = r.year
                break
        if first_shortfall is None:
            successes += 1
        else:
            shortfalls.append(first_shortfall)
        finals.append(results[-1].total_wealth)
        taxes.append(sum(r.total_tax for r in results))

    finals_sorted = sorted(finals)

    def pct(p: int) -> float:
        idx = min(len(finals_sorted) - 1, int(len(finals_sorted) * p / 100))
        return finals_sorted[idx]

    return MonteCarloResult(
        iterations=iterations,
        success_probability=successes / iterations,
        final_wealth_percentiles={p: pct(p) for p in (10, 25, 50, 75, 90)},
        shortfall_years=sorted(shortfalls),
        mean_final_wealth=statistics.mean(finals),
        mean_lifetime_tax=statistics.mean(taxes))
