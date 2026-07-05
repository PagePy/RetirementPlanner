"""Moteur fiscal: fédéral + provinces pluggables."""

from planner.core.tax.types import TaxInput, TaxResult
from planner.core.tax.calculator import TaxCalculator

__all__ = ["TaxInput", "TaxResult", "TaxCalculator"]
