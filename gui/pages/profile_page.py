"""Page Profil — personnes, comptes, cotisations, paramètres de retraite."""
from nicegui import ui


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
        with ui.row().classes("gap-4 flex-wrap"):
            _num(p, "db_pension", "Rente annuelle ($)")
            _num(p, "db_start_age", "Âge de début")
            _num(p, "db_normal_age", "Âge normal (sans pénalité)")
            _pct(p, "db_penalty", "Pénalité/an anticipé")

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
