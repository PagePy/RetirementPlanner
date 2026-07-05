"""Chargement des paramètres de comptes versionnés + tables FERR/FRV."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "accounts"


def available_years() -> list[int]:
    return sorted(int(p.name) for p in DATA_DIR.iterdir() if p.is_dir() and p.name.isdigit())


@lru_cache(maxsize=32)
def load_account_params(year: int) -> dict:
    years = available_years()
    candidates = [y for y in years if y <= year]
    effective_year = max(candidates) if candidates else min(years)
    with open(DATA_DIR / str(effective_year) / "accounts.json", encoding="utf-8") as f:
        params = json.load(f)
    params["_effective_year"] = effective_year
    return params


@lru_cache(maxsize=1)
def load_rrif_factors() -> dict:
    with open(DATA_DIR / "rrif_lif_factors.json", encoding="utf-8") as f:
        return json.load(f)
