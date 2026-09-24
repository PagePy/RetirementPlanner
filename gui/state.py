"""État de l'application et gestion des profils (sauvegarde/chargement/migration)."""
import json
import re
from datetime import datetime
from pathlib import Path

from planner.core.simulation import (
    AccountsConfig, ContributionsConfig, PersonConfig,
    HouseholdConfig, ScenarioConfig, AnnuityConfig, LifeInsuranceConfig,
    DebtConfig, RealAssetConfig, VehicleReplacementConfig)

PROFILES_DIR = Path(__file__).resolve().parents[1] / "profiles"
_PROFILE_NAME_RE = re.compile(r"^[\w\- .]+$")


def profile_path(name: str) -> Path:
    """Chemin du fichier de profil; refuse tout nom sortant de PROFILES_DIR."""
    name = (name or "").strip()
    if not name or ".." in name or not _PROFILE_NAME_RE.match(name):
        raise ValueError(
            "Nom de profil invalide: lettres, chiffres, espaces, '-', '_' et '.' seulement")
    path = (PROFILES_DIR / f"{name}.json").resolve()
    if path.parent != PROFILES_DIR.resolve():
        raise ValueError("Nom de profil invalide")
    return path


def _coerce_float(value, default: float = 0.0) -> float:
    return default if value in (None, "") else float(value)


def _normalize_db_status(value: str | None, db_pension: float) -> str:
    if value in {"none", "active", "deferred", "closed_salary_linked", "in_payment"}:
        return value
    return "active" if db_pension > 0 else "none"


def _normalize_person_state(person: dict) -> None:
    person.setdefault("db_indexed", True)
    person.setdefault("retirement_month", 1)
    person.setdefault("sex", "F")
    person.setdefault("part_time_income", 0.0)
    person.setdefault("part_time_until_age", 0)
    person.setdefault("medical_expenses", 0.0)
    person.setdefault("donations", 0.0)
    person.setdefault("home_support_expenses", 0.0)
    accounts = person.setdefault("accounts", {})
    accounts.setdefault("fee_rate", 0.0)
    accounts.setdefault("retirement_return_delta", 0.0)
    contributions = person.setdefault("contributions", {})
    contributions.setdefault("celi_fixed_indexed", False)
    contributions.setdefault("celi_overflow_to_taxable", True)
    contributions.setdefault("spousal_reer_pct", 0.0)
    contributions.setdefault("spousal_reer_fixed", 0.0)
    person["db_pension"] = _coerce_float(person.get("db_pension"))
    person["db_active_growth"] = _coerce_float(
        person.get("db_active_growth"), _coerce_float(person.get("salary_growth"), 2.0))
    person["db_status"] = _normalize_db_status(
        person.get("db_status"), person["db_pension"])


def default_person(name: str = "") -> dict:
    return {
        "name": name, "birth_year": 1970, "retirement_age": 65,
        "retirement_month": 1, "sex": "F",
        "life_expectancy": 92, "salary": 70000.0, "salary_growth": 2.0,
        "part_time_income": 0.0, "part_time_until_age": 0,
        "medical_expenses": 0.0, "donations": 0.0, "home_support_expenses": 0.0,
        "db_status": "none",
        "db_pension": 0.0, "db_start_age": 65, "db_normal_age": 65,
        "db_penalty": 6.0, "db_indexed": True, "db_active_growth": 2.0,
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
            "fee_rate": 0.0, "retirement_return_delta": 0.0,
        },
        "contributions": {
            "reer_pct": 10.0, "reer_fixed": 0.0,
            "spousal_reer_pct": 0.0, "spousal_reer_fixed": 0.0,
            "celi_pct": 0.0, "celi_fixed": 7000.0,
            "celi_fixed_indexed": False, "celi_overflow_to_taxable": True,
            "celiapp_fixed": 0.0,
            "taxable_pct": 0.0, "taxable_fixed": 0.0,
            "dc_employee_pct": 0.0, "dc_employee_fixed": 0.0,
            "dc_employer_pct": 0.0, "dc_employer_fixed": 0.0,
        },
    }


def default_state() -> dict:
    return {
        "profile_name": "MonProfil",
        "is_couple": False,
        "persons_side_by_side": False,
        "province": "QC",
        "target_net_income": 60000.0,
        "target_indexed": True,
        "celi_strategy": "dernier",
        "inflation": 2.0,
        "start_year": 2026,
        "use_spouse_age_for_ferr": False,
        "rrq_sharing": False,
        "rrq_share_fraction": 100.0,
        "taxable_income_floor": None,
        "persons": [default_person("Personne 1"), default_person("Personne 2")],
        "debts": [],
        "assets": [],
        "vehicles": [],
        "special_expenses": [],
        "annuities": [],
        "life_insurances": [],
    }


# ==================== CONVERSION VERS LE MOTEUR ====================

def _person_config(p: dict) -> PersonConfig:
    a, c = p["accounts"], p["contributions"]
    db_pension = _coerce_float(p.get("db_pension"))
    return PersonConfig(
        name=p["name"], birth_year=int(p["birth_year"]),
        retirement_age=int(p["retirement_age"]),
        retirement_month=int(p.get("retirement_month") or 1),
        life_expectancy=int(p["life_expectancy"]),
        sex=p.get("sex") or "F",
        salary=float(p["salary"]), salary_growth=float(p["salary_growth"]) / 100,
        part_time_income=_coerce_float(p.get("part_time_income")),
        part_time_until_age=int(p.get("part_time_until_age") or 0),
        medical_expenses=_coerce_float(p.get("medical_expenses")),
        donations=_coerce_float(p.get("donations")),
        home_support_expenses=_coerce_float(p.get("home_support_expenses")),
        db_status=_normalize_db_status(p.get("db_status"), db_pension),
        db_pension=db_pension,
        db_start_age=int(p["db_start_age"]), db_normal_age=int(p["db_normal_age"]),
        db_penalty_per_year=float(p["db_penalty"]) / 100,
        db_indexed=bool(p.get("db_indexed", True)),
        db_active_growth=_coerce_float(p.get("db_active_growth")) / 100,
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
            fee_rate=_coerce_float(a.get("fee_rate")) / 100,
            retirement_return_delta=_coerce_float(a.get("retirement_return_delta")) / 100,
        ),
        contributions=ContributionsConfig(
            reer_pct=_coerce_float(c.get("reer_pct")) / 100,
            reer_fixed=_coerce_float(c.get("reer_fixed")),
            spousal_reer_pct=_coerce_float(c.get("spousal_reer_pct")) / 100,
            spousal_reer_fixed=_coerce_float(c.get("spousal_reer_fixed")),
            celi_pct=_coerce_float(c.get("celi_pct")) / 100,
            celi_fixed=_coerce_float(c.get("celi_fixed")),
            celi_fixed_indexed=bool(c.get("celi_fixed_indexed", False)),
            celi_overflow_to_taxable=bool(c.get("celi_overflow_to_taxable", True)),
            celiapp_fixed=_coerce_float(c.get("celiapp_fixed")),
            taxable_pct=_coerce_float(c.get("taxable_pct")) / 100,
            taxable_fixed=_coerce_float(c.get("taxable_fixed")),
            dc_employee_pct=_coerce_float(c.get("dc_employee_pct")) / 100,
            dc_employee_fixed=_coerce_float(c.get("dc_employee_fixed")),
            dc_employer_pct=_coerce_float(c.get("dc_employer_pct")) / 100,
            dc_employer_fixed=_coerce_float(c.get("dc_employer_fixed")),
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
            linked_debt=a.get("linked_debt") or None,
            net_rental_income=_coerce_float(a.get("net_rental_income")),
            cca_rate=_coerce_float(a.get("cca_rate")) / 100,
            ucc=(float(a["ucc"]) if a.get("ucc") not in (None, "") else None))
            for a in state["assets"]],
        vehicle_plans=[VehicleReplacementConfig(
            name=v["name"], first_year=int(v["first_year"]),
            every_years=int(v["every_years"]), net_cost=float(v["net_cost"]),
            last_year=(int(v["last_year"]) if v.get("last_year") else None))
            for v in state["vehicles"]],
        annuities=[AnnuityConfig(
            name=an.get("name") or "Rente viagère",
            person_index=int(an.get("person_index") or 0),
            purchase_year=int(an["purchase_year"]),
            premium=float(an["premium"]), annual_payment=float(an["annual_payment"]),
            source=an.get("source") or "reer", indexed=bool(an.get("indexed", False)))
            for an in state.get("annuities", [])],
        life_insurances=[LifeInsuranceConfig(
            name=ins.get("name") or "Assurance vie",
            person_index=int(ins.get("person_index") or 0),
            face_amount=float(ins["face_amount"]),
            annual_premium=float(ins["annual_premium"]),
            premium_until_age=int(ins.get("premium_until_age") or 100),
            coverage_until_age=int(ins.get("coverage_until_age") or 120))
            for ins in state.get("life_insurances", [])],
        use_spouse_age_for_ferr=bool(state["use_spouse_age_for_ferr"]),
        rrq_sharing=bool(state.get("rrq_sharing", False)),
        rrq_share_fraction=_coerce_float(state.get("rrq_share_fraction"), 100.0) / 100,
        taxable_income_floor=(float(state["taxable_income_floor"])
                              if state.get("taxable_income_floor") else None),
    )
    scen = ScenarioConfig(start_year=int(state["start_year"]),
                          inflation=float(state["inflation"]) / 100)
    return hh, scen


# ==================== PROFILS ====================

def list_profiles() -> list[str]:
    PROFILES_DIR.mkdir(exist_ok=True)
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def save_profile(state: dict) -> Path:
    path = profile_path(state["profile_name"])
    PROFILES_DIR.mkdir(exist_ok=True)
    data = {"format": "v2", **{k: v for k, v in state.items()}}
    data["persons"] = [dict(person) for person in state["persons"]]
    for person in data["persons"]:
        _normalize_person_state(person)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if path.exists() and path.read_text(encoding="utf-8") != text:
        _archive_version(path)
    path.write_text(text, encoding="utf-8")
    return path


# ==================== HISTORIQUE ====================

HISTORY_DIRNAME = "history"
MAX_VERSIONS = 50


def _history_dir(name: str) -> Path:
    return profile_path(name).parent / HISTORY_DIRNAME / profile_path(name).stem


def _archive_version(path: Path) -> Path:
    """Copie la version courante du profil dans l'historique avant écrasement."""
    hist = path.parent / HISTORY_DIRNAME / path.stem
    hist.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    target = hist / f"{stamp}.json"
    n = 1
    while target.exists():
        n += 1
        target = hist / f"{stamp}_{n}.json"
    target.write_bytes(path.read_bytes())
    for old in sorted(hist.glob("*.json"))[:-MAX_VERSIONS]:
        old.unlink()
    return target


def profile_history(name: str) -> list[Path]:
    """Versions archivées d'un profil, de la plus récente à la plus ancienne."""
    hist = _history_dir(name)
    if not hist.exists():
        return []
    return sorted(hist.glob("*.json"), reverse=True)


def load_version(path: Path) -> dict:
    """Charge une version archivée (même normalisation qu'un profil)."""
    if path.resolve().parent.parent != (PROFILES_DIR / HISTORY_DIRNAME).resolve():
        raise ValueError("Version hors de l'historique")
    data = json.loads(path.read_text(encoding="utf-8"))
    state = default_state()
    for key in state:
        if key in data:
            state[key] = data[key]
    while len(state["persons"]) < 2:
        state["persons"].append(default_person("Personne 2"))
    for person in state["persons"]:
        _normalize_person_state(person)
    return state


def _flatten(obj, prefix: str = "") -> dict[str, object]:
    out = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(_flatten(v, f"{prefix}{k}."))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            label = v.get("name") if isinstance(v, dict) and v.get("name") else str(i)
            out.update(_flatten(v, f"{prefix}[{label}]."))
    else:
        out[prefix[:-1]] = obj
    return out


def diff_states(old: dict, new: dict) -> list[dict]:
    """Différences champ par champ: [{"path", "old", "new"}], triées par chemin."""
    a, b = _flatten(old), _flatten(new)
    changes = []
    for key in sorted(set(a) | set(b)):
        if a.get(key, "∅") != b.get(key, "∅"):
            changes.append({"path": key, "old": a.get(key, "∅"), "new": b.get(key, "∅")})
    return changes


def load_profile(name: str) -> dict:
    """Charge un profil v2, ou migre automatiquement un ancien profil Streamlit."""
    data = json.loads(profile_path(name).read_text(encoding="utf-8"))
    if data.get("format") == "v2":
        state = default_state()
        for key in state:
            if key in data:
                state[key] = data[key]
        # compléter les personnes manquantes
        while len(state["persons"]) < 2:
            state["persons"].append(default_person("Personne 2"))
        for person in state["persons"]:
            _normalize_person_state(person)
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
            "db_status": _normalize_db_status(
                ret.get("db_status"), float(ret.get("rente_pd", 0.0))),
            "db_start_age": int(ret.get("rente_pd_age_debut", 65)),
            "db_normal_age": int(ret.get("rente_pd_age_normal", 65)),
            "db_penalty": float(ret.get("rente_pd_penalite_annuelle", 6.0)),
        })
        _normalize_person_state(person)
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
            # L'ancien CRI était alimenté par les cotisations de l'employé (régime CD)
            "dc_employee_pct": float(contrib.get("cri_percent", 0.0)),
            "dc_employee_fixed": float(contrib.get("cri_fixed", 0.0)),
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
