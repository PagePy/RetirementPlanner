"""Page Résultats — dashboard de décaissement exhaustif."""
import csv
import io

import plotly.graph_objects as go
from nicegui import ui, run

from gui import compute
from gui.state import to_configs
from planner.core.analysis import build_tax_sheet, verify


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


_CHART_LAYOUT = dict(height=420, margin=dict(l=40, r=80, t=50, b=40))


def _add_stacked_bars(fig, years, series) -> None:
    """Ajoute une barre par série non nulle (series = [(nom, valeurs)])."""
    for name, values in series:
        if any(abs(v) > 1 for v in values):
            fig.add_trace(go.Bar(name=name, x=years, y=values))


def _withdrawals_chart(results) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    accounts = [
        ("REER", lambda p: p.wd_reer), ("FERR", lambda p: p.wd_ferr),
        ("FRV", lambda p: p.wd_frv), ("CELI", lambda p: p.wd_celi),
        ("Non-enregistré", lambda p: p.wd_taxable),
    ]
    _add_stacked_bars(fig, years, [
        (name, [sum(fn(p) for p in r.persons) for r in results]) for name, fn in accounts])
    minimums = [sum(_minimums(p) for p in r.persons) for r in results]
    if any(v > 1 for v in minimums):
        fig.add_trace(go.Scatter(
            name="Minimum FERR/FRV obligatoire", x=years, y=minimums,
            mode="lines", line=dict(color="black", dash="dash")))
    fig.update_layout(barmode="stack", title="Décaissement par compte", **_CHART_LAYOUT)
    return fig


def _first_retirement_year(results):
    for r in results:
        if any(p.retired for p in r.persons if p.alive):
            return r.year
    return None


def _gap_chart(results) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    shortfalls = [min(0.0, r.target_gap) for r in results]
    if any(v < -1 for v in shortfalls):
        fig.add_trace(go.Bar(name="Insuffisance vs cible", x=years, y=shortfalls,
                             marker_color="#c62828"))
    reinvested = [r.reinvested for r in results]
    if any(v > 1 for v in reinvested):
        fig.add_trace(go.Bar(name="Surplus réinvesti", x=years, y=reinvested,
                             marker_color="#2e7d32"))
    retired = [r for r in results if any(p.retired for p in r.persons if p.alive)]
    fig.add_trace(go.Scatter(
        name="Couverture de la cible (%)", x=[r.year for r in retired],
        y=[r.net_cash / r.target_net if r.target_net > 1 else 0.0 for r in retired],
        mode="lines", line=dict(color="black", dash="dash"), yaxis="y2"))
    start = _first_retirement_year(results)
    if start is not None:
        fig.add_vline(x=start, line=dict(color="gray", dash="dot"),
                      annotation_text="Retraite", annotation_position="top left")
    fig.update_layout(
        barmode="relative", title="Écart annuel vs cible et surplus réinvesti",
        xaxis=dict(range=[years[0] - 0.5, years[-1] + 0.5]),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    tickformat=".0%", rangemode="tozero"),
        **_CHART_LAYOUT)
    return fig


def _effective_rate(p) -> float:
    return (p.tax_total + p.oas_clawback) / p.taxable_income if p.taxable_income > 1 else 0.0


def _tax_rate_chart(results, names: list[str]) -> go.Figure:
    fig = go.Figure()
    palette = ["#1565c0", "#ef6c00", "#6a1b9a"]
    for i, name in enumerate(names):
        name = name or f"Personne {i + 1}"
        rows = [(r.year, r.persons[i]) for r in results if r.persons[i].alive]
        if not rows:
            continue
        years = [y for y, _ in rows]
        color = palette[i % len(palette)]
        fig.add_trace(go.Scatter(
            name=f"{name} — taux effectif", x=years,
            y=[_effective_rate(p) for _, p in rows], mode="lines", line=dict(color=color)))
        fig.add_trace(go.Scatter(
            name=f"{name} — taux marginal", x=years,
            y=[p.marginal_rate for _, p in rows], mode="lines",
            line=dict(color=color, dash="dot")))
        clawback = [p.oas_clawback for _, p in rows]
        if any(v > 1 for v in clawback):
            fig.add_trace(go.Bar(name=f"{name} — récupération SV ($)", x=years, y=clawback,
                                 marker_color=color, opacity=0.3, yaxis="y2"))
    fig.update_layout(
        title="Taux d'imposition effectif et marginal",
        yaxis=dict(tickformat=".0%", rangemode="tozero"),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, rangemode="tozero",
                    ticksuffix=" $"),
        barmode="stack", **_CHART_LAYOUT)
    return fig


def _wealth_mix_chart(results) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    groups = [
        ("Enregistré imposable (REER/CRI/FERR/FRV)",
         lambda p: p.bal_reer + p.bal_cri + p.bal_ferr + p.bal_frv),
        ("Libre d'impôt (CELI/CELIAPP)", lambda p: p.bal_celi + p.bal_celiapp),
        ("Non-enr. — coût", lambda p: max(0.0, p.bal_taxable - p.taxable_unrealized_gain)),
        ("Non-enr. — gain latent", lambda p: max(0.0, p.taxable_unrealized_gain)),
    ]
    for name, fn in groups:
        values = [sum(fn(p) for p in r.persons) for r in results]
        if any(v > 1 for v in values):
            fig.add_trace(go.Scatter(name=name, x=years, y=values, mode="lines",
                                     stackgroup="one", groupnorm="percent"))
    fig.update_layout(title="Composition du patrimoine financier (%)",
                      yaxis=dict(ticksuffix="%", range=[0, 100]), **_CHART_LAYOUT)
    return fig


def _benefits_chart(results) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    sources = [
        ("RRQ", lambda p: p.rrq), ("SV", lambda p: p.oas), ("SRG", lambda p: p.gis),
        ("Crédits remboursables", lambda p: p.refundable_credits),
        ("Récupération SV", lambda p: -p.oas_clawback),
    ]
    _add_stacked_bars(fig, years, [
        (name, [sum(fn(p) for p in r.persons) for r in results]) for name, fn in sources])
    share = [(sum(p.rrq + p.oas + p.gis + p.refundable_credits - p.oas_clawback
                  for p in r.persons) / r.net_cash) if r.net_cash > 1 else 0.0
             for r in results]
    fig.add_trace(go.Scatter(
        name="% du net encaissé", x=years, y=share, mode="lines",
        line=dict(color="black", dash="dash"), yaxis="y2"))
    fig.update_layout(
        title="Prestations gouvernementales", barmode="relative",
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    tickformat=".0%", rangemode="tozero"),
        **_CHART_LAYOUT)
    return fig


def _estate_chart(results, estates) -> go.Figure:
    debts = {r.year: r.debts_balance for r in results}
    years = [e.year for e in estates]
    fig = go.Figure()
    _add_stacked_bars(fig, years, [
        ("Succession nette", [e.net_estate for e in estates]),
        ("Impôt au décès", [e.tax_at_death for e in estates]),
        ("Dettes à rembourser", [debts.get(e.year, 0.0) for e in estates]),
    ])
    fig.add_trace(go.Scatter(
        name="Succession brute", x=years, y=[e.gross_estate for e in estates],
        mode="lines", line=dict(color="black", dash="dot")))
    fig.update_layout(barmode="stack", title="Décomposition de la succession (si décès cette année)",
                      **_CHART_LAYOUT)
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
    "net": "Total net encaissé après impôts: revenus, retraits, SRG et crédits remboursables, "
           "moins impôts et récupération SV (à comparer à la colonne Dépenses).",
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
            ("tax", "Impôts + récup. SV"), ("net", "Net encaissé"),
            ("expenses", "Dépenses"),
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
        "net": sum(p.net_cash for p in persons),
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


def _columns(spec: list[tuple[str, str, str]]) -> list[dict]:
    return [{"name": name, "label": label, "field": name, "align": "right",
             "tooltip": tip} for name, label, tip in spec]


SUMMARY_COLUMNS = _columns([
    ("period", "Période", "Tranche de 5 années civiles."),
    ("ages", "Âges", "Âge de chaque personne au début → à la fin de la période."),
    ("salary", "Revenu gagné", "Salaires, emploi à temps partiel et loyers nets cumulés."),
    ("benefits", "Prestations gouv.", "RRQ + SV + SRG + crédits remboursables cumulés."),
    ("pensions", "Rentes", "Rentes PD et rentes viagères cumulées."),
    ("registered", "Retraits enregistrés", "Retraits REER + FERR + FRV cumulés."),
    ("free", "Retraits CELI / non-enr.", "Retraits du CELI et du compte non enregistré cumulés."),
    ("savings", "Épargne", "Cotisations cumulées (REER, CELI, CELIAPP, non-enr., régime CD)."),
    ("tax", "Impôts + récup. SV", "Impôts et récupération de la SV cumulés."),
    ("rate", "Taux effectif", "Impôts cumulés ÷ revenu imposable cumulé de la période."),
    ("net", "Net encaissé", "Total net encaissé après impôts, cumulé."),
    ("expenses", "Dépenses", "Cible de revenu net cumulée."),
    ("shortfall", "Insuffisances", "Portion cumulée de la cible non financée."),
    ("wealth", "Placements (fin)", "Total des comptes financiers à la fin de la période."),
    ("net_worth", "Valeur nette (fin)", "Placements + immobilier − dettes à la fin de la période."),
])


def _summary_rows(results, fmt=_fmt, span: int = 5) -> list[dict]:
    """Agrégats du ménage par tranche de `span` années."""
    start = results[0].year
    buckets: dict[int, list] = {}
    for r in results:
        buckets.setdefault((r.year - start) // span, []).append(r)
    rows = []
    for group in buckets.values():
        first, last = group[0], group[-1]
        alive = [(r, p) for r in group for p in r.persons if p.alive]
        persons = [p for _, p in alive]
        tax = sum(p.tax_total + p.oas_clawback for p in persons)
        taxable = sum(p.taxable_income for p in persons)
        ages = " / ".join(
            f"{a.age}→{b.age}" for a, b in zip(first.persons, last.persons) if a.alive)
        rows.append({
            "period": f"{first.year}–{last.year}" if first is not last else str(first.year),
            "ages": ages,
            "salary": fmt(sum(p.salary + p.part_time_income + p.rental_income for p in persons)),
            "benefits": fmt(sum(p.rrq + p.oas + p.gis + p.refundable_credits for p in persons)),
            "pensions": fmt(sum(p.db_pension + p.annuity_income for p in persons)),
            "registered": fmt(sum(p.wd_reer + p.wd_ferr + p.wd_frv for p in persons)),
            "free": fmt(sum(p.wd_celi + p.wd_taxable for p in persons)),
            "savings": fmt(sum(_savings(p) for p in persons)),
            "tax": fmt(tax),
            "rate": f"{tax / taxable:.1%}" if taxable > 1 else "—",
            "net": fmt(sum(r.net_cash for r in group)),
            "expenses": fmt(sum(r.target_net for r in group)),
            "shortfall": fmt(sum(max(0.0, -r.target_gap) for r in group)),
            "wealth": fmt(last.total_wealth),
            "net_worth": fmt(last.net_worth),
        })
    return rows


def _summary_table(results):
    ui.label("Sommaire par tranche de 5 ans").classes("font-bold mt-4")
    ui.label("Flux cumulés sur la période; soldes à la fin de la période.") \
        .classes("text-sm text-gray-500")
    _cash_flow_table(SUMMARY_COLUMNS, _summary_rows(results))


BALANCE_SHEET_COLUMNS = _columns([
    ("year", "Année", "Année civile (soldes à la fin de l'année)."),
    ("ages", "Âges", "Âge de chaque personne à la fin de l'année."),
    ("registered", "Enregistré imposable", "REER + CRI + FERR + FRV : 100 % imposable au décès."),
    ("tax_free", "CELI / CELIAPP", "Comptes libres d'impôt."),
    ("nonreg", "Non-enregistré", "Valeur marchande du compte non enregistré."),
    ("gain", "dont gain latent", "Gain non réalisé du compte non enregistré (imposable à 50 % lors de la vente)."),
    ("wealth", "Total placements", "Somme de tous les comptes financiers."),
    ("real_assets", "Immobilier", "Valeur des actifs réels (résidence, chalet, immeubles)."),
    ("insurance", "Assurance vie", "Capitaux-décès en vigueur (versés libres d'impôt au décès)."),
    ("debts", "Dettes", "Solde total des dettes."),
    ("net_worth", "Valeur nette", "Placements + immobilier − dettes (exclut l'assurance vie)."),
    ("death_tax", "Impôt au décès", "Impôt sur la disposition réputée si tous décédaient cette année."),
    ("net_estate", "Succession nette", "Valeur brute + assurance − impôt au décès − dettes."),
])


def _balance_sheet_rows(results, estates, fmt=_fmt) -> list[dict]:
    estate_by_year = {e.year: e for e in estates}
    rows = []
    for r in results:
        alive = [p for p in r.persons if p.alive]
        e = estate_by_year.get(r.year)
        rows.append({
            "year": r.year,
            "ages": " / ".join(str(p.age) for p in alive),
            "registered": fmt(sum(p.bal_reer + p.bal_cri + p.bal_ferr + p.bal_frv for p in alive)),
            "tax_free": fmt(sum(p.bal_celi + p.bal_celiapp for p in alive)),
            "nonreg": fmt(sum(p.bal_taxable for p in alive)),
            "gain": fmt(sum(p.taxable_unrealized_gain for p in alive)),
            "wealth": fmt(r.total_wealth),
            "real_assets": fmt(r.real_assets_value),
            "insurance": fmt(r.insurance_in_force),
            "debts": fmt(r.debts_balance),
            "net_worth": fmt(r.net_worth),
            "death_tax": fmt(e.tax_at_death) if e else "—",
            "net_estate": fmt(e.net_estate) if e else "—",
        })
    return rows


def _balance_sheet_table(results, estates):
    ui.label("Bilan annuel (actif / passif)").classes("font-bold mt-4")
    ui.label("Soldes à la fin de chaque année; la succession suppose le décès de tous cette année-là.") \
        .classes("text-sm text-gray-500")
    _cash_flow_table(BALANCE_SHEET_COLUMNS, _balance_sheet_rows(results, estates))


def _pct(x: float) -> str:
    return f"{x * 100:.2f} %"


def _kv_table(rows: list[tuple[str, str]]):
    """Table libellé/valeur; les lignes dont le libellé commence par « = » sont en gras."""
    table = ui.table(
        columns=[{"name": "k", "label": "", "field": "k", "align": "left"},
                 {"name": "v", "label": "", "field": "v", "align": "right"}],
        rows=[{"k": k, "v": v} for k, v in rows], pagination=False) \
        .classes("w-full").props("dense flat bordered hide-header hide-bottom separator=horizontal")
    table.add_slot("body-cell", '''
<q-td :props="props" :class="props.row.k.startsWith('=') ? 'font-bold' : ''">
  {{ props.value }}
</q-td>''')
    return table


def _level_block(level):
    ui.label(level.label).classes("font-bold mt-2")
    bracket_rows = [{
        "range": (f"{_fmt(b.lower)} à {_fmt(b.upper)}" if b.upper is not None
                  else f"plus de {_fmt(b.lower)}"),
        "rate": _pct(b.rate), "amount": _fmt(b.amount), "tax": _fmt(b.tax),
    } for b in level.brackets if b.amount > 0.005]
    ui.table(columns=[
        {"name": "range", "label": "Tranche (indexée)", "field": "range", "align": "left"},
        {"name": "rate", "label": "Taux", "field": "rate", "align": "right"},
        {"name": "amount", "label": "Revenu imposé", "field": "amount", "align": "right"},
        {"name": "tax", "label": "Impôt", "field": "tax", "align": "right"},
    ], rows=bracket_rows, pagination=False).classes("w-full").props("dense flat bordered hide-bottom")
    rows = [("Impôt brut (somme des tranches)", _fmt(level.gross_tax))]
    rows += [(f"  {label}", _fmt(value)) for label, value in level.credits]
    rows += [
        (f"Crédits non remboursables (montants × {_pct(level.credit_rate)} + crédits en $)",
         "− " + _fmt(level.non_refundable_credits)),
    ]
    if level.dividend_credits > 0.005:
        rows.append(("Crédit d'impôt pour dividendes", "− " + _fmt(level.dividend_credits)))
    if level.abatement > 0.005:
        rows.append(("Abattement du Québec (16,5 %)", "− " + _fmt(level.abatement)))
    if level.refundable_credits > 0.005:
        rows.append(("Crédits remboursables (versés en sus)", _fmt(level.refundable_credits)))
    rows.append(("= Impôt net à payer", _fmt(level.net_tax)))
    _kv_table(rows)


def _render_tax_sheet(sheet, name: str):
    ui.label(f"Feuille d'impôt {sheet.year} — {name}, {sheet.age} ans — "
             f"barèmes indexés × {sheet.price_factor:.3f}").classes("font-bold")
    for w in sheet.warnings:
        ui.label(f"⚠️ {w}").classes("text-sm text-negative")
    with ui.row().classes("w-full gap-6 flex-wrap items-start"):
        with ui.column().classes("w-full lg:w-[48%] gap-1"):
            ui.label("Revenus").classes("font-bold")
            rows = [(label, _fmt(v)) for label, v in sheet.income_lines]
            rows.append(("= Revenu ordinaire (entrée du calcul)", _fmt(sheet.ordinary_income)))
            if abs(sheet.unexplained_income) > 1:
                rows.append(("  dont écart non détaillé", _fmt(sheet.unexplained_income)))
            if sheet.dividends_received > 0.005:
                rows += [("Dividendes reçus", _fmt(sheet.dividends_received)),
                         ("  Dividendes majorés (imposables)", _fmt(sheet.dividends_grossed_up))]
            if sheet.capital_gains > 0.005:
                rows += [("Gains en capital réalisés", _fmt(sheet.capital_gains)),
                         ("  Gains imposables (50 %)", _fmt(sheet.taxable_capital_gains))]
            rows += [
                ("= Revenu total", _fmt(sheet.total_income)),
                ("Déductions (REER, CELIAPP…)", "− " + _fmt(sheet.deductions)),
                ("= Revenu net", _fmt(sheet.net_income)),
                ("= Revenu imposable", _fmt(sheet.taxable_income)),
                ("Revenu de pension admissible (crédit)", _fmt(sheet.eligible_pension_income)),
            ]
            if sheet.family_net_income is not None:
                rows.append(("Revenu familial net (crédits QC)", _fmt(sheet.family_net_income)))
            if sheet.lives_alone:
                rows.append(("Personne vivant seule", "oui"))
            _kv_table(rows)

            ui.label("Sommaire").classes("font-bold mt-2")
            _kv_table([
                ("Impôt fédéral net", _fmt(sheet.federal.net_tax)),
                ("Impôt provincial net", _fmt(sheet.provincial.net_tax)),
                ("= Impôt total", _fmt(sheet.total_tax)),
                (f"Récupération SV (seuil {_fmt(sheet.oas_clawback_threshold)})",
                 _fmt(sheet.oas_clawback)),
                ("Crédits remboursables reçus", _fmt(sheet.refundable_credits)),
                ("Taux effectif (impôt + récup. SV) / revenu imposable", _pct(sheet.effective_rate)),
                ("Taux marginal (100 $ de revenu ordinaire de plus)", _pct(sheet.marginal_rate)),
            ])
        with ui.column().classes("w-full lg:w-[48%] gap-1"):
            _level_block(sheet.federal)
            _level_block(sheet.provincial)


def _tax_sheet_panel(results, names: list[str], province: str, start_year: int):
    ui.label("Feuille d'impôt détaillée").classes("font-bold mt-4")
    ui.label("Déclaration simplifiée reconstituée à partir du calcul exact utilisé par la "
             "simulation (après fractionnement). À comparer avec un calculateur externe "
             "ou une déclaration réelle.").classes("text-sm text-gray-500")
    by_year = {r.year: r for r in results}
    selection = {"year": results[0].year, "person": 0}
    area = ui.column().classes("w-full")

    def render():
        area.clear()
        hr = by_year[selection["year"]]
        i = selection["person"]
        with area:
            try:
                sheet = build_tax_sheet(hr, i, province, start_year)
            except ValueError as exc:
                ui.label(str(exc)).classes("text-gray-500")
                return
            _render_tax_sheet(sheet, names[i] or f"Personne {i + 1}")

    def set_year(e):
        selection["year"] = int(e.value)
        render()

    def set_person(e):
        selection["person"] = int(e.value)
        render()

    with ui.row().classes("gap-4 items-end"):
        ui.select([r.year for r in results], value=selection["year"], label="Année",
                  on_change=set_year).props("dense outlined").classes("w-32")
        if len(names) > 1:
            ui.select({i: (n or f"Personne {i + 1}") for i, n in enumerate(names)},
                      value=0, label="Personne", on_change=set_person) \
                .props("dense outlined").classes("w-48")
    render()


def _signed(x: float) -> str:
    return ("+" if x > 0 else "") + _fmt(x)


# Cotisations par compte: (champ, libellé, infobulle)
_CONTRIB_FIELDS = [
    ("contrib_reer", "REER", "Cotisation à son propre REER (déductible)."),
    ("contrib_spousal_reer", "REER du conjoint",
     "Cotisation versée par cette personne au REER de son conjoint (déductible pour elle)."),
    ("contrib_celi", "CELI", "Cotisation au CELI, incluant le surplus de retraite réinvesti."),
    ("contrib_celiapp", "CELIAPP", "Cotisation au CELIAPP (déductible)."),
    ("contrib_taxable", "Non enregistré",
     "Placement non enregistré, incluant l'excédent CELI redirigé et le surplus réinvesti."),
    ("contrib_dc_employee", "Régime CD — employé", "Part de l'employé au régime à cotisations déterminées (CRI)."),
    ("contrib_dc_employer", "Régime CD — employeur", "Part de l'employeur (n'est pas un décaissement)."),
]


def _active_contrib_fields(results, persons_filter=None) -> list[tuple[str, str, str]]:
    def people(r):
        return [p for i, p in enumerate(r.persons) if persons_filter is None or i == persons_filter]
    return [(f, l, t) for f, l, t in _CONTRIB_FIELDS
            if any(getattr(p, f) > 1 for r in results for p in people(r))]


def _contributions_chart(results) -> go.Figure:
    years = [r.year for r in results]
    fig = go.Figure()
    _add_stacked_bars(fig, years, [
        (label, [sum(getattr(p, f) for p in r.persons) for r in results])
        for f, label, _ in _CONTRIB_FIELDS])
    room = [sum(p.celi_room for p in r.persons if p.alive) for r in results]
    if any(v > 1 for v in room):
        fig.add_trace(go.Scatter(name="Droits CELI inutilisés (fin d'année)", x=years, y=room,
                                 mode="lines", line=dict(color="black", dash="dot"), yaxis="y2"))
    fig.update_layout(
        barmode="stack", title="Cotisations annuelles par compte",
        yaxis2=dict(overlaying="y", side="right", showgrid=False, rangemode="tozero"),
        **_CHART_LAYOUT)
    return fig


def _contribution_rows(results, person_index=None, fmt=_fmt) -> list[dict]:
    fields = _active_contrib_fields(results, person_index)
    rows, cumul = [], 0.0
    for r in results:
        persons = [p for i, p in enumerate(r.persons)
                   if p.alive and (person_index is None or i == person_index)]
        if not persons:
            continue
        total = sum(getattr(p, f) for f, _, _ in fields for p in persons)
        cumul += total
        salary = sum(p.salary + p.part_time_income for p in persons)
        row = {"year": r.year, "ages": " / ".join(str(p.age) for p in persons),
               "salary": fmt(salary),
               **{f: fmt(sum(getattr(p, f) for p in persons)) for f, _, _ in fields},
               "total": fmt(total), "cumul": fmt(cumul),
               "rate": f"{total / salary:.1%}" if salary > 1 else "—",
               "reinvested": fmt(r.reinvested) if person_index is None else "—",
               "reer_room": fmt(sum(p.reer_room for p in persons)),
               "celi_room": fmt(sum(p.celi_room for p in persons))}
        rows.append(row)
    return rows


def _contribution_columns(fields) -> list[dict]:
    cols = _columns([
        ("year", "Année", "Année civile."),
        ("ages", "Âges", "Âge à la fin de l'année."),
        ("salary", "Revenu d'emploi", "Salaire et emploi à temps partiel (base du taux d'épargne)."),
    ])
    cols += _columns([(f, l, t) for f, l, t in fields])
    cols += _columns([
        ("total", "Total cotisé", "Somme des cotisations de l'année (part employeur incluse)."),
        ("rate", "Taux d'épargne", "Total cotisé ÷ revenu d'emploi."),
        ("reinvested", "dont surplus réinvesti", "À la retraite: excédent sur la cible placé au CELI puis au non-enregistré."),
        ("cumul", "Cumul", "Cotisations cumulées depuis le début de la projection."),
        ("reer_room", "Droits REER restants", "Droits de cotisation REER inutilisés à la fin de l'année."),
        ("celi_room", "Droits CELI restants", "Droits de cotisation CELI inutilisés à la fin de l'année."),
    ])
    return cols


def _contributions_panel(results, names: list[str]):
    ui.label("Cotisations et placements").classes("font-bold mt-4")
    ui.label("Ce que vous placez chaque année dans chaque compte, le taux d'épargne et les droits "
             "de cotisation qui restent inutilisés.").classes("text-sm text-gray-500")
    all_fields = _active_contrib_fields(results)
    totals = {label: sum(getattr(p, f) for r in results for p in r.persons) for f, label, _ in all_fields}
    accumulation = [r for r in results if any(p.salary > 0 for p in r.persons)]
    salaries = sum(p.salary + p.part_time_income for r in accumulation for p in r.persons)
    saved = sum(getattr(p, f) for r in accumulation for f, _, _ in all_fields for p in r.persons)
    with ui.row().classes("gap-4 flex-wrap"):
        cards = [("Total cotisé à vie", _fmt(sum(totals.values())))]
        cards += [(label, _fmt(v)) for label, v in totals.items()]
        cards.append(("Taux d'épargne moyen (accumulation)",
                      f"{saved / salaries:.1%}" if salaries > 1 else "—"))
        cards.append(("Surplus réinvesti à la retraite", _fmt(sum(r.reinvested for r in results))))
        for title, value in cards:
            with ui.card().classes("min-w-40"):
                ui.label(title).classes("text-xs text-gray-500")
                ui.label(value).classes("text-lg font-bold text-primary")
    ui.plotly(_contributions_chart(results)).classes("w-full")

    selection = {"who": None}

    def set_who(e):
        selection["who"] = None if e.value == "hh" else int(e.value)
        render()

    if len(names) > 1:
        options = {"hh": "Ménage", **{i: (n or f"Personne {i + 1}") for i, n in enumerate(names)}}
        ui.select(options, value="hh", label="Vue", on_change=set_who) \
            .props("dense outlined").classes("w-48")
    area = ui.column().classes("w-full")

    def render():
        area.clear()
        who = selection["who"]
        fields = _active_contrib_fields(results, who)
        with area:
            _cash_flow_table(_contribution_columns(fields), _contribution_rows(results, who))

    render()


def _journal_panel(results):
    ui.label("Journal des décisions du simulateur").classes("font-bold mt-4")
    ui.label("Pour chaque année: conversions, minimums obligatoires, besoin à financer, ordre "
             "de retrait appliqué (demandé vs disponible par compte), fractionnement, surplus "
             "réinvesti, événements (vente, rente, décès). Les années où la cible n'est pas "
             "atteinte sont marquées ⚠️.").classes("text-sm text-gray-500")
    filters = {"text": "", "only_flagged": False}
    area = ui.column().classes("w-full gap-1")

    def render():
        area.clear()
        needle = filters["text"].strip().lower()
        with area:
            shown = 0
            for r in results:
                alive = [p for p in r.persons if p.alive]
                if not alive:
                    continue
                lines = [d for d in r.decisions if not needle or needle in d.lower()]
                flagged = r.target_gap < -500
                if (needle and not lines) or (filters["only_flagged"] and not flagged):
                    continue
                shown += 1
                ages = " / ".join(str(p.age) for p in alive)
                title = f"{'⚠️ ' if flagged else ''}{r.year} — {ages} ans — {len(lines)} entrées"
                with ui.expansion(title, value=bool(needle) or flagged).classes("w-full"):
                    for d in lines:
                        indent = d.startswith("  ")
                        ui.label(d.strip()).classes(
                            "text-sm" + (" ml-6 text-gray-700" if indent else "")
                            + (" text-negative" if d.startswith("⚠️") else ""))
            if not shown:
                ui.label("Aucune entrée ne correspond au filtre.").classes("text-gray-500")

    def set_text(e):
        filters["text"] = e.value or ""
        render()

    def set_flagged(e):
        filters["only_flagged"] = bool(e.value)
        render()

    with ui.row().classes("gap-4 items-end"):
        ui.input("Filtrer (ex.: FERR, fractionnement, vente)", on_change=set_text) \
            .props("dense outlined clearable debounce=300").classes("w-80")
        ui.switch("Seulement les années sous la cible", on_change=set_flagged)
    render()


def _verification_panel(verification):
    v = verification
    failed = v.failed_checks
    applicable = [c for c in v.checks if c.applicable]
    ui.label("Vérification de la projection").classes("font-bold mt-4")
    ui.label("Contrôles automatiques reconstruits à partir des résultats: cohérence interne, "
             "règles légales, preuve de caisse et rendement implicite de chaque compte.") \
        .classes("text-sm text-gray-500")
    with ui.row().classes("gap-4 flex-wrap"):
        for title, value, color in [
                ("Contrôles", f"{len(applicable) - len(failed)} / {len(applicable)} réussis",
                 "text-positive" if not failed else "text-negative"),
                ("Preuve de caisse", f"{sum(1 for r in v.cash_proof if r.balanced)} / "
                 f"{len(v.cash_proof)} années bouclées", "text-primary"),
                ("Rendements", f"{sum(1 for r in v.roll_forward if r.consistent)} / "
                 f"{len(v.roll_forward)} lignes dans la fourchette", "text-primary")]:
            with ui.card().classes("min-w-56"):
                ui.label(title).classes("text-xs text-gray-500")
                ui.label(value).classes(f"text-xl font-bold {color}")

    # --- invariants ---
    ui.label("Contrôles d'invariants").classes("font-bold mt-2")
    for c in v.checks:
        icon = "—" if not c.applicable else ("✅" if c.passed else "❌")
        header = f"{icon} {c.name}" + (f" ({len(c.failures)})" if c.failures else "")
        if c.failures:
            with ui.expansion(header).classes("w-full"):
                ui.label(c.description).classes("text-sm text-gray-500")
                for f in c.failures[:25]:
                    ui.label(f).classes("text-sm text-negative")
                if len(c.failures) > 25:
                    ui.label(f"… et {len(c.failures) - 25} autres").classes("text-sm text-gray-500")
        else:
            with ui.row().classes("items-center gap-2"):
                ui.label(header).classes("text-sm" + ("" if c.applicable else " text-gray-400"))
                ui.label(c.description).classes("text-xs text-gray-500")

    # --- preuve de caisse ---
    ui.label("Preuve de caisse annuelle").classes("font-bold mt-4")
    ui.label("Revenus + retraits + SRG + crédits − cotisations − primes − impôts − récup. SV "
             "= net encaissé; net encaissé − cible = écart (surplus réinvesti ou insuffisance).") \
        .classes("text-sm text-gray-500")
    in_keys = list(v.cash_proof[0].inflows) if v.cash_proof else []
    out_keys = list(v.cash_proof[0].outflows) if v.cash_proof else []
    active_in = [k for k in in_keys if any(r.inflows[k] > 1 for r in v.cash_proof)]
    active_out = [k for k in out_keys if any(r.outflows[k] > 1 for r in v.cash_proof)]
    columns = [{"name": "year", "label": "Année", "field": "year", "align": "right",
                "tooltip": "Année civile."}]
    columns += [{"name": f"in{i}", "label": k, "field": f"in{i}", "align": "right",
                 "tooltip": "Entrée de fonds."} for i, k in enumerate(active_in)]
    columns += [{"name": f"out{i}", "label": "− " + k, "field": f"out{i}", "align": "right",
                 "tooltip": "Sortie de fonds."} for i, k in enumerate(active_out)]
    columns += [
        {"name": "explained", "label": "= Net calculé", "field": "explained", "align": "right",
         "tooltip": "Somme des entrées moins les sorties."},
        {"name": "reported", "label": "Net encaissé", "field": "reported", "align": "right",
         "tooltip": "Valeur rapportée par la simulation."},
        {"name": "diff", "label": "Écart", "field": "diff", "align": "right",
         "tooltip": "Net encaissé − net calculé (doit être 0)."},
        {"name": "target", "label": "Cible", "field": "target", "align": "right",
         "tooltip": "Cible de l'année (dépenses spéciales seulement en accumulation)."},
        {"name": "gap", "label": "Net − cible", "field": "gap", "align": "right",
         "tooltip": "Positif = surplus réinvesti; négatif = insuffisance."},
        {"name": "reinv", "label": "Réinvesti", "field": "reinv", "align": "right",
         "tooltip": "Surplus placé dans le CELI puis le non-enregistré."},
    ]
    rows = []
    for r in v.cash_proof:
        row = {"year": r.year, "explained": _fmt(r.explained_net), "reported": _fmt(r.reported_net),
               "diff": ("✓" if r.balanced else "⚠️ " + _signed(r.difference)),
               "target": _fmt(r.target), "gap": _signed(r.gap), "reinv": _fmt(r.reinvested)}
        row.update({f"in{i}": _fmt(r.inflows[k]) for i, k in enumerate(active_in)})
        row.update({f"out{i}": _fmt(r.outflows[k]) for i, k in enumerate(active_out)})
        rows.append(row)
    _cash_flow_table(columns, rows)

    # --- roll-forward ---
    ui.label("Rapprochement des soldes (roll-forward)").classes("font-bold mt-4")
    ui.label("Ouverture + cotisations + rendement − retraits ± transferts = fermeture. Le rendement "
             "est déduit et son taux comparé aux hypothèses nettes de frais (± 0,25 pt). "
             "REER/FERR et CRI/FRV sont regroupés (conversions internes).") \
        .classes("text-sm text-gray-500")
    groups = [g for g in dict.fromkeys(r.group for r in v.roll_forward)]
    selection = {"group": groups[0] if groups else None}
    area = ui.column().classes("w-full")

    def render_rf():
        area.clear()
        rows = []
        for r in v.roll_forward:
            if r.group != selection["group"]:
                continue
            rate = f"{r.implied_rate:.2%}" if r.implied_rate is not None else "—"
            rows.append({
                "year": r.year, "open": _fmt(r.opening), "contrib": _fmt(r.contributions),
                "ret": _signed(r.implied_return), "wd": _fmt(r.withdrawals),
                "tr": _signed(r.transfers) if abs(r.transfers) > 0.5 else "",
                "close": _fmt(r.closing),
                "rate": ("✓ " if r.consistent else "⚠️ ") + rate,
                "exp": (f"{r.expected_rate_low:.2%}" if r.expected_rate_low == r.expected_rate_high
                        else f"{r.expected_rate_low:.2%} – {r.expected_rate_high:.2%}")
                if r.expected_rate_low is not None else "—",
                "note": r.note,
            })
        with area:
            _cash_flow_table([
                {"name": "year", "label": "Année", "field": "year", "align": "right", "tooltip": ""},
                {"name": "open", "label": "Ouverture", "field": "open", "align": "right",
                 "tooltip": "Solde de fin de l'année précédente (+ capital-décès reçu en début d'année)."},
                {"name": "contrib", "label": "+ Cotisations", "field": "contrib", "align": "right",
                 "tooltip": "Cotisations de l'année, y compris le surplus réinvesti et la part employeur."},
                {"name": "ret", "label": "+ Rendement (déduit)", "field": "ret", "align": "right",
                 "tooltip": "Fermeture − ouverture − cotisations + retraits − transferts."},
                {"name": "wd", "label": "− Retraits", "field": "wd", "align": "right",
                 "tooltip": "Retraits de l'année (minimums, solveur, fonte du REER)."},
                {"name": "tr", "label": "± Transferts", "field": "tr", "align": "right",
                 "tooltip": "Produit de vente d'actif (+), prime de rente viagère (−)."},
                {"name": "close", "label": "= Fermeture", "field": "close", "align": "right",
                 "tooltip": "Solde de fin d'année."},
                {"name": "rate", "label": "Taux implicite", "field": "rate", "align": "right",
                 "tooltip": "Rendement déduit ÷ ouverture."},
                {"name": "exp", "label": "Taux attendu", "field": "exp", "align": "right",
                 "tooltip": "Hypothèse nette de frais (et ajustée à la retraite / au choc du scénario)."},
                {"name": "note", "label": "Note", "field": "note", "align": "left", "tooltip": ""},
            ], rows)

    def set_group(e):
        selection["group"] = e.value
        render_rf()

    if groups:
        ui.select(groups, value=groups[0], label="Groupe de comptes", on_change=set_group) \
            .props("dense outlined").classes("w-56")
        render_rf()


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
                    "- **Net encaissé** : total après impôts de tous les revenus, "
                    "retraits, SRG et crédits remboursables — c'est ce montant qui "
                    "doit couvrir la colonne **Dépenses**.\n"
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
                summary_tab = ui.tab("Sommaire 5 ans")
                balance_tab = ui.tab("Bilan")
                contrib_tab = ui.tab("Cotisations")
                tax_sheet_tab = ui.tab("Feuille d'impôt")
                verification = verify(results, estates, hh, scen)
                verif_tab = ui.tab("Vérification" if not verification.failed_checks
                                   else f"⚠️ Vérification ({len(verification.failed_checks)})")
                journal_tab = ui.tab("Journal")
            with ui.tab_panels(cash_flow_tabs, value=household_tab).classes("w-full"):
                with ui.tab_panel(household_tab):
                    _year_table(results)
                for i, person_tab in enumerate(person_tabs):
                    with ui.tab_panel(person_tab):
                        _person_detail_table(results, i, state["persons"][i]["name"])
                with ui.tab_panel(summary_tab):
                    _summary_table(results)
                with ui.tab_panel(balance_tab):
                    _balance_sheet_table(results, estates)
                with ui.tab_panel(contrib_tab):
                    _contributions_panel(results, names)
                with ui.tab_panel(tax_sheet_tab):
                    _tax_sheet_panel(results, names, hh.province, scen.start_year)
                with ui.tab_panel(verif_tab):
                    _verification_panel(verification)
                with ui.tab_panel(journal_tab):
                    _journal_panel(results)
            ui.label("Analyse détaillée").classes("text-lg font-bold mt-2")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                ui.plotly(_wealth_chart(results)).classes("w-full lg:w-[48%]")
                ui.plotly(_tax_chart(results, estates)).classes("w-full lg:w-[48%]")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                ui.plotly(_withdrawals_chart(results)).classes("w-full lg:w-[48%]")
                ui.plotly(_gap_chart(results)).classes("w-full lg:w-[48%]")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                ui.plotly(_tax_rate_chart(results, names)).classes("w-full lg:w-[48%]")
                ui.plotly(_benefits_chart(results)).classes("w-full lg:w-[48%]")
            with ui.row().classes("w-full gap-4 flex-wrap"):
                ui.plotly(_wealth_mix_chart(results)).classes("w-full lg:w-[48%]")
                if estates:
                    ui.plotly(_estate_chart(results, estates)).classes("w-full lg:w-[48%]")

    with ui.row().classes("items-center gap-4"):
        ui.button("🚀 Lancer la simulation", on_click=run_simulation) \
            .props("size=lg color=primary")
        ui.label("Simulation complète: impôts réels, fractionnement optimal, "
                 "SRG, dettes et actifs.").classes("text-gray-500")
    container = ui.column().classes("w-full gap-4")
