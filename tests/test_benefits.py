"""Tests des prestations gouvernementales (RRQ, SV, SRG, Allocation).

Références 2025: RRQ max 1 433,44$/mois à 65 ans; SV 734,95$/mois (65-74);
SRG seul max 1 097,75$/mois; seuil récupération SV 93 454$.
"""
import pytest

from planner.core.benefits import RRQ, OAS, GIS
from planner.core.benefits.params import load_benefits, available_years


# ==================== RRQ ====================

class TestRRQ:
    def setup_method(self):
        self.rrq = RRQ(2025)

    def test_facteur_a_60_ans(self):
        """60 mois d'anticipation × 0,6% = -36%."""
        assert self.rrq.adjustment_factor(60) == pytest.approx(0.64)

    def test_facteur_a_65_ans(self):
        assert self.rrq.adjustment_factor(65) == pytest.approx(1.0)

    def test_facteur_a_72_ans(self):
        """84 mois de report × 0,7% = +58,8%."""
        assert self.rrq.adjustment_factor(72) == pytest.approx(1.588)

    def test_facteur_borne_aux_ages_legaux(self):
        assert self.rrq.adjustment_factor(55) == self.rrq.adjustment_factor(60)
        assert self.rrq.adjustment_factor(80) == self.rrq.adjustment_factor(72)

    def test_rente_annuelle_1000_par_mois_debut_60(self):
        assert self.rrq.annual_pension(1000.0, 60) == pytest.approx(7680.0)

    def test_rente_annuelle_debut_72(self):
        assert self.rrq.annual_pension(1000.0, 72) == pytest.approx(19056.0)

    def test_rente_plafonnee_au_maximum(self):
        """Un montant saisi au-dessus du max RRQ est plafonné."""
        assert self.rrq.annual_pension(2000.0, 65) == pytest.approx(1433.44 * 12)

    def test_rente_survivant_60_pct(self):
        s = self.rrq.survivor_pension(
            deceased_annual_pension=12000.0, survivor_own_annual_pension=10000.0)
        assert s == pytest.approx(7200.0)

    def test_rente_survivant_plafonnee_max_combine(self):
        """Le total rente propre + survivant ne dépasse pas le max à 65 ans."""
        s = self.rrq.survivor_pension(
            deceased_annual_pension=12000.0, survivor_own_annual_pension=16000.0)
        assert s == pytest.approx(1433.44 * 12 - 16000.0)

    def test_prestation_deces(self):
        assert self.rrq.death_benefit() == 2500.0


# ==================== SV (OAS) ====================

class TestOAS:
    def setup_method(self):
        self.oas = OAS(2025)

    def test_pension_normale_65(self):
        assert self.oas.annual_pension(70, start_age=65) == pytest.approx(734.95 * 12)

    def test_report_a_70_ans_plus_36_pct(self):
        expected = 734.95 * 12 * 1.36
        assert self.oas.annual_pension(70, start_age=70) == pytest.approx(expected)

    def test_majoration_75_ans_plus_10_pct(self):
        expected = 734.95 * 12 * 1.10
        assert self.oas.annual_pension(76, start_age=65) == pytest.approx(expected)

    def test_avant_debut_aucune_pension(self):
        assert self.oas.annual_pension(64, start_age=65) == 0.0
        assert self.oas.annual_pension(66, start_age=68) == 0.0

    def test_proratisation_residence(self):
        """20 ans de résidence sur 40 = demi-pension."""
        full = self.oas.annual_pension(70, start_age=65, residence_years=40)
        half = self.oas.annual_pension(70, start_age=65, residence_years=20)
        assert half == pytest.approx(full / 2)

    def test_clawback_sous_seuil_nul(self):
        assert self.oas.clawback(90000.0, 8819.40) == 0.0

    def test_clawback_partiel(self):
        """(100 000 − 93 454) × 15% = 981,90."""
        assert self.oas.clawback(100000.0, 8819.40) == pytest.approx(981.90)

    def test_clawback_plafonne_a_la_sv_recue(self):
        assert self.oas.clawback(200000.0, 8819.40) == pytest.approx(8819.40)


# ==================== SRG (GIS) + Allocation ====================

class TestGIS:
    def setup_method(self):
        self.gis = GIS(2025)

    def test_personne_seule_sans_revenu_maximum(self):
        assert self.gis.annual_single(0.0) == pytest.approx(1097.75 * 12)

    def test_personne_seule_reduction_50_cents(self):
        """10 000$ de revenu (hors SV, non-emploi) → réduction de 5 000$."""
        expected = 1097.75 * 12 - 5000.0
        assert self.gis.annual_single(10000.0) == pytest.approx(expected)

    def test_personne_seule_revenu_eleve_zero(self):
        assert self.gis.annual_single(30000.0) == 0.0

    def test_exemption_revenu_emploi(self):
        """10 000$ tout en emploi: 5 000$ exemptés → réduction de 2 500$ seulement."""
        expected = 1097.75 * 12 - 2500.0
        assert self.gis.annual_single(10000.0, employment_income=10000.0) == pytest.approx(expected)

    def test_couple_reduction_25_cents_chacun(self):
        """Revenu combiné 12 000$ → réduction de 3 000$ chacun."""
        expected = 660.78 * 12 - 3000.0
        assert self.gis.annual_couple_each(12000.0) == pytest.approx(expected)

    def test_srg_couple_inferieur_srg_seul(self):
        assert self.gis.annual_couple_each(0.0) < self.gis.annual_single(0.0)

    def test_allocation_conjoint_60_64(self):
        assert self.gis.annual_allowance(62, 0.0) == pytest.approx(1395.73 * 12)

    def test_allocation_hors_tranche_age(self):
        assert self.gis.annual_allowance(59, 0.0) == 0.0
        assert self.gis.annual_allowance(65, 0.0) == 0.0

    def test_allocation_reduction_75_cents(self):
        expected = 1395.73 * 12 - 0.75 * 10000.0
        assert self.gis.annual_allowance(62, 10000.0) == pytest.approx(expected)


# ==================== INFRASTRUCTURE ====================

class TestInfrastructure:
    def test_annees_disponibles(self):
        years = available_years()
        assert 2025 in years and 2026 in years

    def test_2026_estime_et_indexe(self):
        p25, p26 = load_benefits(2025), load_benefits(2026)
        assert p26["estimated"] is True
        assert p26["rrq"]["max_monthly_at_65"] > p25["rrq"]["max_monthly_at_65"]

    def test_annee_future_repli_derniere_connue(self):
        assert load_benefits(2040)["_effective_year"] == max(available_years())
