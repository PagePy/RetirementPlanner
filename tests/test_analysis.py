"""Tests des analyses: succession, stress, Monte Carlo, stratégies."""
import pytest

from planner.core.analysis import (
    estate_at_death, estate_timeline,
    run_baseline, run_market_crash, run_longevity, run_all_stress_tests,
    run_monte_carlo, compare_strategies, attribute_taxes, build_tax_sheet, verify)
from planner.core.analysis.tax_attribution import CLAWBACK, DEATH_TAX, SOURCES
from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)
from planner.core.simulation.types import (
    AnnuityConfig, DebtConfig, LifeInsuranceConfig, PersonYearResult,
    RealAssetConfig, VehicleReplacementConfig)
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


# ==================== ATTRIBUTION DE L'IMPÔT ====================

@pytest.fixture(scope="module")
def attribution():
    hh = household()
    results = HouseholdSimulator(hh, SCEN).run()
    estates = estate_timeline(results, hh.province, SCEN.inflation)
    return results, attribute_taxes(results, estates)


class TestTaxAttribution:
    def test_somme_egale_impot_total(self, attribution):
        results, a = attribution
        for i, r in enumerate(results):
            allocated = sum(a.tax_by_year[s][i] for s in SOURCES + [CLAWBACK])
            assert allocated == pytest.approx(r.total_tax, abs=0.01)
        assert a.total_tax == pytest.approx(sum(r.total_tax for r in results))

    def test_emploi_avant_retraite_retraits_apres(self, attribution):
        results, a = attribution
        first = a.years.index(results[0].year)
        assert a.tax_by_year["Emploi et loyers"][first] > 0
        assert a.tax_by_year["Retraits REER/FERR/FRV"][first] == 0
        assert sum(a.tax_by_year["Retraits REER/FERR/FRV"]) > 0

    def test_impot_au_deces_et_parts(self, attribution):
        _, a = attribution
        rows = a.lifetime()
        assert [r["source"] for r in rows] == SOURCES + [CLAWBACK, DEATH_TAX]
        assert a.death_tax > 0  # REER restant à la fin
        assert sum(r["share"] for r in rows) == pytest.approx(1.0)
        assert all(0 <= r["rate"] <= 1 for r in rows if r["rate"] is not None)

    def test_sans_succession(self):
        results = HouseholdSimulator(household(), SCEN).run()
        a = attribute_taxes(results)
        assert a.death_tax == 0.0 and a.death_year is None

    def test_annee_sans_revenu_imposable(self):
        pr = PersonYearResult(year=2030, age=60, alive=True, tax_total=0.0, wd_celi=40000.0)
        from planner.core.simulation.types import HouseholdYearResult
        hr = HouseholdYearResult(year=2030, persons=[pr])
        a = attribute_taxes([hr])
        assert all(v == [0.0] for v in a.tax_by_year.values())


# ==================== FEUILLE D'IMPÔT ====================

class TestTaxSheet:
    def _sheet(self, hh, year_offset):
        results = HouseholdSimulator(hh, SCEN).run()
        hr = results[year_offset]
        return hr, build_tax_sheet(hr, 0, hh.province, SCEN.start_year)

    def test_tranches_reproduisent_impot_brut(self):
        _, s = self._sheet(household(), 10)  # retraité, barèmes indexés
        assert s.price_factor == pytest.approx(1.02 ** 10)
        assert sum(b.tax for b in s.federal.brackets) == pytest.approx(s.federal.gross_tax, abs=1)
        assert sum(b.tax for b in s.provincial.brackets) == pytest.approx(
            s.provincial.gross_tax, abs=1)
        assert sum(b.amount for b in s.federal.brackets) == pytest.approx(s.taxable_income, abs=1)

    def test_totaux_coherents(self):
        hr, s = self._sheet(household(), 10)
        p = hr.persons[0]
        assert s.federal.net_tax + s.provincial.net_tax == pytest.approx(s.total_tax, abs=1)
        assert s.total_tax == pytest.approx(p.tax_total)
        assert s.oas_clawback == p.oas_clawback
        assert s.unexplained_income == pytest.approx(0.0, abs=1)
        assert s.warnings == []

    def test_lignes_de_revenu_pertinentes(self):
        hr, s = self._sheet(household(), 0)  # année de travail
        labels = dict(s.income_lines)
        assert labels["Revenu d'emploi"] == pytest.approx(hr.persons[0].salary)
        assert "Retraits FERR" not in labels
        assert s.deductions > 0  # cotisations REER

    def test_couple_avec_fractionnement(self):
        hh = HouseholdConfig(
            persons=[person(name="A", accounts=AccountsConfig(reer_balance=900000.0)),
                     person(name="B", birth_year=1968, salary=30000.0, accounts=AccountsConfig())],
            target_net_income=70000.0)
        results = HouseholdSimulator(hh, SCEN).run()
        hr = next(r for r in results if abs(r.persons[0].pension_split_received) > 1)
        for i in (0, 1):
            s = build_tax_sheet(hr, i, hh.province, SCEN.start_year)
            assert s.unexplained_income == pytest.approx(0.0, abs=1)
            assert s.total_tax == pytest.approx(hr.persons[i].tax_total)
        assert s.family_net_income is not None

    def test_personne_sans_calcul(self):
        from planner.core.simulation.types import HouseholdYearResult
        hr = HouseholdYearResult(year=2030, persons=[PersonYearResult(year=2030, age=90, alive=False)])
        with pytest.raises(ValueError):
            build_tax_sheet(hr, 0, "QC", 2026)


# ==================== VÉRIFICATION ====================

def _verify(hh, scen=SCEN):
    results = HouseholdSimulator(hh, scen).run()
    estates = estate_timeline(results, hh.province, scen.inflation)
    return results, verify(results, estates, hh, scen)


def _complex_household() -> HouseholdConfig:
    """Couple avec tout ce qui touche aux flux: rente achetée, assurance, chalet
    vendu avec dette liée, véhicules, fonte du REER, partage RRQ, décès prématuré."""
    return HouseholdConfig(
        persons=[
            person(name="A", accounts=AccountsConfig(
                reer_balance=600000.0, celi_balance=80000.0, celi_room=7000.0,
                cri_balance=150000.0, taxable_balance=250000.0, taxable_acb=150000.0,
                fee_rate=0.01, retirement_return_delta=-0.01),
                contributions=ContributionsConfig(reer_pct=0.08, spousal_reer_fixed=3000.0,
                                                  dc_employee_pct=0.05, dc_employer_pct=0.05)),
            person(name="B", birth_year=1969, salary=45000.0, rrq_monthly_at_65=600.0,
                   life_expectancy=92, accounts=AccountsConfig(
                       reer_balance=100000.0, celi_balance=20000.0, celi_room=7000.0),
                   contributions=ContributionsConfig(celi_fixed=7000.0)),
        ],
        target_net_income=75000.0, taxable_income_floor=40000.0, rrq_sharing=True,
        special_expenses={2033: 25000.0},
        debts=[DebtConfig("Hypothèque chalet", 120000.0, 0.05, 15000.0, "hypotheque")],
        real_assets=[RealAssetConfig("Chalet", 350000.0, kind="chalet", cost_base=200000.0,
                                     is_principal_residence=False, sale_year=2038,
                                     linked_debt="Hypothèque chalet")],
        vehicle_plans=[VehicleReplacementConfig(first_year=2034, every_years=10, net_cost=35000.0)],
        annuities=[AnnuityConfig(person_index=0, purchase_year=2036, premium=150000.0,
                                 annual_payment=9000.0, source="reer")],
        life_insurances=[LifeInsuranceConfig(person_index=0, face_amount=200000.0,
                                             annual_premium=2500.0, premium_until_age=75)],
        premature_death={"person_index": 0, "year": 2048},
    )


class TestVerification:
    def test_menage_simple_tout_passe(self):
        results, v = _verify(household())
        assert v.failed_checks == []
        assert len(v.cash_proof) == len(results)
        assert all(r.balanced for r in v.cash_proof)
        assert all(r.consistent for r in v.roll_forward)

    def test_menage_complexe_tout_passe(self):
        results, v = _verify(_complex_household())
        assert v.failed_checks == [], [(c.name, c.failures[:3]) for c in v.failed_checks]
        # Les événements ont bien eu lieu
        assert any(r.transfers < 0 and "rente" in r.note for r in v.roll_forward)
        assert any(r.transfers > 0 and "vente" in r.note for r in v.roll_forward)
        assert any("capital-décès" in r.note for r in v.roll_forward)
        assert any(not hr.persons[0].alive for hr in results)
        assert any(hr.reinvested > 0 for hr in results)

    def test_choc_de_rendement_dans_la_fourchette(self):
        scen = ScenarioConfig(start_year=2026, inflation=0.02,
                              return_delta_by_year={2030: -0.30})
        _, v = _verify(household(), scen)
        krach = [r for r in v.roll_forward if r.year == 2030 and r.group == "REER + FERR"][0]
        assert krach.implied_rate < -0.2 and krach.consistent
        assert v.failed_checks == []

    def test_preuve_de_caisse_detaille_les_flux(self):
        results, v = _verify(household())
        row = next(r for r in v.cash_proof if r.year == 2036)  # retraité
        assert row.inflows["RRQ"] > 0 and row.inflows["SV"] > 0
        assert row.outflows["Impôts"] > 0
        assert row.inflows["Emploi (salaire + temps partiel)"] == 0

    def test_roll_forward_taux_implicite(self):
        results, v = _verify(household())
        first = next(r for r in v.roll_forward if r.year == 2026 and r.group == "CELI")
        assert first.opening == pytest.approx(100000.0)
        assert first.contributions == pytest.approx(7000.0)
        assert first.implied_rate == pytest.approx(0.05, abs=1e-6)

    def test_detecte_resultats_alteres(self):
        hh = household()
        results = HouseholdSimulator(hh, SCEN).run()
        estates = estate_timeline(results, hh.province, SCEN.inflation)
        r = next(r for r in results if r.year == 2040)
        r.net_cash += 1000.0                     # agrégat et preuve de caisse
        r.persons[0].wd_ferr = 0.0               # minimum FERR violé (75 ans)
        r.persons[0].bal_reer = 5000.0           # REER après 71 ans
        r.persons[0].oas_clawback = r.persons[0].oas + 500.0
        v = verify(results, estates, hh, SCEN)
        failed = {c.name for c in v.failed_checks}
        assert {"Agrégats du ménage", "Preuve de caisse", "Minimums FERR / FRV",
                "Conversion à 71 ans", "Récupération de la SV", "Rendement des comptes"} <= failed
        assert any("2040" in f for f in next(
            c for c in v.checks if c.name == "Preuve de caisse").failures)


# ==================== JOURNAL DES DÉCISIONS ====================

class TestJournal:
    def test_journal_simple(self):
        results = HouseholdSimulator(household(), SCEN).run()
        by_year = {r.year: r for r in results}
        assert all(r.decisions for r in results)
        first_retired = next(r for r in results if r.persons[0].retired and r.persons[0].salary == 0)
        text = "\n".join(first_retired.decisions)
        assert "Besoin net de l'année" in text
        assert "ordre de retrait: non-enregistré → REER" in text
        assert "besoin comblé" in text
        at_71 = by_year[1966 + 71]
        assert any("converti en FERR" in d for d in at_71.decisions)
        assert any("retraits minimums obligatoires" in d for d in by_year[1966 + 72].decisions)

    def test_journal_evenements_complexes(self):
        hh = _complex_household()
        results = HouseholdSimulator(hh, SCEN).run()
        text = {r.year: "\n".join(r.decisions) for r in results}
        assert "achat de la rente" in text[2036]
        assert "Vente de « Chalet »" in text[2038] and "gain imposable" in text[2038]
        assert "Décès de A" in text[2048] and "Roulement" in text[2048]
        assert any("Fonte du REER" in t for t in text.values())
        assert any("Fractionnement de pension" in t for t in text.values())
        assert any("Partage RRQ" in t for t in text.values())
        assert any("Surplus de" in t and "réinvesti" in t for t in text.values())

    def test_journal_signale_insuffisance(self):
        hh = household(target=150000.0)
        results = HouseholdSimulator(hh, SCEN).run()
        short = next(r for r in results if r.shortfall_note)
        assert any(d.startswith("⚠️ Cible non atteinte") for d in short.decisions)
        assert any("tout retiré" in d for d in short.decisions)
