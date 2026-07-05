"""Fonctions de calcul exécutées hors du thread UI (picklables pour run.cpu_bound)."""
from planner.core.analysis import (
    estate_timeline, run_all_stress_tests, run_monte_carlo, compare_strategies)
from planner.core.goals import (
    required_annual_savings, achievable_retirement_age,
    sustainable_income, optimal_benefit_ages)
from planner.core.projects import (
    compare_down_payment_strategies, retirement_cost_of_project)
from planner.core.simulation import HouseholdSimulator


def simulate(hh, scen):
    return HouseholdSimulator(hh, scen).run()


def simulate_with_estate(hh, scen):
    results = HouseholdSimulator(hh, scen).run()
    estates = estate_timeline(results, hh.province)
    return results, estates


def monte_carlo(hh, scen, iterations, volatility):
    return run_monte_carlo(hh, scen, iterations=iterations,
                           return_volatility=volatility)


def stress_battery(hh, scen):
    return run_all_stress_tests(hh, scen)


def strategy_comparison(hh, scen):
    return compare_strategies(hh, scen)


def solve_goals(hh, scen):
    """Exécute les 3 solveurs principaux."""
    return {
        "sustainable": sustainable_income(hh, scen),
        "required_savings": required_annual_savings(hh, scen),
        "earliest_age": achievable_retirement_age(hh, scen),
    }


def benefit_ages(hh, scen):
    return optimal_benefit_ages(hh, scen)


def down_payment(annual_savings, years, marginal_rate, couple):
    return compare_down_payment_strategies(
        annual_savings, years, marginal_rate, couple=couple)


def project_cost(hh, scen, name, year, amount):
    return retirement_cost_of_project(hh, scen, name, year, amount)
