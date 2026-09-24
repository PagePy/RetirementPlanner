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
