"""Feuille d'impôt détaillée d'une personne pour une année simulée.

Reconstruit une déclaration simplifiée (T1 / TP-1) à partir de l'entrée et du
résultat fiscal exacts conservés sur `PersonYearResult`, pour comparaison avec
un calculateur externe ou une déclaration réelle.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from planner.core.benefits.oas import OAS
from planner.core.simulation.types import HouseholdYearResult, PersonYearResult
from planner.core.tax.params import load_params
from planner.core.tax.provincial import get_province_tax
from planner.core.tax.types import TaxInput, TaxResult


@dataclass
class BracketLine:
    lower: float
    upper: float | None
    rate: float
    amount: float  # revenu imposé dans la tranche
    tax: float


@dataclass
class LevelSheet:
    label: str
    brackets: list[BracketLine]
    gross_tax: float
    credits: list[tuple[str, float]]  # montants de base ou crédits (libellé, valeur)
    credit_rate: float
    non_refundable_credits: float
    dividend_credits: float
    abatement: float
    refundable_credits: float
    net_tax: float


@dataclass
class TaxSheet:
    year: int
    age: int
    province: str
    price_factor: float
    income_lines: list[tuple[str, float]]
    ordinary_income: float          # TaxInput
    ordinary_explained: float       # somme des lignes ordinaires de PersonYearResult
    dividends_received: float
    dividends_grossed_up: float
    capital_gains: float
    taxable_capital_gains: float
    total_income: float
    deductions: float
    net_income: float
    taxable_income: float
    federal: LevelSheet
    provincial: LevelSheet
    total_tax: float
    oas_clawback: float
    oas_clawback_threshold: float
    refundable_credits: float
    effective_rate: float
    marginal_rate: float
    eligible_pension_income: float
    family_net_income: float | None
    lives_alone: bool
    warnings: list[str] = field(default_factory=list)

    @property
    def unexplained_income(self) -> float:
        return self.ordinary_income - self.ordinary_explained


_FED_CREDIT_LABELS = [
    ("bpa", "Montant personnel de base"),
    ("age_amount", "Montant en raison de l'âge (65+)"),
    ("pension_amount", "Montant pour revenu de pension"),
    ("medical_amount", "Frais médicaux admissibles"),
    ("donation_credit", "Crédit pour dons (déjà en $ d'impôt)"),
]
_QC_CREDIT_LABELS = [
    ("bpa", "Montant personnel de base"),
    ("senior_amount_before_reduction", "Montants aînés avant réduction (âge + retraite + seul)"),
    ("senior_amount", "Montants aînés après réduction (revenu familial)"),
    ("medical_credit", "Crédit frais médicaux (déjà en $ d'impôt)"),
    ("donation_credit", "Crédit pour dons (déjà en $ d'impôt)"),
    ("home_support_credit", "Crédit remboursable maintien à domicile"),
]


def _bracket_lines(taxable_income: float, brackets: list, pf: float) -> list[BracketLine]:
    lines, lower = [], 0.0
    for threshold, rate in brackets:
        upper = None if threshold is None else float(threshold) * pf
        top = taxable_income if upper is None else min(taxable_income, upper)
        amount = max(0.0, top - lower)
        lines.append(BracketLine(lower, upper, rate, amount, amount * rate))
        if upper is None or taxable_income <= upper:
            break
        lower = upper
    return lines


def _level_sheet(label: str, lvl, brackets: list, taxable_income: float,
                 pf: float, credit_labels) -> LevelSheet:
    detail = lvl.credits_detail
    return LevelSheet(
        label=label,
        brackets=_bracket_lines(taxable_income, brackets, pf),
        gross_tax=lvl.gross_tax,
        credits=[(text, detail[key]) for key, text in credit_labels if key in detail],
        credit_rate=detail.get("credit_rate", 0.0),
        non_refundable_credits=lvl.non_refundable_credits,
        dividend_credits=lvl.dividend_credits,
        abatement=lvl.abatement,
        refundable_credits=lvl.refundable_credits,
        net_tax=lvl.net_tax)


def _income_lines(p: PersonYearResult) -> list[tuple[str, float]]:
    lines = [
        ("Revenu d'emploi", p.salary),
        ("Emploi à temps partiel", p.part_time_income),
        ("Revenus locatifs nets", p.rental_income),
        ("Rente d'employeur (PD)", p.db_pension),
        ("Rentes viagères", p.annuity_income),
        ("RRQ / RPC", p.rrq),
        ("Pension de la SV", p.oas),
        ("Retraits REER", p.wd_reer),
        ("Retraits FERR", p.wd_ferr),
        ("Retraits FRV", p.wd_frv),
        ("Intérêts (non enregistré)", p.investment_interest),
        ("Fractionnement de pension reçu (+) / cédé (−)", p.pension_split_received),
        ("REER du conjoint attribué", p.spousal_attributed),
    ]
    return [(label, value) for label, value in lines if abs(value) > 0.005]


def build_tax_sheet(hr: HouseholdYearResult, person_index: int,
                    province: str, start_year: int) -> TaxSheet:
    p = hr.persons[person_index]
    inp: TaxInput | None = p.tax_input
    res: TaxResult | None = p.tax_result
    if inp is None or res is None:
        raise ValueError(f"Aucun calcul d'impôt conservé pour {hr.year} "
                         "(personne décédée ou simulation antérieure).")
    pf = p.price_factor
    fed_params = load_params(start_year, "federal")
    prov = get_province_tax(province, start_year)
    prov_brackets = getattr(prov, "p", {}).get("brackets", [])
    gross_up = fed_params["dividends"]["eligible"]["gross_up"]
    inclusion = fed_params["capital_gains_inclusion"]

    lines = _income_lines(p)
    ordinary_explained = sum(v for _, v in lines)
    warnings = []
    if abs(inp.ordinary_income - ordinary_explained) > 1.0:
        warnings.append(
            "Le revenu ordinaire du calcul d'impôt diffère de la somme des lignes "
            "détaillées (ventes d'actifs, récupération d'amortissement ou "
            "réattribution du REER conjoint).")
    if abs((res.federal.net_tax + res.provincial.net_tax) - res.total_tax) > 1.0:
        warnings.append("Fédéral + provincial ≠ impôt total.")
    if abs(sum(b.tax for b in _bracket_lines(res.taxable_income, fed_params["brackets"], pf))
           - res.federal.gross_tax) > 1.0:
        warnings.append("Le détail par tranche fédéral ne reproduit pas l'impôt brut.")

    return TaxSheet(
        year=hr.year, age=p.age, province=province, price_factor=pf,
        income_lines=lines,
        ordinary_income=inp.ordinary_income, ordinary_explained=ordinary_explained,
        dividends_received=inp.eligible_dividends,
        dividends_grossed_up=inp.eligible_dividends * (1 + gross_up),
        capital_gains=inp.capital_gains,
        taxable_capital_gains=inp.capital_gains * inclusion,
        total_income=res.total_income, deductions=inp.deductions,
        net_income=res.net_income, taxable_income=res.taxable_income,
        federal=_level_sheet("Fédéral", res.federal, fed_params["brackets"],
                             res.taxable_income, pf, _FED_CREDIT_LABELS),
        provincial=_level_sheet(f"Provincial ({province})", res.provincial, prov_brackets,
                                res.taxable_income, pf, _QC_CREDIT_LABELS),
        total_tax=res.total_tax, oas_clawback=p.oas_clawback,
        oas_clawback_threshold=OAS(start_year).clawback_threshold * pf,
        refundable_credits=res.refundable_credits,
        effective_rate=(res.total_tax + p.oas_clawback) / res.taxable_income
        if res.taxable_income > 0 else 0.0,
        marginal_rate=p.marginal_rate,
        eligible_pension_income=inp.eligible_pension_income,
        family_net_income=inp.family_net_income, lives_alone=inp.lives_alone,
        warnings=warnings)
