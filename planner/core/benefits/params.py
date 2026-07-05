"""Chargement des paramètres de prestations versionnés par année."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "benefits"


def available_years() -> list[int]:
    return sorted(int(p.name) for p in DATA_DIR.iterdir() if p.is_dir() and p.name.isdigit())


@lru_cache(maxsize=32)
def load_benefits(year: int) -> dict:
    """Charge les paramètres de prestations pour `year` (repli: dernière année <= year)."""
    years = available_years()
    if not years:
        raise FileNotFoundError(f"Aucune donnée de prestations dans {DATA_DIR}")
    candidates = [y for y in years if y <= year]
    effective_year = max(candidates) if candidates else min(years)
    with open(DATA_DIR / str(effective_year) / "benefits.json", encoding="utf-8") as f:
        params = json.load(f)
    params["_effective_year"] = effective_year
    return params
