"""Page Patrimoine — actifs réels, dettes, véhicules, dépenses spéciales."""
from nicegui import ui

from planner.core.assets import DEBT_KINDS, ASSET_KINDS

DEBT_LABELS = {"hypotheque": "Hypothèque", "auto": "Prêt auto",
               "carte_credit": "Carte de crédit", "personnel": "Prêt personnel",
               "marge": "Marge de crédit", "autre": "Autre"}
ASSET_LABELS = {"maison": "Maison", "chalet": "Chalet", "terrain": "Terrain",
                "immeuble_locatif": "Immeuble locatif",
                "vehicule": "Véhicule", "autre": "Autre"}
ANNUITY_SOURCES = {"reer": "REER (rente enregistrée)", "ferr": "FERR",
                   "taxable": "Non-enregistré (rente prescrite)", "celi": "CELI"}
# Taux de rente viagère indicatifs (versement annuel / capital) selon l'âge d'achat
ANNUITY_RATE_BY_AGE = {60: 0.055, 65: 0.063, 70: 0.073, 75: 0.088, 80: 0.105}


def _persons_options(state: dict) -> dict:
    n = 2 if state.get("is_couple") else 1
    return {i: (state["persons"][i]["name"] or f"Personne {i + 1}") for i in range(n)}


def _annuity_rate(age: int) -> float:
    ages = sorted(ANNUITY_RATE_BY_AGE)
    if age <= ages[0]:
        return ANNUITY_RATE_BY_AGE[ages[0]]
    if age >= ages[-1]:
        return ANNUITY_RATE_BY_AGE[ages[-1]]
    for a, b in zip(ages, ages[1:]):
        if a <= age <= b:
            t = (age - a) / (b - a)
            return ANNUITY_RATE_BY_AGE[a] + t * (ANNUITY_RATE_BY_AGE[b] - ANNUITY_RATE_BY_AGE[a])
    return 0.06


def _remove(items: list, item: dict) -> None:
    """Retire par identité (pas par index): insensible aux rafraîchissements."""
    items[:] = [x for x in items if x is not item]


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
                for d in state["debts"]:
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
                                  on_click=lambda d=d: (
                                      _remove(state["debts"], d),
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
                                  "linked_debt": None,
                                  "net_rental_income": 0.0, "cca_rate": 0.0,
                                  "ucc": None}), assets_section.refresh()))
                if not state["assets"]:
                    ui.label("Aucun actif. Ajoutez maison, chalet, terrain...") \
                        .classes("text-gray-500")
                for a in state["assets"]:
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
                                  on_click=lambda a=a: (
                                      _remove(state["assets"], a),
                                      assets_section.refresh())).props("flat")
                    with ui.row().classes("gap-3 items-end flex-wrap pl-8") \
                            .bind_visibility_from(a, "kind", value="immeuble_locatif"):
                        ui.number("Loyers nets ($/an)", format="%.0f") \
                            .bind_value(a, "net_rental_income").classes("w-36").tooltip(
                            "Revenus locatifs moins dépenses (taxes, entretien, intérêts), "
                            "avant DPA; dollars d'aujourd'hui, indexés. Imposables.")
                        ui.number("DPA (%)", format="%.1f", min=0, max=10) \
                            .bind_value(a, "cca_rate").classes("w-28").tooltip(
                            "Taux d'amortissement fiscal (catégorie 1 = 4 %). 0 = aucune DPA. "
                            "Récupérée à la vente (imposable à 100 %).")
                        ui.number("FNACC ($, vide = coût)", format="%.0f") \
                            .bind_value(a, "ucc").classes("w-40").tooltip(
                            "Fraction non amortie du coût en capital au départ.")

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
                for v in state["vehicles"]:
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
                                  on_click=lambda v=v: (
                                      _remove(state["vehicles"], v),
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
                for e in state["special_expenses"]:
                    with ui.row().classes("gap-3 items-end flex-wrap"):
                        ui.input("Nom").bind_value(e, "name").classes("w-48")
                        ui.number("Année", format="%.0f").bind_value(
                            e, "year").classes("w-28")
                        ui.number("Montant ($)", format="%.0f").bind_value(
                            e, "amount").classes("w-32")
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda e=e: (
                                      _remove(state["special_expenses"], e),
                                      specials_section.refresh())).props("flat")

        # ==================== RENTES VIAGÈRES ====================
        @ui.refreshable
        def annuities_section():
            state.setdefault("annuities", [])
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("🏦 Rentes viagères").classes("text-lg font-bold text-primary")
                    ui.button("Ajouter une rente", icon="add",
                              on_click=lambda: (state["annuities"].append({
                                  "name": "Rente viagère", "person_index": 0,
                                  "purchase_year": int(state.get("start_year") or 2026) + 10,
                                  "premium": 100000.0, "annual_payment": 6300.0,
                                  "source": "reer", "indexed": False}),
                                  annuities_section.refresh()))
                ui.label("Achat d'une rente à vie avec une partie d'un compte: transfert "
                         "de risque de longévité. Le capital quitte le compte l'année "
                         "d'achat; les versements durent jusqu'au décès.") \
                    .classes("text-gray-500 text-sm")
                for an in state["annuities"]:
                    with ui.row().classes("gap-3 items-end flex-wrap"):
                        ui.input("Nom").bind_value(an, "name").classes("w-32")
                        ui.select(_persons_options(state), label="Rentier") \
                            .bind_value(an, "person_index").classes("w-36")
                        ui.select(ANNUITY_SOURCES, label="Source") \
                            .bind_value(an, "source").classes("w-56")
                        ui.number("Année d'achat", format="%.0f") \
                            .bind_value(an, "purchase_year").classes("w-32")
                        ui.number("Capital ($)", format="%.0f") \
                            .bind_value(an, "premium").classes("w-32")
                        ui.number("Versement ($/an)", format="%.0f") \
                            .bind_value(an, "annual_payment").classes("w-36")

                        def estimate(an=an):
                            p = state["persons"][int(an.get("person_index") or 0)]
                            age = int(an["purchase_year"]) - int(p["birth_year"])
                            an["annual_payment"] = round(float(an["premium"]) * _annuity_rate(age))
                            ui.notify(f"Taux indicatif à {age} ans: "
                                      f"{_annuity_rate(age) * 100:.1f} % du capital.", type="info")

                        ui.button("Estimer", on_click=estimate).props("flat dense") \
                            .tooltip("Versement indicatif selon l'âge à l'achat (taux du "
                                     "marché approximatifs, rente non réversible).")
                        ui.checkbox("Indexée").bind_value(an, "indexed")
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda an=an: (
                                      _remove(state["annuities"], an),
                                      annuities_section.refresh())).props("flat")

        # ==================== ASSURANCES VIE ====================
        @ui.refreshable
        def insurance_section():
            state.setdefault("life_insurances", [])
            with ui.card().classes("w-full"):
                with ui.row().classes("items-center justify-between w-full"):
                    ui.label("🛡️ Assurances vie").classes("text-lg font-bold text-primary")
                    ui.button("Ajouter une police", icon="add",
                              on_click=lambda: (state["life_insurances"].append({
                                  "name": "Assurance vie", "person_index": 0,
                                  "face_amount": 250000.0, "annual_premium": 2000.0,
                                  "premium_until_age": 100, "coverage_until_age": 120}),
                                  insurance_section.refresh()))
                ui.label("Prime fixe (non indexée) ajoutée aux dépenses; capital-décès "
                         "libre d'impôt versé au conjoint survivant ou ajouté à la "
                         "succession nette. Temporaire: fixez l'âge de fin de couverture.") \
                    .classes("text-gray-500 text-sm")
                for ins in state["life_insurances"]:
                    with ui.row().classes("gap-3 items-end flex-wrap"):
                        ui.input("Nom").bind_value(ins, "name").classes("w-32")
                        ui.select(_persons_options(state), label="Assuré") \
                            .bind_value(ins, "person_index").classes("w-36")
                        ui.number("Capital-décès ($)", format="%.0f") \
                            .bind_value(ins, "face_amount").classes("w-36")
                        ui.number("Prime ($/an)", format="%.0f") \
                            .bind_value(ins, "annual_premium").classes("w-28")
                        ui.number("Primes jusqu'à (âge)", format="%.0f") \
                            .bind_value(ins, "premium_until_age").classes("w-36")
                        ui.number("Couverture jusqu'à (âge)", format="%.0f") \
                            .bind_value(ins, "coverage_until_age").classes("w-40")
                        ui.button(icon="delete", color="negative",
                                  on_click=lambda ins=ins: (
                                      _remove(state["life_insurances"], ins),
                                      insurance_section.refresh())).props("flat")

        debts_section()
        assets_section()
        vehicles_section()
        specials_section()
        annuities_section()
        insurance_section()
