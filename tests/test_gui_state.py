"""Tests de l'état GUI: chemins de profils et migration des anciens profils."""
import pytest

from gui import state


class TestProfilePath:
    @pytest.mark.parametrize("name", [
        "MonProfil", "Profil_2025-11-29", "Chris Lulu", "Élise.v2"])
    def test_noms_valides(self, name):
        path = state.profile_path(name)
        assert path.parent == state.PROFILES_DIR.resolve()
        assert path.name == f"{name}.json"

    @pytest.mark.parametrize("name", [
        "", "   ", "..", "../x", "..\\x", "a/b", "a\\b", "C:evil", "x*y", "a:b"])
    def test_noms_rejetes(self, name):
        with pytest.raises(ValueError):
            state.profile_path(name)

    def test_save_refuse_nom_invalide(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "PROFILES_DIR", tmp_path)
        s = state.default_state()
        s["profile_name"] = "../evil"
        with pytest.raises(ValueError):
            state.save_profile(s)
        assert not list(tmp_path.parent.glob("evil.json"))

    def test_aller_retour_sauvegarde(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "PROFILES_DIR", tmp_path)
        s = state.default_state()
        s["profile_name"] = "Test"
        s["target_net_income"] = 61000.0
        state.save_profile(s)
        loaded = state.load_profile("Test")
        assert loaded["target_net_income"] == 61000.0
        assert state.list_profiles() == ["Test"]


class TestHistorique:
    def test_sauvegarde_archive_la_version_precedente(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "PROFILES_DIR", tmp_path)
        s = state.default_state()
        s["profile_name"] = "Hist"
        state.save_profile(s)
        assert state.profile_history("Hist") == []
        state.save_profile(s)  # identique: pas d'archive
        assert state.profile_history("Hist") == []
        s["target_net_income"] = 70000.0
        s["persons"][0]["name"] = "Alice"
        state.save_profile(s)
        versions = state.profile_history("Hist")
        assert len(versions) == 1
        old = state.load_version(versions[0])
        assert old["target_net_income"] == 60000.0
        changes = state.diff_states(old, state.load_profile("Hist"))
        paths = {c["path"] for c in changes}
        assert "target_net_income" in paths
        assert any(p.startswith("persons.[") and p.endswith(".name") for p in paths)
        assert state.list_profiles() == ["Hist"]  # l'historique n'apparaît pas

    def test_diff_vide_si_identique(self):
        s = state.default_state()
        assert state.diff_states(s, state.default_state()) == []

    def test_warning_hidden_persists_in_state(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "PROFILES_DIR", tmp_path)
        s = state.default_state()
        assert s.get("hide_data_warning") is False
        s["hide_data_warning"] = True
        state.save_profile(s)
        loaded = state.load_profile(s["profile_name"])
        assert loaded["hide_data_warning"] is True


class TestRelevePD:
    def test_ancien_profil_recoit_valeurs_par_defaut(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "PROFILES_DIR", tmp_path)
        s = state.default_state()
        s["profile_name"] = "Ancien"
        for key in state.DB_STATEMENT_DEFAULTS:
            del s["persons"][0][key]
        state.save_profile(s)
        person = state.load_profile("Ancien")["persons"][0]
        assert person["db_service_years"] == 0.0
        assert person["db_coordination"] == "none"
        hh, _ = state.to_configs(state.load_profile("Ancien"))
        assert not hh.persons[0].db_from_statement

    def test_conversion_des_pourcentages(self):
        s = state.default_state()
        s["persons"][0].update(db_status="active", db_service_years=12.5,
                               db_avg_salary=80000.0, db_accrual_rate=1.8,
                               db_avg_years=5, db_coordination="bridge",
                               db_bridge_rate=0.7)
        cfg = state.to_configs(s)[0].persons[0]
        assert cfg.db_from_statement
        assert cfg.db_accrual_rate == pytest.approx(0.018)
        assert cfg.db_bridge_rate == pytest.approx(0.007)
        assert cfg.db_avg_years == 5 and cfg.db_coordination == "bridge"

    def test_pdf_avec_releve(self):
        from gui import compute, report
        s = state.default_state()
        s["persons"][0].update(db_status="active", db_service_years=10.0,
                               db_avg_salary=70000.0)
        hh, scen = state.to_configs(s)
        results, estates = compute.simulate_with_estate(hh, scen)
        assert report.build_pdf(s, hh, scen, results, estates)[:5] == b"%PDF-"


class TestDateDeNaissance:
    def test_date_donne_annee_et_mois(self):
        s = state.default_state()
        s["persons"][0].update(birth_date="1970-06-15", birth_year=1900)
        cfg = state.to_configs(s)[0].persons[0]
        assert (cfg.birth_year, cfg.birth_month) == (1970, 6)
        assert cfg.retirement_month == 0  # auto

    def test_mois_de_depart_choisi_avec_date(self):
        s = state.default_state()
        s["persons"][0].update(birth_date="1970-06-15", retirement_month=3,
                               retirement_start_month=10)
        assert state.to_configs(s)[0].persons[0].retirement_month == 10

    def test_sans_date_garde_ancien_mois_de_depart(self):
        s = state.default_state()
        s["persons"][0].update(birth_date="", retirement_month=7,
                               retirement_start_month=10)
        assert state.to_configs(s)[0].persons[0].retirement_month == 7

    @pytest.mark.parametrize("value", ["", None, "1970-13-01", "pas une date"])
    def test_date_vide_ou_invalide_garde_l_annee(self, value):
        s = state.default_state()
        s["persons"][0].update(birth_date=value, birth_year=1968)
        cfg = state.to_configs(s)[0].persons[0]
        assert (cfg.birth_year, cfg.birth_month) == (1968, 0)

    def test_chargement_synchronise_l_annee(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "PROFILES_DIR", tmp_path)
        s = state.default_state()
        s["profile_name"] = "Date"
        s["persons"][0].update(birth_date="1971-03-02", birth_year=1970)
        state.save_profile(s)
        assert state.load_profile("Date")["persons"][0]["birth_year"] == 1971

    def test_ancien_profil_sans_date(self, tmp_path, monkeypatch):
        monkeypatch.setattr(state, "PROFILES_DIR", tmp_path)
        s = state.default_state()
        s["profile_name"] = "SansDate"
        del s["persons"][0]["birth_date"]
        state.save_profile(s)
        assert state.load_profile("SansDate")["persons"][0]["birth_date"] == ""

    def test_pdf_avec_date(self):
        from gui import compute, report
        s = state.default_state()
        s["persons"][0]["birth_date"] = "1970-06-15"
        hh, scen = state.to_configs(s)
        results, estates = compute.simulate_with_estate(hh, scen)
        assert report.build_pdf(s, hh, scen, results, estates)[:5] == b"%PDF-"


class TestRapportPDF:
    def test_pdf_genere(self):
        from gui import compute, report
        s = state.default_state()
        s["persons"][0]["accounts"]["reer_balance"] = 200000.0
        hh, scen = state.to_configs(s)
        results, estates = compute.simulate_with_estate(hh, scen)
        pdf = report.build_pdf(s, hh, scen, results, estates)
        assert pdf[:5] == b"%PDF-"
        assert len(pdf) > 20000


@pytest.fixture(scope="module")
def sim():
    from gui import compute
    s = state.default_state()
    s["persons"][0]["accounts"]["reer_balance"] = 200000.0
    s["persons"][0]["accounts"]["celi_balance"] = 50000.0
    s["persons"][0]["accounts"]["taxable_balance"] = 80000.0
    hh, scen = state.to_configs(s)
    results, estates = compute.simulate_with_estate(hh, scen)
    return s, results, estates


class TestGraphiquesResultats:
    def test_graphiques_ont_des_traces(self, sim):
        from gui.pages import resultats_page as rp
        s, results, estates = sim
        names = [p["name"] for p in s["persons"][:len(results[0].persons)]]
        figs = [rp._withdrawals_chart(results), rp._gap_chart(results),
                rp._tax_rate_chart(results, names), rp._benefits_chart(results),
                rp._wealth_mix_chart(results), rp._estate_chart(results, estates)]
        for fig in figs:
            assert len(fig.data) >= 1

    def test_taux_effectif_protege_division(self):
        from gui.pages import resultats_page as rp
        from planner.core.simulation.types import PersonYearResult
        p = PersonYearResult(year=2030, age=60, taxable_income=0.0, tax_total=0.0)
        assert rp._effective_rate(p) == 0.0

    def test_sommaire_par_5_ans(self, sim):
        from gui.pages import resultats_page as rp
        _, results, _ = sim
        rows = rp._summary_rows(results)
        assert len(rows) == -(-len(results) // 5)
        assert rows[0]["period"].startswith(str(results[0].year))
        assert all(row["rate"].endswith("%") or row["rate"] == "—" for row in rows)

    def test_bilan_annuel(self, sim):
        from gui.pages import resultats_page as rp
        _, results, estates = sim
        rows = rp._balance_sheet_rows(results, estates)
        assert len(rows) == len(results)
        assert rows[0]["net_worth"] == rp._fmt(results[0].net_worth)
        assert rows[-1]["net_estate"] == rp._fmt(estates[-1].net_estate)

    def test_bilan_sans_succession(self, sim):
        from gui.pages import resultats_page as rp
        _, results, _ = sim
        assert rp._balance_sheet_rows(results, [])[0]["death_tax"] == "—"

    def test_cotisations(self, sim):
        from gui.pages import resultats_page as rp
        _, results, _ = sim
        rows = rp._contribution_rows(results, fmt=lambda x: round(x))
        first = rows[0]
        p = results[0].persons[0]
        assert first["contrib_reer"] == round(p.contrib_reer) and first["contrib_reer"] > 0
        assert first["total"] == round(p.contrib_reer + p.contrib_celi)
        assert first["rate"].endswith("%")
        assert first["reer_room"] == round(p.reer_room) and first["celi_room"] == round(p.celi_room)
        assert rows[-1]["cumul"] == round(sum(
            p.contrib_reer + p.contrib_celi + p.contrib_taxable for r in results for p in r.persons))
        assert len(rp._contributions_chart(results).data) >= 2
        # Vue par personne: mêmes valeurs pour une personne seule
        assert rp._contribution_rows(results, 0, fmt=lambda x: round(x))[0]["total"] == first["total"]


class TestMigrationLegacy:
    def test_cotisations_cri_migrees_vers_cd_employe(self):
        legacy = {
            "household_type": "Personne seule",
            "p1": {"name": "A", "birth_year": 1975, "salary": 80000.0},
            "contrib1": {"cri_percent": 13.0, "cri_fixed": 500.0,
                         "reer_percent": 5.0},
            "retire1": {"retirement_age": 62, "target_income": 4000.0},
        }
        s = state._migrate_legacy(legacy, "vieux")
        c = s["persons"][0]["contributions"]
        assert c["dc_employee_pct"] == 13.0
        assert c["dc_employee_fixed"] == 500.0
        assert c["reer_pct"] == 5.0
        assert s["persons"][0]["retirement_age"] == 62
        assert s["target_net_income"] == 48000.0
        assert not s["is_couple"]
