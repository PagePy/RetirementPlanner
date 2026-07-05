# models/special_projects.py
from dataclasses import dataclass
from typing import List

@dataclass
class SpecialProject:
    year: int
    amount: float
    person: str = "household"  # "primary", "spouse", ou "household"
    description: str = ""

def total_projects_for_year(projects: List[SpecialProject], year: int, person: str = None) -> float:
    total = 0.0
    for p in projects:
        if p.year == year:
            if person is None or p.person == person or p.person == "household":
                total += p.amount
    return total