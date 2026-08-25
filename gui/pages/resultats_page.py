"""Page Résultats — dashboard de décaissement exhaustif."""
import plotly.graph_objects as go
from nicegui import ui, run

from gui import compute
from gui.state import to_configs


def _fmt(x: float) -> str:
    return f"{x:,.0f}$".replace(",", " ")


def _income_chart(results) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    sources = [
        ("Salaires", lambda r: sum(p.salary for p in r.persons)),
        ("Rentes PD", lambda r: sum(p.db_pension for p in r.persons)),
        ("RRQ", lambda r: sum(p.rrq for p in r.persons)),
        ("SV", lambda r: sum(p.oas for p in r.persons)),
        ("SRG", lambda r: sum(p.gis for p in r.persons)),
        ("FERR/FRV", lambda r: sum(p.wd_ferr + p.wd_frv for p in r.persons)),
        ("REER", lambda r: sum(p.wd_reer for p in r.persons)),
        ("Non-enregistré", lambda r: sum(p.wd_taxable for p in r.persons)),
        ("CELI", lambda r: sum(p.wd_celi for p in r.persons)),
    ]
    for name, fn in sources:
        values = [fn(r) for r in results]
        if any(v > 1 for v in values):
            fig.add_trace(go.Bar(name=name, x=years, y=values))
    fig.add_trace(go.Scatter(
        name="Cible nette", x=years, y=[r.target_net for r in results],
        mode="lines", line=dict(color="black", dash="dash")))
    fig.add_trace(go.Scatter(
        name="Net encaissé", x=years, y=[r.net_cash for r in results],
        mode="lines", line=dict(color="green", width=3)))
    fig.update_layout(barmode="stack", title="Sources de revenus vs cible",
                      height=420, margin=dict(l=40, r=20, t=50, b=40))
    return fig


def _wealth_chart(results) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    accounts = [
        ("REER", lambda p: p.bal_reer), ("CELI", lambda p: p.bal_celi),
        ("CELIAPP", lambda p: p.bal_celiapp), ("CRI", lambda p: p.bal_cri),
        ("FERR", lambda p: p.bal_ferr), ("FRV", lambda p: p.bal_frv),
        ("Non-enregistré", lambda p: p.bal_taxable),
    ]
    for name, fn in accounts:
        values = [sum(fn(p) for p in r.persons) for r in results]
        if any(v > 1 for v in values):
            fig.add_trace(go.Scatter(name=name, x=years, y=values,
                                     stackgroup="one", mode="lines"))
    fig.add_trace(go.Scatter(
        name="Valeur nette (incl. immobilier − dettes)",
        x=years, y=[r.net_worth for r in results],
        mode="lines", line=dict(color="black", width=2, dash="dot")))
    fig.update_layout(title="Évolution du patrimoine", height=420,
                      margin=dict(l=40, r=20, t=50, b=40))
    return fig


def _tax_chart(results, estates) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Impôts + récup. SV", x=years,
                         y=[r.total_tax for r in results]))
    if estates:
        fig.add_trace(go.Scatter(
            name="Succession nette (si décès cette année)",
            x=[e.year for e in estates], y=[e.net_estate for e in estates],
            mode="lines", line=dict(color="purple"), yaxis="y2"))
    fig.update_layout(
        title="Impôts annuels et succession nette",
        yaxis2=dict(overlaying="y", side="right", showgrid=False),
        height=420, margin=dict(l=40, r=60, t=50, b=40))
    return fig


def _cash_flow_columns():
    columns = [
        {"name": c, "label": l, "field": c, "align": "right"}
        for c, l in [
            ("year", "Année"), ("ages", "Âges"),
            ("salary", "Revenu gagné"), ("db", "Régimes de retraite"),
            ("rrq", "RPC/RRQ"), ("oas", "SV"), ("minimums", "Minimums"),
            ("registered", "Enregistré"), ("celi", "CELI"),
            ("nonreg", "Non enregistré"), ("other", "Autre"),
            ("debt", "Dette"), ("savings", "Épargne"),
            ("tax", "Retenues/Impôts"), ("expenses", "Dépenses"),
            ("shortfall", "Insuffisances"),
        ]]
    return columns


def _minimums(p) -> float:
    return p.ferr_min + p.frv_min


def _registered_withdrawals(p) -> float:
    return p.wd_reer + max(0.0, p.wd_ferr + p.wd_frv - _minimums(p))


def _savings(p) -> float:
    return (p.contrib_reer + p.contrib_celi + p.contrib_celiapp
            + p.contrib_taxable + p.contrib_dc_employee + p.contrib_dc_employer)


def _flow_values(persons) -> dict:
    return {
        "salary": sum(p.salary for p in persons),
        "db": sum(p.db_pension for p in persons),
        "rrq": sum(p.rrq for p in persons),
        "oas": sum(p.oas for p in persons),
        "minimums": sum(_minimums(p) for p in persons),
        "registered": sum(_registered_withdrawals(p) for p in persons),
        "celi": sum(p.wd_celi for p in persons),
        "nonreg": sum(p.wd_taxable for p in persons),
        "other": sum(p.gis for p in persons),
        "savings": sum(_savings(p) for p in persons),
        "tax": sum(p.tax_total + p.oas_clawback for p in persons),
    }


def _year_table(results):
    rows = []
    for r in results:
        alive = [p for p in r.persons if p.alive]
        values = _flow_values(alive)
        rows.append({
            "year": r.year,
            "ages": " / ".join(str(p.age) for p in alive),
            **{key: _fmt(value) for key, value in values.items()},
            "debt": _fmt(r.debt_service),
            "expenses": _fmt(max(0.0, r.target_net - r.debt_service)),
            "shortfall": _fmt(max(0.0, -r.target_gap)),
        })
    ui.table(columns=_cash_flow_columns(), rows=rows, pagination=False).classes("w-full") \
        .props("dense flat bordered separator=horizontal")


def _person_detail_table(results, person_index: int, name: str):
    ui.label(f"Flux individuel — {name}").classes("font-bold mt-4")
    ui.label("Les dépenses et dettes communes sont présentées dans la vue familiale.") \
        .classes("text-sm text-gray-500")
    rows = []
    for r in results:
        p = r.persons[person_index]
        if not p.alive:
            continue
        values = _flow_values([p])
        rows.append({
            "year": r.year, "ages": str(p.age),
            **{key: _fmt(value) for key, value in values.items()},
            "debt": "—", "expenses": "—", "shortfall": "—",
        })
    ui.table(columns=_cash_flow_columns(), rows=rows, pagination=False).classes("w-full") \
        .props("dense flat bordered separator=horizontal")


def build(state: dict):
    async def run_simulation():
        container.clear()
        with container:
            ui.spinner(size="lg")
            ui.label("Simulation en cours...")
        try:
            hh, scen = to_configs(state)
            results, estates = await run.cpu_bound(
                compute.simulate_with_estate, hh, scen)
        except Exception as exc:
            container.clear()
            with container:
                ui.label(f"Erreur: {exc}").classes("text-negative")
            return
        container.clear()
        with container:
            retired = [r for r in results
                       if any(p.retired for p in r.persons if p.alive)]
            shortfalls = [r for r in retired if r.target_gap < -500]
            with ui.row().classes("gap-4 w-full flex-wrap"):
                def card(title, value, color="text-primary"):
                    with ui.card().classes("min-w-44"):
                        ui.label(title).classes("text-xs text-gray-500")
                        ui.label(value).classes(f"text-xl font-bold {color}")
                card("Plan", "✅ Réussi" if not shortfalls
                     else f"⚠️ {len(shortfalls)} années sous la cible",
                     "text-positive" if not shortfalls else "text-negative")
                card("Impôt total à vie", _fmt(sum(r.total_tax for r in results)))
                card("Patrimoine final", _fmt(results[-1].total_wealth))
                card("Valeur nette finale", _fmt(results[-1].net_worth))
                card("Succession nette finale",
                     _fmt(estates[-1].net_estate) if estates else "—")
            ui.plotly(_income_chart(results)).classes("w-full")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                ui.plotly(_wealth_chart(results)).classes("w-full lg:w-[48%]")
                ui.plotly(_tax_chart(results, estates)).classes("w-full lg:w-[48%]")
            ui.label("Projection du flux monétaire brut").classes(
                "text-lg font-bold mt-2")
            with ui.tabs().classes("w-full") as cash_flow_tabs:
                household_tab = ui.tab("Familial")
                person_tabs = [ui.tab(state["persons"][i]["name"] or f"Personne {i + 1}")
                               for i in range(len(results[0].persons))]
            with ui.tab_panels(cash_flow_tabs, value=household_tab).classes("w-full"):
                with ui.tab_panel(household_tab):
                    _year_table(results)
                for i, person_tab in enumerate(person_tabs):
                    with ui.tab_panel(person_tab):
                        _person_detail_table(results, i, state["persons"][i]["name"])

    with ui.row().classes("items-center gap-4"):
        ui.button("🚀 Lancer la simulation", on_click=run_simulation) \
            .props("size=lg color=primary")
        ui.label("Simulation complète: impôts réels, fractionnement optimal, "
                 "SRG, dettes et actifs.").classes("text-gray-500")
    container = ui.column().classes("w-full gap-4")
