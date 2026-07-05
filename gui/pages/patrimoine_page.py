"""Page Patrimoine — actifs réels, dettes, véhicules, dépenses spéciales."""
from nicegui import ui

from planner.core.assets import DEBT_KINDS, ASSET_KINDS

DEBT_LABELS = {"hypotheque": "Hypothèque", "auto": "Prêt auto",
               "carte_credit": "Carte de crédit", "personnel": "Prêt personnel",
               "marge": "Marge de crédit", "autre": "Autre"}
ASSET_LABELS = {"maison": "Maison", "chalet": "Chalet", "terrain": "Terrain",
                "vehicule": "Véhicule", "autre": "Autre"}


def build(state: dict):
    with ui.column().classes("w-full gap-4"):

        # ==================== DETTES ====================
        @ui.refreshable
        def debts_section():
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("💳 Passifs (dettes)").classes(
                        "text-lg font-bold text-primary")
                    ui.button("Ajouter une dette", icon="add",
                              on_click=lambda: (state["debts"].append({
                                  "name": "Nouvelle dette", "kind": "autre",
                                  "balance": 0.0, "rate": 5.0,
                                  "payment": 0.0}), debts_section.refresh()))
                if not state["debts"]:
                    ui.label("Aucune dette. Ajoutez hypothèque, prêt auto, "
                             "carte de crédit, prêt personnel...").classes(
                        "text-gray-500")
                for i, d in enumerate(state["debts"]):
                    with ui.row().classes("gap-3 items-end flex-wrap"):
                        ui.input("Nom").bind_value(d, "name").classes("w-40")
                        ui.select(DEBT_LABELS, label="Type").bind_value(
                            d, "kind").classes("w-40")
                        ui.number("Solde ($)", format="%.0f").bind_value(
                            d, "balance").classes("w-32")
                        ui.number("Taux (%)", format="%.2f").bind_value(
                            d, "rate").classes("w-28")
                        ui.number("Paiement annuel ($)", format="%.0f") \
                            .bind_value(d, "payment").classes("w-36")
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda i=i: (
                                      state["debts"].pop(i),
                                      debts_section.refresh())).props("flat")

        # ==================== ACTIFS ====================
        @ui.refreshable
        def assets_section():
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("🏠 Actifs réels").classes(
                        "text-lg font-bold text-primary")
                    ui.button("Ajouter un actif", icon="add",
                              on_click=lambda: (state["assets"].append({
                                  "name": "Maison", "kind": "maison",
                                  "value": 0.0, "appreciation": 2.0,
                                  "is_principal_residence": True,
                                  "cost_base": None, "sale_year": None,
                                  "linked_debt": None}), assets_section.refresh()))
                if not state["assets"]:
                    ui.label("Aucun actif. Ajoutez maison, chalet, terrain...") \
                        .classes("text-gray-500")
                for i, a in enumerate(state["assets"]):
                    with ui.row().classes("gap-3 items-end flex-wrap"):
                        ui.input("Nom").bind_value(a, "name").classes("w-36")
                        ui.select(ASSET_LABELS, label="Type").bind_value(
                            a, "kind").classes("w-32")
                        ui.number("Valeur ($)", format="%.0f").bind_value(
                            a, "value").classes("w-32")
                        ui.number("Appréciation (%)", format="%.1f").bind_value(
                            a, "appreciation").classes("w-32")
                        ui.checkbox("Résidence principale").bind_value(
                            a, "is_principal_residence")
                        ui.number("Coût d'achat ($)", format="%.0f").bind_value(
                            a, "cost_base").classes("w-32").tooltip(
                            "Pour le gain en capital si non exonéré")
                        ui.number("Vente prévue (année)", format="%.0f") \
                            .bind_value(a, "sale_year").classes("w-36")
                        ui.select([""] + [d["name"] for d in state["debts"]],
                                  label="Dette liée").bind_value(
                            a, "linked_debt").classes("w-36").tooltip(
                            "Remboursée avec le produit de la vente")
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda i=i: (
                                      state["assets"].pop(i),
                                      assets_section.refresh())).props("flat")

        # ==================== VÉHICULES ====================
        @ui.refreshable
        def vehicles_section():
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("🚗 Remplacement de véhicules").classes(
                        "text-lg font-bold text-primary")
                    ui.button("Ajouter un plan", icon="add",
                              on_click=lambda: (state["vehicles"].append({
                                  "name": "Auto", "first_year": 2030,
                                  "every_years": 8, "net_cost": 30000.0,
                                  "last_year": None}), vehicles_section.refresh()))
                ui.label("Coût net d'échange (prix du neuf − valeur de reprise), "
                         "en dollars d'aujourd'hui, indexé automatiquement.") \
                    .classes("text-gray-500 text-sm")
                for i, v in enumerate(state["vehicles"]):
                    with ui.row().classes("gap-3 items-end flex-wrap"):
                        ui.input("Nom").bind_value(v, "name").classes("w-32")
                        ui.number("Premier achat (année)", format="%.0f") \
                            .bind_value(v, "first_year").classes("w-40")
                        ui.number("Aux X années", format="%.0f").bind_value(
                            v, "every_years").classes("w-28")
                        ui.number("Coût net ($)", format="%.0f").bind_value(
                            v, "net_cost").classes("w-32")
                        ui.number("Dernier achat (année)", format="%.0f") \
                            .bind_value(v, "last_year").classes("w-40")
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda i=i: (
                                      state["vehicles"].pop(i),
                                      vehicles_section.refresh())).props("flat")

        # ==================== DÉPENSES SPÉCIALES ====================
        @ui.refreshable
        def specials_section():
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("🎯 Dépenses spéciales (mariage, voyage, réno...)") \
                        .classes("text-lg font-bold text-primary")
                    ui.button("Ajouter", icon="add",
                              on_click=lambda: (state["special_expenses"].append({
                                  "name": "Projet", "year": 2030,
                                  "amount": 10000.0}), specials_section.refresh()))
                for i, e in enumerate(state["special_expenses"]):
                    with ui.row().classes("gap-3 items-end flex-wrap"):
                        ui.input("Nom").bind_value(e, "name").classes("w-48")
                        ui.number("Année", format="%.0f").bind_value(
                            e, "year").classes("w-28")
                        ui.number("Montant ($)", format="%.0f").bind_value(
                            e, "amount").classes("w-32")
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda i=i: (
                                      state["special_expenses"].pop(i),
                                      specials_section.refresh())).props("flat")

        debts_section()
        assets_section()
        vehicles_section()
        specials_section()
