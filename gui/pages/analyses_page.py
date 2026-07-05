"""Page Analyses — Monte Carlo, stress tests, stratégies, succession."""
import plotly.graph_objects as go
from nicegui import ui, run

from gui import compute
from gui.state import to_configs


def _fmt(x: float) -> str:
    return f"{x:,.0f}$".replace(",", " ")


def build(state: dict):
    with ui.column().classes("w-full gap-4"):

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
