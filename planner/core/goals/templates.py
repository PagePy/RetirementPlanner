"""Plans suggérés pour utilisateurs peu expérimentés.

Un questionnaire simple produit un plan pré-rempli avec des recommandations
pédagogiques expliquées. Règles inspirées des pratiques de planification
courantes au Canada (priorités de comptes selon le taux marginal, CELIAPP
pour premier achat, etc.).
"""
from dataclasses import dataclass, field


@dataclass
class ProfileAnswers:
    """Réponses au questionnaire de profil."""
    age: int
    salary: float
    couple: bool = False
    spouse_age: int | None = None
    spouse_salary: float = 0.0
    owns_home: bool = False
    wants_to_buy_home: bool = False
    has_children: bool = False
    target_retirement_age: int = 65
    employer_pension: bool = False   # régime PD ou cotisations appariées
    risk_comfort: str = "modere"     # "prudent" | "modere" | "audacieux"


@dataclass
class PlanSuggestion:
    template_name: str
    title: str
    savings_rate: float                 # % du revenu brut recommandé
    account_priority: list[str]         # ordre de priorité des cotisations
    suggested_returns: dict             # rendements suggérés selon profil de risque
    explanations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_RETURNS_BY_RISK = {
    "prudent": {"equity_heavy": 0.040, "balanced": 0.035, "safe": 0.025},
    "modere": {"equity_heavy": 0.055, "balanced": 0.045, "safe": 0.030},
    "audacieux": {"equity_heavy": 0.065, "balanced": 0.055, "safe": 0.030},
}

# Seuil au-delà duquel le REER devient prioritaire sur le CELI
# (taux marginal élevé → la déduction REER vaut plus).
_REER_PRIORITY_SALARY = 60000.0


def suggest_plan(answers: ProfileAnswers) -> PlanSuggestion:
    """Produit un plan suggéré à partir du questionnaire."""
    a = answers
    returns = _RETURNS_BY_RISK.get(a.risk_comfort, _RETURNS_BY_RISK["modere"])
    years_to_retirement = max(1, a.target_retirement_age - a.age)

    # ---------- jeune ménage visant un premier achat ----------
    if a.wants_to_buy_home and not a.owns_home:
        priority = ["CELIAPP", "CELI", "REER"]
        expl = [
            "Le CELIAPP est le meilleur véhicule pour une mise de fonds: "
            "cotisations déductibles (comme un REER) ET retrait non imposable "
            "(comme un CELI) — 8 000$/an, 40 000$ à vie par personne.",
            "En couple, chaque conjoint a son propre CELIAPP: jusqu'à 80 000$ "
            "combinés plus les rendements.",
            "Le RAP permet en plus d'emprunter jusqu'à 60 000$ de son REER "
            "sans impôt (remboursable sur 15 ans).",
            "Après l'achat, redirigez les cotisations CELIAPP vers le CELI/REER.",
        ]
        warnings = []
        if years_to_retirement < 20:
            warnings.append(
                "Un achat immobilier tardif réduit les années d'épargne retraite: "
                "visez de rembourser l'hypothèque avant la retraite.")
        return PlanSuggestion(
            template_name="jeune_menage_maison",
            title="Jeune ménage — objectif premier achat",
            savings_rate=0.18,
            account_priority=priority,
            suggested_returns=returns,
            explanations=expl, warnings=warnings)

    # ---------- pré-retraité 55+ ----------
    if a.age >= 55:
        expl = [
            "À l'approche de la retraite, maximisez les droits REER/CELI "
            "inutilisés pendant vos dernières années à taux marginal élevé.",
            "Planifiez l'ordre de décaissement AVANT la retraite: il peut "
            "changer l'impôt à vie de dizaines de milliers de dollars.",
            "Évaluez le report de la RRQ (+0,7%/mois après 65 ans) et de la SV "
            "(+0,6%/mois): souvent avantageux si votre espérance de vie est bonne.",
            "Réduisez graduellement le risque du portefeuille 5 ans avant le "
            "décaissement (risque de séquence des rendements).",
        ]
        warnings = []
        if not a.employer_pension:
            warnings.append(
                "Sans régime d'employeur, votre plan repose entièrement sur "
                "l'épargne personnelle: testez-le avec les scénarios de stress.")
        return PlanSuggestion(
            template_name="pre_retraite",
            title="Pré-retraité — consolidation et stratégie de décaissement",
            savings_rate=0.20,
            account_priority=(["REER", "CELI", "Non-enregistré"]
                              if a.salary >= _REER_PRIORITY_SALARY
                              else ["CELI", "REER", "Non-enregistré"]),
            suggested_returns=returns,
            explanations=expl, warnings=warnings)

    # ---------- retraite anticipée ----------
    if a.target_retirement_age <= 57:
        return PlanSuggestion(
            template_name="retraite_anticipee",
            title="Retraite anticipée — taux d'épargne élevé",
            savings_rate=0.35,
            account_priority=["REER", "CELI", "Non-enregistré"],
            suggested_returns=returns,
            explanations=[
                "La retraite anticipée exige typiquement 30-40% d'épargne.",
                "Le non-enregistré sert de pont avant 60 ans (RRQ) et 65 ans (SV): "
                "les gains en capital y sont imposés à seulement 50%.",
                "Attention: la RRQ prise à 60 ans est réduite de 36% à vie.",
            ],
            warnings=[
                "Un horizon de décaissement de 35+ ans amplifie les risques "
                "d'inflation et de longévité: visez une marge de sécurité.",
            ])

    # ---------- famille / mi-carrière (défaut) ----------
    priority = (["REER", "CELI", "Non-enregistré"]
                if a.salary >= _REER_PRIORITY_SALARY
                else ["CELI", "REER", "Non-enregistré"])
    expl = [
        ("Salaire élevé: le REER d'abord — la déduction vaut votre taux marginal "
         "aujourd'hui, et le retrait sera imposé à un taux plus bas à la retraite.")
        if a.salary >= _REER_PRIORITY_SALARY else
        ("Salaire modeste: le CELI d'abord — votre taux marginal actuel est bas, "
         "gardez vos droits REER pour vos années mieux payées."),
        "Règle générale: viser 10-15% du revenu brut dès que possible; "
        "chaque année de retard coûte cher en intérêts composés.",
    ]
    if a.has_children:
        expl.append(
            "Avec des enfants: le REEE offre 30% de subventions garanties au "
            "Québec (20% SCEE + 10% IQEE) — un rendement imbattable sur les "
            "premiers 2 500$/an par enfant.")
    if a.employer_pension:
        expl.append(
            "Cotisez toujours assez pour capter 100% de l'appariement de votre "
            "employeur avant tout autre compte: c'est de l'argent gratuit.")
    return PlanSuggestion(
        template_name="mi_carriere",
        title="Accumulation mi-carrière",
        savings_rate=0.15,
        account_priority=priority,
        suggested_returns=returns,
        explanations=expl)
