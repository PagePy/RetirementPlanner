"""Tests des actifs réels, passifs et remplacements de véhicules."""
import pytest

from planner.core.analysis import estate_timeline
from planner.core.assets import (
    Debt, DebtConfig, RealAsset, RealAssetConfig, VehicleReplacementConfig)
from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, HouseholdSimulator)


def person(**overrides) -> PersonConfig:
    defaults = dict(
        name="Test", birth_year=1966, retirement_age=65, life_expectancy=85,
        salary=85000.0, rrq_monthly_at_65=1000.0,
        accounts=AccountsConfig(
            reer_balance=450000.0, celi_balance=100000.0, celi_room=7000.0,
            taxable_balance=150000.0, taxable_acb=100000.0),
        contributions=ContributionsConfig(reer_pct=0.10, celi_fixed=7000.0),
    )
    defaults.update(overrides)
    return PersonConfig(**defaults)


SCEN = ScenarioConfig(start_year=2026, inflation=0.02)


def run(**hh_overrides):
    defaults = dict(persons=[person()], target_net_income=48000.0)
    defaults.update(hh_overrides)
    return HouseholdSimulator(HouseholdConfig(**defaults), SCEN).run()


# ==================== DETTES (unités) ====================

class TestDebt:
    def test_amortissement_hypotheque(self):
        """300k$ à 5%, paiement 24k$/an: intérêts an 1 = 15k$, capital = 9k$."""
        d = Debt(cfg=DebtConfig("Hypothèque", 300000.0, 0.05, 24000.0, "hypotheque"))
        s = d.annual_service()
        assert s["interest"] == pytest.approx(15000.0)
        assert s["principal"] == pytest.approx(9000.0)
        assert d.balance == pytest.approx(291000.0)

    def test_extinction_complete(self):
        d = Debt(cfg=DebtConfig("Prêt auto", 10000.0, 0.07, 6000.0, "auto"))
        total_paid = 0.0
        for _ in range(5):
            total_paid += d.annual_service()["payment"]
        assert not d.is_active
        assert total_paid < 5 * 6000.0  # dernier paiement partiel

    def test_paiement_minimum_dette_croit(self):
        """Carte de crédit à 20%, paiement inférieur aux intérêts → solde croît."""
        d = Debt(cfg=DebtConfig("Visa", 10000.0, 0.20, 1500.0, "carte_credit"))
        d.annual_service()
        assert d.balance > 10000.0
        assert d.years_to_payoff() is None

    def test_annees_avant_extinction(self):
        d = Debt(cfg=DebtConfig("Prêt", 50000.0, 0.06, 12000.0, "personnel"))
        assert d.years_to_payoff() == 5


# ==================== ACTIFS RÉELS (unités) ====================

class TestRealAsset:
    def test_appreciation(self):
        a = RealAsset(cfg=RealAssetConfig("Maison", 500000.0, appreciation=0.03))
        a.appreciate()
        assert a.value == pytest.approx(515000.0)

    def test_residence_principale_exoneree(self):
        a = RealAsset(cfg=RealAssetConfig(
            "Maison", 600000.0, cost_base=300000.0, is_principal_residence=True))
        sale = a.sell()
        assert sale["proceeds"] == pytest.approx(600000.0)
        assert sale["taxable_gain"] == 0.0

    def test_chalet_gain_imposable(self):
        a = RealAsset(cfg=RealAssetConfig(
            "Chalet", 400000.0, kind="chalet", cost_base=250000.0))
        sale = a.sell()
        assert sale["taxable_gain"] == pytest.approx(150000.0)

    def test_vehicule_recurrence(self):
        v = VehicleReplacementConfig(first_year=2030, every_years=8,
                                     net_cost=30000.0, last_year=2050)
        assert v.cost_in_year(2030) and v.cost_in_year(2038) and v.cost_in_year(2046)
        assert not v.cost_in_year(2029)
        assert not v.cost_in_year(2034)
        assert not v.cost_in_year(2054)


# ==================== INTÉGRATION SIMULATEUR ====================

class TestSimulatorIntegration:
    def test_hypotheque_amortie_dans_simulation(self):
        results = run(debts=[DebtConfig("Hypothèque", 200000.0, 0.05, 30000.0,
                                        "hypotheque")])
        assert results[0].debts_balance < 200000.0
        # Éteinte en ~8-9 ans
        assert next(r for r in results if r.year == 2036).debts_balance == 0.0
        assert results[0].debt_interest == pytest.approx(10000.0)

    def test_service_dette_ajoute_a_la_cible_retraite(self):
        """Une dette active à la retraite augmente la cible de retraits."""
        base = run()
        avec = run(debts=[DebtConfig("Hypothèque", 300000.0, 0.05, 25000.0,
                                     "hypotheque")])
        # À la retraite (2031+), la cible inclut le service de la dette
        r_base = next(r for r in base if r.year == 2032)
        r_avec = next(r for r in avec if r.year == 2032)
        assert r_avec.target_net == pytest.approx(
            r_base.target_net + r_avec.debt_service, rel=0.001)
        # Le patrimoine final en souffre
        assert avec[-1].total_wealth < base[-1].total_wealth

    def test_maison_dans_valeur_nette(self):
        results = run(real_assets=[RealAssetConfig(
            "Maison", 500000.0, is_principal_residence=True)])
        r0 = results[0]
        assert r0.real_assets_value == pytest.approx(500000.0 * 1.02)
        assert r0.net_worth == pytest.approx(r0.total_wealth + r0.real_assets_value)

    def test_vente_maison_produit_investi(self):
        """Vente en 2040: le produit va au non-enregistré, sans impôt
        (résidence principale)."""
        results = run(real_assets=[RealAssetConfig(
            "Maison", 500000.0, is_principal_residence=True, sale_year=2040)])
        r2040 = next(r for r in results if r.year == 2040)
        r2041 = next(r for r in results if r.year == 2041)
        assert r2040.asset_sale_proceeds > 500000.0  # apprécié depuis 2026
        assert r2040.real_assets_value == 0.0
        assert r2041.persons[0].bal_taxable > 400000.0

    def test_vente_avec_dette_liee_remboursee(self):
        results = run(
            real_assets=[RealAssetConfig(
                "Maison", 500000.0, is_principal_residence=True,
                sale_year=2035, linked_debt="Hypothèque")],
            debts=[DebtConfig("Hypothèque", 200000.0, 0.05, 18000.0, "hypotheque")])
        r2035 = next(r for r in results if r.year == 2035)
        assert r2035.debts_balance == 0.0  # hypothèque éteinte à la vente

    def test_vente_chalet_genere_impot(self):
        """La vente d'un chalet (non exonéré) crée un gain imposable."""
        base = run(real_assets=[RealAssetConfig(
            "Chalet", 300000.0, kind="chalet", cost_base=150000.0,
            is_principal_residence=True, sale_year=2040)])  # exonéré (contrôle)
        taxed = run(real_assets=[RealAssetConfig(
            "Chalet", 300000.0, kind="chalet", cost_base=150000.0,
            is_principal_residence=False, sale_year=2040)])
        tax_base = next(r for r in base if r.year == 2040).total_tax
        tax_taxed = next(r for r in taxed if r.year == 2040).total_tax
        assert tax_taxed > tax_base + 10000.0

    def test_remplacement_vehicule_cout_indexe(self):
        results = run(vehicle_plans=[VehicleReplacementConfig(
            first_year=2032, every_years=8, net_cost=30000.0)])
        r2032 = next(r for r in results if r.year == 2032)
        r2040 = next(r for r in results if r.year == 2040)
        r2033 = next(r for r in results if r.year == 2033)
        assert r2032.vehicle_expenses == pytest.approx(30000.0 * 1.02 ** 6)
        assert r2040.vehicle_expenses > r2032.vehicle_expenses  # indexé
        assert r2033.vehicle_expenses == 0.0
        # La cible de 2032 (retraite) inclut le véhicule
        assert r2032.target_net > r2033.target_net

    def test_succession_inclut_actifs_et_dettes(self):
        results = run(
            real_assets=[RealAssetConfig("Maison", 400000.0,
                                         is_principal_residence=True)],
            debts=[DebtConfig("Hypothèque", 150000.0, 0.05, 12000.0,
                              "hypotheque")])
        estates = estate_timeline(results, "QC")
        e0 = estates[0]
        r0 = results[0]
        assert e0.gross_estate == pytest.approx(
            r0.total_wealth + r0.real_assets_value)
        # Dettes déduites de la succession nette
        assert e0.net_estate < e0.gross_estate - e0.tax_at_death + 0.01

    def test_chalet_gain_latent_dans_succession(self):
        exonere = run(real_assets=[RealAssetConfig(
            "Chalet", 300000.0, cost_base=100000.0, is_principal_residence=True)])
        impose = run(real_assets=[RealAssetConfig(
            "Chalet", 300000.0, cost_base=100000.0, is_principal_residence=False)])
        e_ex = estate_timeline(exonere, "QC")[-1]
        e_im = estate_timeline(impose, "QC")[-1]
        assert e_im.tax_at_death > e_ex.tax_at_death
