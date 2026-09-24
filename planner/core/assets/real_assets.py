"""Actifs réels du ménage — maison, chalet, terrains, véhicules, etc.

Règles:
- Appréciation annuelle configurable par actif.
- Vente planifiée à une année donnée: le produit rembourse la dette liée,
  le reste est versé au compte non-enregistré.
- Résidence principale: gain en capital EXONÉRÉ à la vente et au décès.
- Autres actifs (chalet, terrain...): gain imposable (inclusion 50%) à la
  vente et gain latent imposé au décès (succession).
- Plan de remplacement de véhicule: dépense nette récurrente aux X années.
"""
from dataclasses import dataclass, field

ASSET_KINDS = ("maison", "chalet", "terrain", "immeuble_locatif", "vehicule", "autre")


@dataclass
class RealAssetConfig:
    name: str
    value: float
    kind: str = "maison"
    appreciation: float = 0.02
    is_principal_residence: bool = False
    cost_base: float | None = None     # défaut: valeur initiale
    sale_year: int | None = None       # vente planifiée
    linked_debt: str | None = None     # dette remboursée à la vente
    # Immeuble locatif: loyers nets (avant DPA) en dollars d'aujourd'hui, indexés
    net_rental_income: float = 0.0
    cca_rate: float = 0.0              # DPA (cat. 1 = 4 %); 0 = sans DPA
    ucc: float | None = None           # FNACC initiale (défaut: coût)


@dataclass
class RealAsset:
    """État runtime d'un actif réel."""
    cfg: RealAssetConfig
    value: float = field(init=False)
    cost_base: float = field(init=False)
    ucc: float = field(init=False)
    sold: bool = False

    def __post_init__(self):
        self.value = self.cfg.value
        self.cost_base = (self.cfg.cost_base
                          if self.cfg.cost_base is not None else self.cfg.value)
        self.ucc = self.cfg.ucc if self.cfg.ucc is not None else self.cost_base

    def appreciate(self) -> None:
        if not self.sold:
            self.value *= (1 + self.cfg.appreciation)

    @property
    def is_rental(self) -> bool:
        return self.cfg.net_rental_income > 0 and not self.sold

    def annual_rental(self, price_factor: float) -> dict:
        """Loyers nets de l'année: {"cash", "taxable", "cca"}.

        La DPA ne peut pas créer de perte locative; elle réduit la FNACC.
        """
        if not self.is_rental:
            return {"cash": 0.0, "taxable": 0.0, "cca": 0.0}
        cash = self.cfg.net_rental_income * price_factor
        cca = min(self.ucc * self.cfg.cca_rate, cash) if self.cfg.cca_rate > 0 else 0.0
        self.ucc -= cca
        return {"cash": cash, "taxable": cash - cca, "cca": cca}

    @property
    def unrealized_gain(self) -> float:
        if self.sold or self.cfg.is_principal_residence:
            return 0.0
        return max(0.0, self.value - self.cost_base)

    @property
    def unrealized_recapture(self) -> float:
        """Récupération de DPA latente (imposable à 100 %)."""
        if self.sold or self.cfg.cca_rate <= 0:
            return 0.0
        return max(0.0, min(self.value, self.cost_base) - self.ucc)

    def sell(self) -> dict:
        """Vend l'actif. Retourne {"proceeds", "taxable_gain", "recapture"}."""
        if self.sold:
            return {"proceeds": 0.0, "taxable_gain": 0.0, "recapture": 0.0}
        proceeds = self.value
        gain = 0.0 if self.cfg.is_principal_residence else max(
            0.0, self.value - self.cost_base)
        recapture = self.unrealized_recapture
        self.sold = True
        self.value = 0.0
        self.ucc = 0.0
        return {"proceeds": proceeds, "taxable_gain": gain, "recapture": recapture}


@dataclass
class VehicleReplacementConfig:
    """Remplacement de véhicule récurrent.

    `net_cost`: coût net d'échange en dollars d'aujourd'hui (prix du neuf
    moins valeur de reprise de l'ancien).
    """
    name: str = "Auto"
    first_year: int = 2030
    every_years: int = 8
    net_cost: float = 30000.0
    last_year: int | None = None  # défaut: jusqu'à la fin de la simulation

    def cost_in_year(self, year: int) -> bool:
        if year < self.first_year:
            return False
        if self.last_year is not None and year > self.last_year:
            return False
        return (year - self.first_year) % self.every_years == 0
