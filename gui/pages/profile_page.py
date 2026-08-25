"""Page Profil — personnes, comptes, cotisations, paramètres de retraite."""
from nicegui import ui


DB_STATUS_LABELS = {
    "none": "Aucun régime PD",
    "active": "PD actif",
    "deferred": "PD différé ou gelé",
    "closed_salary_linked": "PD fermé, emploi toujours actif",
    "in_payment": "PD déjà en paiement",
}


def _num(container_dict: dict, key: str, label: str, **kwargs):
    return ui.number(label, format="%.0f", **kwargs).bind_value(
        container_dict, key).classes("w-40")


def _pct(container_dict: dict, key: str, label: str, **kwargs):
    return ui.number(label, format="%.2f", suffix="%", **kwargs).bind_value(
        container_dict, key).classes("w-36")


def _person_form(p: dict, title: str):
    with ui.card().classes("w-full"):
        ui.label(title).classes("text-lg font-bold text-primary")
        with ui.row().classes("gap-4 flex-wrap"):
            ui.input("Nom").bind_value(p, "name").classes("w-40")
            _num(p, "birth_year", "Année de naissance")
            _num(p, "retirement_age", "Âge de retraite")
            _num(p, "life_expectancy", "Espérance de vie")
        with ui.row().classes("gap-4 flex-wrap"):
            _num(p, "salary", "Salaire annuel ($)")
            _pct(p, "salary_growth", "Croissance salaire")

        ui.separator()
        ui.label("Prestations gouvernementales").classes("font-bold")
        with ui.row().classes("gap-4 flex-wrap"):
            _num(p, "rrq_monthly_at_65", "RRQ à 65 ans ($/mois)")
            _num(p, "rrq_start_age", "Début RRQ (60-72)")
            _num(p, "oas_start_age", "Début SV (65-70)")
            _num(p, "oas_residence_years", "Années résidence Canada")

        ui.separator()
        ui.label("Rente d'employeur (PD)").classes("font-bold")
        ui.select(DB_STATUS_LABELS, label="Statut du régime PD") \
            .bind_value(p, "db_status").classes("w-72") \
            .tooltip("Choisissez le statut qui décrit le régime aujourd'hui.")
        with ui.expansion("Comment choisir le statut de la rente PD ?", icon="help_outline") \
                .classes("w-full max-w-3xl text-sm"):
            ui.label("Aucun régime PD: la personne n'a pas de rente à prestations "
                     "déterminées à recevoir.")
            ui.label("PD actif: la personne participe toujours au régime; sa rente "
                     "continue d'augmenter grâce au service et/ou au salaire.")
            ui.label("PD différé ou gelé: la personne a quitté l'employeur ou le "
                     "régime est fermé; la rente accumulée n'augmente plus avant son "
                     "début, sauf règle d'indexation particulière du régime.")
            ui.label("PD fermé, emploi toujours actif: la personne travaille encore "
                     "pour l'employeur, mais n'accumule plus de service. La rente peut "
                     "encore augmenter si la formule utilise les meilleures années de salaire.")
            ui.label("PD déjà en paiement: la personne reçoit déjà cette rente. Entrez "
                     "le montant annuel reçu aujourd'hui; aucune pénalité anticipée n'est "
                     "appliquée.")
            ui.label("Croissance PD active sert seulement au statut PD actif. Pour le "
                     "statut fermé avec emploi actif, le logiciel utilise plutôt la "
                     "croissance du salaire.").classes("text-gray-600")
        with ui.row().classes("gap-4 flex-wrap"):
            _num(p, "db_pension", "Rente annuelle estimée ($)")
            _num(p, "db_start_age", "Âge de début")
            _num(p, "db_normal_age", "Âge normal (sans pénalité)")
            _pct(p, "db_penalty", "Pénalité/an anticipé")
            _pct(p, "db_active_growth", "Croissance PD active")
            ui.checkbox("Rente indexée une fois en paiement") \
                .bind_value(p, "db_indexed")

        a = p["accounts"]
        ui.separator()
        ui.label("Comptes — soldes et rendements").classes("font-bold")
        with ui.row().classes("gap-4 flex-wrap"):
            _num(a, "reer_balance", "REER ($)")
            _pct(a, "reer_return", "Rend. REER")
            _num(a, "reer_room", "Droits REER ($)")
            _num(a, "celi_balance", "CELI ($)")
            _pct(a, "celi_return", "Rend. CELI")
            _num(a, "celi_room", "Droits CELI ($)")
        with ui.row().classes("gap-4 flex-wrap"):
            _num(a, "celiapp_balance", "CELIAPP ($)")
            _num(a, "cri_balance", "CRI ($)")
            _num(a, "ferr_balance", "FERR ($)")
            _num(a, "frv_balance", "FRV ($)")
        with ui.row().classes("gap-4 flex-wrap"):
            _num(a, "taxable_balance", "Non-enregistré ($)")
            _num(a, "taxable_acb", "PBR non-enr. ($, vide = solde)")
            _pct(a, "taxable_return", "Rend. non-enr.")
            _pct(a, "taxable_interest_ratio", "Part intérêts")
            _pct(a, "taxable_dividend_ratio", "Part dividendes")

        c = p["contributions"]
        ui.separator()
        ui.label("Cotisations annuelles (accumulation)").classes("font-bold")
        with ui.row().classes("gap-4 flex-wrap"):
            _pct(c, "reer_pct", "REER % salaire")
            _num(c, "reer_fixed", "REER fixe ($)")
            _pct(c, "celi_pct", "CELI % salaire")
            _num(c, "celi_fixed", "CELI fixe ($)")
            _num(c, "celiapp_fixed", "CELIAPP fixe ($)")
            _num(c, "taxable_fixed", "Non-enr. fixe ($)")
        with ui.row().classes("gap-4 flex-wrap"):
            _pct(c, "taxable_pct", "Non-enr. % salaire")

        ui.separator()
        ui.label("Régime CD (alimente le CRI unique)").classes("font-bold")
        ui.label("Les cotisations en % sont recalculées chaque année sur le "
                 "salaire annuel courant.") \
            .classes("text-sm text-gray-500")
        with ui.row().classes("gap-4 flex-wrap"):
            _pct(c, "dc_employee_pct", "CD employé % salaire")
            _num(c, "dc_employee_fixed", "CD employé fixe annuel ($)")
            _pct(c, "dc_employer_pct", "CD employeur % salaire")
            _num(c, "dc_employer_fixed", "CD employeur fixe annuel ($)")


def build(state: dict):
    with ui.column().classes("w-full gap-4"):
        with ui.card().classes("w-full"):
            ui.label("Ménage et objectif").classes("text-lg font-bold text-primary")
            with ui.row().classes("gap-6 items-center flex-wrap"):
                ui.switch("Couple").bind_value(state, "is_couple")
                ui.select(["QC"], label="Province").bind_value(
                    state, "province").classes("w-28")
                ui.number("Revenu net cible du ménage ($/an)", format="%.0f") \
                    .bind_value(state, "target_net_income").classes("w-56")
                ui.switch("Cible indexée à l'inflation").bind_value(
                    state, "target_indexed")
            with ui.row().classes("gap-6 items-center flex-wrap"):
                ui.select({"dernier": "CELI en dernier recours",
                           "jamais": "CELI jamais (succession)"},
                          label="Stratégie CELI").bind_value(
                    state, "celi_strategy").classes("w-64")
                ui.number("Inflation (%)", format="%.1f").bind_value(
                    state, "inflation").classes("w-32")
                ui.number("Année de départ", format="%.0f").bind_value(
                    state, "start_year").classes("w-32")
                ui.switch("Minimum FERR sur l'âge du conjoint").bind_value(
                    state, "use_spouse_age_for_ferr")

        _person_form(state["persons"][0], "Personne 1")
        with ui.column().classes("w-full").bind_visibility_from(state, "is_couple"):
            _person_form(state["persons"][1], "Personne 2")
