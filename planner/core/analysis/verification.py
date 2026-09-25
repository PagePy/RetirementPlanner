"""Vérification d'une projection: preuve de caisse, roll-forward des comptes
et contrôles d'invariants (règles légales et cohérence interne).

Tout est reconstruit à partir des résultats annuels; aucun recalcul du moteur.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from planner.core.analysis.succession import EstateResult
from planner.core.benefits.oas import OAS
from planner.core.simulation.types import (
    HouseholdConfig, HouseholdYearResult, PersonYearResult, ScenarioConfig)

TOL = 1.0  # tolérance en dollars pour les rapprochements


# ---------- 1. preuve de caisse ----------

@dataclass
class CashProofRow:
    year: int
    inflows: dict[str, float]
    outflows: dict[str, float]
    explained_net: float
    reported_net: float
    target: float
    gap: float
    reinvested: float

    @property
    def difference(self) -> float:
        return self.reported_net - self.explained_net

    @property
    def balanced(self) -> bool:
        return abs(self.difference) <= TOL


def _cash_proof_row(hr: HouseholdYearResult) -> CashProofRow:
    alive = [p for p in hr.persons if p.alive]
    s = lambda fn: sum(fn(p) for p in alive)  # noqa: E731
    inflows = {
        "Emploi (salaire + temps partiel)": s(lambda p: p.salary + p.part_time_income),
        "Loyers nets": s(lambda p: p.rental_income),
        "Rentes PD et viagères": s(lambda p: p.db_pension + p.annuity_income),
        "RRQ": s(lambda p: p.rrq),
        "SV": s(lambda p: p.oas),
        "Retraits REER": s(lambda p: p.wd_reer),
        "Retraits FERR / FRV": s(lambda p: p.wd_ferr + p.wd_frv),
        "Retraits CELI": s(lambda p: p.wd_celi),
        "Retraits non enregistré": s(lambda p: p.wd_taxable),
        "SRG": s(lambda p: p.gis),
        "Crédits remboursables": s(lambda p: p.refundable_credits),
    }
    # Le surplus réinvesti est compté dans contrib_celi/contrib_taxable mais
    # n'a jamais quitté le net encaissé; les primes ne sortent du salaire
    # qu'en accumulation (à la retraite elles sont ajoutées à la cible).
    contributions = s(lambda p: p.contrib_reer + p.contrib_spousal_reer + p.contrib_celi
                      + p.contrib_celiapp + p.contrib_taxable + p.contrib_dc_employee)
    outflows = {
        "Cotisations prélevées sur le salaire": contributions - hr.reinvested,
        "Primes d'assurance (en accumulation)": s(
            lambda p: p.insurance_premium if not p.retired else 0.0),
        "Impôts": s(lambda p: p.tax_total),
        "Récupération SV": s(lambda p: p.oas_clawback),
    }
    return CashProofRow(
        year=hr.year, inflows=inflows, outflows=outflows,
        explained_net=sum(inflows.values()) - sum(outflows.values()),
        reported_net=hr.net_cash, target=hr.target_net, gap=hr.target_gap,
        reinvested=hr.reinvested)


# ---------- 2. roll-forward des comptes ----------

GROUPS = ["REER + FERR", "CRI + FRV", "CELI", "CELIAPP", "Non enregistré"]

_GROUP_BALANCE = {
    "REER + FERR": lambda p: p.bal_reer + p.bal_ferr,
    "CRI + FRV": lambda p: p.bal_cri + p.bal_frv,
    "CELI": lambda p: p.bal_celi,
    "CELIAPP": lambda p: p.bal_celiapp,
    "Non enregistré": lambda p: p.bal_taxable,
}
_GROUP_CONTRIB = {
    "REER + FERR": lambda p: p.contrib_reer + p.contrib_spousal_reer,
    "CRI + FRV": lambda p: p.contrib_dc_employee + p.contrib_dc_employer,
    "CELI": lambda p: p.contrib_celi,
    "CELIAPP": lambda p: p.contrib_celiapp,
    "Non enregistré": lambda p: p.contrib_taxable,
}
_GROUP_WITHDRAW = {
    "REER + FERR": lambda p: p.wd_reer + p.wd_ferr,
    "CRI + FRV": lambda p: p.wd_frv,
    "CELI": lambda p: p.wd_celi,
    "CELIAPP": lambda p: 0.0,
    "Non enregistré": lambda p: p.wd_taxable,
}
_GROUP_OPENING = {
    "REER + FERR": lambda a: a.reer_balance + a.ferr_balance,
    "CRI + FRV": lambda a: a.cri_balance + a.frv_balance,
    "CELI": lambda a: a.celi_balance,
    "CELIAPP": lambda a: a.celiapp_balance,
    "Non enregistré": lambda a: a.taxable_balance,
}
_GROUP_RETURNS = {
    "REER + FERR": ("reer_return", "ferr_return"),
    "CRI + FRV": ("cri_return", "frv_return"),
    "CELI": ("celi_return",),
    "CELIAPP": ("celiapp_return",),
    "Non enregistré": ("taxable_return",),
}
_ANNUITY_GROUP = {"reer": "REER + FERR", "ferr": "REER + FERR",
                  "celi": "CELI", "taxable": "Non enregistré"}


@dataclass
class RollForwardRow:
    year: int
    group: str
    opening: float
    contributions: float
    withdrawals: float
    transfers: float          # entrées (+) / sorties (−) hors cotisations et retraits
    closing: float
    expected_rate_low: float | None
    expected_rate_high: float | None
    note: str = ""

    @property
    def implied_return(self) -> float:
        return (self.closing - self.opening - self.contributions
                + self.withdrawals - self.transfers)

    @property
    def implied_rate(self) -> float | None:
        return self.implied_return / self.opening if self.opening > 1.0 else None

    @property
    def consistent(self) -> bool:
        if self.implied_rate is None or self.expected_rate_low is None:
            return True
        return (self.expected_rate_low - 0.0025 <= self.implied_rate
                <= self.expected_rate_high + 0.0025)


def _fully_retired(p: PersonYearResult, cfg) -> bool:
    return p.age > cfg.retirement_age


def _expected_range(group: str, hr: HouseholdYearResult, hh: HouseholdConfig,
                    scen: ScenarioConfig) -> tuple[float | None, float | None]:
    delta = scen.return_delta_by_year.get(hr.year, 0.0)
    rates = []
    for cfg, p in zip(hh.persons, hr.persons):
        if not p.alive:
            continue
        # L'année du départ, la phase (active/retraite) dépend du mois: couvrir les deux.
        phases = ({True, False} if p.age == cfg.retirement_age
                  else {_fully_retired(p, cfg)})
        for attr in _GROUP_RETURNS[group]:
            for retired in phases:
                rates.append(max(-0.95, cfg.accounts.net_return(
                    getattr(cfg.accounts, attr), retired) + delta))
    if not rates:
        return None, None
    return min(rates), max(rates)


def roll_forward(results: list[HouseholdYearResult], hh: HouseholdConfig,
                 scen: ScenarioConfig) -> list[RollForwardRow]:
    rows = []
    opening = {g: sum(_GROUP_OPENING[g](cfg.accounts) for cfg in hh.persons) for g in GROUPS}
    for hr in results:
        alive = [p for p in hr.persons if p.alive]
        if not alive:
            break
        transfers = {g: 0.0 for g in GROUPS}
        notes = {g: "" for g in GROUPS}
        opening_adj = {g: 0.0 for g in GROUPS}
        transfers["Non enregistré"] += hr.asset_sale_proceeds
        if hr.asset_sale_proceeds > 0:
            notes["Non enregistré"] = "produit de vente d'actif"
        if hr.insurance_payout > 0:
            # Versé en début d'année au survivant: il croît avec le solde d'ouverture.
            opening_adj["Non enregistré"] += hr.insurance_payout
            notes["Non enregistré"] = "capital-décès reçu (ajouté à l'ouverture)"
        for ann in hh.annuities:
            if ann.purchase_year == hr.year and ann.source in _ANNUITY_GROUP:
                g = _ANNUITY_GROUP[ann.source]
                transfers[g] -= ann.premium
                notes[g] = f"achat de rente ({ann.name})"
        for g in GROUPS:
            closing = sum(_GROUP_BALANCE[g](p) for p in alive)
            if opening[g] <= 1.0 and closing <= 1.0:
                continue
            low, high = _expected_range(g, hr, hh, scen)
            rows.append(RollForwardRow(
                year=hr.year, group=g, opening=opening[g] + opening_adj[g],
                contributions=sum(_GROUP_CONTRIB[g](p) for p in alive),
                withdrawals=sum(_GROUP_WITHDRAW[g](p) for p in alive),
                transfers=transfers[g], closing=closing,
                expected_rate_low=low, expected_rate_high=high, note=notes[g]))
            opening[g] = closing
    return rows


# ---------- 3. invariants ----------

@dataclass
class Check:
    name: str
    description: str
    failures: list[str] = field(default_factory=list)
    applicable: bool = True

    @property
    def passed(self) -> bool:
        return not self.failures


def _fmt(x: float) -> str:
    return f"{x:,.0f} $".replace(",", " ")


def run_checks(results: list[HouseholdYearResult], estates: list[EstateResult],
               hh: HouseholdConfig, scen: ScenarioConfig,
               cash_rows: list[CashProofRow], rf_rows: list[RollForwardRow]) -> list[Check]:
    checks: list[Check] = []
    oas = OAS(scen.start_year)
    start = results[0].year

    def pf(year: int) -> float:
        return (1 + scen.inflation) ** (year - start)

    def person_years():
        for hr in results:
            for i, p in enumerate(hr.persons):
                if p.alive:
                    yield hr, i, p, hh.persons[i]

    def name(i: int) -> str:
        return hh.persons[i].name or f"Personne {i + 1}"

    # Cohérence interne du ménage
    c = Check("Agrégats du ménage", "net encaissé, impôts, patrimoine et valeur nette "
              "= somme des personnes; valeur nette = placements + immobilier − dettes")
    for hr in results:
        alive = [p for p in hr.persons if p.alive]
        if not alive:
            continue
        pairs = [
            ("net encaissé", hr.net_cash, sum(p.net_cash for p in alive)),
            ("impôts", hr.total_tax, sum(p.tax_total + p.oas_clawback for p in alive)),
            ("placements", hr.total_wealth, sum(p.wealth for p in alive)),
            ("valeur nette", hr.net_worth,
             hr.total_wealth + hr.real_assets_value - hr.debts_balance),
        ]
        for label, a, b in pairs:
            if abs(a - b) > TOL:
                c.failures.append(f"{hr.year}: {label} {_fmt(a)} ≠ {_fmt(b)}")
    checks.append(c)

    c = Check("Preuve de caisse", "revenus + retraits + SRG − cotisations − impôts "
              "− récupération SV = net encaissé")
    c.failures = [f"{r.year}: écart {_fmt(r.difference)}" for r in cash_rows if not r.balanced]
    checks.append(c)

    c = Check("Écart vs cible", "à la retraite: net encaissé − cible = écart; "
              "un surplus est réinvesti, un déficit est documenté")
    for hr in results:
        alive = [p for p in hr.persons if p.alive]
        if not alive or not any(p.retired for p in alive):
            continue
        if abs((hr.net_cash - hr.target_net) - hr.target_gap) > TOL:
            c.failures.append(f"{hr.year}: écart {_fmt(hr.target_gap)} ≠ "
                              f"{_fmt(hr.net_cash - hr.target_net)}")
        if hr.target_gap > 5.0 and abs(hr.reinvested - hr.target_gap) > TOL:
            c.failures.append(f"{hr.year}: surplus {_fmt(hr.target_gap)} mais réinvesti "
                              f"{_fmt(hr.reinvested)}")
        if hr.target_gap < -500 and not hr.shortfall_note:
            c.failures.append(f"{hr.year}: déficit {_fmt(-hr.target_gap)} sans explication")
    checks.append(c)

    c = Check("Rendement des comptes", "rendement implicite de chaque groupe de comptes "
              "dans la fourchette des hypothèses (± 0,25 pt)")
    for r in rf_rows:
        if not r.consistent:
            c.failures.append(
                f"{r.year} {r.group}: {r.implied_rate:.2%} hors "
                f"[{r.expected_rate_low:.2%} ; {r.expected_rate_high:.2%}]"
                + (f" ({r.note})" if r.note else ""))
    checks.append(c)

    c = Check("Soldes non négatifs", "aucun compte ni dette sous zéro")
    for hr, i, p, _ in person_years():
        for attr in ("bal_reer", "bal_celi", "bal_celiapp", "bal_cri",
                     "bal_ferr", "bal_frv", "bal_taxable"):
            if getattr(p, attr) < -0.01:
                c.failures.append(f"{hr.year} {name(i)}: {attr} = {_fmt(getattr(p, attr))}")
    for hr in results:
        if hr.debts_balance < -0.01:
            c.failures.append(f"{hr.year}: dettes {_fmt(hr.debts_balance)}")
    checks.append(c)

    c = Check("Minimums FERR / FRV", "retrait ≥ minimum légal chaque année")
    for hr, i, p, _ in person_years():
        if p.wd_ferr < p.ferr_min - TOL:
            c.failures.append(f"{hr.year} {name(i)}: FERR {_fmt(p.wd_ferr)} < min {_fmt(p.ferr_min)}")
        if p.wd_frv < p.frv_min - TOL:
            c.failures.append(f"{hr.year} {name(i)}: FRV {_fmt(p.wd_frv)} < min {_fmt(p.frv_min)}")
    checks.append(c)

    c = Check("Conversion à 71 ans", "plus aucun REER ni CRI à partir de 71 ans")
    for hr, i, p, _ in person_years():
        if p.age >= 71 and (p.bal_reer > TOL or p.bal_cri > TOL):
            c.failures.append(f"{hr.year} {name(i)} ({p.age} ans): REER {_fmt(p.bal_reer)}, "
                              f"CRI {_fmt(p.bal_cri)}")
    checks.append(c)

    c = Check("Début RRQ / SV", "aucune rente avant l'âge choisi; rente versée dès cet âge")
    for hr, i, p, cfg in person_years():
        survivor = hh.is_couple and sum(1 for q in hr.persons if q.alive) == 1
        if cfg.rrq_monthly_at_65 > 0:
            if (p.age < cfg.rrq_start_age and p.rrq > TOL and p.rrq_shared_delta <= TOL
                    and not survivor):
                c.failures.append(f"{hr.year} {name(i)}: RRQ {_fmt(p.rrq)} avant {cfg.rrq_start_age} ans")
            if p.age > cfg.rrq_start_age and p.rrq <= TOL:
                c.failures.append(f"{hr.year} {name(i)}: aucune RRQ à {p.age} ans")
        if cfg.oas_residence_years > 0:
            if p.age < cfg.oas_start_age and p.oas > TOL:
                c.failures.append(f"{hr.year} {name(i)}: SV {_fmt(p.oas)} avant {cfg.oas_start_age} ans")
            if p.age > max(cfg.oas_start_age, 65) and p.oas <= TOL:
                c.failures.append(f"{hr.year} {name(i)}: aucune SV à {p.age} ans")
    checks.append(c)

    c = Check("Récupération de la SV", "nulle sous le seuil indexé, jamais supérieure à la SV reçue")
    for hr, i, p, _ in person_years():
        threshold = oas.clawback_threshold * p.price_factor
        res = p.tax_result
        if res is not None and res.net_income <= threshold and p.oas_clawback > TOL:
            c.failures.append(f"{hr.year} {name(i)}: récupération {_fmt(p.oas_clawback)} avec "
                              f"revenu net {_fmt(res.net_income)} ≤ seuil {_fmt(threshold)}")
        if p.oas_clawback > p.oas + TOL:
            c.failures.append(f"{hr.year} {name(i)}: récupération {_fmt(p.oas_clawback)} > SV {_fmt(p.oas)}")
    checks.append(c)

    c = Check("SRG", "versé seulement avec la SV, et jamais avec une récupération de SV")
    for hr, i, p, _ in person_years():
        if p.gis > TOL and p.oas <= TOL:
            c.failures.append(f"{hr.year} {name(i)}: SRG {_fmt(p.gis)} sans SV")
        if p.gis > TOL and p.oas_clawback > TOL:
            c.failures.append(f"{hr.year} {name(i)}: SRG {_fmt(p.gis)} et récupération SV simultanés")
    checks.append(c)

    c = Check("Fractionnement et partage RRQ", "les transferts entre conjoints s'annulent",
              applicable=hh.is_couple)
    if hh.is_couple:
        for hr in results:
            alive = [p for p in hr.persons if p.alive]
            if len(alive) == 2:
                split = sum(p.pension_split_received for p in alive)
                shared = sum(p.rrq_shared_delta for p in alive)
                if abs(split) > TOL:
                    c.failures.append(f"{hr.year}: fractionnement net {_fmt(split)} ≠ 0")
                if abs(shared) > TOL:
                    c.failures.append(f"{hr.year}: partage RRQ net {_fmt(shared)} ≠ 0")
    checks.append(c)

    c = Check("Âges et espérance de vie", "âge = année − naissance; personne vivante "
              "au-delà de son espérance de vie seulement si aucun décès n'est simulé")
    for hr, i, p, cfg in person_years():
        if p.age != hr.year - cfg.birth_year:
            c.failures.append(f"{hr.year} {name(i)}: âge {p.age} ≠ {hr.year - cfg.birth_year}")
        if p.age > cfg.life_expectancy:
            c.failures.append(f"{hr.year} {name(i)}: vivant à {p.age} ans "
                              f"(espérance {cfg.life_expectancy})")
    checks.append(c)

    c = Check("Indexation de la cible", "cible = base indexée + dépenses spéciales + "
              "dettes + assurance + véhicules, une fois pleinement à la retraite")
    for hr in results:
        alive = [(p, cfg) for p, cfg in zip(hr.persons, hh.persons) if p.alive]
        if not alive or not any(_fully_retired(p, cfg) for p, cfg in alive):
            continue
        base = hh.target_net_income * (pf(hr.year) if hh.target_indexed else 1.0)
        expected = (base + hh.special_expenses.get(hr.year, 0.0) + hr.debt_service
                    + hr.insurance_premiums + hr.vehicle_expenses)
        if abs(hr.target_net - expected) > TOL:
            c.failures.append(f"{hr.year}: cible {_fmt(hr.target_net)} ≠ attendue {_fmt(expected)}")
    checks.append(c)

    c = Check("Feuille d'impôt", "fédéral + provincial = impôt total; revenu imposable ≥ 0")
    for hr, i, p, _ in person_years():
        res = p.tax_result
        if res is None:
            continue
        if abs(res.federal.net_tax + res.provincial.net_tax - p.tax_total) > TOL:
            c.failures.append(f"{hr.year} {name(i)}: fédéral + provincial ≠ total")
        if res.taxable_income < -0.01:
            c.failures.append(f"{hr.year} {name(i)}: revenu imposable négatif")
    checks.append(c)

    c = Check("Succession", "succession nette = brute − impôt au décès − dettes; "
              "impôt au décès ≤ 60 % des sommes enregistrées + gains",
              applicable=bool(estates))
    debts = {hr.year: hr.debts_balance for hr in results}
    recapture = {hr.year: hr.real_assets_recapture for hr in results}
    for e in estates:
        if abs(e.gross_estate - e.tax_at_death - debts.get(e.year, 0.0) - e.net_estate) > TOL:
            c.failures.append(f"{e.year}: {_fmt(e.gross_estate)} − {_fmt(e.tax_at_death)} − "
                              f"{_fmt(debts.get(e.year, 0.0))} ≠ {_fmt(e.net_estate)}")
        base = (e.registered_income_at_death + 0.5 * e.unrealized_gains
                + recapture.get(e.year, 0.0))
        if e.tax_at_death > 0.6 * base + TOL:
            c.failures.append(f"{e.year}: impôt au décès {_fmt(e.tax_at_death)} > 60 % de {_fmt(base)}")
    checks.append(c)
    return checks


# ---------- rapport ----------

@dataclass
class Verification:
    cash_proof: list[CashProofRow]
    roll_forward: list[RollForwardRow]
    checks: list[Check]

    @property
    def failed_checks(self) -> list[Check]:
        return [c for c in self.checks if c.applicable and not c.passed]


def verify(results: list[HouseholdYearResult], estates: list[EstateResult],
           hh: HouseholdConfig, scen: ScenarioConfig) -> Verification:
    cash_rows = [_cash_proof_row(hr) for hr in results if any(p.alive for p in hr.persons)]
    rf_rows = roll_forward(results, hh, scen)
    return Verification(cash_rows, rf_rows, run_checks(results, estates, hh, scen, cash_rows, rf_rows))
