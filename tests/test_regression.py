"""Tests de non-régression numériques.

Trois ménages de référence, résultats clés figés. Une modification du moteur
qui déplace ces valeurs doit être volontaire: mettre à jour les attentes ici
après avoir validé le changement (lancer avec `-s` pour voir les valeurs).
"""
import pytest

from planner.core.analysis import estate_timeline
from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)

SCEN = ScenarioConfig(start_year=2026, inflation=0.02)
REL = 0.005  # 0,5 %


def _single() -> HouseholdConfig:
    p = PersonConfig(
        name="Solo", birth_year=1966, retirement_age=65, life_expectancy=90,
        salary=80000.0, salary_growth=0.02, rrq_monthly_at_65=1000.0,
        accounts=AccountsConfig(
            reer_balance=400000.0, reer_room=20000.0,
            celi_balance=100000.0, celi_room=7000.0,
            taxable_balance=150000.0, taxable_acb=100000.0),
        contributions=ContributionsConfig(reer_pct=0.10, celi_fixed=7000.0))
    return HouseholdConfig(persons=[p], target_net_income=50000.0)


def _couple_pd() -> HouseholdConfig:
    p1 = PersonConfig(
        name="P1", birth_year=1964, retirement_age=65, life_expectancy=90,
        salary=95000.0, rrq_monthly_at_65=1200.0,
        db_status="active", db_pension=30000.0, db_start_age=65,
        db_normal_age=65, db_indexed=True,
        accounts=AccountsConfig(reer_balance=500000.0, celi_balance=50000.0,
                                celi_room=7000.0),
        contributions=ContributionsConfig(reer_pct=0.05, celi_fixed=7000.0))
    p2 = PersonConfig(
        name="P2", birth_year=1968, retirement_age=65, life_expectancy=92,
        salary=50000.0, rrq_monthly_at_65=700.0,
        accounts=AccountsConfig(celi_balance=150000.0, celi_room=7000.0,
                                cri_balance=120000.0),
        contributions=ContributionsConfig(celi_fixed=7000.0,
                                          dc_employee_pct=0.05, dc_employer_pct=0.05))
    return HouseholdConfig(persons=[p1, p2], target_net_income=70000.0)


def _low_income() -> HouseholdConfig:
    p = PersonConfig(
        name="Modeste", birth_year=1961, retirement_age=65, life_expectancy=90,
        salary=0.0, rrq_monthly_at_65=400.0,
        accounts=AccountsConfig(celi_balance=120000.0, celi_room=7000.0,
                                reer_balance=60000.0),
        contributions=ContributionsConfig())
    return HouseholdConfig(persons=[p], target_net_income=28000.0)


def _summary(hh: HouseholdConfig) -> dict:
    results = HouseholdSimulator(hh, SCEN).run()
    estates = estate_timeline(results, hh.province, SCEN.inflation)
    retired = [r for r in results if any(p.retired for p in r.persons if p.alive)]
    return {
        "impot_total": sum(r.total_tax for r in results),
        "srg_total": sum(p.gis for r in results for p in r.persons),
        "recup_sv": sum(p.oas_clawback for r in results for p in r.persons),
        "patrimoine_final": results[-1].total_wealth,
        "succession_finale": estates[-1].net_estate,
        "annees_deficit": sum(1 for r in retired if r.target_gap < -500),
        "derniere_annee": results[-1].year,
    }


EXPECTED = {
    "single": {
        "impot_total": 335622.94, "srg_total": 25454.98, "recup_sv": 0.0,
        "patrimoine_final": 703594.07, "succession_finale": 659835.62,
        "annees_deficit": 0, "derniere_annee": 2056,
    },
    "couple_pd": {
        # Inclut la rente PD réversible à 60 % versée à P2 après le décès de P1 (2055+).
        "impot_total": 857422.85, "srg_total": 0.0, "recup_sv": 0.0,
        "patrimoine_final": 3114162.71, "succession_finale": 2969087.78,
        "annees_deficit": 0, "derniere_annee": 2060,
    },
    "low_income": {
        "impot_total": 0.0, "srg_total": 331614.29, "recup_sv": 0.0,
        "patrimoine_final": 362810.27, "succession_finale": 362810.27,
        "annees_deficit": 0, "derniere_annee": 2051,
    },
}

CASES = {"single": _single, "couple_pd": _couple_pd, "low_income": _low_income}


@pytest.mark.parametrize("case", sorted(CASES))
def test_valeurs_de_reference(case):
    got = _summary(CASES[case]())
    print(f"\n{case}: " + ", ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}"
                                   for k, v in got.items()))
    exp = EXPECTED[case]
    for key, value in exp.items():
        if isinstance(value, int):
            assert got[key] == value, key
        elif value == 0.0:
            assert got[key] == pytest.approx(0.0, abs=1.0), key
        else:
            assert got[key] == pytest.approx(value, rel=REL), key
