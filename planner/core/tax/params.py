"""Chargement des paramètres fiscaux versionnés par année (JSON)."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "tax"


class TaxParamsError(Exception):
    pass


def available_years() -> list[int]:
    return sorted(int(p.name) for p in DATA_DIR.iterdir() if p.is_dir() and p.name.isdigit())


@lru_cache(maxsize=64)
def load_params(year: int, name: str) -> dict:
    """Charge les paramètres `name` (ex: 'federal', 'quebec') pour `year`.

    Si l'année demandée n'existe pas, utilise la plus récente disponible
    (les projections futures réutilisent les derniers barèmes connus; le
    moteur de simulation applique ensuite sa propre indexation).
    """
    years = available_years()
    if not years:
        raise TaxParamsError(f"Aucune donnée fiscale dans {DATA_DIR}")
    effective_year = year if year in years else max(y for y in years if y <= year) if any(y <= year for y in years) else min(years)
    path = DATA_DIR / str(effective_year) / f"{name}.json"
    if not path.exists():
        raise TaxParamsError(f"Paramètres '{name}' introuvables pour {effective_year} ({path})")
    with open(path, encoding="utf-8") as f:
        params = json.load(f)
    params["_effective_year"] = effective_year
    return params


def bracket_tax(taxable_income: float, brackets: list) -> float:
    """Impôt par tranches. `brackets` = [[seuil_max, taux], ..., [null, taux]]."""
    if taxable_income <= 0:
        return 0.0
    tax = 0.0
    lower = 0.0
    for threshold, rate in brackets:
        upper = taxable_income if threshold is None else min(taxable_income, float(threshold))
        if upper > lower:
            tax += (upper - lower) * rate
        if threshold is None or taxable_income <= threshold:
            break
        lower = float(threshold)
    return tax
