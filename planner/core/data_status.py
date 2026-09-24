"""État des jeux de paramètres (fiscalité, prestations, comptes) pour une année.

Permet d'avertir l'utilisateur quand la simulation repose sur des valeurs
estimées (indexées) plutôt que sur les publications officielles.
"""
from dataclasses import dataclass

from planner.core.accounts.params import load_account_params
from planner.core.benefits.params import load_benefits
from planner.core.tax.params import load_params


@dataclass(frozen=True)
class ParamSetStatus:
    name: str            # ex. "Impôt fédéral"
    requested_year: int
    effective_year: int  # année réellement chargée (repli sur la plus récente)
    estimated: bool
    note: str

    @property
    def reliable(self) -> bool:
        return not self.estimated and self.effective_year == self.requested_year


_PROVINCE_FILES = {"QC": "quebec"}


def data_status(year: int, province: str = "QC") -> list[ParamSetStatus]:
    """Statut de chaque jeu de paramètres utilisé pour `year`."""
    prov_file = _PROVINCE_FILES.get(province, province.lower())
    sets = [
        ("Impôt fédéral", load_params(year, "federal")),
        (f"Impôt provincial ({province})", load_params(year, prov_file)),
        ("Prestations (RRQ/SV/SRG)", load_benefits(year)),
        ("Comptes (REER/CELI/FERR)", load_account_params(year)),
    ]
    return [
        ParamSetStatus(name=name, requested_year=year,
                       effective_year=p["_effective_year"],
                       estimated=bool(p.get("estimated", False)),
                       note=p.get("note", ""))
        for name, p in sets
    ]


def unreliable_sets(year: int, province: str = "QC") -> list[ParamSetStatus]:
    """Jeux estimés ou chargés par repli sur une autre année."""
    return [s for s in data_status(year, province) if not s.reliable]


def warning_message(year: int, province: str = "QC") -> str:
    """Texte d'avertissement pour l'interface; vide si tout est confirmé."""
    bad = unreliable_sets(year, province)
    if not bad:
        return ""
    parts = []
    for s in bad:
        if s.effective_year != s.requested_year:
            parts.append(f"{s.name}: barèmes {s.effective_year} (année {s.requested_year} indisponible)")
        else:
            parts.append(f"{s.name}: valeurs {s.effective_year} estimées")
    return "Paramètres non confirmés — " + "; ".join(parts)
