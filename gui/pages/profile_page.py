"""Page Profil — personnes, comptes, cotisations, paramètres de retraite."""
from contextlib import contextmanager

from nicegui import ui

from planner.core.accounts.celi import cumulative_room
from planner.core.assumptions import load_iqpf, portfolio_return, portfolio_labels


DB_STATUS_LABELS = {
    "none": "Aucun régime PD",
    "active": "PD actif",
    "deferred": "PD différé ou gelé",
    "closed_salary_linked": "PD fermé, emploi toujours actif",
    "in_payment": "PD déjà en paiement",
}


def _num(container_dict: dict, key: str, label: str, **kwargs):
    kwargs.setdefault("min", 0)
    return ui.number(label, format="%.0f", **kwargs).bind_value(
        container_dict, key).props("dense outlined").classes("w-40")


def _pct(container_dict: dict, key: str, label: str, **kwargs):
    kwargs.setdefault("min", -50)
    kwargs.setdefault("max", 100)
    return ui.number(label, format="%.2f", suffix="%", **kwargs).bind_value(
        container_dict, key).props("dense outlined").classes("w-36")


def _account_label(label: str):
    ui.label(label).classes("w-36 font-medium text-grey-8")


@contextmanager
def _section(title: str, icon: str):
    """Bloc de sous-section avec en-tête à icône."""
    with ui.card().classes(
            "w-full bg-grey-1 rounded-borders shadow-none "
            "border border-gray-200 gap-2"):
        with ui.row().classes("items-center gap-2"):
            ui.icon(icon).classes("text-primary text-xl")
            ui.label(title).classes("text-base font-semibold text-grey-9")
        yield


def _person_form(p: dict, title: str, state: dict):
    with ui.card().classes("w-full shadow-md rounded-borders"):
        with ui.row().classes(
                "items-center gap-3 w-full bg-primary text-white "
                "rounded-borders px-3 py-2 -mx-1 -mt-1"):
            ui.icon("account_circle").classes("text-2xl")
            ui.label(title).classes("text-lg font-bold")

        with _section("Identité et carrière", "badge"):
            with ui.row().classes("gap-4 flex-wrap"):
                ui.input("Nom").bind_value(p, "name").props("dense outlined") \
                    .classes("w-40")
                ui.select({"F": "Femme", "M": "Homme"}, label="Sexe") \
                    .bind_value(p, "sex").props("dense outlined").classes("w-28") \
                    .tooltip("Sert aux tables de longévité (onglet Analyses).")
                _num(p, "birth_year", "Année de naissance", min=1900, max=2100)
                _num(p, "retirement_age", "Âge de retraite", max=110)
                _num(p, "retirement_month", "Mois de départ (1-12)", min=1, max=12) \
                    .tooltip("1 = retraité toute l'année de l'âge indiqué; 7 = travaille "
                             "de janvier à juin puis retraité (salaire, cotisations et "
                             "cible au prorata).")
                _num(p, "life_expectancy", "Espérance de vie", max=120)
            with ui.row().classes("gap-4 flex-wrap"):
                _num(p, "salary", "Salaire annuel ($)")
                _pct(p, "salary_growth", "Croissance salaire")
                _num(p, "part_time_income", "Emploi après retraite ($/an)") \
                    .tooltip("Revenu d'emploi à temps partiel après la retraite, en "
                             "dollars d'aujourd'hui (indexé). Imposable; exemption SRG appliquée.")
                _num(p, "part_time_until_age", "… jusqu'à l'âge de", max=110)

        with _section("Dépenses donnant droit à des crédits", "receipt_long"):
            ui.label("Montants annuels en dollars d'aujourd'hui (indexés). Ces dépenses "
                     "font partie de votre cible de dépenses; seul le crédit obtenu "
                     "modifie l'impôt.").classes("text-sm text-grey-6")
            with ui.row().classes("gap-4 flex-wrap"):
                _num(p, "medical_expenses", "Frais médicaux ($)") \
                    .tooltip("Crédit fédéral et QC sur la portion au-delà de 3 % du revenu.")
                _num(p, "donations", "Dons de bienfaisance ($)")
                _num(p, "home_support_expenses", "Maintien à domicile ($)") \
                    .tooltip("Crédit remboursable QC à partir de 70 ans (personne autonome).")

        with _section("Prestations gouvernementales", "account_balance"):
            with ui.row().classes("gap-4 flex-wrap"):
                _num(p, "rrq_monthly_at_65", "RRQ à 65 ans ($/mois)")
                _num(p, "rrq_start_age", "Début RRQ (60-72)", min=60, max=72)
                _num(p, "oas_start_age", "Début SV (65-70)", min=65, max=70)
                _num(p, "oas_residence_years", "Années résidence Canada", max=40)

        a = p["accounts"]
        with _section("Comptes — soldes et rendements", "savings"):
            ui.label("Un compte par ligne : solde, rendement attendu et droits disponibles.") \
                .classes("text-sm text-grey-6")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("REER")
                _num(a, "reer_balance", "Solde ($)")
                _pct(a, "reer_return", "Rendement")
                _num(a, "reer_room", "Droits disponibles ($)")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("CELI")
                _num(a, "celi_balance", "Solde ($)")
                _pct(a, "celi_return", "Rendement")
                _num(a, "celi_room", "Droits disponibles ($)") \
                    .tooltip("Droits au 1er janvier de l'année de départ, incluant "
                             "le plafond de cette année (valeur de Mon dossier ARC).")

                def fill_max_room():
                    year = int(state.get("start_year") or 2026)
                    room = cumulative_room(int(p.get("birth_year") or 1970), year)
                    a["celi_room"] = room
                    ui.notify(f"Droits cumulés 2009–{year} si jamais cotisé: "
                              f"{room:,.0f} $. Soustrayez vos cotisations nettes."
                              .replace(",", " "), type="info")

                ui.button("Max", on_click=fill_max_room).props("flat dense") \
                    .tooltip("Remplir avec le cumul des plafonds depuis 2009 "
                             "(à partir de 18 ans), comme si vous n'aviez jamais cotisé.")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("CELIAPP")
                _num(a, "celiapp_balance", "Solde ($)")
                _pct(a, "celiapp_return", "Rendement")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("CRI (immobilisé)")
                _num(a, "cri_balance", "Solde ($)")
                _pct(a, "cri_return", "Rendement")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("FERR")
                _num(a, "ferr_balance", "Solde ($)")
                _pct(a, "ferr_return", "Rendement")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("FRV")
                _num(a, "frv_balance", "Solde ($)")
                _pct(a, "frv_return", "Rendement")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("Non-enregistré")
                _num(a, "taxable_balance", "Solde ($)")
                _pct(a, "taxable_return", "Rendement")
                _num(a, "taxable_acb", "PBR ($, vide = solde)")
            with ui.row().classes("gap-4 flex-wrap items-center pl-40"):
                _pct(a, "taxable_interest_ratio", "Part intérêts")
                _pct(a, "taxable_dividend_ratio", "Part dividendes")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("Frais et phases")
                _pct(a, "fee_rate", "Frais de gestion") \
                    .tooltip("RFG / honoraires annuels soustraits de tous les rendements "
                             "ci-dessus (les rendements saisis sont donc BRUTS).")
                _pct(a, "retirement_return_delta", "Ajust. à la retraite") \
                    .tooltip("Ajouté aux rendements une fois à la retraite, ex. -1 % "
                             "pour un portefeuille plus prudent.")

                def apply_iqpf(portfolio: str):
                    norms = load_iqpf()
                    r = round(portfolio_return(portfolio, norms) * 100, 2)
                    for key in ("reer_return", "celi_return", "celiapp_return",
                                "cri_return", "ferr_return", "frv_return",
                                "taxable_return"):
                        a[key] = r
                    p["salary_growth"] = round(norms["salary_growth"] * 100, 2)
                    state["inflation"] = round(norms["inflation"] * 100, 2)
                    ui.notify(f"Normes IQPF {norms['year']}: rendement brut {r} %, "
                              f"inflation {state['inflation']} %, salaires "
                              f"{p['salary_growth']} %.", type="info")

                with ui.dropdown_button("Normes IQPF", auto_close=True) \
                        .props("flat dense no-caps") \
                        .tooltip("Applique les hypothèses de projection IQPF/FP Canada "
                                 "(rendements bruts selon le portefeuille, inflation, "
                                 "croissance des salaires). Soustrayez vos frais."):
                    for key, label in portfolio_labels().items():
                        ui.item(label, on_click=lambda k=key: apply_iqpf(k))

        c = p["contributions"]
        with _section("Cotisations annuelles (accumulation)", "trending_up"):
            ui.label("Les montants fixes s'ajoutent aux cotisations calculées en pourcentage du salaire.") \
                .classes("text-sm text-grey-6")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("REER")
                _pct(c, "reer_pct", "% salaire")
                _num(c, "reer_fixed", "Montant fixe ($)")
            with ui.row().classes("gap-4 flex-wrap items-center") \
                    .bind_visibility_from(state, "is_couple"):
                _account_label("REER de conjoint")
                _pct(c, "spousal_reer_pct", "% salaire")
                _num(c, "spousal_reer_fixed", "Montant fixe ($)") \
                    .tooltip("Cotisé par cette personne (ses droits, sa déduction) dans le "
                             "REER du conjoint. Les retraits du conjoint dans les 3 ans "
                             "d'une cotisation sont réattribués au cotisant.")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("CELI")
                _pct(c, "celi_pct", "% salaire")
                _num(c, "celi_fixed", "Montant fixe ($)")
                ui.checkbox("Indexer le montant fixe").bind_value(c, "celi_fixed_indexed") \
                    .tooltip("Le montant fixe augmente chaque année selon l'inflation.")
                ui.checkbox("Excédent vers non-enregistré") \
                    .bind_value(c, "celi_overflow_to_taxable") \
                    .tooltip("La part qui dépasse les droits CELI est investie dans le "
                             "compte non-enregistré au lieu d'être dépensée.")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("CELIAPP")
                _num(c, "celiapp_fixed", "Montant fixe ($)")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _account_label("Non-enregistré")
                _pct(c, "taxable_pct", "% salaire")
                _num(c, "taxable_fixed", "Montant fixe ($)")

        with _section("Rente d'employeur (PD)", "work"):
            ui.select(DB_STATUS_LABELS, label="Statut du régime PD") \
                .bind_value(p, "db_status").props("dense outlined").classes("w-72") \
                .tooltip("Choisissez le statut qui décrit le régime aujourd'hui.")
            with ui.expansion("Comment choisir le statut de la rente PD ?", icon="help_outline") \
                    .classes("w-full max-w-3xl text-sm"):
                ui.label("Aucun régime PD: la personne n'a pas de rente à prestations "
                         "déterminées à recevoir.")
                ui.label("PD actif: la personne participe toujours au régime; sa rente "
                         "continue d'augmenter grâce au service et/ou au salaire.")
                ui.label("PD différé ou gelé: la personne a quitté l'employeur ou le "
                         "régime est fermé; la rente accumulée n'augmente plus avant son "
                         "début, sauf règle d'indexation particulière du régime.")
                ui.label("PD fermé, emploi toujours actif: la personne travaille encore "
                         "pour l'employeur, mais n'accumule plus de service. La rente peut "
                         "encore augmenter si la formule utilise les meilleures années de salaire.")
                ui.label("PD déjà en paiement: la personne reçoit déjà cette rente. Entrez "
                         "le montant annuel reçu aujourd'hui; aucune pénalité anticipée n'est "
                         "appliquée.")
                ui.label("Croissance PD active sert seulement au statut PD actif. Pour le "
                         "statut fermé avec emploi actif, le logiciel utilise plutôt la "
                         "croissance du salaire.").classes("text-gray-600")
            with ui.row().classes("gap-4 flex-wrap items-center"):
                _num(p, "db_pension", "Rente annuelle estimée ($)")
                _num(p, "db_start_age", "Âge de début", max=110)
                _num(p, "db_normal_age", "Âge normal (sans pénalité)", max=110)
                _pct(p, "db_penalty", "Pénalité/an anticipé")
                _pct(p, "db_active_growth", "Croissance PD active")
                ui.checkbox("Rente indexée une fois en paiement") \
                    .bind_value(p, "db_indexed")

        with _section("Régime CD (alimente le CRI unique)", "domain"):
            ui.label("Les cotisations en % sont recalculées chaque année sur le "
                     "salaire annuel courant.") \
                .classes("text-sm text-gray-500")
            with ui.row().classes("gap-4 flex-wrap"):
                _pct(c, "dc_employee_pct", "CD employé % salaire")
                _num(c, "dc_employee_fixed", "CD employé fixe annuel ($)")
                _pct(c, "dc_employer_pct", "CD employeur % salaire")
                _num(c, "dc_employer_fixed", "CD employeur fixe annuel ($)")


def build(state: dict):
    state.setdefault("persons_side_by_side", False)
    persons_box = None

    def apply_layout():
        if persons_box is None:
            return
        side = state["is_couple"] and state["persons_side_by_side"]
        persons_box.classes(replace="w-full grid gap-4 items-start " + (
            "grid-cols-2" if side else "grid-cols-1"))

    with ui.column().classes("w-full gap-4"):
        with ui.card().classes("w-full shadow-md rounded-borders"):
            with ui.row().classes(
                    "items-center gap-3 w-full bg-secondary text-white "
                    "rounded-borders px-3 py-2 -mx-1 -mt-1"):
                ui.icon("diversity_3").classes("text-2xl")
                ui.label("Ménage et objectif").classes("text-lg font-bold")
            with ui.row().classes("gap-6 items-center flex-wrap"):
                ui.switch("Couple", on_change=lambda _: apply_layout()) \
                    .bind_value(state, "is_couple")
                ui.toggle({False: "L'une sous l'autre", True: "Côte à côte"},
                          on_change=lambda _: apply_layout()) \
                    .bind_value(state, "persons_side_by_side") \
                    .bind_visibility_from(state, "is_couple") \
                    .props("dense no-caps") \
                    .tooltip("Disposition des fiches Personne 1 et Personne 2")
                ui.select(["QC"], label="Province").bind_value(
                    state, "province").props("dense outlined").classes("w-28")
                ui.number("Revenu net cible du ménage ($/an)", format="%.0f") \
                    .bind_value(state, "target_net_income") \
                    .props("dense outlined").classes("w-56")
                ui.switch("Cible indexée à l'inflation").bind_value(
                    state, "target_indexed")
            with ui.row().classes("gap-6 items-center flex-wrap"):
                ui.select({"dernier": "CELI en dernier recours",
                           "jamais": "CELI jamais (succession)"},
                          label="Stratégie CELI").bind_value(
                    state, "celi_strategy").props("dense outlined").classes("w-64")
                ui.number("Inflation (%)", format="%.1f").bind_value(
                    state, "inflation").props("dense outlined").classes("w-32")
                ui.number("Année de départ", format="%.0f").bind_value(
                    state, "start_year").props("dense outlined").classes("w-32")
                ui.number("Plancher revenu imposable ($/pers.)", format="%.0f", min=0) \
                    .bind_value(state, "taxable_income_floor") \
                    .props("dense outlined clearable").classes("w-64") \
                    .tooltip("Fonte du REER: chaque année de retraite, retraits REER/FERR "
                             "volontaires jusqu'à ce revenu imposable (dollars d'aujourd'hui), "
                             "excédent réinvesti. Vide = aucun. Voir l'onglet Analyses pour "
                             "comparer les planchers.")
                ui.switch("Minimum FERR sur l'âge du conjoint").bind_value(
                    state, "use_spouse_age_for_ferr") \
                    .tooltip(
                        "Calcule le retrait MINIMUM obligatoire du FERR/FRV sur "
                        "l'âge du conjoint le plus jeune plutôt que le vôtre. "
                        "Si le conjoint est plus jeune, le minimum forcé est "
                        "plus bas : moins d'impôt, plus d'argent à l'abri et "
                        "moins de récupération de la SV. Choix irrévocable fait "
                        "à l'ouverture du FERR ; aucun effet sans conjoint plus jeune.")
            with ui.row().classes("gap-6 items-center flex-wrap") \
                    .bind_visibility_from(state, "is_couple"):
                ui.switch("Partage de la rente RRQ").bind_value(state, "rrq_sharing") \
                    .tooltip("Les deux conjoints ont 60 ans+ et reçoivent leur rente (ou "
                             "n'en ont pas): la part acquise pendant la vie commune est "
                             "divisée à parts égales, ce qui réduit l'impôt quand les "
                             "rentes sont inégales.")
                ui.number("Part acquise en vie commune (%)", format="%.0f",
                          min=0, max=100) \
                    .bind_value(state, "rrq_share_fraction") \
                    .bind_visibility_from(state, "rrq_sharing") \
                    .props("dense outlined").classes("w-56")

        with ui.element("div") as persons_box:
            with ui.column().classes("w-full min-w-0"):
                _person_form(state["persons"][0], "Personne 1", state)
            with ui.column().classes("w-full min-w-0") \
                    .bind_visibility_from(state, "is_couple"):
                _person_form(state["persons"][1], "Personne 2", state)
        apply_layout()
