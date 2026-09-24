"""Tables de longévité simplifiées (probabilités de survie à 65 ans)."""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "assumptions" / "longevity.json"


@lru_cache(maxsize=1)
def load_longevity() -> dict:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


@dataclass(frozen=True)
class PlanningAge:
    probability: int   # % de chances d'atteindre cet âge (à 65 ans)
    age: int


def planning_ages(sex: str) -> list[PlanningAge]:
    """Âges de planification par probabilité de survie, décroissante."""
    table = load_longevity()["planning_ages"]
    row = table.get(sex.upper(), table["F"])
    return sorted((PlanningAge(int(p), int(a)) for p, a in row.items()),
                  key=lambda x: -x.probability)


def recommended_age(sex: str) -> int:
    """Âge recommandé par les normes (probabilité de survie de 25 %)."""
    prob = load_longevity()["recommended_probability"]
    return next(pa.age for pa in planning_ages(sex) if pa.probability == prob)


def survival_probability(sex: str, age: int) -> float:
    """Probabilité approximative (interpolation linéaire) d'atteindre `age`."""
    pts = sorted(planning_ages(sex), key=lambda x: x.age)
    if age <= 65:
        return 1.0
    if age <= pts[0].age:
        # de 100 % à 65 ans jusqu'au premier point
        return 1.0 - (1.0 - pts[0].probability / 100) * (age - 65) / (pts[0].age - 65)
    for a, b in zip(pts, pts[1:]):
        if age <= b.age:
            t = (age - a.age) / (b.age - a.age)
            return (a.probability + (b.probability - a.probability) * t) / 100
    return max(0.0, pts[-1].probability / 100 * (1 - (age - pts[-1].age) / 10))
