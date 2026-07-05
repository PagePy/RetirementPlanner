import streamlit as st

# ==================== FORMULAIRE PROFIL PERSONNEL ====================
def person_form(prefix, initial):
    """Formulaire pour les informations personnelles"""
    # Vérifier que initial est un dictionnaire valide
    if initial is None:
        initial = {}
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("**Identité**")
        name = st.text_input(f"🔤 Nom", value=initial.get("name", ""), key=f"{prefix}_name")
        birth_year = st.number_input(f"🗓️ Année de naissance", 
                                     value=initial.get("birth_year", 1960), 
                                     min_value=1920, max_value=2010, key=f"{prefix}_birth")
    
    with col2:
        st.markdown("**Revenus**")
        salary = st.number_input(f"💵 Salaire annuel", 
                                value=initial.get("salary", 50000.0),
                                min_value=0.0, step=1000.0, key=f"{prefix}_salary")
        salary_increase = st.number_input(f"📈 Augmentation salariale annuelle (%)",
                                value=initial.get("salary_increase", 2.0),
                                min_value=0.0, max_value=15.0, step=0.5, key=f"{prefix}_salary_increase",
                                help="Pourcentage d'augmentation salariale annuelle (peut être supérieur à l'inflation)")
    
    with col3:
        st.markdown("**Espérance de vie**")
        life_expectancy = st.number_input(f"📊 Espérance de vie", 
                                         value=initial.get("life_expectancy", 90),
                                         min_value=75, max_value=100, key=f"{prefix}_lifeexp")
    
    return {
        "name": name,
        "birth_year": int(birth_year),
        "salary": salary,
        "salary_increase": salary_increase,
        "life_expectancy": int(life_expectancy)
    }

# ==================== FORMULAIRE COMPTES FINANCIERS (avec cotisations) ====================
def accounts_form(prefix, initial_acc, initial_contrib):
    """Formulaire pour les comptes financiers avec cotisations intégrées"""
    if initial_acc is None:
        initial_acc = {}
    if initial_contrib is None:
        initial_contrib = {}
    
    accounts_data = {}
    contrib_data = {}
    
    # REER
    with st.expander(f"📋 REER / RRSP", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            accounts_data["REER_balance"] = st.number_input(
                f"{prefix} - Solde REER", 
                value=initial_acc.get("REER_balance", 0.0),
                min_value=0.0, step=1000.0, key=f"{prefix}_reer_bal"
            )
        with col2:
            accounts_data["REER_return"] = st.number_input(
                f"{prefix} - Rendement REER (%)",
                value=initial_acc.get("REER_return", 5.0),
                min_value=-20.0, max_value=20.0, step=0.5, key=f"{prefix}_reer_ret"
            )
        
        st.markdown("**💳 Cotisations REER**")
        col1, col2 = st.columns(2)
        with col1:
            contrib_data["reer_percent"] = st.number_input(
                f"{prefix} - Cotisation REER (% du salaire)",
                value=initial_contrib.get("reer_percent", 10.0),
                min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_reer_pct"
            )
        with col2:
            contrib_data["reer_fixed"] = st.number_input(
                f"{prefix} - Cotisation REER (montant fixe $)",
                value=initial_contrib.get("reer_fixed", 0.0),
                min_value=0.0, step=500.0, key=f"{prefix}_reer_fix"
            )
    
    # CELI
    with st.expander(f"🌱 CELI / TFSA", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            accounts_data["CELI_balance"] = st.number_input(
                f"{prefix} - Solde CELI",
                value=initial_acc.get("CELI_balance", 0.0),
                min_value=0.0, step=1000.0, key=f"{prefix}_celi_bal"
            )
        with col2:
            accounts_data["CELI_return"] = st.number_input(
                f"{prefix} - Rendement CELI (%)",
                value=initial_acc.get("CELI_return", 4.0),
                min_value=-20.0, max_value=20.0, step=0.5, key=f"{prefix}_celi_ret"
            )
        
        st.markdown("**💳 Cotisations CELI**")
        col1, col2 = st.columns(2)
        with col1:
            contrib_data["celi_percent"] = st.number_input(
                f"{prefix} - Cotisation CELI (% du salaire)",
                value=initial_contrib.get("celi_percent", 5.0),
                min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_celi_pct"
            )
        with col2:
            contrib_data["celi_fixed"] = st.number_input(
                f"{prefix} - Cotisation CELI (montant fixe $)",
                value=initial_contrib.get("celi_fixed", 0.0),
                min_value=0.0, step=500.0, key=f"{prefix}_celi_fix"
            )
    
    # CRI
    with st.expander(f"🔒 CRI / LIRA", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            accounts_data["CRI_balance"] = st.number_input(
                f"{prefix} - Solde CRI",
                value=initial_acc.get("CRI_balance", 0.0),
                min_value=0.0, step=1000.0, key=f"{prefix}_cri_bal"
            )
        with col2:
            accounts_data["CRI_return"] = st.number_input(
                f"{prefix} - Rendement CRI (%)",
                value=initial_acc.get("CRI_return", 4.5),
                min_value=-20.0, max_value=20.0, step=0.5, key=f"{prefix}_cri_ret"
            )
        st.caption("💡 Compte immobilisé jusqu'à la retraite")
        
        st.markdown("**💳 Cotisations CRI**")
        col1, col2 = st.columns(2)
        with col1:
            contrib_data["cri_percent"] = st.number_input(
                f"{prefix} - Cotisation CRI (% du salaire)",
                value=initial_contrib.get("cri_percent", 0.0),
                min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_cri_pct"
            )
        with col2:
            contrib_data["cri_fixed"] = st.number_input(
                f"{prefix} - Cotisation CRI (montant fixe $)",
                value=initial_contrib.get("cri_fixed", 0.0),
                min_value=0.0, step=500.0, key=f"{prefix}_cri_fix"
            )
        
    # FERR
    with st.expander(f"🏦 FERR / RRIF", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            accounts_data["FERR_balance"] = st.number_input(
                f"{prefix} - Solde FERR",
                value=initial_acc.get("FERR_balance", 0.0),
                min_value=0.0, step=1000.0, key=f"{prefix}_ferr_bal"
            )
        with col2:
            accounts_data["FERR_return"] = st.number_input(
                f"{prefix} - Rendement FERR (%)",
                value=initial_acc.get("FERR_return", 4.0),
                min_value=-20.0, max_value=20.0, step=0.5, key=f"{prefix}_ferr_ret"
            )
    
    # FRV
    with st.expander(f"💳 FRV / LIF", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            accounts_data["FRV_balance"] = st.number_input(
                f"{prefix} - Solde FRV",
                value=initial_acc.get("FRV_balance", 0.0),
                min_value=0.0, step=1000.0, key=f"{prefix}_frv_bal"
            )
        with col2:
            accounts_data["FRV_return"] = st.number_input(
                f"{prefix} - Rendement FRV (%)",
                value=initial_acc.get("FRV_return", 4.0),
                min_value=-20.0, max_value=20.0, step=0.5, key=f"{prefix}_frv_ret"
            )
    
    # Comptes non-enregistrés
    with st.expander(f"🏪 Compte Non-Enregistré", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            accounts_data["Taxable_balance"] = st.number_input(
                f"{prefix} - Solde Non-Enregistré",
                value=initial_acc.get("Taxable_balance", 0.0),
                min_value=0.0, step=1000.0, key=f"{prefix}_taxable_bal"
            )
        with col2:
            accounts_data["Taxable_return"] = st.number_input(
                f"{prefix} - Rendement (%)",
                value=initial_acc.get("Taxable_return", 3.5),
                min_value=-20.0, max_value=20.0, step=0.5, key=f"{prefix}_taxable_ret"
            )
        
        st.markdown("**💳 Cotisations Non-Enregistré**")
        col1, col2 = st.columns(2)
        with col1:
            contrib_data["nonreg_percent"] = st.number_input(
                f"{prefix} - Cotisation (% du salaire)",
                value=initial_contrib.get("nonreg_percent", 0.0),
                min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_nonreg_pct"
            )
        with col2:
            contrib_data["nonreg_fixed"] = st.number_input(
                f"{prefix} - Cotisation (montant fixe $)",
                value=initial_contrib.get("nonreg_fixed", 0.0),
                min_value=0.0, step=500.0, key=f"{prefix}_nonreg_fix"
            )
    
    return accounts_data, contrib_data

# ==================== FORMULAIRE COTISATIONS ====================
def contributions_form(prefix, initial):
    """Formulaire pour les cotisations annuelles"""
    if initial is None:
        initial = {}
    
    st.markdown(f"### {prefix} - Cotisations annuelles")
    
    contrib_data = {}
    
    col1, col2 = st.columns(2)
    with col1:
        contrib_data["reer_percent"] = st.number_input(
            f"{prefix} - REER (% du salaire)",
            value=initial.get("reer_percent", 10.0),
            min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_reer_pct"
        )
        contrib_data["reer_fixed"] = st.number_input(
            f"{prefix} - REER (montant fixe $)",
            value=initial.get("reer_fixed", 0.0),
            min_value=0.0, step=500.0, key=f"{prefix}_reer_fix"
        )
    
    with col2:
        contrib_data["celi_percent"] = st.number_input(
            f"{prefix} - CELI (% du salaire)",
            value=initial.get("celi_percent", 5.0),
            min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_celi_pct"
        )
        contrib_data["celi_fixed"] = st.number_input(
            f"{prefix} - CELI (montant fixe $)",
            value=initial.get("celi_fixed", 0.0),
            min_value=0.0, step=500.0, key=f"{prefix}_celi_fix"
        )
    
    col1, col2 = st.columns(2)
    with col1:
        contrib_data["cri_percent"] = st.number_input(
            f"{prefix} - CRI (% du salaire)",
            value=initial.get("cri_percent", 0.0),
            min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_cri_pct"
        )
        contrib_data["cri_fixed"] = st.number_input(
            f"{prefix} - CRI (montant fixe $)",
            value=initial.get("cri_fixed", 0.0),
            min_value=0.0, step=500.0, key=f"{prefix}_cri_fix"
        )
    
    with col2:
        contrib_data["nonreg_percent"] = st.number_input(
            f"{prefix} - Non-Enregistré (% du salaire)",
            value=initial.get("nonreg_percent", 0.0),
            min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_nonreg_pct"
        )
        contrib_data["nonreg_fixed"] = st.number_input(
            f"{prefix} - Non-Enregistré (montant fixe $)",
            value=initial.get("nonreg_fixed", 0.0),
            min_value=0.0, step=500.0, key=f"{prefix}_nonreg_fix"
        )
    
    return contrib_data

# ==================== FORMULAIRE RETRAITE ====================
def retirement_form(prefix, initial):
    """Formulaire pour les paramètres de retraite"""
    if initial is None:
        initial = {}
    
    st.markdown(f"### {prefix} - Paramètres de retraite")
    
    retire_data = {}
    
    col1, col2, col3 = st.columns(3)
    with col1:
        retire_data["retirement_age"] = st.number_input(
            f"{prefix} - 🏖️ Âge de retraite",
            value=initial.get("retirement_age", 65),
            min_value=55, max_value=75, key=f"{prefix}_ret_age"
        )
        retire_data["target_income"] = st.number_input(
            f"{prefix} - Revenu net cible (mensuel)",
            value=initial.get("target_income", 5000.0),
            min_value=0.0, step=500.0, key=f"{prefix}_income_target"
        )
    
    with col2:
        retire_data["rrq_age"] = st.number_input(
            f"{prefix} - Âge RRQ/CPP désiré",
            value=initial.get("rrq_age", 65),
            min_value=55, max_value=75, key=f"{prefix}_rrq_age"
        )
        retire_data["rrq_amount_65"] = st.number_input(
            f"{prefix} - RRQ actuel à 65 ans ($/mois)",
            value=initial.get("rrq_amount_65", 1250.0),
            min_value=0.0, step=50.0, key=f"{prefix}_rrq_amount_65"
        )
        retire_data["oas_age"] = st.number_input(
            f"{prefix} - Âge OAS/SRG désiré",
            value=initial.get("oas_age", 65),
            min_value=55, max_value=75, key=f"{prefix}_oas_age"
        )
    
    with col3:
        retire_data["income_indexed"] = st.checkbox(
            f"{prefix} - Revenu indexé à l'inflation",
            value=initial.get("income_indexed", True),
            key=f"{prefix}_indexed"
        )
        retire_data["longevity_buffer"] = st.number_input(
            f"{prefix} - Buffer de longévité",
            value=initial.get("longevity_buffer", 0.0),
            min_value=0.0, max_value=50000.0, step=5000.0, key=f"{prefix}_buffer"
        )
    
    st.markdown("**💰 Stratégie d'utilisation du CELI**")
    celi_opts = [
        "🎯 Optimiser l'impôt (utiliser pour minimiser l'impôt global)",
        "⏳ En dernier recours (garder si possible pour héritage)",
        "🚫 Ne jamais utiliser (100% pour héritiers)"
    ]
    celi_raw = initial.get("celi_strategy", "dernier")
    # Migration: supporter ancien format celi_usage
    if celi_raw not in ["optimiser", "dernier", "jamais"]:
        celi_raw = initial.get("celi_usage", "dernier")
    celi_map = {"optimiser": 0, "dernier": 1, "jamais": 2}
    celi_index = celi_map.get(celi_raw, 1) if isinstance(celi_raw, str) else 1
    celi_selection = st.selectbox(
        f"{prefix} - Stratégie CELI",
        celi_opts,
        index=celi_index,
        key=f"{prefix}_celi_strategy",
        help="Optimiser: utilise le CELI stratégiquement pour réduire l'impôt total sur la retraite. "
             "Dernier recours: utilise seulement si les autres comptes sont épuisés. "
             "Jamais: conserve le CELI intact pour la succession."
    )
    # Convertir en code interne
    celi_reverse_map = {
        "🎯 Optimiser l'impôt (utiliser pour minimiser l'impôt global)": "optimiser",
        "⏳ En dernier recours (garder si possible pour héritage)": "dernier",
        "🚫 Ne jamais utiliser (100% pour héritiers)": "jamais"
    }
    retire_data["celi_strategy"] = celi_reverse_map.get(celi_selection, "dernier")

    st.markdown("**Transfert annuel REER/CRI → FERR/FRV**")
    retire_data["transfer_cap_percent"] = st.number_input(
        f"{prefix} - Plafond de transfert annuel (%)",
        value=initial.get("transfer_cap_percent", 100.0),
        min_value=0.0, max_value=100.0, step=5.0, key=f"{prefix}_transfer_cap"
    )
    
    # ============ RENTE À PRESTATIONS DÉTERMINÉES (PD) ============
    st.markdown("**🏢 Rente à prestations déterminées (PD)**")
    
    col_pd1, col_pd2 = st.columns(2)
    with col_pd1:
        retire_data["rente_pd"] = st.number_input(
            f"{prefix} - Rente PD annuelle (sans pénalité)",
            value=initial.get("rente_pd", 0.0),
            min_value=0.0, step=1000.0, key=f"{prefix}_rente_pd",
            help="Montant annuel de la rente PD si prise à l'âge normal sans pénalité"
        )
        retire_data["rente_pd_age_debut"] = st.number_input(
            f"{prefix} - Âge de début de perception PD",
            value=initial.get("rente_pd_age_debut", 65),
            min_value=55, max_value=75, key=f"{prefix}_pd_age_debut",
            help="Âge choisi pour commencer à percevoir la rente PD"
        )
    
    with col_pd2:
        retire_data["rente_pd_age_normal"] = st.number_input(
            f"{prefix} - Âge normal sans pénalité",
            value=initial.get("rente_pd_age_normal", 65),
            min_value=55, max_value=75, key=f"{prefix}_pd_age_normal",
            help="Âge fixé par le régime pour percevoir la rente sans réduction"
        )
        retire_data["rente_pd_penalite_annuelle"] = st.number_input(
            f"{prefix} - Pénalité annuelle anticipée (%)",
            value=initial.get("rente_pd_penalite_annuelle", 6.0),
            min_value=0.0, max_value=15.0, step=0.5, key=f"{prefix}_pd_penalite",
            help="Réduction appliquée par année si la rente est prise avant l'âge normal (ex: 6% = -6%/an)"
        )
    
    # Afficher un avertissement si pénalité applicable
    if retire_data["rente_pd"] > 0:
        age_debut = retire_data["rente_pd_age_debut"]
        age_normal = retire_data["rente_pd_age_normal"]
        penalite_pct = retire_data["rente_pd_penalite_annuelle"]
        
        if age_debut < age_normal:
            annees_anticipees = age_normal - age_debut
            reduction_totale = annees_anticipees * penalite_pct
            rente_ajustee = retire_data["rente_pd"] * (1 - reduction_totale / 100)
            st.warning(f"⚠️ Retraite anticipée de {annees_anticipees} an(s): réduction de {reduction_totale:.1f}% → Rente ajustée: ${rente_ajustee:,.0f}/an")
        elif age_debut > age_normal:
            st.info(f"ℹ️ Report de {age_debut - age_normal} an(s) après l'âge normal. Vérifiez si votre régime offre une bonification.")
    
    return retire_data

# ==================== FORMULAIRE FISCALITÉ ====================
def tax_form(prefix, initial, province):
    """Formulaire pour les paramètres fiscaux"""
    if initial is None:
        initial = {}
    
    st.markdown(f"### {prefix} - Fiscalité")
    
    tax_data = {}
    
    col1, col2 = st.columns(2)
    with col1:
        tax_data["income_split"] = st.checkbox(
            f"{prefix} - Fractionnement de revenu de pension",
            value=initial.get("income_split", False),
            key=f"{prefix}_split"
        )
        
        if tax_data["income_split"]:
            tax_data["income_split_percent"] = st.slider(
                f"{prefix} - % de revenu fractionné",
                min_value=0, max_value=100, value=initial.get("income_split_percent", 50),
                key=f"{prefix}_split_pct"
            )
    
    with col2:
        tax_data["marital_status"] = st.selectbox(
            f"{prefix} - État matrimonial",
            ["Célibataire", "Marié", "Divorcé", "Veuf"],
            index=initial.get("marital_status", 0),
            key=f"{prefix}_marital"
        )
        
        tax_data["federal_exemption"] = st.number_input(
            f"{prefix} - Montant personnel fédéral",
            value=initial.get("federal_exemption", 15705.0),
            min_value=0.0, step=100.0, key=f"{prefix}_fed_exempt"
        )
    
    with st.expander("✅ Crédits d'impôt fédéraux", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            tax_data["age_credit_eligible"] = st.checkbox(
                f"{prefix} - Admissible au crédit d'âge",
                value=initial.get("age_credit_eligible", False),
                key=f"{prefix}_age_credit"
            )
            tax_data["pension_income_credit"] = st.checkbox(
                f"{prefix} - Crédit pour revenu de pension",
                value=initial.get("pension_income_credit", False),
                key=f"{prefix}_pension_credit"
            )
        
        with col2:
            tax_data["dividend_credit"] = st.checkbox(
                f"{prefix} - Crédit de dividende",
                value=initial.get("dividend_credit", False),
                key=f"{prefix}_div_credit"
            )
            tax_data["caregiver_credit"] = st.checkbox(
                f"{prefix} - Crédit pour personne à charge",
                value=initial.get("caregiver_credit", False),
                key=f"{prefix}_care_credit"
            )
    
    return tax_data

# ==================== FORMULAIRE PROJETS SPÉCIAUX ====================
def special_projects_form(initial):
    """Formulaire pour les projets spéciaux"""
    st.markdown("### 🎯 Projets spéciaux")
    
    projects = initial if isinstance(initial, list) else []
    
    with st.expander("➕ Ajouter un projet", expanded=False):
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            proj_name = st.text_input("Nom du projet", key="new_proj_name")
        with col2:
            proj_year = st.number_input("Année", min_value=2024, max_value=2100, value=2025, key="new_proj_year")
        with col3:
            proj_amount = st.number_input("Montant ($)", min_value=0.0, step=1000.0, key="new_proj_amount")
        with col4:
            proj_person = st.selectbox("Personne", ["P1", "P2", "Couple"], key="new_proj_person")
        
        if st.button("✅ Ajouter le projet"):
            if proj_name and proj_amount > 0:
                projects.append({
                    "name": proj_name,
                    "year": int(proj_year),
                    "amount": proj_amount,
                    "person": proj_person
                })
                st.success(f"✅ Projet '{proj_name}' ajouté!")
    
    if projects:
        st.markdown("**Projets existants:**")
        for i, proj in enumerate(projects):
            col1, col2, col3, col4, col5 = st.columns([2, 1, 1.5, 1.5, 0.5])
            with col1:
                st.write(f"**{proj['name']}**")
            with col2:
                st.write(f"{proj['year']}")
            with col3:
                st.write(f"${proj['amount']:,.0f}")
            with col4:
                st.write(proj['person'])
            with col5:
                if st.button("❌", key=f"delete_proj_{i}"):
                    projects.pop(i)
                    st.rerun()
    
    return projects

# ==================== FORMULAIRE SCÉNARIO (LEGACY) ====================
def scenario_form(initial):
    """Formulaire pour les paramètres du scénario (rétrocompatibilité)"""
    if initial is None:
        initial = {}
    
    col1, col2 = st.columns(2)
    with col1:
        start_year = st.number_input("Année début", value=initial.get("start_year", 2024))
        end_year = st.number_input("Année fin", value=initial.get("end_year", 2055))
    with col2:
        net_target = st.number_input("Cible revenu net", value=initial.get("net_target", 70000.0))
    return {"start_year": start_year, "end_year": end_year, "net_target": net_target}