"""Page Résultats — dashboard de décaissement exhaustif."""
import csv
import io

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
        ("Salaires", lambda r: sum(p.salary + p.part_time_income for p in r.persons)),
        ("Loyers nets", lambda r: r.rental_income),
        ("Rentes PD", lambda r: sum(p.db_pension for p in r.persons)),
        ("Rentes viagères", lambda r: sum(p.annuity_income for p in r.persons)),
        ("RRQ", lambda r: sum(p.rrq for p in r.persons)),
        ("SV", lambda r: sum(p.oas for p in r.persons)),
        ("SRG / crédits remb.", lambda r: sum(p.gis + p.refundable_credits for p in r.persons)),
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


# Soldes de fin d'année exposés dans le tableau (accumulation par compte).
_BALANCE_FIELDS = [
    ("bal_reer", "Solde REER"), ("bal_celi", "Solde CELI"),
    ("bal_celiapp", "Solde CELIAPP"), ("bal_cri", "Solde CRI"),
    ("bal_ferr", "Solde FERR"), ("bal_frv", "Solde FRV"),
    ("bal_taxable", "Solde non-enr."),
]


def _active_balance_fields(results) -> list[tuple[str, str]]:
    """Ne garde que les comptes ayant un solde non nul sur l'horizon."""
    return [(field, label) for field, label in _BALANCE_FIELDS
            if any(getattr(p, field) > 1 for r in results for p in r.persons)]


# Descriptions affichées en infobulle au survol de chaque en-tête de colonne.
_COLUMN_TOOLTIPS = {
    "year": "Année civile de la projection.",
    "ages": "Âge de chaque personne à la fin de l'année.",
    "salary": "Revenu d'emploi (salaire, incluant l'emploi à temps partiel après la retraite) "
              "et loyers nets d'immeubles locatifs.",
    "db": "Rentes d'employeur à prestations déterminées (régimes PD) et rentes viagères achetées.",
    "rrq": "Rente du Régime de rentes du Québec (RRQ / RPC).",
    "oas": "Pension de la Sécurité de la vieillesse (SV), incluant la récupération.",
    "minimums": "Retraits MINIMUMS obligatoires du FERR et du FRV, imposés par la loi selon l'âge.",
    "registered": "Retraits REER + retraits FERR/FRV AU-DELÀ du minimum obligatoire "
                  "(incluant la fonte volontaire du REER, réinvestie).",
    "celi": "Retraits du CELI (non imposables), utilisés en dernier recours.",
    "nonreg": "Retraits du compte non enregistré (imposable sur les gains).",
    "other": "SRG (Supplément de revenu garanti) et crédits remboursables (maintien à domicile), non imposables.",
    "debt": "Paiements de dettes de l'année (service de la dette) et primes d'assurance vie.",
    "savings": "Cotisations de l'année durant l'accumulation : REER, CELI, "
               "CELIAPP, non-enr. et régime CD (incluant la part employeur).",
    "tax": "Impôts totaux + récupération de la SV pour l'année.",
    "expenses": "Cible de revenu net du ménage à financer (hors service de dette).",
    "shortfall": "Portion de la cible que le plan n'arrive PAS à financer.",
    "total_bal": "Somme de tous les comptes financiers à la fin de l'année.",
    "bal_ferr": "Solde du FERR (issu d'un REER, retraits flexibles) à la fin de l'année.",
    "bal_frv": "Solde du FRV (issu d'un CRI immobilisé, retrait plafonné) à la fin de l'année.",
}


def _cash_flow_columns_with_balances(balance_fields):
    columns = [
        {"name": c, "label": l, "field": c, "align": "right",
         "tooltip": _COLUMN_TOOLTIPS.get(c, "")}
        for c, l in [
            ("year", "Année"), ("ages", "Âges"),
            ("salary", "Revenu gagné"), ("db", "Rentes"),
            ("rrq", "RPC/RRQ"), ("oas", "SV"),
            ("minimums", "Min. FERR/FRV"),
            ("registered", "Enregistré"), ("celi", "CELI"),
            ("nonreg", "Non enregistré"), ("other", "SRG / crédits remb."),
            ("debt", "Dette / assur."), ("savings", "Épargne"),
            ("tax", "Impôts + récup. SV"), ("expenses", "Dépenses"),
            ("shortfall", "Insuffisances"),
        ]]
    columns += [{"name": field, "label": label, "field": field, "align": "right",
                 "tooltip": _COLUMN_TOOLTIPS.get(
                     field, f"Solde du compte {label.replace('Solde ', '')} "
                            "à la fin de l'année (accumulation).")}
                for field, label in balance_fields]
    columns.append({"name": "total_bal", "label": "Total placements",
                    "field": "total_bal", "align": "right",
                    "tooltip": _COLUMN_TOOLTIPS["total_bal"]})
    return columns


def _balance_values(persons, balance_fields) -> dict:
    values = {field: sum(getattr(p, field) for p in persons)
              for field, _ in balance_fields}
    values["total_bal"] = sum(p.wealth for p in persons)
    return values


# Slot d'en-tête Quasar: infobulle après ~1 s au survol d'un titre de colonne.
_HEADER_SLOT = '''
<q-tr :props="props">
  <q-th v-for="col in props.cols" :key="col.name" :props="props">
    {{ col.label }}
    <q-tooltip v-if="col.tooltip" :delay="1000" anchor="bottom middle"
               self="top middle" max-width="320px" class="text-body2 bg-grey-9">
      {{ col.tooltip }}
    </q-tooltip>
  </q-th>
</q-tr>
'''


def _cash_flow_table(columns, rows):
    table = ui.table(columns=columns, rows=rows, pagination=False) \
        .classes("w-full").props("dense flat bordered separator=horizontal")
    table.add_slot("header", _HEADER_SLOT)
    return table


def _minimums(p) -> float:
    return p.ferr_min + p.frv_min


def _registered_withdrawals(p) -> float:
    return p.wd_reer + max(0.0, p.wd_ferr + p.wd_frv - _minimums(p))


def _savings(p) -> float:
    return (p.contrib_reer + p.contrib_spousal_reer + p.contrib_celi + p.contrib_celiapp
            + p.contrib_taxable + p.contrib_dc_employee + p.contrib_dc_employer)


def _flow_values(persons) -> dict:
    return {
        "salary": sum(p.salary + p.part_time_income + p.rental_income for p in persons),
        "db": sum(p.db_pension + p.annuity_income for p in persons),
        "rrq": sum(p.rrq for p in persons),
        "oas": sum(p.oas for p in persons),
        "minimums": sum(_minimums(p) for p in persons),
        "registered": sum(_registered_withdrawals(p) for p in persons),
        "celi": sum(p.wd_celi for p in persons),
        "nonreg": sum(p.wd_taxable for p in persons),
        "other": sum(p.gis + p.refundable_credits for p in persons),
        "savings": sum(_savings(p) for p in persons),
        "tax": sum(p.tax_total + p.oas_clawback for p in persons),
    }


def _year_rows(results, balance_fields, fmt=_fmt) -> list[dict]:
    rows = []
    for r in results:
        alive = [p for p in r.persons if p.alive]
        values = _flow_values(alive)
        balances = _balance_values(alive, balance_fields)
        rows.append({
            "year": r.year,
            "ages": " / ".join(str(p.age) for p in alive),
            **{key: fmt(value) for key, value in values.items()},
            **{key: fmt(value) for key, value in balances.items()},
            "debt": fmt(r.debt_service + r.insurance_premiums),
            "expenses": fmt(max(0.0, r.target_net - r.debt_service - r.insurance_premiums)),
            "shortfall": fmt(max(0.0, -r.target_gap)),
        })
    return rows


def _year_table(results):
    balance_fields = _active_balance_fields(results)
    _cash_flow_table(_cash_flow_columns_with_balances(balance_fields),
                     _year_rows(results, balance_fields))


def export_csv(results, person_names: list[str]) -> bytes:
    """Tableau familial + un bloc par personne, valeurs numériques brutes."""
    balance_fields = _active_balance_fields(results)
    columns = _cash_flow_columns_with_balances(balance_fields)
    keys = [c["field"] for c in columns]
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")

    def block(title: str, rows: list[dict]) -> None:
        writer.writerow([title])
        writer.writerow([c["label"] for c in columns])
        for row in rows:
            writer.writerow([row.get(k, "") for k in keys])
        writer.writerow([])

    raw = lambda x: round(x)  # noqa: E731
    block("Ménage", _year_rows(results, balance_fields, fmt=raw))
    for i, name in enumerate(person_names):
        block(name or f"Personne {i + 1}",
              _person_rows(results, i, balance_fields, fmt=raw))
    # BOM pour qu'Excel détecte l'UTF-8
    return ("\ufeff" + buf.getvalue()).encode("utf-8")


def _person_rows(results, person_index: int, balance_fields, fmt=_fmt) -> list[dict]:
    rows = []
    for r in results:
        p = r.persons[person_index]
        if not p.alive:
            continue
        values = _flow_values([p])
        balances = _balance_values([p], balance_fields)
        rows.append({
            "year": r.year, "ages": str(p.age),
            **{key: fmt(value) for key, value in values.items()},
            **{key: fmt(value) for key, value in balances.items()},
            "debt": "—", "expenses": "—", "shortfall": "—",
        })
    return rows


def _person_detail_table(results, person_index: int, name: str):
    ui.label(f"Flux individuel — {name}").classes("font-bold mt-4")
    ui.label("Les dépenses et dettes communes sont présentées dans la vue familiale.") \
        .classes("text-sm text-gray-500")
    balance_fields = _active_balance_fields(results)
    _cash_flow_table(_cash_flow_columns_with_balances(balance_fields),
                     _person_rows(results, person_index, balance_fields))


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
                total_fees = sum(r.total_fees for r in results)
                if total_fees > 0:
                    card("Frais de gestion à vie", _fmt(total_fees), "text-warning")
                card("Patrimoine final", _fmt(results[-1].total_wealth))
                card("Valeur nette finale", _fmt(results[-1].net_worth))
                card("Succession nette finale",
                     _fmt(estates[-1].net_estate) if estates else "—")
            if shortfalls:
                with ui.expansion(
                        f"⚠️ Pourquoi la cible n'est pas atteinte ({len(shortfalls)} années)") \
                        .classes("w-full"):
                    for r in shortfalls:
                        ui.label(f"{r.year}: {r.shortfall_note or 'cible non atteinte'}") \
                            .classes("text-sm")
            names = [state["persons"][i]["name"] for i in range(len(results[0].persons))]
            with ui.row().classes("gap-2"):
                ui.button("⬇️ Exporter CSV", icon="download",
                          on_click=lambda: ui.download.content(
                              export_csv(results, names),
                              f"{state.get('profile_name') or 'simulation'}.csv")) \
                    .props("flat")

                async def do_pdf():
                    from gui import report
                    ui.notify("Génération du rapport PDF...", type="info")
                    try:
                        pdf = await run.cpu_bound(
                            report.build_pdf, dict(state), hh, scen, results, estates)
                    except Exception as exc:
                        ui.notify(f"Erreur PDF: {exc}", type="negative")
                        return
                    ui.download.content(
                        pdf, f"{state.get('profile_name') or 'plan'}-rapport.pdf")

                ui.button("📄 Rapport PDF", icon="picture_as_pdf", on_click=do_pdf) \
                    .props("flat") \
                    .tooltip("Rapport client: hypothèses, résultats clés, graphiques, "
                             "projection annuelle et avertissements.")
            ui.plotly(_income_chart(results)).classes("w-full")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                ui.plotly(_wealth_chart(results)).classes("w-full lg:w-[48%]")
                ui.plotly(_tax_chart(results, estates)).classes("w-full lg:w-[48%]")
            ui.label("Projection du flux monétaire brut").classes(
                "text-lg font-bold mt-2")
            with ui.expansion("ℹ️ Signification des colonnes").classes("w-full"):
                ui.markdown(
                    "- **Min. FERR/FRV** : retraits *minimums obligatoires* du "
                    "FERR et du FRV (imposés par la loi selon l'âge).\n"
                    "- **Enregistré** : retraits REER + retraits FERR/FRV "
                    "*au-delà* du minimum obligatoire.\n"
                    "- **CELI / Non enregistré** : retraits de ces comptes.\n"
                    "- **SRG** : Supplément de revenu garanti reçu "
                    "(prestation non imposable, versée en sus de la cible).\n"
                    "- **Épargne** : cotisations de l'année (REER, CELI, "
                    "CELIAPP, non-enr., régime CD) durant l'accumulation.\n"
                    "- **Colonnes « Solde … »** : valeur de chaque compte à la "
                    "*fin de l'année* (accumulation), et **Total placements** "
                    "= somme de tous les comptes financiers.")
            with ui.expansion("❓ FERR ou FRV : quelle différence ?").classes("w-full"):
                ui.markdown(
                    "Les deux sont des comptes de *décaissement* qui imposent un "
                    "**retrait minimum obligatoire** chaque année (selon l'âge), "
                    "et tout retrait est **imposable**.\n\n"
                    "- **FERR** (Fonds enregistré de revenu de retraite) : "
                    "provient d'un **REER**. Aucun plafond de retrait — vous "
                    "pouvez en sortir autant que voulu.\n"
                    "- **FRV** (Fonds de revenu viager) : provient de fonds "
                    "**immobilisés** d'un régime de retraite d'employeur "
                    "(via un CRI). Il a un **minimum ET un maximum** annuels, "
                    "car l'argent est censé durer toute la vie.\n\n"
                    "En résumé : le **FERR = REER converti** (flexible), le "
                    "**FRV = CRI converti** (plafonné). La conversion se fait au "
                    "plus tard à **71 ans**.")
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
