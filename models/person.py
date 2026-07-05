# models/person.py
from dataclasses import dataclass

@dataclass
class Person:
    name: str
    birth_year: int
    province: str = "QC"
    salary: float = 0.0
    salary_growth: float = 0.02
    retirement_year: int = 2035
    rrq_start_age: int = 65
    oas_start_age: int = 65
    marital_status: str = "single"  # "single" ou "couple"

    def age_in_year(self, year: int) -> int:
        return year - self.birth_year

    def is_retired(self, year: int) -> bool:
        return year >= self.retirement_year