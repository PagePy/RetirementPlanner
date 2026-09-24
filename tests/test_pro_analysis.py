"""Tests des analyses « pro »: fonte du REER, point mort, longévité, objectif
de succession, immeuble locatif, rentes viagères, assurance vie."""
import pytest

from planner.core.analysis import compare_income_floors, estate_timeline
from planner.core.assets import RealAssetConfig
from planner.core.benefits.breakeven import rrq_breakeven, oas_breakeven, standard_breakevens
from planner.core.goals import financial_capacity
from planner.core.longevity import planning_ages, recommended_age, survival_probability
from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig, HouseholdConfig,
    ScenarioConfig, HouseholdSimulator, AnnuityConfig, LifeInsuranceConfig)

SCEN0 = ScenarioConfig(start_year=2026, inflation=0.0)
SCEN2 = ScenarioConfig(start_year=2026, inflation=0.02)


def person(**overrides) -> PersonConfig:
    defaults = dict(
        name="T", birth_year=1961, retirement_age=65, life_expectancy=90,
        salary=0.0, rrq_monthly_at_65=800.0,
        accounts=AccountsConfig(reer_balance=400000.0, celi_balance=50000.0,
                                celi_room=7000.0),
        contributions=ContributionsConfig())
    defaults.update(overrides)
    return PersonConfig(**defaults)


def run(hh, scen=SCEN0):
    return HouseholdSimulator(hh, scen).run()


# ==================== FONTE DU REER ====================

class TestFonteREER:
    def test_plancher_force_des_retraits_reinvestis(self):
        hh = HouseholdConfig(persons=[person()], target_net_income=30000.0,
                             taxable_income_floor=50000.0)
        r0 = run(hh)[0]
        p = r0.persons[0]
        assert p.meltdown_withdrawal > 0
        assert p.taxable_income == pytest.approx(50000.0, abs=50.0)
        assert r0.reinvested > 0
        assert p.contrib_celi == pytest.approx(7000.0)  # droits CELI utilisés d'abord
        assert r0.net_cash - r0.reinvested == pytest.approx(r0.target_net, abs=5.0)

    def test_sans_plancher_aucun_retrait_volontaire(self):
        r0 = run(HouseholdConfig(persons=[person()], target_net_income=30000.0))[0]
        assert r0.persons[0].meltdown_withdrawal == 0.0

    def test_comparateur_retourne_classement(self):
        hh = HouseholdConfig(persons=[person()], target_net_income=35000.0)
        outcomes = compare_income_floors(hh, SCEN2, floors=(None, 40000.0, 60000.0))
        assert len(outcomes) == 3
        assert outcomes[0].final_net_estate >= outcomes[-1].final_net_estate
        none = next(o for o in outcomes if o.floor is None)
        assert none.total_meltdown == 0.0
        assert all(o.success for o in outcomes)


# ==================== POINT MORT ====================

class TestPointMort:
    def test_rrq_60_vs_65(self):
        b = rrq_breakeven(1000.0, 60, 65, 2026)
        assert b.early_annual == pytest.approx(12000 * 0.64)
        assert b.late_annual == pytest.approx(12000)
        # 0,64×(x−60) = (x−65) → x ≈ 73,9 → rentable dès 74 ans
        assert b.breakeven_age in (73, 74, 75)

    def test_sv_65_vs_70(self):
        b = oas_breakeven(65, 70, 2026)
        assert b.late_annual == pytest.approx(b.early_annual * 1.36, rel=1e-6)
        # 1,36×(x−70) > (x−65) → x > 83,9
        assert b.breakeven_age in (83, 84, 85)

    def test_cumuls_coherents(self):
        b = rrq_breakeven(1000.0, 65, 70, 2026)
        assert b.cumulative_late[0] == 0.0          # rien avant 70
        assert b.cumulative_early[0] == pytest.approx(12000.0)
        assert len(b.cumulative_early) == len(b.cumulative_late)

    def test_standard_sans_rrq(self):
        bes = standard_breakevens(0.0, 2026)
        assert [b.benefit for b in bes] == ["SV"]


# ==================== LONGÉVITÉ ====================

class TestLongevite:
    def test_ages_decroissants_avec_probabilite(self):
        for sex in ("M", "F"):
            ages = planning_ages(sex)
            probs = [a.probability for a in ages]
            assert probs == sorted(probs, reverse=True)
            assert [a.age for a in ages] == sorted(a.age for a in ages)

    def test_femmes_vivent_plus_longtemps(self):
        assert recommended_age("F") > recommended_age("M")

    def test_probabilite_survie_monotone(self):
        probs = [survival_probability("M", a) for a in range(65, 101)]
        assert probs[0] == 1.0
        assert all(a >= b for a, b in zip(probs, probs[1:]))
        assert survival_probability("M", recommended_age("M")) == pytest.approx(0.25)


# ==================== OBJECTIF DE SUCCESSION ====================

class TestObjectifSuccession:
    def test_succession_reduit_capacite(self):
        hh = HouseholdConfig(persons=[person()], target_net_income=30000.0)
        sans = financial_capacity(hh, SCEN0, precision=500.0)
        avec = financial_capacity(hh, SCEN0, precision=500.0, estate_goal=200000.0)
        assert avec.annual_income < sans.annual_income
        results = run(HouseholdConfig(persons=[person()],
                                      target_net_income=avec.annual_income))
        estates = estate_timeline(results, "QC", 0.0)
        assert estates[-1].net_estate >= 200000.0 - 1000.0


# ==================== IMMEUBLE LOCATIF ====================

class TestLocatif:
    def rental(self, cca=0.0, sale_year=None):
        return RealAssetConfig(
            name="Triplex", value=600000.0, kind="immeuble_locatif",
            appreciation=0.0, is_principal_residence=False, cost_base=400000.0,
            net_rental_income=24000.0, cca_rate=cca, sale_year=sale_year)

    def test_loyers_imposables_et_encaisses(self):
        hh = HouseholdConfig(persons=[person()], target_net_income=40000.0,
                             real_assets=[self.rental()])
        r0 = run(hh)[0]
        p = r0.persons[0]
        assert r0.rental_income == pytest.approx(24000.0)
        assert p.rental_income == pytest.approx(24000.0)
        sans = run(HouseholdConfig(persons=[person()], target_net_income=40000.0))[0]
        # Les loyers remplacent des retraits REER (le revenu imposable reste
        # dicté par la cible)
        assert p.wd_reer < sans.persons[0].wd_reer - 15000

    def test_dpa_reduit_le_revenu_imposable(self):
        sans = run(HouseholdConfig(persons=[person()], target_net_income=40000.0,
                                   real_assets=[self.rental()]))[0]
        avec = run(HouseholdConfig(persons=[person()], target_net_income=40000.0,
                                   real_assets=[self.rental(cca=0.04)]))[0]
        # DPA = 4 % × 400 000 = 16 000 (≤ loyers), revenu imposable réduit d'autant
        # (à la marge des retraits recalculés)
        assert avec.persons[0].tax_total < sans.persons[0].tax_total
        assert avec.real_assets_recapture == pytest.approx(16000.0)

    def test_vente_recupere_la_dpa(self):
        hh = HouseholdConfig(persons=[person()], target_net_income=40000.0,
                             real_assets=[self.rental(cca=0.04, sale_year=2028)])
        results = run(hh)
        r_sale = next(r for r in results if r.year == 2028)
        r_prev = next(r for r in results if r.year == 2027)
        assert r_sale.asset_sale_proceeds == pytest.approx(600000.0)
        # Récupération (3 ans de DPA) + gain de 200 000 imposé → gros impôt cette année
        assert r_sale.persons[0].tax_total > r_prev.persons[0].tax_total * 3
        assert r_sale.real_assets_recapture == 0.0
        assert results[-1].rental_income == 0.0

    def test_couple_partage_les_loyers(self):
        p2 = person(name="B")
        hh = HouseholdConfig(persons=[person(), p2], target_net_income=60000.0,
                             real_assets=[self.rental()])
        r0 = run(hh)[0]
        assert r0.persons[0].rental_income == pytest.approx(12000.0)
        assert r0.persons[1].rental_income == pytest.approx(12000.0)


# ==================== RENTES VIAGÈRES ====================

class TestRenteViagere:
    def test_rente_reer_retire_le_capital_et_verse_imposable(self):
        ann = AnnuityConfig(person_index=0, purchase_year=2028, premium=100000.0,
                            annual_payment=6500.0, source="reer")
        hh = HouseholdConfig(persons=[person()], target_net_income=30000.0,
                             annuities=[ann])
        results = run(hh)
        sans = run(HouseholdConfig(persons=[person()], target_net_income=30000.0))
        r27, r28 = results[1], results[2]
        s27, s28 = sans[1], sans[2]
        assert r27.persons[0].annuity_income == 0.0
        assert r28.persons[0].annuity_income == pytest.approx(6500.0)
        # Le REER a perdu ~100 000 de plus que sans rente (avant retraits)
        assert s28.persons[0].bal_reer - r28.persons[0].bal_reer > 80000
        assert r28.persons[0].wd_reer < s28.persons[0].wd_reer
        assert results[-1].persons[0].annuity_income == pytest.approx(6500.0)

    def test_rente_celi_non_imposable(self):
        ann = AnnuityConfig(person_index=0, purchase_year=2026, premium=40000.0,
                            annual_payment=2600.0, source="celi")
        hh = HouseholdConfig(persons=[person()], target_net_income=30000.0,
                             annuities=[ann])
        r0 = run(hh)[0]
        sans = run(HouseholdConfig(persons=[person()], target_net_income=30000.0))[0]
        assert r0.persons[0].annuity_income == pytest.approx(2600.0)
        # Retraits REER réduits de ~2 600 sans hausse du revenu imposable
        assert r0.persons[0].taxable_income < sans.persons[0].taxable_income

    def test_rente_indexee(self):
        ann = AnnuityConfig(person_index=0, purchase_year=2026, premium=100000.0,
                            annual_payment=6000.0, source="reer", indexed=True)
        hh = HouseholdConfig(persons=[person()], target_net_income=30000.0,
                             annuities=[ann])
        results = run(hh, SCEN2)
        assert results[5].persons[0].annuity_income == pytest.approx(6000.0 * 1.02 ** 5)


# ==================== ASSURANCE VIE ====================

class TestAssuranceVie:
    def couple(self, insured=True):
        p1 = person(name="A", birth_year=1961, life_expectancy=70)
        p2 = person(name="B", birth_year=1961, life_expectancy=90,
                    accounts=AccountsConfig(celi_balance=50000.0))
        ins = [LifeInsuranceConfig(person_index=0, face_amount=300000.0,
                                   annual_premium=3000.0)] if insured else []
        return HouseholdConfig(persons=[p1, p2], target_net_income=50000.0,
                               life_insurances=ins)

    def test_prime_augmente_la_cible(self):
        avec = run(self.couple())[0]
        sans = run(self.couple(False))[0]
        assert avec.insurance_premiums == pytest.approx(3000.0)
        assert avec.target_net == pytest.approx(sans.target_net + 3000.0)

    def test_capital_deces_verse_au_survivant(self):
        results = run(self.couple())
        death_year = next(r for r in results if not r.persons[0].alive)
        assert death_year.insurance_payout == pytest.approx(300000.0)
        before = next(r for r in results if r.year == death_year.year - 1)
        assert death_year.persons[1].bal_taxable > before.persons[1].bal_taxable + 250000
        assert death_year.insurance_premiums == 0.0  # plus de prime après le décès

    def test_succession_inclut_le_capital_en_vigueur(self):
        results = run(self.couple())
        estates = estate_timeline(results, "QC", 0.0)
        r0 = results[0]
        assert r0.insurance_in_force == pytest.approx(300000.0)
        sans = estate_timeline(run(self.couple(False)), "QC", 0.0)
        assert estates[0].net_estate > sans[0].net_estate + 250000

    def test_temporaire_expire(self):
        p1 = person(name="A", birth_year=1961, life_expectancy=90)
        ins = LifeInsuranceConfig(person_index=0, face_amount=100000.0,
                                  annual_premium=1000.0, coverage_until_age=70)
        results = run(HouseholdConfig(persons=[p1], target_net_income=30000.0,
                                      life_insurances=[ins]))
        by_age = {r.persons[0].age: r for r in results}
        assert by_age[70].insurance_in_force == pytest.approx(100000.0)
        assert by_age[71].insurance_in_force == 0.0
        assert by_age[71].insurance_premiums == 0.0
