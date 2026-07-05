"""Base des régimes fiscaux provinciaux + registre pluggable."""
from abc import ABC, abstractmethod

from planner.core.tax.types import TaxInput, LevelTaxResult


class ProvinceTax(ABC):
    """Interface d'un régime fiscal provincial."""

    code: str = ""
    uses_federal_abatement: bool = False

    @abstractmethod
    def compute(self, inp: TaxInput, taxable_income: float, net_income: float,
                grossed_up_eligible: float, grossed_up_non_eligible: float) -> LevelTaxResult:
        ...


_REGISTRY: dict[str, type[ProvinceTax]] = {}


def register_province(cls: type[ProvinceTax]) -> type[ProvinceTax]:
    _REGISTRY[cls.code] = cls
    return cls


def get_province_tax(code: str, year: int) -> ProvinceTax:
    # Import paresseux pour enregistrer les provinces disponibles.
    import planner.core.tax.quebec  # noqa: F401
    if code not in _REGISTRY:
        raise ValueError(
            f"Province '{code}' non supportée. Disponibles: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[code](year)


def supported_provinces() -> list[str]:
    import planner.core.tax.quebec  # noqa: F401
    return sorted(_REGISTRY)
