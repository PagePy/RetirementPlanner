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


def _year_table(results):
    columns = [
        {"name": c, "label": l, "field": c, "align": "right"}
        for c, l in [
            ("year", "Année"), ("ages", "Âges"), ("salary", "Salaires"),
            ("pensions", "PD+RRQ+SV+SRG"), ("wd", "Retraits"),
            ("net_cash", "Net encaissé"), ("target", "Cible"),
            ("gap", "Écart"), ("tax", "Impôts"),
            ("debt", "Dettes"), ("wealth", "Patrimoine"),
            ("networth", "Valeur nette"),
        ]]
    rows = []
    for r in results:
        alive = [p for p in r.persons if p.alive]
        rows.append({
            "year": r.year,
            "ages": " / ".join(str(p.age) for p in alive),
            "salary": _fmt(sum(p.salary for p in alive)),
            "pensions": _fmt(sum(p.db_pension + p.rrq + p.oas + p.gis
                                 for p in alive)),
            "wd": _fmt(sum(p.wd_reer + p.wd_ferr + p.wd_frv + p.wd_taxable
                           + p.wd_celi for p in alive)),
            "net_cash": _fmt(r.net_cash),
            "target": _fmt(r.target_net),
            "gap": _fmt(r.target_gap),
            "tax": _fmt(r.total_tax),
            "debt": _fmt(r.debts_balance),
            "wealth": _fmt(r.total_wealth),
            "networth": _fmt(r.net_worth),
        })
    ui.table(columns=columns, rows=rows, pagination=15).classes("w-full") \
        .props("dense flat bordered")


def _person_detail_table(results, person_index: int, name: str):
    ui.label(f"Détail — {name}").classes("font-bold mt-4")
    columns = [
        {"name": c, "label": l, "field": c, "align": "right"}
        for c, l in [
            ("year", "Année"), ("age", "Âge"), ("db", "PD"), ("rrq", "RRQ"),
            ("oas", "SV"), ("gis", "SRG"), ("ferr", "FERR/FRV"),
            ("reer", "REER"), ("nonreg", "Non-enr."), ("celi", "CELI"),
            ("split", "Fractionnement"), ("taxable", "Rev. imposable"),
            ("tax", "Impôt"), ("clawback", "Récup. SV"),
        ]]
    rows = []
    for r in results:
        p = r.persons[person_index]
        if not p.alive:
            continue
        rows.append({
            "year": r.year, "age": p.age,
            "db": _fmt(p.db_pension), "rrq": _fmt(p.rrq),
            "oas": _fmt(p.oas), "gis": _fmt(p.gis),
            "ferr": _fmt(p.wd_ferr + p.wd_frv), "reer": _fmt(p.wd_reer),
            "nonreg": _fmt(p.wd_taxable), "celi": _fmt(p.wd_celi),
            "split": _fmt(p.pension_split_received),
            "taxable": _fmt(p.taxable_income), "tax": _fmt(p.tax_total),
            "clawback": _fmt(p.oas_clawback),
        })
    ui.table(columns=columns, rows=rows, pagination=15).classes("w-full") \
        .props("dense flat bordered")


def build(state: dict):
    container = ui.column().classes("w-full gap-4")

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
            ui.label("Projection annuelle du ménage").classes(
                "text-lg font-bold mt-2")
            _year_table(results)
            for i in range(len(results[0].persons)):
                _person_detail_table(results, i, state["persons"][i]["name"])

    with ui.row().classes("items-center gap-4"):
        ui.button("🚀 Lancer la simulation", on_click=run_simulation) \
            .props("size=lg color=primary")
        ui.label("Simulation complète: impôts réels, fractionnement optimal, "
                 "SRG, dettes et actifs.").classes("text-gray-500")
