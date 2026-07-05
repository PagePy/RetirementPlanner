"""Tests du moteur fiscal (fédéral + Québec).

Les cas de référence sont calculés à la main à partir des barèmes 2025:
- Fédéral: paliers 57 375 (14,5%) / 114 750 (20,5%) / ..., BPA 16 129,
  crédit d'âge 9 028 (seuil 45 522), crédit pension 2 000, abattement QC 16,5%.
- Québec: paliers 53 255 (14%) / 106 495 (19%) / ..., BPA 18 571,
  crédits aînés (âge 3 906, retraite 3 470, personne seule 2 128, seuil 42 090).
"""
import pytest

from planner.core.tax import TaxCalculator, TaxInput
from planner.core.tax.params import load_params, bracket_tax, available_years
from planner.core.tax.provincial import get_province_tax, supported_provinces


def make_input(**kwargs) -> TaxInput:
    defaults = {"year": 2025, "age": 40}
    defaults.update(kwargs)
    return TaxInput(**defaults)


# ==================== CAS DE RÉFÉRENCE (calcul manuel) ====================

class TestReferenceCases2025:
    def setup_method(self):
        self.calc = TaxCalculator(year=2025, province="QC")

    def test_salarie_60k(self):
        """Salarié 60 000$, 40 ans.
        Fédéral: 57 375×14,5% + 2 625×20,5% = 8 857,50
                 − BPA 16 129×14,5% = 2 338,71 → 6 518,80
                 − abattement 16,5% → 5 443,19
        Québec:  53 255×14% + 6 745×19% = 8 737,25
                 − BPA 18 571×14% = 2 599,94 → 6 137,31
        Total: 11 580,50
        """
        r = self.calc.compute(make_input(ordinary_income=60000))
        assert r.federal.net_tax == pytest.approx(5443.19, abs=1.0)
        assert r.provincial.net_tax == pytest.approx(6137.31, abs=1.0)
        assert r.total_tax == pytest.approx(11580.50, abs=2.0)

    def test_retraite_70_ans_40k(self):
        """Retraité 70 ans vivant seul, 40 000$ dont 30 000$ de pension admissible.
        Fédéral: 40 000×14,5% = 5 800
                 crédits: (16 129 + 9 028 + 2 000)×14,5% = 3 937,77 → 1 862,23
                 − abattement 16,5% → 1 554,97
        Québec:  40 000×14% = 5 600
                 aînés: 3 906 + 3 470 + 2 128 = 9 504 (aucune réduction, revenu < 42 090)
                 crédits: (18 571 + 9 504)×14% = 3 930,50 → 1 669,50
        Total: 3 224,47
        """
        r = self.calc.compute(make_input(
            age=70, ordinary_income=40000,
            eligible_pension_income=30000, lives_alone=True,
        ))
        assert r.federal.net_tax == pytest.approx(1554.97, abs=1.0)
        assert r.provincial.net_tax == pytest.approx(1669.50, abs=1.0)
        assert r.total_tax == pytest.approx(3224.47, abs=2.0)

    def test_revenu_nul(self):
        r = self.calc.compute(make_input(ordinary_income=0))
        assert r.total_tax == 0.0
        assert r.after_tax_income == 0.0

    def test_dividendes_determines_modestes_zero_impot(self):
        """20 000$ de dividendes déterminés seuls: crédits BPA + crédit dividendes
        dépassent l'impôt brut → impôt nul aux deux paliers."""
        r = self.calc.compute(make_input(eligible_dividends=20000))
        assert r.total_tax == 0.0
        # Revenu imposable = montant majoré (×1,38)
        assert r.taxable_income == pytest.approx(27600.0)

    def test_gains_capital_inclusion_50_pct(self):
        """50 000$ ordinaire + 10 000$ gains: revenu imposable 55 000$."""
        r = self.calc.compute(make_input(ordinary_income=50000, capital_gains=10000))
        assert r.taxable_income == pytest.approx(55000.0)
        # L'argent reçu inclut le gain complet
        assert r.after_tax_income == pytest.approx(60000.0 - r.total_tax)

    def test_deductions_reer(self):
        """Une déduction REER réduit le revenu imposable dollar pour dollar."""
        sans = self.calc.compute(make_input(ordinary_income=80000))
        avec = self.calc.compute(make_input(ordinary_income=80000, deductions=10000))
        assert avec.taxable_income == pytest.approx(70000.0)
        assert avec.total_tax < sans.total_tax


# ==================== CRÉDITS SPÉCIFIQUES ====================

class TestCredits:
    def setup_method(self):
        self.calc = TaxCalculator(year=2025, province="QC")

    def test_credit_age_reduit_impot(self):
        jeune = self.calc.compute(make_input(age=64, ordinary_income=50000))
        aine = self.calc.compute(make_input(age=65, ordinary_income=50000))
        assert aine.total_tax < jeune.total_tax

    def test_credit_age_disparait_haut_revenu(self):
        """À 150 000$, la réduction de 15% × (150 000 − 45 522) dépasse 9 028$."""
        r = self.calc.compute(make_input(age=70, ordinary_income=150000))
        assert r.federal.credits_detail["age_amount"] == 0.0

    def test_credit_pension_plafonne_2000_federal(self):
        r = self.calc.compute(make_input(
            age=70, ordinary_income=50000, eligible_pension_income=30000))
        assert r.federal.credits_detail["pension_amount"] == 2000.0

    def test_bpa_federal_reduit_hauts_revenus(self):
        bas = self.calc.compute(make_input(ordinary_income=100000))
        haut = self.calc.compute(make_input(ordinary_income=300000))
        assert bas.federal.credits_detail["bpa"] == pytest.approx(16129)
        assert haut.federal.credits_detail["bpa"] == pytest.approx(14538)

    def test_credits_aines_qc_reduits_selon_revenu_familial(self):
        """Le revenu familial élevé du couple réduit les crédits aînés QC
        même si le revenu individuel est modeste."""
        seul = self.calc.compute(make_input(
            age=70, ordinary_income=40000, eligible_pension_income=10000))
        avec_conjoint_riche = self.calc.compute(make_input(
            age=70, ordinary_income=40000, eligible_pension_income=10000,
            family_net_income=120000))
        assert avec_conjoint_riche.total_tax > seul.total_tax
        assert avec_conjoint_riche.provincial.credits_detail["senior_amount"] == 0.0


# ==================== INVARIANTS ====================

class TestInvariants:
    def setup_method(self):
        self.calc = TaxCalculator(year=2025, province="QC")

    def test_impot_monotone_croissant(self):
        taxes = [
            self.calc.compute(make_input(ordinary_income=x)).total_tax
            for x in range(0, 300001, 25000)
        ]
        assert taxes == sorted(taxes)

    def test_taux_marginal_borne(self):
        for income in (30000, 60000, 120000, 200000, 400000):
            r = self.calc.compute(make_input(ordinary_income=income))
            assert 0.0 <= r.marginal_rate < 0.60

    def test_taux_marginal_sommet_2025(self):
        """Taux marginal maximal combiné QC ≈ 33%×0,835 + 25,75% = 53,3%."""
        r = self.calc.compute(make_input(ordinary_income=400000))
        assert r.marginal_rate == pytest.approx(0.5330, abs=0.005)

    def test_abattement_quebec_applique(self):
        r = self.calc.compute(make_input(ordinary_income=100000))
        assert r.federal.abatement > 0

    def test_bracket_tax_bornes(self):
        brackets = [[50000, 0.10], [None, 0.20]]
        assert bracket_tax(0, brackets) == 0.0
        assert bracket_tax(50000, brackets) == pytest.approx(5000.0)
        assert bracket_tax(60000, brackets) == pytest.approx(5000.0 + 2000.0)


# ==================== INFRASTRUCTURE ====================

class TestInfrastructure:
    def test_annees_disponibles(self):
        years = available_years()
        assert 2025 in years and 2026 in years

    def test_annee_future_utilise_derniers_baremes(self):
        p = load_params(2035, "federal")
        assert p["_effective_year"] == max(available_years())

    def test_2026_marque_estime(self):
        assert load_params(2026, "federal")["estimated"] is True
        assert load_params(2025, "federal")["estimated"] is False

    def test_province_non_supportee(self):
        with pytest.raises(ValueError, match="non supportée"):
            get_province_tax("ZZ", 2025)

    def test_provinces_supportees(self):
        assert "QC" in supported_provinces()

    def test_calculateur_2026_fonctionne(self):
        r = TaxCalculator(year=2026, province="QC").compute(
            TaxInput(year=2026, age=40, ordinary_income=60000))
        assert 0 < r.total_tax < 60000 * 0.35
