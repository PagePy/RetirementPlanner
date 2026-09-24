"""Rapport client PDF (reportlab) avec graphiques Plotly rendus via kaleido."""
from __future__ import annotations

from datetime import date
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle)

from gui.pages import resultats_page as rp
from planner.core.data_status import warning_message

_styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=_styles["Title"], fontSize=22, spaceAfter=12)
H2 = ParagraphStyle("H2", parent=_styles["Heading2"], spaceBefore=10, spaceAfter=6)
BODY = ParagraphStyle("Body", parent=_styles["BodyText"], fontSize=9, leading=12)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=7.5, leading=9.5,
                       textColor=colors.HexColor("#555555"))
CENTER = ParagraphStyle("Center", parent=BODY, alignment=TA_CENTER)
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=7, leading=8.5)

_TABLE_COLUMNS = [
    ("year", "Année"), ("ages", "Âges"), ("salary", "Revenu gagné"),
    ("db", "Rentes PD"), ("rrq", "RRQ"), ("oas", "SV"), ("minimums", "Min. FERR/FRV"),
    ("registered", "Enregistré"), ("celi", "CELI"), ("nonreg", "Non enr."),
    ("other", "SRG/créd."), ("tax", "Impôts"), ("expenses", "Dépenses"),
    ("shortfall", "Insuff."), ("total_bal", "Total placements"),
]


def _fmt(x: float) -> str:
    return rp._fmt(x)


def _pct(x: float) -> str:
    return f"{x * 100:.2f} %"


def _fig_image(fig, width_cm: float = 24.0, height_px: int = 420) -> Image:
    png = fig.to_image(format="png", width=1200, height=height_px, scale=1)
    img = Image(BytesIO(png))
    ratio = height_px / 1200
    img.drawWidth = width_cm * cm
    img.drawHeight = width_cm * cm * ratio
    return img


def _grid(data: list[list], col_widths=None, header: bool = True) -> Table:
    t = Table(data, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#BBBBBB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                  ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]
    t.setStyle(TableStyle(style))
    return t


def _assumptions(state: dict, hh, scen) -> list:
    rows = [["Paramètre", "Valeur"]]
    rows += [
        ["Année de départ", str(scen.start_year)],
        ["Inflation", _pct(scen.inflation)],
        ["Cible de revenu net du ménage", _fmt(hh.target_net_income)
         + (" (indexée)" if hh.target_indexed else " (fixe)")],
        ["Stratégie CELI", {"dernier": "en dernier recours", "jamais": "jamais"}
         .get(hh.celi_strategy, hh.celi_strategy)],
        ["Ordre de décaissement", " → ".join(hh.withdrawal_order)],
    ]
    if hh.taxable_income_floor:
        rows.append(["Plancher de revenu imposable (fonte REER)",
                     _fmt(hh.taxable_income_floor) + " / personne"])
    if hh.is_couple:
        rows.append(["Partage de la rente RRQ", "oui" if hh.rrq_sharing else "non"])
        rows.append(["Minimum FERR sur l'âge du conjoint",
                     "oui" if hh.use_spouse_age_for_ferr else "non"])
    out = [Paragraph("Hypothèses du ménage", H2), _grid(rows, [8 * cm, 12 * cm])]

    for p in hh.persons:
        a = p.accounts
        rows = [["Paramètre", "Valeur"],
                ["Naissance / retraite",
                 (f"{p.birth_month:02d}/{p.birth_year} / {p.retirement_age} ans"
                  + (f" (départ mois {p.retirement_month})" if p.retirement_month else "")
                  if p.birth_month else
                  f"{p.birth_year} / {p.retirement_age} ans"
                  + (f" (mois {p.retirement_month})" if p.retirement_month > 1 else ""))],
                ["Espérance de vie", f"{p.life_expectancy} ans"],
                ["Salaire / croissance", f"{_fmt(p.salary)} / {_pct(p.salary_growth)}"],
                ["RRQ à 65 ans / début", f"{_fmt(p.rrq_monthly_at_65)} par mois / {p.rrq_start_age} ans"],
                ["SV début", f"{p.oas_start_age} ans"],
                ["Rendements REER / CELI / non-enr.",
                 f"{_pct(a.reer_return)} / {_pct(a.celi_return)} / {_pct(a.taxable_return)}"],
                ["Frais de gestion / ajustement retraite",
                 f"{_pct(a.fee_rate)} / {_pct(a.retirement_return_delta)}"],
                ["Soldes REER / CELI / CRI / non-enr.",
                 f"{_fmt(a.reer_balance)} / {_fmt(a.celi_balance)} / "
                 f"{_fmt(a.cri_balance)} / {_fmt(a.taxable_balance)}"]]
        if p.db_from_statement:
            rows.append(["Rente PD (relevé)",
                         f"{_pct(p.db_accrual_rate)} × {p.db_service_years:.2f} ans de service "
                         f"× moyenne {p.db_avg_years} ans (relevé: {_fmt(p.db_avg_salary)}), "
                         f"dès {p.db_start_age} ans"])
        elif p.db_pension > 0:
            rows.append(["Rente PD", f"{_fmt(p.db_pension)} dès {p.db_start_age} ans ({p.db_status})"])
        if p.part_time_income > 0:
            rows.append(["Emploi après retraite",
                         f"{_fmt(p.part_time_income)} jusqu'à {p.part_time_until_age} ans"])
        out += [Paragraph(f"Hypothèses — {p.name}", H2), _grid(rows, [8 * cm, 12 * cm])]
    return out


def _key_results(results, estates) -> list:
    retired = [r for r in results if any(p.retired for p in r.persons if p.alive)]
    shortfalls = [r for r in retired if r.target_gap < -500]
    fees = sum(r.total_fees for r in results)
    rows = [["Indicateur", "Valeur"],
            ["Plan", "Réussi" if not shortfalls
             else f"{len(shortfalls)} année(s) sous la cible"],
            ["Impôt total à vie (incl. récupération SV)", _fmt(sum(r.total_tax for r in results))],
            ["SRG total reçu", _fmt(sum(p.gis for r in results for p in r.persons))],
            ["Patrimoine financier final", _fmt(results[-1].total_wealth)],
            ["Valeur nette finale", _fmt(results[-1].net_worth)],
            ["Succession nette finale (après impôt au décès)",
             _fmt(estates[-1].net_estate) if estates else "—"],
            ["Dernière année simulée", str(results[-1].year)]]
    if fees > 0:
        rows.append(["Frais de gestion à vie", _fmt(fees)])
    out = [Paragraph("Résultats clés", H2), _grid(rows, [10 * cm, 10 * cm])]
    if shortfalls:
        out.append(Paragraph("Années où la cible n'est pas atteinte", H2))
        for r in shortfalls[:15]:
            out.append(Paragraph(f"{r.year}: {r.shortfall_note or 'cible non atteinte'}", BODY))
    return out


def _year_table(results) -> Table:
    balance_fields = rp._active_balance_fields(results)
    rows = rp._year_rows(results, balance_fields, fmt=lambda x: f"{x:,.0f}".replace(",", " "))
    keys = [k for k, _ in _TABLE_COLUMNS]
    data = [[Paragraph(label, CELL) for _, label in _TABLE_COLUMNS]]
    for row in rows:
        data.append([str(row.get(k, "")) for k in keys])
    widths = [1.3 * cm, 1.6 * cm] + [1.7 * cm] * (len(keys) - 2)
    return _grid(data, widths)


def build_pdf(state: dict, hh, scen, results, estates) -> bytes:
    """Construit le rapport complet; retourne les octets du PDF."""
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=landscape(letter),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        title=f"Plan de retraite — {state.get('profile_name', '')}")
    names = " et ".join(p.name for p in hh.persons)
    story = [
        Spacer(1, 3 * cm),
        Paragraph("Plan de retraite", H1),
        Paragraph(names, ParagraphStyle("N", parent=H1, fontSize=16)),
        Paragraph(f"Profil « {state.get('profile_name', '')} » — "
                  f"préparé le {date.today():%Y-%m-%d}", CENTER),
        Spacer(1, 1 * cm),
    ]
    warning = warning_message(scen.start_year, hh.province)
    if warning:
        story.append(Paragraph(f"<b>Avertissement.</b> {warning}.", CENTER))
    story += [
        Spacer(1, 2 * cm),
        Paragraph(
            "Ce document est une projection fondée sur les hypothèses indiquées; "
            "il ne constitue pas un conseil financier, fiscal ou juridique. Les "
            "résultats varieront selon les rendements réels, l'inflation, la "
            "législation et votre situation personnelle.", SMALL),
        PageBreak(),
    ]
    story += _key_results(results, estates)
    story.append(PageBreak())
    story += _assumptions(state, hh, scen)
    story.append(PageBreak())
    story += [Paragraph("Sources de revenus et cible", H2),
              _fig_image(rp._income_chart(results)), PageBreak(),
              Paragraph("Évolution du patrimoine", H2),
              _fig_image(rp._wealth_chart(results)), PageBreak(),
              Paragraph("Impôts annuels et succession nette", H2),
              _fig_image(rp._tax_chart(results, estates)), PageBreak(),
              Paragraph("Projection annuelle du ménage", H2),
              Paragraph("Montants en dollars courants de chaque année. « Enregistré » = "
                        "retraits REER + FERR/FRV au-delà du minimum; « SRG/créd. » = "
                        "Supplément de revenu garanti et crédits remboursables.", SMALL),
              Spacer(1, 0.3 * cm),
              _year_table(results)]
    doc.build(story)
    return buf.getvalue()
