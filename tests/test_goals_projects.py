"""Tests des outils d'objectifs, plans suggérés et projets de vie."""
import pytest

from planner.core.goals import (
    plan_succeeds, required_annual_savings, achievable_retirement_age,
    sustainable_income, optimal_benefit_ages,
    ProfileAnswers, suggest_plan)
from planner.core.projects import (
    compare_down_payment_strategies, retirement_cost_of_project)
from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)


def person(**overrides) -> PersonConfig:
    defaults = dict(
        name="Test", birth_year=1971, retirement_age=65, life_expectancy=88,
        salary=90000.0, rrq_monthly_at_65=1100.0,
        accounts=AccountsConfig(
            reer_balance=350000.0, celi_balance=90000.0, celi_room=7000.0,
            taxable_balance=100000.0, taxable_acb=70000.0),
        contributions=ContributionsConfig(reer_pct=0.10, celi_fixed=7000.0),
    )
    defaults.update(overrides)
    return PersonConfig(**defaults)


SCEN = ScenarioConfig(start_year=2026, inflation=0.02)


def hh(target=50000.0, **overrides) -> HouseholdConfig:
    return HouseholdConfig(persons=[person()], target_net_income=target,
                           **overrides)


# ==================== SOLVEURS ====================

class TestSolvers:
    def test_plan_deja_suffisant_zero_epargne_requise(self):
        assert required_annual_savings(hh(target=40000.0), SCEN) == 0.0

    def test_epargne_requise_pour_plan_serre(self):
        tight = hh(target=78000.0)
        extra = required_annual_savings(tight, SCEN, max_annual=60000.0)
        assert extra is not None and extra > 0
        # Vérification: le plan réussit avec l'épargne trouvée
        from planner.core.goals.solvers import _with_extra_savings, _run
        assert plan_succeeds(_run(_with_extra_savings(tight, extra), SCEN))

    def test_plan_impossible_retourne_none(self):
        impossible = HouseholdConfig(
            persons=[person(salary=30000.0,
                            accounts=AccountsConfig(reer_balance=10000.0),
                            contributions=ContributionsConfig())],
            target_net_income=200000.0)
        assert required_annual_savings(impossible, SCEN, max_annual=20000.0) is None

    def test_age_retraite_atteignable(self):
        age = achievable_retirement_age(hh(target=45000.0), SCEN)
        assert age is not None and 55 <= age <= 65

    def test_age_retraite_plus_tot_si_cible_basse(self):
        age_low = achievable_retirement_age(hh(target=35000.0), SCEN)
        age_high = achievable_retirement_age(hh(target=60000.0), SCEN)
        assert age_low <= age_high

    def test_revenu_soutenable(self):
        income = sustainable_income(hh(), SCEN)
        assert 30000.0 < income < 300000.0
        assert plan_succeeds(HouseholdSimulator(
            HouseholdConfig(persons=[person()], target_net_income=income * 0.98),
            SCEN).run())

    def test_ages_optimaux_rrq_sv(self):
        options = optimal_benefit_ages(hh(target=45000.0), SCEN,
                                       rrq_ages=(60, 65, 70), oas_ages=(65, 70))
        assert len(options) == 6
        best = options[0]
        assert best.success
        # Les succès sont classés par succession nette décroissante
        ok = [o for o in options if o.success]
        estates = [o.final_net_estate for o in ok]
        assert estates == sorted(estates, reverse=True)


# ==================== PLANS SUGGÉRÉS ====================

class TestTemplates:
    def test_jeune_acheteur_celiapp_prioritaire(self):
        s = suggest_plan(ProfileAnswers(age=28, salary=65000.0,
                                        wants_to_buy_home=True))
        assert s.template_name == "jeune_menage_maison"
        assert s.account_priority[0] == "CELIAPP"
        assert len(s.explanations) >= 3

    def test_pre_retraite(self):
        s = suggest_plan(ProfileAnswers(age=57, salary=95000.0, owns_home=True))
        assert s.template_name == "pre_retraite"
        assert s.account_priority[0] == "REER"  # salaire élevé

    def test_retraite_anticipee_taux_eleve(self):
        s = suggest_plan(ProfileAnswers(age=35, salary=120000.0, owns_home=True,
                                        target_retirement_age=52))
        assert s.template_name == "retraite_anticipee"
        assert s.savings_rate >= 0.30

    def test_salaire_modeste_celi_dabord(self):
        s = suggest_plan(ProfileAnswers(age=40, salary=45000.0, owns_home=True))
        assert s.account_priority[0] == "CELI"

    def test_enfants_mention_reee(self):
        s = suggest_plan(ProfileAnswers(age=40, salary=80000.0, owns_home=True,
                                        has_children=True))
        assert any("REEE" in e for e in s.explanations)

    def test_sans_regime_employeur_avertissement(self):
        s = suggest_plan(ProfileAnswers(age=58, salary=80000.0, owns_home=True,
                                        employer_pension=False))
        assert len(s.warnings) > 0


# ==================== PROJETS DE VIE ====================

class TestLifeProjects:
    def test_trois_strategies_mise_de_fonds(self):
        options = compare_down_payment_strategies(
            annual_savings=12000.0, years_to_purchase=5,
            marginal_rate=0.37, couple=False)
        assert len(options) == 3
        names = {o.name for o in options}
        assert names == {"celiapp", "rap", "celiapp_plus_rap"}

    def test_celiapp_aucun_remboursement(self):
        options = compare_down_payment_strategies(12000.0, 5, 0.37)
        celiapp = next(o for o in options if o.name == "celiapp")
        rap = next(o for o in options if o.name == "rap")
        assert celiapp.rap_repayment_annual == 0.0
        assert rap.rap_repayment_annual > 0.0

    def test_couple_double_les_plafonds(self):
        seul = compare_down_payment_strategies(20000.0, 6, 0.37, couple=False)
        couple = compare_down_payment_strategies(20000.0, 6, 0.37, couple=True)
        c_seul = next(o for o in seul if o.name == "celiapp")
        c_couple = next(o for o in couple if o.name == "celiapp")
        assert c_couple.down_payment > c_seul.down_payment

    def test_combinaison_meilleure_ou_egale(self):
        """CELIAPP+RAP domine ou égale les stratégies simples à épargne élevée."""
        options = compare_down_payment_strategies(25000.0, 5, 0.37)
        combo = next(o for o in options if o.name == "celiapp_plus_rap")
        celiapp = next(o for o in options if o.name == "celiapp")
        assert combo.down_payment >= celiapp.down_payment

    def test_cout_retraite_projet(self):
        impact = retirement_cost_of_project(
            hh(target=45000.0), SCEN, "Rénovation cuisine", 2038, 40000.0)
        assert impact.wealth_cost > 40000.0  # coût réel > montant (rendements perdus)
        assert impact.plan_still_succeeds
        assert impact.final_wealth_with < impact.final_wealth_without

    def test_projet_qui_brise_le_plan_detecte(self):
        impact = retirement_cost_of_project(
            HouseholdConfig(persons=[person(
                accounts=AccountsConfig(reer_balance=150000.0))],
                target_net_income=55000.0),
            SCEN, "Chalet", 2040, 300000.0)
        assert not impact.plan_still_succeeds
