# services/decumulation_household.py
from copy import deepcopy
from services.tax_recalc import recompute_net_income

def withdraw_to_meet_household_target(target_net_income: float,
                                      income_primary: dict,
                                      income_spouse: dict,
                                      accounts_primary: dict,
                                      accounts_spouse: dict,
                                      fiscal,
                                      max_iterations: int = 30,
                                      step_fraction: float = 0.5):
    """
    Cherche à atteindre target_net_income pour le ménage.
    Ordre de retraits: Taxable -> FERR -> FRV -> REER -> CELI pour chaque personne.
    On alterne entre primaire et conjoint pour équilibrer le fardeau fiscal.
    Retourne dict des retraits optionnels par personne.
    """
    opt_p = {"Taxable": 0.0, "FERR": 0.0, "FRV": 0.0, "REER": 0.0, "CELI": 0.0}
    opt_s = {"Taxable": 0.0, "FERR": 0.0, "FRV": 0.0, "REER": 0.0, "CELI": 0.0}

    # Calcul initial du net ménage
    tax_p, net_p = recompute_net_income(deepcopy(income_primary), fiscal)
    tax_s, net_s = recompute_net_income(deepcopy(income_spouse), fiscal)
    net_household = net_p + net_s

    # Boucle adaptative
    for _ in range(max_iterations):
        gap = max(0.0, target_net_income - net_household)
        if gap <= 1.0:
            break
        attempt = gap * step_fraction

        # Fonction de retrait ordonné
        def withdraw_order(accounts, amount):
            order = ("Taxable", "FERR", "FRV", "REER", "CELI")
            withdrawn = 0.0
            for key in order:
                if key in accounts and accounts[key].balance > 0 and withdrawn < amount:
                    amt = min(accounts[key].balance, amount - withdrawn)
                    accounts[key].withdraw(amt)
                    withdrawn += amt
            return withdrawn

        # Alterner: primaire puis conjoint
        withdrawn_p = withdraw_order(accounts_primary, attempt * 0.5)
        # Mise à jour des revenus imposables: on traite les retraits selon leur nature
        income_primary["pension"] += (0.0  # placeholder, ajusté ci-dessous
                                     )
        # On répartit le retrait par type pour les impacts fiscaux:
        # Hypothèse: pour "Taxable", on suppose composition moyenne (40% intérêt, 30% dividendes admissibles, 30% gains)
        # Pour FERR/FRV/REER: entièrement imposable en "pension".
        # Pour CELI: non imposable.
        # Pour simplicité, on applique proportionnellement à chaque palier consommé:
        # Ici, on approximera: si "Taxable" a été retiré, on augmente interest/dividends/capital_gains.

        # Recalcul rapide des composantes (approx) en supposant l'ordre a été respecté:
        # Distribuer withdrawn_p sur types selon disponibilité des comptes
        def distribute_effect(income_dict, accounts_dict, withdrawn_amount):
            # Effet Taxable
            taxable_taken = min(withdrawn_amount, accounts_dict.get("Taxable", None).balance + withdrawn_amount if "Taxable" in accounts_dict else 0.0)
            if taxable_taken > 0.0:
                income_dict["interest"] += taxable_taken * 0.40
                income_dict["eligible_dividends"] += taxable_taken * 0.30
                income_dict["capital_gains"] += taxable_taken * 0.30
            # Effet FERR/FRV/REER (imposable en pension)
            reg_taken = 0.0
            for key in ("FERR", "FRV", "REER"):
                if key in accounts_dict:
                    # impossible de savoir la fraction exacte prise, on approxime par partage équitable
                    reg_taken += 0.0
            # Simplification: si Taxable < withdrawn_amount, le reste est "pension"
            reg_part = max(0.0, withdrawn_amount - taxable_taken)
            income_dict["pension"] += reg_part
            # Effet CELI: non imposable
            # Note: si CELI a été utilisé, c'est déjà compris dans withdrawn_amount; aucune incidence fiscale.

        distribute_effect(income_primary, accounts_primary, withdrawn_p)
        opt_p["Taxable"] += withdrawn_p  # on cumule dans Taxable; la part regs est incluse plus bas
        # Recalcule net personne primaire
        tax_p, net_p = recompute_net_income(deepcopy(income_primary), fiscal)

        withdrawn_s = withdraw_order(accounts_spouse, attempt * 0.5)
        distribute_effect(income_spouse, accounts_spouse, withdrawn_s)
        opt_s["Taxable"] += withdrawn_s
        tax_s, net_s = recompute_net_income(deepcopy(income_spouse), fiscal)

        net_household = net_p + net_s

    return opt_p, opt_s, net_household