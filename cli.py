# cli.py
import argparse
from models.person import Person
from models.reer import REER
from models.celi import CELI
from models.cri import CRI
from models.taxable import Taxable
from services.contributions import ContributionInput
from engine.simulator import run_scenario
from data.fiscal_tables import FiscalQC
from services.stress import StressParams
from project_io.export import export_json, export_csv


def build_accounts():
    return {
        "REER": REER(name="REER", balance=200000, annual_return=0.05),
        "CELI": CELI(name="CELI", balance=50000, annual_return=0.05),
        "CRI":  CRI(name="CRI",  balance=80000,  annual_return=0.05),
        "Taxable": Taxable(name="Taxable", balance=100000, annual_return=0.04,
                           interest_ratio=0.4, eligible_dividend_ratio=0.3, capital_gain_ratio=0.3),
    }

def main():
    parser = argparse.ArgumentParser(description="Planificateur de retraite - Scénarios")
    parser.add_argument("--start", type=int, default=2024, help="Année de début")
    parser.add_argument("--end", type=int, default=2035, help="Année de fin")
    parser.add_argument("--salary", type=float, default=90000.0, help="Salaire initial")
    parser.add_argument("--retire", type=int, default=2025, help="Année de retraite")
    parser.add_argument("--net-target", type=float, default=None, help="Cible de rente nette annuelle")
    parser.add_argument("--inflation", type=float, default=0.02, help="Inflation (stress)")
    parser.add_argument("--shock-year", type=int, default=None, help="Année de choc de rendement")
    parser.add_argument("--shock-reer", type=float, default=None, help="Rendement REER choc (ex: -0.15)")
    parser.add_argument("--shock-taxable", type=float, default=None, help="Rendement Taxable choc (ex: -0.10)")
    parser.add_argument("--unexpected", type=str, default=None, help="Dépenses imprévues: format '2026:15000,2028:8000'")
    parser.add_argument("--death-year", type=int, default=None, help="Année de décès prématuré")
    parser.add_argument("--export", action="store_true", help="Exporter JSON/CSV")
    args = parser.parse_args()

    person = Person(
        name="Test",
        birth_year=1960,
        province="QC",
        salary=args.salary,
        retirement_year=args.retire,
        marital_status="single",
        rrq_start_age=65,
        oas_start_age=65,
    )

    accounts = build_accounts()
    contrib = ContributionInput(reer_pct=0.10, reer_fixed=2000.0, cri_pct=0.05, cri_fixed=0.0, celi_fixed=6500.0)
    fiscal = FiscalQC()

    # Construire stress params
    return_shocks = None
    if args.shock_year and (args.shock_reer is not None or args.shock_taxable is not None):
        return_shocks = {args.shock_year: {}}
        if args.shock_reer is not None:
            return_shocks[args.shock_year]["REER"] = args.shock_reer
        if args.shock_taxable is not None:
            return_shocks[args.shock_year]["Taxable"] = args.shock_taxable

    unexpected_expenses = None
    if args.unexpected:
        unexpected_expenses = {}
        for pair in args.unexpected.split(","):
            y, v = pair.split(":")
            unexpected_expenses[int(y)] = float(v)

    stress = StressParams(
        inflation_rate=args.inflation,
        return_shocks=return_shocks,
        unexpected_expenses=unexpected_expenses,
        premature_death_year=args.death_year,
        premature_death_person="primary" if args.death_year else None,
    )

    results = run_scenario(
        person=person,
        accounts=accounts,
        fiscal=fiscal,
        start_year=args.start,
        end_year=args.end,
        contrib_plan=contrib,
        net_income_target=args.net_target,
        use_spousal_age_for_ferr=False,
        spouse_age_for_ferr=None,
        stress=stress
    )

    for row in results[:6]:
        print(row)

    if args.export:
        export_json(results, "scenario_results.json")
        export_csv(results, "scenario_results.csv")
        print("Exports écrits: scenario_results.json, scenario_results.csv")

if __name__ == "__main__":
    main()