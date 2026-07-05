import streamlit as st
import pandas as pd
import json
from datetime import datetime
from ui_components.forms import (
    person_form, accounts_form, scenario_form, 
    contributions_form, retirement_form, tax_form, special_projects_form
)
from ui_components.storage import list_profiles, load_profile, save_profile
from ui_components.charts import plot_income, plot_wealth, plot_taxes, plot_comparison
from services.decumulation_engine import DecumulationEngine, convert_result_to_dict
from data.fiscal_tables import FiscalQC

# ==================== NORMALISATION CELI STRATEGY ====================
def _normalize_celi_strategy(value: str) -> str:
    """Convertit les valeurs d'affichage en codes internes pour celi_strategy."""
    if not value:
        return "dernier"
    v = value.lower()
    if "optimiser" in v or "minimiser" in v:
        return "optimiser"
    elif "jamais" in v or "ne jamais" in v or "100%" in v or "🚫" in value:
        return "jamais"
    elif "dernier" in v or "recours" in v or "⏳" in value:
        return "dernier"
    # Valeurs déjà normalisées
    if value in ("optimiser", "dernier", "jamais"):
        return value
    return "dernier"  # défaut

# ==================== CONFIGURATION PAGE ====================
st.set_page_config(
    page_title="Planificateur de retraite",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personnalisé pour meilleure apparence
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 1rem;
    }
    .section-header {
        font-size: 1.3rem;
        font-weight: bold;
        color: #2ca02c;
        border-bottom: 2px solid #e0e0e0;
        padding-bottom: 0.5rem;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .info-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

# ==================== HELPERS ====================
def display_performance_indicators(results_df, retire_params, is_couple=False, person_label=""):
    """
    Affiche les indicateurs de performance fiscale conformes au cahier des charges:
    - Taux effectif moyen d'imposition
    - Impôt total cumulé
    - Respect de la rente cible
    """
    # Filtrer les années de retraite
    retired_df = results_df[results_df["retired"] == True]
    
    if len(retired_df) == 0:
        st.warning("Aucune année de retraite dans la simulation")
        return
    
    # Calculs
    total_taxes = retired_df["taxes"].sum()
    total_taxable_income = retired_df.get("taxable_income", retired_df["gross_income"]).sum()
    avg_effective_rate = (total_taxes / total_taxable_income * 100) if total_taxable_income > 0 else 0
    
    # Respect de la cible
    target_monthly = retire_params.get("target_income", 5000.0)
    target_annual = target_monthly * 12
    
    # Analyser les écarts vs cible (si disponible)
    if "target_gap" in retired_df.columns:
        years_under = (retired_df["target_gap"] < -500).sum()  # -500$ de tolérance
        years_over = (retired_df["target_gap"] > 500).sum()
        years_on_target = len(retired_df) - years_under - years_over
    else:
        # Estimation basée sur net_income vs target
        inflation = 0.02  # Approximation
        years_retired = range(len(retired_df))
        targets = [target_annual * ((1 + inflation) ** y) for y in years_retired]
        net_incomes = retired_df["net_income"].tolist()
        years_under = sum(1 for n, t in zip(net_incomes, targets) if n < t - 500)
        years_over = sum(1 for n, t in zip(net_incomes, targets) if n > t + 500)
        years_on_target = len(retired_df) - years_under - years_over
    
    # Affichage
    label = f" - {person_label}" if person_label else ""
    st.markdown(f"### 📊 Indicateurs de performance fiscale{label}")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("💰 Impôt total cumulé", f"${total_taxes:,.0f}")
    with col2:
        st.metric("📈 Taux effectif moyen", f"{avg_effective_rate:.1f}%")
    with col3:
        st.metric("✅ Années sur cible", f"{years_on_target}/{len(retired_df)}")
    with col4:
        st.metric("⚠️ Années sous-financées", f"{years_under}")
    
    # Détails supplémentaires
    with st.expander("📋 Détails fiscaux par année"):
        fiscal_detail = []
        for _, row in retired_df.iterrows():
            fiscal_detail.append({
                "Année": row.get("year"),
                "Âge": row.get("age"),
                "Revenu imposable": row.get("taxable_income", row.get("gross_income", 0)),
                "Impôt fédéral": row.get("tax_federal", 0),
                "Impôt provincial": row.get("tax_provincial", 0),
                "Impôt total": row.get("taxes", 0),
                "Taux effectif": row.get("effective_rate", 0),
                "Récup. PSV": row.get("oas_clawback", 0)
            })
        fiscal_df = pd.DataFrame(fiscal_detail)
        st.dataframe(
            fiscal_df.style.format({
                "Revenu imposable": "${:,.0f}",
                "Impôt fédéral": "${:,.0f}",
                "Impôt provincial": "${:,.0f}",
                "Impôt total": "${:,.0f}",
                "Taux effectif": "{:.1f}%",
                "Récup. PSV": "${:,.0f}"
            }, na_rep="-"),
            use_container_width=True
        )


def format_results_df(df):
    """Formate un DataFrame de résultats pour l'affichage avec $ et colonnes compactes."""
    # Créer une copie pour ne pas modifier l'original
    display_df = df.copy()
    
    # Exclure les colonnes avec dictionnaires (difficiles à lire dans un tableau)
    columns_to_exclude = ["contributions", "balances", "withdrawals", "pensions"]
    for col in columns_to_exclude:
        if col in display_df.columns:
            display_df = display_df.drop(columns=[col])
    
    # Renommer les colonnes en français
    french_columns = {
        "year": "Année",
        "age": "Âge",
        "age1": "Âge P1",
        "age2": "Âge P2",
        "retired": "Retraité",
        "salary": "Salaire",
        "gross_income": "Revenu brut",
        "taxes": "Impôts",
        "net_income": "Revenu net",
        "wealth": "Patrimoine",
        "household_income": "Revenu ménage",
        "household_wealth": "Patrimoine ménage",
        "household_taxes": "Impôts ménage"
    }
    display_df = display_df.rename(columns=french_columns)
    
    # Colonnes monétaires à formater (noms français)
    money_columns = [
        "Salaire", "Revenu brut", "Impôts", "Revenu net", "Patrimoine",
        "Revenu ménage", "Patrimoine ménage", "Impôts ménage"
    ]
    
    # Appliquer le formatage seulement aux colonnes qui existent
    format_dict = {}
    for col in money_columns:
        if col in display_df.columns:
            format_dict[col] = "${:,.0f}"
    
    return display_df.style.format(format_dict, na_rep="-")

# ==================== SIMULATEURS ====================
# Initialiser le moteur de décaissement avec barèmes fiscaux progressifs
_decumulation_engine = DecumulationEngine(FiscalQC())


def simulate_comprehensive_single(p1, acc1, contrib1, retire1, tax1, scen):
    """
    Simulation exhaustive pour une personne utilisant le nouveau moteur conforme au cahier des charges:
    - Barèmes fiscaux progressifs Québec/Fédéral
    - Ordre de retrait: PD+pensions → Non-enregistré → REER/CRI → FERR/FRV → CELI
    - Minimums/maximums FERR/FRV légaux basés sur l'âge
    - Options CELI: dernier / jamais / mixte
    """
    results = _decumulation_engine.simulate_single(
        person=p1,
        accounts=acc1,
        contributions=contrib1,
        retirement=retire1,
        tax_params=tax1,
        scenario=scen
    )
    
    # Convertir en format dictionnaire pour compatibilité
    return [convert_result_to_dict(r) for r in results]


def run_scenario_single(p1, acc1, contrib1, retire1, tax1, scen):
    """Wrapper pour compatibilité - utilise la simulation exhaustive"""
    return simulate_comprehensive_single(p1, acc1, contrib1, retire1, tax1, scen)


def run_scenario_couple(p1, acc1, contrib1, retire1, tax1, p2, acc2, contrib2, retire2, tax2, scen):
    """Simulation pour 2 personnes (couple) avec le nouveau moteur"""
    result = _decumulation_engine.simulate_couple(
        person1=p1, accounts1=acc1, contributions1=contrib1, retirement1=retire1, tax1=tax1,
        person2=p2, accounts2=acc2, contributions2=contrib2, retirement2=retire2, tax2=tax2,
        scenario=scen
    )
    
    # Convertir les résultats individuels
    results1 = [convert_result_to_dict(r) for r in result["person1"]]
    results2 = [convert_result_to_dict(r) for r in result["person2"]]
    
    return {"person1": results1, "person2": results2, "household": result["household"]}


# ==================== PROFIL: SAUVEGARDE / CHARGEMENT FIABLE ====================
def _session_key(k):
    # helper: ensure a consistent session key
    return k

def save_profile_from_session(profile_name, household_type):
    """Construire un dict de configuration à partir de st.session_state de manière sûre."""
    def get(key, default=None):
        return st.session_state.get(key, default)

    config = {"profile_name": profile_name, "household_type": household_type}

    # Personne 1
    config["p1"] = {
        "name": get("P1_name", ""),
        "birth_year": get("P1_birth", 1960),
        "salary": get("P1_salary", 0.0),
        "salary_increase": get("P1_salary_increase", 2.0),
        "life_expectancy": get("P1_lifeexp", 90)
    }

    # Accounts and contributions for P1
    config["acc1"] = {
        "REER_balance": get("P1_reer_bal", 0.0), "REER_return": get("P1_reer_ret", 5.0),
        "CELI_balance": get("P1_celi_bal", 0.0), "CELI_return": get("P1_celi_ret", 4.0),
        "CRI_balance": get("P1_cri_bal", 0.0), "CRI_return": get("P1_cri_ret", 4.5),
        "FERR_balance": get("P1_ferr_bal", 0.0), "FERR_return": get("P1_ferr_ret", 4.0),
        "FRV_balance": get("P1_frv_bal", 0.0), "FRV_return": get("P1_frv_ret", 4.0),
        "Taxable_balance": get("P1_taxable_bal", 0.0), "Taxable_return": get("P1_taxable_ret", 3.5),
        "Taxable_interest": get("P1_interest", 30.0), "Taxable_dividends": get("P1_dividends", 40.0),
        "Taxable_capital": get("P1_capital", 30.0)
    }

    config["contrib1"] = {
        "reer_percent": get("P1_reer_pct", 0.0), "reer_fixed": get("P1_reer_fix", 0.0),
        "celi_percent": get("P1_celi_pct", 0.0), "celi_fixed": get("P1_celi_fix", 0.0),
        "cri_percent": get("P1_cri_pct", 0.0), "cri_fixed": get("P1_cri_fix", 0.0),
        "nonreg_percent": get("P1_nonreg_pct", 0.0), "nonreg_fixed": get("P1_nonreg_fix", 0.0)
    }

    config["retire1"] = {
        "retirement_age": get("P1_ret_age", 65),
        "target_income": get("P1_income_target", 0.0), "income_indexed": get("P1_indexed", True),
        "rrq_age": get("P1_rrq_age", 65), "oas_age": get("P1_oas_age", 65),
        "rrq_amount_65": get("P1_rrq_amount_65", 1250.0),
        "celi_strategy": get("P1_celi_strategy", "dernier"),
        "transfer_cap_percent": get("P1_transfer_cap", 100.0),
        "longevity_buffer": get("P1_buffer", 0.0),
        # Rente PD avec pénalité
        "rente_pd": get("P1_rente_pd", 0.0),
        "rente_pd_age_debut": get("P1_pd_age_debut", 65),
        "rente_pd_age_normal": get("P1_pd_age_normal", 65),
        "rente_pd_penalite_annuelle": get("P1_pd_penalite", 6.0)
    }

    config["tax1"] = {"income_split": get("P1_split", False), "income_split_percent": get("P1_split_pct", 0)}

    # P2 (si couple)
    if household_type == "👥 Couple":
        config["p2"] = {
            "name": get("P2_name", ""),
            "birth_year": get("P2_birth", 1960),
            "salary": get("P2_salary", 0.0),
            "salary_increase": get("P2_salary_increase", 2.0),
            "life_expectancy": get("P2_lifeexp", 90)
        }

        config["acc2"] = {
            "REER_balance": get("P2_reer_bal", 0.0), "REER_return": get("P2_reer_ret", 5.0),
            "CELI_balance": get("P2_celi_bal", 0.0), "CELI_return": get("P2_celi_ret", 4.0),
            "CRI_balance": get("P2_cri_bal", 0.0), "CRI_return": get("P2_cri_ret", 4.5),
            "FERR_balance": get("P2_ferr_bal", 0.0), "FERR_return": get("P2_ferr_ret", 4.0),
            "FRV_balance": get("P2_frv_bal", 0.0), "FRV_return": get("P2_frv_ret", 4.0),
            "Taxable_balance": get("P2_taxable_bal", 0.0), "Taxable_return": get("P2_taxable_ret", 3.5),
            "Taxable_interest": get("P2_interest", 30.0), "Taxable_dividends": get("P2_dividends", 40.0),
            "Taxable_capital": get("P2_capital", 30.0)
        }

        config["contrib2"] = {
            "reer_percent": get("P2_reer_pct", 0.0), "reer_fixed": get("P2_reer_fix", 0.0),
            "celi_percent": get("P2_celi_pct", 0.0), "celi_fixed": get("P2_celi_fix", 0.0),
            "cri_percent": get("P2_cri_pct", 0.0), "cri_fixed": get("P2_cri_fix", 0.0),
            "nonreg_percent": get("P2_nonreg_pct", 0.0), "nonreg_fixed": get("P2_nonreg_fix", 0.0)
        }

        config["retire2"] = {
            "retirement_age": get("P2_ret_age", 65),
            "target_income": get("P2_income_target", 0.0), "income_indexed": get("P2_indexed", True),
            "rrq_age": get("P2_rrq_age", 65), "oas_age": get("P2_oas_age", 65),
            "rrq_amount_65": get("P2_rrq_amount_65", 1250.0),
            "celi_strategy": get("P2_celi_strategy", "dernier"),
            "transfer_cap_percent": get("P2_transfer_cap", 100.0),
            "longevity_buffer": get("P2_buffer", 0.0),
            # Rente PD avec pénalité
            "rente_pd": get("P2_rente_pd", 0.0),
            "rente_pd_age_debut": get("P2_pd_age_debut", 65),
            "rente_pd_age_normal": get("P2_pd_age_normal", 65),
            "rente_pd_penalite_annuelle": get("P2_pd_penalite", 6.0)
        }

        config["tax2"] = {"income_split": get("P2_split", False), "income_split_percent": get("P2_split_pct", 0)}

    # Projets spéciaux et scenario
    config["special_projects"] = get("special_projects", [])
    config["scen"] = {"start_year": get("start_year", 2024), "end_year": get("end_year", 2055), "inflation": get("inflation", 2.0)}

    save_profile(profile_name, config)
    return config


def load_profile_into_session(loaded):
    """Remplir st.session_state avec les valeurs du profil chargé (sécurisé)."""
    if not loaded:
        return

    # p1
    # définir le type de ménage si présent dans le profil
    if "household_type" in loaded:
        st.session_state["household_type"] = loaded.get("household_type")
    p1 = loaded.get("p1", {})
    st.session_state["P1_name"] = p1.get("name", "")
    st.session_state["P1_birth"] = p1.get("birth_year", 1960)
    st.session_state["P1_salary"] = p1.get("salary", 0.0)
    st.session_state["P1_salary_increase"] = p1.get("salary_increase", 2.0)
    st.session_state["P1_lifeexp"] = p1.get("life_expectancy", 90)

    # acc1
    acc1 = loaded.get("acc1", {})
    st.session_state["P1_reer_bal"] = acc1.get("REER_balance", 0.0)
    st.session_state["P1_reer_ret"] = acc1.get("REER_return", 5.0)
    st.session_state["P1_celi_bal"] = acc1.get("CELI_balance", 0.0)
    st.session_state["P1_celi_ret"] = acc1.get("CELI_return", 4.0)
    st.session_state["P1_cri_bal"] = acc1.get("CRI_balance", 0.0)
    st.session_state["P1_cri_ret"] = acc1.get("CRI_return", 4.5)
    st.session_state["P1_ferr_bal"] = acc1.get("FERR_balance", 0.0)
    st.session_state["P1_ferr_ret"] = acc1.get("FERR_return", 4.0)
    st.session_state["P1_frv_bal"] = acc1.get("FRV_balance", 0.0)
    st.session_state["P1_frv_ret"] = acc1.get("FRV_return", 4.0)
    st.session_state["P1_taxable_bal"] = acc1.get("Taxable_balance", 0.0)
    st.session_state["P1_taxable_ret"] = acc1.get("Taxable_return", 3.5)
    st.session_state["P1_interest"] = acc1.get("Taxable_interest", 30.0)
    st.session_state["P1_dividends"] = acc1.get("Taxable_dividends", 40.0)
    st.session_state["P1_capital"] = acc1.get("Taxable_capital", 30.0)

    # contrib1
    contrib1 = loaded.get("contrib1", {})
    st.session_state["P1_reer_pct"] = contrib1.get("reer_percent", 0.0)
    st.session_state["P1_reer_fix"] = contrib1.get("reer_fixed", 0.0)
    st.session_state["P1_celi_pct"] = contrib1.get("celi_percent", 0.0)
    st.session_state["P1_celi_fix"] = contrib1.get("celi_fixed", 0.0)
    st.session_state["P1_cri_pct"] = contrib1.get("cri_percent", 0.0)
    st.session_state["P1_cri_fix"] = contrib1.get("cri_fixed", 0.0)

    # retire1
    retire1 = loaded.get("retire1", {})
    st.session_state["P1_ret_age"] = retire1.get("retirement_age", 65)
    st.session_state["P1_income_target"] = retire1.get("target_income", 0.0)
    st.session_state["P1_indexed"] = retire1.get("income_indexed", True)
    st.session_state["P1_rrq_age"] = retire1.get("rrq_age", 65)
    st.session_state["P1_oas_age"] = retire1.get("oas_age", 65)
    st.session_state["P1_rrq_amount_65"] = retire1.get("rrq_amount_65", 1250.0)
    # Migration: supporter ancien format celi_usage + normaliser valeurs d'affichage
    celi_strat = retire1.get("celi_strategy", retire1.get("celi_usage", "dernier"))
    st.session_state["P1_celi_strategy"] = _normalize_celi_strategy(celi_strat)
    st.session_state["P1_transfer_cap"] = retire1.get("transfer_cap_percent", 100.0)
    st.session_state["P1_buffer"] = retire1.get("longevity_buffer", 0.0)
    # Rente PD (migration: ancien format dans p1, nouveau dans retire1)
    st.session_state["P1_rente_pd"] = retire1.get("rente_pd", loaded.get("p1", {}).get("rente_pd", 0.0))
    st.session_state["P1_pd_age_debut"] = retire1.get("rente_pd_age_debut", 65)
    st.session_state["P1_pd_age_normal"] = retire1.get("rente_pd_age_normal", 65)
    st.session_state["P1_pd_penalite"] = retire1.get("rente_pd_penalite_annuelle", 6.0)

    # tax1
    tax1 = loaded.get("tax1", {})
    st.session_state["P1_split"] = tax1.get("income_split", False)
    st.session_state["P1_split_pct"] = tax1.get("income_split_percent", 0)

    # P2 (si présent)
    p2 = loaded.get("p2")
    if p2:
        st.session_state["P2_name"] = p2.get("name", "")
        st.session_state["P2_birth"] = p2.get("birth_year", 1960)
        st.session_state["P2_salary"] = p2.get("salary", 0.0)
        st.session_state["P2_salary_increase"] = p2.get("salary_increase", 2.0)
        st.session_state["P2_lifeexp"] = p2.get("life_expectancy", 90)

        acc2 = loaded.get("acc2", {})
        st.session_state["P2_reer_bal"] = acc2.get("REER_balance", 0.0)
        st.session_state["P2_reer_ret"] = acc2.get("REER_return", 5.0)
        st.session_state["P2_celi_bal"] = acc2.get("CELI_balance", 0.0)
        st.session_state["P2_celi_ret"] = acc2.get("CELI_return", 4.0)
        st.session_state["P2_cri_bal"] = acc2.get("CRI_balance", 0.0)
        st.session_state["P2_cri_ret"] = acc2.get("CRI_return", 4.5)
        st.session_state["P2_ferr_bal"] = acc2.get("FERR_balance", 0.0)
        st.session_state["P2_ferr_ret"] = acc2.get("FERR_return", 4.0)
        st.session_state["P2_frv_bal"] = acc2.get("FRV_balance", 0.0)
        st.session_state["P2_frv_ret"] = acc2.get("FRV_return", 4.0)
        st.session_state["P2_taxable_bal"] = acc2.get("Taxable_balance", 0.0)
        st.session_state["P2_taxable_ret"] = acc2.get("Taxable_return", 3.5)
        st.session_state["P2_interest"] = acc2.get("Taxable_interest", 30.0)
        st.session_state["P2_dividends"] = acc2.get("Taxable_dividends", 40.0)
        st.session_state["P2_capital"] = acc2.get("Taxable_capital", 30.0)

        contrib2 = loaded.get("contrib2", {})
        st.session_state["P2_reer_pct"] = contrib2.get("reer_percent", 0.0)
        st.session_state["P2_reer_fix"] = contrib2.get("reer_fixed", 0.0)
        st.session_state["P2_celi_pct"] = contrib2.get("celi_percent", 0.0)
        st.session_state["P2_celi_fix"] = contrib2.get("celi_fixed", 0.0)

        retire2 = loaded.get("retire2", {})
        st.session_state["P2_ret_age"] = retire2.get("retirement_age", 65)
        st.session_state["P2_income_target"] = retire2.get("target_income", 0.0)
        st.session_state["P2_indexed"] = retire2.get("income_indexed", True)
        st.session_state["P2_rrq_age"] = retire2.get("rrq_age", 65)
        st.session_state["P2_oas_age"] = retire2.get("oas_age", 65)
        st.session_state["P2_rrq_amount_65"] = retire2.get("rrq_amount_65", 1250.0)
        # Migration: supporter ancien format celi_usage + normaliser valeurs d'affichage
        celi_strat2 = retire2.get("celi_strategy", retire2.get("celi_usage", "dernier"))
        st.session_state["P2_celi_strategy"] = _normalize_celi_strategy(celi_strat2)
        st.session_state["P2_transfer_cap"] = retire2.get("transfer_cap_percent", 100.0)
        st.session_state["P2_buffer"] = retire2.get("longevity_buffer", 0.0)
        # Rente PD (migration: ancien format dans p2, nouveau dans retire2)
        st.session_state["P2_rente_pd"] = retire2.get("rente_pd", p2.get("rente_pd", 0.0))
        st.session_state["P2_pd_age_debut"] = retire2.get("rente_pd_age_debut", 65)
        st.session_state["P2_pd_age_normal"] = retire2.get("rente_pd_age_normal", 65)
        st.session_state["P2_pd_penalite"] = retire2.get("rente_pd_penalite_annuelle", 6.0)

        tax2 = loaded.get("tax2", {})
        st.session_state["P2_split"] = tax2.get("income_split", False)
        st.session_state["P2_split_pct"] = tax2.get("income_split_percent", 0)

    # special projects
    st.session_state["special_projects"] = loaded.get("special_projects", [])
    scen = loaded.get("scen", {})
    st.session_state["start_year"] = scen.get("start_year", 2024)
    st.session_state["end_year"] = scen.get("end_year", 2055)
    st.session_state["inflation"] = scen.get("inflation", 2.0)

def new_profile_session_reset():
    """Réinitialiser uniquement les clés de profil sans perdre d'autres états globaux."""
    keys_to_delete = [k for k in st.session_state.keys() if k.startswith("P1_") or k.startswith("P2_") or k in {
        "special_projects","start_year","end_year","inflation","profile_name","household_type","last_loaded_profile"
    }]
    for k in keys_to_delete:
        del st.session_state[k]
    # valeurs de base
    st.session_state["profile_name"] = f"Profil_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    st.session_state["household_type"] = "👤 Célibataire"
    st.session_state["special_projects"] = []

# ==================== INTERFACE PRINCIPALE ====================
st.markdown("<div class='main-header'>📊 Planificateur de retraite</div>", unsafe_allow_html=True)

# ==================== SIDEBAR - GESTION DES PROFILS ====================
with st.sidebar:
    st.markdown("### 📁 Gestion des profils")
    profiles = list_profiles()

    # Uploader pour import direct JSON
    uploaded_profile = st.file_uploader("Importer un profil (.json)", type=["json"], help="Sélectionnez un fichier de profil exporté")
    if uploaded_profile is not None:
        try:
            raw = uploaded_profile.read().decode("utf-8")
            imported = json.loads(raw)
            load_profile_into_session(imported)
            st.session_state["profile_name"] = imported.get("profile_name", "Profil_import")
            st.success("Profil importé ✅")
        except Exception as e:
            st.error(f"Import échoué: {e}")

    selected_profile = st.selectbox(
        "Charger profil existant",
        ["(Aucun)"] + profiles,
        key="profile_selector"
    )
    if selected_profile != "(Aucun)":
        loaded = load_profile(selected_profile) or {}
        last = st.session_state.get("last_loaded_profile")
        if last != selected_profile:
            load_profile_into_session(loaded)
            st.session_state["last_loaded_profile"] = selected_profile
    else:
        loaded = {}

    # Champ nom du profil (persistant)
    if "profile_name" not in st.session_state:
        st.session_state["profile_name"] = loaded.get("profile_name", f"Profil_{datetime.now().strftime('%Y%m%d')}")
    profile_name = st.text_input("Nom du profil", key="profile_name")

    # Actions
    colA, colB, colC = st.columns(3)
    with colA:
        if st.button("💾 Sauvegarder", use_container_width=True):
            try:
                cfg = save_profile_from_session(profile_name, st.session_state.get("household_type", "👤 Célibataire"))
                st.success("Sauvegarde OK")
            except Exception as e:
                st.error(f"Erreur: {e}")
    with colB:
        if st.button("🆕 Nouveau", use_container_width=True):
            new_profile_session_reset()
            st.success("Profil réinitialisé")
    with colC:
        # Exporter le profil actif
        if st.button("📤 Export", use_container_width=True):
            try:
                cfg = save_profile_from_session(profile_name, st.session_state.get("household_type", "👤 Célibataire"))
                st.download_button(
                    label="Télécharger JSON", file_name=f"{profile_name}.json", mime="application/json",
                    data=json.dumps(cfg, indent=2), key="download_profile_json"
                )
            except Exception as e:
                st.error(f"Export impossible: {e}")

    st.markdown("---")
    st.markdown("### ⚙️ Options")
    
    # utiliser la clé de session pour que le profil chargé puisse pré-configurer ceci
    household_type = st.radio(
        "Type de ménage",
        ["👤 Célibataire", "👥 Couple"],
        key="household_type",
        horizontal=True
    )
    
    language = st.selectbox(
        "Langue",
        ["Français", "English", "Español"],
        index=0
    )
    
    province = st.selectbox(
        "Province de résidence",
        ["QC", "ON", "BC", "AB", "MB", "SK", "NS", "NB", "NL", "PE"],
        index=0
    )

# ==================== ONGLETS PRINCIPAUX ====================
tab_personal, tab_accounts, tab_retirement, tab_tax, tab_special, tab_results = st.tabs([
    "👤 Profil personnel",
    "💰 Comptes & Cotisations",
    "🏖️ Retraite",
    "📋 Fiscalité",
    "🎯 Projets spéciaux",
    "📈 Résultats"
])

# ==================== ONGLET 1: PROFIL PERSONNEL ====================
with tab_personal:
    st.markdown("<div class='section-header'>Informations personnelles</div>", unsafe_allow_html=True)
    
    if household_type == "👤 Célibataire":
        # Utiliser toujours le prefix 'P1' pour cohérence des clés session
        p1 = person_form("P1", loaded.get("p1", {}))
        p2, acc2, contrib2, retire2, tax2 = None, None, None, None, None
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Personne 1**")
            p1 = person_form("P1", loaded.get("p1", {}))
        with col2:
            st.markdown("**Personne 2**")
            p2 = person_form("P2", loaded.get("p2", {}))

# ==================== ONGLET 2: COMPTES & COTISATIONS ====================
with tab_accounts:
    st.markdown("<div class='section-header'>Comptes financiers & Cotisations</div>", unsafe_allow_html=True)
    
    if household_type == "👤 Célibataire":
        acc1, contrib1 = accounts_form("P1", loaded.get("acc1", {}), loaded.get("contrib1", {}))
        # Validation: REER + CRI % ne doit pas dépasser 18% du salaire (règle simplifiée)
        total_pct = float(contrib1.get("reer_percent", 0.0)) + float(contrib1.get("cri_percent", 0.0))
        if total_pct > 18.0:
            st.error(f"Validation: La somme des cotisations en % REER ({contrib1.get('reer_percent', 0.0)}%) + CRI ({contrib1.get('cri_percent', 0.0)}%) dépasse 18%. Ajustez vos pourcentages.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Personne 1**")
            acc1, contrib1 = accounts_form("P1", loaded.get("acc1", {}), loaded.get("contrib1", {}))
            total_pct1 = float(contrib1.get("reer_percent", 0.0)) + float(contrib1.get("cri_percent", 0.0))
            if total_pct1 > 18.0:
                st.error(f"P1: La somme des cotisations en % REER ({contrib1.get('reer_percent', 0.0)}%) + CRI ({contrib1.get('cri_percent', 0.0)}%) dépasse 18%.")
        with col2:
            st.markdown("**Personne 2**")
            acc2, contrib2 = accounts_form("P2", loaded.get("acc2", {}), loaded.get("contrib2", {}))
            total_pct2 = float(contrib2.get("reer_percent", 0.0)) + float(contrib2.get("cri_percent", 0.0))
            if total_pct2 > 18.0:
                st.error(f"P2: La somme des cotisations en % REER ({contrib2.get('reer_percent', 0.0)}%) + CRI ({contrib2.get('cri_percent', 0.0)}%) dépasse 18%.")

# ==================== ONGLET 3: RETRAITE ====================
with tab_retirement:
    st.markdown("<div class='section-header'>Paramètres de retraite</div>", unsafe_allow_html=True)
    
    # Bouton de lancement de simulation au début de l'onglet
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Lancer la simulation", use_container_width=True, key="run_sim_btn"):
            st.session_state["run_simulation"] = True
    with col2:
        st.caption("💡 Configurez tous les paramètres, puis lancez la simulation")
    
    st.markdown("---")
    
    if household_type == "👤 Célibataire":
        retire1 = retirement_form("P1", loaded.get("retire1", {}))
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Personne 1**")
            retire1 = retirement_form("P1", loaded.get("retire1", {}))
        with col2:
            st.markdown("**Personne 2**")
            retire2 = retirement_form("P2", loaded.get("retire2", {}))

# ==================== ONGLET 4: FISCALITÉ ====================
with tab_tax:
    st.markdown("<div class='section-header'>Paramètres fiscaux</div>", unsafe_allow_html=True)
    
    if household_type == "👤 Célibataire":
        tax1 = tax_form("P1", loaded.get("tax1", {}), province)
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Personne 1**")
            tax1 = tax_form("P1", loaded.get("tax1", {}), province)
        with col2:
            st.markdown("**Personne 2**")
            tax2 = tax_form("P2", loaded.get("tax2", {}), province)

# ==================== ONGLET 5: PROJETS SPÉCIAUX ====================
with tab_special:
    st.markdown("<div class='section-header'>Projets spéciaux</div>", unsafe_allow_html=True)
    special_projects = special_projects_form(loaded.get("special_projects", st.session_state.get("special_projects", [])))
    # Mettre à jour la session pour la sauvegarde
    st.session_state["special_projects"] = special_projects

# ==================== ONGLET 6: RÉSULTATS ====================
with tab_results:
    st.markdown("<div class='section-header'>Simulation et résultats</div>", unsafe_allow_html=True)

    from datetime import datetime
    current_year = datetime.now().year
    # Calcul dynamique de l'année de fin selon les espérances de vie
    p1_end = p1.get("birth_year", 1960) + p1.get("life_expectancy", 90)
    if st.session_state.get("household_type") == "👥 Couple" and 'p2' in locals() and p2:
        p2_end = p2.get("birth_year", 1960) + p2.get("life_expectancy", 90)
        end_year = max(p1_end, p2_end)
    else:
        end_year = p1_end

    # Inflation reste paramétrable
    colA, colB, colC = st.columns(3)
    with colA:
        st.metric("Année de début", current_year)
    with colB:
        st.metric("Année de fin", end_year)
    with colC:
        inflation = st.number_input("Inflation annuelle (%)", value=loaded.get("inflation", 2.0), min_value=0.0, max_value=10.0)

    # Mettre à jour dans la session pour cohérence sauvegarde profil
    st.session_state["start_year"] = current_year
    st.session_state["end_year"] = end_year
    st.session_state["inflation"] = inflation

    scen = {"start_year": current_year, "end_year": end_year, "inflation": inflation}
    
    # Affichage des résultats
    if st.session_state.get("run_simulation", False):
        st.info("⏳ Simulation en cours...")
        
        try:
            if household_type == "👤 Célibataire":
                results_df = pd.DataFrame(run_scenario_single(p1, acc1, contrib1, retire1, tax1, scen))
                
                # === Tableau sommaire au début ===
                st.subheader("📋 Sommaire de la projection")
                sommaire_data = []
                for _, row in results_df.iterrows():
                    retired = row.get("retired", False)
                    target_income = retire1.get("target_income", 0.0) * 12 if retired else 0.0
                    
                    sommaire_data.append({
                        "Année": row.get("year"),
                        "Âge": row.get("age"),
                        "Revenu net nécessaire": target_income,
                        "Revenu d'emploi": row.get("salary", 0.0),
                        "Solde REER/FERR": row.get("balances", {}).get("REER", 0.0) + row.get("balances", {}).get("FERR", 0.0),
                        "Solde CRI/FRV": row.get("balances", {}).get("CRI", 0.0) + row.get("balances", {}).get("FRV", 0.0),
                        "Solde CELI": row.get("balances", {}).get("CELI", 0.0),
                        "Solde Non-enregistré": row.get("balances", {}).get("Taxable", 0.0),
                        "Rente PD": row.get("pensions", {}).get("PD", 0.0),
                        "RRQ": row.get("pensions", {}).get("RRQ", 0.0),
                        "SV (OAS)": row.get("pensions", {}).get("OAS", 0.0),
                        "SRG": row.get("pensions", {}).get("SRG", 0.0),
                        "Retrait REER/FERR": row.get("withdrawals", {}).get("FERR", 0.0),
                        "Retrait CRI/FRV": row.get("withdrawals", {}).get("FRV", 0.0),
                        "Retrait CELI": row.get("withdrawals", {}).get("CELI", 0.0),
                        "Retrait Non-enregistré": row.get("withdrawals", {}).get("Taxable", 0.0)
                    })
                sommaire_df = pd.DataFrame(sommaire_data)
                st.dataframe(
                    sommaire_df.style.format({
                        "Revenu net nécessaire": "${:,.0f}",
                        "Revenu d'emploi": "${:,.0f}",
                        "Solde REER/FERR": "${:,.0f}",
                        "Solde CRI/FRV": "${:,.0f}",
                        "Solde CELI": "${:,.0f}",
                        "Solde Non-enregistré": "${:,.0f}",
                        "Rente PD": "${:,.0f}",
                        "RRQ": "${:,.0f}",
                        "SV (OAS)": "${:,.0f}",
                        "SRG": "${:,.0f}",
                        "Retrait REER/FERR": "${:,.0f}",
                        "Retrait CRI/FRV": "${:,.0f}",
                        "Retrait CELI": "${:,.0f}",
                        "Retrait Non-enregistré": "${:,.0f}"
                    }, na_rep="-"),
                    use_container_width=True
                )
                st.markdown("---")
                
                st.subheader("📊 Résultats personnels")
                st.dataframe(
                    format_results_df(results_df),
                    use_container_width=False
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    st.plotly_chart(plot_income(results_df), use_container_width=True)
                with col2:
                    st.plotly_chart(plot_wealth(results_df), use_container_width=True)

                # === Sommaire des revenus ===
                st.subheader("📋 Sommaire des revenus")
                summary_data = []
                for _, row in results_df.iterrows():
                    summary_data.append({
                        "Année": row.get("year"),
                        "Âge": row.get("age"),
                        "Revenu brut": row.get("gross_income", 0.0),
                        "Revenu net après impôt": row.get("net_income", 0.0)
                    })
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(
                    summary_df.style.format({
                        "Revenu brut": "${:,.0f}",
                        "Revenu net après impôt": "${:,.0f}"
                    }, na_rep="-"),
                    use_container_width=False
                )
                
                # === Indicateurs de performance fiscale ===
                st.markdown("---")
                display_performance_indicators(results_df, retire1)
            
            else:
                results = run_scenario_couple(p1, acc1, contrib1, retire1, tax1, p2, acc2, contrib2, retire2, tax2, scen)
                
                # === Tableau sommaire au début - Couple ===
                st.subheader("📋 Sommaire de la projection - Couple")
                df1 = pd.DataFrame(results["person1"])
                df2 = pd.DataFrame(results["person2"])
                
                sommaire_data = []
                for idx in range(len(df1)):
                    row1 = df1.iloc[idx]
                    row2 = df2.iloc[idx]
                    
                    retired1 = row1.get("retired", False)
                    retired2 = row2.get("retired", False)
                    target_income = retire1.get("target_income", 0.0) * 12 if (retired1 or retired2) else 0.0
                    
                    sommaire_data.append({
                        "Année": row1.get("year"),
                        "Âge P1": row1.get("age"),
                        "Âge P2": row2.get("age"),
                        "Revenu net nécessaire": target_income,
                        "Revenu emploi P1": row1.get("salary", 0.0),
                        "Revenu emploi P2": row2.get("salary", 0.0),
                        "Solde REER/FERR P1": row1.get("balances", {}).get("REER", 0.0) + row1.get("balances", {}).get("FERR", 0.0),
                        "Solde REER/FERR P2": row2.get("balances", {}).get("REER", 0.0) + row2.get("balances", {}).get("FERR", 0.0),
                        "Solde CRI/FRV P1": row1.get("balances", {}).get("CRI", 0.0) + row1.get("balances", {}).get("FRV", 0.0),
                        "Solde CRI/FRV P2": row2.get("balances", {}).get("CRI", 0.0) + row2.get("balances", {}).get("FRV", 0.0),
                        "Solde CELI P1": row1.get("balances", {}).get("CELI", 0.0),
                        "Solde CELI P2": row2.get("balances", {}).get("CELI", 0.0),
                        "Solde Non-enreg. P1": row1.get("balances", {}).get("Taxable", 0.0),
                        "Solde Non-enreg. P2": row2.get("balances", {}).get("Taxable", 0.0),
                        "Rente PD P1": row1.get("pensions", {}).get("PD", 0.0),
                        "Rente PD P2": row2.get("pensions", {}).get("PD", 0.0),
                        "RRQ P1": row1.get("pensions", {}).get("RRQ", 0.0),
                        "RRQ P2": row2.get("pensions", {}).get("RRQ", 0.0),
                        "SV P1": row1.get("pensions", {}).get("OAS", 0.0),
                        "SV P2": row2.get("pensions", {}).get("OAS", 0.0),
                        "Retrait REER/FERR P1": row1.get("withdrawals", {}).get("FERR", 0.0),
                        "Retrait REER/FERR P2": row2.get("withdrawals", {}).get("FERR", 0.0),
                        "Retrait CRI/FRV P1": row1.get("withdrawals", {}).get("FRV", 0.0),
                        "Retrait CRI/FRV P2": row2.get("withdrawals", {}).get("FRV", 0.0),
                        "Retrait CELI P1": row1.get("withdrawals", {}).get("CELI", 0.0),
                        "Retrait CELI P2": row2.get("withdrawals", {}).get("CELI", 0.0),
                        "Retrait Non-enreg. P1": row1.get("withdrawals", {}).get("Taxable", 0.0),
                        "Retrait Non-enreg. P2": row2.get("withdrawals", {}).get("Taxable", 0.0)
                    })
                sommaire_df = pd.DataFrame(sommaire_data)
                st.dataframe(
                    sommaire_df.style.format({
                        "Revenu net nécessaire": "${:,.0f}",
                        "Revenu emploi P1": "${:,.0f}",
                        "Revenu emploi P2": "${:,.0f}",
                        "Solde REER/FERR P1": "${:,.0f}",
                        "Solde REER/FERR P2": "${:,.0f}",
                        "Solde CRI/FRV P1": "${:,.0f}",
                        "Solde CRI/FRV P2": "${:,.0f}",
                        "Solde CELI P1": "${:,.0f}",
                        "Solde CELI P2": "${:,.0f}",
                        "Solde Non-enreg. P1": "${:,.0f}",
                        "Solde Non-enreg. P2": "${:,.0f}",
                        "Rente PD P1": "${:,.0f}",
                        "Rente PD P2": "${:,.0f}",
                        "RRQ P1": "${:,.0f}",
                        "RRQ P2": "${:,.0f}",
                        "SV P1": "${:,.0f}",
                        "SV P2": "${:,.0f}",
                        "Retrait REER/FERR P1": "${:,.0f}",
                        "Retrait REER/FERR P2": "${:,.0f}",
                        "Retrait CRI/FRV P1": "${:,.0f}",
                        "Retrait CRI/FRV P2": "${:,.0f}",
                        "Retrait CELI P1": "${:,.0f}",
                        "Retrait CELI P2": "${:,.0f}",
                        "Retrait Non-enreg. P1": "${:,.0f}",
                        "Retrait Non-enreg. P2": "${:,.0f}"
                    }, na_rep="-"),
                    use_container_width=True
                )
                st.markdown("---")
                
                st.subheader("👥 Résultats du ménage")
                household_df = pd.DataFrame(results["household"])
                st.dataframe(
                    format_results_df(household_df),
                    use_container_width=False
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    st.plotly_chart(plot_income(household_df, label="Revenu net du ménage"), use_container_width=True)
                with col2:
                    st.plotly_chart(plot_wealth(household_df, label="Patrimoine du ménage"), use_container_width=True)
                
                st.markdown("---")
                st.subheader("👤 Détails par personne")
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("**Personne 1**")
                    df1 = pd.DataFrame(results["person1"])
                    st.dataframe(
                        format_results_df(df1),
                        use_container_width=False
                    )
                
                with col2:
                    st.markdown("**Personne 2**")
                    df2 = pd.DataFrame(results["person2"])
                    st.dataframe(
                        format_results_df(df2),
                        use_container_width=False
                    )

                # === Sommaire des revenus - Couple ===
                st.subheader("📋 Sommaire des revenus - Couple")
                summary_data = []
                for idx in range(len(df1)):
                    row1 = df1.iloc[idx]
                    row2 = df2.iloc[idx]
                    summary_data.append({
                        "Année": row1.get("year"),
                        "Âge P1": row1.get("age"),
                        "Âge P2": row2.get("age"),
                        "Revenu brut P1": row1.get("gross_income", 0.0),
                        "Revenu brut P2": row2.get("gross_income", 0.0),
                        "Revenu net P1": row1.get("net_income", 0.0),
                        "Revenu net P2": row2.get("net_income", 0.0)
                    })
                summary_df = pd.DataFrame(summary_data)
                st.dataframe(
                    summary_df.style.format({
                        "Revenu brut P1": "${:,.0f}",
                        "Revenu brut P2": "${:,.0f}",
                        "Revenu net P1": "${:,.0f}",
                        "Revenu net P2": "${:,.0f}"
                    }, na_rep="-"),
                    use_container_width=False
                )
            
                # === Sommaire détaillé de la projection - Couple ===
                st.subheader("📋 Sommaire détaillé de la projection - Couple")
                
                # Section 1: Vue d'ensemble
                with st.expander("📊 Vue d'ensemble et revenus", expanded=True):
                    overview_data = []
                    for idx in range(len(df1)):
                        row1 = df1.iloc[idx]
                        row2 = df2.iloc[idx]
                        overview_data.append({
                            "Année": row1.get("year"),
                            "Âge P1": row1.get("age"),
                            "Âge P2": row2.get("age"),
                            "Revenu brut P1": row1.get("gross_income", 0.0),
                            "Revenu brut P2": row2.get("gross_income", 0.0),
                            "Revenu net P1": row1.get("net_income", 0.0),
                            "Revenu net P2": row2.get("net_income", 0.0),
                            "Impôt P1": row1.get("taxes", 0.0),
                            "Impôt P2": row2.get("taxes", 0.0)
                        })
                    overview_df = pd.DataFrame(overview_data)
                    st.dataframe(
                        overview_df.style.format({
                            "Revenu brut P1": "${:,.0f}", "Revenu brut P2": "${:,.0f}",
                            "Revenu net P1": "${:,.0f}", "Revenu net P2": "${:,.0f}",
                            "Impôt P1": "${:,.0f}", "Impôt P2": "${:,.0f}"
                        }, na_rep="-"),
                        use_container_width=True
                    )
                
                # Section 2: Cotisations
                with st.expander("💰 Cotisations annuelles"):
                    contrib_data = []
                    for idx in range(len(df1)):
                        row1 = df1.iloc[idx]
                        row2 = df2.iloc[idx]
                        contrib_data.append({
                            "Année": row1.get("year"),
                            "REER P1": row1.get("contributions", {}).get("REER", 0.0),
                            "REER P2": row2.get("contributions", {}).get("REER", 0.0),
                            "CELI P1": row1.get("contributions", {}).get("CELI", 0.0),
                            "CELI P2": row2.get("contributions", {}).get("CELI", 0.0),
                            "CRI P1": row1.get("contributions", {}).get("CRI", 0.0),
                            "CRI P2": row2.get("contributions", {}).get("CRI", 0.0),
                            "Taxable P1": row1.get("contributions", {}).get("Taxable", 0.0),
                            "Taxable P2": row2.get("contributions", {}).get("Taxable", 0.0)
                        })
                    contrib_df = pd.DataFrame(contrib_data)
                    st.dataframe(
                        contrib_df.style.format({
                            "REER P1": "${:,.0f}", "REER P2": "${:,.0f}",
                            "CELI P1": "${:,.0f}", "CELI P2": "${:,.0f}",
                            "CRI P1": "${:,.0f}", "CRI P2": "${:,.0f}",
                            "Taxable P1": "${:,.0f}", "Taxable P2": "${:,.0f}"
                        }, na_rep="-"),
                        use_container_width=True
                    )
                
                # Section 3: Soldes des comptes
                with st.expander("🏦 Soldes des comptes"):
                    balances_data = []
                    for idx in range(len(df1)):
                        row1 = df1.iloc[idx]
                        row2 = df2.iloc[idx]
                        balances_data.append({
                            "Année": row1.get("year"),
                            "REER P1": row1.get("balances", {}).get("REER", 0.0),
                            "REER P2": row2.get("balances", {}).get("REER", 0.0),
                            "CELI P1": row1.get("balances", {}).get("CELI", 0.0),
                            "CELI P2": row2.get("balances", {}).get("CELI", 0.0),
                            "CRI P1": row1.get("balances", {}).get("CRI", 0.0),
                            "CRI P2": row2.get("balances", {}).get("CRI", 0.0),
                            "FERR P1": row1.get("balances", {}).get("FERR", 0.0),
                            "FERR P2": row2.get("balances", {}).get("FERR", 0.0),
                            "FRV P1": row1.get("balances", {}).get("FRV", 0.0),
                            "FRV P2": row2.get("balances", {}).get("FRV", 0.0),
                            "Taxable P1": row1.get("balances", {}).get("Taxable", 0.0),
                            "Taxable P2": row2.get("balances", {}).get("Taxable", 0.0),
                            "Patrimoine P1": row1.get("wealth", 0.0),
                            "Patrimoine P2": row2.get("wealth", 0.0)
                        })
                    balances_df = pd.DataFrame(balances_data)
                    st.dataframe(
                        balances_df.style.format({
                            "REER P1": "${:,.0f}", "REER P2": "${:,.0f}",
                            "CELI P1": "${:,.0f}", "CELI P2": "${:,.0f}",
                            "CRI P1": "${:,.0f}", "CRI P2": "${:,.0f}",
                            "FERR P1": "${:,.0f}", "FERR P2": "${:,.0f}",
                            "FRV P1": "${:,.0f}", "FRV P2": "${:,.0f}",
                            "Taxable P1": "${:,.0f}", "Taxable P2": "${:,.0f}",
                            "Patrimoine P1": "${:,.0f}", "Patrimoine P2": "${:,.0f}"
                        }, na_rep="-"),
                        use_container_width=True
                    )
                
                # Section 4: Pensions et retraits
                with st.expander("📤 Pensions et retraits"):
                    withdrawal_data = []
                    for idx in range(len(df1)):
                        row1 = df1.iloc[idx]
                        row2 = df2.iloc[idx]
                        withdrawal_data.append({
                            "Année": row1.get("year"),
                            "RRQ P1": row1.get("pensions", {}).get("RRQ", 0.0),
                            "RRQ P2": row2.get("pensions", {}).get("RRQ", 0.0),
                            "OAS P1": row1.get("pensions", {}).get("OAS", 0.0),
                            "OAS P2": row2.get("pensions", {}).get("OAS", 0.0),
                            "Retrait FERR P1": row1.get("withdrawals", {}).get("FERR", 0.0),
                            "Retrait FERR P2": row2.get("withdrawals", {}).get("FERR", 0.0),
                            "Retrait FRV P1": row1.get("withdrawals", {}).get("FRV", 0.0),
                            "Retrait FRV P2": row2.get("withdrawals", {}).get("FRV", 0.0),
                            "Retrait CELI P1": row1.get("withdrawals", {}).get("CELI", 0.0),
                            "Retrait CELI P2": row2.get("withdrawals", {}).get("CELI", 0.0),
                            "Retrait Taxable P1": row1.get("withdrawals", {}).get("Taxable", 0.0),
                            "Retrait Taxable P2": row2.get("withdrawals", {}).get("Taxable", 0.0)
                        })
                    withdrawal_df = pd.DataFrame(withdrawal_data)
                    st.dataframe(
                        withdrawal_df.style.format({
                            "RRQ P1": "${:,.0f}", "RRQ P2": "${:,.0f}",
                            "OAS P1": "${:,.0f}", "OAS P2": "${:,.0f}",
                            "Retrait FERR P1": "${:,.0f}", "Retrait FERR P2": "${:,.0f}",
                            "Retrait FRV P1": "${:,.0f}", "Retrait FRV P2": "${:,.0f}",
                            "Retrait CELI P1": "${:,.0f}", "Retrait CELI P2": "${:,.0f}",
                            "Retrait Taxable P1": "${:,.0f}", "Retrait Taxable P2": "${:,.0f}"
                        }, na_rep="-"),
                        use_container_width=True
                    )
                
                # === Indicateurs de performance fiscale - Couple ===
                st.markdown("---")
                col1, col2 = st.columns(2)
                with col1:
                    display_performance_indicators(df1, retire1, is_couple=True, person_label="Personne 1")
                with col2:
                    display_performance_indicators(df2, retire2, is_couple=True, person_label="Personne 2")
        
            st.success("✅ Simulation terminée avec succès!")
        
        except Exception as e:
            st.error(f"❌ Erreur lors de la simulation: {str(e)}")

"""La sauvegarde est désormais gérée directement via le bouton de la sidebar
    et par les helpers save_profile_from_session / load_profile_into_session."""