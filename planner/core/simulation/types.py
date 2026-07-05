"""Configurations et résultats de la simulation ménage."""
from dataclasses import dataclass, field


@dataclass
class AccountsConfig:
    """Soldes initiaux et rendements d'une personne."""
    reer_balance: float = 0.0
    reer_room: float = 0.0
    celi_balance: float = 0.0
    celi_room: float = 0.0
    celiapp_balance: float = 0.0
    cri_balance: float = 0.0
    ferr_balance: float = 0.0
    frv_balance: float = 0.0
    taxable_balance: float = 0.0
    taxable_acb: float | None = None  # défaut: égal au solde
    # Rendements annuels (décimaux)
    reer_return: float = 0.05
    celi_return: float = 0.05
    celiapp_return: float = 0.04
    cri_return: float = 0.05
    ferr_return: float = 0.04
    frv_return: float = 0.04
    taxable_return: float = 0.04
    # Répartition du rendement non-enregistré
    taxable_interest_ratio: float = 0.3
    taxable_dividend_ratio: float = 0.3
    taxable_growth_ratio: float = 0.4


@dataclass
class ContributionsConfig:
    """Cotisations annuelles pendant l'accumulation."""
    reer_pct: float = 0.0        # % du salaire
    reer_fixed: float = 0.0
    celi_pct: float = 0.0
    celi_fixed: float = 0.0
    celiapp_fixed: float = 0.0
    taxable_pct: float = 0.0
    taxable_fixed: float = 0.0


@dataclass
class PersonConfig:
    name: str
    birth_year: int
    retirement_age: int = 65
    life_expectancy: int = 95
    salary: float = 0.0
    salary_growth: float = 0.02
    # Rente à prestations déterminées
    db_pension: float = 0.0            # rente annuelle à l'âge normal
    db_start_age: int = 65
    db_normal_age: int = 65
    db_penalty_per_year: float = 0.06  # réduction par année d'anticipation
    db_indexed: bool = True
    # Prestations gouvernementales
    rrq_monthly_at_65: float = 0.0
    rrq_start_age: int = 65
    oas_start_age: int = 65
    oas_residence_years: int = 40
    accounts: AccountsConfig = field(default_factory=AccountsConfig)
    contributions: ContributionsConfig = field(default_factory=ContributionsConfig)


@dataclass
class HouseholdConfig:
    persons: list[PersonConfig] = field(default_factory=list)
    province: str = "QC"
    # Cible de revenu net ANNUEL du ménage (dollars d'aujourd'hui)
    target_net_income: float = 60000.0
    target_indexed: bool = True
    # Stratégie CELI: "dernier" | "jamais"
    celi_strategy: str = "dernier"
    # Ordre de retrait des sources (au-delà des minimums obligatoires)
    withdrawal_order: list[str] = field(
        default_factory=lambda: ["taxable", "reer", "ferr", "frv", "celi"])
    # Dépenses spéciales nettes {année: montant}
    special_expenses: dict[int, float] = field(default_factory=dict)
    # Décès prématuré: {"person_index": int, "year": int}
    premature_death: dict | None = None
    use_spouse_age_for_ferr: bool = False

    @property
    def is_couple(self) -> bool:
        return len(self.persons) == 2


@dataclass
class ScenarioConfig:
    start_year: int = 2026
    inflation: float = 0.02
    end_year: int | None = None  # défaut: fin de la plus longue espérance de vie
    # Choc de rendement par année: delta ADDITIF appliqué à tous les comptes
    # (ex: {2030: -0.30} = krach de -30 points en 2030). Utilisé par les
    # tests de stress et le Monte Carlo.
    return_delta_by_year: dict[int, float] = field(default_factory=dict)


@dataclass
class PersonYearResult:
    year: int
    age: int
    alive: bool = True
    retired: bool = False
    # Revenus bruts
    salary: float = 0.0
    db_pension: float = 0.0
    rrq: float = 0.0
    oas: float = 0.0
    gis: float = 0.0  # non imposable
    # Retraits
    wd_taxable: float = 0.0
    wd_taxable_gain: float = 0.0
    wd_reer: float = 0.0
    wd_ferr: float = 0.0
    wd_frv: float = 0.0
    wd_celi: float = 0.0
    ferr_min: float = 0.0
    frv_min: float = 0.0
    # Cotisations
    contrib_reer: float = 0.0
    contrib_celi: float = 0.0
    contrib_celiapp: float = 0.0
    contrib_taxable: float = 0.0
    # Revenus de placement non-enregistrés
    investment_interest: float = 0.0
    investment_dividends: float = 0.0
    # Fiscalité
    taxable_income: float = 0.0
    pension_split_received: float = 0.0  # >0 reçu, <0 cédé
    tax_total: float = 0.0
    oas_clawback: float = 0.0
    marginal_rate: float = 0.0
    # Flux
    net_cash: float = 0.0
    # Soldes de fin d'année
    bal_reer: float = 0.0
    bal_celi: float = 0.0
    bal_celiapp: float = 0.0
    bal_cri: float = 0.0
    bal_ferr: float = 0.0
    bal_frv: float = 0.0
    bal_taxable: float = 0.0
    taxable_unrealized_gain: float = 0.0

    @property
    def wealth(self) -> float:
        return (self.bal_reer + self.bal_celi + self.bal_celiapp + self.bal_cri
                + self.bal_ferr + self.bal_frv + self.bal_taxable)


@dataclass
class HouseholdYearResult:
    year: int
    target_net: float = 0.0
    special_expenses: float = 0.0
    net_cash: float = 0.0
    target_gap: float = 0.0
    total_tax: float = 0.0
    total_wealth: float = 0.0
    persons: list[PersonYearResult] = field(default_factory=list)
