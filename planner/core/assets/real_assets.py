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

ASSET_KINDS = ("maison", "chalet", "terrain", "vehicule", "autre")


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


@dataclass
class RealAsset:
    """État runtime d'un actif réel."""
    cfg: RealAssetConfig
    value: float = field(init=False)
    cost_base: float = field(init=False)
    sold: bool = False

    def __post_init__(self):
        self.value = self.cfg.value
        self.cost_base = (self.cfg.cost_base
                          if self.cfg.cost_base is not None else self.cfg.value)

    def appreciate(self) -> None:
        if not self.sold:
            self.value *= (1 + self.cfg.appreciation)

    @property
    def unrealized_gain(self) -> float:
        if self.sold or self.cfg.is_principal_residence:
            return 0.0
        return max(0.0, self.value - self.cost_base)

    def sell(self) -> dict:
        """Vend l'actif. Retourne {"proceeds", "taxable_gain"}."""
        if self.sold:
            return {"proceeds": 0.0, "taxable_gain": 0.0}
        proceeds = self.value
        gain = 0.0 if self.cfg.is_principal_residence else max(
            0.0, self.value - self.cost_base)
        self.sold = True
        self.value = 0.0
        return {"proceeds": proceeds, "taxable_gain": gain}


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
