# app.py
from models.person import Person
from models.household import Household
from models.reer import REER
from models.celi import CELI
from models.cri import CRI
from models.taxable import Taxable
from services.contributions import ContributionInput
from engine.simulator import run_scenario
from data.fiscal_tables import FiscalQC
from project_io.export import export_json, export_csv
from models.special_projects import SpecialProject

def main():
    primary = Person(
        name="Alex",
        birth_year=1960,
        province="QC",
        salary=90000,
        retirement_year=2025,
        marital_status="couple",
        rrq_start_age=65,
        oas_start_age=65,
    )
    spouse = Person(
        name="Sam",
        birth_year=1962,
        province="QC",
        salary=50000,
        retirement_year=2027,
        marital_status="couple",
        rrq_start_age=65,
        oas_start_age=65,
    )
    hh = Household(primary=primary, spouse=spouse)

    accounts_primary = {
        "REER": REER(name="REER", balance=200000, annual_return=0.05),
        "CELI": CELI(name="CELI", balance=50000, annual_return=0.05),
        "CRI":  CRI(name="CRI",  balance=80000,  annual_return=0.05),
        "Taxable": Taxable(name="Taxable", balance=100000, annual_return=0.04,
                           interest_ratio=0.4, eligible_dividend_ratio=0.3, capital_gain_ratio=0.3),
    }
    accounts_spouse = {
        "REER": REER(name="REER", balance=120000, annual_return=0.05),
        "CELI": CELI(name="CELI", balance=40000, annual_return=0.05),
        "CRI":  CRI(name="CRI",  balance=60000,  annual_return=0.05),
        "Taxable": Taxable(name="Taxable", balance=60000, annual_return=0.04,
                           interest_ratio=0.5, eligible_dividend_ratio=0.2, capital_gain_ratio=0.3),
    }

    contrib_primary = ContributionInput(
        reer_pct=0.10, reer_fixed=2000.0,
        cri_pct=0.05,  cri_fixed=0.0,
        celi_fixed=6500.0
    )
    contrib_spouse = ContributionInput(
        reer_pct=0.08, reer_fixed=1500.0,
        cri_pct=0.03,  cri_fixed=0.0,
        celi_fixed=6500.0
    )

    fiscal = FiscalQC()

    # Projets spéciaux
    projects = [
        SpecialProject(year=2026, amount=15000.0, person="household", description="Rénovation cuisine"),
        SpecialProject(year=2028, amount=12000.0, person="primary", description="Voyage"),
        SpecialProject(year=2029, amount=8000.0, person="spouse", description="Voiture"),
    ]

    # Cible ménage (rente nette)
    net_target_household = 90000.0

    results = run_scenario(
        household=hh,
        accounts_primary=accounts_primary,
        accounts_spouse=accounts_spouse,
        fiscal=fiscal,
        start_year=2024,
        end_year=2035,
        contrib_primary=contrib_primary,
        contrib_spouse=contrib_spouse,
        split_ratio=0.5,
        net_income_target_household=net_target_household,
        projects=projects,
        use_spousal_age_for_ferr_primary=True,
        use_spousal_age_for_ferr_spouse=True
    )

    for row in results[:6]:
        print(row)

    export_json(results, "retirement_couple_target_projects.json")
    export_csv(results, "retirement_couple_target_projects.csv")
    print("Exports écrits: retirement_couple_target_projects.json, retirement_couple_target_projects.csv")

if __name__ == "__main__":
    main()