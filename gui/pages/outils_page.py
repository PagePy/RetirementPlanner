"""Page Outils — solveurs d'objectifs, plan suggéré, projets de vie."""
from nicegui import ui, run

from gui import compute
from gui.state import to_configs
from planner.core.goals import ProfileAnswers, suggest_plan


def _fmt(x: float) -> str:
    return f"{x:,.0f}$".replace(",", " ")


def build(state: dict):
    with ui.column().classes("w-full gap-4"):

        # ==================== SOLVEURS ====================
        with ui.card().classes("w-full"):
            ui.label("🎯 Atteindre vos objectifs").classes(
                "text-lg font-bold text-primary")
            goals_area = ui.column().classes("w-full")

            async def do_goals():
                goals_area.clear()
                with goals_area:
                    ui.spinner()
                    ui.label("Calcul des solveurs (plusieurs simulations)...")
                hh, scen = to_configs(state)
                res = await run.cpu_bound(compute.solve_goals, hh, scen)
                goals_area.clear()
                with goals_area, ui.row().classes("gap-4 flex-wrap"):
                    def card(title, value, note=""):
                        with ui.card().classes("min-w-64"):
                            ui.label(title).classes("text-xs text-gray-500")
                            ui.label(value).classes("text-xl font-bold text-primary")
                            if note:
                                ui.label(note).classes("text-xs text-gray-500")
                    card("Revenu net soutenable maximal",
                         f"{_fmt(res['sustainable'])}/an",
                         "en dollars d'aujourd'hui, indexé à vie")
                    rs = res["required_savings"]
                    card("Épargne additionnelle requise",
                         "Aucune — plan déjà réussi" if rs == 0.0
                         else ("Objectif inatteignable" if rs is None
                               else f"{_fmt(rs)}/an"),
                         "pour atteindre la cible actuelle")
                    ea = res["earliest_age"]
                    card("Retraite au plus tôt",
                         f"{ea} ans" if ea else "Impossible avec la cible",
                         f"pour {state['persons'][0]['name']}")
            ui.button("Calculer mes objectifs", on_click=do_goals)

        # ==================== ÂGES RRQ/SV ====================
        with ui.card().classes("w-full"):
            ui.label("📅 Âge optimal RRQ et SV").classes(
                "text-lg font-bold text-primary")
            ages_area = ui.column().classes("w-full")

            async def do_ages():
                ages_area.clear()
                with ages_area:
                    ui.spinner()
                    ui.label("18 combinaisons simulées...")
                hh, scen = to_configs(state)
                options = await run.cpu_bound(compute.benefit_ages, hh, scen)
                ages_area.clear()
                with ages_area:
                    best = options[0]
                    ui.label(f"Recommandation: RRQ à {best.rrq_age} ans, "
                             f"SV à {best.oas_age} ans").classes(
                        "text-lg font-bold text-positive")
                    columns = [{"name": c, "label": l, "field": c}
                               for c, l in [("rrq", "RRQ"), ("oas", "SV"),
                                            ("ok", "Cible"),
                                            ("estate", "Succession nette"),
                                            ("tax", "Impôt à vie")]]
                    rows = [{"rrq": f"{o.rrq_age} ans", "oas": f"{o.oas_age} ans",
                             "ok": "✅" if o.success else "❌",
                             "estate": _fmt(o.final_net_estate),
                             "tax": _fmt(o.lifetime_tax)} for o in options]
                    ui.table(columns=columns, rows=rows, pagination=9) \
                        .classes("w-full").props("dense flat bordered")
            ui.button("Comparer les âges RRQ/SV", on_click=do_ages)

        # ==================== PLAN SUGGÉRÉ ====================
        with ui.card().classes("w-full"):
            ui.label("🧭 Plan suggéré (pour débuter)").classes(
                "text-lg font-bold text-primary")
            q = {"age": 35, "salary": 60000.0, "couple": False,
                 "owns_home": False, "wants_home": False, "children": False,
                 "retirement_age": 65, "pension": False, "risk": "modere"}
            with ui.row().classes("gap-4 items-end flex-wrap"):
                ui.number("Âge", format="%.0f").bind_value(q, "age").classes("w-24")
                ui.number("Salaire ($)", format="%.0f").bind_value(
                    q, "salary").classes("w-32")
                ui.number("Retraite visée (âge)", format="%.0f").bind_value(
                    q, "retirement_age").classes("w-36")
                ui.select({"prudent": "Prudent", "modere": "Modéré",
                           "audacieux": "Audacieux"}, label="Profil de risque") \
                    .bind_value(q, "risk").classes("w-36")
            with ui.row().classes("gap-4 flex-wrap"):
                ui.checkbox("En couple").bind_value(q, "couple")
                ui.checkbox("Propriétaire").bind_value(q, "owns_home")
                ui.checkbox("Veut acheter une maison").bind_value(q, "wants_home")
                ui.checkbox("Enfants").bind_value(q, "children")
                ui.checkbox("Régime d'employeur").bind_value(q, "pension")
            plan_area = ui.column().classes("w-full")

            def do_suggest():
                plan_area.clear()
                s = suggest_plan(ProfileAnswers(
                    age=int(q["age"]), salary=float(q["salary"]),
                    couple=q["couple"], owns_home=q["owns_home"],
                    wants_to_buy_home=q["wants_home"],
                    has_children=q["children"],
                    target_retirement_age=int(q["retirement_age"]),
                    employer_pension=q["pension"], risk_comfort=q["risk"]))
                with plan_area:
                    ui.label(s.title).classes("text-lg font-bold text-positive")
                    ui.label(f"Taux d'épargne recommandé: "
                             f"{s.savings_rate:.0%} du revenu brut — "
                             f"Priorité: {' → '.join(s.account_priority)}") \
                        .classes("font-bold")
                    for e in s.explanations:
                        ui.label(f"• {e}").classes("text-sm")
                    for w in s.warnings:
                        ui.label(f"⚠️ {w}").classes("text-sm text-warning")
            ui.button("Obtenir mon plan suggéré", on_click=do_suggest)

        # ==================== MISE DE FONDS ====================
        with ui.card().classes("w-full"):
            ui.label("🏡 Mise de fonds: CELIAPP vs RAP").classes(
                "text-lg font-bold text-primary")
            dp = {"savings": 12000.0, "years": 5, "rate": 37.0, "couple": False}
            with ui.row().classes("gap-4 items-end flex-wrap"):
                ui.number("Épargne annuelle ($)", format="%.0f").bind_value(
                    dp, "savings").classes("w-40")
                ui.number("Années avant l'achat", format="%.0f").bind_value(
                    dp, "years").classes("w-40")
                ui.number("Taux marginal (%)", format="%.0f").bind_value(
                    dp, "rate").classes("w-36")
                ui.checkbox("En couple (plafonds doublés)").bind_value(dp, "couple")
            dp_area = ui.column().classes("w-full")

            async def do_dp():
                dp_area.clear()
                options = await run.cpu_bound(
                    compute.down_payment, float(dp["savings"]),
                    int(dp["years"]), float(dp["rate"]) / 100, dp["couple"])
                with dp_area:
                    for o in options:
                        with ui.card().classes("w-full bg-blue-50"):
                            ui.label(f"{o.description} — mise de fonds: "
                                     f"{_fmt(o.down_payment)}").classes("font-bold")
                            for note in o.notes:
                                ui.label(f"• {note}").classes("text-sm")
            ui.button("Comparer", on_click=do_dp)

        # ==================== COÛT D'UN PROJET ====================
        with ui.card().classes("w-full"):
            ui.label("💸 Vrai coût d'un projet sur la retraite").classes(
                "text-lg font-bold text-primary")
            pj = {"name": "Rénovation", "year": 2032, "amount": 30000.0}
            with ui.row().classes("gap-4 items-end flex-wrap"):
                ui.input("Nom").bind_value(pj, "name").classes("w-40")
                ui.number("Année", format="%.0f").bind_value(
                    pj, "year").classes("w-28")
                ui.number("Montant ($)", format="%.0f").bind_value(
                    pj, "amount").classes("w-32")
            pj_area = ui.column().classes("w-full")

            async def do_pj():
                pj_area.clear()
                with pj_area:
                    ui.spinner()
                hh, scen = to_configs(state)
                impact = await run.cpu_bound(
                    compute.project_cost, hh, scen, pj["name"],
                    int(pj["year"]), float(pj["amount"]))
                pj_area.clear()
                with pj_area:
                    ui.label(
                        f"«{impact.name}» ({_fmt(impact.amount)} en {impact.year}) "
                        f"coûtera réellement {_fmt(impact.wealth_cost)} en "
                        f"patrimoine final et {_fmt(impact.net_estate_cost)} en "
                        f"succession nette.").classes("font-bold")
                    ui.label("✅ Votre plan reste réussi avec ce projet."
                             if impact.plan_still_succeeds else
                             "❌ Attention: ce projet compromet votre cible de "
                             "retraite.").classes(
                        "text-positive" if impact.plan_still_succeeds
                        else "text-negative")
            ui.button("Évaluer l'impact", on_click=do_pj)
