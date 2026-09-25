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

    def test_srg_compte_dans_la_cible(self):
        """Le SRG est un revenu disponible: les retraits CELI diminuent d'autant
        et rien n'est retiré pour être aussitôt réinvesti."""
        pauvre = single_person(
            rrq_monthly_at_65=300.0,
            accounts=AccountsConfig(celi_balance=400000.0, celi_room=7000.0),
            contributions=ContributionsConfig())
        results = run_single(pauvre, target_net_income=30000.0)
        r = next(r for r in results if r.persons[0].age == 70)
        p = r.persons[0]
        assert p.gis > 1000
        assert r.net_cash == pytest.approx(r.target_net, abs=5.0)
        assert r.reinvested == 0.0
        assert p.wd_celi == pytest.approx(
            r.target_net - p.rrq - p.oas - p.gis + p.tax_total, abs=5.0)

    def test_gain_capital_au_prorata_du_pbr(self):
        """Les retraits non-enregistrés réalisent un gain partiel, pas 50% forfaitaire."""
        results = run_single(target_net_income=70000.0)
        for r in results:
            p = r.persons[0]
            if p.wd_taxable > 0:
                assert p.wd_taxable_gain < p.wd_taxable

    def test_aucun_pd_donne_rente_nulle(self):
        person = single_person(
            db_status="none",
            db_pension=25000.0,
            retirement_age=65,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        results = run_single(person)
        p65 = next(r.persons[0] for r in results if r.persons[0].age == 65)
        assert p65.db_pension == 0.0

    def test_pd_actif_croit_avec_salaire_avant_debut(self):
        person = single_person(
            db_status="active",
            db_pension=20000.0,
            db_start_age=65,
            db_normal_age=65,
            db_indexed=False,
            salary_growth=0.02,
            db_active_growth=0.02,
            retirement_age=65,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        results = run_single(person)
        p65 = next(r.persons[0] for r in results if r.persons[0].age == 65)
        assert p65.db_pension == pytest.approx(20000.0 * (1.02 ** 5), rel=0.001)

    def test_pd_ferme_emploi_actif_suit_croissance_salaire(self):
        active = single_person(
            db_status="active",
            db_pension=18000.0,
            db_start_age=65,
            db_normal_age=65,
            db_indexed=False,
            salary_growth=0.03,
            retirement_age=65,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        closed = single_person(
            db_status="closed_salary_linked",
            db_pension=18000.0,
            db_start_age=65,
            db_normal_age=65,
            db_indexed=False,
            salary_growth=0.03,
            retirement_age=65,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        r_active = next(r.persons[0] for r in run_single(active) if r.persons[0].age == 65)
        r_closed = next(r.persons[0] for r in run_single(closed) if r.persons[0].age == 65)
        assert r_active.db_pension == pytest.approx(18000.0 * (1.02 ** 5), rel=0.001)
        assert r_closed.db_pension == pytest.approx(18000.0 * (1.03 ** 5), rel=0.001)

    def test_pd_actif_cesse_de_croitre_a_la_retraite(self):
        person = single_person(
            db_status="active", db_pension=20000.0,
            db_start_age=65, db_normal_age=65, db_indexed=False,
            db_active_growth=0.02, retirement_age=62,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        p65 = next(r.persons[0] for r in run_single(person) if r.persons[0].age == 65)
        assert p65.db_pension == pytest.approx(20000.0 * (1.02 ** 2), rel=0.001)

    def test_pd_ferme_cesse_de_croitre_a_la_retraite(self):
        person = single_person(
            db_status="closed_salary_linked", db_pension=18000.0,
            db_start_age=65, db_normal_age=65, db_indexed=False,
            salary_growth=0.03, retirement_age=62,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        p65 = next(r.persons[0] for r in run_single(person) if r.persons[0].age == 65)
        assert p65.db_pension == pytest.approx(18000.0 * (1.03 ** 2), rel=0.001)

    def test_pd_croissance_au_prorata_du_mois_de_retraite(self):
        person = single_person(
            db_status="active", db_pension=20000.0,
            db_start_age=65, db_normal_age=65, db_indexed=False,
            db_active_growth=0.02, retirement_age=62, retirement_month=7,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        p65 = next(r.persons[0] for r in run_single(person) if r.persons[0].age == 65)
        assert p65.db_pension == pytest.approx(20000.0 * (1.02 ** 2.5), rel=0.001)

    def test_pd_differe_reste_gele_jusqu_au_debut(self):
        person = single_person(
            db_status="deferred", db_pension=18000.0,
            db_start_age=65, db_normal_age=65, db_indexed=False,
            salary_growth=0.03, retirement_age=65,
            accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        p65 = next(r.persons[0] for r in run_single(person) if r.persons[0].age == 65)
        assert p65.db_pension == pytest.approx(18000.0)

    def test_pd_en_paiement_utilise_montant_courant(self):
        person = single_person(
            db_status="in_payment", db_pension=18000.0,
            db_start_age=65, db_normal_age=65, db_indexed=False,
            retirement_age=60, accounts=AccountsConfig(celi_balance=10000.0),
            contributions=ContributionsConfig(),
        )
        p62 = next(r.persons[0] for r in run_single(person) if r.persons[0].age == 62)
        assert p62.db_pension == pytest.approx(18000.0)

    def test_cd_desactive_aucun_effet_cri(self):
        person = single_person(
            retirement_age=80,
            accounts=AccountsConfig(cri_balance=0.0, cri_return=0.0),
            contributions=ContributionsConfig(),
        )
        results = run_single(person)
        p0 = next(r.persons[0] for r in results if r.year == 2026)
        assert p0.bal_cri == 0.0

    def test_cd_employe_pct_suit_croissance_salaire(self):
        person = single_person(
            retirement_age=80,
            salary=100000.0,
            salary_growth=0.10,
            accounts=AccountsConfig(cri_balance=0.0, cri_return=0.0),
            contributions=ContributionsConfig(dc_employee_pct=0.10),
        )
        results = run_single(person)
        p2026 = next(r.persons[0] for r in results if r.year == 2026)
        p2027 = next(r.persons[0] for r in results if r.year == 2027)
        assert p2026.bal_cri == pytest.approx(10000.0, rel=0.001)
        assert p2027.bal_cri == pytest.approx(21000.0, rel=0.001)

    def test_cd_employeur_fixe_augmente_cri_sans_baisser_cash(self):
        base = single_person(
            retirement_age=80,
            salary=90000.0,
            accounts=AccountsConfig(cri_balance=0.0, cri_return=0.0),
            contributions=ContributionsConfig(),
        )
        emp = single_person(
            retirement_age=80,
            salary=90000.0,
            accounts=AccountsConfig(cri_balance=0.0, cri_return=0.0),
            contributions=ContributionsConfig(dc_employer_fixed=5000.0),
        )
        r_base = next(r.persons[0] for r in run_single(base) if r.year == 2026)
        r_emp = next(r.persons[0] for r in run_single(emp) if r.year == 2026)
        assert r_emp.bal_cri == pytest.approx(r_base.bal_cri + 5000.0, rel=0.001)
        assert r_emp.net_cash == pytest.approx(r_base.net_cash, rel=0.001)

    def test_cd_employe_fixe_baisse_cash(self):
        base = single_person(
            retirement_age=80,
            salary=90000.0,
            accounts=AccountsConfig(cri_balance=0.0, cri_return=0.0),
            contributions=ContributionsConfig(),
        )
        emp = single_person(
            retirement_age=80,
            salary=90000.0,
            accounts=AccountsConfig(cri_balance=0.0, cri_return=0.0),
            contributions=ContributionsConfig(dc_employee_fixed=5000.0),
        )
        r_base = next(r.persons[0] for r in run_single(base) if r.year == 2026)
        r_emp = next(r.persons[0] for r in run_single(emp) if r.year == 2026)
        assert r_emp.bal_cri == pytest.approx(r_base.bal_cri + 5000.0, rel=0.001)
        assert r_emp.net_cash == pytest.approx(r_base.net_cash - 5000.0, rel=0.001)

    def test_cd_combinaison_pct_et_fixe(self):
        person = single_person(
            retirement_age=80,
            salary=100000.0,
            salary_growth=0.0,
            accounts=AccountsConfig(cri_balance=0.0, cri_return=0.0),
            contributions=ContributionsConfig(
                dc_employee_pct=0.05,
                dc_employee_fixed=2000.0,
                dc_employer_pct=0.04,
                dc_employer_fixed=1000.0,
            ),
        )
        p0 = next(r.persons[0] for r in run_single(person) if r.year == 2026)
        # 5 000 + 2 000 + 4 000 + 1 000
        assert p0.bal_cri == pytest.approx(12000.0, rel=0.001)

    def test_conversion_cri_frv_inchangee_apres_cotisations_cd(self):
        person = single_person(
            birth_year=1955,  # age 71 en 2026
            retirement_age=80,
            salary=100000.0,
            accounts=AccountsConfig(
                cri_balance=10000.0,
                cri_return=0.0,
                frv_balance=0.0,
                frv_return=0.0,
            ),
            contributions=ContributionsConfig(dc_employee_fixed=5000.0),
        )
        p0 = next(r.persons[0] for r in run_single(person) if r.year == 2026)
        # conversion en début d'année (10 000), puis cotisation CD dans le CRI (5 000)
        assert p0.bal_frv == pytest.approx(10000.0, rel=0.001)
        assert p0.bal_cri == pytest.approx(5000.0, rel=0.001)


def _statement_person(**overrides) -> PersonConfig:
    """Née en 1966 (60 ans en 2026), retraite en janvier 2031, relevé: 10 ans de service."""
    defaults = dict(
        db_status="active", db_pension=0.0, db_start_age=65, db_normal_age=65,
        db_indexed=False, salary=100000.0, salary_growth=0.03, retirement_age=65,
        db_service_years=10.0, db_avg_salary=90000.0,
        accounts=AccountsConfig(celi_balance=10000.0),
        contributions=ContributionsConfig(),
    )
    defaults.update(overrides)
    return single_person(**defaults)


def _pd_at(person: PersonConfig, age: int) -> float:
    return next(r.persons[0] for r in run_single(person)
                if r.persons[0].age == age).db_pension


def _avg(values) -> float:
    values = list(values)
    return sum(values) / len(values)


class TestPDReleve:
    AVG_2028_2030 = _avg(100000.0 * 1.03 ** k for k in (2, 3, 4))
    MGA_2028_2030 = _avg(74600.0 * 1.02 ** k for k in (2, 3, 4))

    def test_formule_service_taux_moyenne_3_dernieres_annees(self):
        assert _pd_at(_statement_person(), 65) == pytest.approx(
            0.02 * 15 * self.AVG_2028_2030, rel=1e-6)

    def test_moyenne_sur_5_ans(self):
        avg5 = _avg(100000.0 * 1.03 ** k for k in range(5))
        assert _pd_at(_statement_person(db_avg_years=5), 65) == pytest.approx(
            0.02 * 15 * avg5, rel=1e-6)

    def test_service_plafonne(self):
        person = _statement_person(db_service_years=33.0, db_max_service=35.0)
        assert _pd_at(person, 65) == pytest.approx(0.02 * 35 * self.AVG_2028_2030, rel=1e-6)

    def test_service_au_prorata_du_mois_de_retraite(self):
        # Retraite en juillet 2028: 2,5 ans de service de plus, fenêtre 2025-2027
        person = _statement_person(retirement_age=62, retirement_month=7)
        avg = _avg(100000.0 * 1.03 ** k for k in (-1, 0, 1))
        assert _pd_at(person, 65) == pytest.approx(0.02 * 12.5 * avg, rel=1e-6)

    def test_retraite_immediate_utilise_moyenne_du_releve(self):
        person = _statement_person(retirement_age=60)
        assert _pd_at(person, 65) == pytest.approx(0.02 * 10 * 90000.0, rel=1e-6)

    def test_penalite_anticipee_appliquee(self):
        person = _statement_person(db_normal_age=67, db_penalty_per_year=0.04)
        assert _pd_at(person, 65) == pytest.approx(
            0.02 * 15 * self.AVG_2028_2030 * (1 - 2 * 0.04), rel=1e-6)

    def test_coordination_taux_reduit_sous_mga(self):
        person = _statement_person(db_coordination="step")
        expected = 15 * (0.015 * self.MGA_2028_2030
                         + 0.02 * (self.AVG_2028_2030 - self.MGA_2028_2030))
        assert _pd_at(person, 65) == pytest.approx(expected, rel=1e-6)

    def test_coordination_reduction_a_65_ans(self):
        # Retraite et début à 62 ans (2028): fenêtre 2025-2027, service 12
        person = _statement_person(db_coordination="bridge", retirement_age=62,
                                   db_start_age=62, db_normal_age=62)
        avg = _avg(100000.0 * 1.03 ** k for k in (-1, 0, 1))
        mga = _avg(74600.0 * 1.02 ** k for k in (-1, 0, 1))
        full = 0.02 * 12 * avg
        assert _pd_at(person, 64) == pytest.approx(full, rel=1e-6)
        assert _pd_at(person, 65) == pytest.approx(full - 0.007 * 12 * mga, rel=1e-6)

    def test_releve_vide_garde_ancien_calcul(self):
        person = _statement_person(db_service_years=0.0, db_pension=20000.0,
                                   db_active_growth=0.02)
        assert _pd_at(person, 65) == pytest.approx(20000.0 * 1.02 ** 5, rel=1e-6)

    def test_releve_ignore_si_statut_ferme(self):
        person = _statement_person(db_status="closed_salary_linked", db_pension=18000.0)
        assert _pd_at(person, 65) == pytest.approx(18000.0 * 1.03 ** 5, rel=1e-6)

    def test_mois_travailles_l_annee_du_debut_ajoutes_au_service(self):
        person = _statement_person(retirement_month=7)
        assert _pd_at(person, 65) == pytest.approx(0.02 * 15.5 * self.AVG_2028_2030 * 0.5,
                                                   rel=1e-6)
        assert _pd_at(person, 66) == pytest.approx(0.02 * 15.5 * self.AVG_2028_2030, rel=1e-6)


def _by_age(person: PersonConfig) -> dict:
    return {r.persons[0].age: r.persons[0] for r in run_single(person)}


class TestMoisDeNaissance:
    """Née en juin 1966: retraite, RRQ, SV et PD débutent le 1er juillet."""

    def test_retraite_le_mois_suivant_l_anniversaire(self):
        p = _by_age(single_person(birth_month=6))
        assert p[65].salary == pytest.approx(p[64].salary * 1.02 * 6 / 12, rel=1e-6)
        assert p[66].salary == 0.0

    def test_mois_de_depart_choisi_remplace_l_anniversaire(self):
        p = _by_age(single_person(birth_month=6, retirement_month=10))
        assert p[65].salary == pytest.approx(p[64].salary * 1.02 * 9 / 12, rel=1e-6)
        p = _by_age(single_person(birth_month=6, retirement_month=1))
        assert p[65].salary == 0.0

    def test_rente_pd_debute_au_mois_de_depart_choisi(self):
        person = _statement_person(birth_month=6, retirement_month=10)
        avg = TestPDReleve.AVG_2028_2030
        assert _pd_at(person, 65) == pytest.approx(0.02 * 15.75 * avg * 3 / 12, rel=1e-6)
        assert _pd_at(person, 66) == pytest.approx(0.02 * 15.75 * avg, rel=1e-6)

    def test_anniversaire_en_decembre_travaille_toute_l_annee(self):
        p = _by_age(single_person(birth_month=12))
        assert p[65].salary == pytest.approx(p[64].salary * 1.02, rel=1e-6)
        assert p[66].salary == 0.0

    def test_premiere_annee_rrq_et_sv_au_prorata(self):
        p = _by_age(single_person(birth_month=9, retirement_age=62))
        assert p[65].rrq == pytest.approx(p[66].rrq / 1.02 * 3 / 12, rel=1e-6)
        assert p[65].oas == pytest.approx(p[66].oas / 1.02 * 3 / 12, rel=1e-6)

    def test_sans_mois_de_naissance_rrq_complete_des_janvier(self):
        p = _by_age(single_person(retirement_age=62))
        assert p[65].rrq == pytest.approx(p[66].rrq / 1.02, rel=1e-6)

    def test_rente_pd_releve_avec_mois_de_naissance(self):
        person = _statement_person(birth_month=6)
        avg = TestPDReleve.AVG_2028_2030
        assert _pd_at(person, 65) == pytest.approx(0.02 * 15.5 * avg * 0.5, rel=1e-6)
        assert _pd_at(person, 66) == pytest.approx(0.02 * 15.5 * avg, rel=1e-6)

    def test_rente_pd_debut_apres_retraite_versee_des_juillet(self):
        person = _statement_person(birth_month=6, retirement_age=62)
        avg = _avg(100000.0 * 1.03 ** k for k in (-1, 0, 1))
        assert _pd_at(person, 65) == pytest.approx(0.02 * 12.5 * avg * 0.5, rel=1e-6)
        assert _pd_at(person, 66) == pytest.approx(0.02 * 12.5 * avg, rel=1e-6)


class TestCotisationsCELI:
    @staticmethod
    def _worker(**contrib) -> PersonConfig:
        return single_person(
            birth_year=1990, retirement_age=65,
            accounts=AccountsConfig(celi_room=10000.0),
            contributions=ContributionsConfig(**contrib))

    def _by_year(self, person):
        return {r.year: r.persons[0] for r in run_single(person)}

    def test_droits_saisis_non_doubles_annee_depart(self):
        by_year = self._by_year(self._worker(celi_fixed=20000.0,
                                             celi_overflow_to_taxable=False))
        assert by_year[2026].contrib_celi == pytest.approx(10000.0)
        assert by_year[2027].contrib_celi == pytest.approx(7000.0)

    def test_excedent_vers_non_enregistre(self):
        by_year = self._by_year(self._worker(celi_fixed=12000.0))
        assert by_year[2026].contrib_celi == pytest.approx(10000.0)
        assert by_year[2026].contrib_taxable == pytest.approx(2000.0)

    def test_excedent_non_redirige_si_option_desactivee(self):
        by_year = self._by_year(self._worker(celi_fixed=12000.0,
                                             celi_overflow_to_taxable=False))
        assert by_year[2026].contrib_taxable == 0.0

    def test_montant_fixe_indexe(self):
        by_year = self._by_year(self._worker(celi_fixed=5000.0,
                                             celi_fixed_indexed=True))
        assert by_year[2026].contrib_celi == pytest.approx(5000.0)
        assert by_year[2028].contrib_celi == pytest.approx(5000.0 * 1.02 ** 2)


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

    def test_retraites_decalees_cible_couverte(self):
        """P1 (1964) retraité à 65 en 2029, P2 (1968) travaille jusqu'en 2033:
        la cible ménage s'applique dès la première retraite et est couverte."""
        results = self.couple()
        mixed = [r for r in results if 2029 <= r.year < 2033]
        assert mixed
        for r in mixed:
            assert r.persons[0].retired and not r.persons[1].retired
            assert r.persons[1].salary > 0
            assert r.net_cash >= r.target_net - 5.0, f"année {r.year}"

    def test_roulement_conserve_patrimoine_menage(self):
        """Le décès ne détruit pas de patrimoine: la somme des comptes du
        ménage est continue (à la croissance et aux retraits près)."""
        results = self.couple(premature_death={"person_index": 0, "year": 2040})
        before = next(r for r in results if r.year == 2039).total_wealth
        after = next(r for r in results if r.year == 2040).total_wealth
        assert after > before * 0.85

    def test_fractionnement_optimal_ne_depasse_pas_sans_fractionnement(self):
        from planner.core.benefits import OAS
        from planner.core.simulation.splitting import (
            couple_tax_with_split, optimize_pension_split)
        from planner.core.tax import TaxCalculator, TaxInput
        calc, oas = TaxCalculator(2026, "QC"), OAS(2026)
        i1 = TaxInput(year=2026, age=68, ordinary_income=90000,
                      eligible_pension_income=60000)
        i2 = TaxInput(year=2026, age=66, ordinary_income=15000)
        sans = couple_tax_with_split(calc, oas, i1, i2, 8000, 8000,
                                     60000, 0, 0.0, 0.0)["total"]
        best = optimize_pension_split(calc, oas, i1, i2, 8000, 8000, 60000, 0)
        assert best["total"] < sans
        assert 0 < best["transfer_1_to_2"] <= 30000


class TestRepartitionCouple:
    def retired_couple(self, acc1: AccountsConfig, acc2: AccountsConfig,
                       target: float, **p2_overrides):
        p1 = single_person(name="P1", birth_year=1956, salary=0.0,
                           rrq_monthly_at_65=800.0, accounts=acc1,
                           contributions=ContributionsConfig())
        p2 = single_person(name="P2", birth_year=1956, salary=0.0,
                           rrq_monthly_at_65=800.0, accounts=acc2,
                           contributions=ContributionsConfig(), **p2_overrides)
        hh = HouseholdConfig(persons=[p1, p2], target_net_income=target)
        return HouseholdSimulator(
            hh, ScenarioConfig(start_year=2026, inflation=0.0)).run()

    def test_celi_retire_au_prorata_des_soldes(self):
        results = self.retired_couple(
            AccountsConfig(celi_balance=300000.0), AccountsConfig(celi_balance=100000.0),
            target=60000.0)
        r0 = results[0]
        w1, w2 = r0.persons[0].wd_celi, r0.persons[1].wd_celi
        assert w1 > 0 and w2 > 0
        assert w1 / w2 == pytest.approx(3.0, rel=0.01)

    def test_reer_nivelle_les_revenus_imposables(self):
        """P2 a une rente PD de 30 000$: les retraits REER doivent d'abord
        combler P1 pour égaliser les revenus imposables."""
        results = self.retired_couple(
            AccountsConfig(reer_balance=600000.0), AccountsConfig(reer_balance=600000.0),
            target=70000.0, db_status="in_payment", db_pension=30000.0)
        r0 = results[0]
        p1, p2 = r0.persons
        assert p1.wd_reer > p2.wd_reer
        # Nivellement avant fractionnement: l'écart des retraits compense la rente
        if p2.wd_reer > 0:
            assert p1.wd_reer - p2.wd_reer == pytest.approx(30000.0, abs=200.0)
        else:
            assert p1.wd_reer <= 30000.0 + 200.0

    def test_reer_egal_si_situations_identiques(self):
        results = self.retired_couple(
            AccountsConfig(reer_balance=500000.0), AccountsConfig(reer_balance=500000.0),
            target=70000.0)
        r0 = results[0]
        assert r0.persons[0].wd_reer == pytest.approx(r0.persons[1].wd_reer, rel=0.01)
        assert r0.net_cash >= r0.target_net - 5.0

    def test_solde_epuise_bascule_sur_le_conjoint(self):
        """Quand le REER du conjoint au revenu le plus bas est trop petit, le
        reste vient de l'autre conjoint (pas de cible manquée)."""
        results = self.retired_couple(
            AccountsConfig(reer_balance=5000.0), AccountsConfig(reer_balance=800000.0),
            target=70000.0)
        r0 = results[0]
        assert r0.persons[0].bal_reer == 0.0  # REER de P1 épuisé
        assert r0.persons[1].wd_reer > 30000.0
        assert r0.net_cash >= r0.target_net - 5.0


class TestIndexationFiscale:
    def pensioner(self, inflation: float):
        """Retraité vivant d'une rente PD indexée: revenu réel constant."""
        p = single_person(
            birth_year=1960, retirement_age=60, life_expectancy=90,
            salary=0.0, rrq_monthly_at_65=1200.0,
            db_status="in_payment", db_pension=60000.0, db_indexed=True,
            accounts=AccountsConfig(), contributions=ContributionsConfig())
        # Cible inatteignable: aucun surplus réinvesti, revenu = rente + RRQ + SV
        hh = HouseholdConfig(persons=[p], target_net_income=200000.0)
        return HouseholdSimulator(
            hh, ScenarioConfig(start_year=2026, inflation=inflation)).run()

    def test_taux_moyen_stable_avec_inflation(self):
        """Barèmes indexés: le taux moyen d'impôt ne dérive pas avec l'inflation
        (âge 66 à 74, avant la majoration SV de 75 ans)."""
        results = self.pensioner(0.03)
        rates = {r.persons[0].age: r.persons[0].tax_total / r.persons[0].taxable_income
                 for r in results if 66 <= r.persons[0].age <= 74}
        assert rates[74] == pytest.approx(rates[66], abs=0.002)

    def test_inflation_nulle_impot_constant(self):
        results = self.pensioner(0.0)
        taxes = [r.persons[0].tax_total for r in results
                 if 66 <= r.persons[0].age <= 74]
        assert max(taxes) - min(taxes) < 1.0

    def test_seuil_recuperation_sv_indexe(self):
        """À revenu réel constant sous le seuil, aucune récupération SV n'apparaît
        avec le temps."""
        results = self.pensioner(0.03)
        p_late = next(r.persons[0] for r in results if r.persons[0].age == 85)
        assert p_late.oas > 0
        assert p_late.oas_clawback == 0.0


class TestNoteInsuffisance:
    def test_note_quand_cible_inatteignable(self):
        p = single_person(
            birth_year=1956, salary=0.0, rrq_monthly_at_65=800.0,
            accounts=AccountsConfig(reer_balance=20000.0, celi_balance=50000.0),
            contributions=ContributionsConfig())
        hh = HouseholdConfig(persons=[p], target_net_income=80000.0,
                             celi_strategy="jamais")
        r0 = HouseholdSimulator(hh, ScenarioConfig(start_year=2026)).run()[0]
        assert r0.target_gap < -1000
        assert "manque" in r0.shortfall_note
        assert "REER" in r0.shortfall_note
        assert "CELI exclu" in r0.shortfall_note

    def test_pas_de_note_si_cible_atteinte(self):
        r0 = run_single()[0]
        assert r0.shortfall_note == ""


class TestSurplusReinvesti:
    def test_minimum_ferr_excedentaire_reinvesti(self):
        """Un minimum FERR forcé supérieur à la cible est placé (CELI puis
        non-enregistré) plutôt que perdu."""
        p = single_person(
            birth_year=1950, retirement_age=65, life_expectancy=90,
            salary=0.0, rrq_monthly_at_65=0.0, oas_start_age=70,
            accounts=AccountsConfig(ferr_balance=1500000.0, celi_room=7000.0),
            contributions=ContributionsConfig())
        hh = HouseholdConfig(persons=[p], target_net_income=20000.0)
        results = HouseholdSimulator(
            hh, ScenarioConfig(start_year=2026, inflation=0.0)).run()
        r0 = results[0]
        assert r0.persons[0].ferr_min > 60000
        assert r0.reinvested > 0
        assert r0.persons[0].contrib_celi == pytest.approx(7000.0)
        assert r0.persons[0].bal_taxable > 0
        assert r0.reinvested == pytest.approx(r0.net_cash - r0.target_net)


class TestRentesReversibles:
    """Rente PD et rente viagère réversibles au conjoint survivant."""

    @staticmethod
    def _couple(db_survivor_pct=0.6, annuity_pct=0.6, deceased_life=80):
        from planner.core.simulation.types import AnnuityConfig
        a = single_person(
            name="A", birth_year=1960, life_expectancy=deceased_life,
            db_status="in_payment", db_pension=40000.0, db_indexed=True,
            db_survivor_pct=db_survivor_pct,
            accounts=AccountsConfig(reer_balance=300000.0, celi_room=7000.0),
            contributions=ContributionsConfig())
        b = single_person(
            name="B", birth_year=1963, life_expectancy=95, salary=0.0,
            rrq_monthly_at_65=500.0, accounts=AccountsConfig(celi_room=7000.0),
            contributions=ContributionsConfig())
        hh = HouseholdConfig(
            persons=[a, b], target_net_income=60000.0,
            annuities=[AnnuityConfig(person_index=0, purchase_year=2028, premium=100000.0,
                                     annual_payment=7000.0, source="reer",
                                     survivor_pct=annuity_pct)])
        results = HouseholdSimulator(hh, ScenarioConfig(start_year=2026, inflation=0.02)).run()
        return {r.year: r for r in results}

    def test_rente_pd_reversible_60_pct(self):
        by = self._couple()
        before = by[2040]   # A vivant (80 ans)
        death = by[2041]    # A décède (81 > 80)
        assert before.persons[0].alive and not death.persons[0].alive
        assert before.persons[1].db_pension == 0.0
        expected = 0.6 * before.persons[0].db_pension * 1.02
        assert death.persons[1].db_pension == pytest.approx(expected, rel=1e-6)
        # Indexée les années suivantes
        assert by[2042].persons[1].db_pension == pytest.approx(expected * 1.02, rel=1e-6)
        assert any("rente PD de survivant" in d for d in death.decisions)

    def test_rente_viagere_reversible(self):
        by = self._couple()
        before, death = by[2040], by[2041]
        assert before.persons[0].annuity_income == pytest.approx(7000.0)
        assert before.persons[1].annuity_income == 0.0
        assert death.persons[1].annuity_income == pytest.approx(0.6 * 7000.0)
        assert by[2050].persons[1].annuity_income == pytest.approx(0.6 * 7000.0)

    def test_zero_pct_rien_au_survivant(self):
        by = self._couple(db_survivor_pct=0.0, annuity_pct=0.0)
        death = by[2041]
        assert death.persons[1].db_pension == 0.0
        assert death.persons[1].annuity_income == 0.0

    def test_pct_programmable(self):
        by = self._couple(db_survivor_pct=1.0)
        assert by[2041].persons[1].db_pension == pytest.approx(
            by[2040].persons[0].db_pension * 1.02, rel=1e-6)

    def test_reversion_imposable_chez_le_survivant(self):
        by = self._couple()
        p = by[2041].persons[1]
        assert p.tax_input.ordinary_income >= p.db_pension + p.annuity_income * 0.999
        assert p.tax_input.eligible_pension_income >= p.db_pension
        assert p.tax_total > by[2040].persons[1].tax_total

    def test_deces_avant_debut_de_la_rente(self):
        """Décès avant l'âge de début: la part réversible commence à l'âge prévu."""
        a = single_person(name="A", birth_year=1970, retirement_age=65, life_expectancy=60,
                          db_status="deferred", db_pension=30000.0, db_start_age=65,
                          db_survivor_pct=0.6, accounts=AccountsConfig(celi_room=7000.0),
                          contributions=ContributionsConfig())
        b = single_person(name="B", birth_year=1970, life_expectancy=95, salary=60000.0,
                          accounts=AccountsConfig(reer_balance=200000.0, celi_room=7000.0))
        hh = HouseholdConfig(persons=[a, b], target_net_income=40000.0)
        by = {r.year: r for r in HouseholdSimulator(
            hh, ScenarioConfig(start_year=2026, inflation=0.0)).run()}
        assert not by[2031].persons[0].alive            # A meurt à 61 ans
        assert by[2034].persons[1].db_pension == 0.0    # A aurait eu 64 ans
        assert by[2035].persons[1].db_pension == pytest.approx(0.6 * 30000.0)
