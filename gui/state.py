"""État de l'application et gestion des profils (sauvegarde/chargement/migration)."""
import json
from pathlib import Path

from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig,
    DebtConfig, RealAssetConfig, VehicleReplacementConfig)

PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"


def default_person(name: str = "") -> dict:
    return {
        "name": name, "birth_year": 1970, "retirement_age": 65,
        "life_expectancy": 92, "salary": 70000.0, "salary_growth": 2.0,
        "db_pension": 0.0, "db_start_age": 65, "db_normal_age": 65,
        "db_penalty": 6.0, "db_indexed": True,
        "rrq_monthly_at_65": 1000.0, "rrq_start_age": 65,
        "oas_start_age": 65, "oas_residence_years": 40,
        "accounts": {
            "reer_balance": 0.0, "reer_room": 0.0,
            "celi_balance": 0.0, "celi_room": 7000.0,
            "celiapp_balance": 0.0, "cri_balance": 0.0,
            "ferr_balance": 0.0, "frv_balance": 0.0,
            "taxable_balance": 0.0, "taxable_acb": None,
            "reer_return": 5.0, "celi_return": 5.0, "celiapp_return": 4.0,
            "cri_return": 5.0, "ferr_return": 4.0, "frv_return": 4.0,
            "taxable_return": 4.0,
            "taxable_interest_ratio": 30.0, "taxable_dividend_ratio": 30.0,
        },
        "contributions": {
            "reer_pct": 10.0, "reer_fixed": 0.0,
            "celi_pct": 0.0, "celi_fixed": 7000.0,
            "celiapp_fixed": 0.0,
            "taxable_pct": 0.0, "taxable_fixed": 0.0,
        },
    }


def default_state() -> dict:
    return {
        "profile_name": "MonProfil",
        "is_couple": False,
        "province": "QC",
        "target_net_income": 60000.0,
        "target_indexed": True,
        "celi_strategy": "dernier",
        "inflation": 2.0,
        "start_year": 2026,
        "use_spouse_age_for_ferr": False,
        "persons": [default_person("Personne 1"), default_person("Personne 2")],
        "debts": [],
        "assets": [],
        "vehicles": [],
        "special_expenses": [],
    }


# ==================== CONVERSION VERS LE MOTEUR ====================

def _person_config(p: dict) -> PersonConfig:
    a, c = p["accounts"], p["contributions"]
    return PersonConfig(
        name=p["name"], birth_year=int(p["birth_year"]),
        retirement_age=int(p["retirement_age"]),
        life_expectancy=int(p["life_expectancy"]),
        salary=float(p["salary"]), salary_growth=float(p["salary_growth"]) / 100,
        db_pension=float(p["db_pension"]),
        db_start_age=int(p["db_start_age"]), db_normal_age=int(p["db_normal_age"]),
        db_penalty_per_year=float(p["db_penalty"]) / 100,
        db_indexed=bool(p.get("db_indexed", True)),
        rrq_monthly_at_65=float(p["rrq_monthly_at_65"]),
        rrq_start_age=int(p["rrq_start_age"]),
        oas_start_age=int(p["oas_start_age"]),
        oas_residence_years=int(p.get("oas_residence_years", 40)),
        accounts=AccountsConfig(
            reer_balance=float(a["reer_balance"]), reer_room=float(a["reer_room"]),
            celi_balance=float(a["celi_balance"]), celi_room=float(a["celi_room"]),
            celiapp_balance=float(a["celiapp_balance"]),
            cri_balance=float(a["cri_balance"]),
            ferr_balance=float(a["ferr_balance"]), frv_balance=float(a["frv_balance"]),
            taxable_balance=float(a["taxable_balance"]),
            taxable_acb=(float(a["taxable_acb"])
                         if a.get("taxable_acb") not in (None, "") else None),
            reer_return=float(a["reer_return"]) / 100,
            celi_return=float(a["celi_return"]) / 100,
            celiapp_return=float(a["celiapp_return"]) / 100,
            cri_return=float(a["cri_return"]) / 100,
            ferr_return=float(a["ferr_return"]) / 100,
            frv_return=float(a["frv_return"]) / 100,
            taxable_return=float(a["taxable_return"]) / 100,
            taxable_interest_ratio=float(a["taxable_interest_ratio"]) / 100,
            taxable_dividend_ratio=float(a["taxable_dividend_ratio"]) / 100,
            taxable_growth_ratio=max(0.0, 1.0
                                     - float(a["taxable_interest_ratio"]) / 100
                                     - float(a["taxable_dividend_ratio"]) / 100),
        ),
        contributions=ContributionsConfig(
            reer_pct=float(c["reer_pct"]) / 100, reer_fixed=float(c["reer_fixed"]),
            celi_pct=float(c["celi_pct"]) / 100, celi_fixed=float(c["celi_fixed"]),
            celiapp_fixed=float(c["celiapp_fixed"]),
            taxable_pct=float(c["taxable_pct"]) / 100,
            taxable_fixed=float(c["taxable_fixed"]),
        ),
    )


def to_configs(state: dict) -> tuple[HouseholdConfig, ScenarioConfig]:
    """Construit les configurations moteur à partir de l'état UI."""
    persons = [state["persons"][0]] + (
        [state["persons"][1]] if state["is_couple"] else [])
    hh = HouseholdConfig(
        persons=[_person_config(p) for p in persons],
        province=state["province"],
        target_net_income=float(state["target_net_income"]),
        target_indexed=bool(state["target_indexed"]),
        celi_strategy=state["celi_strategy"],
        special_expenses={int(e["year"]): float(e["amount"])
                          for e in state["special_expenses"]},
        debts=[DebtConfig(name=d["name"], balance=float(d["balance"]),
                          interest_rate=float(d["rate"]) / 100,
                          annual_payment=float(d["payment"]), kind=d["kind"])
               for d in state["debts"]],
        real_assets=[RealAssetConfig(
            name=a["name"], value=float(a["value"]), kind=a["kind"],
            appreciation=float(a["appreciation"]) / 100,
            is_principal_residence=bool(a["is_principal_residence"]),
            cost_base=(float(a["cost_base"])
                       if a.get("cost_base") not in (None, "") else None),
            sale_year=(int(a["sale_year"]) if a.get("sale_year") else None),
            linked_debt=a.get("linked_debt") or None)
            for a in state["assets"]],
        vehicle_plans=[VehicleReplacementConfig(
            name=v["name"], first_year=int(v["first_year"]),
            every_years=int(v["every_years"]), net_cost=float(v["net_cost"]),
            last_year=(int(v["last_year"]) if v.get("last_year") else None))
            for v in state["vehicles"]],
        use_spouse_age_for_ferr=bool(state["use_spouse_age_for_ferr"]),
    )
    scen = ScenarioConfig(start_year=int(state["start_year"]),
                          inflation=float(state["inflation"]) / 100)
    return hh, scen


# ==================== PROFILS ====================

def list_profiles() -> list[str]:
    PROFILES_DIR.mkdir(exist_ok=True)
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def save_profile(state: dict) -> Path:
    PROFILES_DIR.mkdir(exist_ok=True)
    path = PROFILES_DIR / f"{state['profile_name']}.json"
    data = {"format": "v2", **{k: v for k, v in state.items()}}
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path


def load_profile(name: str) -> dict:
    """Charge un profil v2, ou migre automatiquement un ancien profil Streamlit."""
    data = json.loads((PROFILES_DIR / f"{name}.json").read_text(encoding="utf-8"))
    if data.get("format") == "v2":
        state = default_state()
        for key in state:
            if key in data:
                state[key] = data[key]
        # compléter les personnes manquantes
        while len(state["persons"]) < 2:
            state["persons"].append(default_person("Personne 2"))
        return state
    return _migrate_legacy(data, name)


def _migrate_legacy(data: dict, name: str) -> dict:
    """Migre un profil de l'ancienne application Streamlit."""
    state = default_state()
    state["profile_name"] = data.get("profile_name", name)
    state["is_couple"] = "Couple" in str(data.get("household_type", ""))
    state["inflation"] = float(data.get("inflation", 2.0))

    target_total = 0.0
    for i, (pk, ak, ck, rk) in enumerate(
            (("p1", "acc1", "contrib1", "retire1"),
             ("p2", "acc2", "contrib2", "retire2"))):
        if pk not in data or not data[pk]:
            continue
        p, acc = data[pk], data.get(ak, {}) or {}
        contrib, ret = data.get(ck, {}) or {}, data.get(rk, {}) or {}
        person = state["persons"][i]
        person.update({
            "name": p.get("name", f"Personne {i+1}"),
            "birth_year": int(p.get("birth_year", 1970)),
            "life_expectancy": int(p.get("life_expectancy", 92)),
            "salary": float(p.get("salary", 0.0)),
            "salary_growth": float(p.get("salary_increase", 2.0)),
            "retirement_age": int(ret.get("retirement_age", 65)),
            "rrq_monthly_at_65": float(ret.get("rrq_amount_65", 1000.0)),
            "rrq_start_age": int(ret.get("rrq_age", 65)),
            "oas_start_age": int(ret.get("oas_age", 65)),
            "db_pension": float(ret.get("rente_pd", 0.0)),
            "db_start_age": int(ret.get("rente_pd_age_debut", 65)),
            "db_normal_age": int(ret.get("rente_pd_age_normal", 65)),
            "db_penalty": float(ret.get("rente_pd_penalite_annuelle", 6.0)),
        })
        person["accounts"].update({
            "reer_balance": float(acc.get("REER_balance", 0.0)),
            "celi_balance": float(acc.get("CELI_balance", 0.0)),
            "cri_balance": float(acc.get("CRI_balance", 0.0)),
            "ferr_balance": float(acc.get("FERR_balance", 0.0)),
            "frv_balance": float(acc.get("FRV_balance", 0.0)),
            "taxable_balance": float(acc.get("Taxable_balance", 0.0)),
            "reer_return": float(acc.get("REER_return", 5.0)),
            "celi_return": float(acc.get("CELI_return", 5.0)),
            "cri_return": float(acc.get("CRI_return", 5.0)),
            "ferr_return": float(acc.get("FERR_return", 4.0)),
            "frv_return": float(acc.get("FRV_return", 4.0)),
            "taxable_return": float(acc.get("Taxable_return", 4.0)),
        })
        person["contributions"].update({
            "reer_pct": float(contrib.get("reer_percent", 0.0)),
            "reer_fixed": float(contrib.get("reer_fixed", 0.0)),
            "celi_pct": float(contrib.get("celi_percent", 0.0)),
            "celi_fixed": float(contrib.get("celi_fixed", 0.0)),
            "taxable_pct": float(contrib.get("nonreg_percent", 0.0)),
            "taxable_fixed": float(contrib.get("nonreg_fixed", 0.0)),
        })
        target_total += float(ret.get("target_income", 0.0)) * 12
        state["celi_strategy"] = ret.get("celi_strategy", "dernier")
        if state["celi_strategy"] not in ("dernier", "jamais"):
            state["celi_strategy"] = "dernier"

    if target_total > 0:
        state["target_net_income"] = target_total
    for proj in data.get("special_projects", []) or []:
        state["special_expenses"].append({
            "name": proj.get("name", "Projet"),
            "year": int(proj.get("year", 2030)),
            "amount": float(proj.get("amount", 0.0))})
    return state
