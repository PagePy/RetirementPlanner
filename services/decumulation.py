# services/decumulation.py
def withdraw_to_meet_net_target(target_net_income: float,
                                current_net_before_optional: float,
                                accounts: dict,
                                taxes_fn,
                                fiscal,
                                income_context: dict,
                                max_iterations: int = 20):
    """
    Essaie d'atteindre target_net_income en retirant selon l'ordre:
    Taxable -> FERR/FRV (au-delà du minimum) -> REER -> CELI.
    On boucle et recalcule les impôts pour ajuster les retraits.
    income_context: dict des composantes déjà connues (employment, benefits, etc.).
    taxes_fn: fonction compute_taxes_person_qc(...)
    Retourne dict des retraits additionnels effectués.
    """
    additional_withdrawals = {"Taxable": 0.0, "FERR": 0.0, "FRV": 0.0, "REER": 0.0, "CELI": 0.0}
    gap = max(0.0, target_net_income - current_net_before_optional)

    # Helper pour recalculer net après un certain retrait brut taxable
    def recalc_net(extra_taxable: float = 0.0, extra_pension: float = 0.0, extra_reer: float = 0.0, extra_celi: float = 0.0):
        inc = income_context.copy()
        inc["interest"] += extra_taxable * 0.4
        inc["eligible_dividends"] += extra_taxable * 0.3
        inc["capital_gains"] += extra_taxable * 0.3
        inc["pension"] += extra_pension + extra_reer  # REER retrait imposable
        # CELI n'affecte pas l'impôt
        tax_res = taxes_fn(inc, fiscal, pension_income_for_credit=inc["pension"], oas_clawback=0.0)
        net = (
            inc.get("employment", 0.0) + inc.get("pension", 0.0) + inc.get("rrq", 0.0) + inc.get("oas", 0.0)
            + inc.get("interest", 0.0) + inc.get("eligible_dividends", 0.0) + 0.5 * inc.get("capital_gains", 0.0)
            - tax_res.net_tax
            + 0.0  # SRG ignoré ici; peut être recalculé ailleurs
        )
        return net

    # Itérations adaptatives
    for _ in range(max_iterations):
        if gap <= 1.0:  # tolérance
            break

        # Fraction du gap à tenter par palier
        attempt = gap * 0.5

        # 1) Taxable
        if "Taxable" in accounts and accounts["Taxable"].balance > 0:
            withdraw_taxable = min(accounts["Taxable"].balance, attempt)
            accounts["Taxable"].withdraw(withdraw_taxable)
            additional_withdrawals["Taxable"] += withdraw_taxable
            new_net = recalc_net(extra_taxable=withdraw_taxable)
            gap = max(0.0, target_net_income - new_net)
            if gap <= 1.0:
                break

        # 2) FERR/FRV au-delà du minimum
        for key in ("FERR", "FRV"):
            if key in accounts and accounts[key].balance > 0:
                withdraw_reg = min(accounts[key].balance, attempt)
                accounts[key].withdraw(withdraw_reg)
                additional_withdrawals[key] += withdraw_reg
                new_net = recalc_net(extra_pension=withdraw_reg)
                gap = max(0.0, target_net_income - new_net)
                if gap <= 1.0:
                    break
        if gap <= 1.0:
            break

        # 3) REER (avant conversion)
        if "REER" in accounts and accounts["REER"].balance > 0:
            withdraw_reer = min(accounts["REER"].balance, attempt)
            accounts["REER"].withdraw(withdraw_reer)
            additional_withdrawals["REER"] += withdraw_reer
            new_net = recalc_net(extra_reer=withdraw_reer)
            gap = max(0.0, target_net_income - new_net)
            if gap <= 1.0:
                break

        # 4) CELI (non imposable)
        if "CELI" in accounts and accounts["CELI"].balance > 0:
            withdraw_celi = min(accounts["CELI"].balance, attempt)
            accounts["CELI"].withdraw(withdraw_celi)
            additional_withdrawals["CELI"] += withdraw_celi
            # CELI n'affecte pas l'impôt; net augmente du montant
            gap = max(0.0, gap - withdraw_celi)

    return additional_withdrawals