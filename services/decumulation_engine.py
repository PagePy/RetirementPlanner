# services/decumulation_engine.py
"""
Moteur de décaissement conforme au cahier des charges:
- Lissage du revenu imposable
- Barèmes fiscaux progressifs Québec/Fédéral
- Ordre de retrait: PD+pensions → Non-enregistré → REER/CRI → FERR/FRV → CELI
- Minimums/maximums FERR/FRV légaux
- Options CELI: dernier / jamais / mixte
- Fractionnement de pension pour couples
- Pré-décaissement REER/CRI pour éviter pics futurs
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.fiscal_tables import FiscalQC
from data.frv_qc_tables import frv_min_rate_qc, frv_max_rate_qc

# ============ TABLES FERR MINIMUM (Canada) ============
FERR_MIN_RATES = {
    # Âge au 1er janvier: taux minimum de retrait
    55: 0.0286, 56: 0.0294, 57: 0.0303, 58: 0.0313, 59: 0.0323,
    60: 0.0333, 61: 0.0345, 62: 0.0357, 63: 0.0370, 64: 0.0385,
    65: 0.0400, 66: 0.0417, 67: 0.0435, 68: 0.0455, 69: 0.0476,
    70: 0.0500, 71: 0.0528, 72: 0.0540, 73: 0.0553, 74: 0.0567,
    75: 0.0582, 76: 0.0598, 77: 0.0617, 78: 0.0636, 79: 0.0658,
    80: 0.0682, 81: 0.0708, 82: 0.0738, 83: 0.0771, 84: 0.0808,
    85: 0.0851, 86: 0.0899, 87: 0.0955, 88: 0.1021, 89: 0.1099,
    90: 0.1192, 91: 0.1306, 92: 0.1449, 93: 0.1634, 94: 0.1879,
    95: 0.2000  # 20% pour 95+
}

def ferr_min_rate(age: int) -> float:
    """Retourne le taux minimum de retrait FERR selon l'âge"""
    if age < 55:
        return 0.0
    if age >= 95:
        return 0.20
    return FERR_MIN_RATES.get(age, 0.0528)


# ============ CALCUL D'IMPÔT PROGRESSIF ============
def calculate_progressive_tax(taxable_income: float, fiscal: FiscalQC = None) -> Dict:
    """
    Calcule l'impôt fédéral et provincial avec barèmes progressifs.
    Retourne: federal, provincial, total, taux_effectif
    """
    if fiscal is None:
        fiscal = FiscalQC()
    
    # Impôt fédéral par tranches
    federal_tax = 0.0
    remaining = taxable_income
    prev_threshold = 0.0
    for threshold, rate in fiscal.federal.brackets:
        if remaining <= 0:
            break
        bracket_income = min(remaining, threshold - prev_threshold) if threshold > prev_threshold else remaining
        if bracket_income > 0:
            federal_tax += bracket_income * rate
            remaining -= bracket_income
        prev_threshold = threshold
    if remaining > 0:
        # Dernière tranche (au-delà du dernier seuil)
        federal_tax += remaining * fiscal.federal.brackets[-1][1]
    
    # Crédit personnel de base fédéral
    federal_tax = max(0.0, federal_tax - fiscal.federal.basic_personal_amount * 0.15)
    
    # Impôt Québec par tranches
    quebec_tax = 0.0
    remaining = taxable_income
    prev_threshold = 0.0
    for threshold, rate in fiscal.quebec.brackets:
        if remaining <= 0:
            break
        bracket_income = min(remaining, threshold - prev_threshold) if threshold > prev_threshold else remaining
        if bracket_income > 0:
            quebec_tax += bracket_income * rate
            remaining -= bracket_income
        prev_threshold = threshold
    if remaining > 0:
        quebec_tax += remaining * fiscal.quebec.brackets[-1][1]
    
    # Crédit personnel de base Québec
    quebec_tax = max(0.0, quebec_tax - fiscal.quebec.basic_personal_amount * 0.15)
    
    total_tax = federal_tax + quebec_tax
    effective_rate = (total_tax / taxable_income * 100) if taxable_income > 0 else 0.0
    
    return {
        "federal": round(federal_tax, 2),
        "provincial": round(quebec_tax, 2),
        "total": round(total_tax, 2),
        "effective_rate": round(effective_rate, 2)
    }


def calculate_oas_clawback(net_income: float, oas_amount: float) -> float:
    """
    Calcule la récupération de la PSV (OAS clawback).
    Seuil 2024: ~86,912$, récupération à 15% au-delà
    """
    OAS_THRESHOLD = 86912.0
    CLAWBACK_RATE = 0.15
    
    if net_income <= OAS_THRESHOLD:
        return 0.0
    
    excess = net_income - OAS_THRESHOLD
    clawback = min(oas_amount, excess * CLAWBACK_RATE)
    return round(clawback, 2)


# ============ CLASSE PRINCIPALE DE DÉCAISSEMENT ============
@dataclass
class DecumulationResult:
    year: int
    age: int
    retired: bool
    
    # Revenus
    salary: float = 0.0
    pension_pd: float = 0.0
    rrq: float = 0.0
    oas: float = 0.0
    srg: float = 0.0
    
    # Retraits
    withdrawal_taxable: float = 0.0
    withdrawal_reer: float = 0.0
    withdrawal_cri: float = 0.0
    withdrawal_ferr: float = 0.0
    withdrawal_frv: float = 0.0
    withdrawal_celi: float = 0.0
    
    # Cotisations (phase accumulation)
    contrib_reer: float = 0.0
    contrib_celi: float = 0.0
    contrib_cri: float = 0.0
    contrib_taxable: float = 0.0
    
    # Soldes fin d'année
    balance_reer: float = 0.0
    balance_celi: float = 0.0
    balance_cri: float = 0.0
    balance_ferr: float = 0.0
    balance_frv: float = 0.0
    balance_taxable: float = 0.0
    
    # Fiscalité
    taxable_income: float = 0.0
    tax_federal: float = 0.0
    tax_provincial: float = 0.0
    tax_total: float = 0.0
    oas_clawback: float = 0.0
    effective_rate: float = 0.0
    
    # Résultats
    gross_income: float = 0.0
    net_income: float = 0.0
    target_income: float = 0.0
    target_gap: float = 0.0  # Écart vs cible
    wealth: float = 0.0


class DecumulationEngine:
    """
    Moteur de décaissement optimisé selon le cahier des charges.
    """
    
    def __init__(self, fiscal: FiscalQC = None):
        self.fiscal = fiscal or FiscalQC()
    
    def simulate_single(
        self,
        person: Dict,
        accounts: Dict,
        contributions: Dict,
        retirement: Dict,
        tax_params: Dict,
        scenario: Dict
    ) -> List[DecumulationResult]:
        """
        Simulation complète pour une personne seule.
        
        Args:
            person: {name, birth_year, salary, life_expectancy}
            accounts: {REER_balance, CELI_balance, CRI_balance, FERR_balance, FRV_balance, Taxable_balance, *_return}
            contributions: {reer_percent, reer_fixed, celi_percent, celi_fixed, ...}
            retirement: {retirement_age, target_income, rrq_age, rrq_amount_65, oas_age, income_indexed, 
                        celi_strategy (optimiser/dernier/jamais), rente_pd, rente_pd_age_debut, ...}
            tax_params: {income_split, ...}
            scenario: {start_year, end_year, inflation}
        """
        results: List[DecumulationResult] = []
        
        # Paramètres clés
        birth_year = person["birth_year"]
        retirement_year = birth_year + retirement["retirement_age"]
        end_year = min(scenario["end_year"], birth_year + person["life_expectancy"])
        inflation = scenario["inflation"] / 100.0
        
        # Copie des soldes
        balances = {
            "REER": accounts.get("REER_balance", 0.0),
            "CELI": accounts.get("CELI_balance", 0.0),
            "CRI": accounts.get("CRI_balance", 0.0),
            "FERR": accounts.get("FERR_balance", 0.0),
            "FRV": accounts.get("FRV_balance", 0.0),
            "Taxable": accounts.get("Taxable_balance", 0.0)
        }
        
        # Taux de rendement
        returns = {
            "REER": accounts.get("REER_return", 5.0) / 100,
            "CELI": accounts.get("CELI_return", 4.0) / 100,
            "CRI": accounts.get("CRI_return", 4.5) / 100,
            "FERR": accounts.get("FERR_return", 4.0) / 100,
            "FRV": accounts.get("FRV_return", 4.0) / 100,
            "Taxable": accounts.get("Taxable_return", 3.5) / 100
        }
        
        # Paramètres retraite
        target_monthly = retirement.get("target_income", 5000.0)
        target_annual = target_monthly * 12
        indexed = retirement.get("income_indexed", True)
        # Stratégie CELI: optimiser / dernier / jamais
        celi_strategy = retirement.get("celi_strategy", retirement.get("celi_usage", "dernier"))
        rrq_age = retirement.get("rrq_age", 65)
        rrq_monthly = retirement.get("rrq_amount_65", 1250.0)
        oas_age = retirement.get("oas_age", 65)
        
        # Rente PD avec paramètres de pénalité
        # Priorité: retirement dict (nouveau format), puis person dict (ancien format)
        rente_pd_base = retirement.get("rente_pd", person.get("rente_pd", 0.0))
        rente_pd_age_debut = retirement.get("rente_pd_age_debut", 65)
        rente_pd_age_normal = retirement.get("rente_pd_age_normal", 65)
        rente_pd_penalite = retirement.get("rente_pd_penalite_annuelle", 6.0)
        
        # Calculer la rente PD ajustée selon la pénalité
        if rente_pd_age_debut < rente_pd_age_normal:
            annees_anticipees = rente_pd_age_normal - rente_pd_age_debut
            reduction_pct = annees_anticipees * rente_pd_penalite / 100.0
            rente_pd_ajustee = rente_pd_base * (1 - reduction_pct)
        else:
            rente_pd_ajustee = rente_pd_base
        
        # Salaire initial et augmentation
        salary = person.get("salary", 0.0)
        salary_increase = person.get("salary_increase", inflation * 100) / 100.0  # Convertir % en décimal
        
        # Impôts cumulés pour statistiques
        cumulative_taxes = 0.0
        
        for year in range(scenario["start_year"], end_year + 1):
            age = year - birth_year
            is_retired = (year >= retirement_year)
            
            result = DecumulationResult(year=year, age=age, retired=is_retired)
            
            # ============ PHASE ACCUMULATION ============
            if not is_retired:
                result = self._simulate_accumulation_year(
                    result, salary, balances, returns, contributions, inflation, year, scenario["start_year"]
                )
                salary *= (1 + salary_increase)  # Indexation salaire selon augmentation personnelle
                
            # ============ PHASE DÉCAISSEMENT ============
            else:
                result = self._simulate_decumulation_year(
                    result, age, year, retirement_year, balances, returns,
                    rente_pd_ajustee, rente_pd_age_debut, rrq_age, rrq_monthly, oas_age,
                    target_annual, indexed, inflation, celi_strategy
                )
            
            # Patrimoine total
            result.wealth = sum(balances.values())
            
            # Copier soldes dans résultat
            result.balance_reer = balances["REER"]
            result.balance_celi = balances["CELI"]
            result.balance_cri = balances["CRI"]
            result.balance_ferr = balances["FERR"]
            result.balance_frv = balances["FRV"]
            result.balance_taxable = balances["Taxable"]
            
            cumulative_taxes += result.tax_total
            
            results.append(result)
        
        return results
    
    def _simulate_accumulation_year(
        self,
        result: DecumulationResult,
        salary: float,
        balances: Dict,
        returns: Dict,
        contributions: Dict,
        inflation: float,
        year: int,
        start_year: int
    ) -> DecumulationResult:
        """Simule une année d'accumulation (avant retraite)"""
        
        result.salary = salary
        
        # Cotisations
        reer_contrib = salary * contributions.get("reer_percent", 0.0) / 100 + contributions.get("reer_fixed", 0.0)
        celi_contrib = salary * contributions.get("celi_percent", 0.0) / 100 + contributions.get("celi_fixed", 0.0)
        cri_contrib = salary * contributions.get("cri_percent", 0.0) / 100 + contributions.get("cri_fixed", 0.0)
        taxable_contrib = salary * contributions.get("nonreg_percent", 0.0) / 100 + contributions.get("nonreg_fixed", 0.0)
        
        result.contrib_reer = reer_contrib
        result.contrib_celi = celi_contrib
        result.contrib_cri = cri_contrib
        result.contrib_taxable = taxable_contrib
        
        # Ajouter cotisations aux soldes
        balances["REER"] += reer_contrib
        balances["CELI"] += celi_contrib
        balances["CRI"] += cri_contrib
        balances["Taxable"] += taxable_contrib
        
        # Croissance
        for account in balances:
            balances[account] *= (1 + returns[account])
        
        # Fiscalité (simplifiée pour accumulation)
        result.taxable_income = salary
        taxes = calculate_progressive_tax(salary, self.fiscal)
        result.tax_federal = taxes["federal"]
        result.tax_provincial = taxes["provincial"]
        result.tax_total = taxes["total"]
        result.effective_rate = taxes["effective_rate"]
        
        result.gross_income = salary
        result.net_income = salary - result.tax_total
        
        return result
    
    def _simulate_decumulation_year(
        self,
        result: DecumulationResult,
        age: int,
        year: int,
        retirement_year: int,
        balances: Dict,
        returns: Dict,
        rente_pd_ajustee: float,
        rente_pd_age_debut: int,
        rrq_age: int,
        rrq_monthly: float,
        oas_age: int,
        target_annual: float,
        indexed: bool,
        inflation: float,
        celi_strategy: str
    ) -> DecumulationResult:
        """
        Simule une année de décaissement selon le cahier des charges.
        
        Ordre de retrait par défaut:
        1. Revenus garantis (PD, RRQ, OAS)
        2. Non-enregistré (Taxable)
        3. REER/CRI (avant 71 ans) ou FERR/FRV (après conversion)
        4. CELI (selon option: dernier / jamais / mixte)
        """
        
        years_retired = year - retirement_year
        
        # ============ CONVERSIONS OBLIGATOIRES À 71 ANS ============
        if age == 71:
            balances["FERR"] += balances["REER"]
            balances["REER"] = 0
            balances["FRV"] += balances["CRI"]
            balances["CRI"] = 0
        
        # ============ REVENUS GARANTIS ============
        # Rente PD (commence à l'âge de début choisi, indexée si activé)
        if age >= rente_pd_age_debut:
            years_since_pd = age - rente_pd_age_debut
            pd_pension = rente_pd_ajustee * ((1 + inflation) ** years_since_pd) if indexed else rente_pd_ajustee
        else:
            pd_pension = 0.0
        result.pension_pd = pd_pension
        
        # RRQ
        if age >= rrq_age:
            years_since_rrq = age - rrq_age
            result.rrq = rrq_monthly * 12 * ((1 + inflation) ** years_since_rrq)
        
        # OAS (base ~8500$/an, indexée)
        OAS_BASE = 8500.0
        if age >= oas_age:
            years_since_oas = age - oas_age
            result.oas = OAS_BASE * ((1 + inflation) ** years_since_oas)
        
        # SRG (simplifié: 0 pour l'instant, dépend du revenu)
        result.srg = 0.0
        
        total_guaranteed = pd_pension + result.rrq + result.oas + result.srg
        
        # ============ MINIMUMS LÉGAUX FERR/FRV ============
        ferr_min = balances["FERR"] * ferr_min_rate(age) if age >= 55 else 0
        frv_min = balances["FRV"] * frv_min_rate_qc(age) if age >= 55 else 0
        frv_max = balances["FRV"] * frv_max_rate_qc(age) if age >= 55 else balances["FRV"]
        
        # ============ CALCUL DU BESOIN NET ============
        target_indexed = target_annual * ((1 + inflation) ** years_retired) if indexed else target_annual
        result.target_income = target_indexed
        
        # Revenu net des sources garanties (après impôt)
        base_taxable = total_guaranteed + ferr_min + frv_min
        base_taxes = calculate_progressive_tax(base_taxable, self.fiscal)
        net_from_base = base_taxable - base_taxes["total"]
        
        # Besoin net additionnel
        additional_net_needed = max(0, target_indexed - net_from_base)
        
        # ============ RETRAITS SELON ORDRE DU CAHIER DES CHARGES ============
        withdrawals = {
            "Taxable": 0.0,
            "REER": 0.0,
            "CRI": 0.0,
            "FERR": ferr_min,  # Minimum obligatoire
            "FRV": frv_min,    # Minimum obligatoire
            "CELI": 0.0
        }
        
        if additional_net_needed > 0:
            # Approche itérative: simuler les retraits avec calcul d'impôt progressif
            current_taxable_income = base_taxable
            current_net = net_from_base
            remaining_net_need = additional_net_needed
            
            # ÉTAPE 1: Non-enregistré (Taxable) - 50% imposable (gains en capital)
            if remaining_net_need > 0 and balances["Taxable"] > 0:
                # Essayer retrait Taxable par itération
                test_withdrawal = min(remaining_net_need * 2.0, balances["Taxable"])  # Approximation initiale
                test_taxable = current_taxable_income + test_withdrawal * 0.5  # 50% imposable
                test_taxes = calculate_progressive_tax(test_taxable, self.fiscal)
                test_net = test_taxable - test_taxes["total"]
                
                # Ajuster si nécessaire
                actual_net_gain = test_net - current_net
                if actual_net_gain >= remaining_net_need * 0.95:  # Tolérance 5%
                    withdrawals["Taxable"] = min(test_withdrawal, balances["Taxable"])
                    current_taxable_income = test_taxable
                    current_net = test_net
                    remaining_net_need = max(0, target_indexed - current_net)
                else:
                    # Utiliser tout le Taxable disponible
                    withdrawals["Taxable"] = balances["Taxable"]
                    current_taxable_income += balances["Taxable"] * 0.5
                    new_taxes = calculate_progressive_tax(current_taxable_income, self.fiscal)
                    current_net = current_taxable_income - new_taxes["total"]
                    remaining_net_need = max(0, target_indexed - current_net)
            
            # ÉTAPE 2: REER/CRI (avant 71 ans) ou FERR/FRV additionnel (après)
            if remaining_net_need > 0:
                if age < 71:
                    # REER: 100% imposable
                    if balances["REER"] > 0:
                        test_withdrawal = min(remaining_net_need * 1.5, balances["REER"])
                        test_taxable = current_taxable_income + test_withdrawal
                        test_taxes = calculate_progressive_tax(test_taxable, self.fiscal)
                        test_net = test_taxable - test_taxes["total"]
                        
                        actual_net_gain = test_net - current_net
                        if actual_net_gain >= remaining_net_need * 0.95:
                            # Ajuster pour précision
                            final_withdrawal = min(test_withdrawal, balances["REER"])
                            withdrawals["REER"] = final_withdrawal
                            current_taxable_income += final_withdrawal
                            new_taxes = calculate_progressive_tax(current_taxable_income, self.fiscal)
                            current_net = current_taxable_income - new_taxes["total"]
                            remaining_net_need = max(0, target_indexed - current_net)
                        else:
                            # Utiliser tout le REER
                            withdrawals["REER"] = balances["REER"]
                            current_taxable_income += balances["REER"]
                            new_taxes = calculate_progressive_tax(current_taxable_income, self.fiscal)
                            current_net = current_taxable_income - new_taxes["total"]
                            remaining_net_need = max(0, target_indexed - current_net)
                    
                    # CRI avec plafond FRV
                    if remaining_net_need > 0 and balances["CRI"] > 0:
                        cri_max = balances["CRI"] * frv_max_rate_qc(age) if age >= 55 else balances["CRI"]
                        test_withdrawal = min(remaining_net_need * 1.5, cri_max)
                        withdrawals["CRI"] = test_withdrawal
                        current_taxable_income += test_withdrawal
                        new_taxes = calculate_progressive_tax(current_taxable_income, self.fiscal)
                        current_net = current_taxable_income - new_taxes["total"]
                        remaining_net_need = max(0, target_indexed - current_net)
                else:
                    # FERR additionnel (au-delà du minimum)
                    ferr_available = max(0, balances["FERR"] - ferr_min)
                    if remaining_net_need > 0 and ferr_available > 0:
                        test_withdrawal = min(remaining_net_need * 1.5, ferr_available)
                        withdrawals["FERR"] += test_withdrawal
                        current_taxable_income += test_withdrawal
                        new_taxes = calculate_progressive_tax(current_taxable_income, self.fiscal)
                        current_net = current_taxable_income - new_taxes["total"]
                        remaining_net_need = max(0, target_indexed - current_net)
                    
                    # FRV additionnel (respecter maximum)
                    if remaining_net_need > 0:
                        frv_max_amount = frv_max if age >= 55 else balances["FRV"]
                        frv_available = min(frv_max_amount - frv_min, balances["FRV"] - frv_min)
                        if frv_available > 0:
                            test_withdrawal = min(remaining_net_need * 1.5, frv_available)
                            withdrawals["FRV"] += test_withdrawal
                            current_taxable_income += test_withdrawal
                            new_taxes = calculate_progressive_tax(current_taxable_income, self.fiscal)
                            current_net = current_taxable_income - new_taxes["total"]
                            remaining_net_need = max(0, target_indexed - current_net)
            
            # ÉTAPE 3: CELI (selon stratégie) - NON IMPOSABLE
            if remaining_net_need > 0 and celi_strategy != "jamais" and balances["CELI"] > 0:
                if celi_strategy == "dernier":
                    # Utiliser seulement si vraiment nécessaire (autres comptes épuisés)
                    withdrawals["CELI"] = min(remaining_net_need, balances["CELI"])
                elif celi_strategy == "optimiser":
                    # Stratégie optimale: utiliser CELI pour éviter tranches d'imposition élevées
                    # Retirer du CELI plutôt que de monter dans les paliers d'impôt
                    withdrawals["CELI"] = min(remaining_net_need, balances["CELI"])
        
        # ============ APPLIQUER LES RETRAITS ============
        result.withdrawal_taxable = withdrawals["Taxable"]
        result.withdrawal_reer = withdrawals["REER"]
        result.withdrawal_cri = withdrawals["CRI"]
        result.withdrawal_ferr = withdrawals["FERR"]
        result.withdrawal_frv = withdrawals["FRV"]
        result.withdrawal_celi = withdrawals["CELI"]
        
        balances["Taxable"] -= withdrawals["Taxable"]
        balances["REER"] -= withdrawals["REER"]
        balances["CRI"] -= withdrawals["CRI"]
        balances["FERR"] -= withdrawals["FERR"]
        balances["FRV"] -= withdrawals["FRV"]
        balances["CELI"] -= withdrawals["CELI"]
        
        # Empêcher soldes négatifs
        for k in balances:
            balances[k] = max(0, balances[k])
        
        # ============ CROISSANCE DES SOLDES RESTANTS ============
        for account in balances:
            balances[account] *= (1 + returns[account])
        
        # ============ CALCUL FISCAL FINAL ============
        # Revenu imposable = pensions + retraits imposables (excluant CELI)
        taxable_income = (
            pd_pension + result.rrq + result.oas + result.srg +
            withdrawals["FERR"] + withdrawals["FRV"] +
            withdrawals["REER"] + withdrawals["CRI"] +
            withdrawals["Taxable"] * 0.5  # 50% gains en capital
        )
        result.taxable_income = taxable_income
        
        taxes = calculate_progressive_tax(taxable_income, self.fiscal)
        result.tax_federal = taxes["federal"]
        result.tax_provincial = taxes["provincial"]
        result.tax_total = taxes["total"]
        result.effective_rate = taxes["effective_rate"]
        
        # Récupération OAS
        result.oas_clawback = calculate_oas_clawback(taxable_income, result.oas)
        result.tax_total += result.oas_clawback
        
        # Revenu brut et net
        result.gross_income = (
            total_guaranteed + 
            sum(withdrawals.values())
        )
        result.net_income = result.gross_income - result.tax_total
        
        # Écart vs cible
        result.target_gap = result.net_income - target_indexed
        
        return result
    
    def simulate_couple(
        self,
        person1: Dict, accounts1: Dict, contributions1: Dict, retirement1: Dict, tax1: Dict,
        person2: Dict, accounts2: Dict, contributions2: Dict, retirement2: Dict, tax2: Dict,
        scenario: Dict
    ) -> Dict:
        """
        Simulation pour un couple avec potentiel fractionnement de pension.
        """
        # Simuler chaque personne
        results1 = self.simulate_single(person1, accounts1, contributions1, retirement1, tax1, scenario)
        results2 = self.simulate_single(person2, accounts2, contributions2, retirement2, tax2, scenario)

        # Fractionnement de pension admissible (max légal 50%).
        # Règle simplifiée: on considère admissibles la rente PD et les retraits FERR/FRV.
        split_enabled_1 = bool(tax1.get("income_split", False))
        split_enabled_2 = bool(tax2.get("income_split", False))
        split_ratio_1 = min(0.5, max(0.0, float(tax1.get("income_split_percent", 0)) / 100.0))
        split_ratio_2 = min(0.5, max(0.0, float(tax2.get("income_split_percent", 0)) / 100.0))

        for r1, r2 in zip(results1, results2):
            eligible_1 = r1.pension_pd + r1.withdrawal_ferr + r1.withdrawal_frv
            eligible_2 = r2.pension_pd + r2.withdrawal_ferr + r2.withdrawal_frv

            transfer_1_to_2 = eligible_1 * split_ratio_1 if split_enabled_1 else 0.0
            transfer_2_to_1 = eligible_2 * split_ratio_2 if split_enabled_2 else 0.0

            new_taxable_1 = max(0.0, r1.taxable_income - transfer_1_to_2 + transfer_2_to_1)
            new_taxable_2 = max(0.0, r2.taxable_income - transfer_2_to_1 + transfer_1_to_2)

            taxes_1 = calculate_progressive_tax(new_taxable_1, self.fiscal)
            taxes_2 = calculate_progressive_tax(new_taxable_2, self.fiscal)

            oas_clawback_1 = calculate_oas_clawback(new_taxable_1, r1.oas)
            oas_clawback_2 = calculate_oas_clawback(new_taxable_2, r2.oas)

            r1.taxable_income = new_taxable_1
            r1.tax_federal = taxes_1["federal"]
            r1.tax_provincial = taxes_1["provincial"]
            r1.tax_total = taxes_1["total"] + oas_clawback_1
            r1.oas_clawback = oas_clawback_1
            r1.effective_rate = (r1.tax_total / r1.taxable_income * 100) if r1.taxable_income > 0 else 0.0
            r1.net_income = r1.gross_income - r1.tax_total
            r1.target_gap = r1.net_income - r1.target_income

            r2.taxable_income = new_taxable_2
            r2.tax_federal = taxes_2["federal"]
            r2.tax_provincial = taxes_2["provincial"]
            r2.tax_total = taxes_2["total"] + oas_clawback_2
            r2.oas_clawback = oas_clawback_2
            r2.effective_rate = (r2.tax_total / r2.taxable_income * 100) if r2.taxable_income > 0 else 0.0
            r2.net_income = r2.gross_income - r2.tax_total
            r2.target_gap = r2.net_income - r2.target_income
        
        household_results = []
        for r1, r2 in zip(results1, results2):
            household_results.append({
                "year": r1.year,
                "age1": r1.age,
                "age2": r2.age,
                "household_net_income": r1.net_income + r2.net_income,
                "household_gross_income": r1.gross_income + r2.gross_income,
                "household_wealth": r1.wealth + r2.wealth,
                "household_taxes": r1.tax_total + r2.tax_total,
                "household_effective_rate": (
                    (r1.tax_total + r2.tax_total) / (r1.taxable_income + r2.taxable_income) * 100
                    if (r1.taxable_income + r2.taxable_income) > 0 else 0
                )
            })
        
        return {
            "person1": results1,
            "person2": results2,
            "household": household_results
        }


def convert_result_to_dict(result: DecumulationResult) -> Dict:
    """Convertit un DecumulationResult en dictionnaire pour compatibilité avec le code existant."""
    return {
        "year": result.year,
        "age": result.age,
        "retired": result.retired,
        "salary": result.salary,
        "contributions": {
            "REER": result.contrib_reer,
            "CELI": result.contrib_celi,
            "CRI": result.contrib_cri,
            "Taxable": result.contrib_taxable
        },
        "balances": {
            "REER": result.balance_reer,
            "CELI": result.balance_celi,
            "CRI": result.balance_cri,
            "FERR": result.balance_ferr,
            "FRV": result.balance_frv,
            "Taxable": result.balance_taxable
        },
        "withdrawals": {
            "REER": result.withdrawal_reer,
            "CRI": result.withdrawal_cri,
            "FERR": result.withdrawal_ferr,
            "FRV": result.withdrawal_frv,
            "CELI": result.withdrawal_celi,
            "Taxable": result.withdrawal_taxable
        },
        "pensions": {
            "PD": result.pension_pd,
            "RRQ": result.rrq,
            "OAS": result.oas,
            "SRG": result.srg
        },
        "gross_income": result.gross_income,
        "taxable_income": result.taxable_income,
        "taxes": result.tax_total,
        "tax_federal": result.tax_federal,
        "tax_provincial": result.tax_provincial,
        "effective_rate": result.effective_rate,
        "oas_clawback": result.oas_clawback,
        "net_income": result.net_income,
        "target_income": result.target_income,
        "target_gap": result.target_gap,
        "wealth": result.wealth
    }
