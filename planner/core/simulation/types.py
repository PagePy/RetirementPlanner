"""Configurations et résultats de la simulation ménage."""
from dataclasses import dataclass, field

from planner.core.assets import DebtConfig, RealAssetConfig, VehicleReplacementConfig


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
    # Frais de gestion annuels (RFG/honoraires) soustraits des rendements ci-dessus
    fee_rate: float = 0.0
    # Ajustement des rendements une fois à la retraite (ex. -0.01 = portefeuille plus prudent)
    retirement_return_delta: float = 0.0

    def net_return(self, gross: float, retired: bool) -> float:
        """Rendement effectif après frais et ajustement de phase."""
        return gross - self.fee_rate + (self.retirement_return_delta if retired else 0.0)


@dataclass
class ContributionsConfig:
    """Cotisations annuelles pendant l'accumulation."""
    reer_pct: float = 0.0        # % du salaire
    reer_fixed: float = 0.0
    celi_pct: float = 0.0
    celi_fixed: float = 0.0
    celi_fixed_indexed: bool = False    # montant fixe CELI indexé à l'inflation
    celi_overflow_to_taxable: bool = True  # excédent sur les droits -> non-enregistré
    celiapp_fixed: float = 0.0
    taxable_pct: float = 0.0
    taxable_fixed: float = 0.0
    # REER de conjoint: cotisé par cette personne (déduction et droits à elle),
    # déposé dans le REER du conjoint.
    spousal_reer_pct: float = 0.0
    spousal_reer_fixed: float = 0.0
    # Régime CD vers CRI unique
    dc_employee_pct: float = 0.0
    dc_employee_fixed: float = 0.0
    dc_employer_pct: float = 0.0
    dc_employer_fixed: float = 0.0


@dataclass
class PersonConfig:
    name: str
    birth_year: int
    birth_month: int = 0               # 0 = inconnu: retraite selon retirement_month, prestations dès janvier
    retirement_age: int = 65
    retirement_month: int = 0          # mois du départ (7 = travaille janv.–juin); 0 = auto: mois suivant l'anniversaire, sinon 1er janvier
    life_expectancy: int = 95
    sex: str = "F"                     # M | F (tables de longévité)
    salary: float = 0.0
    salary_growth: float = 0.02
    # Emploi à temps partiel après la retraite (dollars d'aujourd'hui, indexé)
    part_time_income: float = 0.0
    part_time_until_age: int = 0
    # Dépenses donnant droit à des crédits (dollars d'aujourd'hui, indexés)
    medical_expenses: float = 0.0
    donations: float = 0.0
    home_support_expenses: float = 0.0  # maintien à domicile (QC, 70+)
    # Rente à prestations déterminées
    db_status: str = "active"         # none | active | deferred | closed_salary_linked | in_payment
    db_pension: float = 0.0            # rente annuelle estimée, en dollars courants
    db_start_age: int = 65
    db_normal_age: int = 65
    db_penalty_per_year: float = 0.06  # réduction par année d'anticipation
    db_indexed: bool = True
    db_active_growth: float = 0.02     # croissance annuelle: service et salaire
    # Relevé annuel du régime PD actif (au 31 déc. précédant l'année de départ);
    # vide = repli sur db_pension × croissance
    db_service_years: float = 0.0
    db_avg_salary: float = 0.0
    db_accrual_rate: float = 0.02
    db_avg_years: int = 3
    db_max_service: float = 35.0       # 0 = aucun plafond
    db_coordination: str = "none"      # none | step (taux réduit sous le MGA) | bridge (réduction à 65 ans)
    db_rate_below_mga: float = 0.015
    db_bridge_rate: float = 0.007
    # Prestations gouvernementales
    rrq_monthly_at_65: float = 0.0
    rrq_start_age: int = 65
    oas_start_age: int = 65
    oas_residence_years: int = 40
    accounts: AccountsConfig = field(default_factory=AccountsConfig)
    contributions: ContributionsConfig = field(default_factory=ContributionsConfig)

    @property
    def db_from_statement(self) -> bool:
        """Rente PD active calculée à partir du relevé (service × taux × salaire moyen)."""
        return (self.db_status == "active" and self.db_service_years > 0
                and self.db_avg_salary > 0)


@dataclass
class AnnuityConfig:
    """Rente viagère achetée à une année donnée avec des fonds d'un compte.

    - source "reer"/"ferr": rente enregistrée, versements 100 % imposables
      (admissibles au crédit pension/fractionnement à 65 ans+);
    - source "taxable": rente prescrite, seule la portion intérêt est imposable;
    - source "celi": versements non imposables.
    """
    person_index: int = 0
    purchase_year: int = 2030
    premium: float = 100000.0          # capital versé (dollars de l'année d'achat)
    annual_payment: float = 6500.0     # versement annuel (dollars de l'année d'achat)
    source: str = "reer"
    indexed: bool = False
    taxable_fraction: float | None = None  # défaut selon la source
    name: str = "Rente viagère"

    def default_taxable_fraction(self) -> float:
        if self.taxable_fraction is not None:
            return self.taxable_fraction
        return {"reer": 1.0, "ferr": 1.0, "celi": 0.0}.get(self.source, 0.35)


@dataclass
class LifeInsuranceConfig:
    """Police d'assurance vie: prime annuelle fixe, capital-décès libre d'impôt."""
    person_index: int = 0
    face_amount: float = 250000.0
    annual_premium: float = 2000.0
    premium_until_age: int = 100       # primes payées jusqu'à cet âge inclus
    coverage_until_age: int = 120      # ex. 85 pour une temporaire
    name: str = "Assurance vie"


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
    # Passifs du ménage (hypothèque, auto, cartes, prêts...)
    debts: list[DebtConfig] = field(default_factory=list)
    # Actifs réels (maison, chalet...) avec vente planifiée optionnelle
    real_assets: list[RealAssetConfig] = field(default_factory=list)
    # Plans de remplacement de véhicules (aux X années)
    vehicle_plans: list[VehicleReplacementConfig] = field(default_factory=list)
    # Décès prématuré: {"person_index": int, "year": int}
    premature_death: dict | None = None
    use_spouse_age_for_ferr: bool = False
    # Partage de la rente RRQ entre conjoints (les deux 60+); fraction = part
    # des rentes acquise pendant la vie commune.
    rrq_sharing: bool = False
    rrq_share_fraction: float = 1.0
    # Fonte du REER: chaque année de retraite, retirer du REER/FERR jusqu'à ce
    # plancher de revenu imposable par personne (dollars d'aujourd'hui, indexé);
    # l'excédent est réinvesti (CELI puis non-enregistré).
    taxable_income_floor: float | None = None
    annuities: list[AnnuityConfig] = field(default_factory=list)
    life_insurances: list[LifeInsuranceConfig] = field(default_factory=list)

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
    part_time_income: float = 0.0
    db_pension: float = 0.0
    rrq: float = 0.0
    rrq_shared_delta: float = 0.0  # effet du partage RRQ (>0 reçu, <0 cédé)
    oas: float = 0.0
    gis: float = 0.0  # non imposable
    refundable_credits: float = 0.0  # ex. maintien à domicile QC
    fees_paid: float = 0.0
    rental_income: float = 0.0       # loyers nets encaissés (part de la personne)
    annuity_income: float = 0.0      # versements de rentes viagères
    meltdown_withdrawal: float = 0.0 # retrait REER/FERR volontaire (plancher de revenu)
    insurance_premium: float = 0.0
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
    contrib_spousal_reer: float = 0.0  # versé dans le REER du conjoint
    contrib_celi: float = 0.0
    contrib_celiapp: float = 0.0
    contrib_taxable: float = 0.0
    contrib_dc_employee: float = 0.0
    contrib_dc_employer: float = 0.0
    # Revenus de placement non-enregistrés
    investment_interest: float = 0.0
    investment_dividends: float = 0.0
    # Fiscalité
    taxable_income: float = 0.0
    pension_split_received: float = 0.0  # >0 reçu, <0 cédé
    spousal_attributed: float = 0.0      # retrait REER conjoint réattribué (>0 ajouté ici)
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
    # Actifs réels et passifs
    debt_service: float = 0.0        # paiements de dettes de l'année
    debt_interest: float = 0.0
    debts_balance: float = 0.0       # solde total des dettes (fin d'année)
    real_assets_value: float = 0.0   # valeur des actifs réels (fin d'année)
    real_assets_gain: float = 0.0    # gain latent imposable (non exonéré)
    real_assets_recapture: float = 0.0  # récupération de DPA latente
    vehicle_expenses: float = 0.0    # remplacements de véhicules de l'année
    asset_sale_proceeds: float = 0.0 # produits de ventes d'actifs de l'année
    reinvested: float = 0.0          # surplus de retraite réinvesti (CELI puis non-enr.)
    shortfall_note: str = ""         # pourquoi la cible n'est pas atteinte (vide sinon)
    total_fees: float = 0.0          # frais de gestion payés dans l'année
    rental_income: float = 0.0       # loyers nets du ménage
    insurance_premiums: float = 0.0  # primes d'assurance vie de l'année
    insurance_in_force: float = 0.0  # capitaux-décès en vigueur (fin d'année)
    insurance_payout: float = 0.0    # capital-décès versé au survivant cette année
    persons: list[PersonYearResult] = field(default_factory=list)

    @property
    def net_worth(self) -> float:
        """Valeur nette du ménage: financier + actifs réels − dettes."""
        return self.total_wealth + self.real_assets_value - self.debts_balance
