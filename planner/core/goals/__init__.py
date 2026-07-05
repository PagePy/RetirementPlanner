"""Outils d'objectifs: solveurs, plans suggérés."""

from planner.core.goals.solvers import (
    plan_succeeds, required_annual_savings, achievable_retirement_age,
    sustainable_income, optimal_benefit_ages, BenefitAgeOption)
from planner.core.goals.templates import (
    ProfileAnswers, PlanSuggestion, suggest_plan)

__all__ = [
    "plan_succeeds", "required_annual_savings", "achievable_retirement_age",
    "sustainable_income", "optimal_benefit_ages", "BenefitAgeOption",
    "ProfileAnswers", "PlanSuggestion", "suggest_plan",
]
