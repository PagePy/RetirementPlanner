"""Fractionnement de pension optimal pour un couple.

Recherche le transfert (jusqu'à 50% du revenu de pension admissible d'un
conjoint vers l'autre) qui minimise l'impôt combiné du couple, incluant la
récupération de la SV.

Admissibilité (règles fédérales, harmonisées QC):
- Rente d'un régime PD: admissible à tout âge.
- FERR/FRV/rente REER: admissibles à partir de 65 ans.
"""
from dataclasses import replace

from planner.core.tax import TaxCalculator, TaxInput
from planner.core.benefits import OAS


def eligible_pension_for_splitting(age: int, db_pension: float,
                                   ferr_frv_withdrawals: float) -> float:
    """Revenu de pension admissible au fractionnement."""
    eligible = db_pension
    if age >= 65:
        eligible += ferr_frv_withdrawals
    return eligible


def couple_tax_with_split(calc: TaxCalculator, oas: OAS,
                          inp1: TaxInput, inp2: TaxInput,
                          oas1: float, oas2: float,
                          eligible1: float, eligible2: float,
                          transfer_1_to_2: float, transfer_2_to_1: float) -> dict:
    """Impôt total du couple (+ récupération SV) pour un transfert donné."""
    net_transfer = transfer_1_to_2 - transfer_2_to_1

    def adjusted(inp: TaxInput, delta: float, pension_delta: float) -> TaxInput:
        return replace(
            inp,
            ordinary_income=max(0.0, inp.ordinary_income + delta),
            eligible_pension_income=max(0.0, inp.eligible_pension_income + pension_delta),
        )

    a1 = adjusted(inp1, -net_transfer, -net_transfer)
    a2 = adjusted(inp2, net_transfer, net_transfer)

    # Revenu familial net pour les crédits QC des aînés
    family_income_probe = calc.compute(a1, _marginal_probe=False).net_income \
        + calc.compute(a2, _marginal_probe=False).net_income
    a1 = replace(a1, family_net_income=family_income_probe)
    a2 = replace(a2, family_net_income=family_income_probe)

    r1 = calc.compute(a1, _marginal_probe=False)
    r2 = calc.compute(a2, _marginal_probe=False)
    cb1 = oas.clawback(r1.net_income, oas1)
    cb2 = oas.clawback(r2.net_income, oas2)
    return {
        "tax1": r1.total_tax, "tax2": r2.total_tax,
        "clawback1": cb1, "clawback2": cb2,
        "net_income1": r1.net_income, "net_income2": r2.net_income,
        "total": r1.total_tax + r2.total_tax + cb1 + cb2,
        "result1": r1, "result2": r2,
    }


def optimize_pension_split(calc: TaxCalculator, oas: OAS,
                           inp1: TaxInput, inp2: TaxInput,
                           oas1: float, oas2: float,
                           eligible1: float, eligible2: float,
                           steps: int = 10) -> dict:
    """Cherche le fractionnement minimisant l'impôt total du couple.

    Explore les transferts de 0 à 50% du revenu admissible dans chaque
    direction. Retourne le meilleur résultat avec les transferts choisis.
    """
    best = None
    for direction in (1, 2):
        eligible = eligible1 if direction == 1 else eligible2
        for i in range(steps + 1):
            fraction = 0.5 * i / steps
            t12 = eligible * fraction if direction == 1 else 0.0
            t21 = eligible * fraction if direction == 2 else 0.0
            outcome = couple_tax_with_split(
                calc, oas, inp1, inp2, oas1, oas2, eligible1, eligible2, t12, t21)
            if best is None or outcome["total"] < best["total"] - 0.01:
                best = {**outcome, "transfer_1_to_2": t12, "transfer_2_to_1": t21}
        if eligible1 == 0.0 and eligible2 == 0.0:
            break  # rien à fractionner
    return best
