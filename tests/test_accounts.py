"""Tests des comptes: REER (droits), CELI, CELIAPP, RAP, FERR/FRV, PBR."""
import pytest

from planner.core.accounts import REER, RAP, CELI, CELIAPP, FERR, FRV, Taxable, rrif_min_factor


# ==================== REER ====================

class TestREER:
    def test_nouveaux_droits_18_pct(self):
        r = REER(year=2025)
        assert r.add_new_room(100000) == pytest.approx(18000.0)

    def test_nouveaux_droits_plafonnes(self):
        """18% de 300 000$ = 54 000$ > plafond 2025 de 32 490$."""
        r = REER(year=2025)
        assert r.add_new_room(300000) == pytest.approx(32490.0)

    def test_cotisation_limitee_aux_droits(self):
        r = REER(contribution_room=10000.0, year=2025)
        assert r.contribute(15000.0) == pytest.approx(10000.0)
        assert r.balance == pytest.approx(10000.0)
        assert r.contribution_room == 0.0

    def test_retrait_ne_restaure_pas_droits(self):
        r = REER(balance=50000.0, contribution_room=0.0, year=2025)
        r.withdraw(10000.0)
        assert r.contribution_room == 0.0
        assert r.balance == pytest.approx(40000.0)

    def test_conversion_obligatoire_71_ans(self):
        r = REER(balance=100000.0, year=2025)
        assert not r.must_convert(70)
        assert r.must_convert(71)
        assert r.convert_to_ferr() == pytest.approx(100000.0)
        assert r.balance == 0.0


# ==================== RAP ====================

class TestRAP:
    def test_retrait_max_60k(self):
        reer = REER(balance=100000.0, year=2025)
        rap = RAP(year=2025)
        assert rap.borrow(reer, 80000.0, year=2025) == pytest.approx(60000.0)
        assert reer.balance == pytest.approx(40000.0)

    def test_retrait_limite_au_solde(self):
        reer = REER(balance=20000.0, year=2025)
        rap = RAP(year=2025)
        assert rap.borrow(reer, 60000.0, year=2025) == pytest.approx(20000.0)

    def test_aucun_remboursement_pendant_grace(self):
        reer = REER(balance=60000.0, year=2025)
        rap = RAP(year=2025)
        rap.borrow(reer, 30000.0, year=2025)
        assert rap.repayment_due(2026) == 0.0
        assert rap.repayment_due(2027) == pytest.approx(30000.0 / 15)

    def test_remboursement_sans_droits_reer(self):
        reer = REER(balance=60000.0, contribution_room=0.0, year=2025)
        rap = RAP(year=2025)
        rap.borrow(reer, 30000.0, year=2025)
        res = rap.repay(reer, 2000.0, year=2027)
        assert res["repaid"] == pytest.approx(2000.0)
        assert res["taxable_shortfall"] == 0.0
        assert reer.balance == pytest.approx(32000.0)  # 30 000 restant + 2 000

    def test_manque_a_rembourser_imposable(self):
        reer = REER(balance=60000.0, year=2025)
        rap = RAP(year=2025)
        rap.borrow(reer, 30000.0, year=2025)
        res = rap.repay(reer, 0.0, year=2027)
        assert res["taxable_shortfall"] == pytest.approx(2000.0)


# ==================== CELI ====================

class TestCELI:
    def test_nouveaux_droits_annuels(self):
        c = CELI(contribution_room=0.0, year=2025)
        c.new_year(2025)
        assert c.contribution_room == pytest.approx(7000.0)

    def test_retrait_restaure_droits_annee_suivante(self):
        c = CELI(balance=50000.0, contribution_room=0.0, year=2025)
        c.withdraw(10000.0)
        assert c.contribution_room == 0.0  # pas tout de suite
        c.new_year(2026)
        assert c.contribution_room == pytest.approx(7000.0 + 10000.0)

    def test_cotisation_limitee(self):
        c = CELI(contribution_room=5000.0, year=2025)
        assert c.contribute(8000.0) == pytest.approx(5000.0)


# ==================== CELIAPP ====================

class TestCELIAPP:
    def test_droits_annuels_8k(self):
        f = CELIAPP(year_opened=2025)
        assert f.contribution_room == pytest.approx(8000.0)

    def test_report_max_8k(self):
        f = CELIAPP(year_opened=2025)
        f.new_year()  # aucune cotisation en 2025 → reporte 8 000
        assert f.contribution_room == pytest.approx(16000.0)
        f.new_year()  # le report est plafonné à 8 000
        assert f.contribution_room == pytest.approx(16000.0)

    def test_plafond_vie_40k(self):
        f = CELIAPP(year_opened=2025, lifetime_contributed=36000.0)
        assert f.contribution_room == pytest.approx(4000.0)

    def test_retrait_admissible_non_imposable(self):
        f = CELIAPP(balance=25000.0, year_opened=2025)
        assert f.qualifying_withdrawal(25000.0) == pytest.approx(25000.0)
        assert f.balance == 0.0

    def test_transfert_reer_sans_droits(self):
        f = CELIAPP(balance=30000.0, year_opened=2025)
        reer = REER(balance=0.0, contribution_room=0.0, year=2025)
        assert f.transfer_to_reer(reer) == pytest.approx(30000.0)
        assert reer.balance == pytest.approx(30000.0)
        assert reer.contribution_room == 0.0  # aucun droit consommé

    def test_fermeture_apres_15_ans_ou_71_ans(self):
        f = CELIAPP(year_opened=2025)
        assert not f.must_close(2030, 40)
        assert f.must_close(2040, 55)   # 15 ans
        assert f.must_close(2030, 71)   # 71 ans


# ==================== FERR / FRV ====================

class TestFERRFRV:
    def test_facteur_avant_71_ans(self):
        """À 65 ans: 1/(90−65) = 4%."""
        assert rrif_min_factor(65) == pytest.approx(0.04)

    def test_facteur_table_legale(self):
        assert rrif_min_factor(71) == pytest.approx(0.0528)
        assert rrif_min_factor(85) == pytest.approx(0.0851)
        assert rrif_min_factor(95) == pytest.approx(0.20)
        assert rrif_min_factor(99) == pytest.approx(0.20)

    def test_minimum_ferr(self):
        f = FERR(balance=200000.0)
        assert f.min_withdrawal(72) == pytest.approx(200000.0 * 0.0540)

    def test_minimum_avec_age_conjoint_plus_jeune(self):
        """Conjoint 5 ans plus jeune → facteur de 67 ans au lieu de 72."""
        f = FERR(balance=200000.0, spouse_age_offset=-5, use_spouse_age=True)
        expected = 200000.0 * (1.0 / (90 - 67))
        assert f.min_withdrawal(72) == pytest.approx(expected)

    def test_frv_quebec_sans_maximum_depuis_2025(self):
        frv = FRV(balance=300000.0, year=2025, province="QC")
        assert frv.max_withdrawal(60) is None

    def test_frv_minimum_comme_ferr(self):
        frv = FRV(balance=100000.0, year=2025)
        assert frv.min_withdrawal(71) == pytest.approx(100000.0 * 0.0528)


# ==================== NON-ENREGISTRÉ (PBR) ====================

class TestTaxable:
    def test_cotisation_augmente_pbr(self):
        t = Taxable(balance=0.0, acb=0.0)
        t.contribute(50000.0)
        assert t.acb == pytest.approx(50000.0)

    def test_retrait_gain_au_prorata(self):
        """Valeur 100k, PBR 60k → retrait de 10k réalise 4k de gain."""
        t = Taxable(balance=100000.0, acb=60000.0)
        res = t.withdraw(10000.0)
        assert res["realized_gain"] == pytest.approx(4000.0)
        assert res["acb_used"] == pytest.approx(6000.0)
        assert t.balance == pytest.approx(90000.0)
        assert t.acb == pytest.approx(54000.0)

    def test_retrait_sans_gain_si_pbr_egal_valeur(self):
        t = Taxable(balance=50000.0, acb=50000.0)
        res = t.withdraw(20000.0)
        assert res["realized_gain"] == pytest.approx(0.0)

    def test_croissance_latente_non_imposee(self):
        t = Taxable(balance=100000.0, acb=100000.0, capital_growth_ratio=1.0)
        income = t.grow(0.06)
        assert income["interest"] == 0.0
        assert income["eligible_dividends"] == 0.0
        assert t.balance == pytest.approx(106000.0)
        assert t.unrealized_gain == pytest.approx(6000.0)

    def test_distributions_imposables_et_reinvesties(self):
        t = Taxable(balance=100000.0, acb=100000.0,
                    interest_ratio=0.5, eligible_dividend_ratio=0.5,
                    capital_growth_ratio=0.0)
        income = t.grow(0.04)
        assert income["interest"] == pytest.approx(2000.0)
        assert income["eligible_dividends"] == pytest.approx(2000.0)
        # Réinvesties: PBR augmente → pas de double imposition future
        assert t.acb == pytest.approx(104000.0)
        assert t.balance == pytest.approx(104000.0)

    def test_gain_latent_pour_succession(self):
        t = Taxable(balance=150000.0, acb=90000.0)
        assert t.unrealized_gain == pytest.approx(60000.0)
