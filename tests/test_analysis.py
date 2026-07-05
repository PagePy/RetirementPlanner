"""Tests des analyses: succession, stress, Monte Carlo, stratégies."""
import pytest

from planner.core.analysis import (
    estate_at_death, estate_timeline,
    run_baseline, run_market_crash, run_longevity, run_all_stress_tests,
    run_monte_carlo, compare_strategies)
from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)
from planner.core.simulation.types import PersonYearResult
from planner.core.tax import TaxCalculator


def person(**overrides) -> PersonConfig:
    defaults = dict(
        name="Test", birth_year=1966, retirement_age=65, life_expectancy=88,
        salary=80000.0, rrq_monthly_at_65=1000.0,
        accounts=AccountsConfig(
            reer_balance=500000.0, celi_balance=100000.0, celi_room=7000.0,
            taxable_balance=200000.0, taxable_acb=120000.0),
        contributions=ContributionsConfig(reer_pct=0.10, celi_fixed=7000.0),
    )
    defaults.update(overrides)
    return PersonConfig(**defaults)


def household(target=55000.0, **overrides) -> HouseholdConfig:
    return HouseholdConfig(persons=[person()], target_net_income=target, **overrides)


SCEN = ScenarioConfig(start_year=2026, inflation=0.02)


# ==================== SUCCESSION ====================

class TestSuccession:
    def test_celi_seul_aucun_impot_au_deces(self):
        pr = PersonYearResult(year=2040, age=74, bal_celi=300000.0)
        r = estate_at_death(pr, TaxCalculator(2026, "QC"))
        assert r.tax_at_death == 0.0
        assert r.net_estate == pytest.approx(300000.0)

    def test_reer_impose_au_deces(self):
        pr = PersonYearResult(year=2040, age=74, bal_ferr=400000.0,
                              taxable_income=30000.0)
        r = estate_at_death(pr, TaxCalculator(2026, "QC"))
        assert r.tax_at_death > 100000.0  # ~40-50% marginal sur 400k
        assert r.net_estate == pytest.approx(400000.0 - r.tax_at_death)

    def test_gain_latent_inclus_a_50_pct(self):
        avec_gain = PersonYearResult(year=2040, age=74, bal_taxable=200000.0,
                                     taxable_unrealized_gain=100000.0)
        sans_gain = PersonYearResult(year=2040, age=74, bal_taxable=200000.0,
                                     taxable_unrealized_gain=0.0)
        calc = TaxCalculator(2026, "QC")
        assert estate_at_death(avec_gain, calc).tax_at_death > 0
        assert estate_at_death(sans_gain, calc).tax_at_death == 0.0

    def test_timeline_successorale(self):
        results = HouseholdSimulator(household(), SCEN).run()
        timeline = estate_timeline(results, "QC")
        assert len(timeline) == len(results)
        for e in timeline:
            assert e.net_estate <= e.gross_estate + 0.01


# ==================== STRESS ====================

class TestStress:
    def test_krach_reduit_patrimoine_final(self):
        base = run_baseline(household(), SCEN)
        crash = run_market_crash(household(), SCEN, crash_year=2032)
        assert crash.final_wealth < base.final_wealth

    def test_longevite_prolonge_horizon(self):
        base = run_baseline(household(), SCEN)
        longe = run_longevity(household(), SCEN, extra_years=5)
        assert longe.results[-1].year == base.results[-1].year + 5

    def test_plan_riche_survit_au_krach(self):
        modest = household(target=40000.0)
        crash = run_market_crash(modest, SCEN, crash_year=2032)
        assert crash.success

    def test_batterie_complete_celibataire(self):
        outcomes = run_all_stress_tests(household(), SCEN)
        assert len(outcomes) == 5
        assert outcomes[0].name == "baseline"

    def test_batterie_couple_inclut_deces(self):
        p2 = person(name="P2", birth_year=1968, salary=50000.0)
        hh = HouseholdConfig(persons=[person(), p2], target_net_income=70000.0)
        outcomes = run_all_stress_tests(hh, SCEN)
        assert any(o.name == "premature_death" for o in outcomes)

    def test_echec_detecte_premiere_annee_manque(self):
        """Plan intenable: cible démesurée → échec avec année identifiée."""
        broke = HouseholdConfig(
            persons=[person(accounts=AccountsConfig(reer_balance=50000.0))],
            target_net_income=100000.0)
        out = run_baseline(broke, SCEN)
        assert not out.success
        assert out.first_shortfall_year is not None


# ==================== MONTE CARLO ====================

class TestMonteCarlo:
    def test_sans_volatilite_egale_deterministe(self):
        mc = run_monte_carlo(household(), SCEN, iterations=3,
                             return_volatility=0.0)
        base = run_baseline(household(), SCEN)
        assert mc.final_wealth_percentiles[50] == pytest.approx(base.final_wealth)
        assert mc.success_probability in (0.0, 1.0)

    def test_probabilite_entre_0_et_1(self):
        mc = run_monte_carlo(household(), SCEN, iterations=25,
                             return_volatility=0.12, seed=7)
        assert 0.0 <= mc.success_probability <= 1.0
        assert mc.iterations == 25

    def test_percentiles_ordonnes(self):
        mc = run_monte_carlo(household(), SCEN, iterations=25, seed=7)
        p = mc.final_wealth_percentiles
        assert p[10] <= p[25] <= p[50] <= p[75] <= p[90]

    def test_reproductible_avec_seed(self):
        a = run_monte_carlo(household(), SCEN, iterations=10, seed=99)
        b = run_monte_carlo(household(), SCEN, iterations=10, seed=99)
        assert a.mean_final_wealth == pytest.approx(b.mean_final_wealth)

    def test_plan_pauvre_echoue_souvent(self):
        broke = HouseholdConfig(
            persons=[person(accounts=AccountsConfig(reer_balance=80000.0))],
            target_net_income=90000.0)
        mc = run_monte_carlo(broke, SCEN, iterations=10, seed=1)
        assert mc.success_probability < 0.5
        assert len(mc.shortfall_years) >= 5


# ==================== STRATÉGIES ====================

class TestStrategies:
    def test_cinq_strategies_comparees(self):
        outcomes = compare_strategies(household(), SCEN)
        assert len(outcomes) == 5

    def test_triees_succes_puis_succession(self):
        outcomes = compare_strategies(household(), SCEN)
        ok = [o for o in outcomes if o.success]
        estates = [o.final_net_estate for o in ok]
        assert estates == sorted(estates, reverse=True)

    def test_impots_differents_selon_ordre(self):
        outcomes = compare_strategies(household(), SCEN)
        taxes = {round(o.lifetime_tax) for o in outcomes}
        assert len(taxes) > 1  # les ordres produisent des impôts différents

    def test_celi_jamais_preserve_celi(self):
        outcomes = compare_strategies(household(target=65000.0), SCEN)
        jamais = next(o for o in outcomes if o.celi_strategy == "jamais")
        assert jamais.final_wealth >= 0.0
