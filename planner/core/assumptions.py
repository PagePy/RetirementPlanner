"""Normes d'hypothèses de projection (IQPF / FP Canada)."""
import json
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "assumptions"


@lru_cache(maxsize=4)
def load_iqpf(year: int | None = None) -> dict:
    """Charge les normes IQPF de `year` (défaut: plus récentes disponibles)."""
    files = sorted(DATA_DIR.glob("iqpf_*.json"))
    if not files:
        raise FileNotFoundError(f"Aucune norme IQPF dans {DATA_DIR}")
    if year is not None:
        match = [f for f in files if f.stem.endswith(str(year))]
        files = match or files
    with open(files[-1], encoding="utf-8") as f:
        return json.load(f)


def portfolio_return(portfolio: str, norms: dict | None = None) -> float:
    """Rendement brut attendu d'un portefeuille type (moyenne pondérée)."""
    norms = norms or load_iqpf()
    weights = norms["portfolios"][portfolio]["weights"]
    returns = norms["asset_returns"]
    return sum(w * returns[k] for k, w in weights.items())


def portfolio_labels(norms: dict | None = None) -> dict[str, str]:
    norms = norms or load_iqpf()
    return {k: v["label"] for k, v in norms["portfolios"].items()}
