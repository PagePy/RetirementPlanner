"""Page Analyses — Monte Carlo, stress tests, stratégies, succession."""
import plotly.graph_objects as go
from nicegui import ui, run

from gui import compute
from gui.state import to_configs
from planner.core.longevity import planning_ages, survival_probability


def _fmt(x: float) -> str:
    return f"{x:,.0f}$".replace(",", " ")


def build(state: dict):
    with ui.column().classes("w-full gap-4"):

        # ==================== CAPACITÉ FINANCIÈRE ====================
        with ui.card().classes("w-full"):
            ui.label("Capacité financière").classes(
                "text-lg font-bold text-primary")
            ui.label(
                "Estime la dépense mensuelle nette qui épuise vos placements "
                "à la fin de votre horizon de retraite — ou qui laisse la "
                "succession souhaitée.").classes(
                    "text-gray-500 text-sm")
            estate_goal = ui.number("Succession nette souhaitée ($ d'aujourd'hui)",
                                    value=0, format="%.0f", min=0) \
                .props("dense outlined").classes("w-72") \
                .tooltip("0 = épuiser le patrimoine. Sinon, la dépense est réduite "
                         "pour laisser au moins ce montant (indexé) après impôt au décès.")
            capacity_area = ui.column().classes("w-full")

            async def do_capacity():
                capacity_area.clear()
                with capacity_area:
                    ui.spinner()
                    ui.label("Calcul de la capacité financière...")
                hh, scen = to_configs(state)
                capacity = await run.cpu_bound(
                    compute.calculate_financial_capacity, hh, scen,
                    float(estate_goal.value or 0))
                capacity_area.clear()
                with capacity_area:
                    ui.label(
                        f"{_fmt(capacity.monthly_income)} / mois").classes(
                            "text-3xl font-bold text-positive")
                    ui.label(
                        f"{_fmt(capacity.annual_income)} par année, en dollars "
                        "d'aujourd'hui et indexé selon votre scénario.").classes(
                            "text-gray-600")
                    ui.label(
                        f"Patrimoine financier projeté en {capacity.end_year}: "
                        f"{_fmt(capacity.final_wealth)}").classes(
                            "text-sm text-gray-500")
                    ui.label(
                        "Les actifs immobiliers sont exclus, sauf si une vente "
                        "est déjà planifiée dans le profil.").classes(
                            "text-xs text-gray-500")

            ui.button("Calculer ma capacité", on_click=do_capacity)

        # ==================== TESTS DE STRESS ====================
        with ui.card().classes("w-full"):
            ui.label("🌪️ Tests de stress").classes("text-lg font-bold text-primary")
            ui.label("Krach, mauvaise séquence de rendements, inflation élevée, "
                     "longévité, décès prématuré.").classes("text-gray-500 text-sm")
            stress_area = ui.column().classes("w-full")

            async def do_stress():
                stress_area.clear()
                with stress_area:
                    ui.spinner()
                hh, scen = to_configs(state)
                outcomes = await run.cpu_bound(compute.stress_battery, hh, scen)
                stress_area.clear()
                with stress_area:
                    columns = [{"name": c, "label": l, "field": c}
                               for c, l in [("desc", "Scénario"),
                                            ("success", "Résultat"),
                                            ("year", "1er manque"),
                                            ("wealth", "Patrimoine final"),
                                            ("tax", "Impôt à vie")]]
                    rows = [{
                        "desc": o.description,
                        "success": "✅ Réussi" if o.success else "❌ Échec",
                        "year": o.first_shortfall_year or "—",
                        "wealth": _fmt(o.final_wealth),
                        "tax": _fmt(o.total_lifetime_tax),
                    } for o in outcomes]
                    ui.table(columns=columns, rows=rows).classes("w-full") \
                        .props("dense flat bordered")
            ui.button("Lancer les tests de stress", on_click=do_stress)

        # ==================== MONTE CARLO ====================
        with ui.card().classes("w-full"):
            ui.label("🎲 Monte Carlo").classes("text-lg font-bold text-primary")
            mc_params = {"iterations": 200, "volatility": 10.0}
            with ui.row().classes("gap-4 items-end"):
                ui.number("Itérations", format="%.0f").bind_value(
                    mc_params, "iterations").classes("w-32")
                ui.number("Volatilité (%)", format="%.0f").bind_value(
                    mc_params, "volatility").classes("w-32")
            mc_area = ui.column().classes("w-full")

            async def do_mc():
                mc_area.clear()
                with mc_area:
                    ui.spinner()
                    ui.label("Simulations en cours (peut prendre un moment)...")
                hh, scen = to_configs(state)
                mc = await run.cpu_bound(
                    compute.monte_carlo, hh, scen,
                    int(mc_params["iterations"]),
                    float(mc_params["volatility"]) / 100)
                mc_area.clear()
                with mc_area:
                    prob = mc.success_probability
                    color = ("text-positive" if prob >= 0.85
                             else "text-warning" if prob >= 0.7
                             else "text-negative")
                    ui.label(f"Probabilité de succès: {prob:.0%}").classes(
                        f"text-2xl font-bold {color}")
                    fig = go.Figure(go.Bar(
                        x=["P10", "P25", "P50 (médiane)", "P75", "P90"],
                        y=[mc.final_wealth_percentiles[p]
                           for p in (10, 25, 50, 75, 90)]))
                    fig.update_layout(title="Patrimoine final — percentiles",
                                      height=340,
                                      margin=dict(l=40, r=20, t=50, b=40))
                    ui.plotly(fig).classes("w-full")
                    if mc.shortfall_years:
                        ui.label(
                            f"Échecs: premier manque médian en "
                            f"{mc.shortfall_years[len(mc.shortfall_years)//2]}") \
                            .classes("text-gray-600")
            ui.button("Lancer le Monte Carlo", on_click=do_mc)

        # ==================== STRATÉGIES ====================
        with ui.card().classes("w-full"):
            ui.label("⚖️ Comparateur de stratégies de décaissement").classes(
                "text-lg font-bold text-primary")
            strat_area = ui.column().classes("w-full")

            async def do_strat():
                strat_area.clear()
                with strat_area:
                    ui.spinner()
                hh, scen = to_configs(state)
                outcomes = await run.cpu_bound(
                    compute.strategy_comparison, hh, scen)
                strat_area.clear()
                with strat_area:
                    columns = [{"name": c, "label": l, "field": c}
                               for c, l in [("desc", "Stratégie"),
                                            ("success", "Cible"),
                                            ("tax", "Impôt à vie"),
                                            ("wealth", "Patrimoine final"),
                                            ("estate", "Succession nette")]]
                    rows = [{
                        "desc": o.description,
                        "success": "✅" if o.success
                                   else f"❌ ({o.years_below_target} ans)",
                        "tax": _fmt(o.lifetime_tax),
                        "wealth": _fmt(o.final_wealth),
                        "estate": _fmt(o.final_net_estate),
                    } for o in outcomes]
                    ui.table(columns=columns, rows=rows).classes("w-full") \
                        .props("dense flat bordered")
                    ui.label("Classement: stratégies réussies d'abord, puis "
                             "succession nette la plus élevée.").classes(
                        "text-gray-500 text-sm")
            ui.button("Comparer les stratégies", on_click=do_strat)

        # ==================== FONTE DU REER ====================
        with ui.card().classes("w-full"):
            ui.label("🧊 Fonte du REER (optimisation fiscale du décaissement)") \
                .classes("text-lg font-bold text-primary")
            ui.label("Retirer volontairement du REER/FERR chaque année jusqu'à un "
                     "plancher de revenu imposable (l'excédent est réinvesti dans le "
                     "CELI puis le non-enregistré) lisse le taux marginal et réduit "
                     "l'impôt au décès. Compare plusieurs planchers.") \
                .classes("text-gray-500 text-sm")
            floor_area = ui.column().classes("w-full")

            async def do_floors():
                floor_area.clear()
                with floor_area:
                    ui.spinner()
                    ui.label("7 planchers simulés...")
                hh, scen = to_configs(state)
                outcomes = await run.cpu_bound(compute.income_floor_comparison, hh, scen)
                floor_area.clear()
                with floor_area:
                    best = outcomes[0]
                    current = state.get("taxable_income_floor")
                    ui.label(f"Meilleur résultat: {best.label}").classes(
                        "text-lg font-bold text-positive")
                    rows = [{"floor": o.label, "ok": "✅" if o.success else "❌",
                             "tax": _fmt(o.lifetime_tax), "gis": _fmt(o.lifetime_gis),
                             "melt": _fmt(o.total_meltdown),
                             "estate": _fmt(o.final_net_estate)} for o in outcomes]
                    ui.table(columns=[
                        {"name": "floor", "label": "Plancher (par personne)", "field": "floor",
                         "align": "left"},
                        {"name": "ok", "label": "Cible", "field": "ok"},
                        {"name": "melt", "label": "Retraits volontaires", "field": "melt"},
                        {"name": "tax", "label": "Impôt à vie", "field": "tax"},
                        {"name": "gis", "label": "SRG à vie", "field": "gis"},
                        {"name": "estate", "label": "Succession nette", "field": "estate"},
                    ], rows=rows).classes("w-full").props("dense flat bordered")

                    def adopt():
                        state["taxable_income_floor"] = best.floor
                        ui.notify(f"Plancher appliqué au profil: {best.label}. "
                                  "Relancez la simulation.", type="positive")

                    with ui.row().classes("items-center gap-4"):
                        ui.button("Adopter le meilleur plancher", on_click=adopt)
                        ui.label("Plancher actuel du profil: "
                                 + (_fmt(current) if current else "aucun")) \
                            .classes("text-sm text-gray-500")
            ui.button("Comparer les planchers", on_click=do_floors)

        # ==================== LONGÉVITÉ ====================
        with ui.card().classes("w-full"):
            ui.label("⏳ Longévité — jusqu'à quel âge planifier ?") \
                .classes("text-lg font-bold text-primary")
            ui.label("Probabilités de survie à 65 ans selon les normes de projection. "
                     "Les normes recommandent de planifier jusqu'à l'âge que l'on a "
                     "25 % de chances d'atteindre.").classes("text-gray-500 text-sm")
            longevity_area = ui.column().classes("w-full")

            @ui.refreshable
            def show_longevity():
                n = 2 if state["is_couple"] else 1
                for i in range(n):
                    p = state["persons"][i]
                    sex = p.get("sex") or "F"
                    ages = planning_ages(sex)
                    with ui.row().classes("items-center gap-4 flex-wrap"):
                        ui.label(f"{p['name'] or f'Personne {i + 1}'} "
                                 f"({'homme' if sex == 'M' else 'femme'}) — "
                                 f"espérance saisie: {p['life_expectancy']} ans, "
                                 f"probabilité d'atteindre cet âge ≈ "
                                 f"{survival_probability(sex, int(p['life_expectancy'])) * 100:.0f} %") \
                            .classes("font-medium")
                        for pa in ages:
                            def set_age(p=p, age=pa.age):
                                p["life_expectancy"] = age
                                show_longevity.refresh()
                                ui.notify(f"Espérance de vie fixée à {age} ans.", type="info")
                            ui.button(f"{pa.probability} % → {pa.age} ans", on_click=set_age) \
                                .props("outline dense no-caps" + (
                                    " color=positive" if pa.probability == 25 else ""))

            with longevity_area:
                show_longevity()

        # ==================== COMPARAISON A/B ====================
        with ui.card().classes("w-full"):
            ui.label("🆚 Comparaison de scénarios").classes(
                "text-lg font-bold text-primary")
            ui.label("Figez le profil actuel comme scénario A, modifiez ce que "
                     "vous voulez dans les autres onglets, puis comparez avec "
                     "l'état actuel (B).").classes("text-gray-500 text-sm")
            snapshot: dict = {}
            with ui.row().classes("items-center gap-4 flex-wrap"):
                name_a = ui.input("Nom du scénario A", value="A") \
                    .props("dense outlined").classes("w-48")
                name_b = ui.input("Nom du scénario B", value="B") \
                    .props("dense outlined").classes("w-48")
                status_a = ui.label("Aucun scénario A figé.").classes(
                    "text-sm text-gray-500")

            def freeze_a():
                hh, scen = to_configs(state)
                snapshot["configs"] = (hh, scen)
                snapshot["name"] = name_a.value or "A"
                status_a.set_text(
                    f"Scénario «{snapshot['name']}» figé "
                    f"(cible {_fmt(hh.target_net_income)}, "
                    f"{len(hh.persons)} personne(s)).")

            ab_area = ui.column().classes("w-full")

            async def do_compare():
                if "configs" not in snapshot:
                    ui.notify("Figez d'abord le scénario A.", type="warning")
                    return
                ab_area.clear()
                with ab_area:
                    ui.spinner()
                    ui.label("Simulation des deux scénarios...")
                hh_a, scen_a = snapshot["configs"]
                hh_b, scen_b = to_configs(state)
                res_a, est_a = await run.cpu_bound(
                    compute.simulate_with_estate, hh_a, scen_a)
                res_b, est_b = await run.cpu_bound(
                    compute.simulate_with_estate, hh_b, scen_b)
                label_a, label_b = snapshot["name"], (name_b.value or "B")
                ab_area.clear()
                with ab_area:
                    rows = [
                        {"metric": m, "a": fa(res_a, est_a), "b": fa(res_b, est_b)}
                        for m, fa in _AB_METRICS]
                    for row in rows:
                        row["delta"] = _delta(row["a"], row["b"])
                        row["a"], row["b"] = _fmt_metric(row["a"]), _fmt_metric(row["b"])
                    ui.table(
                        columns=[
                            {"name": "metric", "label": "Indicateur", "field": "metric",
                             "align": "left"},
                            {"name": "a", "label": label_a, "field": "a", "align": "right"},
                            {"name": "b", "label": label_b, "field": "b", "align": "right"},
                            {"name": "delta", "label": "B − A", "field": "delta",
                             "align": "right"},
                        ],
                        rows=rows).classes("w-full").props("dense flat bordered")
                    fig = go.Figure()
                    for label, res in ((label_a, res_a), (label_b, res_b)):
                        fig.add_trace(go.Scatter(
                            name=f"Valeur nette — {label}", mode="lines",
                            x=[r.year for r in res], y=[r.net_worth for r in res]))
                    for label, res in ((label_a, res_a), (label_b, res_b)):
                        fig.add_trace(go.Scatter(
                            name=f"Net encaissé — {label}", mode="lines",
                            line=dict(dash="dot"), yaxis="y2",
                            x=[r.year for r in res], y=[r.net_cash for r in res]))
                    fig.update_layout(
                        title="Valeur nette et revenu net encaissé",
                        yaxis2=dict(overlaying="y", side="right", showgrid=False),
                        height=420, margin=dict(l=40, r=60, t=50, b=40))
                    ui.plotly(fig).classes("w-full")

            with ui.row().classes("gap-4"):
                ui.button("📌 Figer le scénario A", on_click=freeze_a)
                ui.button("Comparer A et B", on_click=do_compare).props("color=primary")


def _retired_years(results):
    return [r for r in results if any(p.retired for p in r.persons if p.alive)]


_AB_METRICS = [
    ("Années sous la cible",
     lambda res, est: sum(1 for r in _retired_years(res) if r.target_gap < -500)),
    ("Impôt total à vie", lambda res, est: sum(r.total_tax for r in res)),
    ("SRG total reçu", lambda res, est: sum(p.gis for r in res for p in r.persons)),
    ("Récupération SV totale",
     lambda res, est: sum(p.oas_clawback for r in res for p in r.persons)),
    ("Revenu net moyen (retraite)",
     lambda res, est: (sum(r.net_cash for r in _retired_years(res))
                       / max(1, len(_retired_years(res))))),
    ("Patrimoine financier final", lambda res, est: res[-1].total_wealth),
    ("Valeur nette finale", lambda res, est: res[-1].net_worth),
    ("Succession nette finale", lambda res, est: est[-1].net_estate if est else 0.0),
    ("Dernière année simulée", lambda res, est: res[-1].year),
]


def _fmt_metric(v) -> str:
    if isinstance(v, int):
        return str(v)
    return _fmt(v)


def _delta(a, b) -> str:
    d = b - a
    if isinstance(a, int):
        return f"{d:+d}"
    return f"{d:+,.0f}$".replace(",", " ")
