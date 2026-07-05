# models/household.py
from dataclasses import dataclass
from typing import Optional
from .person import Person

@dataclass
class Household:
    primary: Person
    spouse: Optional[Person] = None

    def is_couple(self) -> bool:
        return self.spouse is not None

    def ages_in_year(self, year: int):
        a1 = self.primary.age_in_year(year)
        a2 = self.spouse.age_in_year(year) if self.spouse else None
        return a1, a2