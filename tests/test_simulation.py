"""Tests de la simulation ménage synchronisée."""
import pytest

from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)


def single_person(**overrides) -> PersonConfig:
    defaults = dict(
        name="Test", birth_year=1966, retirement_age=65, life_expectancy=90,
        salary=80000.0, rrq_monthly_at_65=1000.0, rrq_start_age=65,
        oas_start_age=65,
        accounts=AccountsConfig(
            reer_balance=400000.0, celi_balance=100000.0, celi_room=7000.0,
            taxable_balance=150000.0, taxable_acb=100000.0),
        contributions=ContributionsConfig(reer_pct=0.10, celi_fixed=7000.0),
    )
    defaults.update(overrides)
    return PersonConfig(**defaults)


def run_single(person=None, **hh_overrides):
    hh_defaults = dict(target_net_income=50000.0)
    hh_defaults.update(hh_overrides)
    hh = HouseholdConfig(persons=[person or single_person()], **hh_defaults)
    sim = HouseholdSimulator(hh, ScenarioConfig(start_year=2026, inflation=0.02))
    return sim.run()


class TestSingle:
    def test_timeline_complete(self):
        results = run_single()
        assert results[0].year == 2026
        assert results[-1].year == 1966 + 90

    def test_phase_accumulation_puis_retraite(self):
        results = run_single()
        by_age = {r.persons[0].age: r.persons[0] for r in results}
        assert not by_age[62].retired and by_age[62].salary > 0
        assert by_age[66].retired and by_age[66].salary == 0

    def test_cible_nette_atteinte_en_retraite(self):
        results = run_single()
        for r in results:
            p = r.persons[0]
            if p.retired and p.wealth > 50000:
                assert r.net_cash >= r.target_net - 5.0, f"année {r.year}"

    def test_conversion_reer_ferr_71_ans(self):
        results = run_single()
        by_age = {r.persons[0].age: r.persons[0] for r in results}
        assert by_age[70].bal_reer > 0
        assert by_age[71].bal_reer == 0.0

    def test_minimum_ferr_respecte_apres_71(self):
        results = run_single()
        for r in results:
            p = r.persons[0]
            if p.age >= 72 and p.bal_ferr > 0:
                assert p.wd_ferr >= p.ferr_min - 0.01

    def test_rrq_ajustee_selon_age_debut(self):
        """RRQ à 60 ans = 64% du montant à 65 (première année comparable)."""
        p60 = single_person(rrq_start_age=60, retirement_age=60)
        p65 = single_person(rrq_start_age=65, retirement_age=60)
        r60 = {r.persons[0].age: r.persons[0] for r in run_single(p60)}
        r65 = {r.persons[0].age: r.persons[0] for r in run_single(p65)}
        # comparer à 65 ans: même année, facteurs 0,64 vs 1,0
        assert r60[65].rrq == pytest.approx(r65[65].rrq * 0.64, rel=0.01)

    def test_celi_jamais_preserve_solde(self):
        person = single_person(accounts=AccountsConfig(
            reer_balance=100000.0, celi_balance=80000.0, taxable_balance=0.0))
        results = run_single(person, celi_strategy="jamais",
                             target_net_income=60000.0)
        for r in results:
            assert r.persons[0].wd_celi == 0.0

    def test_depense_speciale_augmente_cible(self):
        results = run_single(special_expenses={2035: 25000.0})
        r2035 = next(r for r in results if r.year == 2035)
        r2034 = next(r for r in results if r.year == 2034)
        assert r2035.target_net == pytest.approx(r2034.target_net * 1.02 + 25000.0, rel=0.001)

    def test_srg_verse_a_faible_revenu(self):
        pauvre = single_person(
            rrq_monthly_at_65=300.0,
            accounts=AccountsConfig(celi_balance=50000.0),
            contributions=ContributionsConfig())
        results = run_single(pauvre, target_net_income=22000.0)
        retired = [r.persons[0] for r in results if r.persons[0].age in (70, 75)]
        assert all(p.gis > 0 for p in retired)

    def test_pas_de_srg_haut_revenu(self):
        results = run_single(target_net_income=80000.0)
        p70 = next(r.persons[0] for r in results if r.persons[0].age == 70)
        assert p70.gis == 0.0

    def test_gain_capital_au_prorata_du_pbr(self):
        """Les retraits non-enregistrés réalisent un gain partiel, pas 50% forfaitaire."""
        results = run_single(target_net_income=70000.0)
        for r in results:
            p = r.persons[0]
            if p.wd_taxable > 0:
                assert p.wd_taxable_gain < p.wd_taxable


class TestCouple:
    def couple(self, **hh_overrides):
        p1 = single_person(name="P1", birth_year=1964,
                           db_pension=30000.0, db_start_age=65,
                           accounts=AccountsConfig(reer_balance=500000.0))
        p2 = single_person(name="P2", birth_year=1968, salary=50000.0,
                           rrq_monthly_at_65=700.0,
                           accounts=AccountsConfig(celi_balance=150000.0, celi_room=7000.0))
        defaults = dict(target_net_income=70000.0)
        defaults.update(hh_overrides)
        hh = HouseholdConfig(persons=[p1, p2], **defaults)
        return HouseholdSimulator(hh, ScenarioConfig(start_year=2026, inflation=0.02)).run()

    def test_fractionnement_reduit_impot(self):
        """Avec une grosse rente PD chez P1, le fractionnement doit transférer
        du revenu vers P2 (moins imposée)."""
        results = self.couple()
        split_years = [r for r in results
                       if any(p.pension_split_received > 100 for p in r.persons)]
        assert len(split_years) > 0
        # Conservation: ce que P1 cède = ce que P2 reçoit
        for r in split_years:
            assert sum(p.pension_split_received for p in r.persons) == pytest.approx(0.0, abs=0.01)

    def test_cible_menage_commune(self):
        results = self.couple()
        for r in results:
            if all(p.retired for p in r.persons if p.alive) and r.total_wealth > 100000:
                assert r.net_cash >= r.target_net - 5.0, f"année {r.year}"

    def test_deces_premature_roulement(self):
        results = self.couple(premature_death={"person_index": 0, "year": 2040})
        r_before = next(r for r in results if r.year == 2039)
        r_after = next(r for r in results if r.year == 2040)
        assert r_before.persons[0].alive
        assert not r_after.persons[0].alive
        # Le patrimoine du défunt est roulé au survivant (pas perdu)
        assert r_after.persons[1].wealth > r_before.persons[1].wealth * 1.5

    def test_rente_survivant_rrq(self):
        results = self.couple(premature_death={"person_index": 0, "year": 2040})
        # P2 a 72 ans en 2040 → sa RRQ inclut la rente de survivant
        p2_2039 = next(r for r in results if r.year == 2039).persons[1]
        p2_2041 = next(r for r in results if r.year == 2041).persons[1]
        assert p2_2041.rrq > p2_2039.rrq * 1.02 * 1.05  # au-delà de l'indexation

    def test_ages_differents_synchronises(self):
        results = self.couple()
        r0 = results[0]
        assert r0.persons[0].age - r0.persons[1].age == 4
