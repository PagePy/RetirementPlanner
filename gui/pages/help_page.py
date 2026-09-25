"""Page Aide — guide d'utilisation de l'application."""
from nicegui import ui


_SECTIONS: list[tuple[str, str]] = [
    ("🚀 Démarrage rapide", """
1. **Créez votre profil** dans *👤 Profil & Comptes* : ménage, personnes, prestations
   gouvernementales, comptes et cotisations.
2. Ajoutez, si nécessaire, vos **dettes, immeubles, véhicules, dépenses spéciales, rentes
   viagères et assurances** dans *🏠 Actifs & Dettes*.
3. Donnez un **nom au profil** (en-tête) et cliquez **💾 Sauvegarder**. Chaque sauvegarde qui
   change quelque chose crée une version dans l'historique (bouton 🕘 à côté du profil dans
   *📂 Charger*), avec le détail des changements et la possibilité de restaurer.
4. Dans *📈 Résultats*, cliquez **🚀 Lancer la simulation**. Vérifiez la carte **Plan** : ✅ la
   cible est financée chaque année, ⚠️ sinon le nombre d'années sous la cible s'affiche avec
   l'explication (« Pourquoi la cible n'est pas atteinte »).
5. Explorez ensuite *🔬 Analyses* (robustesse, optimisation) et *🎯 Outils* (solveurs).

> Tous les montants saisis sont en **dollars d'aujourd'hui**; la projection les indexe selon
> l'inflation du scénario et les affiche en **dollars courants** de chaque année.
"""),

    ("👤 Profil & Comptes", """
**Ménage et objectif**
- **Couple** : active la deuxième personne, le fractionnement de pension, le partage RRQ et le
  roulement au conjoint au décès.
- **Revenu net cible du ménage** : ce que vous voulez dépenser par année, après impôt, en
  dollars d'aujourd'hui. Cochez **Cible indexée** pour qu'elle suive l'inflation.
- **Stratégie CELI** : *en dernier recours* (retiré seulement quand les autres comptes ne
  suffisent plus) ou *jamais* (préservé pour la succession).
- **Ordre de décaissement** : ordre dans lequel le solveur puise pour combler la cible
  (par défaut non enregistré → REER → FERR → FRV → CELI).
- **Plancher de revenu imposable (fonte du REER)** : si renseigné, chaque année de retraite le
  simulateur retire volontairement du REER/FERR jusqu'à ce revenu imposable par personne et
  réinvestit l'excédent (CELI puis non enregistré). Utilisez *🔬 Analyses → Fonte du REER*
  pour trouver le meilleur plancher.
- **Minimum FERR sur l'âge du conjoint** : réduit le retrait minimum obligatoire.
- **Partage de la rente RRQ** : les deux conjoints (60 ans+) mettent en commun la part de rente
  acquise pendant la vie commune.

**Chaque personne**
- **Date de naissance, âge et mois de retraite, espérance de vie** : l'onglet *🔬 Analyses →
  Longévité* propose l'âge à planifier selon les tables de survie (norme : 25 % de chances
  d'atteindre l'âge choisi).
- **RRQ à 65 ans ($/mois)** : montant indiqué sur votre relevé Retraite Québec. L'âge de début
  (60 à 72) applique les facteurs d'anticipation/report. **SV** : début 65 à 70, années de
  résidence au Canada pour la proratisation.
- **Rente à prestations déterminées (PD)** : choisissez le statut (active, différée, fermée,
  en paiement). Pour un régime actif, saisissez le **relevé annuel** (salaire moyen, années de
  service, taux d'acquisition, moyenne 3 ou 5 ans, coordination RRQ) — la rente est alors
  recalculée jusqu'à la retraite. **Réversible au conjoint** : part versée au survivant après
  le décès (60 % dans la plupart des régimes; 0 = rente sur une seule tête).
- **Emploi à temps partiel après la retraite**, **frais médicaux, dons, maintien à domicile**
  (crédits d'impôt).
- **Comptes** : solde, droits inutilisés, rendement brut, coût fiscal (PBR) du non enregistré
  et répartition intérêts/dividendes/croissance. **Frais de gestion** et **ajustement du
  rendement à la retraite** s'appliquent à tous les comptes de la personne. Le bouton *Normes
  IQPF* remplit les rendements avec les hypothèses de projection normalisées.
- **Cotisations** : en % du salaire ou montant fixe, pour le REER, le REER du conjoint, le
  CELI (avec débordement vers le non enregistré), le CELIAPP, le non enregistré et le régime à
  cotisations déterminées (parts employé/employeur → CRI).
"""),

    ("🏠 Actifs & Dettes", """
- **Passifs** : solde, taux, paiement annuel. Le service de la dette est ajouté à la cible de
  retraite tant que la dette n'est pas éteinte.
- **Actifs réels** : maison, chalet, terrain, immeuble. Appréciation annuelle, résidence
  principale (exonérée) ou non (gain imposable à la vente), **vente prévue** (le produit va au
  non enregistré, la dette liée est remboursée), loyers nets et DPA pour un immeuble locatif.
- **Véhicules** : coût net de remplacement récurrent (indexé), financé par retraits l'année
  venue.
- **Dépenses spéciales** : montants ponctuels (rénovation, voyage, aide aux enfants) ajoutés à
  la cible de l'année.
- **Rentes viagères** : achat d'une rente avec une partie d'un compte à une année donnée;
  *Estimer* propose un versement indicatif selon l'âge; **Réversible (%)** = part maintenue
  au conjoint survivant.
- **Assurances vie** : prime annuelle (payée à même le salaire en accumulation, ajoutée à la
  cible à la retraite) et capital-décès versé libre d'impôt au survivant.
"""),

    ("📈 Résultats", """
**Cartes** : Plan, impôt total à vie, frais de gestion, patrimoine final, valeur nette finale
(placements + immobilier − dettes) et succession nette finale (après impôt au décès).

**Exports** : **⬇️ CSV** (tableau familial + un bloc par personne, valeurs brutes pour Excel) et
**📄 Rapport PDF** (hypothèses, résultats clés, graphiques, sommaire, bilan et projection).

**Sources de revenus vs cible** : barres empilées de toutes les entrées d'argent, ligne noire =
cible, ligne verte = net encaissé après impôt.

**Projection du flux monétaire** — onglets :
- **Familial / par personne** : flux annuel détaillé. *Min. FERR/FRV* = retraits obligatoires;
  *Enregistré* = retraits REER + FERR/FRV au‑delà du minimum; *Net encaissé* doit couvrir
  *Dépenses*; *Insuffisances* = portion non financée; colonnes *Solde …* = fin d'année.
- **Sommaire 5 ans** : flux cumulés par période et taux d'imposition effectif.
- **Bilan** : actif/passif par année, gain latent, assurance en vigueur, impôt au décès et
  succession nette si tous décédaient cette année-là.
- **Cotisations** : ce que vous placez chaque année dans chaque compte, taux d'épargne, cumul,
  droits REER/CELI restants; surplus réinvesti à la retraite.
- **Feuille d'impôt** : déclaration simplifiée (T1/TP‑1) d'une personne pour une année :
  revenus ligne par ligne, tranches indexées, crédits, abattement, récupération SV, taux
  effectif et marginal. À comparer avec un calculateur externe ou votre déclaration réelle.
- **Vérification** : contrôles automatiques — preuve de caisse (tout se boucle à ±1 $),
  rapprochement des soldes avec rendement implicite, et une quinzaine d'invariants (minimums
  FERR/FRV, conversion à 71 ans, âges RRQ/SV, récupération SV, SRG, fractionnement, succession).
  L'onglet s'affiche ⚠️ si un contrôle échoue.
- **Journal** : pour chaque année, les décisions du simulateur (besoin à financer, ordre de
  retrait appliqué et montants par compte, fonte du REER, fractionnement, surplus réinvesti,
  conversions, ventes, achats de rente, décès). Filtre texte et « seulement les années sous la
  cible ». C'est l'endroit où comprendre un résultat surprenant.

**Analyse détaillée** (bas de page) : patrimoine par compte, impôts et succession,
décaissement par compte vs minimums, écart vs cible et surplus, taux effectif/marginal par
personne, prestations gouvernementales, composition du patrimoine (%), décomposition de la
succession.
"""),

    ("🔬 Analyses", """
- **Capacité financière** : dépense mensuelle nette maximale qui épuise les placements à
  l'horizon (ou laisse la succession souhaitée).
- **Tests de stress** : krach, mauvaise séquence de rendements, inflation élevée, longévité,
  décès prématuré — réussite, première année de manque, patrimoine final, impôt à vie.
- **Monte Carlo** : rendements aléatoires (itérations, volatilité) → probabilité de succès et
  percentiles du patrimoine final.
- **Stratégies de décaissement** : compare les ordres de retrait et les stratégies CELI.
- **Fonte du REER** : compare plusieurs planchers de revenu imposable; **Adopter le meilleur
  plancher** l'inscrit dans le profil.
- **D'où vient l'impôt ?** : répartit l'impôt annuel et à vie entre les sources (emploi,
  rentes, RRQ/SV, retraits enregistrés, placements, récupération SV, impôt au décès) pour voir
  quel levier pèse le plus.
- **Longévité** : probabilités de survie et âge de planification recommandé, applicable en un
  clic.
- **Comparaison de scénarios (A/B)** : **📌 Figer le scénario A**, modifiez n'importe quel
  paramètre dans les autres onglets, puis **Comparer A et B** : tableau de 8 indicateurs et
  courbes superposées.
"""),

    ("🎯 Outils", """
- **Objectifs** : revenu net soutenable, épargne annuelle additionnelle requise, âge de
  retraite le plus tôt possible.
- **Âges RRQ / SV** : 18 combinaisons d'âges de début classées par succession nette, cumul des
  rentes et points morts (60 vs 65, 65 vs 70…).
- **Plan suggéré** : courte entrevue → taux d'épargne recommandé et ordre de priorité des
  comptes.
- **Mise de fonds** : CELIAPP vs RAP vs non enregistré pour l'achat d'une première propriété.
- **Coût réel d'un projet** : impact d'une dépense unique sur le patrimoine final et la
  succession.
"""),

    ("🧠 Comment le simulateur raisonne", """
Chaque année, dans l'ordre :
1. **Décès** (au‑delà de l'espérance de vie ou scénario de décès prématuré) : roulement des
   comptes au conjoint sans impôt, rente de survivant RRQ, rentes PD et viagères réversibles,
   capital‑décès.
2. **Conversions** : REER → FERR et CRI → FRV à 71 ans (CRI → FRV dès la retraite après 55 ans).
3. **Croissance** des comptes (nette de frais) et revenus de placement imposables du non
   enregistré.
4. **Revenus** : salaire et cotisations (accumulation), rente PD, RRQ, SV, minimums FERR/FRV,
   temps partiel, loyers, rentes; service de la dette et primes.
5. **Cible de l'année** = cible indexée + dépenses spéciales + dettes + assurance + véhicule
   (au prorata l'année du départ à la retraite).
6. **Solveur de retraits** : puise dans les comptes selon l'ordre choisi, en nivelant les
   revenus imposables des conjoints, jusqu'à ce que le net après impôt atteigne la cible;
   recherche binaire du montant exact.
7. **Fonte du REER** jusqu'au plancher, puis **impôt final** avec fractionnement de pension
   optimal, récupération de la SV, crédits, puis **SRG**.
8. **Surplus** (p. ex. minimum FERR supérieur au besoin) réinvesti au CELI puis au non enregistré.

Les paramètres fiscaux (paliers, crédits, seuils, plafonds) sont ceux de l'année de départ,
indexés à l'inflation du scénario. Un bandeau signale les années dont les valeurs sont encore
estimées.
"""),

    ("❓ Questions fréquentes", """
**La cible n'est pas atteinte certaines années.** Ouvrez « Pourquoi la cible n'est pas
atteinte » puis l'onglet **Journal** de ces années : vous verrez quels comptes ont été vidés et
ce qui manque. Solutions : réduire la cible, reporter la retraite, étaler une dépense
ponctuelle, retarder la RRQ/SV ou activer la fonte du REER.

**Une grosse dépense fait exploser l'impôt d'une année.** Le solveur finance la dépense par
retraits imposables l'année même; envisagez de l'étaler sur deux ans ou de la financer par le
CELI (stratégie « dernier recours » → placez le CELI plus tôt dans l'ordre de retrait).

**Les chiffres sont-ils fiables ?** L'onglet **Vérification** boucle la caisse et les soldes
année par année et contrôle les règles légales; la **Feuille d'impôt** permet de comparer une
année avec un calculateur externe.

**Comparer deux versions de mon plan.** Utilisez *Comparaison de scénarios* (Analyses) ou
l'**historique** des sauvegardes (📂 Charger → 🕘).

**Où sont mes profils ?** Dans le dossier `profiles/` de l'application (fichiers JSON), avec
l'historique dans `profiles/history/<profil>/`.

> Cet outil produit une projection fondée sur vos hypothèses; il ne constitue pas un conseil
> financier, fiscal ou juridique.
"""),
]


def build(state: dict):
    with ui.column().classes("w-full gap-3 max-w-5xl"):
        ui.label("Aide — comment utiliser le planificateur").classes("text-xl font-bold text-primary")
        ui.label("Cliquez sur une section pour la développer.").classes("text-sm text-gray-500")
        for i, (title, body) in enumerate(_SECTIONS):
            with ui.expansion(title, value=(i == 0)).classes("w-full border rounded"):
                ui.markdown(body).classes("text-sm")
