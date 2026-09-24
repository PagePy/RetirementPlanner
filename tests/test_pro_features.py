"""Tests des fonctions « pro » du moteur: REER de conjoint, partage RRQ, frais,
rendements par phase, crédits (médicaux, dons, maintien à domicile), emploi
post-retraite, année partielle, normes IQPF."""
import pytest

from planner.core.assumptions import load_iqpf, portfolio_return, portfolio_labels
from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)
from planner.core.tax import TaxCalculator, TaxInput

SCEN0 = ScenarioConfig(start_year=2026, inflation=0.0)


def person(**overrides) -> PersonConfig:
    defaults = dict(
        name="T", birth_year=1961, retirement_age=65, life_expectancy=90,
        salary=0.0, rrq_monthly_at_65=800.0,
        accounts=AccountsConfig(reer_balance=300000.0, celi_balance=50000.0),
        contributions=ContributionsConfig())
    defaults.update(overrides)
    return PersonConfig(**defaults)


def run(hh: HouseholdConfig, scen=SCEN0):
    return HouseholdSimulator(hh, scen).run()


# ==================== CRÉDITS FISCAUX ====================

class TestCreditsFiscaux:
    def setup_method(self):
        self.calc = TaxCalculator(2025, "QC")

    def test_frais_medicaux_reduisent_impot(self):
        base = TaxInput(year=2025, age=72, ordinary_income=50000)
        avec = TaxInput(year=2025, age=72, ordinary_income=50000, medical_expenses=6000)
        r0, r1 = self.calc.compute(base), self.calc.compute(avec)
        assert r1.total_tax < r0.total_tax
        # Fédéral: (6000 − min(3%×50000, 2834)) × 14,5% = (6000 − 1500) × 0,145
        assert r1.federal.credits_detail["medical_amount"] == pytest.approx(4500.0)
        # Québec: (6000 − 3%×50000) × 20%
        assert r1.provincial.credits_detail["medical_credit"] == pytest.approx(900.0)

    def test_frais_medicaux_sous_le_seuil_sans_effet(self):
        base = TaxInput(year=2025, age=72, ordinary_income=50000)
        avec = TaxInput(year=2025, age=72, ordinary_income=50000, medical_expenses=1000)
        assert self.calc.compute(avec).total_tax == pytest.approx(
            self.calc.compute(base).total_tax)

    def test_dons_deux_paliers(self):
        r = self.calc.compute(TaxInput(year=2025, age=50, ordinary_income=80000,
                                       donations=1200))
        # Fédéral 200×15% + 1000×29% = 320; QC 200×20% + 1000×24% = 280
        assert r.federal.credits_detail["donation_credit"] == pytest.approx(320.0)
        assert r.provincial.credits_detail["donation_credit"] == pytest.approx(280.0)

    def test_maintien_domicile_remboursable_70_ans(self):
        jeune = TaxInput(year=2025, age=68, ordinary_income=30000,
                         home_support_expenses=10000)
        aine = TaxInput(year=2025, age=72, ordinary_income=30000,
                        home_support_expenses=10000)
        assert self.calc.compute(jeune).refundable_credits == 0.0
        r = self.calc.compute(aine)
        assert r.refundable_credits == pytest.approx(10000 * 0.39)
        assert r.after_tax_income > 30000 - r.total_tax

    def test_maintien_domicile_reduit_haut_revenu(self):
        riche = TaxInput(year=2025, age=75, ordinary_income=120000,
                         home_support_expenses=10000)
        r = self.calc.compute(riche)
        assert r.refundable_credits < 3900.0

    def test_homogeneite_avec_nouveaux_champs(self):
        inp = TaxInput(year=2025, age=72, ordinary_income=60000,
                       medical_expenses=5000, donations=1000,
                       home_support_expenses=8000)
        k = 1.5
        scaled = TaxInput(year=2025, age=72, ordinary_income=60000 * k,
                          medical_expenses=5000 * k, donations=1000 * k,
                          home_support_expenses=8000 * k)
        r0, r1 = self.calc.compute(inp), self.calc.compute(scaled, price_factor=k)
        assert r1.total_tax == pytest.approx(r0.total_tax * k, rel=1e-9)
        assert r1.refundable_credits == pytest.approx(r0.refundable_credits * k, rel=1e-9)


class TestCreditsDansSimulation:
    def test_maintien_domicile_augmente_liquidites(self):
        sans = run(HouseholdConfig(persons=[person(birth_year=1956)],
                                   target_net_income=30000.0))
        avec = run(HouseholdConfig(
            persons=[person(birth_year=1956, home_support_expenses=6000.0)],
            target_net_income=30000.0))
        # Même cible atteinte, mais moins de retraits nécessaires grâce au crédit
        assert avec[0].persons[0].refundable_credits > 2000
        assert avec[0].net_cash == pytest.approx(avec[0].target_net, abs=5.0)
        assert (avec[0].persons[0].wd_reer + avec[0].persons[0].wd_celi
                < sans[0].persons[0].wd_reer + sans[0].persons[0].wd_celi)


# ==================== FRAIS ET PHASES ====================

class TestFraisEtPhases:
    def test_frais_reduisent_le_patrimoine(self):
        sans = run(HouseholdConfig(persons=[person()], target_net_income=30000.0))
        avec = run(HouseholdConfig(
            persons=[person(accounts=AccountsConfig(
                reer_balance=300000.0, celi_balance=50000.0, fee_rate=0.01))],
            target_net_income=30000.0))
        assert avec[0].total_fees == pytest.approx(3500.0)
        assert avec[-1].total_wealth < sans[-1].total_wealth
        assert sum(r.total_fees for r in avec) > 0

    def test_ajustement_retraite_applique_seulement_retraite(self):
        p = person(birth_year=1966, salary=80000.0,
                   accounts=AccountsConfig(reer_balance=100000.0, reer_return=0.05,
                                           retirement_return_delta=-0.02),
                   contributions=ContributionsConfig())
        results = run(HouseholdConfig(persons=[p], target_net_income=0.0))
        by_age = {r.persons[0].age: r.persons[0] for r in results}
        # Accumulation: 5 % plein; retraite: 3 %
        assert by_age[61].bal_reer == pytest.approx(by_age[60].bal_reer * 1.05, rel=1e-6)
        growth_ret = by_age[67].bal_reer / (by_age[66].bal_reer - by_age[67].wd_reer + by_age[67].wd_reer)
        assert growth_ret < 1.05


# ==================== REER DE CONJOINT ====================

class TestReerConjoint:
    def couple(self, spousal_pct=0.10):
        p1 = person(name="Cotisant", birth_year=1970, salary=100000.0,
                    accounts=AccountsConfig(reer_room=50000.0),
                    contributions=ContributionsConfig(spousal_reer_pct=spousal_pct))
        p2 = person(name="Conjoint", birth_year=1970, salary=20000.0,
                    accounts=AccountsConfig(), contributions=ContributionsConfig())
        return HouseholdConfig(persons=[p1, p2], target_net_income=50000.0)

    def test_cotisation_va_dans_reer_du_conjoint(self):
        r0 = run(self.couple())[0]
        p1, p2 = r0.persons
        assert p1.contrib_spousal_reer == pytest.approx(10000.0)
        assert p1.bal_reer == 0.0
        assert p2.bal_reer == pytest.approx(10000.0)

    def test_deduction_chez_le_cotisant(self):
        sans = run(HouseholdConfig(
            persons=[person(birth_year=1970, salary=100000.0,
                            accounts=AccountsConfig(reer_room=50000.0)),
                     person(birth_year=1970, salary=20000.0, accounts=AccountsConfig())],
            target_net_income=50000.0))[0]
        avec = run(self.couple())[0]
        assert avec.persons[0].tax_total < sans.persons[0].tax_total

    def test_attribution_trois_ans(self):
        """Retrait du conjoint dans les 3 ans: revenu réattribué au cotisant."""
        p1 = person(name="Cotisant", birth_year=1970, salary=100000.0,
                    accounts=AccountsConfig(reer_room=50000.0),
                    contributions=ContributionsConfig(spousal_reer_fixed=10000.0))
        p2 = person(name="Conjoint", birth_year=1960, salary=0.0,
                    rrq_monthly_at_65=0.0, oas_start_age=70,
                    accounts=AccountsConfig(reer_balance=100000.0),
                    contributions=ContributionsConfig())
        hh = HouseholdConfig(persons=[p1, p2], target_net_income=150000.0,
                             withdrawal_order=["reer", "celi"])
        r0 = run(hh)[0]
        c, s = r0.persons
        assert s.wd_reer > 10000
        assert s.spousal_attributed == pytest.approx(-10000.0)
        assert c.spousal_attributed == pytest.approx(10000.0)


# ==================== PARTAGE RRQ ====================

class TestPartageRRQ:
    def couple(self, sharing: bool):
        p1 = person(name="A", birth_year=1959, rrq_monthly_at_65=1300.0)
        p2 = person(name="B", birth_year=1959, rrq_monthly_at_65=300.0)
        return HouseholdConfig(persons=[p1, p2], target_net_income=60000.0,
                               rrq_sharing=sharing)

    def test_rentes_egalisees(self):
        r0 = run(self.couple(True))[0]
        a, b = r0.persons
        assert a.rrq == pytest.approx(b.rrq)
        assert a.rrq_shared_delta == pytest.approx(-b.rrq_shared_delta)
        total_sans = sum(p.rrq for p in run(self.couple(False))[0].persons)
        assert a.rrq + b.rrq == pytest.approx(total_sans)

    def test_partage_reduit_ou_egale_impot(self):
        sans = run(self.couple(False))[0].total_tax
        avec = run(self.couple(True))[0].total_tax
        assert avec <= sans + 0.01

    def test_pas_de_partage_avant_60(self):
        p1 = person(name="A", birth_year=1959, rrq_monthly_at_65=1300.0)
        p2 = person(name="B", birth_year=1970, rrq_monthly_at_65=300.0, salary=50000.0)
        r0 = run(HouseholdConfig(persons=[p1, p2], target_net_income=60000.0,
                                 rrq_sharing=True))[0]
        assert r0.persons[0].rrq_shared_delta == 0.0


# ==================== EMPLOI APRÈS RETRAITE / ANNÉE PARTIELLE ====================

class TestEmploiEtAnneePartielle:
    def test_temps_partiel_jusqu_a_l_age(self):
        p = person(part_time_income=15000.0, part_time_until_age=68)
        results = run(HouseholdConfig(persons=[p], target_net_income=40000.0))
        by_age = {r.persons[0].age: r.persons[0] for r in results}
        assert by_age[66].part_time_income == pytest.approx(15000.0)
        assert by_age[68].part_time_income == pytest.approx(15000.0)
        assert by_age[69].part_time_income == 0.0

    def test_temps_partiel_reduit_retraits(self):
        sans = run(HouseholdConfig(persons=[person()], target_net_income=40000.0))[1]
        avec = run(HouseholdConfig(
            persons=[person(part_time_income=15000.0, part_time_until_age=70)],
            target_net_income=40000.0))[1]
        assert avec.persons[0].wd_reer < sans.persons[0].wd_reer

    def test_retraite_en_cours_d_annee(self):
        p = person(birth_year=1961, retirement_age=65, retirement_month=7,
                   salary=60000.0, rrq_monthly_at_65=0.0,
                   contributions=ContributionsConfig(reer_pct=0.10))
        results = run(HouseholdConfig(persons=[p], target_net_income=40000.0))
        r0 = results[0]
        pr = r0.persons[0]
        assert pr.retired
        assert pr.salary == pytest.approx(30000.0)          # 6 mois
        assert pr.contrib_reer == pytest.approx(3000.0)
        assert r0.target_net == pytest.approx(20000.0)      # cible × 6/12
        assert results[1].persons[0].salary == 0.0
        assert results[1].target_net == pytest.approx(40000.0)

    def test_mois_1_equivaut_annee_complete(self):
        base = run(HouseholdConfig(persons=[person()], target_net_income=40000.0))
        m1 = run(HouseholdConfig(persons=[person(retirement_month=1)],
                                 target_net_income=40000.0))
        assert base[0].net_cash == pytest.approx(m1[0].net_cash)
        assert base[-1].total_wealth == pytest.approx(m1[-1].total_wealth)


# ==================== NORMES IQPF ====================

class TestNormesIQPF:
    def test_chargement(self):
        norms = load_iqpf()
        assert norms["inflation"] == pytest.approx(0.021)
        assert set(portfolio_labels()) == {"conservateur", "equilibre", "croissance"}

    def test_rendements_ordonnes(self):
        c, e, g = (portfolio_return(k) for k in ("conservateur", "equilibre", "croissance"))
        assert 0.03 < c < e < g < 0.07

    def test_poids_somment_a_un(self):
        for pf in load_iqpf()["portfolios"].values():
            assert sum(pf["weights"].values()) == pytest.approx(1.0)
