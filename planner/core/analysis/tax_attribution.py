"""D'où vient l'impôt: attribution de l'impôt annuel aux sources de revenu.

Méthode: l'impôt de chaque personne-année est réparti entre ses sources au
prorata de leur part du revenu imposable (gains en capital inclus à 50 %).
La récupération de la SV et l'impôt au décès sont des catégories directes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from planner.core.analysis.succession import EstateResult
from planner.core.simulation.types import HouseholdYearResult, PersonYearResult

SOURCES = [
    "Emploi et loyers",
    "Rentes d'employeur",
    "RRQ et SV",
    "Retraits REER/FERR/FRV",
    "Placements non enregistrés",
]
CLAWBACK = "Récupération SV"
DEATH_TAX = "Impôt au décès"


def _taxable_weights(p: PersonYearResult) -> dict[str, float]:
    deductions = p.contrib_reer + p.contrib_spousal_reer + p.contrib_celiapp
    return {
        "Emploi et loyers": max(
            0.0, p.salary + p.part_time_income + p.rental_income - deductions),
        "Rentes d'employeur": max(
            0.0, p.db_pension + p.annuity_income + p.pension_split_received),
        "RRQ et SV": p.rrq + p.oas,
        "Retraits REER/FERR/FRV": p.wd_reer + p.wd_ferr + p.wd_frv + p.spousal_attributed,
        "Placements non enregistrés": (p.investment_interest + p.investment_dividends
                                       + 0.5 * p.wd_taxable_gain),
    }


def _gross(p: PersonYearResult) -> dict[str, float]:
    return {
        "Emploi et loyers": p.salary + p.part_time_income + p.rental_income,
        "Rentes d'employeur": p.db_pension + p.annuity_income,
        "RRQ et SV": p.rrq + p.oas,
        "Retraits REER/FERR/FRV": p.wd_reer + p.wd_ferr + p.wd_frv,
        "Placements non enregistrés": (p.investment_interest + p.investment_dividends
                                       + p.wd_taxable_gain),
    }


@dataclass
class TaxAttribution:
    years: list[int]
    tax_by_year: dict[str, list[float]]    # source (incl. CLAWBACK) → impôt par année
    gross_by_year: dict[str, list[float]]  # source → revenu brut par année
    death_tax: float = 0.0
    death_year: int | None = None
    total_tax: float = 0.0                 # impôts + récupération SV à vie (hors décès)

    def lifetime(self) -> list[dict]:
        """Une ligne par source: brut, impôt attribué, part, taux effectif moyen."""
        grand_total = self.total_tax + self.death_tax
        rows = []
        for source in SOURCES:
            tax = sum(self.tax_by_year[source])
            gross = sum(self.gross_by_year[source])
            rows.append({"source": source, "gross": gross, "tax": tax,
                         "share": tax / grand_total if grand_total > 0 else 0.0,
                         "rate": tax / gross if gross > 0 else 0.0})
        clawback = sum(self.tax_by_year[CLAWBACK])
        rows.append({"source": CLAWBACK, "gross": sum(self.gross_by_year["RRQ et SV"]),
                     "tax": clawback,
                     "share": clawback / grand_total if grand_total > 0 else 0.0,
                     "rate": None})
        rows.append({"source": DEATH_TAX, "gross": None, "tax": self.death_tax,
                     "share": self.death_tax / grand_total if grand_total > 0 else 0.0,
                     "rate": None})
        return rows


def attribute_taxes(results: list[HouseholdYearResult],
                    estates: list[EstateResult] | None = None) -> TaxAttribution:
    years = [r.year for r in results]
    tax_by_year = {s: [0.0] * len(years) for s in SOURCES + [CLAWBACK]}
    gross_by_year = {s: [0.0] * len(years) for s in SOURCES}
    for i, r in enumerate(results):
        for p in r.persons:
            if not p.alive:
                continue
            weights = _taxable_weights(p)
            total_w = sum(weights.values())
            for source, gross in _gross(p).items():
                gross_by_year[source][i] += gross
                if total_w > 0:
                    tax_by_year[source][i] += p.tax_total * weights[source] / total_w
            tax_by_year[CLAWBACK][i] += p.oas_clawback
    attribution = TaxAttribution(
        years=years, tax_by_year=tax_by_year, gross_by_year=gross_by_year,
        total_tax=sum(r.total_tax for r in results))
    if estates:
        attribution.death_tax = estates[-1].tax_at_death
        attribution.death_year = estates[-1].year
    return attribution
