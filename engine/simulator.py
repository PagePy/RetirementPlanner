# engine/simulator.py (personne seule)
from .timeline import YearContext
from services.contributions import apply_contributions, ContributionInput, CarryForward
from services.validation import validate_inputs
from services.taxes import compute_taxes_person_qc as compute_taxes_qc
from services.conversions import convert_reer_to_ferr, convert_cri_to_frv
from services.withdrawals import apply_ferr_mandatory_withdrawal, apply_frv_min_withdrawal
from services.decumulation import withdraw_to_meet_net_target
from services.stress import StressParams, apply_return_shocks, unexpected_expense_for_year, is_person_deceased, inflate_value
from models.pension_rrq import RRQ
from models.pension_oas import OAS
from models.pension_srg import SRG
from models.taxable import Taxable

def run_scenario(person, accounts, fiscal, start_year: int, end_year: int,
                 contrib_plan: ContributionInput, net_income_target: float = None,
                 use_spousal_age_for_ferr: bool = False, spouse_age_for_ferr: int = None,
                 stress: StressParams = None):
    carry = CarryForward()
    validate_inputs(person, contrib_plan)

    rrq = RRQ(start_age=person.rrq_start_age)
    oas = OAS(start_age=person.oas_start_age)
    srg = SRG()

    results = []
    for year in range(start_year, end_year + 1):
        yc = YearContext(year, person, accounts, fiscal, carry)
        age = person.age_in_year(year)

        # Décès prématuré: si décédé, on fige le salaire et bloque contributions/retraits/prestations
        deceased = is_person_deceased(year, stress, target="primary")

        # Index salaire si vivant et pas retraité
        if year > start_year and not person.is_retired(year) and not deceased:
            person.salary *= (1 + person.salary_growth)

        # Appliquer chocs de rendement avant croissance
        apply_return_shocks(year, accounts, stress)

        # Croissance des comptes
        yc.grow_accounts()

        # Conversions
        if not deceased and age == 71 and "REER" in accounts:
            convert_reer_to_ferr(accounts, owner_age=age, use_spousal_age=use_spousal_age_for_ferr)
        if not deceased and person.is_retired(year) and "CRI" in accounts:
            convert_cri_to_frv(accounts, owner_age=age, province=person.province)

        # Cotisations avant retraite si vivant
        contrib_res = {}
        if not person.is_retired(year) and not deceased:
            contrib_res = apply_contributions(person, accounts, contrib_plan, carry, fiscal)

        # Retraits minimaux si vivant et retraité
        ferr_withdrawal = frv_withdrawal = 0.0
        if person.is_retired(year) and not deceased:
            ferr_withdrawal = apply_ferr_mandatory_withdrawal(
                accounts, person_age=age, spouse_age=spouse_age_for_ferr, use_spousal_age=use_spousal_age_for_ferr
            )
            frv_withdrawal = apply_frv_min_withdrawal(accounts, person_age=age)

        # Prestations publiques (indexées par inflation si fourni)
        years_since_rrq_start = max(0, year - (person.birth_year + person.rrq_start_age))
        rrq_base = rrq.indexed_annual_benefit(age, years_since_rrq_start) if age >= rrq.start_age and not deceased else 0.0
        rrq_benefit = inflate_value(rrq_base, stress.inflation_rate if stress else 0.0, 0)

        years_since_oas_start = max(0, year - (person.birth_year + person.oas_start_age))
        oas_base = oas.indexed_annual_benefit(age, years_since_oas_start) if age >= oas.start_age and not deceased else 0.0
        oas_benefit = inflate_value(oas_base, stress.inflation_rate if stress else 0.0, 0)

        # Revenus placements non enregistrés (composantes)
        interest = eligible_dividends = capital_gains = 0.0
        if "Taxable" in accounts and isinstance(accounts["Taxable"], Taxable):
            comp = accounts["Taxable"].annual_taxable_components()
            interest = comp["interest"]
            eligible_dividends = comp["eligible_dividends"]
            capital_gains = comp["capital_gains"]

        # SRG (approx, indexé par inflation)
        income_for_srg = max(0.0, ferr_withdrawal + frv_withdrawal + rrq_benefit + oas_benefit + interest + eligible_dividends + 0.5 * capital_gains)
        years_since_srg_start = max(0, year - (person.birth_year + 65))
        srg_base = srg.indexed_annual_benefit(age, income_for_srg, years_since_srg_start) if not deceased else 0.0
        srg_benefit = inflate_value(srg_base, stress.inflation_rate if stress else 0.0, 0)

        # Clawback OAS
        estimated_net_income_for_clawback = (
            (person.salary if not person.is_retired(year) and not deceased else 0.0)
            + ferr_withdrawal + frv_withdrawal + rrq_benefit + oas_benefit
            + interest + eligible_dividends + 0.5 * capital_gains
        )
        oas_clawback = oas.clawback(estimated_net_income_for_clawback)

        # Impôts (avant retraits optionnels)
        pension_income_for_credit = ferr_withdrawal + frv_withdrawal
        income_breakdown = {
            "employment": person.salary if not person.is_retired(year) and not deceased else 0.0,
            "pension": pension_income_for_credit,
            "interest": interest,
            "eligible_dividends": eligible_dividends,
            "capital_gains": capital_gains,
            "oas": oas_benefit - oas_clawback,
            "rrq": rrq_benefit,
        }
        tax_res = compute_taxes_qc(income_breakdown, fiscal, pension_income_for_credit=pension_income_for_credit, oas_clawback=oas_clawback)

        # Dépenses imprévues
        unexpected = unexpected_expense_for_year(year, stress)

        net_before_optional = (
            income_breakdown["employment"] + pension_income_for_credit + rrq_benefit + (oas_benefit - oas_clawback) + srg_benefit
            + interest + eligible_dividends + 0.5 * capital_gains
            - tax_res.net_tax
            - unexpected
        )

        # Objectif de rente nette: retirer pour atteindre la cible (si vivant)
        optional_withdrawals = {"Taxable": 0.0, "FERR": 0.0, "FRV": 0.0, "REER": 0.0, "CELI": 0.0}
        if person.is_retired(year) and net_income_target is not None and net_before_optional < net_income_target and not deceased:
            optional_withdrawals = withdraw_to_meet_net_target(
                target_net_income=net_income_target + unexpected,
                current_net_before_optional=net_before_optional,
                accounts=accounts,
                taxes_fn=compute_taxes_qc,
                fiscal=fiscal,
                income_context=income_breakdown,
                max_iterations=20
            )

        net_after_optional = net_before_optional \
            + optional_withdrawals["Taxable"] \
            + optional_withdrawals["FERR"] \
            + optional_withdrawals["FRV"] \
            + optional_withdrawals["REER"] \
            + optional_withdrawals["CELI"]

        results.append({
            "year": year,
            "age": age,
            "retired": person.is_retired(year),
            "deceased": deceased,
            "salary": round(person.salary, 2),
            "balances": {k: round(v.balance, 2) for k, v in accounts.items()},
            "contributions": contrib_res,
            "withdrawals": {
                "mandatory": {"FERR": round(ferr_withdrawal, 2), "FRV": round(frv_withdrawal, 2)},
                "optional": {k: round(v, 2) for k, v in optional_withdrawals.items()},
            },
            "benefits": {
                "RRQ": round(rrq_benefit, 2),
                "OAS": round(oas_benefit, 2),
                "SRG": round(srg_benefit, 2),
                "OAS_clawback": round(oas_clawback, 2),
            },
            "investment_income": {
                "interest": round(interest, 2),
                "eligible_dividends": round(eligible_dividends, 2),
                "capital_gains": round(capital_gains, 2),
            },
            "taxes": tax_res.__dict__,
            "stress": {
                "inflation_rate": (stress.inflation_rate if stress else 0.0),
                "unexpected_expense": round(unexpected, 2),
                "return_shocks_applied": (stress.return_shocks.get(year) if (stress and stress.return_shocks) else None),
            },
            "net_income": {
                "before_optional": round(net_before_optional, 2),
                "after_optional": round(net_after_optional, 2),
                "target": net_income_target,
            },
        })

    return results