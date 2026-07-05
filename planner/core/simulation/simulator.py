"""Simulateur de ménage — timeline annuelle synchronisée pour 1 ou 2 personnes.

Corrige l'ancien moteur qui simulait chaque conjoint isolément:
- Cible de revenu net commune au MÉNAGE, comblée par la personne dont le
  retrait coûte le moins d'impôt (recherche binaire précise, sans heuristique).
- Fractionnement de pension OPTIMAL recalculé chaque année.
- SRG/Allocation, récupération SV, crédits d'âge/pension réels.
- Décès (prématuré ou espérance de vie) avec roulement au conjoint et
  rente de survivant RRQ.

Ordre des opérations annuelles:
1. Décès et roulements; nouveaux droits (CELI/REER); conversions (71 ans).
2. Croissance des comptes (les distributions non-enregistrées deviennent
   imposables cette année).
3. Accumulation: salaire et cotisations.
4. Retraite: revenus garantis, minimums FERR/FRV, retraits pour combler la
   cible nette du ménage.
5. Impôts finaux (avec fractionnement optimal), SRG, récupération SV.

Approximation documentée: le SRG est estimé sur le revenu de base de l'année
courante (hors SV) avant retraits additionnels.
"""
from dataclasses import dataclass, field

from planner.core.accounts import REER, CELI, CELIAPP, FERR, FRV, Taxable
from planner.core.benefits import RRQ, OAS, GIS
from planner.core.simulation.splitting import (
    eligible_pension_for_splitting, optimize_pension_split, couple_tax_with_split)
from planner.core.simulation.types import (
    HouseholdConfig, ScenarioConfig, PersonConfig,
    PersonYearResult, HouseholdYearResult)
from planner.core.tax import TaxCalculator, TaxInput


@dataclass
class _PersonState:
    cfg: PersonConfig
    reer: REER = None
    celi: CELI = None
    celiapp: CELIAPP = None
    cri_balance: float = 0.0
    ferr: FERR = None
    frv: FRV = None
    taxable: Taxable = None
    salary: float = 0.0
    alive: bool = True
    lives_alone: bool = False
    rrq_annual_at_start: float = 0.0  # rente RRQ annuelle (dollars du début)
    survivor_rrq: float = 0.0
    # Situation fiscale de l'année en cours (remplie par le simulateur)
    _tax_situation: dict = field(default_factory=dict)


class HouseholdSimulator:
    TOLERANCE = 1.0  # tolérance sur la cible nette ($)

    def __init__(self, household: HouseholdConfig, scenario: ScenarioConfig):
        self.hh = household
        self.scen = scenario
        self.start_year = scenario.start_year
        self.calc = TaxCalculator(year=self.start_year, province=household.province)
        self.rrq = RRQ(self.start_year)
        self.oas = OAS(self.start_year)
        self.gis = GIS(self.start_year)
        self.states = [self._init_state(p) for p in household.persons]
        if scenario.end_year:
            self.end_year = scenario.end_year
        else:
            self.end_year = max(p.birth_year + p.life_expectancy for p in household.persons)

    # ---------- initialisation ----------
    def _init_state(self, cfg: PersonConfig) -> _PersonState:
        a = cfg.accounts
        st = _PersonState(cfg=cfg)
        st.reer = REER(balance=a.reer_balance, contribution_room=a.reer_room,
                       year=self.start_year)
        st.celi = CELI(balance=a.celi_balance, contribution_room=a.celi_room,
                       year=self.start_year)
        st.celiapp = CELIAPP(balance=a.celiapp_balance, year_opened=self.start_year)
        st.cri_balance = a.cri_balance
        spouse_offset = self._spouse_age_offset(cfg)
        use_spouse = self.hh.use_spouse_age_for_ferr and self.hh.is_couple
        st.ferr = FERR(balance=a.ferr_balance,
                       spouse_age_offset=spouse_offset, use_spouse_age=use_spouse)
        st.frv = FRV(balance=a.frv_balance, year=self.start_year,
                     province=self.hh.province,
                     spouse_age_offset=spouse_offset, use_spouse_age=use_spouse)
        acb = a.taxable_acb if a.taxable_acb is not None else a.taxable_balance
        st.taxable = Taxable(balance=a.taxable_balance, acb=acb,
                             interest_ratio=a.taxable_interest_ratio,
                             eligible_dividend_ratio=a.taxable_dividend_ratio,
                             capital_growth_ratio=a.taxable_growth_ratio)
        st.salary = cfg.salary
        st.lives_alone = not self.hh.is_couple
        st.rrq_annual_at_start = self.rrq.annual_pension(
            cfg.rrq_monthly_at_65, cfg.rrq_start_age)
        return st

    def _spouse_age_offset(self, cfg: PersonConfig) -> int:
        if not self.hh.is_couple:
            return 0
        other = next(p for p in self.hh.persons if p is not cfg)
        return cfg.birth_year - other.birth_year  # conjoint plus jeune → offset négatif

    # ---------- indexation ----------
    def _index(self, amount: float, year: int) -> float:
        return amount * (1 + self.scen.inflation) ** (year - self.start_year)

    # ---------- boucle principale ----------
    def run(self) -> list[HouseholdYearResult]:
        results = []
        for year in range(self.start_year, self.end_year + 1):
            results.append(self._simulate_year(year))
        return results

    def _simulate_year(self, year: int) -> HouseholdYearResult:
        hh_result = HouseholdYearResult(year=year)

        # 1. Décès et roulements
        self._handle_deaths(year)

        alive_states = [s for s in self.states if s.alive]
        person_results: list[PersonYearResult] = []

        for st in self.states:
            age = year - st.cfg.birth_year
            pr = PersonYearResult(year=year, age=age, alive=st.alive)
            person_results.append(pr)
            if not st.alive:
                continue
            retired = age >= st.cfg.retirement_age
            pr.retired = retired

            # Droits et conversions
            st.celi.new_year(year)
            if age >= 71 and st.reer.balance > 0:
                st.ferr.balance += st.reer.convert_to_ferr()
            if st.cri_balance > 0 and (age >= 71 or (retired and age >= 55)):
                st.frv.balance += st.cri_balance
                st.cri_balance = 0.0

            # 2. Croissance (les distributions deviennent imposables cette année)
            a = st.cfg.accounts
            st.reer.grow(a.reer_return)
            st.celi.grow(a.celi_return)
            st.celiapp.grow(a.celiapp_return)
            st.cri_balance *= (1 + a.cri_return)
            st.ferr.grow(a.ferr_return)
            st.frv.grow(a.frv_return)
            inv = st.taxable.grow(a.taxable_return)
            pr.investment_interest = inv["interest"]
            pr.investment_dividends = inv["eligible_dividends"]

            # 3. Accumulation
            if not retired:
                self._accumulation(st, pr, year)
            # 4. Revenus garantis + minimums
            else:
                self._guaranteed_income(st, pr, year, age)

        # 4b. Retraits pour combler la cible du ménage
        target = self._year_target(year)
        hh_result.target_net = target
        hh_result.special_expenses = self.hh.special_expenses.get(year, 0.0)
        self._solve_withdrawals(year, alive_states, person_results, target)

        # 5. Impôts finaux avec fractionnement optimal
        self._finalize_taxes(year, person_results)

        # 5b. SRG calculé sur le revenu imposable réel (hors SV), comme le
        # programme officiel qui se base sur le revenu déclaré. Versé en sus
        # de la cible (non compté par le solveur — approche conservatrice).
        self._compute_gis(year, person_results)

        # Soldes de fin d'année
        for st, pr in zip(self.states, person_results):
            if not st.alive:
                continue
            pr.bal_reer = st.reer.balance
            pr.bal_celi = st.celi.balance
            pr.bal_celiapp = st.celiapp.balance
            pr.bal_cri = st.cri_balance
            pr.bal_ferr = st.ferr.balance
            pr.bal_frv = st.frv.balance
            pr.bal_taxable = st.taxable.balance
            pr.taxable_unrealized_gain = st.taxable.unrealized_gain

        hh_result.persons = person_results
        hh_result.net_cash = sum(p.net_cash for p in person_results)
        hh_result.total_tax = sum(p.tax_total + p.oas_clawback for p in person_results)
        hh_result.total_wealth = sum(p.wealth for p in person_results)
        hh_result.target_gap = hh_result.net_cash - target
        return hh_result

    # ---------- décès ----------
    def _handle_deaths(self, year: int) -> None:
        for i, st in enumerate(self.states):
            if not st.alive:
                continue
            age = year - st.cfg.birth_year
            premature = (self.hh.premature_death
                         and self.hh.premature_death.get("person_index") == i
                         and year >= self.hh.premature_death.get("year", 10**9))
            if age > st.cfg.life_expectancy or premature:
                st.alive = False
                survivors = [s for s in self.states if s.alive]
                if survivors:
                    self._rollover_to_survivor(st, survivors[0], year)

    def _rollover_to_survivor(self, deceased: _PersonState,
                              survivor: _PersonState, year: int) -> None:
        """Roulement au conjoint (sans impôt) + rente de survivant RRQ."""
        survivor.reer.balance += deceased.reer.balance
        survivor.ferr.balance += deceased.ferr.balance
        survivor.frv.balance += deceased.frv.balance
        survivor.cri_balance += deceased.cri_balance
        survivor.celi.balance += deceased.celi.balance  # via désignation
        survivor.taxable.balance += deceased.taxable.balance
        survivor.taxable.acb += deceased.taxable.acb    # roulement au PBR
        deceased_rrq_now = self._index(deceased.rrq_annual_at_start, year)
        survivor_rrq_now = self._index(survivor.rrq_annual_at_start, year)
        survivor.survivor_rrq = self.rrq.survivor_pension(
            deceased_rrq_now, survivor_rrq_now)
        survivor.lives_alone = True
        deceased.reer.balance = deceased.ferr.balance = deceased.frv.balance = 0.0
        deceased.celi.balance = deceased.taxable.balance = deceased.taxable.acb = 0.0
        deceased.cri_balance = 0.0

    # ---------- accumulation ----------
    def _accumulation(self, st: _PersonState, pr: PersonYearResult, year: int) -> None:
        c = st.cfg.contributions
        pr.salary = st.salary
        st.reer.add_new_room(st.salary)
        pr.contrib_reer = st.reer.contribute(st.salary * c.reer_pct + c.reer_fixed)
        pr.contrib_celi = st.celi.contribute(st.salary * c.celi_pct + c.celi_fixed)
        pr.contrib_celiapp = st.celiapp.contribute(c.celiapp_fixed)
        pr.contrib_taxable = st.taxable.contribute(
            st.salary * c.taxable_pct + c.taxable_fixed)
        st.celiapp.new_year()
        st.salary *= (1 + st.cfg.salary_growth)
        st._tax_situation = {
            "ordinary": pr.salary + pr.investment_interest,
            "pension_eligible": 0.0,
            "dividends": pr.investment_dividends,
            "capital_gains": 0.0,
            "deductions": pr.contrib_reer + pr.contrib_celiapp,
            "cash": pr.salary - pr.contrib_reer - pr.contrib_celi
                    - pr.contrib_celiapp - pr.contrib_taxable,
            "oas": 0.0,
        }

    # ---------- revenus garantis ----------
    def _guaranteed_income(self, st: _PersonState, pr: PersonYearResult,
                           year: int, age: int) -> None:
        cfg = st.cfg
        # Rente PD avec pénalité d'anticipation
        if cfg.db_pension > 0 and age >= cfg.db_start_age:
            penalty_years = max(0, cfg.db_normal_age - cfg.db_start_age)
            base = cfg.db_pension * (1 - penalty_years * cfg.db_penalty_per_year)
            start_year_pd = cfg.birth_year + cfg.db_start_age
            pr.db_pension = (self._index(base, year) if cfg.db_indexed
                             else self._index(base, start_year_pd))
        # RRQ (ajustée selon l'âge de début, indexée) + rente de survivant
        if age >= cfg.rrq_start_age and cfg.rrq_monthly_at_65 > 0:
            pr.rrq = self._index(st.rrq_annual_at_start, year)
        pr.rrq += self._index(st.survivor_rrq, year) if st.survivor_rrq else 0.0
        # SV (report, 75+, résidence)
        oas_base = self.oas.annual_pension(age, cfg.oas_start_age,
                                           cfg.oas_residence_years)
        pr.oas = self._index(oas_base, year)
        # Minimums FERR/FRV
        pr.ferr_min = st.ferr.min_withdrawal(age)
        pr.frv_min = st.frv.min_withdrawal(age)
        pr.wd_ferr = st.ferr.withdraw(pr.ferr_min)
        pr.wd_frv = st.frv.withdraw(pr.frv_min)

        ordinary = (pr.db_pension + pr.rrq + pr.oas + pr.wd_ferr + pr.wd_frv
                    + pr.investment_interest)
        pension_eligible = eligible_pension_for_splitting(
            age, pr.db_pension, pr.wd_ferr + pr.wd_frv)
        st._tax_situation = {
            "ordinary": ordinary,
            "pension_eligible": pension_eligible,
            "dividends": pr.investment_dividends,
            "capital_gains": 0.0,
            "deductions": 0.0,
            "cash": pr.db_pension + pr.rrq + pr.oas + pr.gis + pr.wd_ferr + pr.wd_frv,
            "oas": pr.oas,
        }

    # ---------- cible et solveur ----------
    def _year_target(self, year: int) -> float:
        base = self.hh.target_net_income
        target = self._index(base, year) if self.hh.target_indexed else base
        return target + self.hh.special_expenses.get(year, 0.0)

    def _sources_for(self, st: _PersonState, source: str, age: int) -> float:
        if source == "taxable":
            return st.taxable.balance
        if source == "reer":
            return st.reer.balance
        if source == "ferr":
            return st.ferr.balance
        if source == "frv":
            return st.frv.balance
        if source == "celi" and self.hh.celi_strategy != "jamais":
            return st.celi.balance
        return 0.0

    def _household_net(self, person_results: list[PersonYearResult],
                       extras: dict) -> float:
        """Revenu net du ménage pour des retraits additionnels donnés.

        `extras`: {person_index: {source: montant}} — évaluation SANS modifier
        les états.
        """
        inputs, cash_flows, oas_amounts, eligibles = [], [], [], []
        for idx, st in enumerate(self.states):
            if not st.alive:
                continue
            sit = st._tax_situation
            age = person_results[idx].age
            extra = extras.get(idx, {})
            add_ordinary = extra.get("reer", 0.0) + extra.get("ferr", 0.0) + extra.get("frv", 0.0)
            tx = extra.get("taxable", 0.0)
            gain_ratio = (1 - min(1.0, st.taxable.acb / st.taxable.balance)
                          if st.taxable.balance > 0 else 0.0)
            add_gains = tx * gain_ratio
            add_pension = (extra.get("ferr", 0.0) + extra.get("frv", 0.0)) if age >= 65 else 0.0
            inputs.append(TaxInput(
                year=self.calc.year, age=age,
                ordinary_income=sit["ordinary"] + add_ordinary,
                eligible_pension_income=sit["pension_eligible"] + add_pension,
                eligible_dividends=sit["dividends"],
                capital_gains=sit["capital_gains"] + add_gains,
                deductions=sit["deductions"],
                lives_alone=st.lives_alone,
            ))
            cash_flows.append(sit["cash"] + add_ordinary + tx + extra.get("celi", 0.0))
            oas_amounts.append(sit["oas"])
            eligibles.append(sit["pension_eligible"] + add_pension)

        if len(inputs) == 2:
            best = optimize_pension_split(
                self.calc, self.oas, inputs[0], inputs[1],
                oas_amounts[0], oas_amounts[1], eligibles[0], eligibles[1], steps=5)
            total_tax = best["total"]
        else:
            r = self.calc.compute(inputs[0], _marginal_probe=False)
            total_tax = r.total_tax + self.oas.clawback(r.net_income, oas_amounts[0])
        return sum(cash_flows) - total_tax

    def _solve_withdrawals(self, year: int, alive_states: list[_PersonState],
                           person_results: list[PersonYearResult],
                           target: float) -> None:
        extras: dict[int, dict] = {i: {} for i, s in enumerate(self.states) if s.alive}
        current_net = self._household_net(person_results, extras)
        gap = target - current_net
        if gap <= self.TOLERANCE:
            self._apply_extras(person_results, extras)
            return

        order = [s for s in self.hh.withdrawal_order
                 if not (s == "celi" and self.hh.celi_strategy == "jamais")]
        for source in order:
            if gap <= self.TOLERANCE:
                break
            # Personne au revenu imposable le plus bas d'abord (équilibrage)
            candidates = sorted(
                [i for i, s in enumerate(self.states) if s.alive],
                key=lambda i: self.states[i]._tax_situation["ordinary"]
                              + sum(extras[i].values()))
            for idx in candidates:
                if gap <= self.TOLERANCE:
                    break
                st = self.states[idx]
                age = person_results[idx].age
                available = self._sources_for(st, source, age) - extras[idx].get(source, 0.0)
                if available <= 0:
                    continue
                lo, hi = 0.0, available
                # Le retrait maximal suffit-il?
                extras[idx][source] = extras[idx].get(source, 0.0) + hi
                net_hi = self._household_net(person_results, extras)
                if net_hi < target - self.TOLERANCE:
                    gap = target - net_hi
                    continue  # tout pris, source suivante
                # Recherche binaire du montant exact
                for _ in range(30):
                    mid = (lo + hi) / 2
                    extras[idx][source] = extras[idx][source] - (hi - mid)
                    net_mid = self._household_net(person_results, extras)
                    if net_mid >= target:
                        hi = mid
                    else:
                        extras[idx][source] += (hi - mid)
                        lo = mid
                gap = target - self._household_net(person_results, extras)
        self._apply_extras(person_results, extras)

    def _apply_extras(self, person_results: list[PersonYearResult],
                      extras: dict) -> None:
        for idx, extra in extras.items():
            st = self.states[idx]
            pr = person_results[idx]
            sit = st._tax_situation
            if extra.get("reer"):
                pr.wd_reer = st.reer.withdraw(extra["reer"])
                sit["ordinary"] += pr.wd_reer
                sit["cash"] += pr.wd_reer
            if extra.get("ferr"):
                amt = st.ferr.withdraw(extra["ferr"])
                pr.wd_ferr += amt
                sit["ordinary"] += amt
                sit["cash"] += amt
                if pr.age >= 65:
                    sit["pension_eligible"] += amt
            if extra.get("frv"):
                amt = st.frv.withdraw(extra["frv"])
                pr.wd_frv += amt
                sit["ordinary"] += amt
                sit["cash"] += amt
                if pr.age >= 65:
                    sit["pension_eligible"] += amt
            if extra.get("taxable"):
                res = st.taxable.withdraw(extra["taxable"])
                pr.wd_taxable = res["proceeds"]
                pr.wd_taxable_gain = res["realized_gain"]
                sit["capital_gains"] += res["realized_gain"]
                sit["cash"] += res["proceeds"]
            if extra.get("celi"):
                pr.wd_celi = st.celi.withdraw(extra["celi"])
                sit["cash"] += pr.wd_celi

    # ---------- impôts finaux ----------
    def _compute_gis(self, year: int, person_results: list[PersonYearResult]) -> None:
        """SRG basé sur le revenu imposable final (hors SV), en dollars du début."""
        deflator = (1 + self.scen.inflation) ** (year - self.start_year)
        alive = [(i, st) for i, st in enumerate(self.states) if st.alive]
        both_oas = (len(alive) == 2
                    and all(person_results[i].oas > 0 for i, _ in alive))
        combined_income_today = sum(
            max(0.0, person_results[i].taxable_income - person_results[i].oas)
            for i, _ in alive) / deflator
        for i, st in alive:
            pr = person_results[i]
            if pr.age < 65 or pr.oas <= 0:
                continue
            if both_oas:
                gis_today = self.gis.annual_couple_each(combined_income_today)
            else:
                income_today = max(0.0, pr.taxable_income - pr.oas) / deflator
                gis_today = self.gis.annual_single(income_today)
            if gis_today > 0:
                pr.gis = self._index(gis_today, year)
                pr.net_cash += pr.gis

    def _finalize_taxes(self, year: int, person_results: list[PersonYearResult]) -> None:
        alive = [(i, st) for i, st in enumerate(self.states) if st.alive]
        inputs = {}
        for i, st in alive:
            sit = st._tax_situation
            inputs[i] = TaxInput(
                year=self.calc.year, age=person_results[i].age,
                ordinary_income=sit["ordinary"],
                eligible_pension_income=sit["pension_eligible"],
                eligible_dividends=sit["dividends"],
                capital_gains=sit["capital_gains"],
                deductions=sit["deductions"],
                lives_alone=st.lives_alone,
            )
        if len(alive) == 2:
            (i1, s1), (i2, s2) = alive
            best = optimize_pension_split(
                self.calc, self.oas, inputs[i1], inputs[i2],
                s1._tax_situation["oas"], s2._tax_situation["oas"],
                s1._tax_situation["pension_eligible"],
                s2._tax_situation["pension_eligible"], steps=10)
            transfer = best["transfer_1_to_2"] - best["transfer_2_to_1"]
            for i, tax_key, cb_key, tr in (
                    (i1, "tax1", "clawback1", -transfer),
                    (i2, "tax2", "clawback2", transfer)):
                pr = person_results[i]
                pr.tax_total = best[tax_key]
                pr.oas_clawback = best[cb_key]
                pr.pension_split_received = tr
                pr.taxable_income = best[f"result{1 if i == i1 else 2}"].taxable_income
                pr.net_cash = (self.states[i]._tax_situation["cash"]
                               - pr.tax_total - pr.oas_clawback)
        else:
            for i, st in alive:
                r = self.calc.compute(inputs[i])
                pr = person_results[i]
                pr.tax_total = r.total_tax
                pr.taxable_income = r.taxable_income
                pr.marginal_rate = r.marginal_rate
                pr.oas_clawback = self.oas.clawback(
                    r.net_income, st._tax_situation["oas"])
                pr.net_cash = (st._tax_situation["cash"]
                               - pr.tax_total - pr.oas_clawback)
