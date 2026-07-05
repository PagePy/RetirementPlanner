"""Comparateur de stratégies de décaissement.

Compare des ordres de retrait et stratégies CELI sur:
- l'impôt total à vie (incluant récupération SV);
- la succession nette finale (après impôt latent au décès);
- le respect de la cible.
"""
from dataclasses import dataclass, replace

from planner.core.analysis.succession import estate_timeline
from planner.core.simulation import (
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)

STANDARD_ORDERS = [
    (["taxable", "reer", "ferr", "frv", "celi"], "dernier",
     "Non-enregistré → REER → FERR/FRV → CELI (classique)"),
    (["reer", "taxable", "ferr", "frv", "celi"], "dernier",
     "REER d'abord (vider le REER tôt pour réduire l'impôt successoral)"),
    (["taxable", "ferr", "frv", "reer", "celi"], "dernier",
     "Non-enregistré → FERR/FRV → REER → CELI"),
    (["celi", "taxable", "reer", "ferr", "frv"], "dernier",
     "CELI d'abord (préserver les comptes imposables)"),
    (["taxable", "reer", "ferr", "frv", "celi"], "jamais",
     "CELI jamais touché (100% pour la succession)"),
]


@dataclass
class StrategyOutcome:
    order: list[str]
    celi_strategy: str
    description: str
    lifetime_tax: float
    final_wealth: float
    final_net_estate: float
    success: bool
    years_below_target: int


def compare_strategies(hh: HouseholdConfig, scen: ScenarioConfig,
                       orders: list | None = None,
                       tolerance: float = 500.0) -> list[StrategyOutcome]:
    """Simule chaque stratégie et retourne les résultats triés par
    succession nette finale décroissante (à succès égal)."""
    outcomes = []
    for order, celi_strategy, description in (orders or STANDARD_ORDERS):
        hh_i = replace(hh, withdrawal_order=list(order),
                       celi_strategy=celi_strategy)
        results = HouseholdSimulator(hh_i, scen).run()
        below = sum(
            1 for r in results
            if any(p.retired for p in r.persons if p.alive)
            and r.target_gap < -tolerance)
        estates = estate_timeline(results, province=hh.province)
        outcomes.append(StrategyOutcome(
            order=list(order), celi_strategy=celi_strategy,
            description=description,
            lifetime_tax=sum(r.total_tax for r in results),
            final_wealth=results[-1].total_wealth,
            final_net_estate=estates[-1].net_estate if estates else 0.0,
            success=below == 0,
            years_below_target=below))
    return sorted(outcomes,
                  key=lambda o: (not o.success, -o.final_net_estate))
