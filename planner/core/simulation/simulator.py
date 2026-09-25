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

Le SRG est calculé sur le revenu imposable (hors SV) résultant des retraits,
et le solveur le compte comme revenu disponible: il retire donc moins quand
le SRG est versé, au lieu de retirer puis réinvestir l'excédent.
"""
from dataclasses import dataclass, field, replace
import logging

from planner.core.accounts import REER, CELI, CELIAPP, FERR, FRV, Taxable
from planner.core.assets import Debt, RealAsset
from planner.core.benefits import RRQ, OAS, GIS
from planner.core.simulation.splitting import (
    eligible_pension_for_splitting, optimize_pension_split, couple_tax_with_split)
from planner.core.simulation.types import (
    AnnuityConfig, LifeInsuranceConfig,
    HouseholdConfig, ScenarioConfig, PersonConfig,
    PersonYearResult, HouseholdYearResult)
from planner.core.tax import TaxCalculator, TaxInput

log = logging.getLogger(__name__)

SOURCE_LABELS = {"taxable": "non-enregistré", "reer": "REER", "ferr": "FERR",
                 "frv": "FRV", "celi": "CELI"}


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
    # Rente PD réversible héritée: (état du défunt, fraction)
    survivor_db: tuple | None = None
    # Cotisations REER de conjoint reçues {année: montant} (règle des 3 ans)
    spousal_contribs: dict = field(default_factory=dict)
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
        self.debts = [Debt(cfg=d) for d in household.debts]
        self.assets = [RealAsset(cfg=a) for a in household.real_assets]
        self._purchased_annuities: set[int] = set()
        self._death_year: dict[int, int] = {}
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
                       year=self.start_year, inflation=self.scen.inflation)
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

    # ---------- journal ----------
    def _note(self, text: str) -> None:
        self._journal.append(text)

    def _who(self, idx: int) -> str:
        return self.hh.persons[idx].name or f"Personne {idx + 1}"

    @staticmethod
    def _money(x: float) -> str:
        return f"{x:,.0f} $".replace(",", " ")

    def _price_factor(self, year: int) -> float:
        """Niveau des prix de `year` par rapport aux barèmes de l'année de départ."""
        return self._index(1.0, year)

    def _db_status(self, cfg: PersonConfig) -> str:
        if cfg.db_status in {"none", "active", "deferred", "closed_salary_linked", "in_payment"}:
            return cfg.db_status
        return "active" if cfg.db_pension > 0 else "none"

    def _db_pension_for_year(self, st: _PersonState, year: int, age: int) -> float:
        cfg = st.cfg
        status = self._db_status(cfg)
        formula = cfg.db_from_statement
        if (status == "none" or (cfg.db_pension <= 0 and not formula)
                or (status != "in_payment" and age < cfg.db_start_age)):
            return 0.0

        start_year_pd = cfg.birth_year + cfg.db_start_age
        base = cfg.db_pension
        bridge = 0.0
        if status == "in_payment":
            start_year_pd = self.start_year
        else:
            years_to_start = max(0.0, start_year_pd - self.start_year
                                 + self._db_start_offset(cfg))
            retirement_year = cfg.birth_year + cfg.retirement_age
            years_worked = 0.0
            if retirement_year >= self.start_year:
                years_worked = (retirement_year - self.start_year
                                + self._work_fraction(cfg, cfg.retirement_age))
            # La rente cesse de croître à la retraite, même si son début est reporté.
            growth_years = min(years_to_start, years_worked)
            if formula:
                base, bridge = self._db_formula_pension(cfg, growth_years)
            elif status == "active" and growth_years:
                base *= (1 + cfg.db_active_growth) ** growth_years
            elif status == "closed_salary_linked" and growth_years:
                base *= (1 + cfg.salary_growth) ** growth_years

        penalty_years = max(0, cfg.db_normal_age - cfg.db_start_age)
        if status != "in_payment":
            base *= max(0.0, 1 - penalty_years * cfg.db_penalty_per_year)
        if age >= self.rrq.p["reference_age"]:
            base = max(0.0, base - bridge)

        if cfg.db_indexed:
            return base * (1 + self.scen.inflation) ** max(0, year - start_year_pd)
        return base

    def _db_start_offset(self, cfg: PersonConfig) -> float:
        """Part de l'année de début de la rente PD écoulée avant le premier versement."""
        if cfg.db_start_age == cfg.retirement_age:
            return self._work_fraction(cfg, cfg.retirement_age)
        return cfg.birth_month / 12.0

    @staticmethod
    def _first_year_fraction(cfg: PersonConfig) -> float:
        """Part de l'année versée quand une prestation débute le mois suivant l'anniversaire."""
        return 1.0 - cfg.birth_month / 12.0 if cfg.birth_month else 1.0

    def _db_formula_pension(self, cfg: PersonConfig,
                            years_worked: float) -> tuple[float, float]:
        """Rente selon le relevé: (rente annuelle, réduction de coordination dès 65 ans)."""
        service = cfg.db_service_years + years_worked
        if cfg.db_max_service > 0:
            service = min(service, cfg.db_max_service)
        n = max(1, int(cfg.db_avg_years))
        end = int(self.start_year + years_worked)  # première année non complète
        window = range(end - n, end)
        if end <= self.start_year:
            avg_salary = cfg.db_avg_salary
        else:
            avg_salary = sum(cfg.salary * (1 + cfg.salary_growth) ** (y - self.start_year)
                             for y in window) / n
        avg_mga = sum(self.rrq.p["mga"] * (1 + self.scen.inflation) ** (y - self.start_year)
                      for y in window) / n
        coordinated = min(avg_salary, avg_mga)
        if cfg.db_coordination == "step":
            return service * (cfg.db_rate_below_mga * coordinated
                              + cfg.db_accrual_rate * (avg_salary - coordinated)), 0.0
        pension = cfg.db_accrual_rate * service * avg_salary
        if cfg.db_coordination == "bridge":
            return pension, cfg.db_bridge_rate * service * coordinated
        return pension, 0.0

    # ---------- boucle principale ----------
    def run(self) -> list[HouseholdYearResult]:
        results = []
        for year in range(self.start_year, self.end_year + 1):
            results.append(self._simulate_year(year))
        return results

    def _simulate_year(self, year: int) -> HouseholdYearResult:
        hh_result = HouseholdYearResult(year=year)
        self._journal = hh_result.decisions

        # 1. Décès et roulements
        self._pending_payout = 0.0
        self._handle_deaths(year)
        hh_result.insurance_payout = self._pending_payout
        if hh_result.insurance_payout > 0:
            self._note(f"Capital-décès de {self._money(hh_result.insurance_payout)} versé au "
                       "survivant (non-enregistré, libre d'impôt).")

        alive_states = [s for s in self.states if s.alive]
        person_results: list[PersonYearResult] = []

        for st in self.states:
            age = year - st.cfg.birth_year
            pr = PersonYearResult(year=year, age=age, alive=st.alive)
            person_results.append(pr)
            if not st.alive:
                continue
            work = self._work_fraction(st.cfg, age)
            retired = work < 1.0
            pr.retired = retired
            st._tax_situation = self._empty_situation()

            # Droits et conversions (celi_room saisi inclut déjà l'année de départ)
            if year > self.start_year:
                st.celi.new_year(year)
            if age >= 71 and st.reer.balance > 0:
                converted = st.reer.convert_to_ferr()
                st.ferr.balance += converted
                self._note(f"{st.cfg.name}: REER de {self._money(converted)} converti en FERR "
                           f"({age} ans).")
            if st.cri_balance > 0 and (age >= 71 or (work == 0.0 and age >= 55)):
                self._note(f"{st.cfg.name}: CRI de {self._money(st.cri_balance)} converti en FRV "
                           f"({age} ans, {'71 ans atteints' if age >= 71 else 'retraite'}).")
                st.frv.balance += st.cri_balance
                st.cri_balance = 0.0

            # 2. Croissance nette de frais (les distributions deviennent
            #    imposables cette année)
            a = st.cfg.accounts
            delta = self.scen.return_delta_by_year.get(year, 0.0)
            fully_retired = work == 0.0

            def rate(gross: float) -> float:
                return max(-0.95, a.net_return(gross, fully_retired) + delta)

            pr.fees_paid = a.fee_rate * (
                st.reer.balance + st.celi.balance + st.celiapp.balance
                + st.cri_balance + st.ferr.balance + st.frv.balance
                + st.taxable.balance)
            st.reer.grow(rate(a.reer_return))
            st.celi.grow(rate(a.celi_return))
            st.celiapp.grow(rate(a.celiapp_return))
            st.cri_balance *= (1 + rate(a.cri_return))
            st.ferr.grow(rate(a.ferr_return))
            st.frv.grow(rate(a.frv_return))
            inv = st.taxable.grow(rate(a.taxable_return))
            pr.investment_interest = inv["interest"]
            pr.investment_dividends = inv["eligible_dividends"]

        # 3-4. Revenus de l'année, une fois TOUS les comptes ayant crû (les
        # cotisations au REER du conjoint ne doivent pas croître l'année même)
        for st, pr in zip(self.states, person_results):
            if not st.alive:
                continue
            work = self._work_fraction(st.cfg, pr.age)
            if work > 0.0:
                self._accumulation(st, pr, year, work)
            if work < 1.0:
                self._guaranteed_income(st, pr, year, pr.age, 1.0 - work)
            self._personal_credits(st, pr, year)

        # 4a. Partage de la rente RRQ entre conjoints
        self._apply_rrq_sharing(person_results)

        # 4a'. Rentes réversibles au survivant, rentes viagères et primes d'assurance
        self._apply_survivor_db(year, person_results)
        self._process_annuities(year, person_results)
        self._process_insurance_premiums(year, hh_result, person_results)

        # 4b. Actifs réels et passifs du ménage
        self._process_assets_and_debts(year, hh_result, alive_states, person_results)

        # 4c. Retraits pour combler la cible du ménage.
        # La cible ne s'applique qu'à partir de la retraite (au prorata de
        # l'année pour une retraite en cours d'année): pendant
        # l'accumulation, le ménage vit de ses salaires et le solveur ne
        # couvre que les besoins ponctuels (dépenses spéciales, véhicules).
        # Le service de la dette et les primes d'assurance en accumulation
        # sont supposés couverts par les salaires; à la retraite ils
        # s'ajoutent à la cible.
        retired_fraction = max(
            (1.0 - self._work_fraction(st.cfg, year - st.cfg.birth_year)
             for st in alive_states), default=0.0)
        special = (self.hh.special_expenses.get(year, 0.0)
                   + hh_result.vehicle_expenses)
        if retired_fraction > 0.0:
            target = ((self._year_target(year) + hh_result.debt_service
                       + hh_result.insurance_premiums)
                      * retired_fraction + hh_result.vehicle_expenses)
        else:
            target = None
        hh_result.target_net = target if target is not None else special
        hh_result.special_expenses = special
        if target is not None:
            parts = [f"cible {self._money(self._year_target(year))}"]
            if hh_result.debt_service > 0:
                parts.append(f"dettes {self._money(hh_result.debt_service)}")
            if hh_result.insurance_premiums > 0:
                parts.append(f"assurance {self._money(hh_result.insurance_premiums)}")
            if retired_fraction < 1.0:
                parts.append(f"× {retired_fraction:.0%} de l'année à la retraite")
            if hh_result.vehicle_expenses > 0:
                parts.append(f"véhicule {self._money(hh_result.vehicle_expenses)}")
            self._note(f"Besoin net de l'année: {self._money(target)} (" + ", ".join(parts) + ").")
        elif special > 0:
            self._note(f"Accumulation: seules les dépenses ponctuelles de "
                       f"{self._money(special)} sont à financer par retraits.")
        hh_result.shortfall_note = self._solve_withdrawals(
            year, alive_states, person_results, target, special)

        # 4d. Fonte du REER: retraits volontaires jusqu'au plancher de revenu
        if target is not None:
            self._apply_income_floor(year, person_results)

        # 5. Impôts finaux avec fractionnement optimal
        self._finalize_taxes(year, person_results)

        # 5b. SRG calculé sur le revenu imposable réel (hors SV), comme le
        # programme officiel qui se base sur le revenu déclaré. Déjà anticipé
        # par le solveur; recalculé ici sur le fractionnement final.
        self._compute_gis(year, person_results)

        # 5c. Surplus (minimums FERR/FRV forcés) réinvesti plutôt que perdu
        if target is not None:
            hh_result.reinvested = self._reinvest_surplus(person_results, target)
        elif special <= 0 and sum(p.net_cash for p in person_results if p.alive) > 0:
            self._note("Accumulation: le net encaissé des salaires couvre le train de vie "
                       "(aucune cible à combler).")

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
            pr.reer_room = st.reer.contribution_room
            pr.celi_room = st.celi.contribution_room
            pr.celiapp_room = st.celiapp.contribution_room

        hh_result.persons = person_results
        hh_result.net_cash = sum(p.net_cash for p in person_results)
        hh_result.total_tax = sum(p.tax_total + p.oas_clawback for p in person_results)
        hh_result.total_fees = sum(p.fees_paid for p in person_results)
        hh_result.total_wealth = sum(p.wealth for p in person_results)
        hh_result.debts_balance = sum(d.balance for d in self.debts)
        hh_result.real_assets_value = sum(a.value for a in self.assets)
        hh_result.real_assets_gain = sum(a.unrealized_gain for a in self.assets)
        hh_result.real_assets_recapture = sum(a.unrealized_recapture for a in self.assets)
        hh_result.insurance_in_force = sum(
            ins.face_amount for ins in self.hh.life_insurances
            if self._insurance_in_force(ins, year))
        hh_result.target_gap = (hh_result.net_cash - target
                                if target is not None else 0.0)
        return hh_result

    # ---------- rentes viagères et assurance vie ----------
    def _apply_survivor_db(self, year: int,
                           person_results: list[PersonYearResult]) -> None:
        """Rente PD réversible: le survivant reçoit la fraction convenue de la rente
        que le défunt aurait touchée cette année (même indexation, même début)."""
        for i, st in enumerate(self.states):
            if not st.alive or not st.survivor_db:
                continue
            deceased, pct = st.survivor_db
            would_be_age = year - deceased.cfg.birth_year
            amount = pct * self._db_pension_for_year(deceased, year, would_be_age)
            if amount <= self.TOLERANCE:
                continue
            pr = person_results[i]
            pr.db_pension += amount
            sit = st._tax_situation
            sit["ordinary"] += amount
            sit["pension_eligible"] += amount  # rente PD: admissible à tout âge
            sit["cash"] += amount
            if year == self._death_year.get(id(deceased)):
                self._note(f"{st.cfg.name}: rente PD de survivant de {self._money(amount)}/an "
                           f"({pct:.0%} de la rente de {deceased.cfg.name}).")

    def _process_annuities(self, year: int,
                           person_results: list[PersonYearResult]) -> None:
        for k, ann in enumerate(self.hh.annuities):
            if ann.person_index >= len(self.states):
                continue
            st = self.states[ann.person_index]
            pr = person_results[ann.person_index]
            if year < ann.purchase_year:
                continue
            fraction = 1.0
            if not st.alive:
                # Rente réversible: versements réduits au conjoint survivant
                survivor = self._spouse_index(ann.person_index)
                if (k not in self._purchased_annuities or survivor is None
                        or ann.survivor_pct <= 0):
                    continue
                st = self.states[survivor]
                pr = person_results[survivor]
                fraction = ann.survivor_pct
                if year == self._death_year.get(id(self.states[ann.person_index])):
                    self._note(f"{st.cfg.name}: rente « {ann.name} » réversible à "
                               f"{fraction:.0%} — versements maintenus au survivant.")
            sit = st._tax_situation
            if year == ann.purchase_year:
                self._buy_annuity(st, pr, ann)
                self._purchased_annuities.add(k)
                self._note(f"{st.cfg.name}: achat de la rente « {ann.name} » — prime "
                           f"{self._money(ann.premium)} prélevée du {SOURCE_LABELS.get(ann.source, ann.source)}, "
                           f"versement {self._money(ann.annual_payment)}/an"
                           + (f", réversible à {ann.survivor_pct:.0%}" if ann.survivor_pct > 0 else "")
                           + ".")
            payment = fraction * ann.annual_payment * (
                (1 + self.scen.inflation) ** (year - ann.purchase_year)
                if ann.indexed else 1.0)
            taxable = payment * ann.default_taxable_fraction()
            pr.annuity_income += payment
            sit["cash"] += payment
            sit["ordinary"] += taxable
            if ann.source in ("reer", "ferr") and pr.age >= 65:
                sit["pension_eligible"] += taxable

    def _buy_annuity(self, st: _PersonState, pr: PersonYearResult,
                     ann: 'AnnuityConfig') -> None:
        """Prélève la prime dans le compte source (transfert direct: aucun
        impôt pour un REER/FERR; gain réalisé pour le non-enregistré)."""
        sit = st._tax_situation
        if ann.source == "reer":
            taken = st.reer.withdraw(ann.premium)
            if taken < ann.premium:  # compléter avec le FERR si déjà converti
                taken += st.ferr.withdraw(ann.premium - taken)
        elif ann.source == "ferr":
            taken = st.ferr.withdraw(ann.premium)
        elif ann.source == "celi":
            taken = st.celi.withdraw(ann.premium)
        else:
            res = st.taxable.withdraw(ann.premium)
            taken = res["proceeds"]
            sit["capital_gains"] += res["realized_gain"]
        if taken + 1e-6 < ann.premium:
            log.info("%d: prime de rente réduite à %.0f (solde insuffisant)",
                     pr.year, taken)

    def _insurance_in_force(self, ins: 'LifeInsuranceConfig', year: int,
                            require_alive: bool = True) -> bool:
        if ins.person_index >= len(self.states):
            return False
        st = self.states[ins.person_index]
        age = year - st.cfg.birth_year
        return (st.alive or not require_alive) and age <= ins.coverage_until_age

    def _process_insurance_premiums(self, year: int, hh_result: HouseholdYearResult,
                                    person_results: list[PersonYearResult]) -> None:
        for ins in self.hh.life_insurances:
            if not self._insurance_in_force(ins, year):
                continue
            st = self.states[ins.person_index]
            pr = person_results[ins.person_index]
            if pr.age > ins.premium_until_age:
                continue
            pr.insurance_premium += ins.annual_premium
            hh_result.insurance_premiums += ins.annual_premium
            if not pr.retired:  # en accumulation: payée à même le salaire
                st._tax_situation["cash"] -= ins.annual_premium

    def _pay_death_benefits(self, deceased_index: int, survivor: _PersonState,
                            year: int) -> float:
        """Capital-décès (libre d'impôt) versé au conjoint survivant."""
        total = 0.0
        for ins in self.hh.life_insurances:
            if (ins.person_index == deceased_index
                    and self._insurance_in_force(ins, year, require_alive=False)):
                total += ins.face_amount
        if total > 0:
            survivor.taxable.contribute(total)
        return total

    # ---------- fonte du REER ----------
    def _apply_income_floor(self, year: int,
                            person_results: list[PersonYearResult]) -> None:
        """Retire du REER puis du FERR jusqu'au plancher de revenu imposable
        par personne; l'excédent net sera réinvesti par `_reinvest_surplus`."""
        floor = self.hh.taxable_income_floor
        if not floor or floor <= 0:
            return
        floor_now = self._index(floor, year)
        for i, st in enumerate(self.states):
            pr = person_results[i]
            if not st.alive or not pr.retired:
                continue
            sit = st._tax_situation
            room = floor_now - sit["ordinary"]
            if room <= self.TOLERANCE:
                continue
            amt = st.reer.withdraw(room)
            pr.wd_reer += amt
            room -= amt
            from_ferr = 0.0
            if room > self.TOLERANCE and st.ferr.balance > 0:
                from_ferr = st.ferr.withdraw(room)
                pr.wd_ferr += from_ferr
                if pr.age >= 65:
                    sit["pension_eligible"] += from_ferr
                amt += from_ferr
            pr.meltdown_withdrawal = amt
            sit["ordinary"] += amt
            sit["cash"] += amt
            if amt > self.TOLERANCE:
                self._note(f"Fonte du REER — {st.cfg.name}: retrait volontaire de "
                           f"{self._money(amt)} pour porter le revenu imposable au plancher "
                           f"{self._money(floor_now)}"
                           + (f" (dont {self._money(from_ferr)} du FERR)" if from_ferr > self.TOLERANCE else "")
                           + ("; plancher non atteint (comptes épuisés)" if room - from_ferr > self.TOLERANCE else "")
                           + ".")

    # ---------- actifs réels et passifs ----------
    def _process_assets_and_debts(self, year: int,
                                  hh_result: 'HouseholdYearResult',
                                  alive_states: list,
                                  person_results: list[PersonYearResult]) -> None:
        # Service de la dette
        for debt in self.debts:
            service = debt.annual_service()
            hh_result.debt_service += service["payment"]
            hh_result.debt_interest += service["interest"]
        # Appréciation, loyers puis ventes planifiées
        recipient = alive_states[0] if alive_states else None
        alive_idx = [i for i, st in enumerate(self.states) if st.alive]
        pf = self._price_factor(year)
        for asset in self.assets:
            asset.appreciate()
            if asset.is_rental and alive_idx:
                rent = asset.annual_rental(pf)
                hh_result.rental_income += rent["cash"]
                share = 1.0 / len(alive_idx)  # copropriété à parts égales
                for i in alive_idx:
                    sit = self.states[i]._tax_situation
                    sit["cash"] += rent["cash"] * share
                    sit["ordinary"] += rent["taxable"] * share
                    person_results[i].rental_income += rent["cash"] * share
            if (asset.cfg.sale_year == year and not asset.sold
                    and recipient is not None):
                sale = asset.sell()
                proceeds = sale["proceeds"]
                # Rembourser la dette liée
                paid_off = 0.0
                if asset.cfg.linked_debt:
                    for debt in self.debts:
                        if debt.cfg.name == asset.cfg.linked_debt:
                            paid_off = debt.payoff()
                            proceeds -= paid_off
                            break
                proceeds = max(0.0, proceeds)
                self._note(f"Vente de « {asset.cfg.name} »: produit {self._money(sale['proceeds'])}"
                           + (f", dette liée remboursée {self._money(paid_off)}" if paid_off else "")
                           + f" → {self._money(proceeds)} au non-enregistré"
                           + (f"; gain imposable {self._money(sale['taxable_gain'])}"
                              if sale["taxable_gain"] > 0 else "; aucun gain imposable")
                           + ".")
                # Le produit net va au compte non-enregistré (PBR = produit)
                recipient.taxable.contribute(proceeds)
                hh_result.asset_sale_proceeds += proceeds
                # Gain imposable si non exonéré (résidence principale exonérée)
                if sale["taxable_gain"] > 0:
                    recipient._tax_situation["capital_gains"] += sale["taxable_gain"]
                # Récupération de DPA: revenu ordinaire
                if sale["recapture"] > 0:
                    recipient._tax_situation["ordinary"] += sale["recapture"]
        # Remplacements de véhicules (coût indexé)
        for plan in self.hh.vehicle_plans:
            if plan.cost_in_year(year):
                hh_result.vehicle_expenses += self._index(plan.net_cost, year)

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
                self._note(f"Décès de {st.cfg.name} ({age} ans"
                           + (", scénario de décès prématuré" if premature else "") + ").")
                survivors = [s for s in self.states if s.alive]
                if survivors:
                    self._rollover_to_survivor(st, survivors[0], year)
                    self._note(f"Roulement des comptes de {st.cfg.name} à {survivors[0].cfg.name} "
                               "sans impôt; rente de survivant RRQ activée.")
                    self._pending_payout += self._pay_death_benefits(
                        i, survivors[0], year)

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
        if deceased.cfg.db_survivor_pct > 0 and self._db_status(deceased.cfg) != "none":
            survivor.survivor_db = (deceased, deceased.cfg.db_survivor_pct)
        self._death_year[id(deceased)] = year
        deceased.reer.balance = deceased.ferr.balance = deceased.frv.balance = 0.0
        deceased.celi.balance = deceased.taxable.balance = deceased.taxable.acb = 0.0
        deceased.cri_balance = 0.0

    # ---------- situation fiscale de l'année ----------
    @staticmethod
    def _empty_situation() -> dict:
        return {"ordinary": 0.0, "pension_eligible": 0.0, "dividends": 0.0,
                "capital_gains": 0.0, "deductions": 0.0, "cash": 0.0,
                "oas": 0.0, "employment": 0.0,
                "medical": 0.0, "donations": 0.0, "home_support": 0.0}

    def _work_fraction(self, cfg: PersonConfig, age: int) -> float:
        """Part de l'année travaillée: 1 avant la retraite, 0 après, prorata
        l'année de la retraite selon le mois de départ."""
        if age < cfg.retirement_age:
            return 1.0
        if age > cfg.retirement_age:
            return 0.0
        if cfg.retirement_month:
            return (max(1, min(12, cfg.retirement_month)) - 1) / 12.0
        return cfg.birth_month / 12.0  # 1er du mois suivant l'anniversaire (0 si inconnu)

    def _spouse_index(self, idx: int) -> int | None:
        for j, st in enumerate(self.states):
            if j != idx and st.alive:
                return j
        return None

    def _personal_credits(self, st: _PersonState, pr: PersonYearResult,
                          year: int) -> None:
        cfg = st.cfg
        sit = st._tax_situation
        sit["medical"] = self._index(cfg.medical_expenses, year)
        sit["donations"] = self._index(cfg.donations, year)
        sit["home_support"] = self._index(cfg.home_support_expenses, year)
        # Ces dépenses sont réputées incluses dans la cible de dépenses:
        # seul le crédit qui en découle modifie les liquidités.

    def _tax_input(self, st: _PersonState, pr: PersonYearResult,
                   ordinary_extra: float = 0.0, pension_extra: float = 0.0,
                   gains_extra: float = 0.0) -> TaxInput:
        sit = st._tax_situation
        return TaxInput(
            year=self.calc.year, age=pr.age,
            ordinary_income=max(0.0, sit["ordinary"] + ordinary_extra),
            eligible_pension_income=sit["pension_eligible"] + pension_extra,
            eligible_dividends=sit["dividends"],
            capital_gains=sit["capital_gains"] + gains_extra,
            deductions=sit["deductions"],
            lives_alone=st.lives_alone,
            medical_expenses=sit["medical"],
            donations=sit["donations"],
            home_support_expenses=sit["home_support"],
        )

    # ---------- accumulation ----------
    def _accumulation(self, st: _PersonState, pr: PersonYearResult, year: int,
                      fraction: float = 1.0) -> None:
        c = st.cfg.contributions
        pr.salary = st.salary * fraction
        # Les % sont appliqués sur le salaire réellement gagné dans l'année.
        employee_dc = max(0.0, pr.salary * c.dc_employee_pct + c.dc_employee_fixed * fraction)
        employer_dc = max(0.0, pr.salary * c.dc_employer_pct + c.dc_employer_fixed * fraction)
        st.reer.add_new_room(pr.salary, self._price_factor(year))
        pr.contrib_reer = st.reer.contribute(pr.salary * c.reer_pct + c.reer_fixed * fraction)
        pr.contrib_spousal_reer = self._spousal_contribution(
            st, pr.salary * c.spousal_reer_pct + c.spousal_reer_fixed * fraction, year)
        celi_fixed = self._index(c.celi_fixed, year) if c.celi_fixed_indexed else c.celi_fixed
        celi_requested = max(0.0, pr.salary * c.celi_pct + celi_fixed * fraction)
        pr.contrib_celi = st.celi.contribute(celi_requested)
        celi_overflow = (celi_requested - pr.contrib_celi
                         if c.celi_overflow_to_taxable else 0.0)
        pr.contrib_celiapp = st.celiapp.contribute(c.celiapp_fixed * fraction)
        pr.contrib_taxable = st.taxable.contribute(
            pr.salary * c.taxable_pct + c.taxable_fixed * fraction + celi_overflow)
        pr.contrib_dc_employee = employee_dc
        pr.contrib_dc_employer = employer_dc
        st.cri_balance += employee_dc + employer_dc
        st.celiapp.new_year()
        st.salary *= (1 + st.cfg.salary_growth)
        sit = st._tax_situation
        sit["ordinary"] += pr.salary + pr.investment_interest
        sit["employment"] += pr.salary
        sit["dividends"] += pr.investment_dividends
        sit["deductions"] += pr.contrib_reer + pr.contrib_spousal_reer + pr.contrib_celiapp
        sit["cash"] += (pr.salary - pr.contrib_reer - pr.contrib_spousal_reer
                        - pr.contrib_celi - pr.contrib_celiapp - pr.contrib_taxable
                        - employee_dc)

    def _spousal_contribution(self, st: _PersonState, requested: float,
                              year: int) -> float:
        """Cotisation au REER du conjoint: droits et déduction du cotisant."""
        if requested <= 0 or not self.hh.is_couple:
            return 0.0
        idx = self.states.index(st)
        j = self._spouse_index(idx)
        if j is None:
            return 0.0
        spouse = self.states[j]
        actual = max(0.0, min(requested, st.reer.contribution_room))
        if actual <= 0:
            return 0.0
        st.reer.contribution_room -= actual
        spouse.reer.balance += actual
        spouse.spousal_contribs[year] = spouse.spousal_contribs.get(year, 0.0) + actual
        return actual

    def _spousal_attribution(self, idx: int, reer_withdrawal: float,
                             year: int) -> float:
        """Part d'un retrait REER réattribuée au conjoint cotisant (cotisations
        de l'année et des deux précédentes)."""
        st = self.states[idx]
        if reer_withdrawal <= 0 or not st.spousal_contribs:
            return 0.0
        if self._spouse_index(idx) is None:
            return 0.0  # cotisant décédé: pas d'attribution
        pool = sum(v for y, v in st.spousal_contribs.items() if year - 2 <= y <= year)
        return min(reer_withdrawal, pool)

    def _consume_spousal_pool(self, st: _PersonState, amount: float, year: int) -> None:
        for y in sorted(st.spousal_contribs):
            if amount <= 0:
                break
            if y < year - 2:
                continue
            take = min(amount, st.spousal_contribs[y])
            st.spousal_contribs[y] -= take
            amount -= take

    # ---------- revenus garantis ----------
    def _guaranteed_income(self, st: _PersonState, pr: PersonYearResult,
                           year: int, age: int, fraction: float = 1.0) -> None:
        cfg = st.cfg
        # Rente PD avec statut, croissance préretraite et pénalité d'anticipation;
        # au prorata si elle débute l'année de la retraite en cours d'année.
        pr.db_pension = self._db_pension_for_year(st, year, age)
        if self._db_status(cfg) != "in_payment" and age == cfg.db_start_age:
            pr.db_pension *= 1.0 - self._db_start_offset(cfg)
        # RRQ (ajustée selon l'âge de début, indexée) + rente de survivant
        if age >= cfg.rrq_start_age and cfg.rrq_monthly_at_65 > 0:
            pr.rrq = self._index(st.rrq_annual_at_start, year)
            if age == cfg.rrq_start_age:
                pr.rrq *= self._first_year_fraction(cfg)
        pr.rrq += self._index(st.survivor_rrq, year) if st.survivor_rrq else 0.0
        # SV (report, 75+, résidence)
        oas_base = self.oas.annual_pension(age, cfg.oas_start_age,
                                           cfg.oas_residence_years)
        pr.oas = self._index(oas_base, year)
        if age == cfg.oas_start_age:
            pr.oas *= self._first_year_fraction(cfg)
        # Emploi à temps partiel après la retraite
        if cfg.part_time_income > 0 and age <= cfg.part_time_until_age:
            pr.part_time_income = self._index(cfg.part_time_income, year) * fraction
        # Minimums FERR/FRV
        pr.ferr_min = st.ferr.min_withdrawal(age)
        pr.frv_min = st.frv.min_withdrawal(age)
        pr.wd_ferr = st.ferr.withdraw(pr.ferr_min)
        pr.wd_frv = st.frv.withdraw(pr.frv_min)
        if pr.wd_ferr + pr.wd_frv > self.TOLERANCE:
            parts = [f"FERR {self._money(pr.wd_ferr)}"] if pr.wd_ferr > self.TOLERANCE else []
            parts += [f"FRV {self._money(pr.wd_frv)}"] if pr.wd_frv > self.TOLERANCE else []
            self._note(f"{cfg.name}: retraits minimums obligatoires — " + ", ".join(parts)
                       + f" ({age} ans"
                       + (", âge du conjoint" if st.ferr.use_spouse_age else "") + ").")

        pension_eligible = eligible_pension_for_splitting(
            age, pr.db_pension, pr.wd_ferr + pr.wd_frv)
        sit = st._tax_situation
        guaranteed = pr.db_pension + pr.rrq + pr.oas + pr.wd_ferr + pr.wd_frv
        sit["ordinary"] += guaranteed + pr.part_time_income
        sit["employment"] += pr.part_time_income
        sit["pension_eligible"] += pension_eligible
        if fraction >= 1.0:  # sinon déjà comptés par l'accumulation
            sit["ordinary"] += pr.investment_interest
            sit["dividends"] += pr.investment_dividends
        sit["cash"] += guaranteed + pr.part_time_income
        sit["oas"] = pr.oas

    def _apply_rrq_sharing(self, person_results: list[PersonYearResult]) -> None:
        """Partage de la rente RRQ: les deux conjoints ont 60 ans+, chacun
        reçoit ou n'a aucune rente; la part commune est divisée en deux."""
        if not self.hh.rrq_sharing or not self.hh.is_couple:
            return
        alive = [(i, st) for i, st in enumerate(self.states) if st.alive]
        if len(alive) != 2:
            return
        for i, st in alive:
            pr = person_results[i]
            if pr.age < 60:
                return
            receiving = pr.age >= st.cfg.rrq_start_age
            if st.cfg.rrq_monthly_at_65 > 0 and not receiving:
                return
        frac = min(1.0, max(0.0, self.hh.rrq_share_fraction))
        own = {i: person_results[i].rrq - self._index(st.survivor_rrq, person_results[i].year)
               for i, st in alive}  # la rente de survivant n'est pas partageable
        pool = sum(own.values()) * frac
        for i, st in alive:
            new_rrq = own[i] * (1 - frac) + pool / 2
            delta = new_rrq - own[i]
            pr = person_results[i]
            pr.rrq += delta
            pr.rrq_shared_delta = delta
            st._tax_situation["ordinary"] += delta
            st._tax_situation["cash"] += delta
            if delta > self.TOLERANCE:
                self._note(f"Partage RRQ: {self._money(delta)} transférés au profit de "
                           f"{st.cfg.name}.")

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
                       extras: dict, year: int) -> float:
        """Revenu net du ménage pour des retraits additionnels donnés.

        `extras`: {person_index: {source: montant}} — évaluation SANS modifier
        les états.
        """
        pf = self._price_factor(year)
        alive_idx = [i for i, st in enumerate(self.states) if st.alive]
        # Retraits REER de conjoint réattribués au cotisant (règle des 3 ans)
        shift = {i: 0.0 for i in alive_idx}
        for idx in alive_idx:
            attributed = self._spousal_attribution(
                idx, extras.get(idx, {}).get("reer", 0.0), year)
            if attributed > 0:
                shift[idx] -= attributed
                shift[self._spouse_index(idx)] += attributed
        inputs, cash_flows, oas_amounts, eligibles = [], [], [], []
        for idx in alive_idx:
            st = self.states[idx]
            sit = st._tax_situation
            age = person_results[idx].age
            extra = extras.get(idx, {})
            add_ordinary = (extra.get("reer", 0.0) + extra.get("ferr", 0.0)
                            + extra.get("frv", 0.0))
            tx = extra.get("taxable", 0.0)
            gain_ratio = (1 - min(1.0, st.taxable.acb / st.taxable.balance)
                          if st.taxable.balance > 0 else 0.0)
            add_gains = tx * gain_ratio
            add_pension = (extra.get("ferr", 0.0) + extra.get("frv", 0.0)) if age >= 65 else 0.0
            inputs.append(self._tax_input(
                st, person_results[idx],
                ordinary_extra=add_ordinary + shift[idx],
                pension_extra=add_pension, gains_extra=add_gains))
            cash_flows.append(sit["cash"] + add_ordinary + tx + extra.get("celi", 0.0))
            oas_amounts.append(sit["oas"])
            eligibles.append(sit["pension_eligible"] + add_pension)

        if len(inputs) == 2:
            best = optimize_pension_split(
                self.calc, self.oas, inputs[0], inputs[1],
                oas_amounts[0], oas_amounts[1], eligibles[0], eligibles[1],
                steps=5, price_factor=pf)
            total_tax = best["total"]
            results = (best["result1"], best["result2"])
        else:
            r = self.calc.compute(inputs[0], _marginal_probe=False, price_factor=pf)
            total_tax = r.total_tax + self.oas.clawback(r.net_income, oas_amounts[0], pf)
            results = (r,)
        taxable = dict(zip(alive_idx, (r.taxable_income for r in results)))
        refundable = sum(r.refundable_credits for r in results)
        gis = self._gis_amounts(year, person_results, taxable)
        return sum(cash_flows) - total_tax + refundable + sum(gis.values())

    def _solve_withdrawals(self, year: int, alive_states: list[_PersonState],
                           person_results: list[PersonYearResult],
                           target: float | None, special: float = 0.0) -> str:
        """Comble la cible par retraits; retourne une note si elle reste hors
        d'atteinte (vide sinon)."""
        extras: dict[int, dict] = {i: {} for i, s in enumerate(self.states) if s.alive}
        current_net = self._household_net(person_results, extras, year)
        if target is None:
            # Accumulation: le solveur ne couvre que les dépenses spéciales.
            if special <= 0:
                self._apply_extras(person_results, extras)
                return ""
            target = current_net + special
        gap = target - current_net
        if gap <= self.TOLERANCE:
            self._apply_extras(person_results, extras)
            self._note(f"Net avant retraits additionnels {self._money(current_net)} couvre le besoin: "
                       "aucun retrait"
                       + (f", surplus de {self._money(-gap)} à réinvestir" if -gap > self.TOLERANCE else "")
                       + ".")
            return ""
        self._note(f"Net avant retraits additionnels {self._money(current_net)} → manque "
                   f"{self._money(gap)}; ordre de retrait: "
                   + " → ".join(SOURCE_LABELS[s] for s in self.hh.withdrawal_order
                                 if not (s == "celi" and self.hh.celi_strategy == "jamais"))
                   + (" (CELI exclu par la stratégie «jamais»)"
                      if self.hh.celi_strategy == "jamais" else "") + ".")

        order = [s for s in self.hh.withdrawal_order
                 if not (s == "celi" and self.hh.celi_strategy == "jamais")]
        alive_idx = [i for i, s in enumerate(self.states) if s.alive]
        exhausted, empty = [], []
        for source in order:
            if gap <= self.TOLERANCE:
                break
            caps = {i: max(0.0, self._sources_for(self.states[i], source,
                                                  person_results[i].age))
                    for i in alive_idx}
            available = sum(caps.values())
            if available <= 0:
                empty.append(source)
                self._note(f"  {SOURCE_LABELS[source]}: déjà vide, source suivante.")
                continue

            def apply(total: float) -> float:
                for i, amt in self._allocate(source, total, caps, extras).items():
                    extras[i][source] = amt
                return self._household_net(person_results, extras, year)

            def split_text() -> str:
                parts = [f"{self._who(i)} {self._money(extras[i].get(source, 0.0))}"
                         for i in alive_idx if extras[i].get(source, 0.0) > self.TOLERANCE]
                return " (" + ", ".join(parts) + ")" if len(alive_idx) > 1 and parts else ""

            # Le retrait maximal suffit-il?
            net_hi = apply(available)
            if net_hi < target - self.TOLERANCE:
                gap = target - net_hi
                exhausted.append(source)
                self._note(f"  {SOURCE_LABELS[source]}: tout retiré, {self._money(available)}"
                           f"{split_text()} → net {self._money(net_hi)}, manque encore "
                           f"{self._money(gap)}.")
                continue  # tout pris, source suivante
            # Recherche binaire du montant total exact
            lo, hi = 0.0, available
            for _ in range(30):
                mid = (lo + hi) / 2
                if apply(mid) >= target:
                    hi = mid
                else:
                    lo = mid
            net_final = apply(hi)
            gap = target - net_final
            self._note(f"  {SOURCE_LABELS[source]}: retrait de {self._money(hi)} sur "
                       f"{self._money(available)} disponibles{split_text()} → net "
                       f"{self._money(net_final)}, besoin comblé.")
        self._apply_extras(person_results, extras)
        if gap <= self.TOLERANCE:
            return ""
        note = self._shortfall_note(gap, exhausted, empty)
        self._note(f"⚠️ Cible non atteinte: {note}.")
        log.info("%d: %s", year, note)
        return note

    def _shortfall_note(self, gap: float, exhausted: list[str],
                        empty: list[str]) -> str:
        parts = [f"manque {gap:,.0f} $".replace(",", " ")]
        if exhausted:
            parts.append("épuisé cette année: "
                         + ", ".join(SOURCE_LABELS[s] for s in exhausted))
        if empty:
            parts.append("déjà vide: " + ", ".join(SOURCE_LABELS[s] for s in empty))
        if self.hh.celi_strategy == "jamais":
            celi = sum(s.celi.balance for s in self.states if s.alive)
            if celi > 0:
                parts.append(f"CELI exclu par la stratégie «jamais» "
                             f"({celi:,.0f} $ disponibles)".replace(",", " "))
        return "; ".join(parts)

    def _allocate(self, source: str, total: float, caps: dict[int, float],
                  extras: dict) -> dict[int, float]:
        """Répartit un retrait total d'une source entre les personnes vivantes.

        CELI (non imposable): au prorata des soldes. Sources imposables:
        nivellement des revenus imposables (on comble d'abord le conjoint au
        revenu le plus bas), dans la limite des soldes.
        """
        if source == "celi":
            pool = sum(caps.values())
            return {i: total * c / pool for i, c in caps.items()} if pool > 0 else {}

        def taxable_proxy(i: int) -> float:
            ex = extras[i]
            return (self.states[i]._tax_situation["ordinary"]
                    + sum(ex.get(k, 0.0) for k in ("reer", "ferr", "frv")
                          if k != source))

        income = {i: taxable_proxy(i) for i in caps}
        alloc = {i: 0.0 for i in caps}
        remaining = total
        while remaining > 1e-6:
            active = [i for i in caps if alloc[i] < caps[i] - 1e-9]
            if not active:
                break
            levels = {i: income[i] + alloc[i] for i in active}
            lowest = min(levels.values())
            low_set = [i for i in active if levels[i] <= lowest + 1e-6]
            higher = [levels[i] for i in active if i not in low_set]
            room_to_next = (min(higher) - lowest) if higher else float("inf")
            step = min(room_to_next, remaining / len(low_set),
                       min(caps[i] - alloc[i] for i in low_set))
            if step <= 0:
                break
            for i in low_set:
                alloc[i] += step
            remaining -= step * len(low_set)
        return alloc

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
                attributed = self._spousal_attribution(idx, pr.wd_reer, pr.year)
                if attributed > 0:
                    j = self._spouse_index(idx)
                    sit["ordinary"] -= attributed
                    self.states[j]._tax_situation["ordinary"] += attributed
                    pr.spousal_attributed -= attributed
                    person_results[j].spousal_attributed += attributed
                    self._consume_spousal_pool(st, attributed, pr.year)
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

    def _reinvest_surplus(self, person_results: list[PersonYearResult],
                          target: float) -> float:
        """Place l'excédent de liquidités sur la cible: CELI (droits) puis
        non-enregistré de la personne au revenu le plus bas."""
        surplus = sum(p.net_cash for p in person_results if p.alive) - target
        if surplus <= self.TOLERANCE:
            return 0.0
        alive = sorted(
            [(i, st) for i, st in enumerate(self.states) if st.alive],
            key=lambda t: person_results[t[0]].taxable_income)
        remaining = surplus
        placed = []
        for i, st in alive:
            put = st.celi.contribute(remaining)
            person_results[i].contrib_celi += put
            remaining -= put
            if put > self.TOLERANCE:
                placed.append(f"CELI de {self._who(i)} {self._money(put)}")
            if remaining <= 0:
                break
        if remaining > 0:
            i, st = alive[0]
            st.taxable.contribute(remaining)
            person_results[i].contrib_taxable += remaining
            placed.append(f"non-enregistré de {self._who(i)} {self._money(remaining)}")
        self._note(f"Surplus de {self._money(surplus)} réinvesti: " + ", ".join(placed) + ".")
        return surplus

    # ---------- impôts finaux ----------
    def _gis_amounts(self, year: int, person_results: list[PersonYearResult],
                     taxable_income: dict[int, float]) -> dict[int, float]:
        """SRG par personne (dollars de l'année) selon le revenu imposable hors SV.

        Le barème est en dollars du début: revenus déflatés, SRG réinflaté.
        """
        pf = self._price_factor(year)
        alive = list(taxable_income)
        both_oas = (len(alive) == 2
                    and all(person_results[i].oas > 0 for i in alive))
        combined_today = sum(
            max(0.0, taxable_income[i] - person_results[i].oas)
            for i in alive) / pf
        employment_today = sum(
            self.states[i]._tax_situation["employment"] for i in alive) / pf
        out = {}
        for i in alive:
            pr = person_results[i]
            if pr.age < 65 or pr.oas <= 0:
                continue
            if both_oas:
                gis_today = self.gis.annual_couple_each(combined_today, employment_today)
            else:
                income_today = max(0.0, taxable_income[i] - pr.oas) / pf
                gis_today = self.gis.annual_single(
                    income_today, self.states[i]._tax_situation["employment"] / pf)
            if gis_today > 0:
                out[i] = gis_today * pf
        return out

    def _compute_gis(self, year: int, person_results: list[PersonYearResult]) -> None:
        """SRG sur le revenu imposable final (après fractionnement)."""
        taxable = {i: person_results[i].taxable_income
                   for i, st in enumerate(self.states) if st.alive}
        for i, gis in self._gis_amounts(year, person_results, taxable).items():
            person_results[i].gis = gis
            person_results[i].net_cash += gis

    def _marginal_rate(self, inp, base_tax: float, pf: float) -> float:
        """Impôt sur 100 $ de revenu ordinaire additionnel (après fractionnement)."""
        probe = replace(
            inp, ordinary_income=inp.ordinary_income + 100.0,
            family_net_income=(inp.family_net_income + 100.0
                               if inp.family_net_income is not None else None))
        probe_tax = self.calc.compute(probe, _marginal_probe=False, price_factor=pf).total_tax
        return (probe_tax - base_tax) / 100.0

    def _finalize_taxes(self, year: int, person_results: list[PersonYearResult]) -> None:
        pf = self._price_factor(year)
        alive = [(i, st) for i, st in enumerate(self.states) if st.alive]
        inputs = {i: self._tax_input(st, person_results[i]) for i, st in alive}
        if len(alive) == 2:
            (i1, s1), (i2, s2) = alive
            best = optimize_pension_split(
                self.calc, self.oas, inputs[i1], inputs[i2],
                s1._tax_situation["oas"], s2._tax_situation["oas"],
                s1._tax_situation["pension_eligible"],
                s2._tax_situation["pension_eligible"], steps=10, price_factor=pf)
            transfer = best["transfer_1_to_2"] - best["transfer_2_to_1"]
            if abs(transfer) > self.TOLERANCE:
                giver, taker = (i1, i2) if transfer > 0 else (i2, i1)
                self._note(f"Fractionnement de pension: {self._money(abs(transfer))} de "
                           f"{self._who(giver)} attribués à {self._who(taker)} "
                           f"(impôt du couple minimisé à {self._money(best['total'])}).")
            for i, tax_key, cb_key, tr in (
                    (i1, "tax1", "clawback1", -transfer),
                    (i2, "tax2", "clawback2", transfer)):
                pr = person_results[i]
                result = best[f"result{1 if i == i1 else 2}"]
                pr.tax_total = best[tax_key]
                pr.oas_clawback = best[cb_key]
                pr.pension_split_received = tr
                pr.taxable_income = result.taxable_income
                pr.refundable_credits = result.refundable_credits
                pr.marginal_rate = self._marginal_rate(
                    best[f"input{1 if i == i1 else 2}"], result.total_tax, pf)
                pr.tax_input = best[f"input{1 if i == i1 else 2}"]
                pr.tax_result = result
                pr.price_factor = pf
                pr.net_cash = (self.states[i]._tax_situation["cash"]
                               - pr.tax_total - pr.oas_clawback + pr.refundable_credits)
        else:
            for i, st in alive:
                r = self.calc.compute(inputs[i], price_factor=pf)
                pr = person_results[i]
                pr.tax_total = r.total_tax
                pr.taxable_income = r.taxable_income
                pr.marginal_rate = r.marginal_rate
                pr.oas_clawback = self.oas.clawback(
                    r.net_income, st._tax_situation["oas"], pf)
                pr.refundable_credits = r.refundable_credits
                pr.tax_input = inputs[i]
                pr.tax_result = r
                pr.price_factor = pf
                pr.net_cash = (st._tax_situation["cash"]
                               - pr.tax_total - pr.oas_clawback + pr.refundable_credits)
