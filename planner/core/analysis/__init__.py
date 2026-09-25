"""Analyses de décaissement: succession, stress, Monte Carlo, stratégies."""

from planner.core.analysis.succession import (
    EstateResult, estate_at_death, estate_timeline)
from planner.core.analysis.stress import (
    StressOutcome, run_baseline, run_market_crash, run_sequence_risk,
    run_high_inflation, run_longevity, run_premature_death, run_all_stress_tests)
from planner.core.analysis.monte_carlo import MonteCarloResult, run_monte_carlo
from planner.core.analysis.strategies import (
    StrategyOutcome, compare_strategies, STANDARD_ORDERS,
    IncomeFloorOutcome, compare_income_floors, DEFAULT_FLOORS)
from planner.core.analysis.tax_attribution import TaxAttribution, attribute_taxes
from planner.core.analysis.tax_sheet import TaxSheet, build_tax_sheet
from planner.core.analysis.verification import Verification, verify

__all__ = [
    "EstateResult", "estate_at_death", "estate_timeline",
    "StressOutcome", "run_baseline", "run_market_crash", "run_sequence_risk",
    "run_high_inflation", "run_longevity", "run_premature_death",
    "run_all_stress_tests",
    "MonteCarloResult", "run_monte_carlo",
    "StrategyOutcome", "compare_strategies", "STANDARD_ORDERS",
    "IncomeFloorOutcome", "compare_income_floors", "DEFAULT_FLOORS",
    "TaxAttribution", "attribute_taxes",
    "TaxSheet", "build_tax_sheet",
    "Verification", "verify",
]
