"""Types partagés du moteur fiscal."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaxInput:
    """Revenus d'une personne pour une année d'imposition.

    Tous les montants sont en dollars courants de l'année, AVANT majoration
    des dividendes (montants réellement reçus).
    """
    year: int
    age: int
    # Revenus pleinement imposables: emploi, intérêts, retraits REER/FERR/FRV,
    # rentes PD, RRQ, SV, revenus locatifs nets, etc.
    ordinary_income: float = 0.0
    # Portion des revenus ci-dessus admissible au crédit pour revenu de pension
    # (rente PD à tout âge; FERR/FRV/rente REER à partir de 65 ans).
    eligible_pension_income: float = 0.0
    # Gains en capital RÉALISÉS bruts (avant taux d'inclusion).
    capital_gains: float = 0.0
    # Dividendes reçus (montants versés, avant majoration).
    eligible_dividends: float = 0.0
    non_eligible_dividends: float = 0.0
    # Déductions (cotisations REER, frais financiers, pension alimentaire...).
    deductions: float = 0.0
    # Vit seule (crédit QC personne vivant seule).
    lives_alone: bool = False
    # Revenu familial net (pour la réduction des crédits QC des aînés).
    # Si None, le revenu net individuel est utilisé.
    family_net_income: float | None = None
    # Frais médicaux admissibles payés dans l'année (crédit au-delà de 3% du revenu).
    medical_expenses: float = 0.0
    # Dons de bienfaisance de l'année.
    donations: float = 0.0
    # Dépenses de maintien à domicile (crédit remboursable QC, 70 ans+).
    home_support_expenses: float = 0.0


@dataclass
class LevelTaxResult:
    """Détail d'un palier de gouvernement (fédéral ou provincial)."""
    gross_tax: float = 0.0
    non_refundable_credits: float = 0.0
    dividend_credits: float = 0.0
    abatement: float = 0.0
    refundable_credits: float = 0.0  # versés même sans impôt à payer
    net_tax: float = 0.0
    credits_detail: dict = field(default_factory=dict)


@dataclass
class TaxResult:
    """Résultat complet du calcul d'impôt d'une personne."""
    year: int
    province: str
    total_income: float = 0.0        # revenu total (dividendes majorés inclus)
    taxable_income: float = 0.0      # revenu imposable après déductions
    net_income: float = 0.0          # revenu net (base des tests de revenu)
    federal: LevelTaxResult = field(default_factory=LevelTaxResult)
    provincial: LevelTaxResult = field(default_factory=LevelTaxResult)
    total_tax: float = 0.0
    refundable_credits: float = 0.0  # somme des crédits remboursables (liquidités)
    after_tax_income: float = 0.0    # liquidités reçues - impôt total + remboursables
    average_rate: float = 0.0        # impôt / revenu imposable
    marginal_rate: float = 0.0       # sur 100$ de revenu ordinaire additionnel
